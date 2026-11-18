"""Opt-in official annual-page lifecycle without changing category parsers.

Callers provide fresh discovery, a year-scoped reader and source-specific empty
page validation. Full-import failures still reach replacement-source handling;
updates retain a failed cached year pending recovery. Sources that already
support partial full imports opt in separately. These award readers emit
explicit entry provenance, restored after storage elision before reuse.
No raw pages are stored.
"""

import datetime

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError
  from calibre_plugins.list_switchboard.parser.incremental import ParsedUnitCache
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError
  from .incremental import ParsedUnitCache
  from .generic import position_sort_key


def read_annual_pages(source_key, discovered, fetch_url, read_year,
    cached_parsed=None, incremental_update=False, validate_empty=None, progress=None,
    allow_partial=False, failure_note=None):
  cache = ParsedUnitCache('official-annual-pages-v1', source_key, cached_parsed, incremental_update)
  # Storage elides an entry source equal to the list source. These annual award
  # readers always emit explicit provenance; restore it before reuse so an old
  # current-year row cannot inherit next year's new list URL after rollover.
  old_source = (cached_parsed.get('source') if isinstance(cached_parsed,dict) else None) or {}
  if isinstance(old_source,dict) and old_source.get('url'):
    for entry in cache.old_entries:
      if not entry.get('source'):
        entry['source']={'url':old_source['url'],'name':'','source_id':''}
  discovered = list(discovered)
  if not discovered:
    raise ValueError('Official overview did not expose award years.')
  latest = max(year for url, year in discovered)
  entries, notes = [], []
  for index, (url, year) in enumerate(discovered, 1):
    old = cache.old_units.get(url) or {}
    reused = None
    if (year < min(latest, datetime.datetime.now().year) and
        (old.get('metadata') or {}).get('settled') is True):
      reused = cache.reuse(url, revision=year)
    if reused is not None:
      entries.extend(reused)
      notes.extend((old.get('metadata') or {}).get('notes') or [])
    else:
      try:
        html = fetch_url(url)
        parsed = read_year(html, url)
        rows, unit_notes = parsed.get('entries') or [], parsed.get('notes') or []
        if any(str(row.get('award_year')) != str(year) for row in rows):
          raise ValueError('Annual source returned another award year.')
        complete = not unit_notes and (bool(rows) or bool(validate_empty and validate_empty(html, url, year)))
        if not complete and cache.previous(url):
          rows = cache.previous(url)
          if not unit_notes:
            unit_notes = [f'Official award year {year} did not expose a usable snapshot; retained cached entries.']
        cache.put(url, rows, revision=year, complete=complete, metadata={
          'settled': not rows or any(row.get('result') == 'winner' for row in rows),
          'notes': unit_notes})
        entries.extend(rows)
        notes.extend(unit_notes)
      except (ImportCancelledError, CamoufoxRequiredError):
        raise
      except Exception as err:
        if not cache.old_units and not allow_partial:
          raise
        entries.extend(cache.failed(url, revision=year))
        notes.extend((old.get('metadata') or {}).get('notes') or [])
        notes.append(failure_note(url,year,err) if failure_note else
          f'Official award year {year} could not be refreshed: {err}; retained cached entries.')
    if progress is not None:
      progress(index, len(discovered), f'Processed official award year {year}...')
  entries.sort(key=lambda row: position_sort_key(row.get('position', '')))
  return {'entries': entries, 'notes': notes, 'incremental_state': cache.state(entries)}
