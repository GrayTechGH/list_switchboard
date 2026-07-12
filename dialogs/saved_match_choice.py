#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from qt.core import (
  QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
  QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout
)

try:
  from calibre_plugins.list_switchboard.matching import imported_author_search_text
except ImportError:
  from matching import imported_author_search_text


MATCH_CHOICE_HEADERS = ['Title / Series', 'Author']


class SavedMatchChoiceDialog(QDialog):

  SKIPPED = 2

  def __init__(
      self, parent, book_title, book_authors, book_series, position, entries):
    QDialog.__init__(self, parent)
    self.entries = list(entries or [])
    self.selected_entry = None
    self.setWindowTitle('Save Active List Matches')

    layout = QVBoxLayout()
    self.setLayout(layout)
    layout.addWidget(QLabel(
      'Multiple imported entries share this tied position.\n'
      'Choose the imported entry that matches this Calibre book, or skip it.',
      self))

    summary_row = QHBoxLayout()
    layout.addLayout(summary_row)
    summary = QGridLayout()
    summary_row.addLayout(summary)
    summary_row.addStretch(1)
    self.add_summary_row(summary, 0, 'Title:', book_title or 'Untitled')
    self.add_summary_row(summary, 1, 'Author:', self.text_value(book_authors) or 'Unknown author')
    self.add_summary_row(summary, 2, 'Series:', self.text_value(book_series))
    self.add_summary_row(summary, 3, 'Position:', position)

    self.match_table = QTableWidget(self)
    self.match_table.setColumnCount(len(MATCH_CHOICE_HEADERS))
    self.match_table.setHorizontalHeaderLabels(MATCH_CHOICE_HEADERS)
    self.match_table.setSelectionBehavior(self.select_rows_behavior())
    self.match_table.setEditTriggers(self.no_edit_triggers())
    self.configure_table_columns()
    layout.addWidget(self.match_table)

    buttons = QDialogButtonBox(QDialogButtonBox.Cancel, self)
    accept_button = QPushButton('Save Selected Match', self)
    buttons.addButton(accept_button, QDialogButtonBox.AcceptRole)
    skip_button = QPushButton('Skip', self)
    buttons.addButton(skip_button, QDialogButtonBox.ActionRole)
    skip_button.clicked.connect(self.skip)
    buttons.accepted.connect(self.accept)
    buttons.rejected.connect(self.reject)
    layout.addWidget(buttons)

    self.populate()
    self.resize(720, 420)

  def add_summary_row(self, layout, row, label, value):
    label_widget = QLabel(label, self)
    value_widget = QLabel(str(value or ''), self)
    value_widget.setWordWrap(True)
    layout.addWidget(label_widget, row, 0)
    layout.addWidget(value_widget, row, 1)
    layout.setColumnStretch(0, 0)
    layout.setColumnStretch(1, 0)

  def text_value(self, value):
    if isinstance(value, str):
      return value
    if isinstance(value, (list, tuple)):
      return ', '.join(str(item or '').strip() for item in value if str(item or '').strip())
    return str(value or '')

  def row_values(self, entry):
    return [
      entry.get('title', '') or 'Untitled',
      imported_author_search_text(entry) or 'Unknown author',
    ]

  def populate(self):
    self.match_table.setRowCount(len(self.entries))
    for row_index, entry in enumerate(self.entries):
      for column, value in enumerate(self.row_values(entry)):
        self.match_table.setItem(row_index, column, QTableWidgetItem(str(value or '')))
    if self.entries:
      self.match_table.setCurrentCell(0, 0)

  def configure_table_columns(self):
    header = self.match_table.horizontalHeader()
    header.setSectionResizeMode(0, self.header_resize_mode('Stretch'))
    header.setSectionResizeMode(1, self.header_resize_mode('Stretch'))

  def current_entry(self):
    row = self.match_table.currentRow()
    if row < 0 or row >= len(self.entries):
      return None
    return self.entries[row]

  def accept(self):
    self.selected_entry = self.current_entry()
    if self.selected_entry is None:
      return
    QDialog.accept(self)

  def skip(self):
    self.selected_entry = None
    self.done(self.SKIPPED)

  def header_resize_mode(self, mode_name):
    try:
      return getattr(QHeaderView.ResizeMode, mode_name)
    except AttributeError:
      return getattr(QHeaderView, mode_name)

  def select_rows_behavior(self):
    try:
      return getattr(QTableWidget.SelectionBehavior, 'SelectRows')
    except AttributeError:
      return getattr(QTableWidget, 'SelectRows')

  def no_edit_triggers(self):
    try:
      return getattr(QTableWidget.EditTrigger, 'NoEditTriggers')
    except AttributeError:
      return getattr(QTableWidget, 'NoEditTriggers')
