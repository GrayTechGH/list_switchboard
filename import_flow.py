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

from calibre.gui2 import error_dialog, question_dialog

try:
  from calibre_plugins.list_switchboard.dialogs import ImportRecipeDialog, ImportReportDialog
except ImportError:
  from dialogs import ImportRecipeDialog, ImportReportDialog

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, ListSwitchboardError
except ImportError:
  from errors import ImportCancelledError, ListSwitchboardError

try:
  from calibre_plugins.list_switchboard.matching import normalize_key
except ImportError:
  from matching import normalize_key

try:
  from calibre_plugins.list_switchboard.config import prefs
except ImportError:
  from config import prefs

try:
  from calibre_plugins.list_switchboard.metadata import validate_list_name
except ImportError:
  from metadata import validate_list_name


IMPORT_MATCH_PROGRESS_MAX = 500
IMPORT_WRITE_PROGRESS_MAX = 1000
IMPORT_PROGRESS_MESSAGE_MAX = 220
IMPORT_PROGRESS_TOKEN_MAX = 80
IMPORT_PROGRESS_TOKEN_HEAD = 48
IMPORT_PROGRESS_TOKEN_TAIL = 24
IMPORT_PROGRESS_DIALOG_WIDTH = 560
URL_FETCHER_PACKAGE = 'url_fetcher'


def compact_import_progress_message(message):
  """
  Keep progress labels from widening QProgressDialog around long URLs/titles.

  Qt sizes progress dialogs from the label's size hint. A single unbroken URL
  can make the whole dialog comically wide, so long tokens are middle-elided
  before the message is handed to setLabelText().
  """
  text = str(message or '')
  parts = []
  for token in text.split():
    if len(token) > IMPORT_PROGRESS_TOKEN_MAX:
      token = (
        token[:IMPORT_PROGRESS_TOKEN_HEAD] + '...' +
        token[-IMPORT_PROGRESS_TOKEN_TAIL:]
      )
    parts.append(token)
  text = ' '.join(parts)
  if len(text) > IMPORT_PROGRESS_MESSAGE_MAX:
    tail_length = min(IMPORT_PROGRESS_TOKEN_TAIL, len(text))
    head_length = max(0, IMPORT_PROGRESS_MESSAGE_MAX - tail_length - 3)
    text = text[:head_length].rstrip() + '...' + text[-tail_length:]
  return text


def constrain_import_progress_dialog(progress):
  try:
    progress.setFixedWidth(IMPORT_PROGRESS_DIALOG_WIDTH)
  except Exception:
    pass


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

  def choose_and_import_recipe(self):
    if not self.ensure_configured():
      return
    recipes = self.available_import_recipes()
    if not recipes:
      error_dialog(self.gui, 'Import List', self.recipe_discovery_summary(), show=True)
      return
    d = ImportRecipeDialog(self.gui, recipes)
    if d.exec() != QDialog.Accepted:
      return
    recipe = d.selected_recipe
    import_options = getattr(d, 'selected_options', {}) or {}
    if recipe is not None:
      self.import_recipe(recipe, import_options=import_options)

  def import_recipe_by_name(self, recipe_name):
    for recipe in self.available_import_recipes():
      if recipe.NAME == recipe_name:
        self.import_recipe(recipe)
        return
    error_dialog(self.gui, 'Import List', f'Could not find import recipe "{recipe_name}".', show=True)

  def save_active_matches_by_recipe_name(self, recipe_name):
    for recipe in self.available_import_recipes():
      if recipe.NAME == recipe_name:
        try:
          self.save_active_matches_for_recipe(recipe)
        except Exception as err:
          self.show_exception('Save Active List Matches', err)
        return
    error_dialog(self.gui, 'Save Active List Matches', f'Could not find import recipe "{recipe_name}".', show=True)

  def save_active_matches_for_current_active_list(self):
    try:
      self.save_active_matches_for_active_list()
    except Exception as err:
      self.show_exception('Save Active List Matches', err)

  def import_recipe(self, recipe, import_options=None):
    if not self.ensure_configured():
      return
    import_options = dict(import_options or {})
    progress = None
    try:
      self.debug_recipe_start(recipe)
      progress = self.create_import_progress(recipe.NAME)
      self.import_progress = progress
      parsed = self.load_or_fetch_recipe(recipe, import_options=import_options)
      self.show_import_progress_start(parsed)
      self.log_recipe_output(parsed)
      self.import_recipe_result(parsed, recipe=recipe, import_options=import_options)
    except ImportCancelledError as err:
      self.status_message(str(err))
    except Exception as err:
      self.show_exception('Import List', err)
    finally:
      self.import_progress = None
      if progress is not None:
        progress.close()

  def recipe_list_id(self, recipe):
    source_id = getattr(recipe, 'source_id', '') or recipe.NAME
    return self.safe_list_id(source_id)

  def safe_list_id(self, value):
    try:
      from calibre_plugins.list_switchboard.storage import safe_list_id
    except ImportError:
      from storage import safe_list_id
    return safe_list_id(value)

  def load_or_fetch_recipe(self, recipe, import_options=None):
    list_id = self.recipe_list_id(recipe)
    cache = self.read_import_cache(list_id)
    if cache and self.should_use_cached_import(recipe, cache):
      parsed = self.cached_import_to_parsed(cache)
      parsed['list_id'] = list_id
      self.update_import_progress(0, f'Using saved "{recipe.NAME}" list...')
      return parsed
    try:
      self.update_import_progress(0, f'Fetching "{recipe.NAME}"...')
      parsed = self.fetch_and_parse_recipe(recipe, import_options=import_options)
    except Exception:
      if cache and self.should_fallback_to_cached_import(recipe, cache):
        parsed = self.cached_import_to_parsed(cache)
        parsed['list_id'] = list_id
        self.update_import_progress(0, f'Using saved "{recipe.NAME}" list...')
        return parsed
      raise
    parsed['list_id'] = list_id
    if cache:
      self.merge_append_import_cache(list_id, cache, parsed, recipe=recipe)
    else:
      self.write_import_cache(list_id, parsed, recipe=recipe)
    return parsed

  def should_use_cached_import(self, recipe, cache):
    fetched_at = cache.get('fetched_at') or 'unknown time'
    entries = len(cache.get('entries') or [])
    return question_dialog(
      self.gui,
      'Import List',
      f'A saved "{recipe.NAME}" list is available from {fetched_at} with {entries} entries.\n\n'
      'Use the saved list instead of importing from the web?')

  def should_fallback_to_cached_import(self, recipe, cache):
    fetched_at = cache.get('fetched_at') or 'unknown time'
    entries = len(cache.get('entries') or [])
    return question_dialog(
      self.gui,
      'Import List',
      f'Could not import "{recipe.NAME}" from the web.\n\n'
      f'Use the saved list from {fetched_at} with {entries} entries instead?')

  def create_import_progress(self, list_name):
    progress = QProgressDialog('Preparing import...', 'Cancel', 0, IMPORT_WRITE_PROGRESS_MAX, self.gui)
    progress.setWindowTitle(f'Import List: {list_name}')
    progress.setMinimumDuration(0)
    progress.setAutoClose(False)
    progress.setAutoReset(False)
    progress.setValue(0)
    constrain_import_progress_dialog(progress)
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
    constrain_import_progress_dialog(progress)
    QApplication.processEvents()
    return progress

  def update_import_progress(self, value=None, message=None):
    progress = self.import_progress
    if progress is None:
      QApplication.processEvents()
      return
    if message is not None:
      progress.setLabelText(compact_import_progress_message(message))
      constrain_import_progress_dialog(progress)
    if value is not None:
      progress.setValue(value)
      constrain_import_progress_dialog(progress)
    QApplication.processEvents()
    if message is not None or value is not None:
      constrain_import_progress_dialog(progress)
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

  def fetch_and_parse_recipe(self, recipe, import_options=None):
    import_options = import_options or {}
    source_choice = import_options.get('source_choice', 'automatic')
    if bool(import_options.get('disable_fallbacks', False)):
      source_choice = 0
    try:
      return recipe.fetch_and_parse(
        self.fetch_url,
        sleep=lambda seconds, message: self.sleep_with_events(seconds, message),
        fetch_error=lambda url, err, entry: self.debug_recipe_linked_page_failed(url, err, entry),
        log=lambda message: self.debug_parser_message(message),
        progress=lambda done, total, message: self.update_import_fetch_progress(done, total, message),
        force_fallback_level=int(prefs.get('debug_force_fallback_level', 0) or 0),
        disable_fallbacks=bool(import_options.get('disable_fallbacks', False)),
        source_choice=source_choice,
        before_fetch=lambda url: (
          self.debug_recipe_fetch_url(url),
          self.update_import_progress(message=f'Fetching "{recipe.NAME}"...')),
        after_fetch=lambda url, html: self.debug_recipe_fetched(url, html),
        before_parse=lambda _url: self.update_import_progress(message=f'Parsing "{recipe.NAME}"...'))
    except Exception as err:
      raise ListSwitchboardError(str(err))

  def log_recipe_output(self, parsed):
    self.debug_recipe_output(parsed)

  def effective_import_match_series(self, parsed, recipe=None, import_options=None):
    if bool(getattr(recipe, 'REQUIRES_SERIES_MATCHING', False)):
      return True
    if import_options is not None and 'match_series' in import_options:
      return bool(import_options.get('match_series'))
    return parsed.get('match_series', True)

  def import_recipe_result(self, parsed, recipe=None, import_options=None):
    list_name = validate_list_name(parsed['name'])
    entries = parsed.get('entries') or []
    if not entries:
      raise ListSwitchboardError('The imported list did not contain any entries.')

    active = self.current_active()
    self.debug_import_target(list_name, active)
    self.update_import_match_progress(0, len(entries), f'Matching 0 of {len(entries)} recipe entries...')
    match_series = self.effective_import_match_series(parsed, recipe, import_options)
    award_winners_only = bool((import_options or {}).get('award_winners_only', False))
    allow_goodreads_recovery = not parsed.get('from_cache')
    try:
      match_result = self.match_imported_entries(
        entries,
        match_series=match_series,
        list_id=parsed.get('list_id'),
        allow_goodreads_recovery=allow_goodreads_recovery,
        award_winners_only=award_winners_only,
        return_details=True)
      if len(match_result) == 3:
        matched, missing_entries, review_rows = match_result
      else:
        matched, missing_entries = match_result
        review_rows = self.import_review_rows_from_legacy_match(entries, matched, missing_entries)
    except TypeError as err:
      if (
          'match_series' not in str(err)
          and 'allow_goodreads_recovery' not in str(err)
          and 'award_winners_only' not in str(err)
          and 'return_details' not in str(err)):
        raise
      matched, missing_entries = self.match_imported_entries(entries)
      review_rows = self.import_review_rows_from_legacy_match(entries, matched, missing_entries)
    self.debug_import_summary(matched, missing_entries, entries)

    self.update_import_progress(IMPORT_MATCH_PROGRESS_MAX, 'Preparing import review...')
    self.close_import_progress()
    review = self.review_import_matches(
      list_name, parsed.get('list_id'), len(matched), len(entries),
      missing_entries, review_rows, notes=parsed.get('notes'))
    if review is None:
      raise ImportCancelledError('Import cancelled. No Active List metadata was changed.')
    matched, missing_entries, review_rows = review
    if not matched:
      raise ListSwitchboardError('No matched entries were selected for import.')

    try:
      self.import_progress = self.create_import_progress(list_name)
    except AttributeError:
      self.import_progress = None

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
        self.debug_import_matched_book_write_skipped(book_id, list_name, position)
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
    self.close_import_progress()

  def import_review_rows_from_legacy_match(self, entries, matched, missing_entries):
    matched_positions = {}
    for book_id, position in (matched or {}).items():
      matched_positions.setdefault(str(position or ''), []).append(book_id)
    missing = set(id(entry) for entry in (missing_entries or []))
    rows = []
    consumed_book_ids = set()
    for entry in entries:
      position = str(entry.get('position', '') or '')
      book_ids = matched_positions.get(position, []) if id(entry) not in missing else []
      consumed_book_ids.update(book_ids)
      rows.append({
        'entry': entry,
        'imported_position': position,
        'imported_title': entry.get('title', ''),
        'imported_author': entry.get('author', ''),
        'matched': bool(book_ids),
        'original_matched': bool(book_ids),
        'book_ids': book_ids,
        'original_book_ids': list(book_ids),
        'matched_books': [],
        'original_matched_books': [],
        'match_source': 'automatic' if book_ids else 'never matched',
        'original_match_source': 'automatic' if book_ids else 'never matched',
        'can_toggle_on': bool(book_ids),
      })
    for book_id, position in (matched or {}).items():
      if book_id in consumed_book_ids:
        continue
      rows.append({
        'entry': {'position': position, 'title': '', 'author': ''},
        'imported_position': position,
        'imported_title': '',
        'imported_author': '',
        'matched': True,
        'original_matched': True,
        'book_ids': [book_id],
        'original_book_ids': [book_id],
        'matched_books': [],
        'original_matched_books': [],
        'match_source': 'automatic',
        'original_match_source': 'automatic',
        'can_toggle_on': True,
      })
    return rows

  def review_import_matches(
      self, list_name, list_id, matched_count, entries_count, missing_entries,
      review_rows, notes=None):
    self.debug_import_missing_entries(missing_entries)
    try:
      gui = self.gui
    except AttributeError:
      return self.accepted_import_review_rows(review_rows)
    try:
      d = ImportReportDialog(
        gui, list_name, matched_count, entries_count, missing_entries,
        allow_deep_recovery=False, notes=notes, review_rows=review_rows,
        find_match_settings=self.find_match_settings(),
        save_find_match_settings=self.save_find_match_settings,
        find_match_index_callback=self.find_match_library_index,
        find_match_callback=self.find_matches_for_review_rows,
        view_book_callback=self.open_book_detail_window)
    except TypeError as err:
      if (
          'find_match_settings' not in str(err)
          and 'find_match_index_callback' not in str(err)
          and 'view_book_callback' not in str(err)):
        raise
      d = ImportReportDialog(
        gui, list_name, matched_count, entries_count, missing_entries,
        allow_deep_recovery=False, notes=notes, review_rows=review_rows)
    if d.exec() != QDialog.Accepted:
      return None
    self.apply_import_review_match_changes(list_id, d.review_rows)
    return d.accepted_matched(), d.accepted_missing_entries(), d.review_rows

  def find_match_settings(self):
    return {
      'title_mode': prefs.get('find_match_title_mode', 'similar'),
      'author_mode': prefs.get('find_match_author_mode', 'similar'),
      'title_soundex_length': prefs.get('find_match_title_soundex_length', 6),
      'author_soundex_length': prefs.get('find_match_author_soundex_length', 8),
    }

  def save_find_match_settings(self, settings):
    prefs['find_match_title_mode'] = settings.get('title_mode', 'similar')
    prefs['find_match_author_mode'] = settings.get('author_mode', 'similar')
    prefs['find_match_title_soundex_length'] = int(settings.get('title_soundex_length', 6))
    prefs['find_match_author_soundex_length'] = int(settings.get('author_soundex_length', 8))

  def open_book_detail_window(self, book_id):
    gui = getattr(self, 'gui', None)
    if gui is None or book_id is None:
      return False
    for method_name in ('show_book_info', 'show_book_details', 'show_book_details_window'):
      method = getattr(gui, method_name, None)
      if callable(method):
        method(book_id)
        return True
    iactions = getattr(gui, 'iactions', {}) or {}
    for key in ('Show Book Details', 'Book Details', 'View'):
      action = iactions.get(key) if hasattr(iactions, 'get') else None
      if action is None:
        continue
      for method_name in (
          'show_book_info', 'show_book_details', 'show_book_details_window',
          'view_book'):
        method = getattr(action, method_name, None)
        if callable(method):
          method(book_id)
          return True
    library_view = getattr(gui, 'library_view', None)
    select_rows = getattr(library_view, 'select_rows', None)
    if callable(select_rows):
      select_rows([book_id])
    return False

  def find_matches_for_review_rows(self, review_rows, settings, index=None):
    matched_book_ids = set()
    for row in review_rows or []:
      if row.get('matched'):
        matched_book_ids.update(row.get('book_ids') or [])
    if index is None:
      index = self.find_match_library_index(
        title_mode=settings.get('title_mode', 'similar'),
        author_mode=settings.get('author_mode', 'similar'),
        title_soundex_length=settings.get('title_soundex_length', 6),
        author_soundex_length=settings.get('author_soundex_length', 8))
    for row in review_rows or []:
      if row.get('matched'):
        continue
      excluded = matched_book_ids | set(row.get('book_ids') or [])
      row['possible_matches'] = self.find_import_match_candidates_from_index(
        row.get('entry') or {
          'title': row.get('imported_title', ''),
          'author': row.get('imported_author', ''),
        },
        index,
        excluded_book_ids=excluded)
    return review_rows

  def accepted_import_review_rows(self, review_rows):
    matched = {}
    missing_entries = []
    for row in review_rows or []:
      if row.get('matched'):
        for book_id in row.get('book_ids') or []:
          matched[book_id] = row.get('imported_position', '')
      else:
        missing_entries.append(row.get('entry') or {})
    return matched, missing_entries, review_rows

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
    constrain_import_progress_dialog(progress)
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
