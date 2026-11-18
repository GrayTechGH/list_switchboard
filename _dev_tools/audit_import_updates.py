"""Record one reviewed recipe and immediately checkpoint its catalog row.

Run --next after an interruption: it repairs the CSV from the ledger before
showing the lowest unfinished registry index. Classification is a human/code
review; this tool does not infer candidates from URL or page counts.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from _dev_tools.generate_import_list_catalog import (  # noqa: E402
  DEFAULT_OUTPUT, PROGRESS_STATUS_PATH, available_url_fetchers, catalog_rows,
  write_catalog,
)
from _dev_tools.import_update_audit import (  # noqa: E402
  DEFAULT_AUDIT_PATH, load_records, write_records,
)


def status(rows, records):
  decisions = [records.get(row['source_id'], {}).get('candidate', '') for row in rows]
  pending = [row for row in rows if not records.get(row['source_id'], {}).get('candidate')]
  return {
    'total': len(rows),
    'completed': decisions.count('Yes') + decisions.count('No'),
    'yes': decisions.count('Yes'),
    'no': decisions.count('No'),
    'pending': len(pending),
    'unresolved': sum(row['source_id'] in records for row in pending),
    'next': pending[0] if pending else None,
  }


def record_decision(
    source_id, candidate, reason, source_path, evidence, discontinued=False,
    replace=False, ledger_path=DEFAULT_AUDIT_PATH, output_path=DEFAULT_OUTPUT,
    progress_status_path=PROGRESS_STATUS_PATH, fetchers=None):
  fetchers = tuple(fetchers if fetchers is not None else available_url_fetchers())
  fetcher = next((item for item in fetchers if item.source_id == source_id), None)
  if fetcher is None:
    raise ValueError(f'Unknown registered source_id: {source_id}')
  records = load_records(ledger_path)
  if records.get(source_id, {}).get('candidate') and not replace:
    raise ValueError(f'{source_id} is already reviewed; use --replace to correct it.')
  discontinued = discontinued or fetcher.NAME.endswith(' (discontinued)')
  if discontinued and candidate != 'No':
    raise ValueError(f'{source_id}: discontinued lists must be No.')
  records[source_id] = {
    'candidate': candidate,
    'reason': reason,
    'source_path': source_path,
    'evidence': list(evidence),
    'discontinued': discontinued,
    'reviewed_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
  }
  write_records(records, ledger_path)
  # The committed ledger survives a failed CSV replacement. --next/--sync
  # repairs the view before resuming; no completed review needs repeating.
  write_catalog(output_path, fetchers, progress_status_path, ledger_path)
  return records[source_id]


def main(argv=None):
  parser = argparse.ArgumentParser(description=__doc__)
  action = parser.add_mutually_exclusive_group(required=True)
  action.add_argument('--next', action='store_true')
  action.add_argument('--status', action='store_true')
  action.add_argument('--sync', action='store_true')
  action.add_argument('--record', metavar='SOURCE_ID')
  parser.add_argument('--candidate', choices=('Yes', 'No'))
  parser.add_argument('--unresolved', action='store_true')
  parser.add_argument('--reason')
  parser.add_argument('--source-path')
  parser.add_argument('--evidence', action='append')
  parser.add_argument('--discontinued', action='store_true')
  parser.add_argument('--replace', action='store_true')
  parser.add_argument('--ledger', type=Path, default=DEFAULT_AUDIT_PATH)
  parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
  args = parser.parse_args(argv)
  if args.record:
    if (bool(args.candidate) == args.unresolved or not args.reason or
        not args.source_path or not args.evidence):
      parser.error('--record needs --candidate or --unresolved, --reason, --source-path and --evidence')
    record_decision(args.record, args.candidate or '', args.reason,
      args.source_path, args.evidence, args.discontinued, args.replace,
      args.ledger, args.output)
  else:
    write_catalog(args.output, audit_status_path=args.ledger)
  rows = catalog_rows(audit_status_path=args.ledger)
  report = status(rows, load_records(args.ledger))
  print(json.dumps(report['next'] if args.next else report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
  main()
