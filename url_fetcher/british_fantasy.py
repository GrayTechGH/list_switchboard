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
  parsed_source,
)

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError
  from calibre_plugins.list_switchboard.parser.incremental import ParsedUnitCache
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError
  from parser.incremental import ParsedUnitCache


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
    cache = ParsedUnitCache('british-fantasy-empty-years-v1',
      f'{self.source_id}|{self.CATEGORY}|{self.CATEGORY_ALIASES}|'
      f'{self.MIN_AWARD_YEAR}|{self.MAX_AWARD_YEAR}|{SFADB_URL}',
      cached_parsed, incremental_update)
    empty_state = cache.old_discovery.get('empty_year_state')
    supplement_cache = {'entries': [], 'incremental_state': empty_state} if isinstance(empty_state, dict) else None
    parsed_results = []
    notes = []

    winners = self.fetch_parse_bfs_winners(
      parser, fetcher_fetch_url, before_fetch, after_fetch, before_parse)
    parsed_results.append(winners)

    parsed_results.extend(self.fetch_parse_shortlists(
      parser, fetcher_fetch_url, before_fetch, after_fetch, before_parse, log))

    try:
      supplement = self.fetch_parse_sfadb(
        parser, fetcher_fetch_url, before_fetch, after_fetch, before_parse,
        log, progress, cached_parsed=supplement_cache,
        incremental_update=incremental_update)
      parsed_results.append(supplement)
    except (ImportCancelledError, CamoufoxRequiredError):
      raise
    except Exception as err:
      supplement = {'entries': [], 'notes': []}
      note = f'British Fantasy SFADB historical shortlist supplement failed: {err}'
      notes.append(note)
      if log is not None:
        log(note)

    source_state = supplement.get('incremental_state') or {}
    source_units = source_state.get('units') or {}
    failed_years = {str(unit.get('revision', '')) for unit in source_units.values()
      if unit.get('complete') is not True}
    # Cached merged rows are used only after a failed year refresh. Successful
    # ballots are always fetched, preserving authoritative-source deduplication.
    for key, old_unit in cache.old_units.items():
      if not source_state or str(old_unit.get('revision', '')) in failed_years:
        parsed_results.append({'entries': cache.previous(key), 'notes': []})

    combined = parser.combine_results(
      self.NAME,
      self.URL,
      *parsed_results,
      {'entries': (), 'notes': notes})
    if not combined.get('entries'):
      raise UrlFetcherError('Could not fetch or parse the imported list.')
    combined['match_series'] = self.options.get('match_series', True)
    combined.setdefault('source', parsed_source(self.NAME, self.URL, self.source_id))
    years = {}
    for entry in combined['entries']:
      years.setdefault(str(entry.get('award_year', '')), []).append(entry)
    for key, unit in source_units.items():
      year = str(unit.get('revision', ''))
      cache.put(key, years.pop(year, []), revision=unit.get('revision'),
        complete=unit.get('complete') is True)
    for year, entries in years.items():
      cache.put(f'official-year:{year}', entries, revision=year,
        complete=bool(source_state))
    state = cache.state(combined['entries'])
    if source_state:
      # Only verified empty or out-of-scope category years are reusable. This
      # avoids storing duplicate source ballots or reusing merged provenance.
      empty_units = {
        key: dict(unit, entry_indexes=[]) for key, unit in source_units.items()
        if unit.get('complete') is True and (not unit.get('entry_indexes') or
          not parser.year_allowed(int(unit['revision']), self.MIN_AWARD_YEAR, self.MAX_AWARD_YEAR))}
      state['discovery'] = {'empty_year_state': dict(source_state, units=empty_units)}
    elif empty_state:
      state['discovery'] = {'empty_year_state': empty_state}
    combined['incremental_state'] = state
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
    except (ImportCancelledError, CamoufoxRequiredError):
      raise
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
      except (ImportCancelledError, CamoufoxRequiredError):
        raise
      except Exception as err:
        note = f'British Fantasy official shortlist page failed: {url}: {err}'
        parsed_results.append({'entries': (), 'notes': [note]})
        if log is not None:
          log(note)
    return parsed_results

  def fetch_parse_sfadb(
      self, parser, fetch_url, before_fetch, after_fetch, before_parse,
      log, progress, cached_parsed=None, incremental_update=False):
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
      max_year=self.MAX_AWARD_YEAR, cached_parsed=cached_parsed,
      incremental_update=incremental_update, enable_incremental=True)

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
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'british_fantasy_horror_novel'
  NAME = 'British Fantasy - Horror Novel'
  FILTER_CATEGORIES = (CATEGORY_HORROR_DARK_FICTION,)
  CATEGORY = 'Horror Novel'
  CATEGORY_ALIASES = (
    'horror novel',
    'best horror novel',
    'horror novel the august derleth award',
    'horror novel august derleth award',
    'the august derleth award for best horror novel',
    'august derleth award horror novel',
  )
  MIN_AWARD_YEAR = 2012


class UrlFetcherBritishFantasyFantasyNovel(UrlFetcherBritishFantasy):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'british_fantasy_fantasy_novel'
  NAME = 'British Fantasy - Fantasy Novel'
  FILTER_CATEGORIES = (CATEGORY_FANTASY,)
  CATEGORY = 'Fantasy Novel'
  CATEGORY_ALIASES = (
    'fantasy novel',
    'best fantasy novel',
    'fantasy novel the robert holdstock award',
    'fantasy novel robert holdstock award',
    'the robert holdstock award for best fantasy novel',
    'robert holdstock award fantasy novel',
  )
  MIN_AWARD_YEAR = 2012


class UrlFetcherBritishFantasyBestNovel(UrlFetcherBritishFantasy):
  source_id = 'british_fantasy_best_novel'
  NAME = 'British Fantasy - Horror/Fantasy Novel (discontinued)'
  CATEGORY = 'Best Novel'
  CATEGORY_ALIASES = (
    'novel',
    'best novel',
    'novel the august derleth fantasy award',
    'novel the august derleth award',
    'august derleth fantasy award novel',
    'august derleth award novel',
    'august derleth fantasy award best novel',
    'august derleth award best novel',
  )
  MAX_AWARD_YEAR = 2011


class UrlFetcherBritishFantasyNovella(UrlFetcherBritishFantasy):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'british_fantasy_novella'
  NAME = 'British Fantasy - Novella'
  CATEGORY = 'Novella'
  CATEGORY_ALIASES = ('novella', 'best novella')


class UrlFetcherBritishFantasyAnthologyCollection(UrlFetcherBritishFantasy):
  source_id = 'british_fantasy_anthology_collection'
  NAME = 'British Fantasy - Anthology/Collection (discontinued)'
  CATEGORY = 'Anthology/Collection'
  CATEGORY_ALIASES = (
    'anthology/collection',
    'anthology collection',
    'collection',
  )
  MIN_AWARD_YEAR = 1991
  MAX_AWARD_YEAR = 1998


class UrlFetcherBritishFantasyAnthology(UrlFetcherBritishFantasy):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'british_fantasy_anthology'
  NAME = 'British Fantasy - Anthology'
  CATEGORY = 'Anthology'
  CATEGORY_ALIASES = ('anthology', 'best anthology')
  MIN_AWARD_YEAR = 1999


class UrlFetcherBritishFantasyCollection(UrlFetcherBritishFantasy):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'british_fantasy_collection'
  NAME = 'British Fantasy - Collection'
  CATEGORY = 'Collection'
  CATEGORY_ALIASES = ('collection', 'best collection')
  MIN_AWARD_YEAR = 1999


class UrlFetcherBritishFantasyNonfiction(UrlFetcherBritishFantasy):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'british_fantasy_nonfiction'
  NAME = 'British Fantasy - Non-Fiction'
  FILTER_CATEGORIES = SPECULATIVE_CATEGORIES + (CATEGORY_NONFICTION,)
  CATEGORY = 'Non-Fiction'
  CATEGORY_ALIASES = ('non-fiction', 'non fiction', 'nonfiction', 'best non-fiction')
