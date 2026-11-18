"""Durable review decisions for the generated import catalog.

Maintenance notes:
- The ledger is authoritative; the CSV is a generated view. Commit the ledger
  before the CSV so a restarted audit can repair an interrupted regeneration.
- Malformed ledgers must fail visibly rather than erase completed reviews.
"""

import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT_PATH = ROOT / '_dev_tools' / 'import_update_candidates.json'


def atomic_write_text(path, text, encoding='utf-8'):
  path = Path(path)
  path.parent.mkdir(parents=True, exist_ok=True)
  temporary = None
  try:
    with tempfile.NamedTemporaryFile(
        mode='w', encoding=encoding, newline='', dir=path.parent,
        prefix=f'.{path.name}.', suffix='.tmp', delete=False) as output:
      temporary = Path(output.name)
      output.write(text)
      output.flush()
      os.fsync(output.fileno())
    os.replace(temporary, path)
  finally:
    if temporary is not None:
      temporary.unlink(missing_ok=True)


def validate_records(records):
  if not isinstance(records, dict):
    raise ValueError('Update audit recipes must be keyed by source_id.')
  for source_id, record in records.items():
    if not isinstance(source_id, str) or not source_id or not isinstance(record, dict):
      raise ValueError('Invalid update audit recipe record.')
    if record.get('candidate') not in ('', 'Yes', 'No'):
      raise ValueError(f'{source_id}: candidate must be Yes, No, or blank.')
    for field in ('reason', 'source_path'):
      if not isinstance(record.get(field), str) or not record[field].strip():
        raise ValueError(f'{source_id}: {field} is required.')
    evidence = record.get('evidence')
    if (not isinstance(evidence, list) or not evidence or
        any(not isinstance(item, str) or not item.strip() for item in evidence)):
      raise ValueError(f'{source_id}: inspected evidence is required.')
    if not isinstance(record.get('discontinued', False), bool):
      raise ValueError(f'{source_id}: discontinued must be a boolean.')
    if record.get('discontinued') and record['candidate'] != 'No':
      raise ValueError(f'{source_id}: discontinued lists must be No.')
  return records


def load_records(path=DEFAULT_AUDIT_PATH):
  path = Path(path)
  if not path.exists():
    return {}
  data = json.loads(path.read_text(encoding='utf-8'))
  if not isinstance(data, dict) or data.get('schema_version') != 1:
    raise ValueError('Unsupported update audit ledger schema.')
  return validate_records(data.get('recipes'))


def write_records(records, path=DEFAULT_AUDIT_PATH):
  validate_records(records)
  atomic_write_text(path, json.dumps({
    'schema_version': 1,
    'recipes': records,
  }, indent=2, ensure_ascii=False) + '\n')
