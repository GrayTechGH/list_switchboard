"""Exercise the real Calibre browser's redirect processors without web traffic."""
import argparse
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
  """Keep verification active under Calibre's optimized Python."""
  if not condition:
    raise RuntimeError(message)


def worker(sandbox, output):
  sys.path.insert(0, str(ROOT))
  package = types.ModuleType('calibre_plugins.list_switchboard')
  package.__path__ = [str(ROOT)]
  sys.modules['calibre_plugins.list_switchboard'] = package
  from qt.core import QApplication
  from calibre.constants import config_dir, cache_dir, numeric_version
  from calibre_plugins.list_switchboard.main import ListSwitchboardCore
  from calibre_plugins.list_switchboard import wayback_policy as policy
  import mechanize
  for path in (config_dir, cache_dir()):
    require(Path(path).resolve().is_relative_to(Path(sandbox).resolve()), 'Calibre state escaped isolation')
  app = QApplication.instance() or QApplication([])
  now, calls, sleeps = [0.0], [], []
  policy.REQUEST_CLOCK = policy.WaybackRequestClock(clock=lambda: now[0])
  def pause(seconds, _message=''):
    sleeps.append(seconds)
    now[0] += seconds
  class OfflineHTTP(mechanize.HTTPHandler):
    handler_order = 100
    def http_open(self, request):
      url = request.get_full_url()
      calls.append({'url': url, 'time': now[0]})
      if url.endswith('/first'):
        return mechanize.make_response(b'redirect', [('Location', 'http://web.archive.org/second')], url, 302, 'Found')
      if url.endswith('/limited'):
        return mechanize.make_response(b'limited', [('Retry-After', '0')], url, 429, 'Limited')
      return mechanize.make_response(b'<html><title>Fixture</title><p>OK</p></html>', [('Content-Type', 'text/html')], url, 200, 'OK')
  cores = [ListSwitchboardCore(None, lambda **_kwargs: None) for _ in range(2)]
  for core in cores:
    core.sleep_with_events = pause
    browser = core.calibre_browser(core.fetch_headers())
    browser.add_handler(OfflineHTTP())
  try:
    first = cores[0].fetch_url('http://web.archive.org/first')
    second = cores[1].fetch_url('http://web.archive.org/third')
    require('OK' in first and 'OK' in second, 'Offline transport did not return fixture payloads')
    require([call['time'] for call in calls] == [0, 10, 20], calls)
    require(sleeps == [10, 10], sleeps)
    for index, expected_gap in enumerate((20, 40)):
      try:
        cores[0].fetch_url('http://web.archive.org/limited')
      except Exception as err:
        require(getattr(err, 'code', None) == 429, err)
      else:
        raise AssertionError('Expected HTTP 429')
      require(policy.REQUEST_CLOCK.interval == expected_gap, 'Incorrect exponential gap')
      cores[1].fetch_url('http://web.archive.org/after-limit-' + str(index))
    require([call['time'] for call in calls] == [0, 10, 20, 30, 50, 70, 110], calls)
    require(sleeps == [10, 10, 10, 20, 20, 40], sleeps)
    report = {'kind': 'calibre_offline_transport', 'passed': True,
      'calibre_version': list(numeric_version), 'isolated': True,
      'actual_external_requests': 0, 'calls': calls, 'waits': sleeps,
      'python_optimization': sys.flags.optimize,
      'make_response_signature': str(inspect.signature(mechanize.make_response))}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'calibre-spacing.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)
  finally:
    for core in cores:
      core.close_camoufox_transport()


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('--worker')
  parser.add_argument('--output', type=Path, required=True)
  args = parser.parse_args()
  if args.worker:
    worker(args.worker, args.output.resolve())
  else:
    with tempfile.TemporaryDirectory(prefix='list-switchboard-wayback-clock-') as folder:
      env = dict(os.environ, CALIBRE_CONFIG_DIRECTORY=str(Path(folder) / 'config'),
        CALIBRE_CACHE_DIRECTORY=str(Path(folder) / 'cache'))
      raise SystemExit(subprocess.call(['calibre-debug', '-e', str(Path(__file__).resolve()),
        '--', '--worker', folder, '--output', str(args.output.resolve())], env=env, cwd=ROOT))
