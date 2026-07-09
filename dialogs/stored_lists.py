#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from qt.core import (
  QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel, QListWidget,
  QListWidgetItem, QPushButton, QTableWidget, QTableWidgetItem, Qt, QVBoxLayout
)


class StoredListsDialog(QDialog):

  def __init__(self, parent, core, rows):
    QDialog.__init__(self, parent)
    self.core = core
    self.rows = rows
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
    if row < 0 or row >= len(self.rows):
      return None
    selected = self.rows[row]
    if selected.get('is_active'):
      return None
    return selected['name']

  def first_selectable_row(self):
    for row, item in enumerate(self.rows):
      if not item.get('is_active'):
        return row
    return None

  def set_actions_enabled(self):
    enabled = self.selected_list_name() is not None
    self.switch_button.setEnabled(enabled)
    self.rename_button.setEnabled(enabled)
    self.remove_button.setEnabled(enabled)

  def refresh_lists(self):
    current = self.selected_list_name()
    self.list_widget.clear()
    self.rows = self.core.managed_stored_list_rows()
    for row in self.rows:
      name = row['name']
      if row.get('is_active'):
        count = len(self.core.books_for_active_list(name))
        item = QListWidgetItem(f'{name} ({count}) - Active List')
        try:
          item.setFlags(
            item.flags()
            & ~Qt.ItemFlag.ItemIsEnabled
            & ~Qt.ItemFlag.ItemIsSelectable)
        except Exception:
          pass
      else:
        count = len(self.core.books_for_stored_list(name))
        item = QListWidgetItem(f'{name} ({count})')
      self.list_widget.addItem(item)
    if self.rows:
      current_row = next(
        (index for index, row in enumerate(self.rows)
         if row['name'] == current and not row.get('is_active')),
        None)
      if current_row is None:
        current_row = self.first_selectable_row()
      if current_row is not None:
        self.list_widget.setCurrentRow(current_row)
      else:
        self.update_books(-1)
    else:
      self.update_books(-1)
    self.set_actions_enabled()

  def update_books(self, row):
    name = self.selected_list_name()
    rows = self.core.books_for_stored_list(name) if name else []
    self.book_table.setRowCount(len(rows))
    for row_index, row_data in enumerate(rows):
      for column, value in enumerate(row_data):
        self.book_table.setItem(row_index, column, QTableWidgetItem(value))
    self.set_actions_enabled()

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
