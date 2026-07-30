#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

try:
  from calibre_plugins.list_switchboard.parser.this_is_horror import (
    GOODREADS_URL,
    OFFICIAL_AWARDS_API_URL,
    OFFICIAL_AWARDS_URL,
    OFFICIAL_RESULTS_API_URLS,
  )
except ImportError:
  from parser.this_is_horror import (
    GOODREADS_URL,
    OFFICIAL_AWARDS_API_URL,
    OFFICIAL_AWARDS_URL,
    OFFICIAL_RESULTS_API_URLS,
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

MAX_GOODREADS_PAGES = 10


class UrlFetcherThisIsHorror(GoodreadsFetchPolicyMixin, UrlFetcherGeneric):

  URL = OFFICIAL_AWARDS_URL
  FETCH_URLS = ()
  FILTER_CATEGORIES = (CATEGORY_HORROR_DARK_FICTION,)
  order = 92
  options = {'match_series': False}
  AWARD_NAME = 'This Is Horror Award'
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.this_is_horror import (
        ThisIsHorrorParser,
      )
    except ImportError:
      from parser.this_is_horror import ThisIsHorrorParser
    return ThisIsHorrorParser()

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
    notes = []

    ballots = self.fetch_parse_ballots(
      parser, fetcher_fetch_url, before_fetch, after_fetch, before_parse)
    result_pages = self.fetch_parse_result_pages(
      parser, fetcher_fetch_url, before_fetch, after_fetch, before_parse)

    goodreads_pages = []
    try:
      goodreads_pages = self.fetch_parse_goodreads_pages(
        parser, fetcher_fetch_url, before_fetch, after_fetch, before_parse)
    except ImportCancelledError:
      raise
    except Exception as err:
      note = f'This Is Horror Goodreads diagnostic supplement failed: {err}'
      notes.append(note)
      if log is not None:
        log(note)

    combined = parser.combine_results(
      self.NAME,
      self.URL,
      ballots,
      *result_pages,
      *goodreads_pages,
      {'entries': (), 'notes': notes})
    parser.validate_combined_result(combined, self.CATEGORY)
    if not combined.get('entries'):
      raise UrlFetcherError('Could not fetch or parse the imported list.')
    combined['match_series'] = self.options.get('match_series', True)
    combined.setdefault('source', parsed_source(self.NAME, self.URL, self.source_id))
    return combined

  def fetch_parse_ballots(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse):
    source = self.fetch_page(
      fetch_url, OFFICIAL_AWARDS_API_URL, before_fetch, after_fetch)
    self.before_parse(before_parse, OFFICIAL_AWARDS_API_URL)
    parsed = parser.parse_official_ballots(
      source,
      OFFICIAL_AWARDS_URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES)
    parser.validate_official_ballot_result(parsed, self.CATEGORY)
    return parsed

  def fetch_parse_current(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse):
    """Compatibility wrapper for callers using the former method name."""
    return self.fetch_parse_ballots(
      parser, fetch_url, before_fetch, after_fetch, before_parse)

  def fetch_parse_result_pages(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse):
    parsed_results = []
    detail_urls = []
    for url in OFFICIAL_RESULTS_API_URLS:
      source = self.fetch_page(fetch_url, url, before_fetch, after_fetch)
      self.before_parse(before_parse, url)
      parsed_results.append(parser.parse_official_winners(
        source,
        OFFICIAL_AWARDS_URL,
        self.NAME,
        self.CATEGORY,
        self.CATEGORY_ALIASES))
      for detail in parser.discover_result_detail_urls(
          source, self.CATEGORY, self.CATEGORY_ALIASES):
        if detail not in detail_urls:
          detail_urls.append(detail)
    for year, url in detail_urls:
      source = self.fetch_page(fetch_url, url, before_fetch, after_fetch)
      self.before_parse(before_parse, url)
      parsed_results.append(parser.parse_official_winners(
        source,
        url,
        self.NAME,
        self.CATEGORY,
        self.CATEGORY_ALIASES,
        award_year=year))
    return parsed_results

  def fetch_parse_winner_posts(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse, log=None):
    """Compatibility wrapper for callers using the former method name."""
    return self.fetch_parse_result_pages(
      parser, fetch_url, before_fetch, after_fetch, before_parse)

  def fetch_parse_goodreads_pages(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse):
    pending = [GOODREADS_URL]
    seen = set()
    parsed_results = []
    while pending:
      if len(seen) >= MAX_GOODREADS_PAGES:
        raise UrlFetcherError(
          'This Is Horror Goodreads pagination exceeded the '
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
    return parsed_results

  def fetch_parse_goodreads(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse):
    """Compatibility wrapper returning the first parsed Goodreads page."""
    pages = self.fetch_parse_goodreads_pages(
      parser, fetch_url, before_fetch, after_fetch, before_parse)
    return pages[0] if pages else {'entries': (), 'notes': ()}

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


class UrlFetcherThisIsHorrorNovel(UrlFetcherThisIsHorror):
  source_id = 'this_is_horror_novel'
  NAME = 'This Is Horror - Novel'
  CATEGORY = 'Novel'
  CATEGORY_ALIASES = ('novel', 'novel of the year', 'best novel')


class UrlFetcherThisIsHorrorNovella(UrlFetcherThisIsHorror):
  source_id = 'this_is_horror_novella'
  NAME = 'This Is Horror - Novella'
  CATEGORY = 'Novella'
  CATEGORY_ALIASES = ('novella', 'novella of the year', 'best novella')


class UrlFetcherThisIsHorrorShortStoryCollection(UrlFetcherThisIsHorror):
  source_id = 'this_is_horror_short_story_collection'
  NAME = 'This Is Horror - Short Story Collection'
  CATEGORY = 'Short Story Collection'
  CATEGORY_ALIASES = (
    'short story collection',
    'short story collection of the year',
    'collection',
  )


class UrlFetcherThisIsHorrorAnthology(UrlFetcherThisIsHorror):
  source_id = 'this_is_horror_anthology'
  NAME = 'This Is Horror - Anthology (discontinued)'
  CATEGORY = 'Anthology'
  CATEGORY_ALIASES = ('anthology', 'anthology of the year', 'best anthology')
