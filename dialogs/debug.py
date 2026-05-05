#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from collections import OrderedDict

from qt.core import QCheckBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from calibre_plugins.list_switchboard.config import prefs


class DebugDialog(QDialog):

  def __init__(self, parent, debug_sections):
    QDialog.__init__(self, parent)
    self.setWindowTitle('List Switchboard Debug')

    layout = QVBoxLayout()
    self.setLayout(layout)
    layout.addWidget(QLabel(
      'Debug logging writes selected List Switchboard troubleshooting details to the Calibre debug log.',
      self))

    self.debug_logging = QCheckBox('Enable all debug logging', self)
    self.debug_logging.setChecked(bool(prefs.get('debug_logging', False)))
    layout.addWidget(self.debug_logging)

    layout.addWidget(QLabel('Debug sections:', self))
    saved_sections = prefs.get('debug_sections', {}) or {}
    self.section_boxes = OrderedDict()
    for key, label in debug_sections:
      box = QCheckBox(label, self)
      box.setChecked(bool(saved_sections.get(key, False)))
      self.section_boxes[key] = box
      layout.addWidget(box)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
    buttons.accepted.connect(self.accept)
    buttons.rejected.connect(self.reject)
    layout.addWidget(buttons)

