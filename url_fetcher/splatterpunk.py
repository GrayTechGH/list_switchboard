#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

try:
  from calibre_plugins.list_switchboard.parser.splatterpunk import (
    GOODREADS_URL,
    OFFICIAL_AWARDS_API_URL,
    OFFICIAL_AWARDS_URL,
    OFFICIAL_PAST_WINNERS_API_URL,
    OFFICIAL_PAST_WINNERS_URL,
  )
except ImportError:
  from parser.splatterpunk import (
    GOODREADS_URL,
    OFFICIAL_AWARDS_API_URL,
    OFFICIAL_AWARDS_URL,
    OFFICIAL_PAST_WINNERS_API_URL,
    OFFICIAL_PAST_WINNERS_URL,
  )

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError,CamoufoxRequiredError
  from calibre_plugins.list_switchboard.parser.splatterpunk_updates import fetch_splatterpunk
except ImportError:
  from errors import ImportCancelledError,CamoufoxRequiredError
  from parser.splatterpunk_updates import fetch_splatterpunk

from .splatterpunk_transport import SplatterpunkFetchPolicy,SplatterpunkOfficialFetchPolicy

from .generic import (
  CATEGORY_HORROR_DARK_FICTION,
  GoodreadsFetchPolicyMixin,
  UrlFetcherError,
  UrlFetcherGeneric,
  parsed_source,
)

MAX_GOODREADS_PAGES = 25


class UrlFetcherSplatterpunk(GoodreadsFetchPolicyMixin, UrlFetcherGeneric):
  """Keep official sources authoritative and historical recovery page-local.

  Invariants:
  - Official REST and Goodreads supplement policies validate their own sources.
  - Failed live pagination is discarded as a whole; compatible updates retain
    the previous whole supplement pending retry.
  - Operation policy and progress state are cleared on success or failure.
  """

  URL = OFFICIAL_AWARDS_URL
  FETCH_URLS = ()
  FILTER_CATEGORIES = (CATEGORY_HORROR_DARK_FICTION,)
  order = 93
  options = {'match_series': False}
  AWARD_NAME = 'Splatterpunk Award'
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.splatterpunk import (
        SplatterpunkParser,
      )
    except ImportError:
      from parser.splatterpunk import SplatterpunkParser
    return SplatterpunkParser()

  def source_choices(self):
    return ({'label': 'Automatic', 'value': 'automatic'},)

  def fetch_and_parse(
      self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
      before_fetch=None, after_fetch=None, before_parse=None,
      force_fallback_level=0, disable_fallbacks=False, source_choice=None,
      cached_parsed=None, incremental_update=False):
    self._splatterpunk_progress = progress
    self._splatterpunk_fetch_policy = SplatterpunkFetchPolicy(
      fetch_url, lambda url: self.legacy_fetch_url(fetch_url, url), self.parser(),
      log=log, progress=progress)
    self._splatterpunk_official_policy=SplatterpunkOfficialFetchPolicy(
      fetch_url,lambda url:self.legacy_fetch_url(fetch_url,url),self.parser(),log)
    try:
      return self._fetch_and_parse(
        fetch_url, sleep, fetch_error, log, progress, before_fetch, after_fetch,
        before_parse, force_fallback_level, disable_fallbacks, source_choice,
        cached_parsed, incremental_update)
    finally:
      self._splatterpunk_fetch_policy = None
      self._splatterpunk_official_policy = None
      self._splatterpunk_progress = None

  def fetch_url(self, fetch_url, url):
    policy = getattr(self, '_splatterpunk_fetch_policy', None)
    if policy is not None and url.startswith(GOODREADS_URL):
      return policy.fetch(url)
    official=getattr(self,'_splatterpunk_official_policy',None)
    if official is not None and url in (OFFICIAL_AWARDS_API_URL,OFFICIAL_PAST_WINNERS_API_URL):
      return official.fetch(url)
    return self.legacy_fetch_url(fetch_url, url)

  def legacy_fetch_url(self, fetch_url, url):
    retries = self.timeout_retries(url)
    for retry in range(retries + 1):
      try:
        return self.fetch_url_once(fetch_url, url)
      except ImportCancelledError:
        raise
      except Exception as err:
        if retry >= retries or not self.is_timeout_error(err):
          raise
        progress = getattr(self, '_splatterpunk_progress', None)
        if progress is not None:
          progress(0, 1, f'Splatterpunk Goodreads timed out; retry {retry + 1} of {retries}: {url}')

  def _fetch_and_parse(
      self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
      before_fetch=None, after_fetch=None, before_parse=None,
      force_fallback_level=0, disable_fallbacks=False, source_choice=None,
      cached_parsed=None, incremental_update=False):
    if source_choice not in (None, 'automatic'):
      raise UrlFetcherError(
        f'No source fallback attempt exists for selected source {source_choice}.')

    fetcher_fetch_url = lambda target_url: self.fetch_url(fetch_url, target_url)
    parser = self.parser()
    combined=fetch_splatterpunk(self,fetcher_fetch_url,cached_parsed,incremental_update,
      before_fetch,after_fetch,before_parse,log,progress)
    if not combined.get('entries'):
      raise UrlFetcherError('Could not fetch or parse the imported list.')
    combined['match_series'] = self.options.get('match_series', True)
    combined.setdefault('source', parsed_source(self.NAME, self.URL, self.source_id))
    return combined

  def fetch_parse_current(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse):
    source = self.fetch_page(
      fetch_url, OFFICIAL_AWARDS_API_URL, before_fetch, after_fetch)
    self.before_parse(before_parse, OFFICIAL_AWARDS_API_URL)
    parser.validate_official_api_source(source, 'current nominees')
    parsed = parser.parse_official_current(
      source,
      OFFICIAL_AWARDS_URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES)
    parser.validate_official_current_result(parsed,source)
    parsed['current_state']=parser.current_phase(source)
    if parsed['current_state']['intake']:
      parsed['notes'].append('Official KillerCon current page is nomination intake; no finalist ballot is published there yet.')
    return parsed

  def fetch_parse_official_winners(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse):
    source = self.fetch_page(
      fetch_url, OFFICIAL_PAST_WINNERS_API_URL, before_fetch, after_fetch)
    self.before_parse(before_parse, OFFICIAL_PAST_WINNERS_API_URL)
    parser.validate_official_api_source(source, 'past winners')
    parsed = parser.parse_official_winners(
      source,
      OFFICIAL_PAST_WINNERS_URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES)
    parser.validate_official_winner_result(parsed)
    return parsed

  def fetch_parse_goodreads_pages(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse, log,
      progress=None):
    pending = [GOODREADS_URL]
    seen = set()
    parsed_results = []
    while pending:
      if len(seen) >= MAX_GOODREADS_PAGES:
        raise UrlFetcherError(
          'Splatterpunk Goodreads pagination exceeded the '
          f'{MAX_GOODREADS_PAGES}-page safety limit.')
      url = pending.pop(0)
      if url in seen:
        continue
      total = len(seen) + len(pending) + 1
      if progress is not None:
        progress(len(seen), total, f'Fetching Splatterpunk Goodreads page {len(seen) + 1} of {total}')
      html = self.fetch_page(fetch_url, url, before_fetch, after_fetch)
      self.before_parse(before_parse, url)
      parser.validate_goodreads_page(html, url)
      if progress is not None:
        progress(len(seen), total, f'Parsing Splatterpunk Goodreads page {len(seen) + 1} of {total}')
      seen.add(url)
      parsed_results.append(parser.parse_goodreads(
        html,
        url,
        self.NAME,
        self.CATEGORY,
        self.CATEGORY_ALIASES))
      for discovered_url in parser.discover_goodreads_page_urls(html, url):
        if discovered_url not in seen and discovered_url not in pending:
          pending.append(discovered_url)
      if progress is not None:
        progress(len(seen), len(seen) + len(pending),
          f'Parsed Splatterpunk Goodreads page {len(seen)} of {len(seen) + len(pending)}')
    if not any(parsed.get('entries') for parsed in parsed_results):
      raise ValueError(
        'Splatterpunk Goodreads pages did not expose the configured category.')
    return parsed_results

  def fetch_page(self, fetch_url, url, before_fetch, after_fetch):
    if before_fetch is not None:
      before_fetch(url)
    html = fetch_url(url)
    if after_fetch is not None:
      after_fetch(url, html)
    return html

  def before_parse(self, before_parse, url):
    if before_parse is not None:
      before_parse(url)

  def parse(self, html, **_kwargs):
    return self.parser().parse_official_current(
      html,
      OFFICIAL_AWARDS_URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES)


class UrlFetcherSplatterpunkNovel(UrlFetcherSplatterpunk):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'splatterpunk_novel'
  NAME = 'Splatterpunk - Novel'
  CATEGORY = 'Novel'
  CATEGORY_ALIASES = ('novel', 'best novel')


class UrlFetcherSplatterpunkNovella(UrlFetcherSplatterpunk):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'splatterpunk_novella'
  NAME = 'Splatterpunk - Novella'
  CATEGORY = 'Novella'
  CATEGORY_ALIASES = ('novella', 'best novella')


class UrlFetcherSplatterpunkCollection(UrlFetcherSplatterpunk):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'splatterpunk_collection'
  NAME = 'Splatterpunk - Collection'
  CATEGORY = 'Collection'
  CATEGORY_ALIASES = ('collection', 'best collection')


class UrlFetcherSplatterpunkAnthology(UrlFetcherSplatterpunk):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'splatterpunk_anthology'
  NAME = 'Splatterpunk - Anthology'
  CATEGORY = 'Anthology'
  CATEGORY_ALIASES = ('anthology', 'best anthology')
