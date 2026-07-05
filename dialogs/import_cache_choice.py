#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from qt.core import QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout


class ImportCacheChoiceDialog(QDialog):
  """Choose how an existing parsed import cache should be used for this run."""

  def __init__(self, parent, recipe, cache, supports_incremental_update=False):
    QDialog.__init__(self, parent)
    self.choice = 'cancel'
    self.setWindowTitle('Import List')

    fetched_at = cache.get('fetched_at') or 'unknown time'
    entries = len(cache.get('entries') or [])
    layout = QVBoxLayout()
    self.setLayout(layout)
    layout.addWidget(QLabel(
      f'A saved "{recipe.NAME}" list is available from {fetched_at} with {entries} entries.\n\n'
      'Choose how to import it:', self))

    saved_button = QPushButton('Use saved version', self)
    saved_button.clicked.connect(lambda: self.choose('saved'))
    layout.addWidget(saved_button)

    if supports_incremental_update:
      update_button = QPushButton('Update new or undecided pages only', self)
      update_button.clicked.connect(lambda: self.choose('incremental'))
      update_button.setToolTip(
        'Fetch the list index and only linked pages that are new or still unfinished.')
      layout.addWidget(update_button)

    refresh_button = QPushButton('Complete refresh from the web', self)
    refresh_button.clicked.connect(lambda: self.choose('refresh'))
    layout.addWidget(refresh_button)

    buttons = QDialogButtonBox(QDialogButtonBox.Cancel, self)
    buttons.rejected.connect(self.reject)
    layout.addWidget(buttons)
    self.resize(430, 0)

  def choose(self, choice):
    self.choice = choice
    self.accept()
