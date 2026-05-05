#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from qt.core import (
  QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel, QListWidget,
  QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout
)


class StoredListsDialog(QDialog):

  def __init__(self, parent, core, stored):
    QDialog.__init__(self, parent)
    self.core = core
    self.stored = stored
    self.setWindowTitle('Manage Stored Lists')

    layout = QVBoxLayout()
    self.setLayout(layout)

    content = QHBoxLayout()
    layout.addLayout(content)

    left = QVBoxLayout()
    left.addWidget(QLabel('Stored Lists', self))
    self.list_widget = QListWidget(self)
    left.addWidget(self.list_widget)
    content.addLayout(left)

    right = QVBoxLayout()
    right.addWidget(QLabel('Books in selected list', self))
    self.book_table = QTableWidget(self)
    self.book_table.setColumnCount(3)
    self.book_table.setHorizontalHeaderLabels(['Position', 'Title', 'Author'])
    self.book_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    self.book_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    self.book_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    self.book_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    self.book_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
    right.addWidget(self.book_table)
    content.addLayout(right)

    buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
    self.switch_button = QPushButton('Switch to Selected List', self)
    self.rename_button = QPushButton('Rename List', self)
    self.remove_button = QPushButton('Remove List', self)
    buttons.addButton(self.switch_button, QDialogButtonBox.ActionRole)
    buttons.addButton(self.rename_button, QDialogButtonBox.ActionRole)
    buttons.addButton(self.remove_button, QDialogButtonBox.ActionRole)
    buttons.rejected.connect(self.reject)
    self.switch_button.clicked.connect(self.switch_selected)
    self.rename_button.clicked.connect(self.rename_selected)
    self.remove_button.clicked.connect(self.remove_selected)
    layout.addWidget(buttons)

    self.list_widget.currentRowChanged.connect(self.update_books)
    self.refresh_lists()
    self.resize(900, 500)

  def selected_list_name(self):
    row = self.list_widget.currentRow()
    if row < 0 or row >= len(self.stored):
      return None
    return self.stored[row]

  def refresh_lists(self):
    current = self.selected_list_name()
    self.list_widget.clear()
    self.stored = self.core.current_stored_lists()
    for name in self.stored:
      count = len(self.core.books_for_stored_list(name))
      self.list_widget.addItem(f'{name} ({count})')
    if self.stored:
      row = self.stored.index(current) if current in self.stored else 0
      self.list_widget.setCurrentRow(row)
    else:
      self.update_books(-1)

  def update_books(self, row):
    name = self.selected_list_name()
    rows = self.core.books_for_stored_list(name) if name else []
    self.book_table.setRowCount(len(rows))
    for row_index, row_data in enumerate(rows):
      for column, value in enumerate(row_data):
        self.book_table.setItem(row_index, column, QTableWidgetItem(value))

  def switch_selected(self):
    name = self.selected_list_name()
    if not name:
      return
    active = self.core.current_active()
    if active is None:
      self.core.create_new_active_list(selected_ids=self.core.selected_book_ids())
    else:
      try:
        self.core._switch_to_existing(active, name, show_progress=True)
        self.core.status_message(f'Switched Active List to "{name}".')
      except Exception as err:
        self.core.show_exception('Switch Active List', err)
        return
    self.accept()

  def rename_selected(self):
    name = self.selected_list_name()
    if not name:
      return
    self.core.rename_stored_list(name)
    self.refresh_lists()

  def remove_selected(self):
    name = self.selected_list_name()
    if not name:
      return
    self.core.remove_stored_list(name)
    self.refresh_lists()

