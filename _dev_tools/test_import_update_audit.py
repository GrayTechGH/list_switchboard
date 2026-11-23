"""Checkpoint, regeneration and interruption contracts for update reviews."""

import csv
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from _dev_tools.audit_import_updates import main, record_decision, status
from _dev_tools.generate_import_list_catalog import catalog_rows, write_catalog
from _dev_tools.import_update_audit import atomic_write_text, load_records


def recipe(source_id, name=None, updates=False):
  return SimpleNamespace(source_id=source_id, NAME=name or source_id, order=1,
    options={}, display_url=f'https://example.com/{source_id}',
    SUPPORTS_INCREMENTAL_UPDATE=updates, get_filter_list=lambda: (),
    source_choices=lambda: ({'label': 'Automatic', 'value': 'automatic'},))


class ImportUpdateAuditTests(unittest.TestCase):

  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.folder = Path(self.temp.name)
    self.ledger = self.folder / 'audit.json'
    self.output = self.folder / 'catalog.csv'
    self.progress = self.folder / 'progress.json'
    self.progress.write_text(json.dumps({'recipes': [
      {'source_id': 'first', 'manual_status': 'passed'},
      {'source_id': 'second', 'manual_status': 'not_checked'},
    ]}), encoding='utf-8')
    self.fetchers = (recipe('first', updates=True), recipe('second'))
    self.generate()

  def generate(self, fetchers=None):
    return write_catalog(self.output, self.fetchers if fetchers is None else fetchers,
      self.progress, self.ledger)

  def read_csv(self):
    with self.output.open(encoding='utf-8-sig', newline='') as source:
      return list(csv.DictReader(source))

  def record(self, source_id='first', candidate='Yes', **kwargs):
    return record_decision(source_id, candidate,
      'Reuse settled year pages after checking the overview.',
      'Official archive', ['parser/example.py::year_pages'],
      ledger_path=self.ledger, output_path=self.output,
      progress_status_path=self.progress, fetchers=self.fetchers, **kwargs)

  def test_decisions_survive_regeneration_without_other_column_changes(self):
    before = self.read_csv()
    progress = self.progress.read_bytes()
    self.record()
    self.record('second', 'No')
    self.generate()
    after = self.read_csv()
    self.assertEqual(['Yes', 'No'], [row['Update candidate'] for row in after])
    for left, right in zip(before, after):
      self.assertEqual({k: v for k, v in left.items() if k != 'Update candidate'},
        {k: v for k, v in right.items() if k != 'Update candidate'})
    self.assertEqual(progress, self.progress.read_bytes())
    contents = self.output.read_bytes()
    self.generate()
    self.assertEqual(contents, self.output.read_bytes())

  def test_source_ids_preserve_decisions_after_reorder_and_new_rows_are_blank(self):
    self.record()
    self.record('second', 'No')
    self.generate((self.fetchers[1], recipe('new'), self.fetchers[0]))
    self.assertEqual([('second', 'No'), ('new', ''), ('first', 'Yes')],
      [(r['source_id'], r['Update candidate']) for r in self.read_csv()])
    self.generate((self.fetchers[1],))
    self.assertIn('first', load_records(self.ledger))

  def test_interrupted_csv_update_is_repaired_from_committed_ledger(self):
    before = self.output.read_bytes()
    with patch('_dev_tools.audit_import_updates.write_catalog', side_effect=OSError('locked')):
      with self.assertRaises(OSError):
        self.record()
    self.assertEqual(before, self.output.read_bytes())
    self.assertEqual('Yes', load_records(self.ledger)['first']['candidate'])
    self.generate()
    self.assertEqual('Yes', self.read_csv()[0]['Update candidate'])
    rows = catalog_rows(self.fetchers, self.progress, self.ledger)
    self.assertEqual('second', status(rows, load_records(self.ledger))['next']['source_id'])

  def test_failed_atomic_replace_preserves_previous_file_and_cleans_temp(self):
    before = self.output.read_bytes()
    with patch('_dev_tools.import_update_audit.os.replace', side_effect=OSError('locked')):
      with self.assertRaises(OSError):
        atomic_write_text(self.output, 'replacement')
    self.assertEqual(before, self.output.read_bytes())
    self.assertEqual([], list(self.folder.glob('*.tmp')))

  def test_failed_ledger_commit_does_not_change_csv(self):
    before = self.output.read_bytes()
    with patch('_dev_tools.audit_import_updates.write_records', side_effect=OSError('locked')):
      with self.assertRaises(OSError):
        self.record()
    self.assertFalse(self.ledger.exists())
    self.assertEqual(before, self.output.read_bytes())

  def test_discontinued_rows_require_no_including_confirmed_retired_sources(self):
    self.fetchers = (recipe('first', 'First (discontinued)'), recipe('second'))
    with self.assertRaisesRegex(ValueError, 'discontinued lists must be No'):
      self.record()
    self.record(candidate='No')
    with self.assertRaisesRegex(ValueError, 'discontinued lists must be No'):
      self.record('second', 'Yes', discontinued=True)
    self.record('second', 'No', discontinued=True)
    self.assertTrue(load_records(self.ledger)['second']['discontinued'])

  def test_unresolved_stays_blank_and_does_not_count_as_completed(self):
    self.record(candidate='')
    self.record('second', 'No')
    report = status(catalog_rows(self.fetchers, self.progress, self.ledger),
      load_records(self.ledger))
    self.assertEqual((1, 1, 1), (report['completed'], report['pending'], report['unresolved']))
    self.assertEqual('first', report['next']['source_id'])
    self.assertEqual('', self.read_csv()[0]['Update candidate'])
    self.record(candidate='Yes')
    self.assertEqual('Yes', self.read_csv()[0]['Update candidate'])

  def test_newly_discontinued_recipe_can_correct_previous_yes(self):
    self.record()
    self.fetchers = (recipe('first', 'First (discontinued)'), recipe('second'))
    with self.assertRaisesRegex(ValueError, 'discontinued lists must be No'):
      self.generate()
    self.record(candidate='No', replace=True)
    self.assertEqual('No', self.read_csv()[0]['Update candidate'])
    self.assertTrue(load_records(self.ledger)['first']['discontinued'])

  def test_corrupt_or_invalid_ledger_cannot_clear_csv(self):
    self.record()
    before = self.output.read_bytes()
    for contents in ('{', '{"schema_version":2,"recipes":{}}',
        '{"schema_version":1,"recipes":{"first":{"candidate":"maybe"}}}',
        '{"schema_version":1,"recipes":{"first":{"candidate":["Yes"]}}}'):
      with self.subTest(contents=contents):
        self.ledger.write_text(contents, encoding='utf-8')
        with self.assertRaises(ValueError):
          self.generate()
        self.assertEqual(before, self.output.read_bytes())

  def test_unknown_recipe_and_unrequested_replacement_are_rejected(self):
    with self.assertRaisesRegex(ValueError, 'Unknown registered'):
      self.record('missing')
    self.record()
    with self.assertRaisesRegex(ValueError, 'already reviewed'):
      self.record(candidate='No')
    self.record(candidate='No', replace=True)
    self.assertEqual('No', self.read_csv()[0]['Update candidate'])

  def test_record_requires_evidence_and_compatible_values_before_writing(self):
    before = self.output.read_bytes()
    for candidate, evidence in (('maybe', ['file.py']), ('Yes', [])):
      with self.subTest(candidate=candidate, evidence=evidence), self.assertRaises(ValueError):
        record_decision('first', candidate, 'Reason', 'Official', evidence,
          ledger_path=self.ledger, output_path=self.output,
          progress_status_path=self.progress, fetchers=self.fetchers)
    self.assertFalse(self.ledger.exists())
    self.assertEqual(before, self.output.read_bytes())

  def test_cli_resume_repairs_csv_and_completion_has_no_next_row(self):
    with patch('_dev_tools.audit_import_updates.write_catalog', side_effect=OSError('locked')):
      with self.assertRaises(OSError):
        self.record()
    with patch('_dev_tools.generate_import_list_catalog.available_url_fetchers',
        return_value=self.fetchers):
      output = io.StringIO()
      with redirect_stdout(output):
        main(['--next', '--ledger', str(self.ledger), '--output', str(self.output)])
      self.assertEqual('second', json.loads(output.getvalue())['source_id'])
      self.assertEqual('Yes', self.read_csv()[0]['Update candidate'])
      self.record('second', 'No')
      output = io.StringIO()
      with redirect_stdout(output):
        main(['--next', '--ledger', str(self.ledger), '--output', str(self.output)])
      self.assertIsNone(json.loads(output.getvalue()))
      output = io.StringIO()
      with redirect_stdout(output):
        main(['--status', '--ledger', str(self.ledger), '--output', str(self.output)])
      report = json.loads(output.getvalue())
      self.assertEqual((2, 1, 1, 0, 0), (report['completed'], report['yes'],
        report['no'], report['pending'], report['unresolved']))


if __name__ == '__main__':
  unittest.main()
