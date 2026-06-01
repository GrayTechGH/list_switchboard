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
  from calibre_plugins.list_switchboard.matching import match_keys, normalize_match_text
except ImportError:
  from matching import match_keys, normalize_match_text


STORAGE_SCHEMA_VERSION = 1
STORAGE_PARENT_FOLDER = 'plugins'
STORAGE_FOLDER = 'list_switchboard'


def utc_now_text():
  return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def safe_list_id(value):
  value = normalize_match_text(value).replace(' ', '_')
  value = re.sub(r'[^a-z0-9_]+', '_', value).strip('_')
  return value or 'imported_list'


def entry_key(entry):
  return '|'.join([
    normalize_match_text(entry.get('title', '')),
    normalize_match_text(entry.get('author', '')),
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


def build_import_cache_data(list_id, parsed, recipe=None):
  list_id = safe_list_id(list_id)
  entries = parsed.get('entries') or []
  return {
    'schema_version': STORAGE_SCHEMA_VERSION,
    'list_id': list_id,
    'list_name': parsed.get('name') or getattr(recipe, 'NAME', '') or list_id,
    'source_url': parsed.get('source_url') or getattr(recipe, 'URL', ''),
    'fetched_at': utc_now_text(),
    'parser': safe_list_id(getattr(recipe, 'source_id', '') or parsed.get('parser', '') or list_id),
    'entries': entries,
    'notes': parsed.get('notes') or [],
    'match_series': parsed.get('match_series', True),
    'append_state': parsed_append_state(parsed),
  }


def repaired_translator_credit_entry(entry):
  """
  Repair stale cached rows where a parser split `Title, Author, translated by X`
  at the final comma and cached the translator as the author.
  """
  entry = dict(entry or {})
  title = entry.get('title', '')
  author = entry.get('author', '')
  if not isinstance(title, str) or not isinstance(author, str):
    return entry
  if ',' not in title:
    return entry
  if not re.match(r'^(translated\s+by\s+.+|.+\s+translator)$', author.strip(), re.I):
    return entry
  repaired_title, repaired_author = [part.strip() for part in title.rsplit(',', 1)]
  if repaired_title and repaired_author:
    entry['title'] = repaired_title
    entry['author'] = repaired_author
  return entry


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
      if not data or data.get('schema_version') != STORAGE_SCHEMA_VERSION:
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
    return {
      'name': cache.get('list_name') or cache.get('list_id') or '',
      'source_url': cache.get('source_url', ''),
      'entries': [
        repaired_translator_credit_entry(entry)
        for entry in (cache.get('entries') or [])
      ],
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
        'imported_author': entry.get('author', ''),
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
    item['imported_author'] = entry.get('author', item.get('imported_author', ''))
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

  def unmatched_match_item_for_review_row(self, row):
    entry = row.get('entry') or {}
    key = row.get('entry_key') or entry_key(entry)
    if not key:
      return None
    matched_book_ids = list(row.get('original_book_ids') or row.get('book_ids') or [])
    matched_books = list(row.get('original_matched_books') or row.get('matched_books') or [])
    return {
      'entry_key': key,
      'imported_title': entry.get('title', row.get('imported_title', '')),
      'imported_author': entry.get('author', row.get('imported_author', '')),
      'ignored': True,
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
        item = self.unmatched_match_item_for_review_row(row)
        if item is not None and existing_item != item:
          by_key[key] = item
          if not item_is_ignored_directive(existing_item):
            saved_unmatched += 1
          changed = True
      elif not matched:
        if source == 'saved/manual override':
          if key in by_key:
            by_key.pop(key, None)
            removed += 1
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

  def saved_match_entry_for_book(self, book_id, position, entries, db):
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
      and self.author_matches(authors, entry.get('author', ''))
    ]
    if len(matches) == 1:
      return matches[0]
    candidates = matches or entries
    return self.choose_saved_match_entry(book_id, position, candidates, db)

  def saved_match_choice_label(self, entry):
    title = entry.get('title', '') or 'Untitled'
    author = entry.get('author', '') or 'Unknown author'
    return f'{title} - {author}'

  def choose_saved_match_entry(self, book_id, position, entries, db):
    chooser = getattr(self, '_saved_match_entry_chooser', None)
    if chooser is not None:
      return chooser(book_id, position, entries, db)
    try:
      from calibre_plugins.list_switchboard.dialogs import ChoiceDialog
    except ImportError:
      from dialogs import ChoiceDialog
    title = db.field_for('title', book_id, default_value='') or ''
    authors = db.field_for('authors', book_id, default_value=[]) or []
    if not isinstance(authors, (list, tuple)):
      authors = [str(authors)]
    choices = [self.saved_match_choice_label(entry) for entry in entries]
    by_label = dict(zip(choices, entries))
    d = ChoiceDialog(
      self.gui,
      'Save Active List Matches',
      'Multiple imported entries have the same position.\n\n'
      f'Calibre book:\n{title}\n{", ".join(authors)}\n\n'
      f'Position {position}:',
      choices,
      'Save Selected Match')
    accepted = QDialog.Accepted if QDialog is not None else 1
    if d.exec() != accepted:
      self.debug_storage_save_match_skipped(book_id, 'duplicate position disambiguation cancelled', position)
      return None
    return by_label.get(d.choice)

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
    by_key = {}
    db = self.db.new_api
    all_ids = self.all_book_ids()
    titles = db.all_field_for('title', all_ids, default_value='')
    series = self.all_local_series_values(all_ids)
    authors = db.all_field_for('authors', all_ids, default_value='')
    by_title, by_series = self.import_match_indexes(all_ids, titles, series)
    active_index_field = self.active_series_index_field()
    saved = 0
    active_book_ids = self.active_book_ids_for_list(list_name)
    self.debug_storage_save_matches_start(
      list_id, list_name, len(active_book_ids), len(cached_entries), 0)
    active_positions = set()
    for book_id in active_book_ids:
      position, _numeric_position = self.read_position_display(
        active_index_field, book_id,
        self.read_field(self.active_list_field_key(), book_id))
      normalized_position = self.normalized_position_text(position)
      if normalized_position:
        active_positions.add(normalized_position)
    missing_position_entries = [
      entry for entry in cached_entries
      if self.normalized_position_text(entry.get('position', '')) not in active_positions
    ]
    self.debug_storage_save_matches_missing_positions(list_id, missing_position_entries)
    for book_id in active_book_ids:
      position, _numeric_position = self.read_position_display(
        active_index_field, book_id,
        self.read_field(self.active_list_field_key(), book_id))
      position_entries = entries_by_position.get(self.normalized_position_text(position), [])
      entry = self.saved_match_entry_for_book(book_id, position, position_entries, db)
      if not entry:
        continue
      direct_candidates = self.direct_match_candidates_for_entry(
        entry, by_title=by_title, by_series=by_series, authors=authors,
        match_series=cache.get('match_series', True))
      self.debug_storage_save_match_direct_candidates(
        book_id, position, entry, direct_candidates)
      if book_id in direct_candidates:
        self.debug_storage_save_match_skipped(book_id, 'direct match recomputed automatically', position)
        continue
      key = entry_key(entry)
      item = self.saved_match_item_for_book(by_key.get(key), entry, book_id, db)
      if item is None:
        continue
      by_key[key] = item
      self.debug_storage_save_match(book_id, key, position)
      saved += 1
    self.write_match_cache(list_id, list(by_key.values()))
    self.debug_storage_save_matches_finished(list_id, saved, len(by_key))
    if saved:
      self.status_message(f'Saved {saved} manual match override(s) for "{list_name}".')
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
      URL = cache.get('source_url', '')
      source_id = cache.get('list_id') or safe_list_id(active)

    self.save_active_matches_for_recipe(CachedActiveRecipe)

  def active_list_field_key(self):
    try:
      from calibre_plugins.list_switchboard.config import prefs
    except ImportError:
      from config import prefs
    return prefs['active_list_field']
