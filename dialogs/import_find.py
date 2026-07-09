#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from qt.core import (
  QButtonGroup, QDialog, QDialogButtonBox, QGridLayout, QGroupBox, QHBoxLayout,
  QHeaderView, QLabel, QPushButton, QRadioButton, QSpinBox, QTableWidget,
  QTableWidgetItem, QVBoxLayout
)

try:
  from calibre_plugins.list_switchboard.matching import (
    FIND_MATCH_AUTHOR_SOUNDEX_LENGTH_DEFAULT,
    FIND_MATCH_MODES,
    FIND_MATCH_TITLE_SOUNDEX_LENGTH_DEFAULT,
    FIND_MODE_IDENTICAL,
    FIND_MODE_IGNORE,
    FIND_MODE_SIMILAR,
    FIND_MODE_SOUNDEX,
    validate_find_match_modes,
  )
except ImportError:
  from matching import (
    FIND_MATCH_AUTHOR_SOUNDEX_LENGTH_DEFAULT,
    FIND_MATCH_MODES,
    FIND_MATCH_TITLE_SOUNDEX_LENGTH_DEFAULT,
    FIND_MODE_IDENTICAL,
    FIND_MODE_IGNORE,
    FIND_MODE_SIMILAR,
    FIND_MODE_SOUNDEX,
    validate_find_match_modes,
  )


MODE_LABELS = {
  'identical': 'Identical',
  'similar': 'Similar',
  'soundex': 'Soundex',
  'fuzzy': 'Fuzzy',
  'ignore': 'Ignore',
}


class FindModeDialog(QDialog):

  def __init__(self, parent, settings=None):
    QDialog.__init__(self, parent)
    self.setWindowTitle('Match mode')
    settings = settings or {}

    layout = QVBoxLayout()
    self.setLayout(layout)

    match_layout = QHBoxLayout()
    layout.addLayout(match_layout)
    self.title_soundex_length = self.length_spin(
      settings.get('title_soundex_length', FIND_MATCH_TITLE_SOUNDEX_LENGTH_DEFAULT))
    self.author_soundex_length = self.length_spin(
      settings.get('author_soundex_length', FIND_MATCH_AUTHOR_SOUNDEX_LENGTH_DEFAULT))
    title_group, self.title_button_group, self.title_buttons = self.mode_group(
      'Title matching', settings.get('title_mode', FIND_MODE_SIMILAR),
      self.title_soundex_length)
    author_group, self.author_button_group, self.author_buttons = self.mode_group(
      'Author matching', settings.get('author_mode', FIND_MODE_SIMILAR),
      self.author_soundex_length)
    match_layout.addWidget(title_group)
    match_layout.addWidget(author_group)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
    buttons.accepted.connect(self.accept)
    buttons.rejected.connect(self.reject)
    layout.addWidget(buttons)
    self.title_button_group.buttonClicked.connect(self.sync_ignore_buttons)
    self.author_button_group.buttonClicked.connect(self.sync_ignore_buttons)
    self.sync_ignore_buttons()

  def mode_group(self, title, selected, soundex_spin):
    group_box = QGroupBox(title, self)
    layout = QGridLayout()
    group_box.setLayout(layout)
    button_group = QButtonGroup(self)
    buttons = {}
    for row, mode in enumerate(FIND_MATCH_MODES):
      button = QRadioButton(MODE_LABELS.get(mode, mode.title()), self)
      buttons[mode] = button
      button_group.addButton(button)
      layout.addWidget(button, row, 0, 1, 1)
      if mode == FIND_MODE_SOUNDEX:
        layout.addWidget(QLabel('Length:', self), row, 1, 1, 1)
        layout.addWidget(soundex_spin, row, 2, 1, 1)
    buttons.get(selected, buttons[FIND_MODE_SIMILAR]).setChecked(True)
    return group_box, button_group, buttons

  def length_spin(self, selected):
    spin = QSpinBox(self)
    spin.setRange(1, 99)
    spin.setValue(int(selected or FIND_MATCH_TITLE_SOUNDEX_LENGTH_DEFAULT))
    return spin

  def checked_mode(self, buttons):
    for mode, button in buttons.items():
      if button.isChecked():
        return mode
    return FIND_MODE_SIMILAR

  def set_checked_mode(self, buttons, mode):
    for button in buttons.values():
      button.setChecked(False)
    buttons.get(mode, buttons[FIND_MODE_SIMILAR]).setChecked(True)

  def sync_ignore_buttons(self, *_args):
    self.sync_mutually_exclusive_mode(FIND_MODE_IGNORE)
    self.sync_mutually_exclusive_mode(FIND_MODE_IDENTICAL)

  def sync_mutually_exclusive_mode(self, mode):
    title_button = self.title_buttons[mode]
    author_button = self.author_buttons[mode]
    if title_button.isChecked() and author_button.isChecked():
      self.set_checked_mode(self.author_buttons, FIND_MODE_SIMILAR)
    title_button.setEnabled(not author_button.isChecked())
    author_button.setEnabled(not title_button.isChecked())

  def selected_mode(self):
    mode = {
      'title_mode': self.checked_mode(self.title_buttons),
      'author_mode': self.checked_mode(self.author_buttons),
      'title_soundex_length': self.title_soundex_length.value(),
      'author_soundex_length': self.author_soundex_length.value(),
    }
    validate_find_match_modes(mode.get('title_mode'), mode.get('author_mode'))
    return mode

  def accept(self):
    try:
      self.selected_mode()
    except ValueError:
      return
    QDialog.accept(self)


class FindImportMatchesDialog(QDialog):

  def __init__(self, parent, review_rows, find_callback=None, author_display_formatter=None):
    QDialog.__init__(self, parent)
    self.setWindowTitle('Find match')
    self.review_rows = list(review_rows or [])
    self.find_callback = find_callback
    self.author_display_formatter = author_display_formatter
    self.selected_candidate = None

    layout = QVBoxLayout()
    self.setLayout(layout)
    self.match_table = QTableWidget(self)
    self.match_table.setColumnCount(5)
    self.match_table.setHorizontalHeaderLabels([
      'Position', 'Title', 'Author', 'Match', 'Possible matches',
    ])
    self.match_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    self.match_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    layout.addWidget(self.match_table)

    actions = QHBoxLayout()
    self.find_button = QPushButton('Find match', self)
    self.review_button = QPushButton('Review selected', self)
    actions.addWidget(self.find_button)
    actions.addWidget(self.review_button)
    actions.addStretch(1)
    layout.addLayout(actions)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
    buttons.accepted.connect(self.accept)
    buttons.rejected.connect(self.reject)
    layout.addWidget(buttons)

    self.find_button.clicked.connect(self.run_find)
    self.review_button.clicked.connect(self.review_selected)
    self.match_table.currentCellChanged.connect(self.update_review_button)
    self.update_table()

  def update_table(self):
    self.match_table.setRowCount(len(self.review_rows))
    for row_index, row in enumerate(self.review_rows):
      values = [
        row.get('imported_position', ''),
        row.get('imported_title', ''),
        self.display_authors(row.get('imported_author', '')),
        'Yes' if row.get('matched') else 'No',
        str(len(row.get('possible_matches') or [])),
      ]
      for column, value in enumerate(values):
        self.match_table.setItem(row_index, column, QTableWidgetItem(str(value or '')))
    if self.review_rows:
      self.match_table.setCurrentCell(0, 0)
    self.update_review_button()

  def selected_review_row(self):
    row = self.match_table.currentRow()
    if row < 0 or row >= len(self.review_rows):
      return None
    return self.review_rows[row]

  def update_review_button(self, *_args):
    row = self.selected_review_row()
    self.review_button.setEnabled(bool(row and row.get('possible_matches')))

  def run_find(self):
    if self.find_callback is None:
      return
    updated = self.find_callback(self.review_rows)
    if updated is not None:
      self.review_rows = list(updated)
    self.update_table()

  def review_selected(self):
    row = self.selected_review_row()
    if not row or not row.get('possible_matches'):
      return
    dialog = MatchReviewDialog(
      self,
      row,
      author_display_formatter=self.author_display_formatter)
    if dialog.exec() == QDialog.Accepted:
      self.selected_candidate = dialog.selected_candidate

  def display_authors(self, value):
    if self.author_display_formatter is not None:
      try:
        return self.author_display_formatter(value)
      except Exception:
        pass
    if isinstance(value, (list, tuple)):
      return ', '.join(str(item) for item in value)
    return str(value or '')


class MatchReviewDialog(QDialog):

  def __init__(
      self, parent, review_row, candidates=None, view_book_callback=None,
      match_callback=None, ignore_callback=None, previous_callback=None,
      next_callback=None, author_display_formatter=None):
    QDialog.__init__(self, parent)
    self.setWindowTitle('Possible matches')
    self.view_book_callback = view_book_callback
    self.match_callback = match_callback
    self.ignore_callback = ignore_callback
    self.previous_callback = previous_callback
    self.next_callback = next_callback
    self.author_display_formatter = author_display_formatter
    self.selected_candidate = None
    self.navigation_action = None

    layout = QVBoxLayout()
    self.setLayout(layout)
    self.review_label = QLabel('', self)
    layout.addWidget(self.review_label)
    self.match_table = QTableWidget(self)
    self.match_table.setColumnCount(5)
    self.match_table.setHorizontalHeaderLabels(['ID', 'Title', 'Author', 'Series', 'Reason'])
    self.configure_table_columns()
    self.match_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    self.match_table.setSelectionMode(self.selection_mode('ExtendedSelection'))
    self.match_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    layout.addWidget(self.match_table)

    actions = QHBoxLayout()
    self.match_button = QPushButton('Match selected', self)
    self.ignore_button = QPushButton('Ignore', self)
    self.view_book_button = QPushButton('View book', self)
    self.previous_button = QPushButton('Previous', self)
    self.next_button = QPushButton('Next', self)
    self.cancel_button = QPushButton('Cancel', self)
    for button in (
        self.match_button, self.ignore_button, self.view_book_button,
        self.previous_button, self.next_button, self.cancel_button):
      actions.addWidget(button)
    actions.addStretch(1)
    layout.addLayout(actions)
    self.match_button.clicked.connect(self.accept)
    self.ignore_button.clicked.connect(self.ignore_current)
    self.view_book_button.clicked.connect(self.view_selected_book)
    self.previous_button.clicked.connect(self.previous_row)
    self.next_button.clicked.connect(self.next_row)
    self.cancel_button.clicked.connect(self.reject)
    self.set_review_row(review_row, candidates=candidates, preserve_column_widths=False)
    self.resize(820, 500)

  def configure_table_columns(self):
    header = self.match_table.horizontalHeader()
    try:
      header.setStretchLastSection(False)
    except Exception:
      pass
    resize_to_contents = self.header_resize_mode('ResizeToContents')
    stretch = self.header_resize_mode('Stretch')
    for column, mode in (
        (0, resize_to_contents),
        (1, stretch),
        (2, stretch),
        (3, stretch),
        (4, resize_to_contents)):
      if mode is None:
        continue
      try:
        header.setSectionResizeMode(column, mode)
      except Exception:
        pass

  def header_resize_mode(self, mode_name):
    for container in (getattr(QHeaderView, 'ResizeMode', None), QHeaderView):
      if container is None:
        continue
      try:
        return getattr(container, mode_name)
      except AttributeError:
        pass
    return None

  def set_review_row(self, review_row, candidates=None, preserve_column_widths=True):
    widths = self.column_widths() if preserve_column_widths else []
    if isinstance(review_row, (list, tuple)):
      self.review_row = {}
      self.candidates = list(review_row or [])
    else:
      self.review_row = review_row or {}
      self.candidates = list(
        candidates if candidates is not None
        else self.review_row.get('possible_matches') or [])
    self.update_label()
    self.update_table()
    if widths:
      self.restore_column_widths(widths)

  def update_label(self):
    label_lines = []
    if self.review_row:
      label_lines.append(str(self.review_row.get('imported_title', '') or 'Untitled'))
      author = self.display_authors(self.review_row.get('imported_author', ''))
      if author:
        label_lines.append(author)
    self.review_label.setText('\n'.join(label_lines))

  def column_widths(self):
    widths = []
    try:
      for column in range(self.match_table.columnCount()):
        widths.append(self.match_table.columnWidth(column))
    except Exception:
      return []
    return widths

  def restore_column_widths(self, widths):
    for column, width in enumerate(widths or []):
      try:
        self.match_table.setColumnWidth(column, width)
      except Exception:
        pass

  def update_table(self):
    self.match_table.setRowCount(len(self.candidates))
    for row_index, candidate in enumerate(self.candidates):
      authors = candidate.get('authors', candidate.get('matched_authors', ''))
      values = [
        candidate.get('book_id', candidate.get('matched_book_id', '')),
        candidate.get('title', candidate.get('matched_title', '')),
        self.display_authors(authors),
        candidate.get('series', candidate.get('matched_series', '')),
        candidate.get('reason', candidate.get('source', '')),
      ]
      for column, value in enumerate(values):
        if isinstance(value, (list, tuple)):
          value = ', '.join(str(item) for item in value)
        self.match_table.setItem(row_index, column, QTableWidgetItem(str(value or '')))
    if self.candidates:
      self.match_table.setCurrentCell(0, 0)
    enabled = bool(self.candidates)
    self.match_button.setEnabled(enabled)
    self.view_book_button.setEnabled(enabled and self.view_book_callback is not None)
    self.ignore_button.setEnabled(True)

  def selection_mode(self, mode_name):
    try:
      return getattr(QTableWidget.SelectionMode, mode_name)
    except AttributeError:
      return getattr(QTableWidget, mode_name)

  def display_authors(self, value):
    if self.author_display_formatter is not None:
      try:
        return self.author_display_formatter(value)
      except Exception:
        pass
    if isinstance(value, (list, tuple)):
      return ', '.join(str(item) for item in value)
    return str(value or '')

  def selected_row_candidate(self):
    row = self.match_table.currentRow()
    if row < 0 or row >= len(self.candidates):
      return None
    return self.candidates[row]

  def selected_row_indexes(self):
    rows = []
    try:
      selected_rows = self.match_table.selectionModel().selectedRows()
      rows.extend(index.row() for index in selected_rows)
    except Exception:
      pass
    if not rows:
      try:
        rows.extend(item.row() for item in self.match_table.selectedItems())
      except Exception:
        pass
    if not rows:
      row = self.match_table.currentRow()
      if row >= 0:
        rows.append(row)
    unique_rows = []
    for row in rows:
      if row not in unique_rows and 0 <= row < len(self.candidates):
        unique_rows.append(row)
    return sorted(unique_rows)

  def selected_row_candidates(self):
    return [self.candidates[row] for row in self.selected_row_indexes()]

  def accept(self):
    selected = self.selected_row_candidates()
    if not selected:
      return
    self.selected_candidate = selected[0] if len(selected) == 1 else selected
    self.navigation_action = 'match'
    if self.match_callback is not None:
      self.match_callback(self.selected_candidate)
      return
    self.accept_dialog()

  def previous_row(self):
    self.navigation_action = 'previous'
    if self.previous_callback is not None:
      self.previous_callback()
      return
    self.accept_dialog()

  def ignore_current(self):
    self.selected_candidate = None
    self.navigation_action = 'ignore'
    if self.ignore_callback is not None:
      self.ignore_callback()
      return
    self.accept_dialog()

  def next_row(self):
    self.navigation_action = 'next'
    if self.next_callback is not None:
      self.next_callback()
      return
    self.accept_dialog()

  def reject(self):
    self.navigation_action = 'cancel'
    self.selected_candidate = None
    self.reject_dialog()

  def view_selected_book(self):
    candidate = self.selected_row_candidate()
    if candidate is None or self.view_book_callback is None:
      return
    book_id = candidate.get('book_id', candidate.get('matched_book_id'))
    if book_id is not None:
      try:
        self.view_book_callback(book_id, parent=self)
      except TypeError as err:
        if 'parent' not in str(err):
          raise
        self.view_book_callback(book_id)

  def accept_dialog(self):
    try:
      QDialog.accept(self)
    except AttributeError:
      pass

  def reject_dialog(self):
    try:
      QDialog.reject(self)
    except AttributeError:
      pass
