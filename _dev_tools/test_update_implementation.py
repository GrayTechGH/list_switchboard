import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from _dev_tools import implement_import_updates as implementation


def row(source_id, updates='No', candidate='Yes', index=1):
  return {'source_id':source_id,'Updates':updates,'Update candidate':candidate,
    'registry_index':index,'name':source_id}


class ImplementationCheckpointTests(unittest.TestCase):

  def setUp(self):
    self.temp=tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.folder=Path(self.temp.name)
    self.ledger=self.folder/'implementation.json'
    self.rows=[row('first'),row('second',index=2),row('existing','Yes',index=3)]

  def record(self,source_id='first',state='in_progress',rows=None,**kwargs):
    return implementation.record(source_id,state,'Concrete reason',path=self.ledger,
      rows=self.rows if rows is None else rows,sync=False,**kwargs)

  def receipt(self,kind,**changes):
    data={'kind':kind,'passed':True,'source_id':'first'}
    if kind=='live':
      data.update(runtime='calibre',isolated=True,entries_equal=True,repeat_equal=True,
        full_requests=7,update_requests=2,repeat_requests=1,stale_entries=125,entries=126)
    data.update(changes)
    path=self.folder/(kind+'.json')
    path.write_text(json.dumps(data),encoding='utf-8')
    return path

  def test_initial_queue_skips_existing_support_and_retains_it_after_flag_changes(self):
    data=implementation.initialize(self.ledger,self.rows)
    self.assertEqual(['first','second'],list(data['recipes']))
    self.assertEqual(['existing'],data['existing_updates'])
    changed=[row('first','Yes'),row('second',index=2)]
    data=implementation.initialize(self.ledger,changed)
    self.assertEqual('first',implementation.report(data,changed)['next']['source_id'])

  def test_reordered_and_added_recipes_preserve_completed_checkpoint(self):
    self.record()
    rows=[self.rows[1],row('new',index=3),self.rows[0]]
    data=implementation.initialize(self.ledger,rows)
    self.assertEqual('in_progress',data['recipes']['first']['status'])
    self.assertEqual('pending',data['recipes']['new']['status'])
    self.assertEqual('first',implementation.report(data,rows)['next']['source_id'])

  def test_interrupted_catalog_write_keeps_durable_progress(self):
    with patch.object(implementation,'sync_catalog',side_effect=OSError('locked')):
      with self.assertRaises(OSError):
        implementation.record('first','in_progress','Working',path=self.ledger,rows=self.rows)
    self.assertEqual('in_progress',implementation.load_ledger(self.ledger)['recipes']['first']['status'])

  def test_completion_needs_enabled_flag_and_both_recipe_specific_receipts(self):
    tests=self.receipt('automated')
    live=self.receipt('live')
    evidence=dict(source_paths=['official'],changed_code=['parser/example.py'],
      evidence=['fixture'],tests=tests,live=live)
    with self.assertRaises(ValueError):
      self.record(state='complete',**evidence)
    rows=[row('first','Yes'),self.rows[1]]
    self.receipt('live',source_id='different')
    with self.assertRaises(ValueError):
      self.record(state='complete',rows=rows,**evidence)
    self.receipt('live')
    self.record(state='complete',rows=rows,**evidence)
    self.assertEqual('complete',implementation.load_ledger(self.ledger)['recipes']['first']['status'])

  def test_live_transport_failure_or_no_savings_cannot_complete(self):
    for changes in ({'passed':False},{'update_requests':7},{'isolated':False},
        {'entries_equal':False},{'repeat_equal':False},{'update_requests':-1},
        {'repeat_requests':7},{'stale_entries':126}):
      with self.subTest(changes=changes),self.assertRaises(ValueError):
        implementation.verification_report(self.receipt('live',**changes),'live')
    self.record(state='awaiting_live_verification')
    self.assertEqual('awaiting_live_verification',implementation.load_ledger(self.ledger)['recipes']['first']['status'])

  def test_snapshot_receipt_requires_separate_missing_cache_recovery_proof(self):
    proof={'separate_recovery':True,'recovery_requests':7,'recovery_entries_equal':True}
    self.assertTrue(implementation.verification_report(self.receipt('live',**proof),'live')['passed'])
    for invalid in ({'recovery_entries_equal':False},{'recovery_requests':-1},{'recovery_requests':None}):
      with self.assertRaises(ValueError):
        implementation.verification_report(self.receipt('live',**dict(proof,**invalid)),'live')
    with self.assertRaises(ValueError):
      implementation.verification_report(self.receipt('live',**dict(proof,update_requests=7)),'live')

  def test_rejection_repairs_audit_after_interruption_and_does_not_overwrite_other_records(self):
    self.record(state='rejected',source_paths=['official'],evidence=['parser/example.py'])
    data=implementation.load_ledger(self.ledger)
    with patch.object(implementation,'audit_records',return_value={'first':{'candidate':'Yes'}}),\
        patch.object(implementation,'record_decision') as update,\
        patch.object(implementation,'write_catalog') as generate,\
        patch.object(implementation,'write_progress_doc') as document:
      implementation.sync_catalog(data)
    self.assertEqual('first',update.call_args.args[0])
    self.assertEqual('No',update.call_args.args[1])
    generate.assert_called_once()
    document.assert_called_once_with(data)
    self.assertEqual('pending',data['recipes']['second']['status'])

  def test_progress_doc_uses_ledger_counts_and_live_evidence(self):
    self.record()
    data=implementation.load_ledger(self.ledger)
    data['recipes']['first']['live_report']=str(self.receipt('live'))
    target=self.folder/'progress.md'
    implementation.write_progress_doc(data,target)
    contents=target.read_text(encoding='utf-8')
    self.assertIn('in progress: 1',contents)
    self.assertIn('pending: 1',contents)
    self.assertIn('| first | in_progress | 126 | 7 | 2 | 1 |',contents)
    self.assertNotIn('| second |',contents)

  def test_invalid_ledger_fails_instead_of_resetting_progress(self):
    for contents in ('{','{"schema_version":2}',
        '{"schema_version":1,"recipes":{"first":{"status":"unknown"}}}'):
      self.ledger.write_text(contents,encoding='utf-8')
      with self.assertRaises(ValueError):
        implementation.initialize(self.ledger,self.rows)

  def test_user_deferred_future_recipe_is_separate_from_active_progress(self):
    data=implementation.initialize(self.ledger,self.rows)
    data['original_queue_size']=3
    data['deferred_recipes']={'future':{'reason':'User deferred until real data exists',
      'archive':'deferred.json','task':'_docs/TASKS.md'}}
    implementation.save_ledger(data,self.ledger)
    loaded=implementation.load_ledger(self.ledger)
    result=implementation.report(loaded,self.rows)
    self.assertEqual(2,result['total'])
    self.assertEqual(1,result['deferred'])
    self.assertEqual('first',result['next']['source_id'])
    target=self.folder/'progress.md'
    implementation.write_progress_doc(loaded,target)
    text=target.read_text(encoding='utf-8')
    self.assertIn('Original implementation queue: 3; current queue: 2',text)
    self.assertIn('User-deferred future recipes: 1',text)
    self.assertNotIn('| future |',text)
    restored=implementation.initialize(self.ledger,self.rows+[row('future',index=4)])
    self.assertNotIn('future',restored['recipes'])
    loaded['recipes']['future']={'status':'pending'}
    implementation.save_ledger(loaded,self.ledger)
    with self.assertRaises(ValueError):
      implementation.load_ledger(self.ledger)


if __name__=='__main__':
  unittest.main()
