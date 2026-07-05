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
  from calibre_plugins.list_switchboard.dialogs import (
    ActiveAddMatchDialog, ChoiceDialog, StoredListsDialog,
  )
except ImportError:
  from dialogs import ActiveAddMatchDialog, ChoiceDialog, StoredListsDialog

try:
  from calibre_plugins.list_switchboard.errors import DuplicateStoredListsError, ListSwitchboardError
except ImportError:
  from errors import DuplicateStoredListsError, ListSwitchboardError

try:
  from calibre_plugins.list_switchboard.matching import (
    clean_name, match_keys, normalize_key, normalize_match_text, split_position_suffix,
  )
except ImportError:
  from matching import clean_name, match_keys, normalize_key, normalize_match_text, split_position_suffix

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

try:
  from calibre_plugins.list_switchboard.storage import entry_key, entry_title_matches_book
except ImportError:
  from storage import entry_key, entry_title_matches_book


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

  def add_selected_to_active(self, force_match_review=False):
    if not self.ensure_configured():
      return
    ids = self.selected_ids_with_series() if prefs.get('include_calibre_series', False) else self.selected_book_ids()
    self.debug_selection_ids(ids)
    if not ids:
      error_dialog(self.gui, 'List Switchboard', 'Select one or more books first.', show=True)
      return

    self.add_book_ids_to_active(ids, force_match_review=force_match_review)

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

  def add_book_ids_to_active(self, ids, force_match_review=False):
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
    cache = self.import_cache_for_active_list(active)
    if cache:
      self.debug_storage_cached_active_add_start(
        active, cache.get('list_id') or '', len(updates), len(cache.get('entries') or []))
      updates, active_index_updates = self.cached_active_add_updates(
        active, updates, cache, force_match_review=force_match_review)
    else:
      self.debug_storage_import_cache(active, 'miss for active add', reason='no cache for active list')
      active_index_updates = self.added_active_index_updates(active, updates)
    if not updates:
      self.status_message(
        f'Added 0 books to "{active}". Skipped {skipped} already on the list.')
      return
    self.write_fields(
      active_updates=updates,
      assign_series_indexes=True,
      active_index_updates=active_index_updates)
    self.status_message(
      f'Added {len(updates)} books to "{active}". Skipped {skipped} already on the list.')

  def cached_active_add_updates(self, active, active_updates, cache, force_match_review=False):
    fallback_index_updates = self.added_active_index_updates(active, active_updates)
    if not active_updates:
      return {}, {}
    entries = cache.get('entries') or []
    if not entries:
      return active_updates, fallback_index_updates
    db = self.db.new_api
    context = self.cached_active_add_context(active_updates, entries, cache, db)
    updates = {}
    index_updates = {}
    for book_id in active_updates:
      default_index = fallback_index_updates.get(book_id)
      entry, index_value, save_manual = self.cached_active_match_for_book(
        book_id, context, default_index, db,
        force_match_review=force_match_review,
        active_list_name=active)
      if entry is None and index_value is None:
        self.debug_storage_cached_active_add_decision(
          book_id, 'skipped no cached entry/index selected')
        continue
      updates[book_id] = active_updates[book_id]
      if index_value is None:
        index_value = default_index
      if index_value is not None:
        index_updates[book_id] = index_value
      if save_manual and entry is not None:
        self.debug_storage_cached_active_add_decision(
          book_id, 'saving nonautomatic override', entry, index_value)
        self.upsert_saved_match_override_for_book(
          cache.get('list_id') or active, entry, book_id, db=db)
      elif entry is not None:
        self.debug_storage_cached_active_add_decision(
          book_id, 'not saving override', entry, index_value)
    return updates, index_updates

  def cached_active_add_context(self, active_updates, entries, cache, db):
    selected_ids = list(active_updates)
    all_ids = self.all_book_ids()
    titles = self.cached_active_add_all_field_for(db, 'title', selected_ids, default_value='')
    authors = self.cached_active_add_all_field_for(db, 'authors', selected_ids, default_value='')
    list_id = cache.get('list_id')
    overrides = self.saved_match_overrides(list_id) if list_id else {}
    import_map = self.cached_active_add_import_map(cache, entries)

    override_entries_by_book = {}
    for key, override in overrides.items():
      entry = import_map['entries_by_key'].get(key)
      if entry is None:
        continue
      raw_book_ids = override.get('matched_book_ids')
      if raw_book_ids is None:
        raw_book_ids = [override.get('matched_book_id')]
      if not isinstance(raw_book_ids, (list, tuple)):
        raw_book_ids = [raw_book_ids]
      for raw_book_id in raw_book_ids:
        try:
          book_id = int(raw_book_id)
        except Exception:
          continue
        if book_id in active_updates and book_id not in override_entries_by_book:
            override_entries_by_book[book_id] = entry
    if not override_entries_by_book and self.cached_active_add_uses_custom_saved_override_lookup():
      for entry in import_map['unique_entries']:
        for book_id in self.saved_override_candidates_for_entry(
            entry, list_id, selected_ids):
          if book_id in active_updates and book_id not in override_entries_by_book:
            override_entries_by_book[book_id] = entry

    self.debug_storage_cached_active_add_context(
      list_id or '',
      len(selected_ids),
      len(all_ids),
      len(import_map['entries']),
      len(import_map['unique_entries']),
      len(overrides),
      len(override_entries_by_book),
      0,
      0,
      len(import_map['entries_by_title_key']),
      len(import_map['exact_entries_by_key']))

    # This context is deliberately per-click so imports cannot leave stale
    # title/series or cache-entry maps behind.
    return {
      'authors': authors,
      'author_tokens_by_key': import_map['author_tokens_by_key'],
      'all_ids': all_ids,
      'cache': cache,
      'db': db,
      'entries': import_map['entries'],
      'entries_by_title_key': import_map['entries_by_title_key'],
      'exact_entries_by_key': import_map['exact_entries_by_key'],
      'override_entries_by_book': override_entries_by_book,
      'selected_ids': selected_ids,
      'titles': titles,
      'unique_entries': import_map['unique_entries'],
    }

  def cached_active_add_import_map(self, cache, entries):
    list_id = cache.get('list_id') or ''
    cached = getattr(self, '_cached_active_add_import_map', None)
    if (
        cached is not None
        and cached.get('list_id') == list_id
        and cached.get('entries') is entries):
      self.debug_storage_cached_active_add_import_map(
        list_id, 'reused', len(cached['entries']), len(cached['unique_entries']),
        len(cached['entries_by_title_key']), len(cached['exact_entries_by_key']))
      return cached

    import_map = self.build_cached_active_add_import_map(entries)
    import_map['list_id'] = list_id
    self._cached_active_add_import_map = import_map
    self.debug_storage_cached_active_add_import_map(
      list_id, 'built', len(import_map['entries']), len(import_map['unique_entries']),
      len(import_map['entries_by_title_key']), len(import_map['exact_entries_by_key']))
    return import_map

  def build_cached_active_add_import_map(self, entries):
    unique_entries = []
    seen = set()
    entries_by_key = {}
    exact_entries_by_key = {}
    entries_by_title_key = {}
    author_tokens_by_key = {}
    for entry in entries:
      key = entry_key(entry)
      if key in seen:
        continue
      seen.add(key)
      unique_entries.append(entry)
      entries_by_key[key] = entry
      exact_entries_by_key.setdefault(key, []).append(entry)
      author_key = normalize_match_text(entry.get('author', ''))
      author_tokens_by_key[key] = {
        token for token in author_key.split()
        if len(token) > 1
      }
      for title_key in match_keys(entry.get('title', '')):
        entries_by_title_key.setdefault(title_key, []).append(entry)
    return {
      'author_tokens_by_key': author_tokens_by_key,
      'entries': entries,
      'entries_by_key': entries_by_key,
      'entries_by_title_key': entries_by_title_key,
      'exact_entries_by_key': exact_entries_by_key,
      'unique_entries': unique_entries,
    }

  def invalidate_cached_active_add_import_map(self, list_id=None):
    cached = getattr(self, '_cached_active_add_import_map', None)
    if cached is None:
      self.debug_storage_cached_active_add_import_map_invalidated(list_id or '', 0)
      return 0
    if list_id:
      removed = 1 if cached.get('list_id') == list_id else 0
      if removed:
        self._cached_active_add_import_map = None
      self.debug_storage_cached_active_add_import_map_invalidated(list_id, removed)
      return removed
    self._cached_active_add_import_map = None
    self.debug_storage_cached_active_add_import_map_invalidated('', 1)
    return 1

  def cached_active_add_all_field_for(self, db, field, ids, default_value=''):
    if hasattr(db, 'all_field_for'):
      return db.all_field_for(field, ids, default_value=default_value)
    return {
      book_id: db.field_for(field, book_id, default_value=default_value)
      for book_id in ids
    }

  def cached_active_add_uses_custom_saved_override_lookup(self):
    method = getattr(self, 'saved_override_candidates_for_entry', None)
    func = getattr(method, '__func__', method)
    return (
      getattr(func, '__name__', '') != 'saved_override_candidates_for_entry'
      or getattr(func, '__module__', '').split('.')[-1] != 'matching'
    )

  def cached_active_match_for_book(
      self, book_id, context, default_index, db, force_match_review=False,
      active_list_name=None):
    override_entry = self.saved_cached_entry_for_book(book_id, context)
    if override_entry is not None:
      self.debug_storage_cached_active_add_decision(
        book_id, 'using existing saved override', override_entry,
        self.entry_position_index_value(override_entry))
      if force_match_review:
        return self.choose_active_add_match(
          book_id,
          context['entries'],
          [(0, override_entry)],
          default_index,
          db,
          initial_show_all=True,
          preferred_entry=override_entry,
          automatic_entry=override_entry,
          active_list_name=active_list_name)
      return override_entry, self.entry_position_index_value(override_entry), False

    exact_candidates = self.exact_cached_entry_candidates_for_book(book_id, context)
    if len(exact_candidates) == 1:
      self.debug_storage_cached_active_add_decision(
        book_id, 'unique exact cached title/author match', exact_candidates[0][1],
        self.entry_position_index_value(exact_candidates[0][1]))
      if force_match_review:
        return self.choose_active_add_match(
          book_id,
          context['entries'],
          exact_candidates,
          default_index,
          db,
          initial_show_all=True,
          preferred_entry=exact_candidates[0][1],
          automatic_entry=exact_candidates[0][1],
          active_list_name=active_list_name)
      return exact_candidates[0][1], self.entry_position_index_value(exact_candidates[0][1]), False

    candidates = self.cached_entry_candidates_for_book(book_id, context, default_index)
    self.debug_storage_cached_active_add_candidates(book_id, candidates)
    if len(candidates) == 1:
      self.debug_storage_cached_active_add_decision(
        book_id, 'unique nonexact cached match',
        candidates[0][1],
        self.entry_position_index_value(candidates[0][1]))
      if force_match_review:
        return self.choose_active_add_match(
          book_id,
          context['entries'],
          candidates,
          default_index,
          db,
          initial_show_all=True,
          preferred_entry=candidates[0][1],
          active_list_name=active_list_name)
      return candidates[0][1], self.entry_position_index_value(candidates[0][1]), True

    self.debug_storage_cached_active_add_decision(
      book_id, 'needs chooser or manual index', index_value=default_index)
    return self.choose_active_add_match(
      book_id, context['entries'], candidates, default_index, db,
      active_list_name=active_list_name)

  def saved_cached_entry_for_book(self, book_id, context):
    return context['override_entries_by_book'].get(book_id)

  def exact_cached_entry_candidates_for_book(self, book_id, context):
    title_key = normalize_match_text(context['titles'].get(book_id, ''))
    author_key = normalize_match_text(context['authors'].get(book_id, ''))
    if not title_key or not author_key:
      return []
    candidates = [
      (0, entry)
      for entry in context['exact_entries_by_key'].get(f'{title_key}|{author_key}', [])
    ]
    candidates.sort(key=lambda item: self.cached_entry_candidate_sort_key(item))
    return candidates

  def cached_entry_candidates_for_book(self, book_id, context, default_index=None):
    title = context['titles'].get(book_id, '') or ''
    authors = context['authors'].get(book_id, []) or []
    self.debug_storage_cached_active_add_book(book_id, title, authors, default_index)
    title_key = normalize_match_text(title)
    author_key = normalize_match_text(authors)
    ranked = []
    seen = set()
    entries = []
    for key in match_keys(title):
      for entry in context['entries_by_title_key'].get(key, []):
        entry_lookup_key = entry_key(entry)
        if entry_lookup_key not in seen:
          seen.add(entry_lookup_key)
          entries.append(entry)
    for entry in context['unique_entries']:
      entry_lookup_key = entry_key(entry)
      if entry_lookup_key not in seen:
        seen.add(entry_lookup_key)
        entries.append(entry)

    ranked_seen = set()
    for entry in entries:
      key = entry_key(entry)
      if key in ranked_seen:
        continue
      ranked_seen.add(key)
      entry_title_key = normalize_match_text(entry.get('title', ''))
      entry_author_key = normalize_match_text(entry.get('author', ''))
      title_match = entry_title_matches_book(entry, title)
      author_match = self.author_matches(authors, entry.get('author', ''))
      if title_key and entry_title_key == title_key and author_match:
        score = 0 if author_key and entry_author_key == author_key else 1
      elif title_match and author_match:
        score = 1
      elif title_match:
        score = 2
      elif author_match and entry_author_key:
        score = 3
      else:
        continue
      ranked.append((score, entry))
    ranked.sort(key=self.cached_entry_candidate_sort_key)
    return ranked

  def cached_entry_candidate_sort_key(self, item):
    return (
      item[0],
      self.normalized_position_text(item[1].get('position', '')),
      normalize_match_text(item[1].get('title', '')),
      normalize_match_text(item[1].get('author', '')))

  def entry_position_index_value(self, entry):
    position = entry.get('position', '') if entry else ''
    if position in (None, ''):
      return None
    try:
      return float(position)
    except Exception:
      return None

  def choose_active_add_match(
      self, book_id, entries, candidates, default_index, db,
      initial_show_all=False, preferred_entry=None, automatic_entry=None,
      active_list_name=None):
    chooser = getattr(self, '_active_add_match_chooser', None)
    if chooser is not None:
      try:
        result = chooser(
          book_id, entries, candidates, default_index, db,
          initial_show_all=initial_show_all,
          preferred_entry=preferred_entry,
          automatic_entry=automatic_entry,
          active_list_name=active_list_name)
      except TypeError as err:
        if 'unexpected keyword' not in str(err):
          raise
        result = chooser(book_id, entries, candidates, default_index, db)
      return self.normalized_active_add_choice(result, automatic_entry)
    title = db.field_for('title', book_id, default_value='') or ''
    authors = db.field_for('authors', book_id, default_value=[]) or []
    if not isinstance(authors, (list, tuple)):
      authors = [str(authors)]
    d = ActiveAddMatchDialog(
      self.gui,
      title,
      self.display_authors(authors),
      [entry for _score, entry in candidates],
      entries,
      '' if default_index is None else f'{default_index:g}',
      initial_show_all=initial_show_all,
      preferred_entry=preferred_entry,
      active_list_name=active_list_name)
    if d.exec() != QDialog.Accepted:
      return None, None, False
    entry = d.selected_entry
    index_value = d.index_value()
    if index_value is None:
      index_value = default_index
    return self.normalized_active_add_choice((entry, index_value, entry is not None), automatic_entry)

  def normalized_active_add_choice(self, result, automatic_entry=None):
    entry, index_value, save_manual = result
    if (
        entry is not None
        and automatic_entry is not None
        and entry_key(entry) == entry_key(automatic_entry)):
      save_manual = False
    return entry, index_value, save_manual

  def added_active_index_updates(self, active, active_updates):
    index_field = self.active_series_index_field()
    if not active_updates:
      return {}
    if not index_field and not self.active_field_is_series():
      return {}
    active_key = normalize_key(active)
    update_ids = set(active_updates)
    max_index = 0
    max_in_field = 0
    found_active_index = False
    for book_id in self.all_book_ids():
      if book_id in update_ids:
        continue
      index = self.read_active_position(index_field, book_id)
      if index is not None:
        max_in_field = max(max_in_field, index)
      list_name = clean_name(self.read_field(prefs['active_list_field'], book_id))
      if normalize_key(list_name) != active_key:
        continue
      if index is None:
        continue
      found_active_index = True
      max_index = max(max_index, index)

    index_updates = {}
    next_index = next_whole_index_after(max_index if found_active_index else max_in_field)
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
    self.invalidate_cached_active_add_import_map()

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
      self.invalidate_cached_active_add_import_map()
      self.status_message(f'Created Active List "{name}".')
      return name
    except Exception as err:
      self.show_exception('Create New Active List', err)
      return None

  def _move_active_to_stored(self, active):
    active_updates, stored_updates = self.active_to_stored_updates(active)
    self.write_fields(active_updates, stored_updates)
    self.invalidate_cached_active_add_import_map()

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
      self.invalidate_cached_active_add_import_map()
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
    self.invalidate_cached_active_add_import_map()
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
