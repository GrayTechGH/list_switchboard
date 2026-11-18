"""Verify a recipe in isolated Calibre, retaining diagnostic evidence.

Requires --live for actual source requests. Captures belong only in the chosen
development evidence directory, never in the user's runtime import cache.
"""

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
  path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def capture_payload(path,payload):
  """Keep PDF bytes lossless even when core transport returns Latin-1 text."""
  pdf=(isinstance(payload,bytes) and payload.startswith(b'%PDF-')) or (isinstance(payload,str) and payload.startswith('%PDF-'))
  path=path.with_suffix('.pdf' if pdf else ('.bin' if isinstance(payload,bytes) else '.txt'))
  if pdf:path.write_bytes(payload if isinstance(payload,bytes) else payload.encode('latin-1'))
  elif isinstance(payload,bytes):path.write_bytes(payload)
  else:path.write_text(str(payload),encoding='utf-8',newline='')
  return path


def without_unit(cache, key):
  """Make a consistent missing-history fixture without invalidating other units."""
  cache = deepcopy(cache)
  units = cache['incremental_state']['units']
  del units[key]
  kept = sorted({index for unit in units.values() for index in unit['entry_indexes']})
  remap = {old: new for new, old in enumerate(kept)}
  cache['entries'] = [cache['entries'][i] for i in kept]
  for unit in units.values():
    unit['entry_indexes'] = [remap[i] for i in unit['entry_indexes']]
  return cache


def missing_source_fixture(cache, preferred_units=()):
  """Remove real entries even when collapsed works belong to several units."""
  units = cache['incremental_state']['units']
  candidates = [key for key, unit in units.items()
    if unit.get('complete') and unit.get('entry_indexes')]
  preferred = [key for key in candidates if key in preferred_units]
  candidates = preferred or candidates
  if not candidates:
    raise ValueError('No complete parsed source unit is available for an older-cache fixture.')
  chosen = [candidates[-1]]
  stale = without_unit(cache, chosen[0])
  if len(stale['entries']) == len(cache['entries']):
    owners = [tuple(key for key, unit in units.items() if index in unit['entry_indexes'])
      for index in range(len(cache['entries']))]
    owners = [group for group in owners if group]
    if not owners:
      raise ValueError('Cached entries did not belong to source units.')
    chosen = list(min(owners, key=lambda group: (len(group),
      sum(len(units[key]['entry_indexes']) for key in group), group)))
    stale = cache
    for key in chosen:
      stale = without_unit(stale, key)
  if len(stale['entries']) >= len(cache['entries']):
    raise ValueError('The older-cache fixture did not remove any actual entries.')
  return stale, chosen


def worker(args, shared_owner=None):
  sys.path.insert(0, str(ROOT))
  package = types.ModuleType('calibre_plugins.list_switchboard')
  package.__path__ = [str(ROOT)]
  sys.modules['calibre_plugins.list_switchboard'] = package
  from qt.core import QApplication
  from calibre.constants import config_dir, cache_dir, numeric_version
  from calibre_plugins.list_switchboard.config import prefs
  from calibre_plugins.list_switchboard.main import ListSwitchboardCore
  from calibre_plugins.list_switchboard.url_fetcher import available_url_fetchers
  sandbox = Path(args.worker).resolve()
  for path in (config_dir, cache_dir()):
    if not Path(path).resolve().is_relative_to(sandbox):
      raise RuntimeError(f'Calibre state escaped temporary configuration: {path}')
  app = QApplication.instance() or QApplication([])
  prefs['camoufox_first_use_confirmed'] = True
  prefs['debug_browser_fallback_level'] = 0
  prefs['debug_force_fallback_level'] = 0
  core = shared_owner.get('core') if shared_owner is not None else None
  if core is None:
    core = ListSwitchboardCore(None, lambda **_kwargs: None)
    if shared_owner is not None:
      shared_owner['core'] = core
  core.update_import_progress = lambda *_a, **_kw: app.processEvents()
  # Batch recipes share browser lifetime, not a previous import's suppression.
  core._camoufox_disabled_reason = ''
  recipe = next(f for f in available_url_fetchers() if f.source_id == args.recipe)
  requests = []
  phase = 'full'
  phase_counts = {}
  args.output.mkdir(parents=True, exist_ok=True)

  def capture_request(url, call, kwargs, transport):
    number = phase_counts.get(phase, 0) + 1
    phase_counts[phase] = number
    item = {'url': url, 'options': kwargs, 'phase': phase, 'transport':transport}
    requests.append(item)
    print(f'{phase.upper()} {number} {url}', flush=True)
    try:
      payload = call(url, **kwargs)
    except Exception as err:
      item['error'] = str(err)
      raise
    file=capture_payload(args.output/f'{phase}-{number:04d}',payload)
    item['capture'] = file.name
    return payload

  def fetch(url, **kwargs):
    return capture_request(url,core.fetch_url,kwargs,'calibre_fetch')

  # Some official sources use Calibre's native secure-HTTPS recovery outside
  # the core callback. Count/capture those real attempts too, including redirects.
  fetcher_module = sys.modules[type(recipe).__module__]
  native_original = getattr(fetcher_module,'calibre_https_fetch',None)
  if callable(native_original):
    def native_capture(url,**kwargs):
      return capture_request(url,native_original,kwargs,'calibre_secure_https')
    fetcher_module.calibre_https_fetch = native_capture
  original_recipe_fetch = recipe.fetch_url

  def observed_recipe_fetch(callback,url):
    start = len(requests)
    payload = original_recipe_fetch(callback,url)
    for item in requests[start:]:
      if item.get('error'):
        item['recovered_by_fetcher'] = True
    return payload

  recipe.fetch_url = observed_recipe_fetch

  result = {'source_id': args.recipe, 'kind': 'live', 'runtime': 'calibre',
    'calibre_version': list(numeric_version), 'isolated': True, 'passed': False}
  try:
    parsed = recipe.fetch_and_parse(fetch, source_choice=args.source_choice)
    write_json(args.output / 'full.json', parsed)
    result.update(full_requests=len(requests), entries=len(parsed.get('entries', ())))
    if not parsed.get('entries'):
      raise ValueError('The complete import returned no entries.')
    print(f'BASELINE {result["entries"]} entries, {len(requests)} requests', flush=True)
    if args.baseline_only:
      return 0
    if any(item.get('error') and not item.get('recovered_by_fetcher') for item in requests):
      raise ValueError('Complete baseline had transport failures; verification remains pending.')
    units = (parsed.get('incremental_state') or {}).get('units') or {}
    if any(unit.get('complete') is not True for unit in units.values()):
      raise ValueError('Complete baseline has unresolved source units.')
    refresh_units = set(((parsed.get('incremental_state') or {}).get('discovery') or {}).get('refresh_units') or [])
    list_id = recipe.source_id
    cache_path = Path(core.import_cache_path(list_id))
    if not cache_path.resolve().is_relative_to(sandbox):
      raise RuntimeError('Import cache escaped the temporary configuration.')
    core.write_import_cache(list_id, parsed, recipe=recipe)
    cache = core.read_import_cache(list_id)
    stale, removed_units = missing_source_fixture(cache, refresh_units)
    core.write_json_file(str(cache_path), stale)
    write_json(args.output / 'stale.json', stale)
    separate_recovery=getattr(args,'separate_recovery',False)
    phase = 'recovery' if separate_recovery else 'update'
    updated = recipe.fetch_and_parse(fetch, source_choice=args.source_choice,
      cached_parsed=core.read_import_cache(list_id), incremental_update=True)
    if separate_recovery:
      write_json(args.output/'recovery.json',updated)
      result.update(separate_recovery=True,recovery_requests=phase_counts.get('recovery',0),
        recovery_entries_equal=updated['entries']==parsed['entries'])
      if not result['recovery_entries_equal']:
        result['retryable_source_change']=True
        raise ValueError('Missing-cache recovery did not match the complete reference.')
      core.write_import_cache(list_id,updated,recipe=recipe)
      phase='update'
      updated=recipe.fetch_and_parse(fetch,source_choice=args.source_choice,
        cached_parsed=core.read_import_cache(list_id),incremental_update=True)
    write_json(args.output / 'update.json', updated)
    result.update(update_requests=phase_counts.get('update',0),
      removed_unit=removed_units[-1], removed_units=removed_units, stale_entries=len(stale['entries']),
      entries_equal=updated['entries']==parsed['entries'])
    core.write_import_cache(list_id, updated, recipe=recipe)
    phase = 'repeat'
    repeated = recipe.fetch_and_parse(fetch, source_choice=args.source_choice,
      cached_parsed=core.read_import_cache(list_id), incremental_update=True)
    write_json(args.output / 'repeat.json', repeated)
    result.update(repeat_requests=phase_counts.get('repeat',0),
      repeat_equal=repeated['entries']==parsed['entries'])
    if any(item.get('error') and not item.get('recovered_by_fetcher') for item in requests):
      raise ValueError('Live source failures cannot certify an update implementation.')
    if not result['entries_equal'] or not result['repeat_equal']:
      result['retryable_source_change'] = True
      raise ValueError('Full/update/repeat parsed entries differ; inspect source captures.')
    if not (result['update_requests'] < result['full_requests'] and
        result['repeat_requests'] < result['full_requests']):
      raise ValueError('Update/repeat did not reduce the number of source requests.')
    result['passed'] = True
    print(json.dumps(result), flush=True)
    return 0
  except Exception as err:
    result['error'] = f'{type(err).__name__}: {err}'
    print(result['error'], flush=True)
    return 1
  finally:
    write_json(args.output / 'requests.json', requests)
    write_json(args.output / 'live.json', result)
    if shared_owner is None:
      core.close_camoufox_transport()
    recipe.fetch_url = original_recipe_fetch
    if callable(native_original):
      fetcher_module.calibre_https_fetch = native_original


def main():
  p = argparse.ArgumentParser(description=__doc__)
  p.add_argument('--recipe', required=True)
  p.add_argument('--also-recipe', action='append', default=[],
    help='Verify another recipe in the same isolated runtime, with independent fetches and reports.')
  p.add_argument('--output', type=Path, required=True)
  p.add_argument('--live', action='store_true')
  p.add_argument('--baseline-only', action='store_true')
  p.add_argument('--separate-recovery',action='store_true',
    help='Verify missing-cache recovery separately before measuring ordinary/repeated updates for whole-snapshot sources.')
  p.add_argument('--source-choice', default='automatic')
  p.add_argument('--worker', help=argparse.SUPPRESS)
  args = p.parse_args()
  args.output = args.output.resolve()
  if args.worker:
    if args.also_recipe:
      return worker_batch(args)
    return worker(args)
  if not args.live:
    p.error('--live is required for source requests')
  return launch(args)


def launch(args):
  """Retry one changing-source comparison with a fresh isolated baseline."""
  output = args.output
  for attempt in range(2):
    with tempfile.TemporaryDirectory(prefix='list-switchboard-update-') as folder:
      env = dict(os.environ)
      env['CALIBRE_CONFIG_DIRECTORY'] = str(Path(folder) / 'config')
      env['CALIBRE_CACHE_DIRECTORY'] = str(Path(folder) / 'cache')
      command = ['calibre-debug', '-e', str(Path(__file__).resolve()), '--',
        '--worker', folder, '--recipe', args.recipe, '--output', str(output),
        '--source-choice', args.source_choice]
      if args.baseline_only:
        command.append('--baseline-only')
      if getattr(args,'separate_recovery',False):command.append('--separate-recovery')
      for source_id in getattr(args, 'also_recipe', []):
        command.extend(('--also-recipe', source_id))
      code = subprocess.call(command, env=env, cwd=ROOT)
    if getattr(args, 'also_recipe', []):
      return code
    report_path = output / 'live.json'
    report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {}
    if attempt:
      if report:
        report.update(source_change_retry=True,
          verification_directory=str(output),
          previous_live_report=str(args.output / 'live.first_attempt.json'))
        write_json(args.output / 'live.json', report)
      return code
    if code == 0 or args.baseline_only or report.get('retryable_source_change') is not True:
      return code
    write_json(args.output / 'live.first_attempt.json', report)
    output = args.output / 'source-change-retry'
    print('Source changed during comparison; retrying once with a fresh isolated baseline.', flush=True)


def worker_batch(args):
  """Share only the isolated runtime/browser, never source responses or counters."""
  shared_owner, reports = {}, []
  args.output.mkdir(parents=True, exist_ok=True)
  try:
    for source_id in dict.fromkeys([args.recipe] + args.also_recipe):
      child = argparse.Namespace(**vars(args))
      child.recipe, child.also_recipe = source_id, []
      child.output = args.output / source_id
      code = worker(child, shared_owner=shared_owner)
      report = json.loads((child.output / 'live.json').read_text(encoding='utf-8'))
      if code and not args.baseline_only and report.get('retryable_source_change') is True:
        write_json(child.output / 'live.first_attempt.json', report)
        retry = argparse.Namespace(**vars(child))
        retry.output = child.output / 'source-change-retry'
        code = worker(retry)
        report = json.loads((retry.output / 'live.json').read_text(encoding='utf-8'))
        report.update(source_change_retry=True, verification_directory=str(retry.output),
          previous_live_report=str(child.output / 'live.first_attempt.json'))
        write_json(child.output / 'live.json', report)
      reports.append({'source_id': source_id, 'exit_code': code,
        'live_report': str(child.output / 'live.json')})
      write_json(args.output / 'batch.json', reports)
    return int(any(report['exit_code'] for report in reports))
  finally:
    if shared_owner.get('core') is not None:
      shared_owner['core'].close_camoufox_transport()


if __name__ == '__main__':
  raise SystemExit(main())
