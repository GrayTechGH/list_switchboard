"""Build and validate the allowlisted List Switchboard Calibre plugin archive."""

from __future__ import annotations

import argparse
import re
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT_FILES = frozenset((
  '__init__.py',
  'config.py',
  'debug.py',
  'errors.py',
  'goodreads.py',
  'import_flow.py',
  'list_state.py',
  'main.py',
  'matching.py',
  'metadata.py',
  'plugin-import-name-list_switchboard.txt',
  'storage.py',
  'ui.py',
))
RUNTIME_DIRECTORIES = ('dialogs', 'images', 'parser', 'url_fetcher')
RUNTIME_SUFFIXES = frozenset(('.json', '.png', '.py'))
REQUIRED_MEMBERS = frozenset((
  '__init__.py',
  'images/icon.png',
  'parser/__init__.py',
  'parser/data/spsfc_results.json',
  'url_fetcher/__init__.py',
))
PROHIBITED_PARTS = frozenset(('.git', '__pycache__', '_dev_tools', '_docs'))
VERSION_RE = re.compile(r'^\s*version\s*=\s*\((\d+),\s*(\d+),\s*(\d+)\)', re.M)


def plugin_version(root=ROOT):
  """Read the release tuple without importing Calibre-only plugin modules."""
  source = (Path(root) / '__init__.py').read_text(encoding='utf-8')
  match = VERSION_RE.search(source)
  if match is None:
    raise ValueError('Could not find the plugin version tuple in __init__.py')
  return '.'.join(match.groups())


def package_members(root=ROOT):
  """Return sorted archive members from the explicit runtime allowlist."""
  root = Path(root)
  members = [root / name for name in RUNTIME_ROOT_FILES]
  for directory in RUNTIME_DIRECTORIES:
    base = root / directory
    members.extend(
      path for path in base.rglob('*')
      if path.is_file() and path.suffix.casefold() in RUNTIME_SUFFIXES
    )
  missing = [path for path in members if not path.is_file()]
  if missing:
    raise FileNotFoundError('Missing required runtime files: ' + ', '.join(map(str, missing)))
  return sorted(members, key=lambda path: path.relative_to(root).as_posix())


def build_plugin(output=None, root=ROOT):
  """Write a deterministic release archive containing only runtime assets."""
  root = Path(root)
  output = Path(output or root / f'ListSwitchboard-{plugin_version(root)}.zip')
  output.parent.mkdir(parents=True, exist_ok=True)
  with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in package_members(root):
      name = path.relative_to(root).as_posix()
      info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
      info.external_attr = 0o100644 << 16
      info.compress_type = zipfile.ZIP_DEFLATED
      archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
  smoke_check_package(output)
  return output


def smoke_check_package(path):
  """Reject archives missing runtime members or containing development residue."""
  with zipfile.ZipFile(path) as archive:
    members = archive.namelist()
  duplicates = sorted(name for name in set(members) if members.count(name) != 1)
  unexpected = sorted(
    name for name in members
    if any(part in PROHIBITED_PARTS for part in Path(name).parts)
    or name.endswith(('.bak', '.pyc', '.pyo', '.zip'))
  )
  missing = sorted(REQUIRED_MEMBERS - set(members))
  root_files = {name for name in members if '/' not in name}
  missing_root_files = sorted(RUNTIME_ROOT_FILES - root_files)
  if duplicates or unexpected or missing or missing_root_files:
    details = []
    if duplicates:
      details.append('duplicate members: ' + ', '.join(duplicates))
    if unexpected:
      details.append('development residue: ' + ', '.join(unexpected))
    if missing:
      details.append('missing required members: ' + ', '.join(missing))
    if missing_root_files:
      details.append('missing root files: ' + ', '.join(missing_root_files))
    raise ValueError('; '.join(details))
  return sorted(members)


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--output', type=Path, help='Archive path (defaults to ListSwitchboard-<version>.zip).')
  parser.add_argument('--check', type=Path, help='Validate an existing archive without building.')
  args = parser.parse_args()
  if args.check:
    members = smoke_check_package(args.check)
    print(f'Package check passed: {args.check} ({len(members)} files)')
    return
  output = build_plugin(args.output)
  print(f'Built and verified: {output}')


if __name__ == '__main__':
  main()
