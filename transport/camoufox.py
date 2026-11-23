#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Shared import-scoped adapter for Calibre's optional Camoufox recipe browser.

Maintenance notes:
- Calibre 9.16 introduced the browser API used here. Imports stay lazy so the
  plugin continues to load on its declared Calibre 6.0 minimum.
- ``Browser.open()`` blocks its calling thread. Fetches therefore run on a
  background thread while the caller polls a main-thread callback for Qt event
  processing and cancellation.
- The adapter returns decoded rendered HTML. Parsers must not import or depend
  on Camoufox directly.
"""

import queue
import threading
import time
from contextlib import contextmanager
from functools import wraps

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.errors import (
    ImportCancelledError, CamoufoxError, CamoufoxUnavailableError,
    CamoufoxSkippedError, CamoufoxFetchError, CamoufoxChallengeError,
    CamoufoxRequiredError,
  )
except ImportError:
  from errors import (
    ImportCancelledError, CamoufoxError, CamoufoxUnavailableError,
    CamoufoxSkippedError, CamoufoxFetchError, CamoufoxChallengeError,
    CamoufoxRequiredError,
  )


MINIMUM_CAMOUFOX_VERSION = (9, 16, 0)
DEFAULT_CAMOUFOX_TIMEOUT = 60
DEFAULT_RESPONSE_MAX_BYTES = 10 * 1024 * 1024
POLL_INTERVAL_SECONDS = 0.1
SHUTDOWN_JOIN_SECONDS = 2.0
STARTUP_ALLOWANCE_SECONDS = 300
# Calibre can recover a timed-out navigation with a ten-second DOM-ready wait
# before serializing the response. The outer watchdog must let that finish.
RESPONSE_GRACE_SECONDS = 15


@contextmanager
def browser_operation(owner):
  """Nested import ownership; standalone fetch/match/lookup calls also close.

  The outer import spans fetch and automatic matching, but explicitly closes
  before modal review. Nested phases must not reset the failure circuit breaker.
  Only small parsed lookup results live in this scope, never response bodies.
  """
  depth = getattr(owner, '_browser_operation_depth', 0)
  if not depth:
    owner._camoufox_disabled_reason = ''
    owner.goodreads_series_cache = {}
    owner.last_goodreads_lookup_time = 0
  owner._browser_operation_depth = depth + 1
  try:
    yield
  finally:
    owner._browser_operation_depth = depth
    if not depth:
      try:
        close = getattr(owner, 'close_camoufox_transport', None)
        if close is not None:
          close()
      finally:
        owner.goodreads_series_cache = {}


def with_browser_operation(method):
  @wraps(method)
  def scoped(self, *args, **kwargs):
    with browser_operation(self):
      return method(self, *args, **kwargs)
  return scoped

BROWSER_FALLBACK_CHOICES = (
  (0, 'Off - automatic'),
  (1, 'Level 1 - Camoufox, then legacy fetching'),
  (2, 'Level 2 - legacy fetching only'),
)


def browser_fallback_level(preferences):
  """Read the shared setting, falling back to the saved LibraryThing pilot mode."""
  value = preferences.get('debug_browser_fallback_level')
  if value is None:
    return {'automatic': 0, 'camoufox': 1, 'old': 2}.get(
      preferences.get('debug_librarything_transport', 'automatic'), 0)
  try:
    level = int(value)
  except (TypeError, ValueError):
    return 0
  return level if level in (0, 1, 2) else 0


def calibre_version_tuple():
  try:
    from calibre.constants import numeric_version
  except Exception:
    return ()
  try:
    return tuple(int(part) for part in numeric_version[:3])
  except Exception:
    return ()


def format_version(version):
  return '.'.join(str(part) for part in version) if version else 'unknown'


def camoufox_capability():
  """Return ``(available, version, reason)`` without importing at module load."""
  version = calibre_version_tuple()
  if not version or version < MINIMUM_CAMOUFOX_VERSION:
    return False, version, 'Calibre 9.16 or newer is required'
  try:
    from calibre.web.automate.recipes import Browser
  except Exception as err:
    return False, version, f'Camoufox browser API is unavailable: {err}'
  return True, version, Browser


def is_challenge_payload(payload):
  """Recognize common bot-verification documents without source parsing."""
  text = (payload or '').casefold()
  markers = (
    '<title>just a moment',
    '/cdn-cgi/challenge-platform/',
    'cf-chl-',
    'cf-turnstile',
    'checking your browser before accessing',
    'verify you are human',
    'performing security verification',
    'attention required! | cloudflare',
    'sorry, you have been blocked',
  )
  if not any(marker in text for marker in markers):
    return False
  soup = BeautifulSoup(payload, 'html.parser')
  title = soup.title.get_text(' ', strip=True).casefold() if soup.title else ''
  if title.startswith(('just a moment', 'security verification', 'verify you are human')):
    return True
  # Cloudflare also injects challenge scripts into usable LibraryThing pages.
  # A real award table takes precedence over those background script markers.
  for table in soup.find_all('table'):
    headers = {cell.get_text(' ', strip=True).casefold() for cell in table.find_all('th')}
    if {'work', 'year'} <= headers and table.find('a', href=lambda href: href and '/work/' in href):
      return False
  return True


def response_content_length(response):
  try:
    # Calibre synthesizes email headers lazily; repeated remote header values
    # can make that property raise even when rendered HTML is readable. The
    # bounded body read below still enforces the limit without Content-Length.
    headers = getattr(response, 'headers', None)
    if headers is None:
      return None
    value = headers.get('Content-Length')
    return int(value) if value is not None else None
  except (AttributeError, TypeError, ValueError):
    return None


def read_limited_response(response, max_bytes):
  max_bytes = int(max_bytes or DEFAULT_RESPONSE_MAX_BYTES)
  content_length = response_content_length(response)
  if content_length is not None and content_length > max_bytes:
    raise CamoufoxFetchError(
      f'Remote response is {content_length} bytes, exceeding the '
      f'{max_bytes}-byte limit.')
  data = response.read(max_bytes + 1)
  if len(data) > max_bytes:
    raise CamoufoxFetchError(
      f'Remote response exceeds the {max_bytes}-byte limit.')
  return data


class CamoufoxTransport:
  """Own one sequential Camoufox browser for a single recipe import."""

  def __init__(
      self, log=None, wait_callback=None, browser_factory=None,
      poll_interval=POLL_INTERVAL_SECONDS, source_name='LibraryThing',
      warmup_excluded_domains=('librarything.com',), check_challenges=True):
    self.log = log
    self.wait_callback = wait_callback
    self.browser_factory = browser_factory
    self.poll_interval = float(poll_interval)
    self.source_name = source_name
    self.warmup_excluded_domains = tuple(warmup_excluded_domains)
    self.check_challenges = bool(check_challenges)
    self.browser = None
    self.closed = False
    self.shutdown_started = False
    self._browser_lock = threading.RLock()
    self._active_thread = None

  def _log(self, message):
    if self.log is not None:
      self.log(message)

  def _factory(self):
    if self.browser_factory is not None:
      return self.browser_factory
    available, version, result = camoufox_capability()
    if not available:
      raise CamoufoxUnavailableError(
        f'Camoufox unavailable on Calibre {format_version(version)}: {result}')
    return result

  def _browser(self):
    with self._browser_lock:
      if self.closed:
        raise CamoufoxFetchError('Camoufox transport is closed')
      if self.browser is not None:
        self._log('reusing import-scoped browser')
        return self.browser
    # Do not hold the lifecycle lock across initialization: cancellation must
    # return promptly even if a future Calibre browser constructor blocks.
    self._log('initializing browser (first use may download browser data)')
    browser = self._factory()(
      headless=True,
      start_worker=True,
      warmup=True,
      warmup_excluded_domains=self.warmup_excluded_domains,
      max_tabs=1,
      block_images=True,
      verify_ssl_certificates=True)
    try:
      # Worker creation can return before warmup finishes. This harmless query
      # waits for readiness without charging browser setup to the first page.
      user_agent = getattr(browser, 'user_agent', None)
      if callable(user_agent):
        user_agent()
    except BaseException:
      browser.shutdown()
      raise
    with self._browser_lock:
      closed = self.closed
      if not closed:
        self.browser = browser
    if closed:
      browser.shutdown()
      raise CamoufoxFetchError('Camoufox transport closed during initialization')
    return browser

  def _fetch_blocking(self, url, timeout, max_bytes):
    browser = self._browser()
    started = time.monotonic()
    response = browser.open(url, timeout=timeout, as_document=True)
    try:
      data = read_limited_response(response, max_bytes)
      html = data.decode('utf-8', 'replace')
      final_url = getattr(response, 'geturl', lambda: url)() or url
      status = getattr(response, 'status', getattr(response, 'code', 0)) or 0
    finally:
      close = getattr(response, 'close', None)
      if close is not None:
        close()
    elapsed = time.monotonic() - started
    self._log(
      f'fetch completed url={url} final_url={final_url} status={status} '
      f'bytes={len(data)} seconds={elapsed:.1f}')
    if self.check_challenges and is_challenge_payload(html):
      self._log(f'challenge payload detected url={url}')
      raise CamoufoxChallengeError(
        f'{self.source_name} returned a browser verification page through Camoufox.')
    return html

  def fetch(
      self, url, timeout=DEFAULT_CAMOUFOX_TIMEOUT,
      max_bytes=DEFAULT_RESPONSE_MAX_BYTES, wait_message=None):
    """Fetch rendered HTML while keeping the calling GUI thread responsive."""
    if self.closed:
      raise CamoufoxFetchError('Camoufox transport is closed')
    results = queue.Queue(maxsize=1)

    def run():
      try:
        results.put((True, self._fetch_blocking(url, timeout, max_bytes)))
      except BaseException as err:
        results.put((False, err))

    self._log(f'fetch starting url={url} timeout={timeout} max_bytes={max_bytes}')
    thread = threading.Thread(
      target=run, name='ListSwitchboardCamoufoxFetch', daemon=True)
    self._active_thread = thread
    starting_browser = self.browser is None
    deadline = time.monotonic() + (
      STARTUP_ALLOWANCE_SECONDS if starting_browser else float(timeout) + RESPONSE_GRACE_SECONDS)
    thread.start()
    try:
      while True:
        # Browser publication ends startup; every page gets only its own timeout.
        if starting_browser and self.browser is not None:
          starting_browser = False
          deadline = time.monotonic() + float(timeout) + RESPONSE_GRACE_SECONDS
        message = wait_message or (
          f'Starting Camoufox for {self.source_name}; first use may download browser data...'
          if starting_browser else f'Loading {self.source_name} page with Camoufox...')
        if self.wait_callback is not None:
          self.wait_callback(message)
        if not thread.is_alive():
          break
        if time.monotonic() >= deadline:
          self.close()
          stage = 'browser startup' if starting_browser else 'request'
          raise CamoufoxFetchError(f'Camoufox {stage} exceeded its time limit.')
        thread.join(self.poll_interval)
    except ImportCancelledError:
      self._log(f'fetch cancelled url={url}')
      self.close()
      thread.join(SHUTDOWN_JOIN_SECONDS)
      raise
    finally:
      self._active_thread = None
    succeeded, value = results.get()
    if succeeded:
      return value
    if isinstance(value, ImportCancelledError):
      raise value
    if isinstance(value, CamoufoxError):
      raise value
    raise CamoufoxFetchError(str(value) or value.__class__.__name__) from value

  def close(self):
    """Start one bounded browser shutdown; safe on every import exit path."""
    with self._browser_lock:
      if self.shutdown_started:
        self.closed = True
        return
      self.shutdown_started = True
      self.closed = True
      browser = self.browser
    if browser is None:
      return

    finished = threading.Event()

    def shutdown():
      try:
        browser.shutdown()
      except Exception as err:
        self._log(f'browser shutdown failed: {err}')
      finally:
        finished.set()

    self._log('shutting down import-scoped browser')
    thread = threading.Thread(
      target=shutdown, name='ListSwitchboardCamoufoxShutdown', daemon=True)
    thread.start()
    if not finished.wait(SHUTDOWN_JOIN_SECONDS):
      self._log('browser shutdown is continuing in the background')
