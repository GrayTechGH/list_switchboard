#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

__license__ = 'GPL v3'
__copyright__ = '2026, List Switchboard contributors'
__docformat__ = 'restructuredtext en'

"""
Calibre-facing facade for List Switchboard.

Maintenance notes:
- ListSwitchboardCore is intentionally a thin composition layer. Behavior lives
  in mixins by subsystem, while Calibre still imports one facade class.
- Mixin order matters only when mixins provide the same method. Keep DebugMixin
  early so every subsystem can log; workflow helpers use normal facade
  attribute lookup rather than cooperative `super()` calls.
- Module-level imports re-export helper names used by tests and older local
  scripts. Do not remove those compatibility imports just because main.py no
  longer defines the helpers directly.
"""

import os
import ssl
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

from bs4 import UnicodeDammit

from qt.core import QApplication, QDialog, QMessageBox

from calibre.gui2 import error_dialog
from calibre_plugins.list_switchboard.config import prefs

try:
  from calibre_plugins.list_switchboard.debug import DEBUG_SECTIONS, DebugMixin
except ImportError:
  from debug import DEBUG_SECTIONS, DebugMixin

try:
  from calibre_plugins.list_switchboard.errors import (
    DuplicateStoredListsError, ImportCancelledError, ListSwitchboardError
  )
except ImportError:
  from errors import DuplicateStoredListsError, ImportCancelledError, ListSwitchboardError

try:
  from calibre_plugins.list_switchboard.goodreads import (
    GOODREADS_LOOKUP_DELAY_SECONDS, GoodreadsMixin
  )
except ImportError:
  from goodreads import GOODREADS_LOOKUP_DELAY_SECONDS, GoodreadsMixin

try:
  from calibre_plugins.list_switchboard.import_flow import (
    IMPORT_MATCH_PROGRESS_MAX, IMPORT_WRITE_PROGRESS_MAX, URL_FETCHER_PACKAGE,
    ImportFlowMixin,
  )
except ImportError:
  from import_flow import (
    IMPORT_MATCH_PROGRESS_MAX, IMPORT_WRITE_PROGRESS_MAX, URL_FETCHER_PACKAGE,
    ImportFlowMixin,
  )

try:
  from calibre_plugins.list_switchboard.matching import (
    FIND_MATCH_AUTHOR_SOUNDEX_LENGTH_DEFAULT, FIND_MATCH_MODES,
    FIND_MATCH_TITLE_SOUNDEX_LENGTH_DEFAULT, FIND_MODE_FUZZY, FIND_MODE_IDENTICAL,
    FIND_MODE_IGNORE,
    FIND_MODE_SIMILAR, FIND_MODE_SOUNDEX, MatchingMixin, author_find_key,
    clean_name, find_fuzzy_author_key, find_fuzzy_title_key,
    find_identical_author_key, find_identical_title_key,
    find_similar_author_key, find_similar_title_key, imported_author_display_value,
    imported_author_key, imported_author_list, imported_author_search_text,
    imported_entry_source_url, match_keys, normalize_key, normalize_match_text,
    series_match_keys, split_position_suffix, title_find_key,
    title_sort_without_article, validate_find_match_modes,
  )
except ImportError:
  from matching import (
    FIND_MATCH_AUTHOR_SOUNDEX_LENGTH_DEFAULT, FIND_MATCH_MODES,
    FIND_MATCH_TITLE_SOUNDEX_LENGTH_DEFAULT, FIND_MODE_FUZZY, FIND_MODE_IDENTICAL,
    FIND_MODE_IGNORE,
    FIND_MODE_SIMILAR, FIND_MODE_SOUNDEX, MatchingMixin, author_find_key,
    clean_name, find_fuzzy_author_key, find_fuzzy_title_key,
    find_identical_author_key, find_identical_title_key,
    find_similar_author_key, find_similar_title_key, imported_author_display_value,
    imported_author_key, imported_author_list, imported_author_search_text,
    imported_entry_source_url, match_keys, normalize_key, normalize_match_text,
    series_match_keys, split_position_suffix, title_find_key,
    title_sort_without_article, validate_find_match_modes,
  )

try:
  from calibre_plugins.list_switchboard.metadata import (
    MetadataMixin, format_list_entry, format_stored_lists, next_whole_index_after,
    parse_stored_lists, rebuild_stored_lists, sort_names, unique_case_insensitive,
    validate_list_name,
  )
except ImportError:
  from metadata import (
    MetadataMixin, format_list_entry, format_stored_lists, next_whole_index_after,
    parse_stored_lists, rebuild_stored_lists, sort_names, unique_case_insensitive,
    validate_list_name,
  )

try:
  from calibre_plugins.list_switchboard.list_state import ListStateMixin
except ImportError:
  from list_state import ListStateMixin

try:
  from calibre_plugins.list_switchboard.storage import (
    StorageMixin, entry_key, parsed_append_state, safe_list_id,
  )
except ImportError:
  from storage import StorageMixin, entry_key, parsed_append_state, safe_list_id

try:
  from calibre_plugins.list_switchboard.dialogs import DebugDialog
except ImportError:
  from dialogs import DebugDialog

try:
  from calibre.utils.browser import Browser as CalibreBrowser
except Exception as err:
  CalibreBrowser = None
  CalibreBrowserImportError = err
else:
  CalibreBrowserImportError = None


ABOUT_TEXT = '''List Switchboard

A Calibre GUI plugin for managing an active reading list and stored alternate lists using configured metadata fields.

List Switchboard only edits the configured metadata fields. It does not delete, move, convert, or modify book files.'''

DEFAULT_USER_AGENT = (
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
  'AppleWebKit/537.36 (KHTML, like Gecko) '
  'Chrome/124.0.0.0 Safari/537.36'
)
DEFAULT_RESPONSE_MAX_BYTES = 10 * 1024 * 1024
LARGE_RESPONSE_MAX_BYTES = 32 * 1024 * 1024


class ResponseTooLargeError(RuntimeError):
  pass


def response_content_length(response):
  headers = getattr(response, 'headers', None)
  if headers is None:
    return None
  try:
    value = headers.get('Content-Length')
  except Exception:
    return None
  try:
    return int(value) if value is not None else None
  except (TypeError, ValueError):
    return None


def read_limited_response(response, max_bytes=DEFAULT_RESPONSE_MAX_BYTES):
  max_bytes = int(max_bytes or DEFAULT_RESPONSE_MAX_BYTES)
  content_length = response_content_length(response)
  if content_length is not None and content_length > max_bytes:
    raise ResponseTooLargeError(
      f'Remote response is {content_length} bytes, exceeding the {max_bytes}-byte limit.')
  data = response.read(max_bytes + 1)
  if len(data) > max_bytes:
    raise ResponseTooLargeError(
      f'Remote response exceeds the {max_bytes}-byte limit.')
  return data


def decode_url_response(response, max_bytes=DEFAULT_RESPONSE_MAX_BYTES):
  data = read_limited_response(response, max_bytes=max_bytes)
  charset = response.headers.get_content_charset() if response.headers else None
  return decode_response_data(data, charset=charset)


def decode_response_data(data, charset=None):
  known_encodings = (charset,) if charset else ()
  decoded = UnicodeDammit(
    data,
    known_definite_encodings=known_encodings,
    is_html=True).unicode_markup
  if decoded:
    return decoded
  if charset:
    try:
      return data.decode(charset)
    except (LookupError, UnicodeDecodeError):
      pass
  for candidate in ('utf-8', 'windows-1252'):
    try:
      return data.decode(candidate)
    except (LookupError, UnicodeDecodeError):
      pass
  return data.decode(charset or 'utf-8', 'replace')


def ssl_error_reason(err):
  reason = getattr(err, 'reason', err)
  if isinstance(reason, ssl.SSLError):
    return reason
  if isinstance(err, ssl.SSLError):
    return err
  return None


def is_ssl_certificate_error(err):
  reason = ssl_error_reason(err)
  if isinstance(reason, ssl.SSLCertVerificationError):
    return True
  return 'CERTIFICATE_VERIFY_FAILED' in str(err)


def ssl_fetch_diagnostics(url, transport, err):
  verify_paths = ssl.get_default_verify_paths()
  reason = ssl_error_reason(err)
  details = [
    f'url={url}',
    f'transport={transport}',
    f'exception={err.__class__.__name__}: {err}',
    f'openssl={getattr(ssl, "OPENSSL_VERSION", "")}',
    f'default cafile={verify_paths.cafile}',
    f'default capath={verify_paths.capath}',
    f'openssl cafile={verify_paths.openssl_cafile}',
    f'openssl capath={verify_paths.openssl_capath}',
    f'SSL_CERT_FILE={os.environ.get("SSL_CERT_FILE", "")}',
    f'SSL_CERT_DIR={os.environ.get("SSL_CERT_DIR", "")}',
    f'calibre browser available={CalibreBrowser is not None}',
  ]
  if CalibreBrowserImportError is not None:
    details.append(
      f'calibre browser import error={CalibreBrowserImportError.__class__.__name__}: '
      f'{CalibreBrowserImportError}')
  if reason is not None:
    details.append(f'ssl reason={reason.__class__.__name__}: {reason}')
    verify_code = getattr(reason, 'verify_code', None)
    verify_message = getattr(reason, 'verify_message', None)
    if verify_code is not None:
      details.append(f'verify code={verify_code}')
    if verify_message:
      details.append(f'verify message={verify_message}')
  return '; '.join(details)


def certificate_fetch_error(url, transport, err):
  return RuntimeError(
    f'{err}\nSSL fetch diagnostics: {ssl_fetch_diagnostics(url, transport, err)}')


class ListSwitchboardCore(
    DebugMixin,
    StorageMixin,
    ImportFlowMixin,
    ListStateMixin,
    MetadataMixin,
    GoodreadsMixin,
    MatchingMixin):
  """
  Facade object owned by Calibre's InterfaceAction.

  Type constraints:
  - gui must provide the Calibre GUI surface used here: current_db,
    library_view, tags_view, and status_bar.
  - self.db is expected to be a Calibre database object exposing new_api,
    field_metadata, prefs, and set_custom.

  Rationale:
  - The plugin API expects a single action/core object, but the implementation
    is split into mixins so matching, Goodreads, import flow, metadata, list
    state, and debug behavior can be maintained independently.

  Maintenance notes:
  - Runtime state kept here is shared across mixins: Goodreads cache, progress
    dialog, Calibre browser, gui, and db.
  - Do not move these attributes into individual mixin constructors unless every
    construction path calls those constructors.
  """

  def __init__(self, gui, do_user_config, plugin_base=None):
    self.gui = gui
    self.do_user_config = do_user_config
    self.plugin_base = plugin_base
    self.db = getattr(gui, 'current_db', None)
    self.goodreads_series_cache = {}
    self._cached_active_add_import_map = None
    self.last_goodreads_lookup_time = 0
    self.import_progress = None
    self.import_progress_phase_number = 0
    self.import_progress_total_phases = 0
    self.import_progress_phase_name = ''
    self.import_progress_phase_value = 0
    self.browser = None

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

  def display_authors(self, authors):
    if authors is None:
      return ''
    try:
      from calibre.ebooks.metadata import authors_to_string, string_to_authors
    except Exception:
      authors_to_string = string_to_authors = None
    if authors_to_string is not None:
      try:
        if isinstance(authors, (list, tuple)):
          return authors_to_string([str(author) for author in authors])
        text = str(authors or '')
        return authors_to_string(string_to_authors(text)) if text else ''
      except Exception:
        pass
    if isinstance(authors, (list, tuple)):
      return ', '.join(str(author) for author in authors)
    return str(authors)

  def fetch_headers(self, user_agent=None):
    return {
      'User-Agent': user_agent or DEFAULT_USER_AGENT,
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      'Accept-Language': 'en-US,en;q=0.9',
      'Connection': 'close',
    }

  def fetch_url(self, url, user_agent=None, max_bytes=None):
    max_bytes = max_bytes or DEFAULT_RESPONSE_MAX_BYTES
    headers = self.fetch_headers(user_agent=user_agent)
    if CalibreBrowser is not None:
      try:
        browser = self.calibre_browser(headers)
        response = browser.open(url, timeout=30)
        return decode_url_response(response, max_bytes=max_bytes)
      except Exception as err:
        if is_ssl_certificate_error(err):
          diagnostics = ssl_fetch_diagnostics(url, 'calibre browser', err)
          self.debug_log(f'SSL fetch diagnostics: {diagnostics}', section='fallback')
          raise certificate_fetch_error(url, 'calibre browser', err)
        raise
    self.debug_fallback_urllib_fetch(url)
    request = Request(url, headers=headers)
    try:
      with urlopen(request, timeout=30) as response:
        return decode_url_response(response, max_bytes=max_bytes)
    except (URLError, ssl.SSLError) as err:
      if is_ssl_certificate_error(err):
        diagnostics = ssl_fetch_diagnostics(url, 'urllib', err)
        self.debug_log(f'SSL fetch diagnostics: {diagnostics}', section='fallback')
        raise certificate_fetch_error(url, 'urllib', err)
      raise

  def calibre_browser(self, headers):
    if self.browser is None:
      self.browser = CalibreBrowser()
      try:
        self.browser.set_handle_robots(False)
      except Exception:
        pass
    self.browser.addheaders = list(headers.items())
    return self.browser

  def sleep_with_events(self, seconds, message):
    end_time = time.time() + max(0, seconds)
    while time.time() < end_time:
      self.update_import_progress(message=message)
      time.sleep(min(0.1, max(0, end_time - time.time())))

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

  def show_debug_dialog(self):
    d = DebugDialog(self.gui, DEBUG_SECTIONS)
    if d.exec() != QDialog.Accepted:
      return
    prefs['debug_logging'] = bool(d.debug_logging.isChecked())
    prefs['debug_sections'] = {
      key: bool(box.isChecked())
      for key, box in d.section_boxes.items()
    }
    prefs['debug_force_fallback_level'] = int(d.force_fallback_level.currentData() or 0)
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

  def show_about(self):
    QMessageBox.about(self.gui, 'About List Switchboard', ABOUT_TEXT)

  def show_exception(self, title, err):
    self.debug_exception()
    error_dialog(self.gui, title, str(err), show=True)
