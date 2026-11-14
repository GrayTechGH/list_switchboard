#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""r/Fantasy result recipes with browser/legacy recovery per live source.

Maintenance notes:
- Source choices and ranks remain old Reddit, Wayback, and www Reddit.
- Validate Camoufox output before accepting it; an HTTP 200 interstitial
  must retry legacy at the same URL before advancing to another source.
- Wayback stays legacy-only. Browser failure suppression is per import.
"""

from urllib.parse import urlparse

from .generic import (
  CATEGORY_FANTASY,
  CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
  UrlFetcherGeneric,
)

try:
  from calibre_plugins.list_switchboard.errors import (
    CamoufoxRequiredError, CamoufoxSkippedError, ImportCancelledError,
  )
except ImportError:
  from errors import CamoufoxRequiredError, CamoufoxSkippedError, ImportCancelledError


class UrlFetcherReddit(UrlFetcherGeneric):

  FILTER_CATEGORIES = (
    CATEGORY_FANTASY,
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
  )
  WAYBACK_URL = ''
  WAYBACK_CAPTURE_DATE = ''
  WAYBACK_MARKER = '<!-- list-switchboard-r-fantasy-wayback -->'

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.reddit import RedditResultsParser
    except ImportError:
      from parser.reddit import RedditResultsParser

    return RedditResultsParser()

  def fetch_and_parse(
      self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
      before_fetch=None, after_fetch=None, before_parse=None,
      force_fallback_level=0, disable_fallbacks=False, source_choice=None,
      cached_parsed=None, incremental_update=False):
    browser_failed = False
    owner = getattr(fetch_url, '__self__', None)

    def report(message):
      if log is not None:
        log(message)
      browser_log = getattr(owner, 'debug_camoufox', None)
      if browser_log is not None:
        browser_log(message)

    def browser_first(url, **options):
      nonlocal browser_failed
      host = (urlparse(url).hostname or '').casefold()
      if not browser_failed and (host == 'reddit.com' or host.endswith('.reddit.com')):
        try:
          report(f'{self.NAME} transport=Camoufox url={url}')
          if progress is not None:
            progress(0, 1, f'Fetching {self.NAME} via Camoufox...')
          try:
            payload = fetch_url(url, transport='camoufox', **options)
          except TypeError as err:
            if 'transport' not in str(err) and 'keyword' not in str(err):
              raise
            raise CamoufoxSkippedError('Fetch callback does not support Camoufox.') from err
          try:
            self.parse(payload)
          except (ImportCancelledError, CamoufoxRequiredError):
            raise
          except Exception as err:
            reject = getattr(owner, 'reject_camoufox_payload', None)
            if reject is not None:
              reject(str(err) or err.__class__.__name__)
            raise
          report(f'{self.NAME} transport=Camoufox accepted')
          return payload
        except (ImportCancelledError, CamoufoxRequiredError):
          raise
        except Exception as err:
          browser_failed = True
          report(f'{self.NAME} transport=Camoufox failed: {err}')
      report(f'{self.NAME} transport=legacy url={url}')
      if progress is not None:
        progress(0, 1, f'Fetching {self.NAME} via legacy transport...')
      return fetch_url(url, **options)

    parsed = super().fetch_and_parse(
      browser_first, sleep=sleep, fetch_error=fetch_error, log=log, progress=progress,
      before_fetch=before_fetch, after_fetch=after_fetch, before_parse=before_parse,
      force_fallback_level=force_fallback_level, disable_fallbacks=disable_fallbacks,
      source_choice=source_choice, cached_parsed=cached_parsed,
      incremental_update=incremental_update)
    if progress is not None:
      progress(1, 1, f'Finished loading {self.NAME}.')
    return parsed

  def fetch_url(self, fetch_url, url):
    payload = super().fetch_url(fetch_url, url)
    if url == self.WAYBACK_URL and str(payload or '').lstrip().startswith('<'):
      return self.WAYBACK_MARKER + str(payload)
    return payload

  def parse(self, html, **_kwargs):
    archived = self.WAYBACK_MARKER in str(html or '')
    parsed = self.parser().parse(
      html, self.NAME, self.WAYBACK_URL if archived else self.URL, self.schemas)
    if archived:
      captured = self.WAYBACK_CAPTURE_DATE or 'an unknown date'
      parsed.setdefault('notes', []).append(
        f'Internet Archive snapshot captured {captured}; imported results use '
        'archived Reddit content.')
    return parsed
