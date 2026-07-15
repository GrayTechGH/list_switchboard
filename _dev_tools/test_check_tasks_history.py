"""Tests for completed-task retention and section ordering."""

import unittest

from _dev_tools.check_tasks_history import (
  retained_counted_keys,
  section_order_error,
)


class TasksHistoryTests(unittest.TestCase):

  def test_retention_selects_three_newest_counted_versions(self):
    self.assertEqual(
      [(1, 9), (1, 8), (1, 7)],
      retained_counted_keys([
        (1, 9, 0), (1, 8, 2), (1, 8, 0), (1, 7, 0), (1, 6, 0),
      ]))

  def test_section_order_accepts_newest_first_then_tasks_then_reminders(self):
    self.assertEqual('', section_order_error('''
1.9.0:
1.8.0:
1.7.0:
Likely next tasks:
Reminders:
'''))

  def test_section_order_rejects_a_version_after_next_tasks(self):
    self.assertEqual(
      'completed version headings must be newest-first',
      section_order_error('''
1.8.0:
Likely next tasks:
1.9.0:
Reminders:
'''))


if __name__ == '__main__':
  unittest.main()
