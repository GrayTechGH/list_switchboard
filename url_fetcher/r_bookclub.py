#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""URL fetcher for the r/bookclub Previous Selections wiki.

Maintenance notes:
- Source level 0 is the current wiki across browser/legacy representations;
  level 1 is the dated archive. Browser stages are selected independently.
- Parse every live representation before accepting it: Reddit can answer with
  HTTP 200 interstitials. The archive must never hide a usable live result.
"""

from .generic import CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS, UrlFetcherGeneric, UrlFetcherError

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxSkippedError
except ImportError:
  from errors import ImportCancelledError, CamoufoxSkippedError


class UrlFetcherRBookclub(UrlFetcherGeneric):

  source_id = 'r_bookclub_previous_selections'
  NAME = 'r/bookclub'
  URL = 'https://www.reddit.com/r/bookclub/wiki/previous/'
  OLD_REDDIT_URL = 'https://old.reddit.com/r/bookclub/wiki/previous/'
  WAYBACK_URL = (
    'https://web.archive.org/web/20250405185632id_/'
    'https://www.reddit.com/r/bookclub/wiki/previous/'
  )
  WAYBACK_MARKER = '<!-- list-switchboard-r-bookclub-wayback-20250405 -->'
  JSON_URL = 'https://www.reddit.com/r/bookclub/wiki/previous.json?raw_json=1'
  SOURCE_VIEW_URL = 'https://www.reddit.com/r/bookclub/wiki/previous/?show_source='
  API_URL = 'https://api.reddit.com/r/bookclub/wiki/previous'
  FETCH_URLS = (
    OLD_REDDIT_URL, JSON_URL, SOURCE_VIEW_URL, URL, API_URL, WAYBACK_URL)
  order = 54
  FILTER_CATEGORIES = (CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,)
  options = {'match_series': False}

  def source_choices(self):
    # These are transport representations of one official wiki, not separate
    # editorial sources that users need to choose between.
    return ({'label': 'Automatic', 'value': 'automatic'},)

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.r_bookclub import RBookclubParser
    except ImportError:
      from parser.r_bookclub import RBookclubParser
    return RBookclubParser()

  def fetch_and_parse(
      self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
      before_fetch=None, after_fetch=None, before_parse=None,
      force_fallback_level=0, disable_fallbacks=False, source_choice=None,
      cached_parsed=None, incremental_update=False):
    source_level = int(force_fallback_level or 0)
    explicit_source = source_choice is not None and source_choice != 'automatic'
    if explicit_source:
      try:
        source_level = int(source_choice)
      except (TypeError, ValueError):
        raise UrlFetcherError(f'No source fallback exists for selected source {source_choice}.')
    elif disable_fallbacks:
      source_level = 0
    if source_level not in (0, 1):
      raise UrlFetcherError(f'No source fallback exists for level {source_level}.')

    attempts = []
    if source_level == 0:
      attempts.append((self.URL, 'Camoufox', True))
      attempts.extend((url, label, False) for url, label in (
        (self.OLD_REDDIT_URL, 'old Reddit HTML'),
        (self.JSON_URL, 'official JSON'),
        (self.SOURCE_VIEW_URL, 'source view'),
        (self.URL, 'lightweight rendered HTML'),
        (self.API_URL, 'official API'),
      ))
    if source_level == 1 or (not explicit_source and not disable_fallbacks):
      attempts.append((self.WAYBACK_URL, 'Wayback snapshot', False))

    failures = []

    def report(message):
      if log is not None:
        log(message)
      owner = getattr(fetch_url, '__self__', None)
      browser_log = getattr(owner, 'debug_camoufox', None)
      if browser_log is not None:
        browser_log(message)

    for index, (url, label, browser) in enumerate(attempts):
      try:
        if before_fetch is not None:
          before_fetch(url)
        if progress is not None:
          progress(index, len(attempts), f'Fetching r/bookclub via {label}...')
        report(f'r/bookclub attempt={label} url={url}')
        if browser:
          try:
            payload = fetch_url(url, transport='camoufox')
          except TypeError as err:
            if 'transport' not in str(err) and 'keyword' not in str(err):
              raise
            raise CamoufoxSkippedError('Fetch callback does not support Camoufox.') from err
        else:
          payload = self.fetch_url(fetch_url, url)
        if after_fetch is not None:
          after_fetch(url, payload)
        if before_parse is not None:
          before_parse(url)
        parsed = self.parse(payload)
        parsed.setdefault('match_series', False)
        if progress is not None:
          progress(len(attempts), len(attempts), 'Finished loading r/bookclub.')
        return parsed
      except ImportCancelledError:
        raise
      except Exception as err:
        reason = str(err) or err.__class__.__name__
        failures.append(f'{label}: {reason}')
        report(f'r/bookclub attempt={label} failed: {reason}')
    raise UrlFetcherError(
      'Could not fetch or parse r/bookclub.\n\nTried:\n- ' + '\n- '.join(failures))

  def fetch_url(self, fetch_url, url):
    payload = super().fetch_url(fetch_url, url)
    if url == self.WAYBACK_URL and str(payload or '').lstrip().startswith('<'):
      return self.WAYBACK_MARKER + str(payload)
    return payload

  def parse(self, payload, **_kwargs):
    archived = self.WAYBACK_MARKER in str(payload or '')
    parsed = self.parser().parse(
      payload, self.WAYBACK_URL if archived else self.URL, self.NAME)
    if archived:
      parsed.setdefault('notes', []).append(
        'Internet Archive snapshot captured 2025-04-05; selections added '
        'after the snapshot date are not included.')
    return parsed
