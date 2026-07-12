#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Field access, normalization, and metadata writes.

Maintenance notes:
- Stored Lists may be a comments field or a multiple-value text field. Keep
  parse_stored_lists(), rebuild_stored_lists(), format_stored_lists(), and
  stored_write_updates() aligned so reads and writes round-trip through
  Calibre correctly.
- Active List fields are expected to be Calibre series fields. Series index
  lookup is deliberately defensive because Calibre exposes custom series index
  columns differently across versions and field types.
- Multi-book Active List series writes use new_api.set_field() with formatted
  "List Name [index]" values so imports can update the series values in bulk.
  Single-book writes keep set_custom(), which is the safest Calibre API for a
  one-off series value/index pair.
"""

import math
from collections import OrderedDict

from calibre_plugins.list_switchboard.config import prefs

try:
  from calibre_plugins.list_switchboard.errors import ListSwitchboardError
except ImportError:
  from errors import ListSwitchboardError

try:
  from calibre_plugins.list_switchboard.matching import clean_name, normalize_key, split_position_suffix
except ImportError:
  from matching import clean_name, normalize_key, split_position_suffix


def parse_stored_lists(raw):
  if raw is None:
    return []
  if isinstance(raw, (list, tuple, set)):
    return [str(entry).strip() for entry in raw]
  return [entry.strip() for entry in (raw or '').split(',')]


def format_stored_lists(names):
  return ', '.join(sort_names(names))


def rebuild_stored_lists(value, transform=None):
  """Apply a Stored List edit, then return its canonical field value.

  ``value`` may be the raw Calibre value or a parsed entry sequence.  The
  optional transform receives nonempty entries before one shared
  case-insensitive dedupe and formatting pass.
  """
  entries = [entry for entry in parse_stored_lists(value) if entry]
  if transform is not None:
    entries = transform(entries)
  return format_stored_lists(unique_case_insensitive(
    entry for entry in entries if entry))


def sort_names(names):
  return sorted(names, key=lambda item: item.strip().casefold())


def validate_list_name(name):
  raw_name = '' if name is None else str(name).strip()
  _base_name, position = split_position_suffix(raw_name)
  if position is not None:
    raise ListSwitchboardError(
      'Reading list names cannot end in a numeric position such as "[1]" because that syntax is reserved.')
  name = clean_name(raw_name)
  if not name:
    raise ListSwitchboardError('Reading list names cannot be empty.')
  if ',' in name:
    raise ListSwitchboardError(
      'Reading list names cannot contain commas because commas are used to separate Stored Lists.')
  return name


def format_list_entry(name, position=None):
  name = clean_name(name)
  if position in (None, ''):
    return name
  return f'{name} [{position}]'


def unique_case_insensitive(names):
  seen = OrderedDict()
  for name in names:
    key = normalize_key(name)
    if key and key not in seen:
      seen[key] = name.strip()
  return list(seen.values())


def next_whole_index_after(index):
  try:
    return math.floor(float(index)) + 1
  except Exception:
    return 1


class MetadataMixin:
  """
  Metadata primitives shared by import flow and list-state operations.

  Type constraints:
  - self.db must be a Calibre database-like object with new_api, field_metadata,
    prefs, and set_custom.
  - prefs['active_list_field'] must refer to a series field before writes that
    assign positions are attempted.

  Invariants:
  - read_field() returns a string for scalar fields and a comma-formatted string
    for Stored Lists regardless of Calibre's underlying storage shape.
  - write_fields() filters unchanged Active List updates before computing the
    final changed id set.
  - Stored List entries preserve optional position suffixes in the form
    "List Name [1.5]".

  Refactor warning:
  - Several UI progress paths assume progress_callback receives counts matching
    the number of real writes. Do not enqueue unchanged stored rows merely to
    preserve dictionary shape.
  """

  def read_field(self, field, book_id):
    value = self.db.new_api.field_for(field, book_id, default_value='')
    if field == prefs.get('stored_lists_field'):
      return format_stored_lists(parse_stored_lists(value))
    return '' if value is None else str(value)

  def active_field_metadata(self):
    return self.db.field_metadata[prefs['active_list_field']]

  def stored_field_metadata(self):
    return self.db.field_metadata[prefs['stored_lists_field']]

  def active_field_is_series(self):
    return self.active_field_metadata().get('datatype') == 'series'

  def resolve_search_term_fields(self, search_term):
    try:
      mapped = self.db.field_metadata.search_term_to_field_key(search_term)
    except Exception:
      return []
    if not mapped:
      return []
    if isinstance(mapped, (list, tuple, set)):
      return [field for field in mapped if isinstance(field, str)]
    return [mapped] if isinstance(mapped, str) else []

  def local_series_fields(self):
    fields = OrderedDict()
    fields['series'] = None
    search_terms = []
    try:
      search_terms.append(self.db.prefs.get('similar_series_search_key'))
    except Exception:
      pass
    search_terms.append('series')
    for search_term in search_terms:
      if not search_term:
        continue
      for field in self.resolve_search_term_fields(search_term):
        fields[field] = None
    return list(fields)

  def all_local_series_values(self, ids):
    db = self.db.new_api
    values_by_book = {book_id: [] for book_id in ids}
    for field in self.local_series_fields():
      try:
        values = db.all_field_for(field, ids, default_value='')
      except Exception:
        continue
      for book_id, value in values.items():
        for item in parse_stored_lists(value):
          item = clean_name(item)
          if item:
            values_by_book.setdefault(book_id, []).append(item)
    return values_by_book

  def stored_field_is_multiple(self):
    metadata = self.stored_field_metadata()
    return metadata.get('datatype') == 'text' and bool(metadata.get('is_multiple'))

  def supported_stored_field(self):
    metadata = self.stored_field_metadata()
    datatype = metadata.get('datatype')
    return datatype == 'comments' or (datatype == 'text' and bool(metadata.get('is_multiple')))

  def stored_write_updates(self, stored_updates):
    if not stored_updates or not self.stored_field_is_multiple():
      return stored_updates
    return {
      book_id: tuple(entry for entry in parse_stored_lists(value) if entry)
      for book_id, value in stored_updates.items()
    }

  def canonical_stored_value(self, value):
    return format_stored_lists(parse_stored_lists(value))

  def filter_unchanged_stored_updates(self, stored_updates):
    filtered = OrderedDict()
    for book_id, value in (stored_updates or {}).items():
      formatted = self.canonical_stored_value(value)
      current = self.read_field(prefs['stored_lists_field'], book_id)
      if current != formatted:
        filtered[book_id] = formatted
    return filtered

  def active_series_index_field(self):
    metadata = self.active_field_metadata()
    if metadata.get('datatype') != 'series':
      return None
    field = prefs['active_list_field']
    candidates = []
    try:
      candidates.append(self.db.field_metadata.cc_series_index_column_for(field))
    except Exception as err:
      self.debug_metadata_helper_failed(field, err)
    if field:
      candidates.append(f'{field}_index')
      if field.startswith('#'):
        candidates.append(f'{field[1:]}_index')
    for candidate in candidates:
      if not candidate:
        continue
      try:
        if candidate in self.db.field_metadata or self.db.field_metadata.is_series_index(candidate):
          return candidate
      except Exception:
        pass
      ids = self.all_book_ids()
      if ids:
        try:
          self.db.new_api.field_for(candidate, ids[0], default_value=None)
          return candidate
        except Exception:
          pass
    self.debug_metadata_no_series_index_field(field)
    return None

  def read_series_index(self, index_field, book_id):
    try:
      value = self.db.new_api.field_for(index_field, book_id, default_value=None)
      return None if value is None else float(value)
    except Exception:
      return None

  def read_formatted_field(self, field, book_id):
    try:
      metadata = self.db.new_api.get_proxy_metadata(book_id)
      _name, value = metadata.format_field(field, series_with_index=True)
      return '' if value is None else str(value)
    except Exception as err:
      self.debug_metadata_formatted_read_failed(field, book_id, err)
      return ''

  def read_position_display(self, index_field, book_id, fallback_name=None):
    value = self.db.new_api.field_for(index_field, book_id, default_value=None) if index_field else None
    if value is None and fallback_name:
      _name, value = split_position_suffix(fallback_name)
    if value is None:
      formatted = self.read_formatted_field(prefs['active_list_field'], book_id)
      if formatted:
        _name, value = split_position_suffix(formatted)
    if value is None:
      return '', None
    try:
      numeric = float(value)
      return f'{numeric:g}', numeric
    except Exception:
      return str(value), None

  def read_active_position(self, index_field, book_id):
    if index_field:
      numeric_position = self.read_series_index(index_field, book_id)
      if numeric_position is not None:
        return numeric_position
    _position, numeric_position = self.read_position_display(
      None, book_id, self.read_field(prefs['active_list_field'], book_id))
    return numeric_position

  def normalized_position_text(self, position):
    if position in (None, ''):
      return ''
    try:
      return f'{float(position):g}'
    except Exception:
      return str(position).strip()

  def active_list_value_matches(self, book_id, list_name, position):
    current = clean_name(self.read_field(prefs['active_list_field'], book_id))
    if normalize_key(current) != normalize_key(list_name):
      return False
    expected_position = self.normalized_position_text(position)
    if not expected_position:
      return True
    index_field = self.active_series_index_field()
    current_position, _numeric_position = self.read_position_display(
      index_field, book_id, self.read_field(prefs['active_list_field'], book_id))
    return self.normalized_position_text(current_position) == expected_position

  def require_series_position_field(self, action, list_name):
    index_field = self.active_series_index_field()
    if self.active_field_is_series() and not index_field:
      raise ListSwitchboardError(
        f'Cannot {action} "{list_name}" because List Switchboard could not read the series index field. '
        'No Active List metadata was changed.')
    return index_field

  def require_series_position(self, action, list_name, book_id, position):
    if self.active_field_is_series() and not position:
      raise ListSwitchboardError(
        f'Cannot {action} "{list_name}" because List Switchboard could not read the list position for: '
        f'{self.book_summary(book_id)}.\n'
        'No Active List metadata was changed.')

  def require_stored_series_position(self, list_name, book_id, position):
    if self.active_field_is_series() and not position:
      raise ListSwitchboardError(
        f'Cannot switch to "{list_name}" because a book has no stored list position: '
        f'{self.book_summary(book_id)}.\n'
        'No Active List metadata was changed.')

  def book_summary(self, book_id):
    db = self.db.new_api
    title = str(db.field_for('title', book_id, default_value='') or 'Untitled')
    authors = self.display_authors(db.field_for('authors', book_id, default_value=''))
    if authors:
      return f'"{title}" by {authors} (book id {book_id})'
    return f'"{title}" (book id {book_id})'

  def active_book_ids_for_list(self, list_name):
    key = normalize_key(list_name)
    return [
      book_id for book_id in self.all_book_ids()
      if normalize_key(clean_name(self.read_field(prefs['active_list_field'], book_id))) == key
    ]

  def ensure_active_list_can_be_stored(self, list_name):
    if not self.active_field_is_series():
      return
    index_field = self.require_series_position_field('store', list_name)
    missing = []
    for book_id in self.active_book_ids_for_list(list_name):
      raw_active = self.read_field(prefs['active_list_field'], book_id)
      formatted_active = self.read_formatted_field(prefs['active_list_field'], book_id)
      position, _numeric_position = self.read_position_display(index_field, book_id, raw_active)
      self.debug_metadata_preflight_store(
        book_id, raw_active, formatted_active, index_field, position)
      if not position:
        missing.append(book_id)
    if not missing:
      return
    details = '\n'.join(f'- {self.book_summary(book_id)}' for book_id in missing[:12])
    if len(missing) > 12:
      details = f'{details}\n- ...and {len(missing) - 12} more'
    raise ListSwitchboardError(
      f'Cannot store "{list_name}" because List Switchboard could not read list positions for '
      f'{len(missing)} books.\n\n'
      f'{details}\n\nNo Active List metadata was changed.')

  def stored_entry_for_active(self, book_id, active, require_position=False):
    index_field = self.require_series_position_field('store', active) if require_position else (
      self.active_series_index_field())
    raw_active = self.read_field(prefs['active_list_field'], book_id)
    formatted_active = self.read_formatted_field(prefs['active_list_field'], book_id)
    position, _numeric_position = self.read_position_display(
      index_field, book_id, raw_active)
    self.debug_writes_store_active(book_id, active, raw_active, formatted_active, position)
    if require_position:
      self.require_series_position('store', active, book_id, position)
    return format_list_entry(active, position)

  def series_index_updates(self, active_updates):
    index_field = self.active_series_index_field()
    if not index_field and not self.active_field_is_series():
      return {}
    max_by_list = {}
    max_in_field = 0
    update_ids = set(active_updates)
    for book_id in self.all_book_ids():
      if book_id in update_ids:
        continue
      list_name = clean_name(self.read_field(prefs['active_list_field'], book_id))
      index = self.read_active_position(index_field, book_id)
      if index is None:
        continue
      max_in_field = max(max_in_field, index)
      if not list_name:
        continue
      key = normalize_key(list_name)
      max_by_list[key] = max(max_by_list.get(key, 0), index)

    index_updates = {}
    for book_id, list_name in active_updates.items():
      list_name = clean_name(list_name)
      if not list_name:
        continue
      key = normalize_key(list_name)
      current_max = max_by_list[key] if key in max_by_list else max_in_field
      next_index = next_whole_index_after(current_max)
      max_by_list[key] = next_index
      max_in_field = max(max_in_field, next_index)
      index_updates[book_id] = float(next_index)
    return index_updates

  def write_fields(
      self, active_updates=None, stored_updates=None, assign_series_indexes=False,
      active_index_updates=None, progress_callback=None):
    db = self.db.new_api
    changed = set()
    if active_updates:
      if active_index_updates is not None:
        index_updates = active_index_updates
      else:
        index_updates = self.series_index_updates(active_updates) if assign_series_indexes else {}
      active_updates = self.filter_unchanged_active_updates(active_updates, index_updates)
      index_updates = {
        book_id: position for book_id, position in index_updates.items()
        if book_id in active_updates
      }
    stored_updates = self.filter_unchanged_stored_updates(stored_updates)
    snapshots = self.field_write_snapshots(active_updates, stored_updates)
    affected = set(active_updates or ()) | set(stored_updates or ())
    try:
      if active_updates:
        if self.active_field_is_series():
          self.write_active_series_values(active_updates, index_updates, progress_callback)
        else:
          try:
            self.debug_writes_active_field(len(active_updates))
            db.set_field(prefs['active_list_field'], active_updates)
            if progress_callback is not None:
              progress_callback(len(active_updates), 'Finished Active List metadata updates...')
          except Exception as err:
            raise ListSwitchboardError(
              f'Could not write the Active List Field "{prefs["active_list_field"]}": {err}')
        changed.update(active_updates)
      if stored_updates:
        try:
          self.debug_writes_stored_field(len(stored_updates))
          db.set_field(prefs['stored_lists_field'], self.stored_write_updates(stored_updates))
          if progress_callback is not None:
            progress_callback(len(stored_updates), 'Finished Stored Lists metadata updates...')
        except Exception as err:
          raise ListSwitchboardError(
            f'Could not write the Stored Lists Field "{prefs["stored_lists_field"]}": {err}')
        changed.update(stored_updates)
    except Exception as err:
      recovery_failures = self.restore_field_write_snapshots(snapshots)
      try:
        self.refresh_books(affected)
      except Exception as refresh_err:
        recovery_failures.append(f'Could not refresh affected books: {refresh_err}')
      if recovery_failures:
        raise ListSwitchboardError(
          f'{err}\n\nThe failed metadata update may be partially applied. '
          f'Rollback also failed: {"; ".join(recovery_failures)}')
      raise ListSwitchboardError(
        f'{err}\n\nList Switchboard restored the previous Active List and Stored Lists values.')

    self.refresh_books(changed)
    self.debug_writes_finished(active_updates, stored_updates, changed)

  def field_write_snapshots(self, active_updates, stored_updates):
    """Capture every field value touched by one logical metadata transition."""
    db = self.db.new_api
    snapshots = {}
    if active_updates:
      active_field = prefs['active_list_field']
      active_values = {
        book_id: db.field_for(active_field, book_id, default_value='')
        for book_id in active_updates
      }
      active_snapshot = {
        'field': active_field,
        'values': active_values,
        'is_series': self.active_field_is_series(),
      }
      if active_snapshot['is_series']:
        index_field = self.active_series_index_field()
        active_snapshot['index_values'] = {
          book_id: db.field_for(index_field, book_id, default_value=None)
          for book_id in active_updates
        } if index_field else {}
      snapshots['active'] = active_snapshot
    if stored_updates:
      stored_field = prefs['stored_lists_field']
      snapshots['stored'] = {
        'field': stored_field,
        'values': {
          book_id: db.field_for(stored_field, book_id, default_value='')
          for book_id in stored_updates
        },
      }
    return snapshots

  def restore_field_write_snapshots(self, snapshots):
    """Best-effort rollback after either half of a paired field update fails."""
    failures = []
    active = snapshots.get('active')
    if active and active.get('values'):
      try:
        if active.get('is_series'):
          self.write_active_series_values(
            active['values'], active.get('index_values') or {})
        else:
          self.debug_writes_active_field(len(active['values']))
          self.db.new_api.set_field(active['field'], active['values'])
      except Exception as err:
        failures.append(f'could not restore Active List values: {err}')
    stored = snapshots.get('stored')
    if stored and stored.get('values'):
      try:
        self.db.new_api.set_field(
          stored['field'], self.stored_write_updates(stored['values']))
      except Exception as err:
        failures.append(f'could not restore Stored Lists values: {err}')
    return failures

  def filter_unchanged_active_updates(self, active_updates, index_updates=None):
    filtered = OrderedDict()
    index_updates = index_updates or {}
    for book_id, value in active_updates.items():
      position = index_updates.get(book_id)
      if self.active_list_value_matches(book_id, value, position):
        continue
      filtered[book_id] = value
    return filtered

  def write_active_series_values(self, active_updates, index_updates, progress_callback=None):
    field = prefs['active_list_field']
    label = field[1:] if field.startswith('#') else field
    self.debug_writes_active_series_field(field, label, active_updates, index_updates)
    if len(active_updates) > 1:
      try:
        self.db.new_api.set_field(
          field,
          self.formatted_active_series_updates(active_updates, index_updates))
        if progress_callback is not None:
          progress_callback(len(active_updates), 'Finished Active List metadata updates...')
        return
      except Exception as err:
        raise ListSwitchboardError(
          f'Could not write the Active List Field "{prefs["active_list_field"]}": {err}')

    total = len(active_updates)
    for index, (book_id, value) in enumerate(active_updates.items(), start=1):
      extra = index_updates.get(book_id) if index_updates else None
      try:
        self.db.set_custom(
          book_id, clean_name(value), label=label, extra=extra,
          allow_case_change=True)
        if progress_callback is not None:
          progress_callback(1, f'Writing Active List metadata update {index} of {total}...')
      except Exception as err:
        raise ListSwitchboardError(
          f'Could not write "{clean_name(value)}" to the Active List Field for '
          f'{self.book_summary(book_id)}: {err}')

  def formatted_active_series_updates(self, active_updates, index_updates=None):
    index_updates = index_updates or {}
    formatted = {}
    for book_id, value in active_updates.items():
      name = clean_name(value)
      if not name:
        formatted[book_id] = ''
        continue
      position = self.normalized_position_text(index_updates.get(book_id))
      formatted[book_id] = format_list_entry(name, position)
    return formatted

  def repair_missing_stored_positions(self):
    index_field = self.active_series_index_field()
    if not index_field:
      self.debug_metadata_repair_skipped()
      return 0
    stored_updates = {}
    repaired = 0
    for book_id in self.all_book_ids():
      entries = [entry for entry in parse_stored_lists(
        self.read_field(prefs['stored_lists_field'], book_id)) if entry]
      missing = [index for index, entry in enumerate(entries) if split_position_suffix(entry)[1] is None]
      if len(missing) != 1:
        continue
      position, _numeric_position = self.read_position_display(index_field, book_id)
      if not position:
        continue
      entry_index = missing[0]
      name, _old_position = split_position_suffix(entries[entry_index])
      entries[entry_index] = format_list_entry(name, position)
      stored_updates[book_id] = rebuild_stored_lists(entries)
      repaired += 1
      self.debug_metadata_repaired_position(book_id, name, position)
    if stored_updates:
      self.write_fields(stored_updates=stored_updates)
    return repaired

  def clean_up_fields(self):
    if not self.ensure_configured():
      return
    try:
      self.library_state()
      repaired = self.repair_missing_stored_positions()
      if repaired:
        self.status_message(f'Cleaned up List Switchboard fields. Repaired {repaired} stored positions.')
      else:
        self.status_message('Cleaned up List Switchboard fields.')
    except Exception as err:
      self.show_exception('Clean Up List Switchboard Fields', err)
