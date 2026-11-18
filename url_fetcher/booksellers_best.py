#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from urllib.parse import urlsplit

try:
  from calibre.utils.https import get_https_resource_securely as calibre_https_fetch
except ImportError:
  calibre_https_fetch = None

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError
  from calibre_plugins.list_switchboard.http_policy import random_user_agent
  from calibre_plugins.list_switchboard.parser.booksellers_best import BOOKSELLERS_BEST_CDX_URL
  from calibre_plugins.list_switchboard.wayback_policy import paced_native_https, wait_for_wayback
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError
  from http_policy import random_user_agent
  from parser.booksellers_best import BOOKSELLERS_BEST_CDX_URL
  from wayback_policy import paced_native_https, wait_for_wayback

from .generic import (
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_ROMANCE,
  UrlFetcherGeneric,
  UrlFetcherError,
)


def archive_rate_limit(error):
  """Find typed HTTP 429 responses without interpreting source text as status."""
  pending, seen = [error], set()
  while pending:
    current = pending.pop()
    if id(current) in seen:
      continue
    seen.add(id(current))
    if getattr(current, 'code', None) in (429, '429'):
      return current
    for attribute in ('reason', '__cause__', '__context__'):
      nested = getattr(current, attribute, None)
      if isinstance(nested, BaseException):
        pending.append(nested)
  return None


class UrlFetcherBooksellersBestAward(UrlFetcherGeneric):

  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'booksellers_best_award'
  NAME = "Booksellers' Best Award"
  URL = BOOKSELLERS_BEST_CDX_URL
  DISPLAY_URL = 'https://web.archive.org/web/*/http://www.gdrwa.org/contests.html'
  order = 255
  options = {'match_series': False}
  FILTER_CATEGORIES = (CATEGORY_ROMANCE, CATEGORY_REGIONAL_NATIONAL_AWARDS)

  @property
  def display_url(self):
    return self.DISPLAY_URL

  def request_timeout(self, url):
    target = urlsplit(url)
    if target.scheme == 'https' and target.hostname == 'web.archive.org' and target.path == '/cdx/search/cdx':
      return 60
    return super().request_timeout(url)

  def fetch_url(self, fetch_url, url):
    owner = getattr(fetch_url, '__self__', None)
    pause = getattr(self, '_wayback_sleep', None)
    if pause is None and callable(getattr(owner, 'sleep_with_events', None)):
      pause = lambda seconds: owner.sleep_with_events(seconds, 'Waiting before the next Internet Archive request...')
    def legacy():
      if getattr(owner, 'PACES_WAYBACK_REQUESTS', False) is not True:
        wait_for_wayback(url, pause)
      return super(UrlFetcherBooksellersBestAward, self).fetch_url(fetch_url, url)
    target = urlsplit(url)
    if (calibre_https_fetch is None or target.scheme != 'https'
        or target.hostname != 'web.archive.org'
        or not (target.path == '/cdx/search/cdx' or target.path.startswith('/web/'))):
      return legacy()
    try:
      # Some archived captures advertise gzip over an already decoded HTML body.
      # Calibre's native HTTPS helper can read the same URL with identity encoding.
      payload = paced_native_https(calibre_https_fetch, url, sleep=pause, cacerts=None,
        timeout=self.request_timeout(url) or 30, headers={
        'User-Agent': random_user_agent(), 'Accept-Encoding': 'identity'})
      if not isinstance(payload, (bytes, str)) or len(payload) > 16 * 1024 * 1024:
        raise ValueError('Wayback response is invalid or exceeds 16 MiB.')
      return payload
    except (ImportCancelledError, CamoufoxRequiredError):
      raise
    except Exception as err:
      if archive_rate_limit(err) is not None:
        raise
      return legacy()

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.booksellers_best import ( # type: ignore
        BooksellersBestAwardParser,
      )
    except ImportError:
      from parser.booksellers_best import BooksellersBestAwardParser
    return BooksellersBestAwardParser()

  def fetch_and_parse(self,fetch_url,sleep=None,fetch_error=None,log=None,progress=None,
      before_fetch=None,after_fetch=None,before_parse=None,force_fallback_level=0,
      disable_fallbacks=False,source_choice=None,cached_parsed=None,incremental_update=False):
    if source_choice not in (None,'automatic',0,'0') or (int(force_fallback_level or 0)>0 and not disable_fallbacks):
      raise UrlFetcherError('No URL fallback exists for the selected source.')
    try:
      from calibre_plugins.list_switchboard.parser.booksellers_best_updates import fetch_booksellers_best
    except ImportError:
      from parser.booksellers_best_updates import fetch_booksellers_best
    rate_limited = None
    self._wayback_sleep = sleep
    def read(url):
      nonlocal rate_limited
      if rate_limited is not None:
        raise UrlFetcherError(
          'Wayback returned HTTP 429; remaining archive requests were deferred until a later import.') from rate_limited
      if before_fetch is not None:before_fetch(url)
      try:
        html=self.fetch_url(fetch_url,url)
      except (ImportCancelledError, CamoufoxRequiredError):
        raise
      except Exception as err:
        # A rate-limited archive must not receive another transport attempt or
        # the remainder of a multi-capture batch during this import.
        rate_limited = archive_rate_limit(err)
        raise
      if after_fetch is not None:after_fetch(url,html)
      if before_parse is not None:before_parse(url)
      return html
    try:
      parsed=fetch_booksellers_best(self.parser(),read,self.URL,self.NAME,
        cached_parsed,incremental_update,progress=progress)
    finally:
      self._wayback_sleep = None
    if not parsed.get('entries'):
      raise UrlFetcherError('Could not fetch or parse the imported list.')
    return parsed

  def parse(self, html, fetch_url=None,cached_parsed=None,incremental_update=False, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME, fetch_url=fetch_url,
      cached_parsed=cached_parsed,incremental_update=incremental_update)
