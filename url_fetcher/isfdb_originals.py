"""Resolve explicitly linked originals without guessing translated identities.

Only resolved ISFDB IDs collapse editions within the same award year/category.
Parsed metadata is reused from the existing flat import cache for thirty days;
raw pages are never persisted by the runtime resolver.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError
  from calibre_plugins.list_switchboard.parser.award_base import assign_positions
  from calibre_plugins.list_switchboard.parser.isfdb_title import parse_title_record, title_id
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError
  from parser.award_base import assign_positions
  from parser.isfdb_title import parse_title_record, title_id

RESOLUTION_VERSION = 1


def cached_originals(cached, now):
  records = {}
  for entry in (cached or {}).get('entries', ()):
    record = entry.get('original_work') or {}
    if not isinstance(record, dict):
      continue
    try:
      age = now - datetime.fromisoformat(record['resolved_at'].replace('Z', '+00:00'))
      valid = (bool(record.get('id')) and record.get('id') == title_id(record.get('url'))
        and record.get('resolution_version') == RESOLUTION_VERSION
        and record.get('title') and record.get('authors')
        and record.get('language', '').casefold() == 'english'
        and timedelta(0) <= age <= timedelta(days=30))
    except (AttributeError, KeyError, TypeError, ValueError):
      valid = False
    if valid:
      records[record['id']] = deepcopy(record)
  return records


def resolve_original_works(parsed, fetch_url, cached=None, progress=None, now=None):
  now = now or datetime.now(timezone.utc)
  result = deepcopy(parsed)
  entries = result.get('entries', [])
  targets = {}
  for entry in entries:
    original = entry.get('original_work') or {}
    if title_id(original.get('url')):
      targets.setdefault(original['id'], original)
  records = cached_originals(cached, now)
  pending = [(key, target) for key, target in targets.items() if key not in records]
  notes = list(result.get('notes', ()))
  consecutive_failures = 0
  for number, (key, target) in enumerate(pending, 1):
    if progress is not None:
      progress(number, len(pending) + 1,
        f'Resolving original work {number} of {len(pending)}: {target["title"]}...')
    if consecutive_failures >= 3:
      notes.append(f'ISFDB original-work lookups stopped after three consecutive failures; '
        f'{len(pending) - number + 1} records still need review.')
      break
    try:
      if fetch_url is None:
        raise ValueError('No original-work fetcher is available.')
      record = parse_title_record(fetch_url(target['url']), target['url'])
      variants = record.get('english_variants', ())
      consecutive_failures = 0
      if record['language'].casefold() != 'english':
        if not variants:
          notes.append(f'Original work "{target["title"]}" is listed in '
            f'{record["language"]} without a linked English title; '
            'its Japanese edition is retained for review.')
          continue
        english = parse_title_record(fetch_url(variants[0]['url']), variants[0]['url'])
        if english['language'].casefold() != 'english':
          raise ValueError('The linked English variant is not an English record.')
        record = dict(english, id=record['id'], url=record['url'],
          metadata_url=english['url'], original_title=record['title'],
          original_language=record['language'])
      aliases = list(dict.fromkeys(variant['title'] for variant in variants
        if variant['title'] != record['title']))
      if aliases:
        record['aliases'] = aliases
      record.pop('english_variants', None)
      record['resolved_at'] = now.isoformat()
      record['resolution_version'] = RESOLUTION_VERSION
      records[key] = record
    except (ImportCancelledError, CamoufoxRequiredError):
      raise
    except Exception as err:
      consecutive_failures = 0 if isinstance(err, ValueError) else consecutive_failures + 1
      notes.append(f'Could not resolve original work "{target["title"]}" '
        f'({target["url"]}); its Japanese edition is retained: {err}')
  groups = {}
  for index, entry in enumerate(entries):
    original = entry.get('original_work') or {}
    record = records.get(original.get('id'))
    if record is None:
      key = ('unresolved', index)
    else:
      edition = {key: deepcopy(entry[key]) for key in
        ('position', 'title', 'authors', 'source', 'result') if key in entry}
      entry['translated_editions'] = [edition]
      entry['title'] = record['title']
      entry['authors'] = list(record['authors'])
      if record.get('aliases'):
        aliases = entry.get('aliases') or []
        if isinstance(aliases, str):
          aliases = [aliases]
        entry['aliases'] = list(dict.fromkeys(list(aliases) + record['aliases']))
      entry['source'] = {'url': record.get('metadata_url', record['url']), 'name': '', 'source_id': ''}
      entry['original_work'] = deepcopy(record)
      key = (entry.get('award_year'), entry.get('category'), record['id'])
    if key in groups:
      existing = groups[key]
      existing['translated_editions'].extend(entry['translated_editions'])
      if entry.get('result') == 'winner':
        existing['result'] = 'winner'
    else:
      groups[key] = entry
  by_year = {}
  for entry in groups.values():
    by_year.setdefault(entry['award_year'], []).append(entry)
  result['entries'] = []
  for year, rows in by_year.items():
    original_count = sum(entry['award_year'] == year for entry in entries)
    result['entries'].extend(assign_positions(rows, int(year))
      if len(rows) < original_count else rows)
  unresolved = sum(bool(entry.get('original_work')) and
    not entry['original_work'].get('resolved_at') for entry in result['entries'])
  if unresolved:
    notes.append(f'{unresolved} Japanese-edition records could not be resolved to '
      'English originals and remain available for review.')
  result['notes'] = notes
  if progress is not None:
    progress(1, 1, 'Finished resolving original works.')
  return result
