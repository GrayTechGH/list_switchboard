#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from qt.core import (
  QDialog, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
  QSizePolicy, QTableWidget, QTableWidgetItem, Qt, QVBoxLayout
)

try:
  from calibre_plugins.list_switchboard.matching import imported_author_search_text
except ImportError:
  from matching import imported_author_search_text


ADD_MATCH_HEADERS = ['Index', 'Title', 'Author']
EXPAND_TO_ALL_TEXT = 'Expand to all'
SHOW_NEAR_MATCHES_TEXT = 'Show near matches'


class ElidedLinesLabel(QLabel):

  def __init__(self, lines, parent=None):
    QLabel.__init__(self, parent)
    self.lines = []
    self.setSizePolicy(self.ignored_width_size_policy())
    self.set_lines(lines)

  def ignored_width_size_policy(self):
    try:
      return QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    except Exception:
      return QSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

  def elide_mode(self):
    try:
      return Qt.TextElideMode.ElideRight
    except AttributeError:
      return Qt.ElideRight

  def set_lines(self, lines):
    self.lines = [str(line or '') for line in (lines or [])]
    self.setToolTip('\n'.join(self.lines))
    self.update_elided_text()

  def resizeEvent(self, event):
    QLabel.resizeEvent(self, event)
    self.update_elided_text()

  def update_elided_text(self):
    width = self.width() or 520
    width = max(20, width)
    metrics = self.fontMetrics()
    text = '\n'.join(
      metrics.elidedText(line, self.elide_mode(), width)
      for line in self.lines
    )
    if self.text() != text:
      self.setText(text)


class ActiveAddMatchDialog(QDialog):

  def __init__(
      self, parent, book_title, book_authors, candidates, entries, default_index,
      initial_show_all=False, preferred_entry=None, active_list_name=None):
    QDialog.__init__(self, parent)
    self.filtered_entries = list(candidates or [])
    self.all_entries = list(entries or [])
    self.visible_entries = []
    self.selected_entry = None
    self.show_all_entries = bool(initial_show_all)
    self.setWindowTitle('Choose list match')

    layout = QVBoxLayout()
    self.setLayout(layout)
    layout.addWidget(ElidedLinesLabel([
      f'Active list: {active_list_name or "Unknown list"}',
      f'Book: {book_title or "Untitled"} by {book_authors or "Unknown author"}',
    ], self))

    self.match_table = QTableWidget(self)
    self.match_table.setColumnCount(3)
    self.match_table.setHorizontalHeaderLabels(ADD_MATCH_HEADERS)
    self.match_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    self.match_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    self.configure_table_columns()
    layout.addWidget(self.match_table)

    controls_layout = QGridLayout()
    layout.addLayout(controls_layout)

    self.expand_button = QPushButton(EXPAND_TO_ALL_TEXT, self)
    self.configure_scope_button_width()
    self.add_button = QPushButton('Match selected', self)
    self.cancel_button = QPushButton('Cancel', self)

    index_layout = QHBoxLayout()
    index_layout.addWidget(QLabel('Index:', self))
    self.index_edit = QLineEdit(self)
    self.index_edit.setText(str(default_index or ''))
    index_layout.addWidget(self.index_edit)
    controls_layout.addLayout(index_layout, 0, 0, 1, 2)
    controls_layout.addWidget(self.add_button, 1, 0)
    controls_layout.addWidget(self.expand_button, 1, 1)
    controls_layout.setColumnStretch(2, 1)
    controls_layout.addWidget(self.cancel_button, 1, 3)

    self.expand_button.clicked.connect(self.toggle_scope)
    self.add_button.clicked.connect(self.accept)
    self.cancel_button.clicked.connect(self.reject)
    self.match_table.currentCellChanged.connect(self.update_index_from_selection)
    self.populate(self.current_scope_entries(), preferred_entry=preferred_entry)
    self.update_scope_button()
    self.resize(560, 420)

  def configure_table_columns(self):
    header = self.match_table.horizontalHeader()
    header.setSectionResizeMode(0, self.header_resize_mode('ResizeToContents'))
    header.setSectionResizeMode(1, self.header_resize_mode('Stretch'))
    header.setSectionResizeMode(2, self.header_resize_mode('Stretch'))

  def configure_scope_button_width(self):
    original_text = self.expand_button.text()
    self.expand_button.setText(SHOW_NEAR_MATCHES_TEXT)
    width = self.expand_button.sizeHint().width()
    self.expand_button.setText(EXPAND_TO_ALL_TEXT)
    width = max(width, self.expand_button.sizeHint().width())
    self.expand_button.setFixedWidth(width)
    self.expand_button.setText(original_text)
    self.scope_button_width = width

  def header_resize_mode(self, mode_name):
    try:
      return getattr(QHeaderView.ResizeMode, mode_name)
    except AttributeError:
      return getattr(QHeaderView, mode_name)

  def row_values(self, entry):
    return [
      str(entry.get('position', '') or '').strip(),
      entry.get('title', '') or 'Untitled',
      imported_author_search_text(entry) or 'Unknown author',
    ]

  def populate(self, entries, preferred_entry=None):
    current_entry = preferred_entry if preferred_entry is not None else self.current_entry()
    self.visible_entries = list(entries or [])
    self.match_table.setRowCount(len(self.visible_entries))
    for row_index, entry in enumerate(self.visible_entries):
      for column, value in enumerate(self.row_values(entry)):
        self.match_table.setItem(row_index, column, QTableWidgetItem(value))
    if self.visible_entries:
      self.match_table.setCurrentCell(self.preferred_row(current_entry), 0)
      self.add_button.setEnabled(True)
    else:
      self.match_table.setCurrentCell(-1, -1)
      self.add_button.setEnabled(False)

  def preferred_row(self, preferred_entry):
    if preferred_entry is None:
      return 0
    for row, entry in enumerate(self.visible_entries):
      if entry == preferred_entry:
        return row
    return 0

  def current_scope_entries(self):
    return self.all_entries if self.show_all_entries else self.filtered_entries

  def update_scope_button(self):
    if self.show_all_entries:
      self.expand_button.setText(SHOW_NEAR_MATCHES_TEXT)
    else:
      self.expand_button.setText(EXPAND_TO_ALL_TEXT)
    self.expand_button.setEnabled(self.has_alternate_scope())

  def has_alternate_scope(self):
    return list(self.filtered_entries) != list(self.all_entries)

  def toggle_scope(self):
    selected = self.current_entry()
    self.show_all_entries = not self.show_all_entries
    self.populate(self.current_scope_entries(), preferred_entry=selected)
    self.update_scope_button()

  def current_entry(self):
    row = self.match_table.currentRow()
    if row < 0 or row >= len(self.visible_entries):
      return None
    return self.visible_entries[row]

  def update_index_from_selection(self, *_args):
    entry = self.current_entry()
    if entry is None:
      return
    position = str(entry.get('position', '') or '').strip()
    if position:
      self.index_edit.setText(position)

  def index_value(self):
    value = str(self.index_edit.text() or '').strip()
    if not value:
      return None
    try:
      return float(value)
    except Exception:
      return None

  def accept(self):
    self.selected_entry = self.current_entry()
    if self.selected_entry is None:
      return
    QDialog.accept(self)
