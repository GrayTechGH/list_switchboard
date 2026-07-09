#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

import csv
from io import StringIO

from qt.core import (
  QApplication, QComboBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout,
  QHeaderView, QLabel, QPushButton, QSizePolicy, QTableWidget,
  QTableWidgetItem, QUrl, QVBoxLayout
)

from calibre.gui2 import error_dialog, safe_open_url

try:
  from calibre_plugins.list_switchboard.dialogs.import_find import (
    FindModeDialog, MatchReviewDialog,
  )
except ImportError:
  from dialogs.import_find import FindModeDialog, MatchReviewDialog

try:
  from calibre_plugins.list_switchboard.matching import imported_author_display_value
except ImportError:
  from matching import imported_author_display_value

try:
  from calibre_plugins.list_switchboard.matching import imported_entry_source_url
except ImportError:
  from matching import imported_entry_source_url


VIEW_ALL = 'All'
VIEW_MATCHED = 'Matched'
VIEW_UNMATCHED = 'Unmatched'
VIEW_IGNORED = 'Ignored'
AWARD_FILTER_ALL = 'All'
AWARD_FILTER_WINNERS = 'Winners only'
AWARD_FILTER_NOMINEES = 'Nominees only'

IMPORT_REVIEW_HEADERS = [
  'Position', 'Title', 'Author', 'ID', 'Match', 'Source',
]
IMPORT_REVIEW_ID_COLUMN = 3
IMPORT_REVIEW_FIXED_COLUMNS = (0, 3, 4, 5)
IMPORT_REVIEW_STRETCH_COLUMNS = (1, 2)
IMPORT_REVIEW_FIXED_COLUMN_PADDING = 28
IMPORT_REVIEW_ID_WIDTH_FACTOR = 1.75


class ImportReportDialog(QDialog):
  """
  Import review dialog for entry-to-library matches.

  Refactor warning:
  - This dialog is intentionally being rebuilt from the management dialog's
    list/table/action pattern. Keep the imported entry as the primary row; the
    selected Calibre library match is row data, not the other way around.
  """

  def __init__(
      self, parent, list_name, matched_count=0, entries_count=0,
      missing_entries=None, allow_deep_recovery=False, notes=None,
      review_rows=None, find_match_settings=None, save_find_match_settings=None,
      find_match_index_callback=None, find_match_callback=None, view_book_callback=None,
      selected_match_source_callback=None, author_display_formatter=None,
      list_source_url=''):
    QDialog.__init__(self, parent)
    self.list_name = list_name
    self.author_display_formatter = author_display_formatter
    self.list_source_url = str(list_source_url or '').strip()
    self.review_rows = [
      self.normalized_review_row(row) for row in (review_rows or [])
    ]
    if not self.review_rows:
      self.review_rows = [
        self.normalized_review_row({'entry': entry, 'match_source': 'never matched'})
        for entry in (missing_entries or [])
      ]
    self.visible_rows = []
    self.find_match_settings = dict(find_match_settings or {})
    self.save_find_match_settings = save_find_match_settings
    self.find_match_index_callback = find_match_index_callback
    self.find_match_callback = find_match_callback
    self.find_match_index = None
    self.find_match_index_settings = None
    self.view_book_callback = view_book_callback
    self.selected_match_source_callback = selected_match_source_callback
    self.deep_recovery_requested = False
    self.setWindowTitle('Import List Review')
    notes = [note for note in (notes or []) if note]
    note_text = '\n' + '\n'.join(notes) if notes else ''

    layout = QVBoxLayout()
    self.setLayout(layout)
    summary = QLabel(
      f'Review "{list_name}" before writing it as the Active List.\n'
      f'Matched {matched_count} of {entries_count} recipe entries.'
      f'{note_text}',
      self)
    summary.setWordWrap(True)
    summary.setSizePolicy(self.ignored_width_size_policy())
    layout.addWidget(summary)

    view_layout = QHBoxLayout()
    view_layout.addWidget(QLabel('View:', self))
    self.view_combo = QComboBox(self)
    self.view_combo.addItems([VIEW_ALL, VIEW_MATCHED, VIEW_UNMATCHED, VIEW_IGNORED])
    self.view_combo.setCurrentText(VIEW_UNMATCHED)
    view_layout.addWidget(self.view_combo)
    view_layout.addSpacing(12)
    view_layout.addWidget(QLabel('Award:', self))
    self.award_filter_combo = QComboBox(self)
    self.award_filter_combo.addItems([
      AWARD_FILTER_ALL, AWARD_FILTER_WINNERS, AWARD_FILTER_NOMINEES,
    ])
    view_layout.addWidget(self.award_filter_combo)
    view_layout.addStretch(1)
    layout.addLayout(view_layout)

    self.toggle_button = QPushButton('Toggle match', self)
    self.view_source_button = QPushButton('View source', self)
    self.find_button = QPushButton('Find match', self)
    self.match_mode_button = QPushButton('Match mode', self)

    self.match_table = QTableWidget(self)
    self.match_table.setColumnCount(6)
    self.match_table.setHorizontalHeaderLabels(IMPORT_REVIEW_HEADERS)
    self.match_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    self.match_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    self.configure_table_column_resizing()
    layout.addWidget(self.match_table)

    action_layout = QGridLayout()
    action_layout.addWidget(self.toggle_button, 0, 0)
    action_layout.addWidget(self.view_source_button, 1, 0)
    action_layout.addWidget(self.find_button, 0, 1)
    action_layout.addWidget(self.match_mode_button, 0, 2)
    self.copy_button = QPushButton('Copy view', self)
    action_layout.addWidget(self.copy_button, 0, 3)
    if allow_deep_recovery and missing_entries:
      self.deep_recovery_button = QPushButton('Try Deep Recovery', self)
      self.deep_recovery_button.setEnabled(False)
      action_layout.addWidget(self.deep_recovery_button, 0, 4)
    layout.addLayout(action_layout)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
    buttons.accepted.connect(self.accept)
    buttons.rejected.connect(self.reject)
    layout.addWidget(buttons)

    self.view_combo.currentTextChanged.connect(self.update_table)
    self.award_filter_combo.currentTextChanged.connect(self.update_table)
    self.match_table.currentCellChanged.connect(self.update_toggle_button)
    self.match_table.itemSelectionChanged.connect(self.update_toggle_button)
    self.toggle_button.clicked.connect(self.toggle_selected_match)
    self.view_source_button.clicked.connect(self.open_selected_source)
    self.find_button.clicked.connect(self.open_find_matches)
    self.match_mode_button.clicked.connect(self.open_match_mode)
    self.copy_button.clicked.connect(self.copy_current_view)
    self.update_table()
    self.resize(*self.initial_report_size())

  def normalized_review_row(self, row):
    row = dict(row or {})
    entry = row.get('entry') or {}
    row['entry'] = entry
    row.setdefault('imported_position', entry.get('position', ''))
    row.setdefault('imported_title', entry.get('title', ''))
    row.setdefault('imported_author', imported_author_display_value(entry))
    row.setdefault('matched', False)
    row.setdefault('original_matched', bool(row.get('matched')))
    row.setdefault('ignored', False)
    row.setdefault('original_ignored', bool(row.get('ignored')))
    row.setdefault('book_ids', [])
    row.setdefault('original_book_ids', list(row.get('book_ids') or []))
    row.setdefault('matched_books', [])
    row.setdefault('original_matched_books', list(row.get('matched_books') or []))
    row.setdefault('previous_book_ids', [])
    row.setdefault('previous_matched_books', [])
    row.setdefault('previous_match_source', row.get('original_match_source', ''))
    row.setdefault('match_source', 'never matched')
    row.setdefault('original_match_source', row.get('match_source', 'never matched'))
    row.setdefault(
      'can_toggle_on',
      bool(row.get('matched') or row.get('previous_book_ids') or row.get('ignored')))
    row.setdefault('possible_matches', [])
    return row

  def initial_report_size(self):
    width = 980
    height = 560
    try:
      screen = QApplication.primaryScreen()
      if screen is not None:
        available = screen.availableGeometry()
        width = min(width, max(520, int(available.width() * 0.9)))
    except Exception:
      pass
    return width, height

  def ignored_width_size_policy(self):
    try:
      return QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    except Exception:
      return QSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

  def current_view_mode(self):
    try:
      return self.view_combo.currentText()
    except Exception:
      return VIEW_UNMATCHED

  def rows_for_current_view(self):
    return [
      row for row in self.review_rows
      if self.row_matches_view_filter(row) and self.row_matches_award_filter(row)
    ]

  def current_award_filter_mode(self):
    try:
      return self.award_filter_combo.currentText()
    except Exception:
      return AWARD_FILTER_ALL

  def row_matches_view_filter(self, row):
    mode = self.current_view_mode()
    if mode == VIEW_MATCHED:
      return bool(row.get('matched'))
    if mode == VIEW_UNMATCHED:
      return not row.get('matched') and not row.get('ignored')
    if mode == VIEW_IGNORED:
      return bool(row.get('ignored'))
    return True

  def view_mode_for_row(self, row):
    if row is None:
      return VIEW_UNMATCHED
    if row.get('ignored'):
      return VIEW_IGNORED
    if row.get('matched'):
      return VIEW_MATCHED
    return VIEW_UNMATCHED

  def row_award_result(self, row):
    entry = row.get('entry') or {}
    return str(entry.get('result', '') or '').casefold()

  def row_matches_award_filter(self, row):
    mode = self.current_award_filter_mode()
    if mode == AWARD_FILTER_WINNERS:
      return self.row_award_result(row) == 'winner'
    if mode == AWARD_FILTER_NOMINEES:
      return self.row_award_result(row) != 'winner'
    return True

  def update_table(self, *_args):
    selected_row = self.selected_review_row()
    self.update_table_for_row(selected_row)

  def update_table_for_row(self, selected_row=None):
    self.visible_rows = self.rows_for_current_view()
    self.match_table.setRowCount(len(self.visible_rows))
    for row_index, row in enumerate(self.visible_rows):
      display_values = self.display_values_for_row(row)
      for column, value in enumerate(display_values):
        item = QTableWidgetItem(value)
        tooltip = self.tooltip_for_table_cell(row, column)
        if tooltip:
          item.setToolTip(tooltip)
        self.match_table.setItem(row_index, column, item)
    if selected_row in self.visible_rows:
      self.select_review_row(selected_row)
    elif self.visible_rows:
      self.match_table.setCurrentCell(0, 0)
    self.apply_stable_fixed_column_widths()
    self.update_toggle_button()

  def configure_table_column_resizing(self):
    header = self.match_table.horizontalHeader()
    fixed_mode = self.header_resize_mode('Fixed')
    stretch_mode = self.header_resize_mode('Stretch')
    for column in IMPORT_REVIEW_FIXED_COLUMNS:
      header.setSectionResizeMode(column, fixed_mode)
    for column in IMPORT_REVIEW_STRETCH_COLUMNS:
      header.setSectionResizeMode(column, stretch_mode)

  def header_resize_mode(self, mode_name):
    try:
      return getattr(QHeaderView.ResizeMode, mode_name)
    except AttributeError:
      return getattr(QHeaderView, mode_name)

  def stable_width_rows(self):
    matched_rows = [row for row in self.review_rows if row.get('matched')]
    possible_rows = [
      row for row in self.review_rows
      if not row.get('matched') and row.get('possible_matches')
    ]
    return matched_rows + possible_rows or list(self.review_rows)

  def fixed_column_width_values(self, column):
    values = [IMPORT_REVIEW_HEADERS[column]]
    values.extend(
      self.display_values_for_row(row)[column] for row in self.stable_width_rows()
    )
    return values

  def apply_stable_fixed_column_widths(self):
    metrics = self.match_table.fontMetrics()
    for column in IMPORT_REVIEW_FIXED_COLUMNS:
      width = max(
        self.text_width(metrics, value)
        for value in self.fixed_column_width_values(column)
      )
      if column == IMPORT_REVIEW_ID_COLUMN:
        width = min(width, self.max_id_column_content_width(metrics))
      self.match_table.setColumnWidth(column, width + IMPORT_REVIEW_FIXED_COLUMN_PADDING)

  def max_id_column_content_width(self, metrics):
    single_id_widths = [self.text_width(metrics, IMPORT_REVIEW_HEADERS[IMPORT_REVIEW_ID_COLUMN])]
    for row in self.stable_width_rows():
      single_id_widths.extend(
        self.text_width(metrics, book_id)
        for book_id in self.book_id_text_values(row)
      )
    return int(max(single_id_widths) * IMPORT_REVIEW_ID_WIDTH_FACTOR)

  def text_width(self, metrics, value):
    text = str(value or '')
    try:
      return metrics.horizontalAdvance(text)
    except AttributeError:
      return metrics.boundingRect(text).width()

  def selected_review_row(self):
    if not self.table_has_selection():
      return None
    row = self.match_table.currentRow()
    if row < 0 or row >= len(self.visible_rows):
      return None
    return self.visible_rows[row]

  def table_has_selection(self):
    selection_model = getattr(self.match_table, 'selectionModel', None)
    if not callable(selection_model):
      return True
    selection_model = selection_model()
    has_selection = getattr(selection_model, 'hasSelection', None)
    if not callable(has_selection):
      return True
    return bool(has_selection())

  def update_toggle_button(self, *_args):
    row = self.selected_review_row()
    view_source_button = getattr(self, 'view_source_button', None)
    if row is None:
      self.toggle_button.setEnabled(False)
      if view_source_button is not None:
        view_source_button.setEnabled(bool(self.list_source_url))
      return
    self.toggle_button.setEnabled(True)
    if view_source_button is not None:
      view_source_button.setEnabled(bool(self.source_url_for_row(row)))

  def source_url_for_row(self, row):
    entry = (row or {}).get('entry') or {}
    return (
      str(imported_entry_source_url(entry) or '').strip()
      or self.list_source_url
    )

  def open_selected_source(self):
    url = self.source_url_for_row(self.selected_review_row())
    if not url:
      return
    safe_open_url(QUrl(url))

  def toggle_selected_match(self):
    row = self.selected_review_row()
    if row is None:
      return
    if row.get('matched'):
      row['previous_book_ids'] = list(row.get('book_ids') or [])
      row['previous_matched_books'] = list(row.get('matched_books') or [])
      row['previous_match_source'] = row.get('match_source', '')
      row['matched'] = False
      row['ignored'] = False
      row['book_ids'] = []
      row['matched_books'] = []
      row['match_source'] = 'never matched'
      row['can_toggle_on'] = True
    elif row.get('ignored'):
      if row.get('previous_book_ids'):
        row['matched'] = True
        row['ignored'] = False
        row['book_ids'] = list(row.get('previous_book_ids') or [])
        row['matched_books'] = list(row.get('previous_matched_books') or [])
        row['match_source'] = row.get('previous_match_source') or 'automatic'
        row['can_toggle_on'] = True
      else:
        row['matched'] = False
        row['ignored'] = False
        row['match_source'] = 'never matched'
        row['can_toggle_on'] = True
    else:
      row['matched'] = False
      row['ignored'] = True
      row['book_ids'] = []
      row['matched_books'] = []
      row['match_source'] = 'ignored'
      row['can_toggle_on'] = True
    self.update_table_for_row(row)

  def matched_books_text(self, row, field):
    values = []
    for book in row.get('matched_books') or []:
      value = book.get(field, '')
      if field in ('matched_authors', 'authors'):
        value = self.display_authors(value)
      elif isinstance(value, (list, tuple)):
        value = ', '.join(str(item) for item in value)
      if value:
        values.append(str(value))
    return '; '.join(values)

  def display_authors(self, value):
    if self.author_display_formatter is not None:
      try:
        return self.author_display_formatter(value)
      except Exception:
        pass
    if isinstance(value, (list, tuple)):
      return ', '.join(str(item) for item in value)
    return str(value or '')

  def book_id_text_values(self, row):
    return [str(book_id) for book_id in (row.get('book_ids') or [])]

  def book_ids_full_text(self, row):
    return '; '.join(self.book_id_text_values(row))

  def book_ids_display_text(self, row):
    book_ids = self.book_id_text_values(row)
    if len(book_ids) <= 1:
      return self.book_ids_full_text(row)
    return f'{book_ids[0]}; +{len(book_ids) - 1} more'

  def display_values_for_row(self, row):
    values = list(self.csv_values_for_row(row))
    values[IMPORT_REVIEW_ID_COLUMN] = self.book_ids_display_text(row)
    return values

  def tooltip_for_table_cell(self, row, column):
    if column != IMPORT_REVIEW_ID_COLUMN:
      return ''
    full_text = self.book_ids_full_text(row)
    display_text = self.book_ids_display_text(row)
    return full_text if full_text != display_text else ''

  def csv_values_for_row(self, row):
    match = 'Yes' if row.get('matched') else 'No'
    if row.get('ignored'):
      match = 'Ignored'
    elif not row.get('matched') and row.get('possible_matches'):
      match = f'Possible ({len(row.get("possible_matches") or [])})'
    source = str(row.get('match_source', '') or '')
    if source in ('never matched', 'explicit unmatched'):
      source = 'None'
    elif source == 'ignored':
      source = 'Ignored'
    return [
      str(row.get('imported_position', '') or ''),
      str(row.get('imported_title', '') or ''),
      self.display_authors(row.get('imported_author', '')),
      self.book_ids_full_text(row),
      match,
      source,
    ]

  def unmatched_review_rows(self):
    return [row for row in self.review_rows if not row.get('matched')]

  def candidate_review_rows(self):
    return [
      row for row in self.review_rows
      if not row.get('matched') and row.get('possible_matches')
    ]

  def select_review_row(self, target_row):
    if target_row is None:
      return
    if target_row not in self.rows_for_current_view():
      try:
        self.view_combo.setCurrentText(self.view_mode_for_row(target_row))
      except Exception:
        pass
      self.update_table_for_row(target_row)
    for row_index, row in enumerate(self.visible_rows):
      if row is target_row:
        self.match_table.setCurrentCell(row_index, 0)
        return

  def candidate_row_from(self, row=None, direction=1, include_start=True):
    candidates = self.candidate_review_rows()
    if not candidates:
      return None
    if row is None:
      return candidates[0]
    try:
      start_index = self.review_rows.index(row)
    except ValueError:
      return candidates[0]
    if include_start and row in candidates:
      return row
    step = 1 if direction >= 0 else -1
    count = len(self.review_rows)
    for offset in range(1, count + 1):
      candidate = self.review_rows[(start_index + (offset * step)) % count]
      if candidate in candidates:
        return candidate
    return None

  def show_find_notice(self, message):
    error_dialog(self, 'Find match', message, show=True)

  def open_match_mode(self):
    dialog = FindModeDialog(self, self.find_match_settings)
    if dialog.exec() != QDialog.Accepted:
      return
    settings = dialog.selected_mode()
    if dict(settings) != self.find_match_settings:
      self.find_match_index = None
      self.find_match_index_settings = None
      for row in self.review_rows:
        row['possible_matches'] = []
    self.find_match_settings = dict(settings)
    if self.save_find_match_settings is not None:
      self.save_find_match_settings(settings)

  def open_find_matches(self):
    selected_row = self.selected_review_row()
    if not self.candidate_review_rows():
      self.run_find_matches(self.review_rows)
      self.update_table()
      if not self.candidate_review_rows():
        self.show_find_notice(
          'No possible matches were found. Change Match mode to use different criteria.')
        return
    row = self.candidate_row_from(selected_row, include_start=True)
    if row is None:
      self.show_find_notice(
        'There are no possible matches left. Change Match mode to find more candidates.')
      return
    self.review_candidate_rows(row)
    self.update_table_for_row(self.selected_review_row())

  def run_find_matches(self, rows):
    if self.find_match_callback is None:
      return rows
    index = self.current_find_match_index()
    try:
      self.find_match_callback(self.review_rows, self.find_match_settings, index=index)
    except TypeError as err:
      if 'index' not in str(err):
        raise
      self.find_match_callback(self.review_rows, self.find_match_settings)
    return rows

  def current_find_match_index(self):
    settings = dict(self.find_match_settings)
    if self.find_match_index is not None and self.find_match_index_settings == settings:
      return self.find_match_index
    if self.find_match_index_callback is None:
      return None
    self.find_match_index = self.find_match_index_callback(
      title_mode=settings.get('title_mode', 'similar'),
      author_mode=settings.get('author_mode', 'similar'),
      title_soundex_length=settings.get('title_soundex_length', 6),
      author_soundex_length=settings.get('author_soundex_length', 8))
    self.find_match_index_settings = settings
    return self.find_match_index

  def review_candidate_rows(self, start_row):
    current = {'row': start_row}
    dialog = {'value': None}

    def set_current_row(row):
      current['row'] = row
      self.select_review_row(row)
      dialog['value'].set_review_row(row)

    def close_when_done():
      try:
        dialog['value'].accept_dialog()
      except Exception:
        pass
      self.show_find_notice(
        'There are no possible matches left. Change Match mode to find more candidates.')

    def match_selected(candidate):
      row = current.get('row')
      if row is None:
        return
      self.apply_manual_find_match(row, candidate)
      self.update_table_for_row(row)
      move_after_choice(row)

    def ignore_current():
      row = current.get('row')
      if row is None:
        return
      self.apply_ignore_match(row)
      self.update_table_for_row(row)
      move_after_choice(row)

    def move_after_choice(row):
      next_row = self.candidate_row_from(row, direction=1, include_start=False)
      if next_row is None:
        close_when_done()
        return
      set_current_row(next_row)

    def move(direction):
      row = current.get('row')
      next_row = self.candidate_row_from(row, direction=direction, include_start=False)
      if next_row is not None:
        set_current_row(next_row)

    self.select_review_row(start_row)
    dialog['value'] = MatchReviewDialog(
      self, start_row, view_book_callback=self.view_book_callback,
      match_callback=match_selected,
      ignore_callback=ignore_current,
      previous_callback=lambda: move(-1),
      next_callback=lambda: move(1),
      author_display_formatter=self.author_display_formatter)
    dialog['value'].exec()

  def apply_ignore_match(self, row):
    if row is None:
      return
    if row.get('matched'):
      row['previous_book_ids'] = list(row.get('book_ids') or [])
      row['previous_matched_books'] = list(row.get('matched_books') or [])
      row['previous_match_source'] = row.get('match_source', '')
    row['matched'] = False
    row['ignored'] = True
    row['book_ids'] = []
    row['matched_books'] = []
    row['match_source'] = 'ignored'
    row['can_toggle_on'] = True

  def apply_manual_find_match(self, row, candidate):
    if row is None or candidate is None:
      return
    candidates = self.selected_candidate_list(candidate)
    book_ids = []
    matched_books = []
    for item in candidates:
      book_id = item.get('book_id', item.get('matched_book_id'))
      if book_id is None or book_id in book_ids:
        continue
      authors = item.get('authors', item.get('matched_authors', ''))
      book_ids.append(book_id)
      matched_books.append({
        'matched_book_id': book_id,
        'matched_title': item.get('title', item.get('matched_title', '')),
        'matched_authors': authors,
      })
    if not book_ids:
      return
    row['matched'] = True
    row['ignored'] = False
    row['book_ids'] = book_ids
    row['matched_books'] = matched_books
    row['previous_book_ids'] = list(book_ids)
    row['previous_matched_books'] = list(row['matched_books'])
    match_source = self.manual_find_match_source(row, candidates)
    row['previous_match_source'] = match_source
    row['match_source'] = match_source
    row['can_toggle_on'] = True

  def selected_candidate_list(self, candidate):
    if isinstance(candidate, (list, tuple)):
      return [item for item in candidate if isinstance(item, dict)]
    if isinstance(candidate, dict):
      return [candidate]
    return []

  def manual_find_match_source(self, row, candidates):
    if len(candidates) != 1 or self.selected_match_source_callback is None:
      return 'manual find'
    try:
      return self.selected_match_source_callback(row, candidates[0]) or 'manual find'
    except Exception:
      return 'manual find'

  def current_view_csv(self):
    output = StringIO()
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(IMPORT_REVIEW_HEADERS)
    for row in self.rows_for_current_view():
      writer.writerow(self.csv_values_for_row(row))
    return output.getvalue()

  def copy_current_view(self):
    QApplication.clipboard().setText(self.current_view_csv())

  def accepted_matched(self):
    matched = {}
    for row in self.review_rows:
      if not row.get('matched'):
        continue
      position = row.get('imported_position', '')
      for book_id in row.get('book_ids') or []:
        matched[book_id] = position
    return matched

  def accepted_missing_entries(self):
    return [
      row.get('entry') or {}
      for row in self.review_rows
      if not row.get('matched')
    ]
