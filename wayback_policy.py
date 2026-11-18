"""One process-wide request clock for the plugin's Wayback transports.

Request processors run for redirect hops as well as initial requests. Waiting
never holds the clock lock, so UI event processing and cancellation can reenter
the importer safely. Native HTTPS callers disable automatic redirects and let
the paced legacy transport follow them instead. Every 429 doubles the shared
gap for this process lifetime. Installed response processors own that notification;
the core reports exceptions only for transports without those processors.
"""

from datetime import timezone
from email.utils import parsedate_to_datetime
import math
from threading import Lock
import time
from urllib.parse import urlsplit
from urllib.request import BaseHandler, build_opener


MIN_INTERVAL_SECONDS = 10.0
RATE_LIMIT_SECONDS = 60.0


def is_wayback_url(url):
  target = urlsplit(str(url))
  return target.scheme in ('http', 'https') and (target.hostname or '').casefold().rstrip('.') == 'web.archive.org'


class WaybackRequestClock:

  def __init__(self, interval=MIN_INTERVAL_SECONDS, clock=None, wall_clock=None):
    self.interval = interval
    self.clock = clock or time.monotonic
    self.wall_clock = wall_clock or time.time
    self.lock = Lock()
    self.next_request = 0.0

  def wait(self, url, sleep=None):
    if not is_wayback_url(url):
      return
    while True:
      with self.lock:
        now = self.clock()
        delay = self.next_request - now
        if delay <= 0:
          self.next_request = now + self.interval
          return
      if sleep is not None:
        sleep(delay)
      else:
        time.sleep(min(delay, 0.1))

  def limited(self, url, headers=None):
    if not is_wayback_url(url):
      return
    delay = RATE_LIMIT_SECONDS
    value = (headers or {}).get('Retry-After')
    if value is None and headers is not None:
      value = next((value for name, value in headers.items() if name.casefold() == 'retry-after'), None)
    if value is not None:
      try:
        seconds = float(value)
        if math.isfinite(seconds) and seconds >= 0:
          delay = seconds
      except (TypeError, ValueError):
        try:
          when = parsedate_to_datetime(str(value))
          if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
          delay = max(0, when.timestamp() - self.wall_clock())
        except (TypeError, ValueError, OverflowError):
          pass
    with self.lock:
      self.interval *= 2
      delay = max(self.interval, delay)
      self.next_request = max(self.next_request, self.clock() + delay)


REQUEST_CLOCK = WaybackRequestClock()


def wait_for_wayback(url, sleep=None):
  REQUEST_CLOCK.wait(url, sleep)


def note_wayback_error(url, error):
  if getattr(error, 'code', None) in (429, '429'):
    REQUEST_CLOCK.limited(url, getattr(error, 'headers', None))


def pacing_handler(base, sleep=None):
  class WaybackHandler(base):
    handler_order = 10

    def http_request(self, request):
      wait_for_wayback(request.get_full_url(), sleep)
      return request

    https_request = http_request

    def http_response(self, request, response):
      if getattr(response, 'code', None) == 429:
        REQUEST_CLOCK.limited(request.get_full_url(), getattr(response, 'headers', None))
      return response

    https_response = http_response
  return WaybackHandler()


def install_browser_pacing(browser, sleep=None):
  if getattr(browser, '_list_switchboard_wayback_pacing', False) is True:
    return True
  if not callable(getattr(browser, 'add_handler', None)):
    return False
  try:
    from mechanize import BaseHandler as MechanizeBaseHandler
  except ImportError:
    MechanizeBaseHandler = BaseHandler
  browser.add_handler(pacing_handler(MechanizeBaseHandler, sleep))
  browser._list_switchboard_wayback_pacing = True
  return True


def paced_urlopen(request, timeout, sleep=None):
  return build_opener(pacing_handler(BaseHandler, sleep)).open(request, timeout=timeout)


def paced_native_https(fetch, url, sleep=None, **kwargs):
  wait_for_wayback(url, sleep)
  # The Calibre helper otherwise follows redirects internally without a hook.
  # A redirected response falls back to the browser, whose every hop is paced.
  kwargs['max_redirects'] = 0
  try:
    return fetch(url, **kwargs)
  except Exception as err:
    note_wayback_error(url, err)
    raise
