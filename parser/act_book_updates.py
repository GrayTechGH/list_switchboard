"""Reuse complete official year units; keep automatic Wikipedia winners fresh."""

import datetime
import json

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError
  from calibre_plugins.list_switchboard.parser.incremental import ParsedUnitCache, project_parsed_units, restore_parsed_units
  from calibre_plugins.list_switchboard.parser.award_base import normalize_heading
  from calibre_plugins.list_switchboard.parser.base import author_list
  from calibre_plugins.list_switchboard.parser.act_book_sources import discover_archive, read_year
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError
  from .incremental import ParsedUnitCache, project_parsed_units, restore_parsed_units
  from .award_base import normalize_heading
  from .base import author_list
  from .act_book_sources import discover_archive, read_year


def scope(recipe):
  return json.dumps([recipe.source_id, recipe.URL, recipe.WIKIPEDIA_URL, recipe.FIRST_YEAR, recipe.NAME])


def identity(row):
  return (str(row.get('award_year')), normalize_heading(row.get('title', '')),
    tuple(sorted(normalize_heading(author) for author in author_list(row.get('authors', row.get('author', ''))))))


def restore_official(recipe, cached, incremental):
  return restore_parsed_units(ParsedUnitCache('act-automatic-projections-v1', scope(recipe), cached, incremental))


def with_supplement_state(recipe, official, supplemented):
  if not official.get('incremental_state'):
    return supplemented
  entries = supplemented['entries']
  state = project_parsed_units(official, entries, 'act-automatic-projections-v1', scope(recipe), identity)
  owned = {i for unit in state['units'].values() for i in unit['entry_indexes']}
  # Appended Wikipedia-only winners need ownership too. Restoration deliberately
  # ignores this fresh supplement unit, rebuilding only original official years.
  state['units']['wikipedia-winners'] = {'revision': None,
    'complete': not any(note.startswith('Wikipedia winner supplement failed:') for note in supplemented.get('notes', [])),
    'entry_indexes': [i for i in range(len(entries)) if i not in owned]}
  supplemented['incremental_state'] = state
  return supplemented


def fetch_act_official(recipe, parser, html, fetch_url, cached=None, incremental=False):
  discovery = discover_archive(html, recipe.URL)
  years = discovery['years']
  if not years or set(years) != set(range(recipe.FIRST_YEAR, max(years) + 1)) or max(years) < datetime.datetime.now().year - 1:
    raise ValueError('Libraries ACT archive had missing or unexpected award-year coverage.')
  cache = ParsedUnitCache('act-official-years-v1', scope(recipe), cached, incremental)
  rows, notes = [], []
  latest = max(years)
  for year in sorted(years):
    key = str(year)
    urls = sorted(years[year])
    revision = [urls, discovery['covers'].get(year, [])]
    old = cache.old_units.get(key) or {}
    metadata = old.get('metadata') or {}
    previous = cache.previous(key)
    reused = None
    if (year < min(latest, datetime.datetime.now().year) and metadata.get('settled') is True and
        previous and all(row.get('award_year') == key for row in previous) and
        any(row.get('result') == 'winner' for row in previous)):
      reused = cache.reuse(key, revision)
    if reused is not None:
      rows.extend(reused)
      notes.extend(metadata.get('notes', []))
      continue
    source_rows, unit_notes, complete = [], [], True
    try:
      for url in urls:
        source = read_year(parser, fetch_url(url), url, year)
        source_rows.extend(source['rows']); unit_notes.extend(source['notes'])
        complete = complete and source['complete']
      entries = parser.entries_from_rows(parser.dedupe_rows(source_rows))
      if not complete and previous:
        entries = previous
    except (ImportCancelledError, CamoufoxRequiredError):
      raise
    except Exception as err:
      entries, complete = previous, False
      unit_notes.append(f'Libraries ACT {year} could not be refreshed: {err}; retained cached year where available.')
    cache.put(key, entries, revision=revision, complete=complete,
      metadata={'settled': any(row.get('result') == 'winner' for row in entries), 'notes': unit_notes})
    rows.extend(entries); notes.extend(unit_notes)
  parsed = parser.parsed_result(recipe.NAME, recipe.URL, rows, notes)
  parsed['incremental_state'] = cache.state(rows)
  return parsed
