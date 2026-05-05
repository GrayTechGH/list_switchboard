#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Import recipe orchestration and progress accounting.

Maintenance notes:
- Progress ranges are split for imports: matching/fetching uses 0..500 and
  metadata writes use 500..1000. Operation-only writes use the full 0..1000
  range.
- write_fields_with_progress() assumes update dictionaries contain real writes,
  not every book in the library. Inflated denominators make progress bars appear
  stuck.
- Recipes are loaded lazily from url_fetcher so Calibre startup can succeed even
  before a database object is fully available.
"""

from qt.core import QApplication, QDialog, QProgressDialog

from calibre.gui2 import error_dialog

try:
  from calibre_plugins.list_switchboard.dialogs import ImportReportDialog
except ImportError:
  from dialogs import ImportReportDialog

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, ListSwitchboardError
except ImportError:
  from errors import ImportCancelledError, ListSwitchboardError

try:
  from calibre_plugins.list_switchboard.matching import normalize_key
except ImportError:
  from matching import normalize_key

try:
  from calibre_plugins.list_switchboard.metadata import validate_list_name
except ImportError:
  from metadata import validate_list_name


IMPORT_MATCH_PROGRESS_MAX = 500
IMPORT_WRITE_PROGRESS_MAX = 1000
URL_FETCHER_PACKAGE = 'url_fetcher'


class ImportFlowMixin:
  """
  Coordinates recipe fetching, matching, writing, reports, and deep recovery.

  Type constraints:
  - self.gui must support Qt progress dialogs.
  - MatchingMixin, MetadataMixin, ListStateMixin, GoodreadsMixin, and DebugMixin
    methods are expected on self through ListSwitchboardCore composition.
  - Recipes must expose NAME, URL, order, and fetch_and_parse().

  Invariants:
  - Import cancellation must leave Active List metadata unchanged once writes
    have begun; the cancel button is removed before write_fields().
  - matched maps book_id -> imported position string.
  - missing_entries are parser entry dictionaries that could not be matched.

  Refactor warning:
  - Do not turn progress callbacks into percentages at the write_fields() layer.
    That layer reports write counts; this module maps counts to UI ranges.
  """

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
