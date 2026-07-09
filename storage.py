#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
File-backed import cache and saved match overrides.

Maintenance notes:
- Files live under Calibre's user configuration plugins directory in a
  `list_switchboard` folder. Do not introduce nested cache folders inside it;
  users may inspect or back up these JSON files by hand.
- Import files cache parsed recipe output, not raw fetched source pages.
- Match files store explicit override matches only. Normal direct matches should
  be recomputed against the current library on each import.
"""

import json
import os
import re
from datetime import datetime, timezone

try:
  from qt.core import QDialog
except Exception:
  QDialog = None

try:
  from calibre.constants import config_dir
except Exception:
  config_dir = None

try:
  from calibre_plugins.list_switchboard.errors import ListSwitchboardError
except ImportError:
  from errors import ListSwitchboardError

try:
  from calibre_plugins.list_switchboard.matching import (
    imported_author_display_value, imported_author_key,
    imported_author_search_text, match_keys, normalize_match_text,
    series_match_keys,
  )
except ImportError:
  from matching import (
    imported_author_display_value, imported_author_key,
    imported_author_search_text, match_keys, normalize_match_text,
    series_match_keys,
  )


STORAGE_SCHEMA_VERSION = 2
STORAGE_PARENT_FOLDER = 'plugins'
STORAGE_FOLDER = 'list_switchboard'


class SaveActiveMatchesCancelled(Exception):
  pass


def utc_now_text():
  return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def safe_list_id(value):
  value = normalize_match_text(value).replace(' ', '_')
  value = re.sub(r'[^a-z0-9_]+', '_', value).strip('_')
  return value or 'imported_list'


def entry_key(entry):
  return '|'.join([
    normalize_match_text(entry.get('title', '')),
    imported_author_key(entry),
  ])


def entry_title_matches_book(entry, title):
  imported_title = normalize_match_text(entry.get('title', ''))
  book_title = normalize_match_text(title)
  if not imported_title or not book_title:
    return False
  if imported_title == book_title:
    return True
  imported_keys = set(match_keys(entry.get('title', '')))
  book_keys = set(match_keys(title))
  if imported_keys & book_keys:
    return True
  return imported_title in book_title or book_title in imported_title


def item_is_ignored_directive(item):
  if not isinstance(item, dict):
    return False
  return bool(item.get('ignored') or item.get('unmatched'))


def matched_book_ids_for_match_item(item):
  if not isinstance(item, dict):
    return []
  raw_book_ids = item.get('matched_book_ids')
  if raw_book_ids is None:
    raw_book_ids = [item.get('matched_book_id')]
  if not isinstance(raw_book_ids, (list, tuple)):
    raw_book_ids = [raw_book_ids]
  book_ids = []
  for raw_book_id in raw_book_ids:
    append_unique_book_id(book_ids, raw_book_id)
  return book_ids


def append_unique_book_id(values, book_id):
  try:
    book_id = int(book_id)
  except Exception:
    return values
  if book_id not in values:
    values.append(book_id)
  return values


def parsed_append_state(parsed):
  entries = parsed.get('entries') or []
  last_entry = entries[-1] if entries else {}
  return {
    'entry_count': len(entries),
    'last_position': str(last_entry.get('position', '') or ''),
    'last_entry_key': entry_key(last_entry) if last_entry else '',
    'source_revision': parsed.get('source_revision'),
  }


def source_object(url='', name='', source_id=''):
  return {
    'url': str(url or ''),
    'name': str(name or ''),
    'source_id': str(source_id or ''),
  }


def parsed_source_object(list_id, parsed, recipe=None):
  existing = parsed.get('source') if isinstance(parsed.get('source'), dict) else {}
  source_id = (
    existing.get('source_id')
    or getattr(recipe, 'source_id', '')
    or parsed.get('source_id', '')
    or parsed.get('parser', '')
    or list_id
  )
  return source_object(
    existing.get('url') or getattr(recipe, 'URL', ''),
    existing.get('name') or parsed.get('source_name') or getattr(recipe, 'SOURCE_NAME', '') or getattr(recipe, 'NAME', ''),
    source_id)


def cache_source_object(cache):
  source = cache.get('source') if isinstance(cache.get('source'), dict) else {}
  return source_object(
    source.get('url', ''),
    source.get('name', ''),
    source.get('source_id', ''))


def entry_source_object(entry, list_source):
  source = entry.get('source') if isinstance(entry.get('source'), dict) else {}
  url = source.get('url', '')
  name = source.get('name', '')
  source_id = source.get('source_id', '')
  if not url and not name and not source_id:
    return None
  candidate = source_object(url, name, source_id)
  if (
      candidate.get('url') == list_source.get('url')
      and candidate.get('name') in ('', list_source.get('name'))
      and candidate.get('source_id') in ('', list_source.get('source_id'))):
    return None
  return candidate


def normalize_cache_entry_for_write(entry, list_source):
  legacy_keys = [key for key in ('author', 'source_url') if key in entry]
  if legacy_keys:
    raise ListSwitchboardError(
      'Imported entries must use schema 2 fields; found legacy field(s): '
      + ', '.join(legacy_keys))
  normalized = {
    'position': str(entry.get('position', '') or ''),
    'title': str(entry.get('title', '') or ''),
    'authors': [str(author or '').strip() for author in (entry.get('authors') or []) if str(author or '').strip()],
  }
  for key, value in entry.items():
    if key in ('position', 'title', 'authors', 'source'):
      continue
    normalized[key] = value
  source = entry_source_object(entry, list_source)
  if source is not None:
    normalized['source'] = source
  return normalized


def build_import_cache_data(list_id, parsed, recipe=None):
  list_id = safe_list_id(list_id)
  list_source = parsed_source_object(list_id, parsed, recipe=recipe)
  entries = [
    normalize_cache_entry_for_write(entry, list_source)
    for entry in (parsed.get('entries') or [])
  ]
  data = {
    'schema_version': STORAGE_SCHEMA_VERSION,
    'list_id': list_id,
    'list_name': parsed.get('name') or getattr(recipe, 'NAME', '') or list_id,
    'source': list_source,
    'fetched_at': utc_now_text(),
    'parser': safe_list_id(getattr(recipe, 'source_id', '') or parsed.get('parser', '') or list_id),
    'entries': entries,
    'notes': parsed.get('notes') or [],
    'match_series': parsed.get('match_series', True),
    'append_state': parsed_append_state({'entries': entries, 'source_revision': parsed.get('source_revision')}),
  }
  incremental_state = parsed.get('incremental_state')
  if isinstance(incremental_state, dict):
    data['incremental_state'] = incremental_state
  return data


class StorageMixin:
  """
  Owns JSON persistence for imported-list cache and match overrides.

  Type constraints:
  - self.db.new_api must be available when saving match overrides from the
    current Active List.
  - MetadataMixin methods are expected on self through ListSwitchboardCore.
  """

  def __getattr__(self, name):
    if name.startswith('debug_storage_') or name.startswith('debug_import_'):
      return self._debug_storage_noop
    raise AttributeError(name)

  def _debug_storage_noop(self, *_args, **_kwargs):
    pass

  def storage_root(self):
    root = getattr(self, '_storage_root', None)
    if root:
      self.debug_storage_root(root, 'override')
      return root
    base = config_dir or os.getcwd()
    root = os.path.join(base, STORAGE_PARENT_FOLDER, STORAGE_FOLDER)
    source = 'calibre config_dir' if config_dir else 'current working directory fallback'
    self.debug_storage_root(root, source)
    return root

  def ensure_storage_root(self):
    root = self.storage_root()
    os.makedirs(root, exist_ok=True)
    self.debug_storage_root_ready(root)
    return root

  def storage_path(self, filename):
    return os.path.join(self.storage_root(), filename)

  def import_cache_path(self, list_id):
    path = self.storage_path(f'import_{safe_list_id(list_id)}.json')
    self.debug_storage_path('import cache', path)
    return path

  def match_cache_path(self, list_id):
    path = self.storage_path(f'match_{safe_list_id(list_id)}.json')
    self.debug_storage_path('match cache', path)
    return path

  def import_cache_paths(self):
    root = self.storage_root()
    try:
      names = os.listdir(root)
    except FileNotFoundError:
      return []
    except Exception as err:
      self.debug_storage_read_failed(root, err)
      return []
    return [
      os.path.join(root, name) for name in sorted(names)
      if name.startswith('import_') and name.endswith('.json')
    ]

  def read_json_file(self, path):
    try:
      with open(path, 'r', encoding='utf-8') as handle:
        data = json.load(handle)
    except FileNotFoundError:
      self.debug_storage_read_missing(path)
      return None
    except Exception as err:
      self.debug_storage_read_failed(path, err)
      return None
    if not isinstance(data, dict):
      self.debug_storage_read_invalid(path, 'top-level value is not a JSON object')
      return None
    self.debug_storage_read_ok(path, sorted(data.keys()))
    return data

  def write_json_file(self, path, data):
    try:
      self.ensure_storage_root()
      with open(path, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write('\n')
      self.debug_storage_write_ok(path, os.path.getsize(path))
    except Exception as err:
      raise ListSwitchboardError(f'Could not write List Switchboard data file "{path}": {err}')

  def read_import_cache(self, list_id):
    safe_id = safe_list_id(list_id)
    data = self.read_json_file(self.import_cache_path(safe_id))
    if not data:
      self.debug_storage_import_cache(safe_id, 'miss', reason='file not found or unreadable')
      return None
    if data.get('schema_version') != STORAGE_SCHEMA_VERSION:
      self.debug_storage_import_cache(
        safe_id, 'ignored', reason=f'schema_version={data.get("schema_version")}')
      return None
    if not isinstance(data.get('entries'), list):
      self.debug_storage_import_cache(safe_id, 'ignored', reason='entries is not a list')
      return None
    self.debug_storage_import_cache(safe_id, 'hit', entries=len(data.get('entries') or []))
    return data

  def import_cache_for_active_list(self, list_name):
    list_key = normalize_match_text(list_name)
    for path in self.import_cache_paths():
      data = self.read_json_file(path)
      if not data:
        continue
      if data.get('schema_version') != STORAGE_SCHEMA_VERSION:
        continue
      if normalize_match_text(data.get('list_name', '')) == list_key:
        if not isinstance(data.get('entries'), list):
          self.debug_storage_import_cache(
            data.get('list_id', ''), 'ignored', reason='entries is not a list')
          continue
        self.debug_storage_import_cache(
          data.get('list_id', ''), 'hit for active list',
          entries=len(data.get('entries') or []))
        return data
    return None

  def write_import_cache(self, list_id, parsed, recipe=None):
    list_id = safe_list_id(list_id)
    path = self.import_cache_path(list_id)
    data = build_import_cache_data(list_id, parsed, recipe=recipe)
    entries = data.get('entries') or []
    self.debug_storage_write_start(path, 'import cache', len(entries))
    self.write_json_file(path, data)
    invalidator = getattr(self, 'invalidate_cached_active_add_import_map', None)
    if invalidator is not None:
      invalidator(list_id)
    self.debug_storage_import_cache(list_id, 'saved', entries=len(entries))
    return data

  def cached_import_to_parsed(self, cache):
    source = cache_source_object(cache)
    return {
      'name': cache.get('list_name') or cache.get('list_id') or '',
      'source': source,
      'entries': [dict(entry) for entry in (cache.get('entries') or [])],
      'notes': cache.get('notes') or [],
      'match_series': cache.get('match_series', True),
      'list_id': cache.get('list_id') or '',
      'from_cache': True,
    }

  def merge_append_import_cache(self, list_id, old_cache, parsed, recipe=None):
    list_id = safe_list_id(list_id)
    old_entries = old_cache.get('entries') or []
    new_entries = parsed.get('entries') or []
    if not old_entries or not new_entries:
      self.debug_storage_append_cache(
        list_id, len(old_entries), len(new_entries), 'replace',
        reason='old or new cache has no entries')
      return self.write_import_cache(list_id, parsed, recipe=recipe)
    old_keys = [entry_key(entry) for entry in old_entries]
    new_keys = [entry_key(entry) for entry in new_entries]
    if not old_keys or new_keys[:len(old_keys)] != old_keys:
      self.debug_storage_append_cache(
        list_id, len(old_entries), len(new_entries), 'replace',
        reason='new entries do not preserve old prefix')
      return self.write_import_cache(list_id, parsed, recipe=recipe)
    merged = dict(parsed)
    merged['entries'] = old_entries + new_entries[len(old_entries):]
    self.debug_storage_append_cache(
      list_id, len(old_entries), len(new_entries), 'append',
      reason=f'added={len(merged["entries"]) - len(old_entries)}')
    return self.write_import_cache(list_id, merged, recipe=recipe)

  def read_match_cache(self, list_id):
    safe_id = safe_list_id(list_id)
    data = self.read_json_file(self.match_cache_path(safe_id))
    if not data:
      self.debug_storage_match_cache(safe_id, 'miss', reason='file not found or unreadable')
      return {'schema_version': STORAGE_SCHEMA_VERSION, 'list_id': safe_id, 'matches': []}
    if data.get('schema_version') != STORAGE_SCHEMA_VERSION:
      self.debug_storage_match_cache(
        safe_id, 'ignored', reason=f'schema_version={data.get("schema_version")}')
      return {'schema_version': STORAGE_SCHEMA_VERSION, 'list_id': safe_id, 'matches': []}
    if not isinstance(data.get('matches'), list):
      data['matches'] = []
      self.debug_storage_match_cache(safe_id, 'normalized', reason='matches was not a list')
    self.debug_storage_match_cache(safe_id, 'hit', matches=len(data.get('matches') or []))
    return data

  def write_match_cache(self, list_id, matches):
    safe_id = safe_list_id(list_id)
    path = self.match_cache_path(safe_id)
    data = {
      'schema_version': STORAGE_SCHEMA_VERSION,
      'list_id': safe_id,
      'saved_at': utc_now_text(),
      'matches': matches,
    }
    self.debug_storage_write_start(path, 'match cache', len(matches))
    self.write_json_file(path, data)
    self.debug_storage_match_cache(safe_id, 'saved', matches=len(matches))
    return data

  def saved_match_overrides(self, list_id):
    overrides = {}
    for item in self.read_match_cache(list_id).get('matches', []):
      key = item.get('entry_key')
      book_id = item.get('matched_book_id')
      if key and book_id is not None and not item_is_ignored_directive(item):
        overrides[key] = item
    self.debug_storage_match_cache(safe_list_id(list_id), 'overrides loaded', matches=len(overrides))
    return overrides

  def saved_unmatched_overrides(self, list_id):
    overrides = {}
    for item in self.read_match_cache(list_id).get('matches', []):
      key = item.get('entry_key') if isinstance(item, dict) else None
      if key and item_is_ignored_directive(item):
        overrides[key] = item
    self.debug_storage_match_cache(
      safe_list_id(list_id), 'unmatched directives loaded', matches=len(overrides))
    return overrides

  def saved_match_item_for_book(self, item, entry, book_id, db):
    key = entry_key(entry)
    if not key:
      return None
    matched_title = db.field_for('title', book_id, default_value='') or ''
    matched_authors = db.field_for('authors', book_id, default_value=[]) or []
    if not isinstance(matched_authors, (list, tuple)):
      matched_authors = [str(matched_authors)]

    if item is None:
      item = {
        'entry_key': key,
        'imported_title': entry.get('title', ''),
        'imported_author': imported_author_display_value(entry),
        'matched_book_id': book_id,
        'matched_book_ids': [],
        'matched_title': matched_title,
        'matched_authors': list(matched_authors),
        'matched_books': [],
        'matched_at': utc_now_text(),
      }
    else:
      item.pop('ignored', None)
      item.pop('unmatched', None)
      item.pop('previous_matched_book_id', None)
      item.pop('previous_matched_book_ids', None)
      item.pop('previous_matched_books', None)
      item.pop('previous_match_source', None)
      item.pop('unmatched_at', None)

    item['imported_title'] = entry.get('title', item.get('imported_title', ''))
    item['imported_author'] = imported_author_display_value(entry) or item.get('imported_author', '')
    matched_book_ids = item.get('matched_book_ids')
    if not isinstance(matched_book_ids, list):
      matched_book_ids = []
    if item.get('matched_book_id') is not None:
      append_unique_book_id(matched_book_ids, item.get('matched_book_id'))
    append_unique_book_id(matched_book_ids, book_id)
    item['matched_book_ids'] = matched_book_ids
    item['matched_book_id'] = matched_book_ids[0] if matched_book_ids else book_id

    matched_books = item.get('matched_books')
    if not isinstance(matched_books, list):
      matched_books = []
    existing_book = None
    for matched_book in matched_books:
      if isinstance(matched_book, dict) and matched_book.get('matched_book_id') == book_id:
        existing_book = matched_book
        break
    if existing_book is None:
      matched_books.append({
        'matched_book_id': book_id,
        'matched_title': matched_title,
        'matched_authors': list(matched_authors),
      })
    else:
      existing_book['matched_title'] = matched_title
      existing_book['matched_authors'] = list(matched_authors)
    item['matched_books'] = matched_books
    item['matched_at'] = utc_now_text()
    item['matched_title'] = matched_title
    item['matched_authors'] = list(matched_authors)
    return item

  def upsert_saved_match_override_for_book(self, list_id, entry, book_id, db=None):
    key = entry_key(entry)
    if not key:
      return None
    db = db or self.db.new_api
    existing = self.read_match_cache(list_id).get('matches', [])
    unkeyed = []
    by_key = {}
    for item in existing:
      item_key = item.get('entry_key') if isinstance(item, dict) else None
      if item_key:
        by_key[item_key] = dict(item)
      elif isinstance(item, dict):
        unkeyed.append(item)
    by_key[key] = self.saved_match_item_for_book(by_key.get(key), entry, book_id, db)
    self.write_match_cache(list_id, unkeyed + list(by_key.values()))
    self.debug_storage_save_match(book_id, key, entry.get('position', ''))
    return by_key[key]

  def remove_saved_match_override(self, list_id, entry_or_key):
    key = entry_or_key if isinstance(entry_or_key, str) else entry_key(entry_or_key)
    if not key:
      return False
    existing = self.read_match_cache(list_id).get('matches', [])
    kept = []
    removed = False
    for item in existing:
      item_key = item.get('entry_key') if isinstance(item, dict) else None
      if item_key == key:
        removed = True
        continue
      kept.append(item)
    if removed:
      self.write_match_cache(list_id, kept)
    return removed

  def unmatched_match_item_for_review_row(self, row, ignored=False):
    entry = row.get('entry') or {}
    key = row.get('entry_key') or entry_key(entry)
    if not key:
      return None
    matched_book_ids = list(
      row.get('original_book_ids')
      or row.get('book_ids')
      or row.get('previous_book_ids')
      or [])
    matched_books = list(
      row.get('original_matched_books')
      or row.get('matched_books')
      or row.get('previous_matched_books')
      or [])
    item = {
      'entry_key': key,
      'imported_title': entry.get('title', row.get('imported_title', '')),
      'imported_author': imported_author_display_value(entry) or row.get('imported_author', ''),
      'unmatched': True,
      'previous_matched_book_id': matched_book_ids[0] if matched_book_ids else None,
      'previous_matched_book_ids': matched_book_ids,
      'previous_matched_books': matched_books,
      'previous_match_source': (
        row.get('previous_match_source')
        or row.get('original_match_source')
        or row.get('match_source', '')
      ),
      'unmatched_at': utc_now_text(),
    }
    if ignored:
      item['ignored'] = True
    return item

  def apply_import_review_match_changes(self, list_id, rows):
    if not list_id:
      return {'saved_unmatched': 0, 'removed': 0}
    existing = self.read_match_cache(list_id).get('matches', [])
    unkeyed = []
    by_key = {}
    for item in existing:
      item_key = item.get('entry_key') if isinstance(item, dict) else None
      if item_key:
        by_key[item_key] = dict(item)
      elif isinstance(item, dict):
        unkeyed.append(item)

    saved_unmatched = 0
    removed = 0
    changed = False
    for row in rows or []:
      key = row.get('entry_key') or entry_key(row.get('entry') or {})
      if not key:
        continue
      original_matched = bool(row.get('original_matched'))
      original_ignored = bool(row.get('original_ignored'))
      matched = bool(row.get('matched'))
      ignored = bool(row.get('ignored'))
      source = row.get('original_match_source') or row.get('match_source', '')
      current_source = row.get('match_source', '')
      existing_item = by_key.get(key)
      if ignored:
        item = self.unmatched_match_item_for_review_row(row, ignored=True)
        if item is not None and existing_item != item:
          by_key[key] = item
          if not item_is_ignored_directive(existing_item):
            saved_unmatched += 1
          changed = True
      elif not matched:
        save_unmatched = bool(
          original_matched
          or row.get('original_book_ids')
          or row.get('previous_book_ids')
          or source == 'saved/manual override')
        if save_unmatched:
          item = self.unmatched_match_item_for_review_row(row)
          if item is not None and existing_item != item:
            by_key[key] = item
            if not item_is_ignored_directive(existing_item):
              saved_unmatched += 1
            changed = True
        elif original_ignored and key in by_key and item_is_ignored_directive(by_key[key]):
          by_key.pop(key, None)
          removed += 1
          changed = True
      elif matched and current_source in ('manual find', 'active list/manual edit'):
        for book_id in row.get('book_ids') or []:
          by_key[key] = self.saved_match_item_for_book(
            by_key.get(key), row.get('entry') or {}, book_id, self.db.new_api)
          changed = True
      elif matched and (original_ignored or source == 'explicit unmatched' or source == 'ignored'):
        if key in by_key and item_is_ignored_directive(by_key[key]):
          by_key.pop(key, None)
          removed += 1
          changed = True

    if changed:
      self.write_match_cache(list_id, unkeyed + list(by_key.values()))
    return {'saved_unmatched': saved_unmatched, 'removed': removed}

  def cached_entries_by_position(self, entries):
    by_position = {}
    for entry in entries or []:
      position = self.normalized_position_text(entry.get('position', ''))
      if position:
        by_position.setdefault(position, []).append(entry)
    return by_position

  def cached_entries_by_key(self, entries):
    by_key = {}
    for entry in entries or []:
      key = entry_key(entry)
      if key and key not in by_key:
        by_key[key] = entry
    return by_key

  def saved_match_entries_by_active_book(self, existing_matches, entries_by_key, active_book_ids):
    active_book_ids = set(active_book_ids or [])
    entries_by_book = {}
    used_entry_keys = set()
    for item in existing_matches or []:
      if not isinstance(item, dict) or item_is_ignored_directive(item):
        continue
      key = item.get('entry_key')
      entry = entries_by_key.get(key)
      if not key or entry is None:
        continue
      for book_id in matched_book_ids_for_match_item(item):
        if book_id in active_book_ids:
          entries_by_book.setdefault(book_id, [])
          if entry not in entries_by_book[book_id]:
            entries_by_book[book_id].append(entry)
          used_entry_keys.add(key)
    return entries_by_book, used_entry_keys

  def saved_match_entry_for_book(
      self, book_id, position, entries, db, match_series=True, book_series=None):
    if not entries:
      self.debug_storage_save_match_skipped(book_id, 'no cached entry at active position', position)
      return None
    if len(entries) == 1:
      return entries[0]

    title = db.field_for('title', book_id, default_value='') or ''
    authors = db.field_for('authors', book_id, default_value=[]) or []
    matches = [
      entry for entry in entries
      if entry_title_matches_book(entry, title)
      and self.author_matches(authors, imported_author_search_text(entry))
    ]
    if len(matches) == 1:
      return matches[0]
    series_matches = []
    if match_series:
      series_matches = [
        entry for entry in entries
        if self.entry_matches_book_series(entry, book_series)
        and self.author_matches(authors, imported_author_search_text(entry))
      ]
      if len(series_matches) == 1:
        return series_matches[0]
    author_matches = [
      entry for entry in entries
      if self.author_matches(authors, imported_author_search_text(entry))
    ]
    if len(author_matches) == 1:
      return author_matches[0]
    candidates = matches or series_matches or author_matches or entries
    return self.choose_saved_match_entry(
      book_id, position, candidates, db, book_series=book_series)

  def entry_matches_book_series(self, entry, book_series):
    entry_keys = set(match_keys(entry.get('title', '')))
    if not entry_keys:
      return False
    if isinstance(book_series, str):
      series_values = [book_series] if book_series else []
    else:
      series_values = list(book_series or [])
    for series_value in series_values:
      if entry_keys & set(series_match_keys(series_value)):
        return True
    return False

  def choose_saved_match_entry(self, book_id, position, entries, db, book_series=None):
    chooser = getattr(self, '_saved_match_entry_chooser', None)
    if chooser is not None:
      return chooser(book_id, position, entries, db)
    try:
      from calibre_plugins.list_switchboard.dialogs import SavedMatchChoiceDialog
    except ImportError:
      from dialogs import SavedMatchChoiceDialog
    title = db.field_for('title', book_id, default_value='') or ''
    authors = db.field_for('authors', book_id, default_value=[]) or []
    if not isinstance(authors, (list, tuple)):
      authors = [str(authors)]
    d = SavedMatchChoiceDialog(
      self.gui,
      title,
      authors,
      book_series,
      position,
      entries)
    accepted = QDialog.Accepted if QDialog is not None else 1
    result = d.exec()
    if result == accepted:
      return d.selected_entry
    if result == getattr(d, 'SKIPPED', 2):
      self.debug_storage_save_match_skipped(book_id, 'duplicate position disambiguation skipped', position)
      return None
    else:
      self.debug_storage_save_match_skipped(book_id, 'duplicate position disambiguation cancelled', position)
      raise SaveActiveMatchesCancelled()

  def save_active_matches_for_recipe(self, recipe):
    if not self.ensure_configured():
      return
    list_id = safe_list_id(getattr(recipe, 'source_id', '') or recipe.NAME)
    cache = self.read_import_cache(list_id)
    if not cache:
      self.debug_storage_import_cache(list_id, 'miss', reason='cannot save overrides without parsed cache')
      raise ListSwitchboardError(
        f'Import "{recipe.NAME}" before saving match overrides. No cached parsed list was found.')
    list_name = cache.get('list_name') or recipe.NAME
    cached_entries = cache.get('entries') or []
    entries_by_position = self.cached_entries_by_position(cached_entries)
    entries_by_key = self.cached_entries_by_key(cached_entries)
    existing_matches = self.read_match_cache(list_id).get('matches', [])
    unkeyed = []
    by_key = {}
    for item in existing_matches:
      key = item.get('entry_key') if isinstance(item, dict) else None
      if key:
        by_key[key] = item
      else:
        unkeyed.append(item)
    db = self.db.new_api
    all_ids = self.all_book_ids()
    titles = db.all_field_for('title', all_ids, default_value='')
    series = self.all_local_series_values(all_ids)
    authors = db.all_field_for('authors', all_ids, default_value='')
    by_title, by_series = self.import_match_indexes(all_ids, titles, series)
    active_index_field = self.active_series_index_field()
    saved = 0
    active_book_ids = self.active_book_ids_for_list(list_name)
    existing_entries_by_book, used_entry_keys = self.saved_match_entries_by_active_book(
      existing_matches, entries_by_key, active_book_ids)
    self.debug_storage_save_matches_start(
      list_id, list_name, len(active_book_ids), len(cached_entries), 0)
    active_positions = set()
    active_positions_by_book = {}
    active_book_ids_by_position = {}
    for book_id in active_book_ids:
      position, _numeric_position = self.read_position_display(
        active_index_field, book_id,
        self.read_field(self.active_list_field_key(), book_id))
      normalized_position = self.normalized_position_text(position)
      if normalized_position:
        active_positions.add(normalized_position)
        active_positions_by_book[book_id] = normalized_position
        active_book_ids_by_position.setdefault(normalized_position, set()).add(book_id)
    saved_unmatched = 0
    for key, item in list(by_key.items()):
      if not isinstance(item, dict) or item_is_ignored_directive(item):
        continue
      entry = entries_by_key.get(key)
      if entry is None:
        continue
      entry_position = self.normalized_position_text(entry.get('position', ''))
      matched_book_ids = matched_book_ids_for_match_item(item)
      if not matched_book_ids:
        continue
      if any(active_positions_by_book.get(book_id) == entry_position for book_id in matched_book_ids):
        continue
      by_key[key] = self.unmatched_match_item_for_review_row({
        'entry': entry,
        'entry_key': key,
        'original_book_ids': matched_book_ids,
        'original_matched_books': item.get('matched_books') or [],
        'previous_match_source': 'saved/manual override',
        'original_match_source': 'saved/manual override',
      })
      saved_unmatched += 1
    existing_entry_keys_by_position = {}
    for book_id, entries in existing_entries_by_book.items():
      position = active_positions_by_book.get(book_id)
      if not position:
        continue
      for entry in entries:
        if self.normalized_position_text(entry.get('position', '')) == position:
          existing_entry_keys_by_position.setdefault(position, set()).add(entry_key(entry))
    direct_entry_keys_by_position = {}
    for position, position_entries in entries_by_position.items():
      if len(position_entries) < 2:
        continue
      active_ids_at_position = active_book_ids_by_position.get(position, set())
      if not active_ids_at_position:
        continue
      for entry in position_entries:
        direct_candidates = self.direct_match_candidates_for_entry(
          entry, by_title=by_title, by_series=by_series, authors=authors,
          match_series=cache.get('match_series', True))
        if active_ids_at_position & set(direct_candidates):
          direct_entry_keys_by_position.setdefault(position, set()).add(entry_key(entry))
    missing_position_entries = [
      entry for entry in cached_entries
      if self.normalized_position_text(entry.get('position', '')) not in active_positions
    ]
    self.debug_storage_save_matches_missing_positions(list_id, missing_position_entries)
    prompted_tied_positions = set()
    explicit_entry_keys = set()
    try:
      for book_id in active_book_ids:
        position, _numeric_position = self.read_position_display(
          active_index_field, book_id,
          self.read_field(self.active_list_field_key(), book_id))
        normalized_position = self.normalized_position_text(position)
        position_entries = entries_by_position.get(normalized_position, [])
        existing_entries = [
          entry for entry in existing_entries_by_book.get(book_id, [])
          if (
            self.normalized_position_text(entry.get('position', ''))
            == normalized_position
          )
        ]
        if existing_entries:
          continue
        saved_entry_keys_at_position = existing_entry_keys_by_position.get(normalized_position, set())
        direct_entry_keys_at_position = direct_entry_keys_by_position.get(normalized_position, set())
        resolved_entry_keys_at_position = saved_entry_keys_at_position | direct_entry_keys_at_position
        position_entry_keys = {entry_key(entry) for entry in position_entries}
        if len(position_entries) > 1 and position_entry_keys <= resolved_entry_keys_at_position:
          continue
        if normalized_position in prompted_tied_positions:
          continue
        if len(position_entries) > 1 and saved_entry_keys_at_position:
          prompted_tied_positions.add(normalized_position)
          entry = self.choose_saved_match_entry(
            book_id, position, position_entries, db,
            book_series=series.get(book_id, []))
          if not entry:
            continue
          explicit_entry_keys.add(entry_key(entry))
          selected_entries = [entry]
        else:
          available_position_entries = [
            candidate for candidate in position_entries
            if entry_key(candidate) not in used_entry_keys
          ]
          candidate_entries = position_entries if len(position_entries) > 1 else available_position_entries
          entry = self.saved_match_entry_for_book(
            book_id, position, candidate_entries, db,
            match_series=cache.get('match_series', True),
            book_series=series.get(book_id, []))
          selected_entries = [entry] if entry else []
        if not selected_entries:
          continue
        for entry in selected_entries:
          used_entry_keys.add(entry_key(entry))
          direct_candidates = self.direct_match_candidates_for_entry(
            entry, by_title=by_title, by_series=by_series, authors=authors,
            match_series=cache.get('match_series', True))
          self.debug_storage_save_match_direct_candidates(
            book_id, position, entry, direct_candidates)
          key = entry_key(entry)
          if book_id in direct_candidates and key not in explicit_entry_keys:
            self.debug_storage_save_match_skipped(book_id, 'direct match recomputed automatically', position)
            continue
          item = self.saved_match_item_for_book(by_key.get(key), entry, book_id, db)
          if item is None:
            continue
          by_key[key] = item
          self.debug_storage_save_match(book_id, key, position)
          saved += 1
    except SaveActiveMatchesCancelled:
      self.status_message(f'Save Active List Matches cancelled for "{list_name}".')
      return
    self.write_match_cache(list_id, unkeyed + list(by_key.values()))
    self.debug_storage_save_matches_finished(list_id, saved, len(by_key))
    if saved and saved_unmatched:
      self.status_message(
        f'Saved {saved} manual match override(s) and {saved_unmatched} unmatched directive(s) '
        f'for "{list_name}".')
    elif saved:
      self.status_message(f'Saved {saved} manual match override(s) for "{list_name}".')
    elif saved_unmatched:
      self.status_message(f'Saved {saved_unmatched} unmatched directive(s) for "{list_name}".')
    else:
      self.status_message(
        f'No manual match overrides needed for "{list_name}". Direct matches will be recomputed.')

  def save_active_matches_for_active_list(self):
    if not self.ensure_configured():
      return
    active = self.current_active()
    if not active:
      raise ListSwitchboardError('Create an Active List before saving match overrides.')
    cache = self.import_cache_for_active_list(active)
    if not cache:
      raise ListSwitchboardError(
        f'No cached imported list was found for the current Active List "{active}". '
        'Import that list before saving match overrides.')

    class CachedActiveRecipe:
      NAME = cache.get('list_name') or active
      URL = cache_source_object(cache).get('url', '')
      source_id = cache.get('list_id') or safe_list_id(active)

    self.save_active_matches_for_recipe(CachedActiveRecipe)

  def active_list_field_key(self):
    try:
      from calibre_plugins.list_switchboard.config import prefs
    except ImportError:
      from config import prefs
    return prefs['active_list_field']
