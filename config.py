#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

__license__ = 'GPL v3'
__copyright__ = '2026, List Switchboard contributors'
__docformat__ = 'restructuredtext en'

from qt.core import QCheckBox, QComboBox, QFormLayout, QLabel, QSpinBox, QWidget

from calibre.gui2 import error_dialog
from calibre.utils.config import JSONConfig

try:
  from calibre_plugins.list_switchboard.transport.camoufox import (
    MINIMUM_CAMOUFOX_VERSION, browser_fallback_level, calibre_version_tuple,
  )
except ImportError:
  from transport.camoufox import (
    MINIMUM_CAMOUFOX_VERSION, browser_fallback_level, calibre_version_tuple,
  )


prefs = JSONConfig('plugins/list_switchboard')
prefs.defaults['active_list_field'] = ''
prefs.defaults['stored_lists_field'] = ''
prefs.defaults['include_calibre_series'] = False
prefs.defaults['max_selected_books'] = 20
prefs.defaults['debug_logging'] = False
prefs.defaults['debug_sections'] = {}
prefs.defaults['debug_force_fallback_level'] = 0
prefs.defaults['debug_librarything_transport'] = 'automatic'
# None retains the saved pilot setting until configuration saves the checkbox.
prefs.defaults['debug_browser_fallback_level'] = None
prefs.defaults['camoufox_first_use_confirmed'] = False
prefs.defaults['find_match_title_mode'] = 'similar'
prefs.defaults['find_match_author_mode'] = 'similar'
prefs.defaults['find_match_title_soundex_length'] = 6
prefs.defaults['find_match_author_soundex_length'] = 8

def field_label(field_key, metadata):
  name = metadata.get('name') or field_key
  return f'{name} ({field_key})'


def is_active_list_field(metadata):
  return metadata.get('datatype') == 'series'


def is_stored_lists_field(metadata):
  datatype = metadata.get('datatype')
  return datatype == 'comments' or (datatype == 'text' and bool(metadata.get('is_multiple')))


class ConfigWidget(QWidget):

  def __init__(self):
    QWidget.__init__(self)
    self.l = QFormLayout()
    self.setLayout(self.l)

    self.active_field = QComboBox(self)
    self.stored_field = QComboBox(self)

    self._populate_fields()

    self.l.addRow(QLabel('Active List Field:'), self.active_field)
    self.l.addRow(QLabel('Stored Lists Field:'), self.stored_field)

    self.camoufox_supported = calibre_version_tuple() >= MINIMUM_CAMOUFOX_VERSION
    self.enable_camoufox = QCheckBox('Enable Camoufox', self)
    self.enable_camoufox.setChecked(
      self.camoufox_supported and browser_fallback_level(prefs) != 2)
    self.enable_camoufox.setEnabled(self.camoufox_supported)
    self.enable_camoufox.setToolTip(
      'Use Camoufox first for supported web sources, with legacy fetching as fallback. '
      'Requires Calibre 9.16 or newer.')
    self.l.addRow(self.enable_camoufox)

    self.max_selected_books = QSpinBox(self)
    self.max_selected_books.setRange(1, 1000000)
    try:
      selection_limit = int(prefs.get('max_selected_books', 20))
    except (TypeError, ValueError):
      selection_limit = 20
    if selection_limit < 1:
      selection_limit = 20
    self.max_selected_books.setValue(selection_limit)
    self.max_selected_books.setToolTip(
      'Maximum books per Add Selected or Create New Active List action. '
      'Books added through Include series count toward the limit. '
      'An action exceeding the limit stops without changing any books.')
    self.l.addRow(QLabel('Maximum selected books:'), self.max_selected_books)

  def _populate_fields(self):
    self.active_field.addItem('Choose a series-like custom field...', '')
    self.stored_field.addItem('Choose a long text or comma-separated custom field...', '')

    db = getattr(getattr(self, 'gui', None), 'current_db', None)
    # The configuration widget may be opened without a direct GUI reference on
    # some Calibre versions, so use the global GUI if available.
    if db is None:
      try:
        from calibre.gui2.ui import get_gui
        gui = get_gui()
        db = gui.current_db if gui is not None else None
      except Exception:
        db = None

    if db is None:
      return

    fields = []
    for key, metadata in db.field_metadata.custom_iteritems():
      fields.append((metadata.get('name') or key, key, metadata))

    for _name, key, metadata in sorted(fields, key=lambda item: item[0].lower()):
      if is_active_list_field(metadata):
        self.active_field.addItem(field_label(key, metadata), key)
      if is_stored_lists_field(metadata):
        self.stored_field.addItem(field_label(key, metadata), key)

    self._select_value(self.active_field, prefs['active_list_field'])
    self._select_value(self.stored_field, prefs['stored_lists_field'])

  def _select_value(self, combo, value):
    index = combo.findData(value)
    if index >= 0:
      combo.setCurrentIndex(index)

  def validate(self):
    active = self.active_field.currentData()
    stored = self.stored_field.currentData()
    if not active or not stored:
      error_dialog(self, 'List Switchboard configuration',
        'Choose both an Active List Field and a Stored Lists Field.', show=True)
      return False
    if active == stored:
      error_dialog(self, 'List Switchboard configuration',
        'The Active List Field and Stored Lists Field must be different fields.', show=True)
      return False
    return True

  def save_settings(self):
    prefs['active_list_field'] = self.active_field.currentData() or ''
    prefs['stored_lists_field'] = self.stored_field.currentData() or ''
    # Saving other settings on old Calibre must not disable support after an upgrade.
    if self.camoufox_supported:
      prefs['debug_browser_fallback_level'] = 0 if self.enable_camoufox.isChecked() else 2
    prefs['max_selected_books'] = self.max_selected_books.value()
