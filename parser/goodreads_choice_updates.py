"""Parsed Goodreads Choice year units; current and failed ballots stay fresh.

Maintenance notes:
- An overview with no matching category is a discovered absence, not a ballot.
  Reuse requires a complete older year and a later year advertised by the fresh
  landing document. A readable voting-round roster is complete intake data,
  while winnerless units stay unsettled and refresh on every update.
- Projections retain book identities and source order before entry conversion.
  Only parsed contributor names are cached, guarded by book URL and title.
"""

from copy import deepcopy
import json

from . import goodreads_choice_awards as choice
from .award_base import normalize_heading
from .generic import position_sort_key
from .incremental import ParsedUnitCache, project_source_rows, restore_source_rows

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError


STRATEGY = 'goodreads-choice-ballot-stages-v2'


def row_identity(row):
  return (str(row.get('award_year')), normalize_heading(row.get('title', '')),
    choice.category_key(row.get('category', '')),
    row.get('source_url') or (row.get('source') or {}).get('url'))


def previous_rows(cache, key):
  try:
    rows = restore_source_rows(cache.previous(key),
      (cache.old_units.get(key) or {}).get('metadata') or {})
    year = str(choice.year_from_text(key))
    if any(str(row.get('award_year')) != year or not row.get('title')
        or not isinstance(row.get('authors'), list) or not row['authors']
        or not all(isinstance(author, str) and author.strip() for author in row['authors'])
        or row.get('result') not in ('winner', 'nominee') for row in rows):
      return []
    return rows
  except (ValueError, TypeError, KeyError):
    return []


def parse_choice_units(parser, html, base_url, name, fetch_url, log, progress,
    sleep, cached_parsed, incremental_update, enrich_contributors):
  scope = json.dumps([base_url, name, parser.category, parser.category_aliases,
    parser.contributor_corrections, enrich_contributors], sort_keys=True)
  cache = ParsedUnitCache(STRATEGY, scope, cached_parsed, incremental_update)
  notes, units = [], {}
  root_links = parser.discover_category_links(html, base_url)
  advertised = parser.advertised_overview_years(html, base_url)
  advertised.update(link['year'] for link in root_links)
  current = choice.date.today().year
  latest = max(advertised, default=0)
  known_years = set()
  for key in cache.old_units:
    year = choice.year_from_text(key)
    if year is not None and parser.same_url(key, choice.goodreads_choice_overview_url(year)):
      known_years.add(year)
  years = set(choice.goodreads_choice_candidate_years()) | advertised | known_years
  years = sorted(year for year in years if year >= choice.FIRST_OVERVIEW_YEAR
    and (year != current or year in advertised or year in known_years))
  contributor_cache = deepcopy(cache.old_discovery.get('contributors') or {})
  if not isinstance(contributor_cache, dict):
    contributor_cache = {}
  for index, year in enumerate(years, 1):
    key = choice.goodreads_choice_overview_url(year)
    old = cache.old_units.get(key) or {}
    metadata = old.get('metadata') or {}
    fresh_links = [link for link in root_links if link['year'] == year]
    closed = year < current and year < latest
    rows = previous_rows(cache, key)
    links = metadata.get('links')
    reusable = (closed and old.get('complete') is True and old.get('revision') == year
      and metadata.get('year') == year and isinstance(links, list)
      and all(isinstance(link, dict) and link.get('year') == year
        and isinstance(link.get('url'), str) and parser.category_matches(link.get('category', ''))
        for link in links)
      and (not fresh_links or fresh_links == links)
      and ((bool(rows) and bool(links) and sum(row['result'] == 'winner' for row in rows) == 1)
        or (not rows and not links and not cache.previous(key))))
    if reusable:
      units[key] = (rows, links, True)
      continue
    if progress is not None:
      progress(index, len(years), f'Fetching Goodreads Choice Awards {year}')
    complete, fresh_rows, discovered = True, [], []
    try:
      page = html if parser.same_url(key, base_url) else fetch_url(key)
      parser.validate_fetch_payload(page, key)
      discovered = list(parser.discover_category_links(page, key))
      # Overview navigation must not assign another year's category to this unit.
      discovered = [link for link in discovered if link['year'] == year]
      for link in fresh_links:
        if link not in discovered:
          discovered.append(link)
      discovered.sort(key=lambda link: (link['year'], link['url']))
      for ballot_index, link in enumerate(discovered, 1):
        if progress is not None:
          progress(ballot_index, len(discovered),
            f'Fetching {parser.category} result page {ballot_index} of {len(discovered)}')
        page = fetch_url(link['url'])
        parser.validate_fetch_payload(page, link['url'])
        ballot = parser.parse_category_page(page, link['url'], fallback_year=year,
          fallback_category=link['category'], notes=notes, validate=True)
        if not ballot or any(int(row['award_year']) != year for row in ballot):
          raise ValueError('No complete category-year ballot was parsed.')
        fresh_rows.extend(ballot)
    except (ImportCancelledError, CamoufoxRequiredError):
      raise
    except Exception as err:
      complete = False
      notes.append(f'Goodreads Choice Awards year could not be completed: {key}: {err}')
      if log is not None:
        log(notes[-1])
    if (complete and any(row['result'] == 'winner' for row in rows)
        and fresh_rows and not any(row['result'] == 'winner' for row in fresh_rows)):
      complete = False
      notes.append(f'Goodreads Choice Awards {year} returned an earlier voting round after a cached winner; retained settled results pending retry.')
    if complete:
      rows = parser.dedupe_rows(fresh_rows)
    else:
      notes.append(f'Goodreads Choice Awards {year} remains pending; retained its whole cached ballot when available.')
    units[key] = (rows, discovered if complete else metadata.get('links', discovered), complete)

  rows = parser.dedupe_rows([deepcopy(row) for unit, _links, _complete in units.values() for row in unit])
  corrected = parser.apply_contributor_corrections(rows)
  if enrich_contributors:
    parser.enrich_latest_contributors(rows, fetch_url, notes, sleep=sleep,
      progress=progress, corrected_book_ids=corrected,
      latest_published_year=max({latest} | known_years) or None, contributor_cache=contributor_cache)
  entries = sorted(parser.entries_from_rows(rows),
    key=lambda row: position_sort_key(row.get('position', '')))
  # Keep successful enrichment with its year across rollover. Failed year refreshes
  # retain their original complete roster, but remain ineligible for reuse.
  processed = {row_identity(row): row for row in rows}
  for key, (unit_rows, links, complete) in units.items():
    source_rows = [processed.get(row_identity(row), row) for row in unit_rows]
    projected, metadata = project_source_rows(source_rows, entries, row_identity)
    metadata.update(year=choice.year_from_text(key), links=links,
      settled=bool(source_rows) and sum(row['result'] == 'winner' for row in source_rows) == 1)
    cache.put(key, projected, revision=choice.year_from_text(key),
      complete=complete, metadata=metadata)
  state = cache.state(entries)
  # Retain successful metadata only for books still owned by this source scope.
  ids = {parser.goodreads_book_id(row.get('_book_url', '')) for row in rows}
  state['discovery'] = {'latest_advertised_year': latest,
    'contributors': {key: value for key, value in contributor_cache.items() if key in ids}}
  if not entries:
    notes.append(f'No Goodreads Choice Awards rows were parsed for {parser.category}.')
  parsed = parser.parsed_result(name, base_url, entries, notes=notes)
  parsed['incremental_state'] = state
  return parsed
