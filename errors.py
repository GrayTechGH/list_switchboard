#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai


class ListSwitchboardError(Exception):
  pass


class DuplicateStoredListsError(ListSwitchboardError):

  def __init__(self, duplicate_groups):
    ListSwitchboardError.__init__(self, 'Duplicate Stored Lists found')
    self.duplicate_groups = duplicate_groups


class ImportCancelledError(ListSwitchboardError):
  pass
