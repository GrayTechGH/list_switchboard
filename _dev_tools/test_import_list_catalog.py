"""Regression coverage for the built-in import-list CSV catalog."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from _dev_tools.generate_import_list_catalog import FIELDNAMES, write_catalog
from url_fetcher import available_url_fetchers


class ImportListCatalogTests(unittest.TestCase):

  def test_catalog_covers_registry_with_stable_columns(self):
    fetchers = available_url_fetchers()
    with tempfile.TemporaryDirectory() as folder:
      status_path = Path(folder) / 'progress.json'
      status_path.write_text(json.dumps({
        'recipes': [{
          'source_id': fetchers[0].source_id,
          'manual_status': 'passed',
        }],
      }), encoding='utf-8')
      output_path, count = write_catalog(
        Path(folder) / 'lists.csv',
        fetchers=fetchers,
        progress_status_path=status_path)
      with output_path.open(encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source)
        rows = list(reader)

    self.assertEqual(list(FIELDNAMES), reader.fieldnames)
    self.assertEqual('Manual Test', reader.fieldnames[-1])
    self.assertEqual(len(fetchers), count)
    self.assertEqual(len(fetchers), len(rows))
    self.assertEqual(
      [fetcher.source_id for fetcher in fetchers],
      [row['source_id'] for row in rows])
    self.assertEqual(
      [str(index) for index in range(1, len(rows) + 1)],
      [row['registry_index'] for row in rows])
    self.assertEqual(len(rows), len({row['source_id'] for row in rows}))
    self.assertEqual('passed', rows[0]['Manual Test'])
    self.assertTrue(all(
      row['Manual Test'] == 'not_checked' for row in rows[1:]))

  def test_catalog_exposes_discontinued_and_matching_metadata(self):
    with tempfile.TemporaryDirectory() as folder:
      output_path, _count = write_catalog(Path(folder) / 'lists.csv')
      with output_path.open(encoding='utf-8-sig', newline='') as source:
        rows = {
          row['source_id']: row
          for row in csv.DictReader(source)
        }

    discontinued = rows['big_library_read']
    self.assertEqual('true', discontinued['discontinued'])
    self.assertEqual('false', discontinued['match_series'])
    self.assertIn('Online Community Book Clubs', discontinued['filter_categories'])
    self.assertEqual('true', discontinued['automatic_source_only'])

    series_recipe = rows['aurealis_sara_douglass_book_series_award']
    self.assertEqual('true', series_recipe['match_series'])
    self.assertEqual('true', series_recipe['requires_series_matching'])


if __name__ == '__main__':
  unittest.main()
