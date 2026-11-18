"""Probe one official archive index before committing to another full import."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types

ROOT = Path(__file__).resolve().parents[1]


def worker(sandbox, output):
  sys.path.insert(0, str(ROOT))
  package = types.ModuleType('calibre_plugins.list_switchboard')
  package.__path__ = [str(ROOT)]
  sys.modules['calibre_plugins.list_switchboard'] = package
  from qt.core import QApplication
  from calibre.constants import config_dir, cache_dir
  from calibre_plugins.list_switchboard.main import ListSwitchboardCore
  from calibre_plugins.list_switchboard.url_fetcher import booksellers_best as transport
  from calibre_plugins.list_switchboard.parser.booksellers_best import BOOKSELLERS_BEST_CDX_URLS
  from calibre_plugins.list_switchboard.parser.booksellers_best_updates import capture_index
  from calibre_plugins.list_switchboard import wayback_policy
  from _dev_tools.verify_import_updates import capture_payload, write_json
  for path in (config_dir, cache_dir()):
    if not Path(path).resolve().is_relative_to(Path(sandbox).resolve()):
      raise RuntimeError('Calibre state escaped the temporary configuration')
  app = QApplication.instance() or QApplication([])
  core = ListSwitchboardCore(None, lambda **_kwargs: None)
  core.update_import_progress = lambda *_args, **_kwargs: app.processEvents()
  recipe = transport.UrlFetcherBooksellersBestAward()
  recipe._wayback_sleep = lambda seconds: core.sleep_with_events(seconds, 'Waiting for the archive...')
  output.mkdir(parents=True, exist_ok=True)
  requests = []
  native = transport.calibre_https_fetch
  def observed(url, call, kwargs, name):
    item = {'url': url, 'transport': name, 'options': kwargs, 'start': time.time()}
    requests.append(item)
    print(name, url, flush=True)
    try:
      payload = call(url, **kwargs)
      item['capture'] = capture_payload(output / f'request-{len(requests):02d}', payload).name
      return payload
    except Exception as error:
      item['error'] = str(error)
      raise
  if native is not None:
    transport.calibre_https_fetch = lambda url, **kwargs: observed(url, native, kwargs, 'native')
  def legacy(url, **kwargs):
    return observed(url, core.fetch_url, kwargs, 'legacy')
  result = {'kind': 'archive_index_preflight', 'passed': False, 'isolated': True,
    'runtime': 'calibre', 'url': BOOKSELLERS_BEST_CDX_URLS[2]}
  try:
    source = recipe.fetch_url(legacy, result['url'])
    captures = capture_index(recipe.parser(), source)
    result.update(passed=True, discovered_captures=len(captures))
  except Exception as error:
    result.update(error=str(error), rate_limited=transport.archive_rate_limit(error) is not None)
  finally:
    result.update(requests=len(requests), next_gap_seconds=wayback_policy.REQUEST_CLOCK.interval)
    write_json(output / 'requests.json', requests)
    write_json(output / 'preflight.json', result)
    transport.calibre_https_fetch = native
    core.close_camoufox_transport()
  print(json.dumps(result), flush=True)
  return int(not result['passed'])


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('--worker')
  parser.add_argument('--output', type=Path, required=True)
  parser.add_argument('--live', action='store_true')
  args = parser.parse_args()
  if args.worker:
    raise SystemExit(worker(args.worker, args.output.resolve()))
  if not args.live:
    parser.error('--live is required')
  with tempfile.TemporaryDirectory(prefix='list-switchboard-index-check-') as sandbox:
    env = dict(os.environ, CALIBRE_CONFIG_DIRECTORY=str(Path(sandbox) / 'config'),
      CALIBRE_CACHE_DIRECTORY=str(Path(sandbox) / 'cache'))
    raise SystemExit(subprocess.call(['calibre-debug', '-e', str(Path(__file__).resolve()),
      '--', '--worker', sandbox, '--output', str(args.output.resolve())], env=env, cwd=ROOT))
