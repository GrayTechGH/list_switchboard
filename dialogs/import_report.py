#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from qt.core import (
  QApplication, QDialog, QDialogButtonBox, QHeaderView, QLabel, QPushButton,
  QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout
)


class ImportReportDialog(QDialog):

  def __init__(
      self, parent, list_name, matched_count, entries_count, missing_entries,
      allow_deep_recovery=False, notes=None):
    QDialog.__init__(self, parent)
    self.missing_entries = missing_entries
    self.deep_recovery_requested = False
    self.setWindowTitle('Import List Report')
    notes = [note for note in (notes or []) if note]
    note_text = '\n' + '\n'.join(notes) if notes else ''

    layout = QVBoxLayout()
    self.setLayout(layout)
    summary = QLabel(
      f'Imported "{list_name}".\n'
      f'Placed {matched_count} books in the Active List.\n'
      f'Matched {matched_count} of {entries_count} recipe entries.\n'
      f'Missing {len(missing_entries)} recipe entries.'
      f'{note_text}',
      self)
    summary.setWordWrap(True)
    summary.setSizePolicy(self.ignored_width_size_policy())
    layout.addWidget(summary)

    self.missing_table = QTableWidget(self)
    self.missing_table.setColumnCount(3)
    self.missing_table.setHorizontalHeaderLabels(['Position', 'Title', 'Author'])
    self.missing_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    self.missing_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    self.missing_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    self.missing_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    self.missing_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
    self.missing_table.setRowCount(len(missing_entries))
    for row, entry in enumerate(missing_entries):
      values = [
        str(entry.get('position', '') or ''),
        str(entry.get('title', '') or ''),
        str(entry.get('author', '') or ''),
      ]
      for column, value in enumerate(values):
        self.missing_table.setItem(row, column, QTableWidgetItem(value))
    layout.addWidget(self.missing_table)

    buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
    self.copy_button = QPushButton('Copy Missing List', self)
    buttons.addButton(self.copy_button, QDialogButtonBox.ActionRole)
    self.copy_button.clicked.connect(self.copy_missing_list)
    if allow_deep_recovery and missing_entries:
      self.deep_recovery_button = QPushButton('Try Deep Recovery', self)
      buttons.addButton(self.deep_recovery_button, QDialogButtonBox.ActionRole)
      self.deep_recovery_button.clicked.connect(self.request_deep_recovery)
    buttons.rejected.connect(self.reject)
    layout.addWidget(buttons)
    self.resize(*self.initial_report_size())

  def initial_report_size(self):
    width = 850
    height = 500
    try:
      screen = QApplication.primaryScreen()
      if screen is not None:
        available = screen.availableGeometry()
        width = min(width, max(420, int(available.width() * 0.85)))
    except Exception:
      pass
    return width, height

  def ignored_width_size_policy(self):
    try:
      return QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    except Exception:
      return QSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

  def missing_list_text(self):
    lines = ['Position\tTitle\tAuthor']
    for entry in self.missing_entries:
      lines.append('\t'.join([
        str(entry.get('position', '') or ''),
        str(entry.get('title', '') or ''),
        str(entry.get('author', '') or ''),
      ]))
    return '\n'.join(lines)

  def copy_missing_list(self):
    QApplication.clipboard().setText(self.missing_list_text())

  def request_deep_recovery(self):
    self.deep_recovery_requested = True
    self.accept()

