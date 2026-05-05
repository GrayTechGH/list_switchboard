#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Active List and Stored Lists workflows.

Maintenance notes:
- This module owns user-visible list operations: add, switch, create, rename,
  remove, manage, and conflict repair.
- It depends on MetadataMixin for field parsing/writing and ImportFlowMixin for
  progress-wrapped writes. Keep those calls at the workflow boundary rather than
  duplicating field-write logic here.
- Operations should only add stored_updates for rows whose stored value changes.
  Progress dialogs use update counts as their denominator.
"""

from collections import Counter, OrderedDict

from qt.core import QDialog, QInputDialog

from calibre.gui2 import error_dialog, question_dialog
from calibre_plugins.list_switchboard.config import prefs

try:
  from calibre_plugins.list_switchboard.dialogs import ChoiceDialog, StoredListsDialog
except ImportError:
  from dialogs import ChoiceDialog, StoredListsDialog

try:
  from calibre_plugins.list_switchboard.errors import DuplicateStoredListsError, ListSwitchboardError
except ImportError:
  from errors import DuplicateStoredListsError, ListSwitchboardError

try:
  from calibre_plugins.list_switchboard.matching import clean_name, normalize_key, split_position_suffix
except ImportError:
  from matching import clean_name, normalize_key, split_position_suffix

try:
  from calibre_plugins.list_switchboard.metadata import (
    format_list_entry, format_stored_lists, next_whole_index_after, parse_stored_lists,
    unique_case_insensitive, validate_list_name,
  )
except ImportError:
  from metadata import (
    format_list_entry, format_stored_lists, next_whole_index_after, parse_stored_lists,
    unique_case_insensitive, validate_list_name,
  )


class ListStateMixin:
  """
  Maintains the logical Active List and Stored Lists state.

  Type constraints:
  - self.gui must be available for dialogs.
  - self.all_book_ids(), read_field(), write_fields(), and write_fields_with_progress()
    must be provided by the facade/mixins.

  Invariants:
  - At most one list is considered active after library_state() resolves or
    raises on conflicts.
  - Stored Lists must not contain duplicate case-insensitive list names for a
    single book after cleanup.
  - Switching lists moves the old Active List into Stored Lists before restoring
    the selected Stored List into the Active List field.

  Refactor warning:
  - Do not collapse Active List and Stored Lists writes into a single raw field
    operation. Series fields need position-aware active_index_updates.
  """

  def library_state(self, allow_duplicate_dialog=True):
    active_field = prefs['active_list_field']
    stored_field = prefs['stored_lists_field']
    ids = self.all_book_ids()
    active_counts = Counter()
    stored_names = OrderedDict()
    active_updates = {}
    stored_updates = {}
    duplicate_groups = []

    self.debug_metadata_library_state(active_field, stored_field)
    for book_id in ids:
      raw_active = self.read_field(active_field, book_id)
      raw_stored = self.read_field(stored_field, book_id)
      active, active_position = split_position_suffix(raw_active)
      if active:
        validate_list_name(active)
        active_counts[active] += 1

      entries = [entry for entry in parse_stored_lists(raw_stored) if entry]
      groups = OrderedDict()
      for entry in entries:
        validate_list_name(clean_name(entry))
        groups.setdefault(normalize_key(entry), []).append(entry)
      for values in groups.values():
        if len(values) > 1:
          duplicate_groups.append((book_id, values))

      cleaned_entries = []
      for key, values in groups.items():
        name = values[0]
        if active and key == normalize_key(active):
          continue
        cleaned_entries.append(name)
        stored_names.setdefault(key, clean_name(name))

      formatted = format_stored_lists(cleaned_entries)
      if active != raw_active:
        active_updates[book_id] = active
      if formatted != (raw_stored or ''):
        stored_updates[book_id] = formatted

    if duplicate_groups:
      if allow_duplicate_dialog and self.resolve_duplicate_stored_lists(duplicate_groups):
        return self.library_state(allow_duplicate_dialog=False)
      raise DuplicateStoredListsError(duplicate_groups)

    if active_updates or stored_updates:
      self.write_fields(active_updates, stored_updates)

    self.debug_metadata_counts(active_counts, stored_names)
    return active_counts, list(stored_names.values())

  def current_active(self):
    active_counts, _stored = self.library_state()
    if not active_counts:
      return None
    grouped = OrderedDict()
    for name, count in active_counts.items():
      grouped[normalize_key(name)] = (name, grouped.get(normalize_key(name), ('', 0))[1] + count)
    if len(grouped) == 1:
      return next(iter(grouped.values()))[0]
    return self.resolve_active_conflict(grouped)

  def add_selected_to_active(self):
    if not self.ensure_configured():
      return
    ids = self.selected_ids_with_series() if prefs.get('include_calibre_series', False) else self.selected_book_ids()
    self.debug_selection_ids(ids)
    if not ids:
      error_dialog(self.gui, 'List Switchboard', 'Select one or more books first.', show=True)
      return

    self.add_book_ids_to_active(ids)

  def selected_ids_with_series(self):
    return self.expand_ids_with_series(self.selected_book_ids())

  def expand_ids_with_series(self, ids):
    ids = sorted(set(ids))
    if not ids:
      return []
    all_ids = self.all_book_ids()
    series_by_id = self.all_local_series_values(all_ids)
    selected_series = set()
    for book_id in ids:
      selected_series.update(series_by_id.get(book_id, []))
    selected_series.discard('')
    if not selected_series:
      return ids

    expanded = set(ids)
    selected_keys = {normalize_key(name) for name in selected_series}
    for book_id, series_names in series_by_id.items():
      if any(normalize_key(clean_name(series_name or '')) in selected_keys for series_name in series_names):
        expanded.add(book_id)
    self.debug_selection_expanded_series(ids, expanded)
    return sorted(expanded)

  def add_book_ids_to_active(self, ids):
    active = self.current_active()
    if active is None:
      active = self.create_new_active_list(selected_ids=ids)
      if active is None:
        return

    updates = {}
    skipped = 0
    active_field = prefs['active_list_field']
    for book_id in ids:
      current = clean_name(self.read_field(active_field, book_id))
      if normalize_key(current) == normalize_key(active):
        skipped += 1
      else:
        updates[book_id] = active
    active_index_updates = self.added_active_index_updates(active, updates)
    self.write_fields(
      active_updates=updates,
      assign_series_indexes=True,
      active_index_updates=active_index_updates)
    self.status_message(
      f'Added {len(updates)} books to "{active}". Skipped {skipped} already on the list.')

  def added_active_index_updates(self, active, active_updates):
    index_field = self.active_series_index_field()
    if not index_field or not active_updates:
      return {}
    active_key = normalize_key(active)
    update_ids = set(active_updates)
    max_index = 0
    for book_id in self.all_book_ids():
      if book_id in update_ids:
        continue
      list_name = clean_name(self.read_field(prefs['active_list_field'], book_id))
      if normalize_key(list_name) != active_key:
        continue
      index = self.read_series_index(index_field, book_id)
      if index is None:
        continue
      max_index = max(max_index, index)

    index_updates = {}
    next_index = next_whole_index_after(max_index)
    for book_id in active_updates:
      index_updates[book_id] = float(next_index)
      next_index += 1
    return index_updates

  def select_active_list_books(self):
    if not self.ensure_configured():
      return
    active = self.current_active()
    if active is None:
      self.status_message('Create an Active List first.')
      return
    active_key = normalize_key(active)
    ids = [
      book_id for book_id in self.all_book_ids()
      if normalize_key(clean_name(self.read_field(prefs['active_list_field'], book_id))) == active_key
    ]
    if prefs.get('include_calibre_series', False):
      ids = self.expand_ids_with_series(ids)
    self.select_book_ids(ids, f'Selected {len(ids)} books in "{active}".')

  def current_stored_lists(self):
    _counts, stored = self.library_state()
    return stored

  def books_for_stored_list(self, list_name):
    if not list_name:
      return []
    db = self.db.new_api
    key = normalize_key(list_name)
    index_field = self.active_series_index_field()
    rows = []
    for book_id in self.all_book_ids():
      stored = parse_stored_lists(self.read_field(prefs['stored_lists_field'], book_id))
      stored_by_key = {normalize_key(entry): entry for entry in stored if entry}
      if key not in stored_by_key:
        continue
      position, numeric_position = self.read_position_display(index_field, book_id, stored_by_key[key])
      title = str(db.field_for('title', book_id, default_value='') or '')
      authors = self.display_authors(db.field_for('authors', book_id, default_value=''))
      sort_key = (
        0 if numeric_position is not None else 1,
        numeric_position if numeric_position is not None else 0,
        title.casefold(),
        authors.casefold()
      )
      rows.append((sort_key, position, title, authors))
    rows.sort(key=lambda row: row[0])
    return [(position, title, authors) for _sort_key, position, title, authors in rows]

  def switch_active_list(self):
    if not self.ensure_configured():
      return
    active = self.current_active()
    if active is None:
      self.create_new_active_list(selected_ids=self.selected_book_ids())
      return
    _counts, stored = self.library_state()
    choices = [name for name in stored if normalize_key(name) != normalize_key(active)]
    if not choices:
      self.status_message('There are no Stored Lists to switch to.')
      return
    intro = f'Current Active List:\n{active}\n\nStored Lists:'
    d = ChoiceDialog(self.gui, 'Switch Active List', intro, choices, 'Switch to Selected List')
    if d.exec() != QDialog.Accepted:
      return
    try:
      self._switch_to_existing(active, d.choice, show_progress=True)
      self.status_message(f'Switched Active List to "{d.choice}".')
    except Exception as err:
      self.show_exception('Switch Active List', err)

  def _switch_to_existing(self, old_active, new_active, show_progress=False):
    self.ensure_active_list_can_be_stored(old_active)
    active_updates = {}
    active_index_updates = {}
    index_field = self.active_series_index_field()
    stored_updates = {}
    for book_id in self.all_book_ids():
      active = clean_name(self.read_field(prefs['active_list_field'], book_id))
      stored = unique_case_insensitive([entry for entry in parse_stored_lists(
        self.read_field(prefs['stored_lists_field'], book_id)) if entry])
      stored_by_key = OrderedDict((normalize_key(name), name) for name in stored)

      if normalize_key(active) == normalize_key(old_active):
        active_updates[book_id] = ''
        stored_by_key[normalize_key(old_active)] = self.stored_entry_for_active(
          book_id, old_active, require_position=True)
      if normalize_key(new_active) in stored_by_key:
        stored_entry = stored_by_key[normalize_key(new_active)]
        active_name, position = split_position_suffix(stored_entry)
        index_field = self.require_series_position_field('switch to', new_active)
        self.require_stored_series_position(new_active, book_id, position)
        active_updates[book_id] = active_name
        if index_field and position:
          try:
            active_index_updates[book_id] = float(position)
          except Exception:
            pass
        del stored_by_key[normalize_key(new_active)]
      if active and normalize_key(active) != normalize_key(old_active):
        active_updates[book_id] = active

      stored_updates[book_id] = format_stored_lists(stored_by_key.values())
    if show_progress:
      self.write_fields_with_progress(
        'Switch Active List',
        f'Switching Active List to "{new_active}"...',
        active_updates=active_updates,
        stored_updates=stored_updates,
        assign_series_indexes=True,
        active_index_updates=active_index_updates,
        finishing_message=f'Switched Active List to "{new_active}".')
    else:
      self.write_fields(
        active_updates, stored_updates, assign_series_indexes=True,
        active_index_updates=active_index_updates)

  def create_new_active_list(self, selected_ids=None):
    if not self.ensure_configured():
      return None
    selected_ids = selected_ids if selected_ids is not None else self.selected_book_ids()
    name, ok = QInputDialog.getText(self.gui, 'Create New Active List', 'New Active List name:')
    if not ok:
      return None
    try:
      name = validate_list_name(str(name))
      active = self.current_active()
      _counts, stored = self.library_state()
      stored_by_key = OrderedDict((normalize_key(item), item) for item in stored)
      if active and normalize_key(name) == normalize_key(active):
        self._remove_active_from_stored(active)
        self.status_message(f'"{active}" is already the Active List.')
        return active
      if normalize_key(name) in stored_by_key:
        existing = stored_by_key[normalize_key(name)]
        if active:
          self._switch_to_existing(active, existing, show_progress=True)
        return existing
      if not selected_ids:
        error_dialog(self.gui, 'List Switchboard',
          'Select one or more books before creating a new Active List.', show=True)
        return None
      active_updates = {}
      stored_updates = {}
      if active:
        active_updates, stored_updates = self.active_to_stored_updates(active)
      active_updates.update({book_id: name for book_id in selected_ids})
      self.write_fields_with_progress(
        'Create New Active List',
        f'Creating Active List "{name}"...',
        active_updates=active_updates,
        stored_updates=stored_updates,
        assign_series_indexes=True,
        finishing_message=f'Created Active List "{name}".')
      self.status_message(f'Created Active List "{name}".')
      return name
    except Exception as err:
      self.show_exception('Create New Active List', err)
      return None

  def _move_active_to_stored(self, active):
    active_updates, stored_updates = self.active_to_stored_updates(active)
    self.write_fields(active_updates, stored_updates)

  def active_to_stored_updates(self, active):
    self.ensure_active_list_can_be_stored(active)
    active_updates = {}
    stored_updates = {}
    key = normalize_key(active)
    for book_id in self.all_book_ids():
      current = clean_name(self.read_field(prefs['active_list_field'], book_id))
      raw_stored = self.read_field(prefs['stored_lists_field'], book_id)
      stored = unique_case_insensitive([entry for entry in parse_stored_lists(
        raw_stored) if entry])
      stored_by_key = OrderedDict((normalize_key(name), name) for name in stored)
      if normalize_key(current) == key:
        active_updates[book_id] = ''
        stored_by_key[key] = self.stored_entry_for_active(book_id, active, require_position=True)
      formatted = format_stored_lists(stored_by_key.values())
      if formatted != (raw_stored or ''):
        stored_updates[book_id] = formatted
    return active_updates, stored_updates

  def _remove_active_from_stored(self, active):
    stored_updates = {}
    key = normalize_key(active)
    for book_id in self.all_book_ids():
      stored = [entry for entry in parse_stored_lists(
        self.read_field(prefs['stored_lists_field'], book_id)) if normalize_key(entry) != key]
      stored_updates[book_id] = format_stored_lists(unique_case_insensitive(stored))
    self.write_fields(stored_updates=stored_updates)

  def rename_active_list(self):
    active = self.current_active()
    if not active:
      error_dialog(self.gui, 'List Switchboard', 'Create an Active List first.', show=True)
      return
    new_name, ok = QInputDialog.getText(self.gui, 'Rename Active List', 'New Active List name:', text=active)
    if not ok:
      return
    try:
      new_name = validate_list_name(str(new_name))
      _counts, stored = self.library_state()
      if normalize_key(new_name) != normalize_key(active):
        all_names = [name for name in stored if normalize_key(name) != normalize_key(active)]
        if normalize_key(new_name) in {normalize_key(name) for name in all_names}:
          raise ListSwitchboardError('A list with that name already exists. Choose a unique name.')
      updates = {}
      for book_id in self.all_book_ids():
        if normalize_key(self.read_field(prefs['active_list_field'], book_id)) == normalize_key(active):
          updates[book_id] = new_name
      self.write_fields_with_progress(
        'Rename Active List',
        f'Renaming Active List to "{new_name}"...',
        active_updates=updates,
        finishing_message=f'Renamed Active List to "{new_name}".')
      self.status_message(f'Renamed Active List to "{new_name}".')
    except Exception as err:
      self.show_exception('Rename Active List', err)

  def remove_active_list(self):
    active = self.current_active()
    if not active:
      error_dialog(self.gui, 'List Switchboard', 'There is no Active List to remove.', show=True)
      return
    if not question_dialog(self.gui, 'Remove Active List',
      'This removes the list name from the configured metadata field.\n'
      'No books or book files will be deleted.\n\n'
      'This change cannot be undone by List Switchboard.\n'
      'You can manually edit the configured metadata fields afterward if needed.'):
      return
    active_updates = {}
    stored_updates = {}
    key = normalize_key(active)
    for book_id in self.all_book_ids():
      if normalize_key(self.read_field(prefs['active_list_field'], book_id)) == key:
        active_updates[book_id] = ''
      raw_stored = self.read_field(prefs['stored_lists_field'], book_id)
      stored = [entry for entry in parse_stored_lists(
        raw_stored) if normalize_key(entry) != key]
      formatted = format_stored_lists(unique_case_insensitive(stored))
      if formatted != (raw_stored or ''):
        stored_updates[book_id] = formatted
    self.write_fields_with_progress(
      'Remove Active List',
      f'Removing Active List "{active}"...',
      active_updates=active_updates,
      stored_updates=stored_updates,
      finishing_message=f'Removed Active List "{active}".')
    self.status_message(f'Removed Active List "{active}".')

  def manage_stored_lists(self):
    if not self.ensure_configured():
      return
    _counts, stored = self.library_state()
    if not stored:
      self.status_message('There are no Stored Lists to manage.')
      return
    d = StoredListsDialog(self.gui, self, stored)
    d.exec()

  def rename_stored_list(self, old_name):
    new_name, ok = QInputDialog.getText(self.gui, 'Rename Stored List', 'New Stored List name:', text=old_name)
    if not ok:
      return
    try:
      new_name = validate_list_name(str(new_name))
      active = self.current_active()
      _counts, stored = self.library_state()
      existing = {normalize_key(name) for name in stored if normalize_key(name) != normalize_key(old_name)}
      if active:
        existing.add(normalize_key(active))
      if normalize_key(new_name) in existing:
        raise ListSwitchboardError('A list with that name already exists. Choose a unique name.')
      stored_updates = {}
      for book_id in self.all_book_ids():
        updated = []
        for entry in parse_stored_lists(self.read_field(prefs['stored_lists_field'], book_id)):
          if not entry:
            continue
          if normalize_key(entry) == normalize_key(old_name):
            _old_entry_name, position = split_position_suffix(entry)
            updated.append(format_list_entry(new_name, position))
          else:
            updated.append(entry)
        stored_updates[book_id] = format_stored_lists(unique_case_insensitive(updated))
      self.write_fields_with_progress(
        'Rename Stored List',
        f'Renaming Stored List to "{new_name}"...',
        stored_updates=stored_updates,
        finishing_message=f'Renamed Stored List to "{new_name}".')
      self.status_message(f'Renamed Stored List to "{new_name}".')
    except Exception as err:
      self.show_exception('Rename Stored List', err)

  def remove_stored_list(self, name=None):
    if name is None:
      _counts, stored = self.library_state()
      d = ChoiceDialog(self.gui, 'Remove Stored List', 'Stored Lists:', stored, 'Remove Selected List')
      if d.exec() != QDialog.Accepted:
        return
      name = d.choice
    if not question_dialog(self.gui, 'Remove Stored List',
      f'Remove "{name}" from Stored Lists?\n\n'
      'This only removes the list name from the configured Stored Lists Field.\n'
      'No books or book files will be deleted.\n\n'
      'This change cannot be undone by List Switchboard.'):
      return
    key = normalize_key(name)
    stored_updates = {}
    for book_id in self.all_book_ids():
      stored = [entry for entry in parse_stored_lists(
        self.read_field(prefs['stored_lists_field'], book_id)) if normalize_key(entry) != key]
      stored_updates[book_id] = format_stored_lists(unique_case_insensitive(stored))
    self.write_fields_with_progress(
      'Remove Stored List',
      f'Removing Stored List "{name}"...',
      stored_updates=stored_updates,
      finishing_message=f'Removed Stored List "{name}".')
    self.status_message(f'Removed Stored List "{name}".')

  def resolve_active_conflict(self, grouped):
    choices = [f'{name}: {count} books' for name, count in grouped.values()]
    d = ChoiceDialog(self.gui, 'Resolve Active List Conflict',
      'The Active List Field currently contains multiple list names.\n'
      'Choose which list should become the Active List.', choices,
      'Set Selected List as Active List')
    if d.exec() != QDialog.Accepted:
      raise ListSwitchboardError('Resolve the Active List conflict before continuing.')
    chosen = d.choice.rsplit(': ', 1)[0]
    if not question_dialog(self.gui, 'Resolve Active List Conflict',
      f'Set "{chosen}" as the Active List and move the other Active List names to Stored Lists?'):
      raise ListSwitchboardError('Resolve the Active List conflict before continuing.')
    active_updates = {}
    stored_updates = {}
    chosen_key = normalize_key(chosen)
    moving_names = OrderedDict()
    for book_id in self.all_book_ids():
      active = clean_name(self.read_field(prefs['active_list_field'], book_id))
      if active and normalize_key(active) != chosen_key:
        moving_names.setdefault(normalize_key(active), active)
    for active in moving_names.values():
      self.ensure_active_list_can_be_stored(active)
    for book_id in self.all_book_ids():
      active = clean_name(self.read_field(prefs['active_list_field'], book_id))
      stored = unique_case_insensitive([entry for entry in parse_stored_lists(
        self.read_field(prefs['stored_lists_field'], book_id)) if entry])
      stored_by_key = OrderedDict((normalize_key(name), name) for name in stored)
      if active and normalize_key(active) != chosen_key:
        active_updates[book_id] = ''
        stored_by_key[normalize_key(active)] = self.stored_entry_for_active(
          book_id, active, require_position=True)
      elif active:
        active_updates[book_id] = chosen
      stored_by_key.pop(chosen_key, None)
      stored_updates[book_id] = format_stored_lists(stored_by_key.values())
    self.write_fields(active_updates, stored_updates)
    return chosen

  def resolve_duplicate_stored_lists(self, duplicate_groups):
    if not question_dialog(self.gui, 'Duplicate Stored Lists Found',
      'The Stored Lists Field contains duplicate list names.\n\n'
      'List Switchboard can keep the first spelling found for each duplicate group and remove the others.'):
      return False
    stored_updates = {}
    for book_id in self.all_book_ids():
      entries = [entry for entry in parse_stored_lists(self.read_field(
        prefs['stored_lists_field'], book_id)) if entry]
      stored_updates[book_id] = format_stored_lists(unique_case_insensitive(entries))
    self.write_fields(stored_updates=stored_updates)
    return True
