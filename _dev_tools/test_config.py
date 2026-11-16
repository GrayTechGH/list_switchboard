"""Configuration persistence and selected-book action boundaries."""

import importlib.util
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from _dev_tools import test_import_matching as fixtures


class ConfigControlsTest(unittest.TestCase):

  def setUp(self):
    class Widget:
      def __init__(self, *_args):
        self.enabled = True
      def setLayout(self, layout):
        self.layout = layout
      def setEnabled(self, enabled):
        self.enabled = enabled
      def setToolTip(self, text):
        self.tooltip = text

    class CheckBox(Widget):
      def setChecked(self, checked):
        self.checked = checked
      def isChecked(self):
        return self.checked

    class ComboBox(Widget):
      def __init__(self, *_args):
        self.items, self.index = [], 0
      def addItem(self, label, data):
        self.items.append((label, data))
      def currentData(self):
        return self.items[self.index][1]

    class SpinBox(Widget):
      def setRange(self, minimum, maximum):
        self.minimum, self.maximum = minimum, maximum
      def setValue(self, value):
        self.number = min(self.maximum, max(self.minimum, value))
      def value(self):
        return self.number

    class Layout:
      def addRow(self, *_args):
        pass

    class Preferences(dict):
      def __init__(self, *_args):
        self.defaults = {}
      def get(self, key, default=None):
        return super().get(key, self.defaults.get(key, default))

    config_api = types.ModuleType('calibre.utils.config')
    config_api.JSONConfig = Preferences
    self.enterContext(patch.dict('sys.modules', {'calibre.utils.config': config_api}))
    for name, widget in (
        ('QWidget', Widget), ('QLabel', Widget), ('QCheckBox', CheckBox),
        ('QComboBox', ComboBox), ('QSpinBox', SpinBox), ('QFormLayout', Layout)):
      self.enterContext(patch.object(fixtures.qt_core, name, widget, create=True))
    spec = importlib.util.spec_from_file_location(
      'isolated_config', Path(__file__).resolve().parents[1] / 'config.py')
    self.config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(self.config)
    self.enterContext(patch.object(self.config, 'calibre_version_tuple', return_value=(9, 18, 0)))

  def test_defaults_and_saved_settings_reopen(self):
    widget = self.config.ConfigWidget()
    self.assertTrue(widget.enable_camoufox.isChecked())
    self.assertEqual(20, widget.max_selected_books.value())
    widget.enable_camoufox.setChecked(False)
    widget.max_selected_books.setValue(35)
    widget.save_settings()
    reopened = self.config.ConfigWidget()
    self.assertFalse(reopened.enable_camoufox.isChecked())
    self.assertEqual(35, reopened.max_selected_books.value())
    self.assertEqual(2, self.config.prefs['debug_browser_fallback_level'])

  def test_existing_browser_preferences_are_preserved_until_config_save(self):
    for mode, enabled in (('automatic', True), ('camoufox', True), ('old', False)):
      self.config.prefs.clear()
      self.config.prefs['debug_librarything_transport'] = mode
      self.assertEqual(enabled, self.config.ConfigWidget().enable_camoufox.isChecked())
    for level in (0, 1, 2):
      self.config.prefs['debug_browser_fallback_level'] = level
      self.assertEqual(level != 2, self.config.ConfigWidget().enable_camoufox.isChecked())

  def test_old_calibre_does_not_save_unavailable_checkbox_as_disabled_preference(self):
    with patch.object(self.config, 'calibre_version_tuple', return_value=(9, 15, 0)):
      widget = self.config.ConfigWidget()
      self.assertFalse(widget.enable_camoufox.enabled)
      self.assertFalse(widget.enable_camoufox.isChecked())
      widget.save_settings()
    self.assertNotIn('debug_browser_fallback_level', self.config.prefs)
    self.assertTrue(self.config.ConfigWidget().enable_camoufox.isChecked())

  def test_unsaved_config_changes_do_not_change_preferences(self):
    before = dict(self.config.prefs)
    widget = self.config.ConfigWidget()
    widget.enable_camoufox.setChecked(False)
    widget.max_selected_books.setValue(50)
    self.assertEqual(before, dict(self.config.prefs))

  def test_config_disable_prevents_browser_api_for_supported_sources(self):
    widget = self.config.ConfigWidget()
    widget.enable_camoufox.setChecked(False)
    widget.save_settings()
    core = fixtures.main.ListSwitchboardCore(types.SimpleNamespace(), lambda **_kw: None)
    with patch.dict(fixtures.main.prefs, self.config.prefs):
      with patch.object(fixtures.main, 'camoufox_capability') as capability:
        with patch.object(fixtures.main, 'CamoufoxTransport') as factory:
          for host in ('www.librarything.com', 'www.reddit.com', 'www.pulitzer.org', 'www.goodreads.com'):
            with self.assertRaises(fixtures.main.CamoufoxSkippedError):
              core.fetch_url('https://' + host + '/test', transport='camoufox')
          factory.assert_not_called()
          capability.assert_not_called()


class SelectedBookLimitTest(unittest.TestCase):

  def setUp(self):
    self.core = object.__new__(fixtures.main.ListSwitchboardCore)
    self.core.gui = None
    self.core.current_active = Mock(side_effect=AssertionError('No metadata actions allowed'))
    self.notice = self.enterContext(patch.object(fixtures.list_state, 'error_dialog'))
    self.enterContext(patch.dict(fixtures.main.prefs, {'max_selected_books': 20}))

  def test_default_limit_blocks_raw_selection_before_series_expansion(self):
    self.core.selected_book_ids = lambda: list(range(21))
    self.core.selected_ids_with_series = Mock(side_effect=AssertionError('Do not expand over-limit selection'))
    with patch.dict(fixtures.main.prefs, {'include_calibre_series': True}):
      self.core._add_selected_to_active()
    self.core.current_active.assert_not_called()
    self.notice.assert_called_once()
    message = self.notice.call_args.args[2]
    self.assertIn('21 books', message)
    self.assertIn('maximum is 20', message)
    self.assertIn('Maintenance > Configure', message)

  def test_series_expansion_is_limited_before_metadata_or_matching(self):
    self.core.selected_book_ids = lambda: [20]
    self.core.all_book_ids = lambda: list(range(21))
    self.core.all_local_series_values = lambda ids: {book_id: ['Jaran'] for book_id in ids}
    for name in ('debug_selection_expanded_series', 'debug_active_add_timing', 'debug_selection_ids'):
      setattr(self.core, name, lambda *_args, **_kw: None)
    with patch.dict(fixtures.main.prefs, {'include_calibre_series': True}):
      self.core._add_selected_to_active()
    self.core.current_active.assert_not_called()
    self.notice.assert_called_once()

  def test_create_list_is_blocked_before_name_prompt(self):
    with patch.object(fixtures.list_state.QInputDialog, 'getText', create=True) as prompt:
      self.assertIsNone(self.core._create_new_active_list(selected_ids=list(range(21))))
      prompt.assert_not_called()
    self.core.current_active.assert_not_called()
    self.notice.assert_called_once()

  def test_configured_limit_allows_boundary_and_rejects_next_book(self):
    self.core.add_book_ids_to_active = Mock()
    self.core.debug_active_add_timing = lambda *_args, **_kw: None
    self.core.debug_selection_ids = lambda *_args: None
    with patch.dict(fixtures.main.prefs, {'max_selected_books': 25, 'include_calibre_series': False}):
      self.core.selected_book_ids = lambda: list(range(25))
      self.core._add_selected_to_active()
      self.core.add_book_ids_to_active.assert_called_once_with(list(range(25)), force_match_review=False)
      self.notice.assert_not_called()
      self.core.selected_book_ids = lambda: list(range(26))
      self.core._add_selected_to_active()
    self.assertEqual(1, self.core.add_book_ids_to_active.call_count)
    self.notice.assert_called_once()


if __name__ == '__main__':
  unittest.main()
