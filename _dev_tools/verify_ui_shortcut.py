"""Verify native shortcut registration and dispatch in isolated, offscreen Calibre."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types


ROOT = Path(__file__).resolve().parents[1]


def worker(folder):
  sys.path.insert(0, str(ROOT))
  package = types.ModuleType('calibre_plugins.list_switchboard')
  package.__path__ = [str(ROOT)]
  sys.modules['calibre_plugins.list_switchboard'] = package
  from calibre.constants import config_dir, numeric_version
  from calibre.gui2.keyboard import Manager
  from qt.core import QApplication, QIcon, QKeySequence, QMainWindow, QShortcutEvent, QTimer, QWidget
  from calibre_plugins.list_switchboard import ui

  assert Path(config_dir).resolve().is_relative_to(Path(folder).resolve())
  app = QApplication.instance() or QApplication([])
  ui.get_icons = lambda *_args: QIcon()
  gui = QMainWindow()
  gui.bars_manager = types.SimpleNamespace(bars=[], menu_bar=types.SimpleNamespace(added_actions=[]))
  gui.status_bar_extra_buttons = []
  gui.library_view = QWidget(gui)
  gui.setCentralWidget(gui.library_view)
  gui.keyboard = Manager(gui, config_name='shortcuts/list-switchboard-test')
  plugin = ui.ListSwitchboardAction(gui, '')
  plugin.interface_action_base_plugin = types.SimpleNamespace(name='List Switchboard')
  calls = []
  core = types.SimpleNamespace(
    add_selected_to_active=lambda **kwargs: calls.append(('add', kwargs)),
    show_debug_dialog=lambda: calls.append(('debug', {})),
    choose_and_import_recipe=lambda: calls.append(('import', {})),
    manage_current_active_list=lambda: calls.append(('manage', {})))
  plugin.core = lambda: core
  plugin.create_action()
  gui.addAction(plugin.qaction)
  gui.addAction(plugin.menuless_qaction)
  plugin.genesis()
  gui.keyboard.finalize()
  name = plugin.unique_name + ' - qaction'
  shortcut = gui.keyboard.shortcuts[name]
  assert shortcut['name'] == 'Add selected books to Active List'
  assert shortcut['default_keys'] == ()
  assert shortcut['action'] is plugin.menuless_qaction
  assert not plugin.menuless_qaction.shortcuts()
  import_name = plugin.unique_name + ' - import_list_action'
  manage_name = plugin.unique_name + ' - manage_active_list_action'
  menu_name = plugin.unique_name + ' - show_main_menu_action'
  for shortcut_name, action in ((import_name, plugin.import_list_action),
                                 (manage_name, plugin.manage_active_list_action),
                                 (menu_name, plugin.show_main_menu_action)):
    assert gui.keyboard.shortcuts[shortcut_name]['default_keys'] == ()
    assert gui.keyboard.shortcuts[shortcut_name]['action'] is action
    assert not action.shortcuts()

  bindings = {name: ['Ctrl+Shift+R'], import_name: ['Ctrl+Alt+I'],
    manage_name: ['Ctrl+Alt+M'], menu_name: ['Ctrl+Alt+L']}
  gui.keyboard.config['map'] = bindings
  gui.keyboard.finalize()
  assert plugin.menuless_qaction.shortcuts() == [QKeySequence('Ctrl+Shift+R')]
  reopened = Manager(gui, config_name='shortcuts/list-switchboard-test')
  assert reopened.config['map'][name] == ['Ctrl+Shift+R']

  plugin.shift_pressed = lambda: True
  plugin.ctrl_pressed = lambda: True
  QApplication.sendEvent(plugin.menuless_qaction, QShortcutEvent(QKeySequence('Ctrl+Shift+R'), 1))
  assert calls == [('add', {})], calls
  plugin.qaction.trigger()
  assert calls[-1] == ('debug', {}), calls
  plugin.ctrl_pressed = lambda: False
  plugin.qaction.trigger()
  assert calls[-1] == ('add', {'force_match_review': True}), calls
  plugin.shift_pressed = lambda: False
  plugin.qaction.trigger()
  assert calls[-1] == ('add', {'force_match_review': False}), calls
  QApplication.sendEvent(plugin.import_list_action, QShortcutEvent(QKeySequence('Ctrl+Alt+I'), 2))
  assert calls[-1] == ('import', {}), calls
  QApplication.sendEvent(plugin.manage_active_list_action, QShortcutEvent(QKeySequence('Ctrl+Alt+M'), 3))
  assert calls[-1] == ('manage', {}), calls
  menu_events = []
  menu = plugin.qaction.menu()
  menu.aboutToShow.connect(lambda: menu_events.append('shown'))
  QTimer.singleShot(0, menu.close)
  QApplication.sendEvent(plugin.show_main_menu_action, QShortcutEvent(QKeySequence('Ctrl+Alt+L'), 4))
  assert menu_events == ['shown'], menu_events

  registered_actions = {key: value['action'] for key, value in gui.keyboard.shortcuts.items()}
  plugin.apply_settings()
  gui.keyboard.finalize()
  assert len(gui.keyboard.shortcuts) == 4
  assert registered_actions == {key: value['action'] for key, value in gui.keyboard.shortcuts.items()}
  assert plugin.menuless_qaction.shortcuts() == [QKeySequence('Ctrl+Shift+R')]
  assert plugin.import_list_action.shortcuts() == [QKeySequence('Ctrl+Alt+I')]
  assert plugin.manage_active_list_action.shortcuts() == [QKeySequence('Ctrl+Alt+M')]
  assert plugin.show_main_menu_action.shortcuts() == [QKeySequence('Ctrl+Alt+L')]
  assert reopened.config.refresh() is None
  assert reopened.config['map'] == bindings
  QApplication.sendEvent(plugin.import_list_action, QShortcutEvent(QKeySequence('Ctrl+Alt+I'), 2))
  assert calls[-1] == ('import', {}), calls
  QApplication.sendEvent(plugin.manage_active_list_action, QShortcutEvent(QKeySequence('Ctrl+Alt+M'), 3))
  assert calls[-1] == ('manage', {}), calls
  QTimer.singleShot(0, menu.close)
  QApplication.sendEvent(plugin.show_main_menu_action, QShortcutEvent(QKeySequence('Ctrl+Alt+L'), 4))
  assert menu_events == ['shown', 'shown'], menu_events
  native_show_menu = ui.show_menu_under_widget
  ui.show_menu_under_widget = None
  QTimer.singleShot(0, menu.close)
  plugin.show_main_menu()
  assert menu_events == ['shown', 'shown', 'shown'], menu_events
  helper_calls = []
  ui.show_menu_under_widget = lambda window, popup, action: helper_calls.append((window, popup, action))
  plugin.show_main_menu()
  assert helper_calls == [(gui, menu, plugin.qaction)]
  ui.show_menu_under_widget = native_show_menu
  gui.keyboard.config['map'] = {key: [] for key in bindings}
  gui.keyboard.finalize()
  assert all(not action.shortcuts() for action in registered_actions.values())
  assert reopened.config.refresh() is None
  assert reopened.config['map'][name] == []
  print(json.dumps({
    'passed': True, 'calibre_version': list(numeric_version),
    'unassigned_default': True, 'assignment_persisted': True,
    'shortcut_ignores_click_modifiers': True, 'toolbar_modifiers_preserved': True,
    'settings_rebuild_preserves_binding': True, 'clearing_persisted': True,
    'import_and_manage_registered_unassigned': True, 'import_and_manage_dispatch': True,
    'main_menu_shortcut_opens_menu': True,
    'menu_helper_compatibility': True,
    'isolated': True,
  }), flush=True)
  gui.close()
  app.processEvents()


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--worker', help=argparse.SUPPRESS)
  args = parser.parse_args()
  if args.worker:
    worker(args.worker)
    return 0
  with tempfile.TemporaryDirectory(prefix='list-switchboard-shortcut-') as folder:
    env = dict(os.environ)
    env['CALIBRE_CONFIG_DIRECTORY'] = str(Path(folder) / 'config')
    env['CALIBRE_CACHE_DIRECTORY'] = str(Path(folder) / 'cache')
    env['QT_QPA_PLATFORM'] = 'offscreen'
    calibre = Path('C:/Program Files/Calibre2/calibre-debug.exe')
    command = [str(calibre) if calibre.exists() else 'calibre-debug',
      '-e', str(Path(__file__).resolve()), '--', '--worker', folder]
    code = subprocess.call(command, cwd=ROOT, env=env)
    if code:
      print(f'Isolated Calibre exited with code {code}', flush=True)
    return code


if __name__ == '__main__':
  raise SystemExit(main())
