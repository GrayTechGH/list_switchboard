#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from qt.core import QDialog, QDialogButtonBox, QLabel, QListWidget, QPushButton, QVBoxLayout


class ChoiceDialog(QDialog):

  SKIPPED = 2

  def __init__(self, parent, title, intro, choices, button_text, skip_button_text=None):
    QDialog.__init__(self, parent)
    self.setWindowTitle(title)
    self.choice = None

    layout = QVBoxLayout()
    self.setLayout(layout)
    layout.addWidget(QLabel(intro, self))

    self.list_widget = QListWidget(self)
    for choice in choices:
      self.list_widget.addItem(choice)
    if choices:
      self.list_widget.setCurrentRow(0)
    layout.addWidget(self.list_widget)

    buttons = QDialogButtonBox(QDialogButtonBox.Cancel, self)
    accept_button = QPushButton(button_text, self)
    buttons.addButton(accept_button, QDialogButtonBox.AcceptRole)
    if skip_button_text:
      skip_button = QPushButton(skip_button_text, self)
      buttons.addButton(skip_button, QDialogButtonBox.ActionRole)
      skip_button.clicked.connect(self.skip)
    buttons.accepted.connect(self.accept)
    buttons.rejected.connect(self.reject)
    layout.addWidget(buttons)

  def accept(self):
    item = self.list_widget.currentItem()
    if item is None:
      return
    self.choice = item.text()
    QDialog.accept(self)

  def skip(self):
    self.choice = None
    self.done(self.SKIPPED)
