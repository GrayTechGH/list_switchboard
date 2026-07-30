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

import re
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
    clean_name, imported_author_list, imported_author_search_text, match_keys,
    normalize_key, normalize_match_text, series_match_keys, split_position_suffix,
  )
except ImportError:
  from matching import clean_name, match_keys, normalize_key, normalize_match_text, split_position_suffix
  from matching import imported_author_list, imported_author_search_text, series_match_keys

try:
  from calibre_plugins.list_switchboard.metadata import (
    format_list_entry, next_whole_index_after, parse_stored_lists,
    rebuild_stored_lists, sort_names, validate_list_name,
  )
except ImportError:
  from metadata import (
    format_list_entry, next_whole_index_after, parse_stored_lists,
    rebuild_stored_lists, sort_names, validate_list_name,
  )

try:
  from calibre_plugins.list_switchboard.storage import entry_key
except ImportError:
  from storage import entry_key


CACHED_ACTIVE_ADD_BUTTON_MATCH_EXACT = 'exact'
CACHED_ACTIVE_ADD_BUTTON_MATCH_PARTIAL = 'partial'
CACHED_ACTIVE_ADD_BUTTON_MATCH_NONE = 'none'
CACHED_ACTIVE_ADD_BUTTON_AUTHOR_SUFFIXES = frozenset([
  'jr', 'sr', 'ii', 'iii', 'iv', 'v',
])
CACHED_ACTIVE_ADD_BUTTON_TITLE_BOUNDARY_RE = re.compile(r'\s+(?:–|—)\s+|[:;]')
CACHED_ACTIVE_ADD_BUTTON_QUOTED_TITLE_RES = (
  re.compile(r'"([^"\r\n]+)"'),
  re.compile(r'“([^”\r\n]+)”'),
  re.compile(r'‘([^’\r\n]+)’'),
  re.compile(r"(?<!\w)'([^'\r\n]+)'(?!\w)"),
)
CACHED_ACTIVE_ADD_BUTTON_TRAILING_QUALIFIER_RES = (
  re.compile(r'^(.*?)\s*\([^()]+\)\s*$'),
  re.compile(r'^(.*?)\s*\[[^\[\]]+\]\s*$'),
  re.compile(r'^(.*?)\s*\{[^{}]+\}\s*$'),
)


def cached_active_add_button_title_components(value):
  """Return structural title components for the cached Active Add GUI button only.

  This boundary is intentionally separate from import matching, Find Match,
  and saved-match reconciliation. Do not merge these rules into their generic
  title helpers or reuse this function outside the button workflow.
  """
  raw = clean_name(str(value or '')).strip()
  components = []

  def append_component(component):
    key = normalize_match_text(component)
    if key and key not in components:
      components.append(key)
    without_article = re.sub(r'^(?:a|an|the)\s+', '', key).strip()
    if without_article and without_article not in components:
      components.append(without_article)

  append_component(raw)
  for component in CACHED_ACTIVE_ADD_BUTTON_TITLE_BOUNDARY_RE.split(raw):
    append_component(component)
  for quoted_re in CACHED_ACTIVE_ADD_BUTTON_QUOTED_TITLE_RES:
    for match in quoted_re.finditer(raw):
      append_component(match.group(1))
  for qualifier_re in CACHED_ACTIVE_ADD_BUTTON_TRAILING_QUALIFIER_RES:
    match = qualifier_re.match(raw)
    if match is not None:
      append_component(match.group(1))
  return tuple(components)


def cached_active_add_button_title_match_kind(book_title, imported_title):
  """Classify title evidence only for the cached Active Add GUI button."""
  book_key = normalize_match_text(book_title)
  imported_key = normalize_match_text(imported_title)
  if not book_key or not imported_key:
    return CACHED_ACTIVE_ADD_BUTTON_MATCH_NONE
  if book_key == imported_key:
    return CACHED_ACTIVE_ADD_BUTTON_MATCH_EXACT
  book_components = set(cached_active_add_button_title_components(book_title))
  imported_components = set(cached_active_add_button_title_components(imported_title))
  if book_components & imported_components:
    return CACHED_ACTIVE_ADD_BUTTON_MATCH_PARTIAL
  return CACHED_ACTIVE_ADD_BUTTON_MATCH_NONE


def cached_active_add_button_author_name_parts(value):
  """Parse one author name only for the cached Active Add GUI button."""
  raw = str(value or '').strip()
  if not raw:
    return {
      'canonical': '', 'surname': '', 'single_name': '',
      'given_full': (), 'given_initials': (),
    }
  comma_parts = [part.strip() for part in raw.split(',') if part.strip()]
  if len(comma_parts) > 1:
    surname_tokens = normalize_match_text(comma_parts[0]).split()
    given_tokens = normalize_match_text(' '.join(comma_parts[1:])).split()
    tokens = given_tokens + surname_tokens
  else:
    tokens = normalize_match_text(raw).split()
    surname_tokens = []
    given_tokens = []

  suffixes = []
  while tokens and tokens[-1] in CACHED_ACTIVE_ADD_BUTTON_AUTHOR_SUFFIXES:
    suffixes.insert(0, tokens.pop())
  if len(comma_parts) > 1:
    while given_tokens and given_tokens[-1] in CACHED_ACTIVE_ADD_BUTTON_AUTHOR_SUFFIXES:
      suffixes.insert(0, given_tokens.pop())
    surname = surname_tokens[-1] if surname_tokens else ''
    given = list(given_tokens)
  elif tokens and all(len(token) == 1 for token in tokens):
    surname = ''
    single_name = ''
    given = list(tokens)
  elif len(tokens) == 1:
    surname = ''
    single_name = tokens[0]
    given = []
  elif tokens:
    surname = tokens[-1]
    single_name = ''
    given = list(tokens[:-1])
  else:
    surname = ''
    single_name = ''
    given = []

  if len(comma_parts) > 1:
    single_name = ''

  given_full = tuple(token for token in given if len(token) > 1)
  given_initials = tuple(dict.fromkeys(token[0] for token in given if token))
  canonical_parts = (
    list(given) + ([surname or single_name] if surname or single_name else [])
    + suffixes)
  return {
    'canonical': ' '.join(canonical_parts),
    'surname': surname,
    'single_name': single_name,
    'given_full': given_full,
    'given_initials': given_initials,
  }


def cached_active_add_button_author_parts_are_partial_match(left, right):
  """Compare parsed names only for the cached Active Add GUI button."""
  left_surname = left['surname']
  right_surname = right['surname']
  if left_surname and right_surname:
    if left_surname != right_surname:
      return False
    left_initials = set(left['given_initials'])
    right_initials = set(right['given_initials'])
    if left_initials and right_initials:
      return bool(left_initials & right_initials)
    return True

  left_single = left['single_name']
  right_single = right['single_name']
  if left_single and right_surname and left_single == right_surname:
    return True
  if right_single and left_surname and right_single == left_surname:
    return True

  left_full = set(left['given_full'])
  right_full = set(right['given_full'])
  if left_single:
    left_full.add(left_single)
  if right_single:
    right_full.add(right_single)
  if left_full and right_full:
    return bool(left_full & right_full)
  left_initials = set(left['given_initials'])
  right_initials = set(right['given_initials'])
  if left_full and right_initials:
    return bool({name[0] for name in left_full} & right_initials)
  if right_full and left_initials:
    return bool({name[0] for name in right_full} & left_initials)
  return bool(left_initials and right_initials and left_initials & right_initials)


def cached_active_add_button_author_match_kind(book_authors, imported_authors):
  """Classify author evidence only for the cached Active Add GUI button."""
  if isinstance(book_authors, str):
    book_authors = [book_authors]
  if isinstance(imported_authors, str):
    imported_authors = [imported_authors]
  book_parts = [
    cached_active_add_button_author_name_parts(author)
    for author in (book_authors or [])
  ]
  imported_parts = [
    cached_active_add_button_author_name_parts(author)
    for author in (imported_authors or [])
  ]
  book_parts = [parts for parts in book_parts if parts['canonical']]
  imported_parts = [parts for parts in imported_parts if parts['canonical']]
  if not book_parts or not imported_parts:
    return CACHED_ACTIVE_ADD_BUTTON_MATCH_NONE
  if any(
      left['canonical'] == right['canonical']
      for left in book_parts for right in imported_parts):
    return CACHED_ACTIVE_ADD_BUTTON_MATCH_EXACT
  if any(
      cached_active_add_button_author_parts_are_partial_match(left, right)
      for left in book_parts for right in imported_parts):
    return CACHED_ACTIVE_ADD_BUTTON_MATCH_PARTIAL
  return CACHED_ACTIVE_ADD_BUTTON_MATCH_NONE


def cached_active_add_button_candidate_evidence(
    entry, book_title, book_authors, series_match=False):
  """Build evidence only for the cached Active Add GUI button."""
  title_kind = cached_active_add_button_title_match_kind(
    book_title, entry.get('title', ''))
  author_kind = cached_active_add_button_author_match_kind(
    book_authors, imported_author_list(entry))
  return {
    'title': title_kind,
    'author': author_kind,
    'series': bool(series_match),
    'auto_eligible': (
      title_kind != CACHED_ACTIVE_ADD_BUTTON_MATCH_NONE
      and author_kind != CACHED_ACTIVE_ADD_BUTTON_MATCH_NONE),
  }


def cached_active_add_button_candidate_sort_key(item, normalized_position):
  """Sort evidence only for the cached Active Add GUI button."""
  evidence, entry = item
  strength = {
    CACHED_ACTIVE_ADD_BUTTON_MATCH_EXACT: 0,
    CACHED_ACTIVE_ADD_BUTTON_MATCH_PARTIAL: 1,
    CACHED_ACTIVE_ADD_BUTTON_MATCH_NONE: 2,
  }
  return (
    strength[evidence['title']],
    strength[evidence['author']],
    0 if evidence['series'] else 1,
    normalized_position(entry.get('position', '')),
    normalize_match_text(entry.get('title', '')),
    normalize_match_text(imported_author_search_text(entry)),
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

      formatted = rebuild_stored_lists(cleaned_entries)
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

  def run_configured_list_action(self, title, action):
    """Run a public list action with one configuration and error boundary."""
    try:
      if not self.ensure_configured():
        return None
      return action()
    except Exception as err:
      self.show_exception(title, err)
      return None

  def add_selected_to_active(self, force_match_review=False):
    return self.run_configured_list_action(
      'Add selected books to Active List',
      lambda: self._add_selected_to_active(force_match_review=force_match_review))

  def _add_selected_to_active(self, force_match_review=False):
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
    match_series = cache.get('match_series', True)
    series = self.all_local_series_values(selected_ids) if match_series else {}
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
      len(override_entries_by_book))

    # This context is deliberately per-click so imports cannot leave stale
    # title/series or cache-entry maps behind.
    return {
      'authors': authors,
      'all_ids': all_ids,
      'cache': cache,
      'db': db,
      'entries': import_map['entries'],
      'match_series': match_series,
      'override_entries_by_book': override_entries_by_book,
      'selected_ids': selected_ids,
      'series': series,
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
        list_id, 'reused', len(cached['entries']), len(cached['unique_entries']))
      return cached

    import_map = self.build_cached_active_add_import_map(entries)
    import_map['list_id'] = list_id
    self._cached_active_add_import_map = import_map
    self.debug_storage_cached_active_add_import_map(
      list_id, 'built', len(import_map['entries']), len(import_map['unique_entries']))
    return import_map

  def build_cached_active_add_import_map(self, entries):
    unique_entries = []
    seen = set()
    entries_by_key = {}
    for entry in entries:
      key = entry_key(entry)
      if key in seen:
        continue
      seen.add(key)
      unique_entries.append(entry)
      entries_by_key[key] = entry
    return {
      'entries': entries,
      'entries_by_key': entries_by_key,
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

    candidates = self.cached_entry_candidates_for_book(book_id, context, default_index)
    self.debug_storage_cached_active_add_candidates(book_id, candidates)
    automatic_candidates = [
      (evidence, entry) for evidence, entry in candidates
      if evidence['auto_eligible']
    ]
    if len(automatic_candidates) == 1:
      automatic_entry = automatic_candidates[0][1]
      self.debug_storage_cached_active_add_decision(
        book_id, 'unique cached button title/author match', automatic_entry,
        self.entry_position_index_value(automatic_entry))
      if force_match_review:
        return self.choose_active_add_match(
          book_id,
          context['entries'],
          candidates,
          default_index,
          db,
          initial_show_all=True,
          preferred_entry=automatic_entry,
          automatic_entry=automatic_entry,
          active_list_name=active_list_name)
      return automatic_entry, self.entry_position_index_value(automatic_entry), False

    self.debug_storage_cached_active_add_decision(
      book_id, 'needs chooser or manual index', index_value=default_index)
    return self.choose_active_add_match(
      book_id, context['entries'], candidates, default_index, db,
      active_list_name=active_list_name)

  def saved_cached_entry_for_book(self, book_id, context):
    return context['override_entries_by_book'].get(book_id)

  def cached_entry_candidates_for_book(self, book_id, context, default_index=None):
    title = context['titles'].get(book_id, '') or ''
    authors = context['authors'].get(book_id, []) or []
    book_series = context.get('series', {}).get(book_id, []) if context.get('match_series') else []
    self.debug_storage_cached_active_add_book(book_id, title, authors, default_index)
    ranked = []
    for entry in context['unique_entries']:
      evidence = cached_active_add_button_candidate_evidence(
        entry,
        title,
        authors,
        series_match=self.cached_entry_title_matches_book_series(entry, book_series))
      if (
          evidence['title'] == CACHED_ACTIVE_ADD_BUTTON_MATCH_NONE
          and evidence['author'] == CACHED_ACTIVE_ADD_BUTTON_MATCH_NONE
          and not evidence['series']):
        continue
      ranked.append((evidence, entry))
    ranked.sort(key=lambda item: cached_active_add_button_candidate_sort_key(
      item, self.normalized_position_text))
    return ranked

  def cached_entry_title_matches_book_series(self, entry, book_series):
    if not book_series:
      return False
    entry_keys = set(match_keys(entry.get('title', '')))
    if not entry_keys:
      return False
    for series_value in book_series:
      if entry_keys & set(series_match_keys(series_value)):
        return True
    return False

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
    return self.run_configured_list_action(
      'Select books in Active List', self._select_active_list_books)

  def _select_active_list_books(self):
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
    return sort_names(stored)

  def managed_stored_list_rows(self):
    active = self.current_active()
    rows_by_key = OrderedDict()
    for name in self.current_stored_lists():
      rows_by_key[normalize_key(name)] = {'name': name, 'is_active': False}
    if active:
      rows_by_key[normalize_key(active)] = {'name': active, 'is_active': True}
    return sorted(rows_by_key.values(), key=lambda row: row['name'].strip().casefold())

  def books_for_active_list(self, list_name):
    if not list_name:
      return []
    db = self.db.new_api
    key = normalize_key(list_name)
    index_field = self.active_series_index_field()
    rows = []
    for book_id in self.all_book_ids():
      active = clean_name(self.read_field(prefs['active_list_field'], book_id))
      if normalize_key(active) != key:
        continue
      position, numeric_position = self.read_position_display(index_field, book_id, active)
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
    return self.run_configured_list_action(
      'Switch Active List', self._switch_active_list)

  def _switch_active_list(self):
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
    stored_updates = {}
    for book_id in self.all_book_ids():
      active = clean_name(self.read_field(prefs['active_list_field'], book_id))

      def switch_entries(entries):
        stored_by_key = OrderedDict((normalize_key(name), name) for name in entries)
        if normalize_key(active) == normalize_key(old_active):
          active_updates[book_id] = ''
          stored_by_key[normalize_key(old_active)] = self.stored_entry_for_active(
            book_id, old_active, require_position=True)
        if normalize_key(new_active) in stored_by_key:
          stored_entry = stored_by_key[normalize_key(new_active)]
          active_name, position = split_position_suffix(stored_entry)
          required_index_field = self.require_series_position_field('switch to', new_active)
          self.require_stored_series_position(new_active, book_id, position)
          active_updates[book_id] = active_name
          if required_index_field and position:
            try:
              active_index_updates[book_id] = float(position)
            except Exception:
              pass
          del stored_by_key[normalize_key(new_active)]
        if active and normalize_key(active) != normalize_key(old_active):
          active_updates[book_id] = active
        return stored_by_key.values()

      stored_updates[book_id] = rebuild_stored_lists(
        self.read_field(prefs['stored_lists_field'], book_id), switch_entries)
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
    return self.run_configured_list_action(
      'Create New Active List',
      lambda: self._create_new_active_list(selected_ids=selected_ids))

  def _create_new_active_list(self, selected_ids=None):
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
      def store_active(entries):
        stored_by_key = OrderedDict((normalize_key(name), name) for name in entries)
        if normalize_key(current) == key:
          stored_by_key[key] = self.stored_entry_for_active(
            book_id, active, require_position=True)
        return stored_by_key.values()

      if normalize_key(current) == key:
        active_updates[book_id] = ''
      formatted = rebuild_stored_lists(raw_stored, store_active)
      if formatted != (raw_stored or ''):
        stored_updates[book_id] = formatted
    return active_updates, stored_updates

  def _remove_active_from_stored(self, active):
    stored_updates = {}
    key = normalize_key(active)
    for book_id in self.all_book_ids():
      raw_stored = self.read_field(prefs['stored_lists_field'], book_id)
      formatted = rebuild_stored_lists(
        raw_stored, lambda entries: (entry for entry in entries if normalize_key(entry) != key))
      if formatted != (raw_stored or ''):
        stored_updates[book_id] = formatted
    self.write_fields(stored_updates=stored_updates)

  def rename_active_list(self):
    return self.run_configured_list_action('Rename Active List', self._rename_active_list)

  def _rename_active_list(self):
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
    return self.run_configured_list_action('Remove Active List', self._remove_active_list)

  def _remove_active_list(self):
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
      formatted = rebuild_stored_lists(
        raw_stored, lambda entries: (entry for entry in entries if normalize_key(entry) != key))
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
    return self.run_configured_list_action('Manage Stored Lists', self._manage_stored_lists)

  def _manage_stored_lists(self):
    rows = self.managed_stored_list_rows()
    if not rows:
      self.status_message('There are no Stored Lists to manage.')
      return
    d = StoredListsDialog(self.gui, self, rows)
    d.exec()

  def rename_stored_list(self, old_name):
    return self.run_configured_list_action(
      'Rename Stored List', lambda: self._rename_stored_list(old_name))

  def _rename_stored_list(self, old_name):
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
        def rename_entries(entries):
          updated = []
          for entry in entries:
            if normalize_key(entry) == normalize_key(old_name):
              _old_entry_name, position = split_position_suffix(entry)
              updated.append(format_list_entry(new_name, position))
            else:
              updated.append(entry)
          return updated

        stored_updates[book_id] = rebuild_stored_lists(
          self.read_field(prefs['stored_lists_field'], book_id), rename_entries)
      self.write_fields_with_progress(
        'Rename Stored List',
        f'Renaming Stored List to "{new_name}"...',
        stored_updates=stored_updates,
        finishing_message=f'Renamed Stored List to "{new_name}".')
      self.status_message(f'Renamed Stored List to "{new_name}".')
    except Exception as err:
      self.show_exception('Rename Stored List', err)

  def remove_stored_list(self, name=None):
    return self.run_configured_list_action(
      'Remove Stored List', lambda: self._remove_stored_list(name=name))

  def _remove_stored_list(self, name=None):
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
      raw_stored = self.read_field(prefs['stored_lists_field'], book_id)
      stored_updates[book_id] = rebuild_stored_lists(
        raw_stored, lambda entries: (entry for entry in entries if normalize_key(entry) != key))
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
      def resolve_entries(entries):
        stored_by_key = OrderedDict((normalize_key(name), name) for name in entries)
        if active and normalize_key(active) != chosen_key:
          stored_by_key[normalize_key(active)] = self.stored_entry_for_active(
            book_id, active, require_position=True)
        stored_by_key.pop(chosen_key, None)
        return stored_by_key.values()

      if active and normalize_key(active) != chosen_key:
        active_updates[book_id] = ''
      elif active:
        active_updates[book_id] = chosen
      stored_updates[book_id] = rebuild_stored_lists(
        self.read_field(prefs['stored_lists_field'], book_id), resolve_entries)
    self.write_fields(active_updates, stored_updates)
    return chosen

  def resolve_duplicate_stored_lists(self, duplicate_groups):
    if not question_dialog(self.gui, 'Duplicate Stored Lists Found',
      'The Stored Lists Field contains duplicate list names.\n\n'
      'List Switchboard can keep the first spelling found for each duplicate group and remove the others.'):
      return False
    stored_updates = {}
    for book_id in self.all_book_ids():
      stored_updates[book_id] = rebuild_stored_lists(
        self.read_field(prefs['stored_lists_field'], book_id))
    self.write_fields(stored_updates=stored_updates)
    return True
