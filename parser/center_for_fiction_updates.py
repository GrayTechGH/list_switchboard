"""Fresh winner/discovery snapshots certify complete per-year parsed ballots.

Each year owns all of its advertised annual/shortlist pages as one unit. This
keeps current winner promotions and source removals reversible without storing
raw pages or flattening every source into independently reusable final rows.
"""

import datetime
import json
from copy import deepcopy

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError
  from calibre_plugins.list_switchboard.parser.incremental import ParsedUnitCache
  from calibre_plugins.list_switchboard.parser.base import author_list
  from calibre_plugins.list_switchboard.parser.award_base import normalize_heading
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
  from calibre_plugins.list_switchboard.parser.center_for_fiction_sources import WINNERS_URL, discover_links
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError
  from .incremental import ParsedUnitCache
  from .base import author_list
  from .award_base import normalize_heading
  from .generic import position_sort_key
  from .center_for_fiction_sources import WINNERS_URL, discover_links


def work_key(row):
  return [normalize_heading(row.get('title', '')),
    sorted(normalize_heading(author) for author in author_list(row.get('authors', row.get('author', ''))))]


def correct_winner_credit(rows, winner, history_url):
  """Use explicit history authority only for the same year's titled winner.

  Annual winner cards contain misspellings that disagree with their inline
  roster/history. Preserve original credits as provenance, not matching aliases.
  Shortlisted works and distinct titles cannot acquire this author correction.
  """
  matching = [row for row in rows if row.get('result') == 'winner' and
    row['award_year'] == winner['award_year'] and
    normalize_heading(row['title']) == normalize_heading(winner['title'])]
  if not any(work_key(row) != work_key(winner) for row in matching):
    return
  credits = []
  for row in matching:
    credit = {'author': row['author'], 'url': row['source_url']}
    if credit not in credits:
      credits.append(credit)
  for row in matching:
    row['author'] = winner['author']
    row['author_source_url'] = history_url
    row['source_author_credits'] = credits


def reconcile_winner(rows, winner, history_url):
  correct_winner_credit(rows, winner, history_url)
  reference = work_key(winner)
  present = False
  for row in rows:
    if work_key(row) == reference:
      result, present = 'winner', True
    elif row.get('result') == 'winner':
      result = 'shortlisted'
    else:
      continue
    if row['result'] != result:
      row['result'] = result
      row['result_source_url'] = history_url
  if not present:
    rows.append(deepcopy(winner))


def fetch_center_official(recipe, parser, html, base_url, fetch_url,
    cached_parsed=None, incremental_update=False, progress=None):
  links = discover_links(html, base_url)
  if not links:
    raise ValueError('Official First Novel Prize landing page exposed no annual sources.')
  if fetch_url is None:
    raise ValueError('Official First Novel Prize history requires linked annual sources.')
  history_html = fetch_url(recipe.WINNERS_URL)
  history = parser.read_official_source(history_html, recipe.WINNERS_URL)
  if not history['complete']:
    raise ValueError('Official First Novel Prize winner history is incomplete: ' + '; '.join(history['notes']))
  links.extend(item for item in discover_links(history_html, recipe.WINNERS_URL) if item not in links)
  urls_by_year = {}
  for year, url in links:
    urls_by_year.setdefault(year, []).append(url)
  if not urls_by_year:
    raise ValueError('Official First Novel Prize discovery exposed no annual sources.')
  latest = max(urls_by_year)
  expected = set(range(recipe.FIRST_YEAR, latest + 1))
  if set(urls_by_year) != expected or latest < datetime.datetime.now().year - 1:
    raise ValueError('Official First Novel Prize annual discovery has missing or unexpected award years.')
  winners = {}
  winner_rows = {}
  for row in history['rows']:
    winners.setdefault(str(row['award_year']), []).append(work_key(row))
    winner_rows[str(row['award_year'])] = row
  if (any(len(works) != 1 for works in winners.values()) or
      set(winners) != {str(year) for year in range(recipe.FIRST_YEAR, max(map(int, winners)) + 1)}):
    raise ValueError('Official First Novel Prize winner history has missing award years.')
  cache = ParsedUnitCache('center-first-novel-annual-v1', json.dumps([
    recipe.source_id, base_url, recipe.WINNERS_URL, recipe.FIRST_YEAR, recipe.NAME]),
    cached_parsed, incremental_update)
  entries, notes = [], []
  for index, year in enumerate(sorted(urls_by_year), 1):
    key = str(year)
    urls = sorted(set(urls_by_year[year]))
    winner = sorted(winners.get(key, []))
    revision = [urls, winner]
    old = cache.old_units.get(key) or {}
    old_meta = old.get('metadata') or {}
    reused = None
    previous_winners = sorted(work_key(row) for row in cache.previous(key) if row.get('result') == 'winner')
    if (year < min(latest, datetime.datetime.now().year) and winner and
        old_meta.get('settled') is True and previous_winners == winner and
        all(row.get('award_year') == key for row in cache.previous(key))):
      reused = cache.reuse(key, revision)
    if reused is not None:
      entries.extend(reused)
      notes.extend(old_meta.get('notes', []))
      continue
    source_rows, source_notes, complete = [], [], True
    try:
      for url in urls:
        source = parser.read_official_source(fetch_url(url), url)
        if any(row['award_year'] != key for row in source['rows']):
          raise ValueError('Official First Novel Prize source returned another award year.')
        source_rows.extend(source['rows'])
        source_notes.extend(source['notes'])
        complete = complete and source['complete']
      if key in winner_rows:
        reconcile_winner(source_rows, winner_rows[key], recipe.WINNERS_URL)
      rows = parser.entries_from_rows(parser.dedupe_rows(source_rows))
      if not complete and cache.previous(key):
        rows = cache.previous(key)
    except (ImportCancelledError, CamoufoxRequiredError):
      raise
    except Exception as err:
      # Existing full imports allow useful partial official history. Compatible
      # updates retain an entire failed year, never a mixture of stale ballots.
      rows, complete = cache.previous(key), False
      source_notes.append(f'Official First Novel Prize {year} could not be refreshed: {err}; retained cached year where available.')
    actual_winners = sorted(work_key(row) for row in rows if row.get('result') == 'winner')
    settled = bool(rows) and bool(winner) and actual_winners == winner
    cache.put(key, rows, revision=revision, complete=complete,
      metadata={'settled': settled, 'notes': source_notes})
    entries.extend(rows)
    notes.extend(source_notes)
    if progress:
      progress(index, len(urls_by_year), f'Processed First Novel Prize {year}')
  entries.sort(key=lambda row: position_sort_key(row.get('position', '')))
  parsed = parser.parsed_result(recipe.NAME, base_url, entries, notes)
  parsed['incremental_state'] = cache.state(entries)
  return parsed
