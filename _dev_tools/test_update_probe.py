import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from _dev_tools.verify_import_updates import launch, write_json, worker_batch, missing_source_fixture,capture_payload


class UpdateProbeTests(unittest.TestCase):

  def test_transport_fixture_checks_remain_active_with_optimized_python(self):
    import subprocess
    import sys
    result = subprocess.run([sys.executable, '-O', '-c',
      'from _dev_tools.verify_wayback_spacing import require; require(False, "invalid pacing")'],
      cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    self.assertNotEqual(0, result.returncode)
    self.assertIn('invalid pacing', result.stderr)

  def test_pdf_captures_preserve_every_byte_without_windows_newline_translation(self):
    data=b'%PDF-1.4\r\n'+bytes(range(256))+b'\r\n\r\n\r'
    with tempfile.TemporaryDirectory() as folder:
      for index,payload in enumerate((data,data.decode('latin-1'))):
        captured=capture_payload(Path(folder)/f'capture-{index}',payload)
        self.assertEqual('.pdf',captured.suffix)
        self.assertEqual(data,captured.read_bytes())

  def test_text_capture_does_not_change_line_endings(self):
    text='<html>one\r\ntwo\nthree\r</html>'
    with tempfile.TemporaryDirectory() as folder:
      path=capture_payload(Path(folder)/'page',text)
      self.assertEqual(text,path.read_bytes().decode('utf-8'))

  def run_probe(self, reports):
    with tempfile.TemporaryDirectory() as folder:
      root = Path(folder)
      arguments = argparse.Namespace(output=root, recipe='test',
        source_choice='automatic', baseline_only=False)
      configs = []
      def call(command, env, cwd):
        output = Path(command[command.index('--output') + 1])
        output.mkdir(parents=True, exist_ok=True)
        report = reports[len(configs)]
        configs.append(env['CALIBRE_CONFIG_DIRECTORY'])
        write_json(output / 'live.json', report)
        return 0 if report['passed'] else 1
      with patch('_dev_tools.verify_import_updates.subprocess.call', side_effect=call):
        code = launch(arguments)
      return code, json.loads((root / 'live.json').read_text()), configs

  def test_changed_source_retries_once_and_links_actual_successful_evidence(self):
    code, report, configs = self.run_probe([
      {'passed': False, 'retryable_source_change': True},
      {'passed': True, 'entries_equal': True},
    ])
    self.assertEqual(0, code)
    self.assertTrue(report['passed'])
    self.assertTrue(report['source_change_retry'])
    self.assertTrue(report['verification_directory'].endswith('source-change-retry'))
    self.assertEqual(2, len(set(configs)))

  def test_second_comparison_failure_is_retained_without_another_retry(self):
    code, report, configs = self.run_probe([
      {'passed': False, 'retryable_source_change': True},
      {'passed': False, 'retryable_source_change': True},
    ])
    self.assertEqual(1, code)
    self.assertFalse(report['passed'])
    self.assertEqual(2, len(configs))

  def test_success_or_transport_failure_does_not_trigger_source_change_retry(self):
    for report in ({'passed': True}, {'passed': False, 'error': 'offline'}):
      code, result, configs = self.run_probe([report])
      self.assertEqual(int(not report['passed']), code)
      self.assertEqual(report, result)
      self.assertEqual(1, len(configs))

  def test_batch_keeps_per_recipe_reports_and_closes_shared_runtime(self):
    from unittest.mock import Mock
    with tempfile.TemporaryDirectory() as folder:
      root, core, owners = Path(folder), Mock(), []
      args = argparse.Namespace(output=root, recipe='one', also_recipe=['two'], baseline_only=False)
      def fake_worker(child, shared_owner=None):
        owners.append(shared_owner)
        shared_owner['core'] = core
        child.output.mkdir(parents=True, exist_ok=True)
        write_json(child.output / 'live.json', {'source_id': child.recipe, 'passed': child.recipe == 'one'})
        return int(child.recipe != 'one')
      with patch('_dev_tools.verify_import_updates.worker', side_effect=fake_worker):
        self.assertEqual(1, worker_batch(args))
      self.assertIs(owners[0], owners[1])
      core.close_camoufox_transport.assert_called_once()
      reports = json.loads((root / 'batch.json').read_text())
      self.assertEqual(['one', 'two'], [r['source_id'] for r in reports])
      self.assertEqual([0, 1], [r['exit_code'] for r in reports])

  def test_batch_source_change_retries_with_a_separate_owner(self):
    from unittest.mock import Mock
    with tempfile.TemporaryDirectory() as folder:
      root, core, owners = Path(folder), Mock(), []
      args = argparse.Namespace(output=root, recipe='one', also_recipe=[], baseline_only=False)
      def fake_worker(child, shared_owner=None):
        owners.append(shared_owner)
        if shared_owner is not None:
          shared_owner['core'] = core
        child.output.mkdir(parents=True, exist_ok=True)
        passed = shared_owner is None
        write_json(child.output / 'live.json', {'source_id': child.recipe, 'passed': passed,
          'retryable_source_change': not passed})
        return int(not passed)
      with patch('_dev_tools.verify_import_updates.worker', side_effect=fake_worker):
        self.assertEqual(0, worker_batch(args))
      self.assertIsNone(owners[1])
      self.assertTrue(json.loads((root / 'one/live.json').read_text())['passed'])
      self.assertTrue((root / 'one/live.first_attempt.json').exists())
      core.close_camoufox_transport.assert_called_once()

  def test_shared_work_fixture_removes_all_owning_units_to_create_actual_missing_entries(self):
    cache = {'entries': [{'title': value} for value in 'ABC'], 'incremental_state': {'units': {
      'one': {'complete': True, 'entry_indexes': [0, 1]},
      'two': {'complete': True, 'entry_indexes': [0, 2]},
      'three': {'complete': True, 'entry_indexes': [1, 2]},
    }}}
    stale, removed = missing_source_fixture(cache, ['three'])
    self.assertEqual(2, len(removed))
    self.assertLess(len(stale['entries']), len(cache['entries']))
    indexes = {i for unit in stale['incremental_state']['units'].values() for i in unit['entry_indexes']}
    self.assertEqual(set(range(len(stale['entries']))), indexes)


if __name__ == '__main__':
  unittest.main()
