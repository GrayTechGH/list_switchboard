#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

try:
  from calibre_plugins.list_switchboard.parser.british_fantasy import (
    BFS_AWARDS_URL, BFS_LEGACY_SHORTLIST_URL, BFS_WINNERS_URL, SFADB_URL,
  )
except ImportError:
  from parser.british_fantasy import (
    BFS_AWARDS_URL, BFS_LEGACY_SHORTLIST_URL, BFS_WINNERS_URL, SFADB_URL,
  )

from .generic import (
  CATEGORY_FANTASY,
  CATEGORY_HORROR_DARK_FICTION,
  CATEGORY_NONFICTION,
  UrlFetcherError,
  UrlFetcherGeneric,
)


SPECULATIVE_CATEGORIES = (CATEGORY_FANTASY, CATEGORY_HORROR_DARK_FICTION)


class UrlFetcherBritishFantasy(UrlFetcherGeneric):

  URL = BFS_WINNERS_URL
  FETCH_URLS = ()
  FILTER_CATEGORIES = SPECULATIVE_CATEGORIES
  order = 91
  options = {'match_series': False}
  AWARD_NAME = 'British Fantasy Award'
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  MIN_AWARD_YEAR = None
  MAX_AWARD_YEAR = None

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.british_fantasy import (
        BritishFantasyParser,
      )
    except ImportError:
      from parser.british_fantasy import BritishFantasyParser
    return BritishFantasyParser()

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

    winners = self.fetch_parse_bfs_winners(
      parser, fetcher_fetch_url, before_fetch, after_fetch, before_parse)
    parsed_results.append(winners)

    parsed_results.extend(self.fetch_parse_shortlists(
      parser, fetcher_fetch_url, before_fetch, after_fetch, before_parse, log))

    try:
      parsed_results.append(self.fetch_parse_sfadb(
        parser, fetcher_fetch_url, before_fetch, after_fetch, before_parse,
        log, progress))
    except Exception as err:
      note = f'British Fantasy SFADB historical shortlist supplement failed: {err}'
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
    combined.setdefault('source_url', self.URL)
    return combined

  def fetch_parse_bfs_winners(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse):
    html = self.fetch_page(fetch_url, BFS_WINNERS_URL, before_fetch, after_fetch)
    self.before_parse(before_parse, BFS_WINNERS_URL)
    parsed = parser.parse_bfs_winners(
      html,
      BFS_WINNERS_URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES,
      min_year=self.MIN_AWARD_YEAR,
      max_year=self.MAX_AWARD_YEAR)
    if not parsed.get('entries'):
      raise ValueError('BFS winners archive did not contain usable entries')
    return parsed

  def fetch_parse_shortlists(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse, log):
    parsed_results = []
    urls = []
    try:
      html = self.fetch_page(fetch_url, BFS_AWARDS_URL, before_fetch, after_fetch)
      urls = list(parser.discover_shortlist_urls(html, BFS_AWARDS_URL))
    except Exception as err:
      if log is not None:
        log(f'British Fantasy awards info page failed: {err}')
    if not urls:
      urls = [BFS_LEGACY_SHORTLIST_URL]
    for url in urls[:2]:
      try:
        html = self.fetch_page(fetch_url, url, before_fetch, after_fetch)
        self.before_parse(before_parse, url)
        parsed_results.append(parser.parse_bfs_shortlist(
          html,
          url,
          self.NAME,
          self.CATEGORY,
          self.CATEGORY_ALIASES,
          min_year=self.MIN_AWARD_YEAR,
          max_year=self.MAX_AWARD_YEAR))
      except Exception as err:
        note = f'British Fantasy official shortlist page failed: {url}: {err}'
        parsed_results.append({'entries': (), 'notes': [note]})
        if log is not None:
          log(note)
    return parsed_results

  def fetch_parse_sfadb(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse,
      log, progress):
    html = self.fetch_page(fetch_url, SFADB_URL, before_fetch, after_fetch)
    self.before_parse(before_parse, SFADB_URL)
    return parser.parse_sfadb(
      html,
      SFADB_URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES,
      fetch_url=fetch_url,
      log=log,
      progress=progress,
      min_year=self.MIN_AWARD_YEAR,
      max_year=self.MAX_AWARD_YEAR)

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
    return self.parser().parse_bfs_winners(
      html,
      self.URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES,
      min_year=self.MIN_AWARD_YEAR,
      max_year=self.MAX_AWARD_YEAR)


class UrlFetcherBritishFantasyHorrorNovel(UrlFetcherBritishFantasy):
  source_id = 'british_fantasy_horror_novel'
  NAME = 'British Fantasy - Horror Novel'
  FILTER_CATEGORIES = (CATEGORY_HORROR_DARK_FICTION,)
  CATEGORY = 'Horror Novel'
  CATEGORY_ALIASES = (
    'horror novel',
    'best horror novel',
    'horror novel the august derleth award',
    'the august derleth award for best horror novel',
    'august derleth award horror novel',
  )
  MIN_AWARD_YEAR = 2012


class UrlFetcherBritishFantasyFantasyNovel(UrlFetcherBritishFantasy):
  source_id = 'british_fantasy_fantasy_novel'
  NAME = 'British Fantasy - Fantasy Novel'
  FILTER_CATEGORIES = (CATEGORY_FANTASY,)
  CATEGORY = 'Fantasy Novel'
  CATEGORY_ALIASES = (
    'fantasy novel',
    'best fantasy novel',
    'fantasy novel the robert holdstock award',
    'the robert holdstock award for best fantasy novel',
    'robert holdstock award fantasy novel',
  )
  MIN_AWARD_YEAR = 2012


class UrlFetcherBritishFantasyBestNovel(UrlFetcherBritishFantasy):
  source_id = 'british_fantasy_best_novel'
  NAME = 'British Fantasy - Best Novel (pre-2012 August Derleth)'
  CATEGORY = 'Best Novel'
  CATEGORY_ALIASES = (
    'novel',
    'best novel',
    'august derleth fantasy award best novel',
    'august derleth award best novel',
  )
  MAX_AWARD_YEAR = 2011


class UrlFetcherBritishFantasyNovella(UrlFetcherBritishFantasy):
  source_id = 'british_fantasy_novella'
  NAME = 'British Fantasy - Novella'
  CATEGORY = 'Novella'
  CATEGORY_ALIASES = ('novella', 'best novella')


class UrlFetcherBritishFantasyAnthology(UrlFetcherBritishFantasy):
  source_id = 'british_fantasy_anthology'
  NAME = 'British Fantasy - Anthology'
  CATEGORY = 'Anthology'
  CATEGORY_ALIASES = ('anthology', 'best anthology')


class UrlFetcherBritishFantasyCollection(UrlFetcherBritishFantasy):
  source_id = 'british_fantasy_collection'
  NAME = 'British Fantasy - Collection'
  CATEGORY = 'Collection'
  CATEGORY_ALIASES = ('collection', 'best collection')


class UrlFetcherBritishFantasyNonfiction(UrlFetcherBritishFantasy):
  source_id = 'british_fantasy_nonfiction'
  NAME = 'British Fantasy - Non-Fiction'
  FILTER_CATEGORIES = SPECULATIVE_CATEGORIES + (CATEGORY_NONFICTION,)
  CATEGORY = 'Non-Fiction'
  CATEGORY_ALIASES = ('non-fiction', 'non fiction', 'nonfiction', 'best non-fiction')
