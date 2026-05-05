#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

__license__ = 'GPL v3'
__copyright__ = '2026, List Switchboard contributors'
__docformat__ = 'restructuredtext en'

import re
import os
import traceback
import json
import time
from urllib.request import Request, urlopen
from collections import Counter, OrderedDict

try:
  from bs4 import BeautifulSoup
except Exception:
  BeautifulSoup = None

from qt.core import QApplication, QDialog, QInputDialog, QMessageBox, QProgressDialog

from calibre.ebooks.metadata import title_sort
from calibre.gui2 import error_dialog, question_dialog
from calibre_plugins.list_switchboard.config import prefs

try:
  from calibre_plugins.list_switchboard.dialogs import (
    ChoiceDialog, DebugDialog, ImportReportDialog, StoredListsDialog
  )
except ImportError:
  from dialogs import ChoiceDialog, DebugDialog, ImportReportDialog, StoredListsDialog

try:
  from calibre.utils.browser import Browser as CalibreBrowser
except Exception:
  CalibreBrowser = None


ABOUT_TEXT = '''List Switchboard

A Calibre GUI plugin for managing an active reading list and stored alternate lists using configured metadata fields.

List Switchboard only edits the configured metadata fields. It does not delete, move, convert, or modify book files.'''

GOODREADS_LOOKUP_DELAY_SECONDS = 1.5
SERIES_SUFFIX_WORDS = frozenset([
  'cycle', 'saga', 'series', 'trilogy', 'universe', 'world'
])
DEBUG_SECTIONS = (
  ('general', 'General'),
  ('metadata', 'Metadata state and cleanup'),
  ('selection', 'Book selection and series expansion'),
  ('writes', 'Metadata writes'),
  ('recipe', 'Recipe fetch and parsed output'),
  ('fallback', 'Fallback activity only'),
  ('import', 'Import matching and report'),
  ('goodreads', 'Goodreads lookups'),
  ('errors', 'Exceptions and tracebacks'),
)
IMPORT_MATCH_PROGRESS_MAX = 500
IMPORT_WRITE_PROGRESS_MAX = 1000
RELAXED_MATCH_MIN_NON_INITIAL_CHARS = 6
URL_FETCHER_PACKAGE = 'url_fetcher'


class ListSwitchboardError(Exception):
  pass


class DuplicateStoredListsError(ListSwitchboardError):

  def __init__(self, duplicate_groups):
    ListSwitchboardError.__init__(self, 'Duplicate Stored Lists found')
    self.duplicate_groups = duplicate_groups


class ImportCancelledError(ListSwitchboardError):
  pass


def normalize_key(name):
  return clean_name(name).casefold()


POSITION_SUFFIX = re.compile(r'^(.*?)\s*\[([0-9]+(?:\.[0-9]+)?)\]\s*$')


def split_position_suffix(name):
  name = (name or '').strip()
  match = POSITION_SUFFIX.match(name)
  if match is None:
    return name, None
  return match.group(1).strip(), match.group(2)


def clean_name(name):
  name, _position = split_position_suffix(name)
  return name


def parse_stored_lists(raw):
  if raw is None:
    return []
  if isinstance(raw, (list, tuple, set)):
    return [str(entry).strip() for entry in raw]
  return [entry.strip() for entry in (raw or '').split(',')]


def format_stored_lists(names):
  return ', '.join(sort_names(names))


def sort_names(names):
  return sorted(names, key=lambda item: item.strip().casefold())


def validate_list_name(name):
  name = clean_name(name)
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


def normalize_match_text(value):
  if value is None:
    value = ''
  elif isinstance(value, (list, tuple, set)):
    value = ' '.join(str(item) for item in value)
  else:
    value = str(value)
  value = clean_name(value).casefold()
  return re.sub(r'[^a-z0-9]+', ' ', value).strip()


def title_sort_without_article(value):
  value = clean_name(value)
  if not value:
    return ''
  try:
    sorted_value = title_sort(value)
  except Exception:
    return ''
  if ',' in sorted_value:
    sorted_value = sorted_value.rsplit(',', 1)[0]
  return sorted_value.strip()


def remove_single_letter_tokens(key):
  return ' '.join(token for token in key.split() if len(token) > 1)


def enough_non_initial_characters(key):
  return sum(len(token) for token in key.split() if len(token) > 1) >= RELAXED_MATCH_MIN_NON_INITIAL_CHARS


def match_keys(value):
  keys = []
  for candidate in (value, title_sort_without_article(value)):
    key = normalize_match_text(candidate)
    if key and key not in keys:
      keys.append(key)
    relaxed_key = remove_single_letter_tokens(key)
    if relaxed_key and relaxed_key not in keys and enough_non_initial_characters(key):
      keys.append(relaxed_key)
  return keys


def relaxed_series_key(value):
  parts = normalize_match_text(value).split()
  while parts and parts[-1] in SERIES_SUFFIX_WORDS:
    parts.pop()
  return ' '.join(parts)


def series_match_keys(value):
  keys = []
  for key in match_keys(value):
    if key and key not in keys:
      keys.append(key)
    relaxed_key = relaxed_series_key(key)
    if relaxed_key and relaxed_key not in keys:
      keys.append(relaxed_key)
    for article_key in match_keys(relaxed_key):
      if article_key and article_key not in keys:
        keys.append(article_key)
  return keys


def unique_case_insensitive(names):
  seen = OrderedDict()
  for name in names:
    key = normalize_key(name)
    if key and key not in seen:
      seen[key] = name.strip()
  return list(seen.values())


class ListSwitchboardCore:

  def __init__(self, gui, do_user_config, plugin_base=None):
    self.gui = gui
    self.do_user_config = do_user_config
    self.plugin_base = plugin_base
    self.db = getattr(gui, 'current_db', None)
    self.goodreads_series_cache = {}
    self.last_goodreads_lookup_time = 0
    self.import_progress = None
    self.browser = None

  def debug_enabled(self, section='general'):
    if prefs.get('debug_logging', False):
      return True
    sections = prefs.get('debug_sections', {}) or {}
    return bool(sections.get(section, False))

  def debug_log(self, message, section='general'):
    if not self.debug_enabled(section):
      return
    print(f'List Switchboard [{section}]: {message}', flush=True)

  def debug_log_preview(self, label, text, limit=3000, section='general'):
    if not self.debug_enabled(section):
      return
    text = (text or '').replace('\r', '\\r').replace('\n', '\\n')
    if len(text) > limit:
      text = f'{text[:limit]}... <truncated {len(text) - limit} chars>'
    self.debug_log(f'{label}: {text}', section=section)

  def debug_metadata_helper_failed(self, field, err):
    self.debug_log(
      f'could not resolve series index field via Calibre helper for {field}: {err}',
      section='metadata')

  def debug_metadata_no_series_index_field(self, field):
    self.debug_log(f'no readable series index field found for {field}', section='metadata')

  def debug_metadata_formatted_read_failed(self, field, book_id, err):
    self.debug_log(
      f'formatted field read failed field={field} book_id={book_id}: {err}',
      section='metadata')

  def debug_metadata_preflight_store(self, book_id, raw_active, formatted_active, index_field, position):
    self.debug_log(
      f'preflight store book_id={book_id} raw_active={raw_active} '
      f'formatted_active={formatted_active} index_field={index_field} position={position}',
      section='metadata')

  def debug_metadata_library_state(self, active_field, stored_field):
    self.debug_log(
      f'configured fields active={active_field} stored={stored_field}',
      section='metadata')

  def debug_metadata_counts(self, active_counts, stored_names):
    self.debug_log(
      f'active counts={dict(active_counts)} stored={list(stored_names.values())}',
      section='metadata')

  def debug_metadata_repair_skipped(self):
    self.debug_log(
      'missing stored position repair skipped; no series index field',
      section='metadata')

  def debug_metadata_repaired_position(self, book_id, name, position):
    self.debug_log(
      f'repaired stored list position book_id={book_id} list={name} position={position}',
      section='metadata')

  def debug_selection_ids(self, ids):
    self.debug_log(f'selected book ids={ids}', section='selection')

  def debug_selection_expanded_series(self, ids, expanded):
    self.debug_log(f'expanded ids {ids} to series ids {sorted(expanded)}', section='selection')

  def debug_writes_store_active(self, book_id, active, raw_active, formatted_active, position):
    self.debug_log(
      f'storing active list book_id={book_id} active={active} raw_active={raw_active} '
      f'formatted_active={formatted_active} position={position}', section='writes')

  def debug_writes_active_field(self, count):
    self.debug_log(
      f'writing active field={prefs["active_list_field"]} count={count}',
      section='writes')

  def debug_writes_stored_field(self, count):
    self.debug_log(
      f'writing stored field={prefs["stored_lists_field"]} count={count}',
      section='writes')

  def debug_writes_finished(self, active_updates, stored_updates, changed):
    self.debug_log(
      f'wrote active_count={len(active_updates or {})} stored_count={len(stored_updates or {})} '
      f'changed_count={len(changed)}', section='writes')

  def debug_writes_active_series_field(self, field, label, active_updates, index_updates):
    self.debug_log(
      f'writing active series field={field} label={label} count={len(active_updates)} '
      f'index_count={len(index_updates or {})}', section='writes')

  def debug_recipe_start(self, recipe):
    self.debug_log(f'import recipe={recipe.NAME} url={recipe.URL}', section='recipe')

  def debug_recipe_fetch_url(self, url):
    self.debug_log(f'import fetch url={url}', section='recipe')

  def debug_recipe_fetched(self, url, html):
    self.debug_log(f'import fetched bytes={len(html)} from {url}', section='recipe')
    self.debug_log_preview('import fetched preview', html, section='recipe')

  def debug_recipe_failed(self, url, err):
    self.debug_log(f'recipe fetch/parse failed for {url}: {err}', section='recipe')

  def debug_fallback_urls(self, url, urls):
    self.debug_log(f'fallback fetch urls for {url}: {urls}', section='fallback')

  def debug_fallback_urllib_fetch(self, url):
    self.debug_log(f'fallback urllib fetch url={url}', section='fallback')

  def debug_recipe_linked_page_failed(self, url, err, entry):
    title = entry.get('title', '') if entry else ''
    self.debug_log(
      f'recipe linked page failed title={title} url={url}: {err}',
      section='recipe')

  def debug_parser_message(self, message):
    self.debug_log(message, section='recipe')

  def debug_recipe_output(self, parsed):
    entries = parsed.get('entries') or []
    self.debug_log(
      f'recipe output name={parsed.get("name", "")} url={parsed.get("url", "")} entries={len(entries)}',
      section='recipe')
    for index, entry in enumerate(entries[:25], start=1):
      self.debug_log(f'recipe entry {index}: {entry}', section='recipe')
    if len(entries) > 25:
      self.debug_log(
        f'recipe entry log truncated; {len(entries) - 25} additional entries',
        section='recipe')

  def debug_import_target(self, list_name, active):
    self.debug_log(f'import target list={list_name} current active={active}', section='import')

  def debug_import_summary(self, matched, missing_entries, entries):
    self.debug_log(
      f'import matched books={len(matched)} missing entries={len(missing_entries)} '
      f'of entries={len(entries)}', section='import')

  def debug_import_missing_entries(self, missing_entries):
    for index, entry in enumerate(missing_entries[:50], start=1):
      self.debug_log(f'import missing entry {index}: {entry}', section='import')
    if len(missing_entries) > 50:
      self.debug_log(
        f'import missing entry log truncated; {len(missing_entries) - 50} additional entries',
        section='import')

  def debug_import_empty_entry(self, entry):
    self.debug_log(f'import skipped empty title entry={entry}', section='import')

  def debug_import_match_entry(self, entry, candidates):
    self.debug_log(
      f'import match entry position={entry.get("position", "")} title={entry.get("title", "")} '
      f'aliases={entry.get("aliases", [])} author={entry.get("author", "")} candidates={candidates}',
      section='import')

  def debug_import_matched_book(self, label, book_id, entry, titles, series):
    self.debug_log(
      f'import {label} book_id={book_id} position={entry.get("position", "")} '
      f'title={titles.get(book_id, "")} series={series.get(book_id, "")}',
      section='import')

  def debug_import_goodreads_candidates(self, entry, candidates):
    self.debug_log(
      f'import Goodreads recovery entry={entry.get("title", "")} candidates={candidates}',
      section='import')

  def debug_import_goodreads_source_candidates(self, entry, data, candidates):
    self.debug_log(
      f'import Goodreads source recovery entry={entry.get("title", "")} '
      f'series={data.get("series_names", [])} books={len(data.get("books", []))} '
      f'candidates={candidates}', section='import')

  def debug_goodreads_throttled(self, delay, source=False):
    name = 'source lookup' if source else 'lookup'
    self.debug_log(f'Goodreads {name} throttled for {delay:.2f}s', section='goodreads')

  def debug_goodreads_lookup_url(self, url, source=False):
    name = 'source lookup' if source else 'lookup'
    self.debug_log(f'Goodreads {name} url={url}', section='goodreads')

  def debug_goodreads_lookup_failed(self, identifier, err, source=False):
    if source:
      self.debug_log(f'Goodreads source lookup failed url={identifier}: {err}', section='goodreads')
    else:
      self.debug_log(f'Goodreads lookup failed id={identifier}: {err}', section='goodreads')

  def debug_goodreads_lookup_result(self, goodreads_id, series_names):
    self.debug_log(f'Goodreads lookup id={goodreads_id} series={series_names}', section='goodreads')

  def debug_goodreads_source_result(self, data):
    self.debug_log(
      f'Goodreads source lookup series={data.get("series_names", [])} '
      f'books={len(data.get("books", []))}', section='goodreads')

  def debug_goodreads_json_failed(self, err):
    self.debug_log(f'Goodreads JSON parse failed: {err}', section='goodreads')

  def debug_exception(self):
    if not self.debug_enabled('errors'):
      return
    self.debug_log('exception', section='errors')
    for line in traceback.format_exc().rstrip().splitlines():
      self.debug_log(line, section='errors')

  def debug_general_status_message(self, message):
    self.debug_log(message, section='general')

  def configured(self):
    if not (prefs['active_list_field'] and prefs['stored_lists_field']
        and prefs['active_list_field'] != prefs['stored_lists_field']):
      return False
    try:
      return self.active_field_is_series() and self.supported_stored_field()
    except Exception:
      return False

  def ensure_configured(self):
    if self.configured():
      return True
    self.do_user_config(parent=self.gui)
    return self.configured()

  def selected_book_ids(self):
    rows = self.gui.library_view.selectionModel().selectedRows()
    return list(map(self.gui.library_view.model().id, rows or []))

  def current_book_id(self):
    index = self.gui.library_view.currentIndex()
    if not index.isValid():
      return None
    try:
      return self.gui.library_view.model().id(index)
    except Exception:
      return None

  def all_book_ids(self):
    return list(self.db.new_api.all_book_ids())

  def select_book_ids(self, ids, message):
    ids = sorted(set(ids))
    if not ids:
      self.status_message(message)
      return
    keep_current = self.current_book_id() in ids
    self.gui.library_view.select_rows(
      ids,
      using_ids=True,
      change_current=not keep_current,
      scroll=not keep_current)
    self.status_message(message)

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

  def display_authors(self, authors):
    if authors is None:
      return ''
    if isinstance(authors, (list, tuple)):
      return ', '.join(str(author) for author in authors)
    return str(authors)

  def author_matches(self, book_authors, imported_author):
    imported = normalize_match_text(imported_author)
    if not imported:
      return True
    book_text = normalize_match_text(book_authors)
    if not book_text:
      return True
    imported_parts = {part for part in imported.split() if len(part) > 1}
    book_parts = {part for part in book_text.split() if len(part) > 1}
    return bool(imported_parts & book_parts)

  def identifiers_for_book(self, book_id):
    try:
      identifiers = self.db.new_api.field_for('identifiers', book_id, default_value={}) or {}
      return identifiers if isinstance(identifiers, dict) else {}
    except Exception:
      return {}

  def goodreads_id_for_book(self, book_id):
    identifiers = self.identifiers_for_book(book_id)
    for key in ('goodreads', 'gr'):
      value = identifiers.get(key)
      if value:
        return str(value).strip()
    return ''

  def fetch_goodreads_series_names(self, goodreads_id):
    if not goodreads_id:
      return []
    if goodreads_id in self.goodreads_series_cache:
      return self.goodreads_series_cache[goodreads_id]

    elapsed = time.time() - self.last_goodreads_lookup_time
    if elapsed < GOODREADS_LOOKUP_DELAY_SECONDS:
      delay = GOODREADS_LOOKUP_DELAY_SECONDS - elapsed
      self.debug_goodreads_throttled(delay)
      self.sleep_with_events(delay, f'Waiting before Goodreads lookup for book {goodreads_id}...')

    url = f'https://www.goodreads.com/book/show/{goodreads_id}'
    self.update_import_progress(message=f'Looking up Goodreads book {goodreads_id}...')
    self.debug_goodreads_lookup_url(url)
    self.last_goodreads_lookup_time = time.time()
    try:
      html = self.fetch_url(url)
      series_names = self.extract_goodreads_series_names(html)
    except Exception as err:
      self.debug_goodreads_lookup_failed(goodreads_id, err)
      series_names = []
    self.goodreads_series_cache[goodreads_id] = series_names
    self.debug_goodreads_lookup_result(goodreads_id, series_names)
    return series_names

  def fetch_goodreads_source_data(self, url):
    if not url or 'goodreads.com/' not in url:
      return {'series_names': [], 'books': []}
    cache_key = f'source:{url}'
    if cache_key in self.goodreads_series_cache:
      return self.goodreads_series_cache[cache_key]

    elapsed = time.time() - self.last_goodreads_lookup_time
    if elapsed < GOODREADS_LOOKUP_DELAY_SECONDS:
      delay = GOODREADS_LOOKUP_DELAY_SECONDS - elapsed
      self.debug_goodreads_throttled(delay, source=True)
      self.sleep_with_events(delay, 'Waiting before Goodreads source lookup...')

    self.debug_goodreads_lookup_url(url, source=True)
    self.update_import_progress(message='Looking up Goodreads source page...')
    self.last_goodreads_lookup_time = time.time()
    try:
      html = self.fetch_url(url)
      data = self.extract_goodreads_source_data(html)
    except Exception as err:
      self.debug_goodreads_lookup_failed(url, err, source=True)
      data = {'series_names': [], 'books': []}
    self.goodreads_series_cache[cache_key] = data
    self.debug_goodreads_source_result(data)
    return data

  def extract_goodreads_source_data(self, html):
    if BeautifulSoup is None:
      return {'series_names': [], 'books': []}
    soup = BeautifulSoup(html or '', 'html.parser')
    series_names = []
    heading = soup.find('h1')
    if heading is not None:
      series_names.append(heading.get_text(' ', strip=True))

    books = []
    seen_titles = set()
    for link in soup.find_all('a', href=True):
      href = link.get('href') or ''
      title = link.get_text(' ', strip=True)
      if not title or '/book/show/' not in href:
        continue
      title_key = normalize_match_text(title)
      if not title_key or title_key in seen_titles:
        continue
      seen_titles.add(title_key)
      container = link.find_parent(['div', 'li', 'tr'])
      author = ''
      if container is not None:
        author_link = container.find('a', href=lambda value: value and '/author/show/' in value)
        if author_link is not None:
          author = author_link.get_text(' ', strip=True)
      books.append({'title': title, 'author': author})
    return {'series_names': unique_case_insensitive(series_names), 'books': books}

  def extract_goodreads_series_names(self, html):
    if BeautifulSoup is None:
      return []
    soup = BeautifulSoup(html or '', 'html.parser')
    script_node = soup.find('script', attrs={'id': '__NEXT_DATA__'})
    if script_node is None:
      return []
    raw_payload = script_node.string or script_node.get_text() or ''
    try:
      payload = json.loads(raw_payload)
    except Exception as err:
      self.debug_goodreads_json_failed(err)
      return []
    values = []
    self.collect_goodreads_series_values(payload, values)
    return unique_case_insensitive(values)

  def collect_goodreads_series_values(self, node, values):
    if isinstance(node, list):
      for item in node:
        self.collect_goodreads_series_values(item, values)
      return
    if not isinstance(node, dict):
      return

    typename = str(node.get('__typename') or '').casefold()
    if 'series' in typename:
      for key in ('title', 'name', 'seriesTitle'):
        value = node.get(key)
        if value:
          values.append(str(value))
    for key in ('series', 'bookSeries', 'primarySeries'):
      value = node.get(key)
      if isinstance(value, str):
        values.append(value)
      elif isinstance(value, (dict, list)):
        self.collect_goodreads_series_values(value, values)

    for child in node.values():
      if isinstance(child, (dict, list)):
        self.collect_goodreads_series_values(child, values)

  def fetch_url(self, url):
    headers = {
      'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
      ),
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      'Accept-Language': 'en-US,en;q=0.9',
      'Connection': 'close',
    }
    if CalibreBrowser is not None:
      browser = self.calibre_browser(headers)
      response = browser.open(url, timeout=30)
      charset = response.headers.get_content_charset() or 'utf-8'
      return response.read().decode(charset, 'replace')
    self.debug_fallback_urllib_fetch(url)
    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:
      charset = response.headers.get_content_charset() or 'utf-8'
      return response.read().decode(charset, 'replace')

  def calibre_browser(self, headers):
    if self.browser is None:
      self.browser = CalibreBrowser()
      try:
        self.browser.set_handle_robots(False)
      except Exception:
        pass
    self.browser.addheaders = list(headers.items())
    return self.browser

  def fallback_fetch_urls(self, url):
    for fetcher in self.available_import_recipes():
      urls = fetcher.fallback_urls(url) if hasattr(fetcher, 'fallback_urls') else ()
      if urls:
        self.debug_fallback_urls(url, urls)
        return urls
    return ()

  def load_default_recipe(self):
    recipes = self.available_import_recipes()
    if not recipes:
      raise ListSwitchboardError('No import recipes were found.')
    return recipes[0]

  def available_import_recipes(self):
    try:
      fetchers = self.builtin_url_fetchers()
    except Exception as err:
      self.debug_log(f'could not load URL fetchers: {err}', section='recipe')
      return ()
    return tuple(sorted(fetchers, key=lambda fetcher: (fetcher.order, fetcher.NAME.casefold())))

  def builtin_url_fetchers(self):
    try:
      from calibre_plugins.list_switchboard.url_fetcher import available_url_fetchers
    except ImportError:
      from url_fetcher import available_url_fetchers
    return available_url_fetchers()

  def recipe_discovery_summary(self):
    return f'Could not load built-in URL fetchers from {URL_FETCHER_PACKAGE}.'

  def import_default_recipe(self):
    self.import_recipe(self.load_default_recipe())

  def import_recipe_by_name(self, recipe_name):
    for recipe in self.available_import_recipes():
      if recipe.NAME == recipe_name:
        self.import_recipe(recipe)
        return
    error_dialog(self.gui, 'Import List', f'Could not find import recipe "{recipe_name}".', show=True)

  def import_recipe(self, recipe):
    if not self.ensure_configured():
      return
    progress = None
    try:
      self.debug_recipe_start(recipe)
      progress = self.create_import_progress(recipe.NAME)
      self.import_progress = progress
      self.update_import_progress(0, f'Fetching "{recipe.NAME}"...')
      parsed = self.fetch_and_parse_recipe(recipe)
      self.show_import_progress_start(parsed)
      self.log_recipe_output(parsed)
      self.import_recipe_result(parsed)
    except ImportCancelledError as err:
      self.status_message(str(err))
    except Exception as err:
      self.show_exception('Import List', err)
    finally:
      self.import_progress = None
      if progress is not None:
        progress.close()

  def create_import_progress(self, list_name):
    progress = QProgressDialog('Preparing import...', 'Cancel', 0, IMPORT_WRITE_PROGRESS_MAX, self.gui)
    progress.setWindowTitle(f'Import List: {list_name}')
    progress.setMinimumDuration(0)
    progress.setAutoClose(False)
    progress.setAutoReset(False)
    progress.setValue(0)
    QApplication.processEvents()
    return progress

  def show_import_progress_start(self, parsed):
    entries = parsed.get('entries') or []
    self.update_import_progress(
      0,
      f'Matching 0 of {len(entries)} recipe entries...')
    try:
      QApplication.processEvents()
    except Exception:
      pass

  def create_operation_progress(self, title, message):
    progress = QProgressDialog(message, '', 0, IMPORT_WRITE_PROGRESS_MAX, self.gui)
    progress.setWindowTitle(title)
    progress.setMinimumDuration(0)
    progress.setAutoClose(False)
    progress.setAutoReset(False)
    progress.setValue(0)
    progress.setCancelButton(None)
    QApplication.processEvents()
    return progress

  def update_import_progress(self, value=None, message=None):
    progress = self.import_progress
    if progress is None:
      QApplication.processEvents()
      return
    if message is not None:
      progress.setLabelText(message)
    if value is not None:
      progress.setValue(value)
    QApplication.processEvents()
    if progress.wasCanceled():
      raise ImportCancelledError('Import cancelled. No Active List metadata was changed.')

  def close_import_progress(self):
    progress = self.import_progress
    self.import_progress = None
    if progress is not None:
      progress.close()
    try:
      QApplication.processEvents()
    except Exception:
      pass

  def update_import_match_progress(self, done, total, message):
    total = max(total, 1)
    value = int(round((float(done) / total) * IMPORT_MATCH_PROGRESS_MAX))
    self.update_import_progress(value, message)

  def update_import_match_step_progress(self, entry_index, total, fraction, message):
    total = max(total, 1)
    fraction = min(max(float(fraction), 0.0), 1.0)
    done = (entry_index - 1) + fraction
    value = int(round((done / total) * IMPORT_MATCH_PROGRESS_MAX))
    self.update_import_progress(value, message)

  def update_import_write_progress(self, done, total, message):
    total = max(total, 1)
    span = IMPORT_WRITE_PROGRESS_MAX - IMPORT_MATCH_PROGRESS_MAX
    value = IMPORT_MATCH_PROGRESS_MAX + int(round((float(done) / total) * span))
    self.update_import_progress(value, message)

  def update_import_fetch_progress(self, done, total, message):
    total = max(total, 1)
    value = int(round((float(done) / total) * IMPORT_MATCH_PROGRESS_MAX))
    self.update_import_progress(value, message)

  def update_operation_write_progress(self, done, total, message):
    total = max(total, 1)
    value = int(round((float(done) / total) * IMPORT_WRITE_PROGRESS_MAX))
    self.update_import_progress(value, message)

  def write_fields_with_progress(
      self, title, initial_message, active_updates=None, stored_updates=None,
      assign_series_indexes=False, active_index_updates=None, finishing_message=None):
    progress = self.create_operation_progress(title, initial_message)
    self.import_progress = progress
    total_write_units = len(active_updates or {}) + len(stored_updates or {})
    written_units = [0]

    def operation_write_progress(count, message):
      written_units[0] += count
      self.update_operation_write_progress(written_units[0], total_write_units, message)

    try:
      self.write_fields(
        active_updates=active_updates,
        stored_updates=stored_updates,
        assign_series_indexes=assign_series_indexes,
        active_index_updates=active_index_updates,
        progress_callback=operation_write_progress)
      self.update_import_progress(
        IMPORT_WRITE_PROGRESS_MAX,
        finishing_message or 'Finished metadata updates.')
    finally:
      self.close_import_progress()

  def sleep_with_events(self, seconds, message):
    end_time = time.time() + max(0, seconds)
    while time.time() < end_time:
      self.update_import_progress(message=message)
      time.sleep(min(0.1, max(0, end_time - time.time())))

  def fetch_and_parse_recipe(self, recipe):
    try:
      return recipe.fetch_and_parse(
        self.fetch_url,
        sleep=lambda seconds, message: self.sleep_with_events(seconds, message),
        fetch_error=lambda url, err, entry: self.debug_recipe_linked_page_failed(url, err, entry),
        log=lambda message: self.debug_parser_message(message),
        progress=lambda done, total, message: self.update_import_fetch_progress(done, total, message),
        before_fetch=lambda url: (
          self.debug_recipe_fetch_url(url),
          self.update_import_progress(message=f'Fetching "{recipe.NAME}"...')),
        after_fetch=lambda url, html: self.debug_recipe_fetched(url, html),
        before_parse=lambda _url: self.update_import_progress(message=f'Parsing "{recipe.NAME}"...'))
    except Exception as err:
      raise ListSwitchboardError(str(err))

  def log_recipe_output(self, parsed):
    self.debug_recipe_output(parsed)

  def import_recipe_result(self, parsed):
    list_name = validate_list_name(parsed['name'])
    entries = parsed.get('entries') or []
    if not entries:
      raise ListSwitchboardError('The imported list did not contain any entries.')

    active = self.current_active()
    self.debug_import_target(list_name, active)
    self.update_import_match_progress(0, len(entries), f'Matching 0 of {len(entries)} recipe entries...')
    match_series = parsed.get('match_series', True)
    try:
      matched, missing_entries = self.match_imported_entries(entries, match_series=match_series)
    except TypeError as err:
      if 'match_series' not in str(err):
        raise
      matched, missing_entries = self.match_imported_entries(entries)
    self.debug_import_summary(matched, missing_entries, entries)
    if not matched:
      raise ListSwitchboardError('No books in this library matched the imported list.')

    if self.import_progress is not None:
      self.import_progress.setCancelButton(None)
    active_updates = {}
    stored_updates = {}
    index_updates = {}
    if active and normalize_key(active) != normalize_key(list_name):
      self.update_import_progress(message=f'Storing previous Active List "{active}"...')
      active_updates, stored_updates = self.active_to_stored_updates(active)

    self.update_import_progress(IMPORT_MATCH_PROGRESS_MAX, f'Writing "{list_name}" to matched books...')
    for book_id, position in matched.items():
      if self.active_list_value_matches(book_id, list_name, position):
        continue
      active_updates[book_id] = list_name
      try:
        index_updates[book_id] = float(position)
      except Exception:
        pass
    total_write_units = len(active_updates) + len(stored_updates)
    written_units = [0]

    def import_write_progress(count, message):
      written_units[0] += count
      self.update_import_write_progress(written_units[0], total_write_units, message)

    self.write_fields(
      active_updates=active_updates,
      stored_updates=stored_updates,
      assign_series_indexes=True,
      active_index_updates=index_updates,
      progress_callback=import_write_progress)
    self.update_import_progress(IMPORT_WRITE_PROGRESS_MAX, 'Preparing import report...')
    self.status_message(
      f'Imported "{list_name}" as Active List. Placed {len(matched)} books; '
      f'{len(missing_entries)} missing.')
    self.show_import_report(
      list_name, len(matched), len(entries), missing_entries,
      matched_book_ids=set(matched), notes=parsed.get('notes'),
      match_series=match_series)

  def show_import_report(
      self, list_name, matched_count, entries_count, missing_entries,
      allow_deep_recovery=True, matched_book_ids=None, notes=None,
      match_series=True):
    self.debug_import_missing_entries(missing_entries)
    d = ImportReportDialog(
      self.gui, list_name, matched_count, entries_count, missing_entries,
      allow_deep_recovery=allow_deep_recovery, notes=notes)
    if d.exec() == QDialog.Accepted and d.deep_recovery_requested:
      self.close_import_progress()
      self.run_deep_recovery(
        list_name, matched_count, entries_count, missing_entries,
        excluded_book_ids=matched_book_ids,
        match_series=match_series)

  def run_deep_recovery(
      self, list_name, matched_count, entries_count, missing_entries,
      excluded_book_ids=None, match_series=True):
    if not missing_entries:
      return
    excluded_book_ids = set(excluded_book_ids or [])
    progress = QProgressDialog(
      'Preparing deep recovery...', 'Cancel', 0, IMPORT_WRITE_PROGRESS_MAX, self.gui)
    progress.setWindowTitle('Deep Recovery')
    progress.setMinimumDuration(0)
    progress.setAutoClose(False)
    progress.setAutoReset(False)
    progress.setValue(0)
    self.import_progress = progress
    QApplication.processEvents()
    try:
      matched, still_missing = self.match_deep_recovery_entries(
        missing_entries, excluded_book_ids=excluded_book_ids,
        match_series=match_series)
      if matched:
        progress.setCancelButton(None)
        index_updates = {}
        for book_id, position in matched.items():
          try:
            index_updates[book_id] = float(position)
          except Exception:
            pass
        written = [0]

        def write_progress(count, message):
          written[0] += count
          self.update_import_write_progress(written[0], len(matched), message)

        self.write_fields(
          active_updates={
            book_id: list_name for book_id, position in matched.items()
            if not self.active_list_value_matches(book_id, list_name, position)
          },
          assign_series_indexes=True,
          active_index_updates=index_updates,
          progress_callback=write_progress)
      self.update_import_progress(IMPORT_WRITE_PROGRESS_MAX, 'Preparing deep recovery report...')
      total_matched = matched_count + len(matched)
      self.status_message(
        f'Deep Recovery placed {len(matched)} more books in "{list_name}". '
        f'{len(still_missing)} missing.')
      self.close_import_progress()
      self.show_import_report(
        list_name, total_matched, entries_count, still_missing,
        allow_deep_recovery=False,
        matched_book_ids=excluded_book_ids | set(matched),
        match_series=match_series)
    except ImportCancelledError as err:
      self.status_message(str(err))
    except Exception as err:
      self.show_exception('Deep Recovery', err)
    finally:
      self.import_progress = None
      progress.close()

  def match_imported_entries(self, entries, match_series=True):
    db = self.db.new_api
    ids = self.all_book_ids()
    titles = db.all_field_for('title', ids, default_value='')
    series = self.all_local_series_values(ids)
    authors = db.all_field_for('authors', ids, default_value='')

    by_title = {}
    by_series = {}
    for book_id in ids:
      for title_key in match_keys(titles.get(book_id, '')):
        by_title.setdefault(title_key, []).append(book_id)
      for series_value in series.get(book_id, []):
        for series_key in series_match_keys(series_value):
          by_series.setdefault(series_key, []).append(book_id)

    matched = OrderedDict()
    missing_entries = []
    total_entries = len(entries)
    for entry_index, entry in enumerate(entries, start=1):
      self.update_import_match_progress(
        entry_index - 1,
        total_entries,
        f'Matching {entry_index} of {total_entries}: {entry.get("title", "")}')
      entry_keys = self.import_entry_keys(entry)
      if not entry_keys:
        self.debug_import_empty_entry(entry)
        missing_entries.append(entry)
        self.update_import_match_progress(
          entry_index,
          total_entries,
          f'Matched {entry_index} of {total_entries} recipe entries...')
        continue
      title_candidates = []
      series_candidates = []
      for entry_key in entry_keys:
        title_candidates.extend(by_title.get(entry_key, []))
        series_candidates.extend(by_series.get(entry_key, []))
      candidates = title_candidates + (series_candidates if match_series else [])
      candidates = list(OrderedDict((book_id, None) for book_id in candidates).keys())
      self.debug_import_match_entry(entry, candidates)
      entry_matched = False
      if match_series:
        series_candidates = list(OrderedDict(
          (book_id, None) for book_id in series_candidates).keys())
        for book_id in series_candidates:
          if book_id in matched:
            continue
          if self.author_matches(authors.get(book_id, ''), entry.get('author', '')):
            matched[book_id] = entry.get('position', '')
            entry_matched = True
            self.debug_import_matched_book('matched', book_id, entry, titles, series)
      if not entry_matched:
        title_candidates = list(OrderedDict(
          (book_id, None) for book_id in title_candidates).keys())
        for book_id in title_candidates:
          if book_id in matched:
            continue
          if self.author_matches(authors.get(book_id, ''), entry.get('author', '')):
            matched[book_id] = entry.get('position', '')
            entry_matched = True
            self.debug_import_matched_book('matched', book_id, entry, titles, series)
            break
      if not entry_matched:
        self.update_import_match_step_progress(
          entry_index,
          total_entries,
          0.35,
          f'Checking Goodreads for {entry_index} of {total_entries}: {entry.get("title", "")}')
        progress = lambda fraction, message: self.update_import_match_step_progress(
          entry_index, total_entries, fraction, message)
        goodreads_candidates = self.goodreads_source_recovery_candidates_for_match(
          entry, titles, series, authors, by_title, by_series,
          match_series=match_series)
        progress(0.6, f'Checked Goodreads source for: {entry.get("title", "")}')
        self.debug_import_goodreads_candidates(entry, goodreads_candidates)
        for book_id in goodreads_candidates:
          if book_id in matched:
            continue
          matched[book_id] = entry.get('position', '')
          entry_matched = True
          self.debug_import_matched_book('Goodreads matched', book_id, entry, titles, series)
      if not entry_matched:
        missing_entries.append(entry)
      self.update_import_match_progress(
        entry_index,
        total_entries,
        f'Matched {entry_index} of {total_entries} recipe entries...')
    return matched, missing_entries

  def match_deep_recovery_entries(self, entries, excluded_book_ids=None, match_series=True):
    excluded_book_ids = set(excluded_book_ids or [])
    db = self.db.new_api
    ids = self.all_book_ids()
    titles = db.all_field_for('title', ids, default_value='')
    series = self.all_local_series_values(ids)
    authors = db.all_field_for('authors', ids, default_value='')

    by_title = {}
    by_series = {}
    for book_id in ids:
      for title_key in match_keys(titles.get(book_id, '')):
        by_title.setdefault(title_key, []).append(book_id)
      for series_value in series.get(book_id, []):
        for series_key in series_match_keys(series_value):
          by_series.setdefault(series_key, []).append(book_id)

    matched = OrderedDict()
    missing_entries = []
    total_entries = len(entries)
    for entry_index, entry in enumerate(entries, start=1):
      self.update_import_match_step_progress(
        entry_index,
        total_entries,
        0.2,
        f'Deep Recovery {entry_index} of {total_entries}: {entry.get("title", "")}')
      progress = lambda fraction, message: self.update_import_match_step_progress(
        entry_index, total_entries, fraction, message)
      candidates = self.goodreads_recovery_candidates(
        entry, ids, titles, series, authors, by_title, by_series, progress,
        excluded_book_ids=excluded_book_ids,
        match_series=match_series)
      self.debug_import_goodreads_candidates(entry, candidates)
      entry_matched = False
      for book_id in candidates:
        if book_id in matched or book_id in excluded_book_ids:
          continue
        matched[book_id] = entry.get('position', '')
        entry_matched = True
        self.debug_import_matched_book('Deep Recovery matched', book_id, entry, titles, series)
      if not entry_matched:
        missing_entries.append(entry)
      self.update_import_match_progress(
        entry_index,
        total_entries,
        f'Deep Recovery checked {entry_index} of {total_entries} recipe entries...')
    return matched, missing_entries

  def goodreads_recovery_candidates(
      self, entry, ids, titles, series, authors, by_title, by_series, progress=None,
      excluded_book_ids=None, match_series=True):
    excluded_book_ids = set(excluded_book_ids or [])
    source_candidates = self.goodreads_source_recovery_candidates_for_match(
      entry, titles, series, authors, by_title, by_series,
      match_series=match_series)
    source_candidates = [
      book_id for book_id in source_candidates
      if book_id not in excluded_book_ids
    ]
    if progress is not None:
      progress(0.6, f'Checked Goodreads source for: {entry.get("title", "")}')
    if source_candidates:
      return source_candidates

    if not match_series:
      return []

    entry_keys = self.import_entry_keys(entry)
    relaxed_entry_keys = set()
    for key in entry_keys:
      relaxed_entry_keys.update(series_match_keys(key))
    relaxed_entry_keys.discard('')
    if not relaxed_entry_keys:
      return []
    candidates = []
    candidate_ids = []
    for book_id in ids:
      if book_id in excluded_book_ids:
        continue
      if not self.author_matches(authors.get(book_id, ''), entry.get('author', '')):
        continue
      goodreads_id = self.goodreads_id_for_book(book_id)
      if not goodreads_id:
        continue
      candidate_ids.append((book_id, goodreads_id))

    total_candidates = max(len(candidate_ids), 1)
    for lookup_index, (book_id, goodreads_id) in enumerate(candidate_ids, start=1):
      if progress is not None:
        fraction = 0.6 + (0.35 * (float(lookup_index - 1) / total_candidates))
        progress(
          fraction,
          f'Checking Goodreads book {lookup_index} of {total_candidates}: {entry.get("title", "")}')
      series_names = self.fetch_goodreads_series_names(goodreads_id)
      for series_name in series_names:
        keys = set(series_match_keys(series_name))
        if keys & relaxed_entry_keys:
          candidates.append(book_id)
          break
    if progress is not None:
      progress(0.95, f'Finished Goodreads checks for: {entry.get("title", "")}')
    return candidates

  def goodreads_source_recovery_candidates_for_match(
      self, entry, titles, series, authors, by_title, by_series, match_series=True):
    try:
      return self.goodreads_source_recovery_candidates(
        entry, titles, series, authors, by_title, by_series,
        match_series=match_series)
    except TypeError as err:
      if 'match_series' not in str(err):
        raise
      return self.goodreads_source_recovery_candidates(
        entry, titles, series, authors, by_title, by_series) if match_series else []

  def goodreads_source_recovery_candidates(
      self, entry, titles, series, authors, by_title, by_series, match_series=True):
    data = self.fetch_goodreads_source_data(entry.get('source_url', ''))
    candidates = []
    if match_series:
      for series_name in data.get('series_names', []):
        keys = set(series_match_keys(series_name))
        for key in keys:
          candidates.extend(by_series.get(key, []))
    for source_book in data.get('books', []):
      for title_key in match_keys(source_book.get('title', '')):
        for book_id in by_title.get(title_key, []):
          source_author = source_book.get('author', '') or entry.get('author', '')
          if self.author_matches(authors.get(book_id, ''), source_author):
            candidates.append(book_id)

    deduped = []
    seen = set()
    for book_id in candidates:
      if book_id not in seen:
        seen.add(book_id)
        deduped.append(book_id)
    self.debug_import_goodreads_source_candidates(entry, data, deduped)
    return deduped

  def import_entry_keys(self, entry):
    names = [entry.get('title', '')]
    aliases = entry.get('aliases') or []
    if isinstance(aliases, str):
      aliases = [aliases]
    names.extend(aliases)
    keys = []
    for name in names:
      for key in match_keys(name):
        if key and key not in keys:
          keys.append(key)
    return keys

  def series_index_updates(self, active_updates):
    index_field = self.active_series_index_field()
    if not index_field:
      return {}
    max_by_list = {}
    update_ids = set(active_updates)
    for book_id in self.all_book_ids():
      if book_id in update_ids:
        continue
      list_name = clean_name(self.read_field(prefs['active_list_field'], book_id))
      if not list_name:
        continue
      index = self.read_series_index(index_field, book_id)
      if index is None:
        continue
      key = normalize_key(list_name)
      max_by_list[key] = max(max_by_list.get(key, 0), index)

    index_updates = {}
    for book_id, list_name in active_updates.items():
      list_name = clean_name(list_name)
      if not list_name:
        continue
      key = normalize_key(list_name)
      next_index = int(max_by_list.get(key, 0)) + 1
      max_by_list[key] = next_index
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
    self.refresh_books(changed)
    self.debug_writes_finished(active_updates, stored_updates, changed)

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

  def status_message(self, message):
    status_bar = getattr(self.gui, 'status_bar', None)
    if hasattr(status_bar, 'show_message'):
      status_bar.show_message(message, 5000)
    elif hasattr(status_bar, 'showMessage'):
      status_bar.showMessage(message, 5000)
    else:
      self.debug_general_status_message(message)

  def refresh_books(self, ids):
    if not ids:
      return
    model = self.gui.library_view.model()
    model.refresh_ids(list(ids))
    try:
      self.gui.tags_view.recount()
    except Exception:
      pass

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
    self.write_fields(active_updates=updates, assign_series_indexes=True)
    self.status_message(
      f'Added {len(updates)} books to "{active}". Skipped {skipped} already on the list.')

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

  def show_debug_dialog(self):
    d = DebugDialog(self.gui, DEBUG_SECTIONS)
    if d.exec() != QDialog.Accepted:
      return
    prefs['debug_logging'] = bool(d.debug_logging.isChecked())
    prefs['debug_sections'] = {
      key: bool(box.isChecked())
      for key, box in d.section_boxes.items()
    }
    if prefs['debug_logging']:
      self.status_message('List Switchboard debug logging is on for all sections.')
    else:
      enabled = [label for key, label in DEBUG_SECTIONS if prefs['debug_sections'].get(key)]
      if enabled:
        self.status_message(f'List Switchboard debug logging is on for: {", ".join(enabled)}.')
      else:
        self.status_message('List Switchboard debug logging is off.')

  def set_include_calibre_series(self, enabled):
    prefs['include_calibre_series'] = bool(enabled)
    state = 'on' if prefs['include_calibre_series'] else 'off'
    self.status_message(f'Include series when adding is {state}.')

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
      stored = unique_case_insensitive([entry for entry in parse_stored_lists(
        self.read_field(prefs['stored_lists_field'], book_id)) if entry])
      stored_by_key = OrderedDict((normalize_key(name), name) for name in stored)
      if normalize_key(current) == key:
        active_updates[book_id] = ''
        stored_by_key[key] = self.stored_entry_for_active(book_id, active, require_position=True)
      stored_updates[book_id] = format_stored_lists(stored_by_key.values())
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
      stored = [entry for entry in parse_stored_lists(
        self.read_field(prefs['stored_lists_field'], book_id)) if normalize_key(entry) != key]
      stored_updates[book_id] = format_stored_lists(unique_case_insensitive(stored))
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
      stored_updates[book_id] = format_stored_lists(unique_case_insensitive(entries))
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

  def show_about(self):
    QMessageBox.about(self.gui, 'About List Switchboard', ABOUT_TEXT)

  def show_exception(self, title, err):
    self.debug_exception()
    error_dialog(self.gui, title, str(err), show=True)
