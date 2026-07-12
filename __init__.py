#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

__license__ = 'GPL v3'
__copyright__ = '2026, List Switchboard contributors'
__docformat__ = 'restructuredtext en'

from calibre.customize import InterfaceActionBase


class ListSwitchboardPlugin(InterfaceActionBase):
  name = 'List Switchboard'
  description = 'Manage active and stored reading lists in configured metadata fields'
  supported_platforms = ['windows', 'osx', 'linux']
  author = 'GrayTechGH'
  version = (1, 9, 0)
  # The plugin imports Qt through calibre.qt.core and relies on Calibre's
  # Python-3 database API.  Calibre 6 is the first supported Qt-6 generation.
  minimum_calibre_version = (6, 0, 0)
  actual_plugin = 'calibre_plugins.list_switchboard.ui:ListSwitchboardAction'

  def is_customizable(self):
    return True

  def config_widget(self):
    from calibre_plugins.list_switchboard.config import ConfigWidget
    return ConfigWidget()

  def save_settings(self, config_widget):
    config_widget.save_settings()
    ac = self.actual_plugin_
    if ac is not None:
      ac.apply_settings()
