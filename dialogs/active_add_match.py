#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from dataclasses import dataclass

from qt.core import (
  QDialog, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
  QSizePolicy, QTableWidget, QTableWidgetItem, Qt, QVBoxLayout
)

from calibre.gui2 import question_dialog

try:
  from calibre_plugins.list_switchboard.matching import imported_author_search_text
except ImportError:
  from matching import imported_author_search_text


ADD_MATCH_HEADERS = ['Index', 'Title', 'Author']
EXPAND_TO_ALL_TEXT = 'Expand to all'
SHOW_NEAR_MATCHES_TEXT = 'Show near matches'


@dataclass
class ActiveAddMatchRequest:
  book_id: int
  entries: list
  candidates: list
  default_index: object
  initial_show_all: bool = False
  preferred_entry: object = None
  automatic_entry: object = None


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
  """Choose one match while earlier books' accepted additions remain staged.

  The batch controller supplies pending-choice state. A default index or focused
  candidate in this dialog is not an accepted choice to protect on cancellation.
  """

  def __init__(
      self, parent, book_title, book_authors, candidates, entries, default_index,
      initial_show_all=False, preferred_entry=None, active_list_name=None,
      has_pending_choices=False):
    QDialog.__init__(self, parent)
    self.filtered_entries = list(candidates or [])
    self.all_entries = list(entries or [])
    self.visible_entries = []
    self.selected_entry = None
    self.has_pending_choices = bool(has_pending_choices)
    self.show_all_entries = bool(initial_show_all)
    self.setWindowTitle('Choose list match')

    layout = QVBoxLayout()
    self.setLayout(layout)
    self.book_label = ElidedLinesLabel([
      f'Active list: {active_list_name or "Unknown list"}',
      f'Book: {book_title or "Untitled"} by {book_authors or "Unknown author"}',
    ], self)
    layout.addWidget(self.book_label)

    self.match_table = QTableWidget(self)
    self.match_table.setColumnCount(3)
    self.match_table.setHorizontalHeaderLabels(ADD_MATCH_HEADERS)
    self.match_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    self.match_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    self.configure_table_columns()
    layout.addWidget(self.match_table)

    controls_layout = QGridLayout()
    self.controls_layout = controls_layout
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
    controls_layout.addLayout(index_layout, 0, 0)
    controls_layout.addWidget(self.add_button, 0, 1)
    controls_layout.addWidget(self.expand_button, 0, 2)
    controls_layout.setColumnStretch(0, 1)
    self.footer_layout = QHBoxLayout()
    self.footer_layout.addStretch(1)
    self.footer_layout.addWidget(self.cancel_button)
    controls_layout.addLayout(self.footer_layout, 1, 0, 1, 3)

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

  def reject(self):
    if not self.has_pending_choices:
      QDialog.reject(self)
      return
    if question_dialog(
        self, 'Discard pending choices',
        'Discard all pending choices and cancel this add operation?',
        default_yes=False, yes_text='Discard choices', no_text='Continue reviewing'):
      QDialog.reject(self)


class ActiveAddMatchBatchDialog(ActiveAddMatchDialog):
  """Review a batch without persisting choices until every book is resolved.

  Page drafts retain row, index, and scope independently of accepted choices.
  Automatic matches seed the choices but do not count as user interaction for
  discard confirmation. Previous and Next preserve drafts without accepting
  them. Match selected accepts a choice; Finish requires every book resolved.
  """

  def __init__(self, parent, books, active_list_name=None):
    self.books = [dict(book) for book in books]
    self.book_number = 0
    self.active_list_name = active_list_name
    self.choices = {
      book['book_id']: book['choice'] for book in self.books
      if book.get('choice') is not None
    }
    first = self.books[0]
    ActiveAddMatchDialog.__init__(
      self, parent, first['title'], first['authors'], first['candidates'],
      first['entries'], self.default_index_text(first),
      initial_show_all=first.get('initial_show_all', False),
      preferred_entry=first.get('preferred_entry'), active_list_name=active_list_name)
    self.previous_button = QPushButton('Previous', self)
    self.previous_button.setToolTip(
      'Return to the previous book; keep this selection and index for review.')
    self.next_button = QPushButton('Next', self)
    self.book_counter = QLabel(self)
    self.layout().insertWidget(0, self.book_counter)
    self.footer_layout.insertWidget(0, self.previous_button)
    self.footer_layout.insertWidget(1, self.next_button)
    self.previous_button.clicked.connect(self.previous_book)
    self.next_button.clicked.connect(self.next_book)
    self.match_table.currentCellChanged.connect(self.update_navigation)
    self.load_book(0)

  def default_index_text(self, book):
    choice = self.choices.get(book['book_id'])
    value = choice[1] if choice is not None else book['default_index']
    return '' if value is None else f'{value:g}'

  def remember_draft(self):
    self.books[self.book_number]['draft'] = {
      'entry': self.current_entry(), 'index': self.index_edit.text(),
      'show_all': self.show_all_entries,
    }

  def load_book(self, number):
    self.book_number = number
    book = self.books[number]
    draft = book.get('draft')
    choice = self.choices.get(book['book_id'])
    self.filtered_entries = list(book['candidates'])
    self.all_entries = list(book['entries'])
    self.show_all_entries = draft['show_all'] if draft else book.get('initial_show_all', False)
    preferred = draft['entry'] if draft else (
      choice[0] if choice is not None else book.get('preferred_entry'))
    self.book_label.set_lines([
      f'Active list: {self.active_list_name or "Unknown list"}',
      f'Book: {book["title"] or "Untitled"} by {book["authors"] or "Unknown author"}',
    ])
    self.visible_entries = []
    self.populate(self.current_scope_entries(), preferred_entry=preferred)
    self.index_edit.setText(draft['index'] if draft else self.default_index_text(book))
    if not draft and choice is None:
      self.update_index_from_selection()
    self.update_scope_button()
    self.update_navigation()

  def stage_current_choice(self):
    entry = self.current_entry()
    if entry is None:
      return False
    book = self.books[self.book_number]
    index = self.index_value()
    if index is None:
      index = book['default_index']
    self.choices[book['book_id']] = (entry, index, True)
    self.has_pending_choices = True
    return True

  def can_finish(self):
    current_id = self.books[self.book_number]['book_id']
    return all(
      book['book_id'] in self.choices for book in self.books
      if book['book_id'] != current_id
    ) and (current_id in self.choices or self.current_entry() is not None)

  def update_navigation(self, *_args):
    last = self.book_number == len(self.books) - 1
    self.previous_button.setEnabled(self.book_number > 0)
    self.book_counter.setText(f'Book {self.book_number + 1} of {len(self.books)}')
    self.next_button.setText('Finish' if last else 'Next')
    self.next_button.setEnabled(not last or self.can_finish())
    if last:
      self.next_button.setToolTip('Finish reviewing and add these books.' if self.can_finish()
        else 'Choose a match for each book before finishing.')
    else:
      self.next_button.setToolTip(
        'Go to the next book without accepting this match; keep its draft for review.')

  def previous_book(self):
    if self.book_number > 0:
      self.remember_draft()
      self.load_book(self.book_number - 1)

  def next_book(self):
    if self.book_number == len(self.books) - 1:
      if self.can_finish():
        self.stage_current_choice()
        QDialog.accept(self)
      return
    self.remember_draft()
    self.load_book(self.book_number + 1)

  def accept(self):
    if self.current_entry() is not None:
      if self.book_number == len(self.books) - 1:
        self.stage_current_choice()
        self.update_navigation()
        if self.can_finish():
          QDialog.accept(self)
      else:
        self.stage_current_choice()
        self.next_book()
