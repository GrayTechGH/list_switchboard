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
  from calibre_plugins.list_switchboard.errors import ImportCancelledError
except ImportError:
  from errors import ImportCancelledError

from .generic import (
  CATEGORY_HORROR_DARK_FICTION,
  GoodreadsFetchPolicyMixin,
  UrlFetcherError,
  UrlFetcherGeneric,
  parsed_source,
)

MAX_GOODREADS_PAGES = 25


class UrlFetcherSplatterpunk(GoodreadsFetchPolicyMixin, UrlFetcherGeneric):

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
    if source_choice not in (None, 'automatic'):
      raise UrlFetcherError(
        f'No source fallback attempt exists for selected source {source_choice}.')

    fetcher_fetch_url = lambda target_url: self.fetch_url(fetch_url, target_url)
    parser = self.parser()
    parsed_results = []
    notes = []

    try:
      parsed_results.append(self.fetch_parse_current(
        parser, fetcher_fetch_url, before_fetch, after_fetch, before_parse))
    except ImportCancelledError:
      raise
    except Exception as err:
      note = f'Splatterpunk official current nominees failed: {err}'
      notes.append(note)
      if log is not None:
        log(note)

    try:
      parsed_results.append(self.fetch_parse_official_winners(
        parser, fetcher_fetch_url, before_fetch, after_fetch, before_parse))
    except ImportCancelledError:
      raise
    except Exception as err:
      note = f'Splatterpunk official past winners failed: {err}'
      notes.append(note)
      if log is not None:
        log(note)

    try:
      parsed_results.extend(self.fetch_parse_goodreads_pages(
        parser, fetcher_fetch_url, before_fetch, after_fetch, before_parse, log))
    except ImportCancelledError:
      raise
    except Exception as err:
      note = f'Splatterpunk Goodreads historical supplement failed: {err}'
      notes.append(note)
      if log is not None:
        log(note)

    combined = parser.combine_results(
      self.NAME,
      self.URL,
      *parsed_results,
      {'entries': (), 'notes': notes})
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
    parser.validate_official_current_result(parsed)
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
      self, parser, fetch_url, before_fetch, after_fetch, before_parse, log):
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
      html = self.fetch_page(fetch_url, url, before_fetch, after_fetch)
      self.before_parse(before_parse, url)
      parser.validate_goodreads_page(html)
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
  source_id = 'splatterpunk_novel'
  NAME = 'Splatterpunk - Novel'
  CATEGORY = 'Novel'
  CATEGORY_ALIASES = ('novel', 'best novel')


class UrlFetcherSplatterpunkNovella(UrlFetcherSplatterpunk):
  source_id = 'splatterpunk_novella'
  NAME = 'Splatterpunk - Novella'
  CATEGORY = 'Novella'
  CATEGORY_ALIASES = ('novella', 'best novella')


class UrlFetcherSplatterpunkCollection(UrlFetcherSplatterpunk):
  source_id = 'splatterpunk_collection'
  NAME = 'Splatterpunk - Collection'
  CATEGORY = 'Collection'
  CATEGORY_ALIASES = ('collection', 'best collection')


class UrlFetcherSplatterpunkAnthology(UrlFetcherSplatterpunk):
  source_id = 'splatterpunk_anthology'
  NAME = 'Splatterpunk - Anthology'
  CATEGORY = 'Anthology'
  CATEGORY_ALIASES = ('anthology', 'best anthology')
