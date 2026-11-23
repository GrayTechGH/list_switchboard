"""Checkpoint implementation and verification of audited update candidates.

The original queue is retained even after flags or candidate decisions change,
so an interrupted implementation cannot disappear from the remaining work.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from _dev_tools.generate_import_list_catalog import catalog_rows, write_catalog
from _dev_tools.import_update_audit import atomic_write_text, load_records as audit_records
from _dev_tools.audit_import_updates import record_decision

DEFAULT_LEDGER = ROOT / '_dev_tools' / 'import_update_implementation.json'
STATUSES = ('pending', 'in_progress', 'awaiting_live_verification', 'complete', 'rejected')


def timestamp():
  return datetime.now(timezone.utc).isoformat(timespec='seconds')


def load_ledger(path=DEFAULT_LEDGER):
  data = json.loads(Path(path).read_text(encoding='utf-8'))
  if not isinstance(data, dict) or data.get('schema_version') != 1:
    raise ValueError('Unsupported implementation ledger schema.')
  records = data.get('recipes')
  if not isinstance(records, dict):
    raise ValueError('Implementation recipes must be keyed by source_id.')
  deferred = data.get('deferred_recipes', {})
  if not isinstance(deferred, dict) or any(
      not isinstance(sid, str) or not isinstance(item, dict) for sid, item in deferred.items()):
    raise ValueError('Deferred recipes must be keyed by source_id.')
  if set(deferred) & set(records):
    raise ValueError('A recipe cannot be both active and deferred.')
  for source_id, record in records.items():
    if not isinstance(source_id, str) or not isinstance(record, dict):
      raise ValueError('Invalid implementation record.')
    if record.get('status') not in STATUSES:
      raise ValueError(f'{source_id}: invalid implementation status.')
  return data


def save_ledger(data, path=DEFAULT_LEDGER):
  atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def initialize(path=DEFAULT_LEDGER, rows=None):
  rows = catalog_rows() if rows is None else rows
  if Path(path).exists():
    data = load_ledger(path)
  else:
    data = {'schema_version': 1, 'created_at': timestamp(), 'recipes': {}}
    progress = ROOT / '_dev_tools' / 'import_progress_status.json'
    data['manual_ledger_sha256'] = hashlib.sha256(progress.read_bytes()).hexdigest()
    data['existing_updates'] = [r['source_id'] for r in rows if r['Updates'] == 'Yes']
  changed = False
  for row in rows:
    if (row['Update candidate'] == 'Yes' and row['Updates'] == 'No'
        and row['source_id'] not in data['recipes']
        and row['source_id'] not in data.get('deferred_recipes', {})):
      data['recipes'][row['source_id']] = {
        'status': 'pending', 'registry_index_at_start': int(row['registry_index']),
        'name': row['name'], 'updated_at': timestamp(), 'history': [],
      }
      changed = True
  if changed or not Path(path).exists():
    save_ledger(data, path)
  return data


def verification_report(path, kind):
  path = Path(path)
  data = json.loads(path.read_text(encoding='utf-8'))
  if data.get('kind') != kind or data.get('passed') is not True:
    raise ValueError(f'{kind} verification has not passed: {path}')
  if kind == 'live':
    if data.get('runtime') != 'calibre' or data.get('isolated') is not True:
      raise ValueError('Live verification must use isolated Calibre.')
    if data.get('entries_equal') is not True or data.get('repeat_equal') is not True:
      raise ValueError('Live updated/repeated entries must match the full reference.')
    if data.get('separate_recovery'):
      if data.get('recovery_entries_equal') is not True or type(data.get('recovery_requests')) is not int or data['recovery_requests']<0:
        raise ValueError('Separate missing-cache recovery must have matched the full reference with measured requests.')
    full, update, repeat = (data.get(key) for key in
      ('full_requests', 'update_requests', 'repeat_requests'))
    if (any(type(value) is not int for value in (full, update, repeat)) or
        not 0 <= update < full or not 0 <= repeat < full):
      raise ValueError('Live update and repeat must demonstrate fewer source requests.')
    if not (type(data.get('stale_entries')) is int and type(data.get('entries')) is int
        and 0 <= data['stale_entries'] < data['entries']):
      raise ValueError('Live verification must recover actual missing cached entries.')
  return data


def record(source_id, state, reason, source_paths=(), changed_code=(), evidence=(),
           tests=None, live=None, path=DEFAULT_LEDGER, rows=None, sync=True):
  if state not in STATUSES or not reason.strip():
    raise ValueError('A valid state and reason are required.')
  rows = catalog_rows() if rows is None else rows
  data = initialize(path, rows)
  if source_id not in data['recipes']:
    raise ValueError(f'Not in the implementation queue: {source_id}')
  row = next((r for r in rows if r['source_id'] == source_id), None)
  if row is None:
    raise ValueError(f'Recipe is no longer registered: {source_id}')
  item = dict(data['recipes'][source_id])
  if item['status'] in ('complete', 'rejected') and state != item['status']:
    raise ValueError('Completed records require explicit code/evidence review before reopening.')
  if state in ('complete', 'rejected') and (not source_paths or not evidence):
    raise ValueError('Final decisions need source paths and inspected evidence.')
  if state == 'complete':
    if row['Updates'] != 'Yes' or not changed_code or not tests or not live:
      raise ValueError('Completion needs an enabled flag, changed code and both verification reports.')
    for kind, report_path in (('automated', tests), ('live', live)):
      result = verification_report(report_path, kind)
      if result.get('source_id') != source_id:
        raise ValueError(f'{kind} report belongs to a different recipe.')
    item['automated_report'], item['live_report'] = str(tests), str(live)
  if state == 'rejected' and row['Updates'] == 'Yes':
    raise ValueError('Disable advertised update support before rejecting a recipe.')
  item.update(status=state, reason=reason, source_paths=list(source_paths),
    changed_code=list(changed_code), evidence=list(evidence), updated_at=timestamp())
  item['history'] = list(item.get('history', ())) + [
    {'status': state, 'reason': reason, 'at': item['updated_at']}]
  data['recipes'][source_id] = item
  # Commit the decision first. sync_catalog repairs the dependent audit/CSV
  # views if replacement fails, without dropping the original queue membership.
  save_ledger(data, path)
  if sync:
    sync_catalog(data)
  return item


def sync_catalog(data):
  audited = audit_records()
  for source_id, item in data['recipes'].items():
    if item['status'] == 'rejected' and audited.get(source_id, {}).get('candidate') != 'No':
      record_decision(source_id, 'No', item['reason'], ' | '.join(item['source_paths']),
        item['evidence'], replace=True)
  write_catalog()
  write_progress_doc(data)


def write_progress_doc(data, path=ROOT / '_docs' / 'UPDATE_IMPLEMENTATION_RESULTS.md'):
  counts = {state:sum(r['status']==state for r in data['recipes'].values()) for state in STATUSES}
  deferred = data.get('deferred_recipes') or {}
  original_count = data.get('original_queue_size', len(data['recipes']))
  lines = ['# Update Implementation Progress', '',
    'Generated from `_dev_tools/import_update_implementation.json`; do not edit this view by hand.', '',
    f"Original implementation queue: {original_count}; current queue: {len(data['recipes'])} recipes. "
    f"Complete: {counts['complete']}; rejected: {counts['rejected']}; "
    f"in progress: {counts['in_progress']}; awaiting live verification: {counts['awaiting_live_verification']}; "
    f"pending: {counts['pending']}.", '',
    'Existing support at the start: ' + ', '.join(data.get('existing_updates') or []) + '.', '',
    *([f"User-deferred future recipes: {len(deferred)}. "
      'Their history is archived separately and future work is tracked in `_docs/TASKS.md`.', ''] if deferred else []),
    '| Recipe | Status | Entries | Full requests | Update | Repeat | Separate recovery |',
    '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
  for source_id,item in data['recipes'].items():
    if item['status']=='pending':
      continue
    live = {}
    if item.get('live_report'):
      report_path = Path(item['live_report'])
      if not report_path.is_absolute():
        report_path = ROOT / report_path
      try:
        live = json.loads(report_path.read_text(encoding='utf-8'))
      except (OSError,ValueError):
        live = {'entries':'evidence unavailable'}
    values = [source_id,item['status']] + [str(live.get(key,'-')) for key in
      ('entries','full_requests','update_requests','repeat_requests','recovery_requests')]
    lines.append('| ' + ' | '.join(value.replace('|','\\|') for value in values) + ' |')
  lines.extend(['', 'Counts include source-request attempts observed by the live probe; native HTTPS recovery '
    'is captured separately where used. Site retries can make these counts vary between runs.', '',
    'Whole-snapshot recipes can measure missing-cache recovery separately from ordinary/repeated updates. '
    'That recovery must reproduce the full entries, and its actual request cost is shown above.', '',
    'Each completed recipe has automated and isolated-live evidence linked from its ledger record. '
    'Current/upcoming data remains refreshed; manual QA statuses are independent.', '',
    'Resume:', '', '```powershell',
    '.\\.venv\\Scripts\\python.exe _dev_tools/implement_import_updates.py --next',
    '.\\.venv\\Scripts\\python.exe _dev_tools/implement_import_updates.py --status', '```', ''])
  atomic_write_text(path,'\n'.join(lines))


def report(data, rows=None):
  rows = catalog_rows() if rows is None else rows
  ordered = [dict(row, implementation=data['recipes'][row['source_id']])
    for row in rows if row['source_id'] in data['recipes']]
  unfinished = [r for r in ordered if r['implementation']['status'] not in ('complete', 'rejected')]
  interrupted = [r for r in unfinished if r['implementation']['status'] != 'pending']
  return {
    'total': len(data['recipes']),
    'deferred': len(data.get('deferred_recipes') or {}),
    **{state: sum(r['status'] == state for r in data['recipes'].values()) for state in STATUSES},
    'next': (interrupted or unfinished or [None])[0],
    'next_pending': next((r for r in unfinished if r['implementation']['status'] == 'pending'), None),
  }


def main():
  p = argparse.ArgumentParser(description=__doc__)
  a = p.add_mutually_exclusive_group(required=True)
  a.add_argument('--init', action='store_true')
  a.add_argument('--next', action='store_true')
  a.add_argument('--next-pending', action='store_true')
  a.add_argument('--status', action='store_true')
  a.add_argument('--sync', action='store_true')
  a.add_argument('--record')
  p.add_argument('--state', choices=STATUSES)
  p.add_argument('--reason')
  p.add_argument('--source-path', action='append', default=[])
  p.add_argument('--changed-code', action='append', default=[])
  p.add_argument('--evidence', action='append', default=[])
  p.add_argument('--tests', type=Path)
  p.add_argument('--live', type=Path)
  p.add_argument('--ledger', type=Path, default=DEFAULT_LEDGER)
  args = p.parse_args()
  if args.record:
    if not args.state or not args.reason:
      p.error('--record requires --state and --reason')
    record(args.record, args.state, args.reason, args.source_path, args.changed_code,
      args.evidence, args.tests, args.live, args.ledger)
  data = initialize(args.ledger)
  if args.sync or args.next or args.next_pending:
    sync_catalog(data)
  result = report(data)
  print(json.dumps(result['next'] if args.next else result['next_pending']
    if args.next_pending else {k:v for k,v in result.items() if k not in ('next','next_pending')}, indent=2))


if __name__ == '__main__':
  main()
