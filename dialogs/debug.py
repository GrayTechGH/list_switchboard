#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from collections import OrderedDict

from qt.core import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from calibre_plugins.list_switchboard.config import prefs

try:
  from calibre_plugins.list_switchboard.camoufox_transport import browser_fallback_level
except ImportError:
  from camoufox_transport import browser_fallback_level


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

    layout.addWidget(QLabel('Force fetcher fallback level:', self))
    self.force_fallback_level = QComboBox(self)
    for level, label in (
        (0, 'Off'),
        (1, 'Level 1 - first fallback source'),
        (2, 'Level 2 - second fallback source'),
        (3, 'Level 3 - third fallback source'),
    ):
      self.force_fallback_level.addItem(label, level)
    saved_level = int(prefs.get('debug_force_fallback_level', 0) or 0)
    index = self.force_fallback_level.findData(saved_level)
    self.force_fallback_level.setCurrentIndex(index if index >= 0 else 0)
    layout.addWidget(self.force_fallback_level)

    self.disable_camoufox = QCheckBox('Disable Camoufox (use legacy fetching)', self)
    self.disable_camoufox.setChecked(browser_fallback_level(prefs) == 2)
    layout.addWidget(self.disable_camoufox)
    help_text = QLabel(
      'Applies to LibraryThing, r/bookclub, official Pulitzer, Goodreads Choice Awards, and Goodreads deep recovery. '
      'When unchecked, try Camoufox first, then legacy fetching. '
      'Fetcher levels select recovery sources. For r/bookclub, source level 1 is Wayback; '
      'source levels 2 and 3 are unavailable.', self)
    help_text.setWordWrap(True)
    layout.addWidget(help_text)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
    buttons.accepted.connect(self.accept)
    buttons.rejected.connect(self.reject)
    layout.addWidget(buttons)
