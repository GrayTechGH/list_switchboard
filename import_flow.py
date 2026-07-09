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
  from calibre_plugins.list_switchboard.dialogs import (
    ImportCacheChoiceDialog, ImportRecipeDialog, ImportReportDialog)
except ImportError:
  from dialogs import ImportCacheChoiceDialog, ImportRecipeDialog, ImportReportDialog

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, ListSwitchboardError
except ImportError:
  from errors import ImportCancelledError, ListSwitchboardError

try:
  from calibre_plugins.list_switchboard.matching import (
    imported_author_search_text, normalize_key,
  )
except ImportError:
  from matching import imported_author_search_text, normalize_key

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


def parsed_list_source_url(parsed):
  source = parsed.get('source') if isinstance(parsed.get('source'), dict) else {}
  return str(source.get('url') or '')


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

  def manage_current_active_list(self):
    try:
      self.manage_active_list_review()
    except Exception as err:
      self.show_exception('Manage Active List', err)

  def show_current_active_list_position_problems(self):
    try:
      problems = self.current_active_list_position_problems()
      active = self.current_active() or 'Active List'
      if not problems:
        self.status_message(f'No position problems found for "{active}".')
        return
      details = '\n'.join(
        f'- {row["position"]}: {row["title"]} by {row["author"]} (book id {row["book_id"]})'
        for row in problems[:20])
      if len(problems) > 20:
        details = f'{details}\n- ...and {len(problems) - 20} more'
      error_dialog(
        self.gui,
        'Active List Position Problems',
        f'{len(problems)} current Active List book(s) use positions not found in the imported recipe.\n\n'
        f'{details}',
        show=True)
    except Exception as err:
      self.show_exception('Active List Position Problems', err)

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
    import_options = dict(import_options or {})
    list_id = self.recipe_list_id(recipe)
    cache = self.read_import_cache(list_id)
    cache_choice = 'refresh'
    if cache:
      cache_choice = self.choose_cached_import_action(recipe, cache)
    if cache_choice == 'cancel':
      raise ImportCancelledError('Import cancelled. No Active List metadata was changed.')
    if cache_choice == 'saved':
      parsed = self.cached_import_to_parsed(cache)
      parsed['list_id'] = list_id
      self.update_import_progress(0, f'Using saved "{recipe.NAME}" list...')
      return parsed
    can_incrementally_update = cache_choice == 'incremental'
    try:
      action = 'Updating saved pages for' if can_incrementally_update else 'Fetching'
      self.update_import_progress(0, f'{action} "{recipe.NAME}"...')
      parsed = self.fetch_and_parse_recipe(
        recipe,
        import_options=import_options,
        cache=cache if can_incrementally_update else None)
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

  def choose_cached_import_action(self, recipe, cache):
    dialog = ImportCacheChoiceDialog(
      self.gui,
      recipe,
      cache,
      supports_incremental_update=bool(
        getattr(recipe, 'SUPPORTS_INCREMENTAL_UPDATE', False)))
    if dialog.exec() != QDialog.Accepted:
      return 'cancel'
    return getattr(dialog, 'choice', 'cancel')

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
      for method_name in ('close', 'reset', 'deleteLater'):
        method = getattr(progress, method_name, None)
        if method is None:
          continue
        try:
          method()
        except Exception as err:
          debug_log = getattr(self, 'debug_log', None)
          if debug_log is not None:
            try:
              debug_log(
                f'progress dialog cleanup failed during {method_name}: {err}',
                section='errors')
            except Exception:
              pass
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

  def fetch_and_parse_recipe(self, recipe, import_options=None, cache=None):
    import_options = import_options or {}
    source_choice = import_options.get('source_choice', 'automatic')
    if bool(import_options.get('disable_fallbacks', False)):
      source_choice = 0
    try:
      fetch_kwargs = {
        'sleep': lambda seconds, message: self.sleep_with_events(seconds, message),
        'fetch_error': lambda url, err, entry: self.debug_recipe_linked_page_failed(url, err, entry),
        'log': lambda message: self.debug_parser_message(message),
        'progress': lambda done, total, message: self.update_import_fetch_progress(done, total, message),
        'force_fallback_level': int(prefs.get('debug_force_fallback_level', 0) or 0),
        'disable_fallbacks': bool(import_options.get('disable_fallbacks', False)),
        'source_choice': source_choice,
        'before_fetch': lambda url: (
          self.debug_recipe_fetch_url(url),
          self.update_import_progress(message=f'Fetching "{recipe.NAME}"...')),
        'after_fetch': lambda url, html: self.debug_recipe_fetched(url, html),
        'before_parse': lambda _url: self.update_import_progress(message=f'Parsing "{recipe.NAME}"...'),
      }
      if cache is not None:
        # Only opt-in incremental recipes receive the expanded parser contract;
        # older custom fetchers retain their existing fetch_and_parse signature.
        fetch_kwargs['cached_parsed'] = cache
        fetch_kwargs['incremental_update'] = True
      return recipe.fetch_and_parse(
        self.fetch_url,
        **fetch_kwargs)
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
    matched, missing_entries, review_rows = self.match_imported_entries(
      entries,
      match_series=match_series,
      list_id=parsed.get('list_id'),
      allow_goodreads_recovery=allow_goodreads_recovery,
      award_winners_only=award_winners_only,
      return_details=True)
    self.debug_import_summary(matched, missing_entries, entries)

    self.update_import_progress(IMPORT_MATCH_PROGRESS_MAX, 'Preparing import review...')
    review_rows, reconciliation_notes = self.reconcile_review_rows_with_active_list(
      list_name, review_rows, active_name=active)
    if reconciliation_notes:
      notes = list(parsed.get('notes') or [])
      notes.extend(reconciliation_notes)
      parsed = dict(parsed)
      parsed['notes'] = notes
    matched_entry_count = self.import_review_matched_entry_count(review_rows)
    matched, missing_entries, review_rows = self.accepted_import_review_rows(review_rows)
    self.close_import_progress()
    review = self.review_import_matches(
      list_name, parsed.get('list_id'), matched_entry_count, len(entries),
      missing_entries, review_rows, notes=parsed.get('notes'),
      match_series=match_series, allow_goodreads_recovery=allow_goodreads_recovery,
      list_source_url=parsed_list_source_url(parsed))
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

  def manage_active_list_review(self):
    if not self.ensure_configured():
      return
    active = self.current_active()
    if not active:
      raise ListSwitchboardError('Create an Active List before managing imported-list matches.')
    cache = self.import_cache_for_active_list(active)
    if not cache:
      raise ListSwitchboardError(
        f'No cached imported list was found for the current Active List "{active}". '
        'Import that list before managing matches.')

    parsed = self.cached_import_to_parsed(cache)
    list_name = validate_list_name(parsed.get('name') or active)
    entries = parsed.get('entries') or []
    if not entries:
      raise ListSwitchboardError('The cached imported list did not contain any entries.')
    list_id = parsed.get('list_id') or cache.get('list_id') or self.safe_list_id(list_name)
    match_series = parsed.get('match_series', True)
    matched, missing_entries, review_rows = self.match_imported_entries(
      entries,
      match_series=match_series,
      list_id=list_id,
      allow_goodreads_recovery=False,
      return_details=True)
    review_rows, reconciliation_notes = self.reconcile_review_rows_with_active_list(
      list_name, review_rows, active_name=active)
    notes = list(parsed.get('notes') or [])
    notes.extend(reconciliation_notes)
    matched_entry_count = self.import_review_matched_entry_count(review_rows)
    matched, missing_entries, review_rows = self.accepted_import_review_rows(review_rows)
    review = self.review_import_matches(
      list_name, list_id, matched_entry_count, len(entries), missing_entries,
      review_rows, notes=notes, match_series=match_series,
      allow_goodreads_recovery=False,
      list_source_url=parsed_list_source_url(parsed))
    if review is None:
      return
    matched, _missing_entries, _review_rows = review
    self.write_active_review_matches(list_name, entries, matched)

  def write_active_review_matches(self, list_name, entries, matched):
    reviewed_positions = {
      self.normalized_position_text(entry.get('position', ''))
      for entry in entries or []
      if self.normalized_position_text(entry.get('position', ''))
    }
    active_book_ids = set(self.active_book_ids_for_list(list_name))
    active_positions = self.active_review_positions_by_book(active_book_ids)
    active_updates = {}
    index_updates = {}
    matched = matched or {}
    matched_book_ids = set(matched)
    for book_id, position in active_positions.items():
      if position in reviewed_positions and book_id not in matched_book_ids:
        active_updates[book_id] = ''
    for book_id, position in matched.items():
      active_updates[book_id] = list_name
      try:
        index_updates[book_id] = float(position)
      except Exception:
        pass
    if not active_updates:
      self.status_message(f'No Active List changes needed for "{list_name}".')
      return
    self.write_fields_with_progress(
      'Manage Active List',
      f'Updating Active List "{list_name}"...',
      active_updates=active_updates,
      active_index_updates=index_updates,
      finishing_message=f'Updated Active List "{list_name}".')
    self.status_message(f'Updated Active List "{list_name}".')

  def current_active_list_position_problems(self):
    if not self.ensure_configured():
      return []
    active = self.current_active()
    if not active:
      raise ListSwitchboardError('Create an Active List before showing position problems.')
    cache = self.import_cache_for_active_list(active)
    if not cache:
      raise ListSwitchboardError(
        f'No cached imported list was found for the current Active List "{active}". '
        'Import that list before showing position problems.')
    parsed = self.cached_import_to_parsed(cache)
    recipe_positions = {
      self.normalized_position_text(entry.get('position', ''))
      for entry in parsed.get('entries') or []
      if self.normalized_position_text(entry.get('position', ''))
    }
    active_book_ids = set(self.active_book_ids_for_list(active))
    active_positions = self.active_review_positions_by_book(active_book_ids)
    details = self.review_book_details(active_book_ids)
    problems = []
    for book_id, position in sorted(
        active_positions.items(),
        key=lambda item: self.position_problem_sort_key(item[1], item[0])):
      if position in recipe_positions:
        continue
      detail = details.get(book_id) or {}
      problems.append({
        'book_id': book_id,
        'position': position,
        'title': detail.get('matched_title') or '',
        'author': detail.get('matched_authors') or '',
      })
    return problems

  def position_problem_sort_key(self, position, book_id):
    try:
      position_key = float(position)
    except Exception:
      position_key = float('inf')
    return position_key, str(position), book_id

  def reconcile_review_rows_with_active_list(self, list_name, review_rows, active_name=None):
    rows = list(review_rows or [])
    if not rows:
      return rows, []
    if active_name is None:
      active_name = self.current_active()
    if not active_name or normalize_key(active_name) != normalize_key(list_name):
      return rows, []

    try:
      active_book_ids = set(self.active_book_ids_for_list(list_name))
    except AttributeError:
      return rows, []
    rows_by_position = {}
    for row in rows:
      position = self.normalized_position_text(
        row.get('imported_position', '') or (row.get('entry') or {}).get('position', ''))
      if position:
        rows_by_position.setdefault(position, []).append(row)

    book_to_row = {}
    for row in rows:
      for book_id in row.get('book_ids') or []:
        book_to_row[book_id] = row

    for row in rows:
      if row.get('ignored') or not row.get('matched'):
        continue
      if self.review_row_match_is_automatic(row):
        continue
      missing_book_ids = [
        book_id for book_id in (row.get('book_ids') or [])
        if book_id not in active_book_ids
      ]
      if not missing_book_ids:
        continue
      self.remember_review_row_previous_match(row)
      remaining = [
        book_id for book_id in (row.get('book_ids') or [])
        if book_id in active_book_ids
      ]
      if remaining:
        row['book_ids'] = remaining
        row['matched_books'] = [
          book for book in (row.get('matched_books') or [])
          if book.get('matched_book_id') in set(remaining)
        ]
        continue
      self.clear_review_row_match(row)

    notes = []
    unknown_position_count = 0
    active_positions = self.active_review_positions_by_book(active_book_ids)
    book_details = self.review_book_details(active_book_ids)
    for book_id, position in active_positions.items():
      target_rows = rows_by_position.get(position, [])
      if not target_rows:
        unknown_position_count += 1
        continue
      target_row = self.active_position_target_row(book_id, target_rows, book_details)
      if target_row.get('ignored'):
        continue
      current_row = book_to_row.get(book_id)
      if current_row is target_row and book_id in (target_row.get('book_ids') or []):
        continue
      if (
          current_row is not None
          and self.review_row_match_is_automatic(current_row)
          and current_row is not target_row
          and self.review_row_match_is_automatic(target_row)):
        continue
      if current_row is not None and current_row is not target_row:
        self.remove_book_from_review_row(current_row, book_id)
      self.add_active_manual_match_to_review_row(target_row, book_id, book_details)
      book_to_row[book_id] = target_row

    if unknown_position_count:
      notes.append(
        f'{unknown_position_count} current Active List book(s) use positions not found in the imported recipe.')
    return rows, notes

  def review_row_match_is_automatic(self, row):
    return row.get('matched') and row.get('match_source') == 'automatic'

  def active_review_positions_by_book(self, active_book_ids):
    positions = {}
    index_field = self.active_series_index_field()
    for book_id in active_book_ids:
      position, _numeric_position = self.read_position_display(
        index_field, book_id, self.read_field(prefs['active_list_field'], book_id))
      position = self.normalized_position_text(position)
      if position:
        positions[book_id] = position
    return positions

  def review_book_details(self, book_ids):
    db = self.db.new_api
    book_ids = list(book_ids or [])
    titles = db.all_field_for('title', book_ids, default_value='')
    authors = db.all_field_for('authors', book_ids, default_value='')
    return {
      detail.get('matched_book_id'): detail
      for detail in self.matched_book_details(book_ids, titles, authors)
    }

  def active_position_target_row(self, book_id, rows, book_details):
    for row in rows:
      if book_id in (row.get('book_ids') or []):
        return row
    detail = book_details.get(book_id) or {}
    for row in rows:
      entry = row.get('entry') or {}
      if entry.get('title') and detail.get('matched_title'):
        if normalize_key(entry.get('title')) != normalize_key(detail.get('matched_title')):
          continue
      imported_author = imported_author_search_text(entry)
      if imported_author and detail.get('matched_authors'):
        if not self.author_matches(detail.get('matched_authors'), imported_author):
          continue
      return row
    return rows[0]

  def remember_review_row_previous_match(self, row):
    row['previous_book_ids'] = list(
      row.get('previous_book_ids') or row.get('book_ids') or row.get('original_book_ids') or [])
    row['previous_matched_books'] = list(
      row.get('previous_matched_books')
      or row.get('matched_books') or row.get('original_matched_books') or [])
    row['previous_match_source'] = (
      row.get('previous_match_source')
      or row.get('match_source')
      or row.get('original_match_source')
      or '')
    row['can_toggle_on'] = True

  def clear_review_row_match(self, row):
    row['matched'] = False
    row['ignored'] = False
    row['book_ids'] = []
    row['matched_books'] = []
    row['match_source'] = 'never matched'
    row['can_toggle_on'] = True

  def remove_book_from_review_row(self, row, book_id):
    if book_id not in (row.get('book_ids') or []):
      return
    self.remember_review_row_previous_match(row)
    row['book_ids'] = [
      existing_id for existing_id in (row.get('book_ids') or [])
      if existing_id != book_id
    ]
    row['matched_books'] = [
      book for book in (row.get('matched_books') or [])
      if book.get('matched_book_id') != book_id
    ]
    if not row['book_ids']:
      self.clear_review_row_match(row)

  def add_active_manual_match_to_review_row(self, row, book_id, book_details):
    if book_id not in (row.get('book_ids') or []):
      row.setdefault('book_ids', []).append(book_id)
    detail = book_details.get(book_id)
    if detail:
      matched_books = [
        book for book in (row.get('matched_books') or [])
        if book.get('matched_book_id') != book_id
      ]
      matched_books.append(detail)
      row['matched_books'] = matched_books
    row['matched'] = True
    row['ignored'] = False
    row['match_source'] = 'active list/manual edit'
    row['can_toggle_on'] = True

  def review_import_matches(
      self, list_name, list_id, matched_count, entries_count, missing_entries,
      review_rows, notes=None, match_series=True, allow_goodreads_recovery=True,
      list_source_url=''):
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
        find_match_index_callback=lambda **kwargs: self.find_match_library_index(
          match_series=match_series, **kwargs),
        find_match_callback=lambda review_rows, settings, index=None: self.find_matches_for_review_rows(
          review_rows, settings, index=index, match_series=match_series),
        view_book_callback=self.open_book_detail_window,
        author_display_formatter=self.display_authors,
        list_source_url=list_source_url,
        selected_match_source_callback=lambda row, candidate: self.review_match_source_for_candidate(
          row.get('entry') or {}, candidate.get('book_id', candidate.get('matched_book_id')),
          list_id=list_id, match_series=match_series,
          allow_goodreads_recovery=allow_goodreads_recovery))
    except TypeError as err:
      if (
          'find_match_settings' not in str(err)
          and 'find_match_index_callback' not in str(err)
          and 'view_book_callback' not in str(err)
          and 'author_display_formatter' not in str(err)
          and 'list_source_url' not in str(err)):
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

  def open_book_detail_window(self, book_id, parent=None):
    gui = getattr(self, 'gui', None)
    if gui is None or book_id is None:
      return False
    if self.open_modal_book_info(book_id, focus_parent=parent):
      return True
    for method_name in ('show_book_info', 'show_book_details', 'show_book_details_window'):
      method = getattr(gui, method_name, None)
      if self.call_book_detail_method(method, book_id):
        return True
    iactions = getattr(gui, 'iactions', {}) or {}
    for key in ('Show Book Details', 'Book Details'):
      action = iactions.get(key) if hasattr(iactions, 'get') else None
      if action is None:
        continue
      for method_name in ('show_book_info', 'show_book_details', 'show_book_details_window'):
        method = getattr(action, method_name, None)
        if self.call_book_detail_method(method, book_id):
          return True
    library_view = getattr(gui, 'library_view', None)
    select_rows = getattr(library_view, 'select_rows', None)
    if callable(select_rows):
      select_rows([book_id])
    return False

  def call_book_detail_method(self, method, book_id):
    if not callable(method):
      return False
    try:
      method(book_id=book_id)
      return True
    except TypeError as err:
      if 'book_id' not in str(err) and 'keyword' not in str(err):
        raise
    return False

  def open_modal_book_info(self, book_id, focus_parent=None):
    gui = getattr(self, 'gui', None)
    try:
      from calibre.gui2.dialogs.book_info import BookInfo, DialogNumbers
    except Exception:
      return False
    library_view = getattr(gui, 'library_view', None)
    if library_view is None:
      return False
    book_details = getattr(gui, 'book_details', None)
    link_delegate = getattr(book_details, 'handle_click_from_popup', None)
    if link_delegate is None:
      link_delegate = lambda *_args, **_kwargs: None
    index = self.library_index_for_book_id(book_id)
    try:
      dialog = BookInfo(
        gui, library_view, index, link_delegate,
        dialog_number=DialogNumbers.Locked, book_id=book_id)
    except Exception:
      return False
    open_cover_with = getattr(dialog, 'open_cover_with', None)
    bd_open_cover_with = getattr(gui, 'bd_open_cover_with', None)
    connect = getattr(open_cover_with, 'connect', None)
    if callable(connect) and bd_open_cover_with is not None:
      try:
        connect(bd_open_cover_with)
      except Exception:
        pass
    try:
      dialog.exec()
    finally:
      self.refocus_dialog_parent(focus_parent)
    return True

  def library_index_for_book_id(self, book_id):
    gui = getattr(self, 'gui', None)
    library_view = getattr(gui, 'library_view', None)
    model = library_view.model() if library_view is not None else None
    current_index = None
    try:
      current_index = library_view.currentIndex()
      if current_index is not None and current_index.isValid():
        if model.id(current_index) == book_id:
          return current_index
    except Exception:
      pass
    try:
      for row in range(model.rowCount()):
        index = model.index(row, 0)
        if model.id(index) == book_id:
          return index
    except Exception:
      pass
    return current_index

  def refocus_dialog_parent(self, focus_parent):
    if focus_parent is None:
      return
    for method_name in ('raise_', 'activateWindow', 'setFocus'):
      method = getattr(focus_parent, method_name, None)
      if callable(method):
        try:
          method()
        except Exception:
          pass

  def find_matches_for_review_rows(self, review_rows, settings, index=None, match_series=False):
    matched_book_ids = set()
    for row in review_rows or []:
      if row.get('matched'):
        matched_book_ids.update(row.get('book_ids') or [])
    if index is None:
      index = self.find_match_library_index(
        title_mode=settings.get('title_mode', 'similar'),
        author_mode=settings.get('author_mode', 'similar'),
        title_soundex_length=settings.get('title_soundex_length', 6),
        author_soundex_length=settings.get('author_soundex_length', 8),
        match_series=match_series)
    for row in review_rows or []:
      if row.get('matched'):
        continue
      excluded = matched_book_ids | set(row.get('book_ids') or [])
      row['possible_matches'] = self.find_import_match_candidates_from_index(
        row.get('entry') or {
          'title': row.get('imported_title', ''),
          'authors': row.get('imported_author', []),
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

  def import_review_matched_entry_count(self, review_rows):
    return sum(1 for row in (review_rows or []) if row.get('matched'))

  def show_import_report(
      self, list_name, matched_count, entries_count, missing_entries,
      allow_deep_recovery=True, matched_book_ids=None, notes=None,
      match_series=True, list_source_url=''):
    self.debug_import_missing_entries(missing_entries)
    d = ImportReportDialog(
      self.gui, list_name, matched_count, entries_count, missing_entries,
      allow_deep_recovery=allow_deep_recovery, notes=notes,
      author_display_formatter=self.display_authors,
      list_source_url=list_source_url)
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
