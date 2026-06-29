#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

__license__ = 'GPL v3'
__copyright__ = '2026, List Switchboard contributors'
__docformat__ = 'restructuredtext en'

if False:
  get_icons = None

from qt.core import QAction, QActionGroup, QApplication, QMenu, Qt

from calibre.gui2.actions import InterfaceAction
from calibre_plugins.list_switchboard.main import ListSwitchboardCore


class ListSwitchboardAction(InterfaceAction):
  name = 'List Switchboard'
  action_spec = (
    'List SB',
    None,
    'Add selected books to Active List',
    None
  )
  action_type = 'current'
  action_add_menu = True
  action_menu_clone_qaction = 'Add selected books to Active List'

  def genesis(self):
    icon = get_icons('images/icon.png', 'List Switchboard')
    self.qaction.setIcon(icon)
    self.qaction.setToolTip('Add selected books to Active List')
    self.qaction.setStatusTip('Add selected books to Active List')
    self.qaction.triggered.connect(self.add_selected_to_active)
    self.populate_menu(self.qaction.menu())

  def core(self):
    return ListSwitchboardCore(
      self.gui,
      self.interface_action_base_plugin.do_user_config,
      plugin_base=self.interface_action_base_plugin
    )

  def build_menu(self):
    menu = QMenu('List Switchboard', self.gui)
    self.populate_menu(menu)
    return menu

  def populate_menu(self, menu):
    menu.clear()

    series_menu = menu.addMenu('Series handling')
    series_group = QActionGroup(series_menu)
    series_group.setExclusive(True)
    selected_only = self.add_menu_action(series_menu, 'Selected books only',
      lambda checked=False: self.core().set_include_calibre_series(False),
      checkable=True, checked=not bool(self.core_prefs().get('include_calibre_series', False)))
    include_series = self.add_menu_action(series_menu, 'Include series',
      lambda checked=False: self.core().set_include_calibre_series(True),
      checkable=True, checked=bool(self.core_prefs().get('include_calibre_series', False)))
    series_group.addAction(selected_only)
    series_group.addAction(include_series)

    menu.addSeparator()

    self.add_menu_action(menu, 'Add selected books to Active List', self.add_selected_to_active)
    self.add_menu_action(menu, 'Select books in Active List',
      lambda: self.core().select_active_list_books())

    menu.addSeparator()

    self.add_menu_action(menu, 'Import List...',
      lambda: self.core().choose_and_import_recipe())

    menu.addSeparator()

    active_menu = menu.addMenu('Active List')
    self.add_menu_action(active_menu, 'Manage Active List...',
      lambda: self.core().manage_current_active_list())
    self.add_menu_action(active_menu, 'Show Position Problems...',
      lambda: self.core().show_current_active_list_position_problems())
    active_menu.addSeparator()
    self.add_menu_action(active_menu, 'Save Matches',
      lambda: self.core().save_active_matches_for_current_active_list())
    active_menu.addSeparator()
    self.add_menu_action(active_menu, 'Switch...', lambda: self.core().switch_active_list())
    self.add_menu_action(active_menu, 'Create New...', lambda: self.core().create_new_active_list())
    self.add_menu_action(active_menu, 'Rename...', lambda: self.core().rename_active_list())
    self.add_menu_action(active_menu, 'Remove...', lambda: self.core().remove_active_list())

    self.add_menu_action(menu, 'Manage Stored Lists...', lambda: self.core().manage_stored_lists())

    menu.addSeparator()
    maintenance_menu = menu.addMenu('Maintenance')
    self.add_menu_action(maintenance_menu, 'Clean Up List Switchboard Fields',
      lambda: self.core().clean_up_fields())
    self.add_menu_action(maintenance_menu, 'Configure...', self.configure)
    self.add_menu_action(maintenance_menu, 'About List Switchboard',
      lambda: self.core().show_about())

    menu.aboutToShow.connect(lambda: self.sync_menu_checks(menu))
    series_menu.aboutToShow.connect(lambda: self.sync_menu_checks(series_menu))

  def core_prefs(self):
    from calibre_plugins.list_switchboard.config import prefs
    return prefs

  def sync_menu_checks(self, menu):
    prefs = self.core_prefs()
    for action in menu.actions():
      if action.menu() is not None:
        self.sync_menu_checks(action.menu())
      if action.text() == 'Selected books only':
        action.setChecked(not bool(prefs.get('include_calibre_series', False)))
      if action.text() == 'Include series':
        action.setChecked(bool(prefs.get('include_calibre_series', False)))

  def add_menu_action(self, menu, text, callback, checkable=False, checked=False):
    action = QAction(text, self.gui)
    action.setCheckable(checkable)
    if checkable:
      action.setChecked(checked)
    action.triggered.connect(callback)
    menu.addAction(action)
    return action

  def shift_pressed(self):
    modifiers = QApplication.keyboardModifiers()
    return bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

  def ctrl_pressed(self):
    modifiers = QApplication.keyboardModifiers()
    return bool(modifiers & Qt.KeyboardModifier.ControlModifier)

  def add_selected_to_active(self, checked=False):
    shift = self.shift_pressed()
    ctrl = self.ctrl_pressed()
    if shift and ctrl:
      self.core().show_debug_dialog()
      return
    self.core().add_selected_to_active(force_match_review=shift)

  def configure(self):
    self.interface_action_base_plugin.do_user_config(parent=self.gui)

  def apply_settings(self):
    self.populate_menu(self.qaction.menu())
