"""Exercise real plugin dialogs with temporary Calibre config and no database.

Launch with the repo venv. Only the explicitly labelled QA window is opened;
the ordinary Calibre application and its library are never launched.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://www.goodreads.com/choiceawards/best-books-2016'


def worker(args):
  sys.path.insert(0, str(ROOT))
  package = types.ModuleType('calibre_plugins.list_switchboard')
  package.__path__ = [str(ROOT)]
  sys.modules['calibre_plugins.list_switchboard'] = package
  from qt.core import QApplication, QDialog, QLabel, QPushButton, QPlainTextEdit, QVBoxLayout, QTimer
  from calibre.constants import config_dir, cache_dir
  from calibre_plugins.list_switchboard.config import prefs
  from calibre_plugins.list_switchboard.main import ListSwitchboardCore
  from calibre_plugins.list_switchboard.transport.camoufox import browser_operation
  from calibre_plugins.list_switchboard.errors import ImportCancelledError
  from calibre_plugins.list_switchboard.parser.goodreads_choice_awards import GoodreadsChoiceAwardsParser
  from calibre_plugins.list_switchboard.url_fetcher.goodreads_choice_transport import GoodreadsChoiceFetchPolicy

  sandbox = Path(args.worker).resolve()
  if any(not Path(path).resolve().is_relative_to(sandbox) for path in (config_dir, cache_dir())):
    raise RuntimeError('QA configuration escaped its sandbox')
  app = QApplication.instance() or QApplication([])
  app.setQuitOnLastWindowClosed(True)
  window = QDialog()
  window.setWindowTitle('List Switchboard isolated Camoufox QA')
  window.resize(760, 540)
  layout = QVBoxLayout(window)
  layout.addWidget(QLabel('Isolated dialog QA — temporary configuration; NO Calibre library or metadata writes.'))
  output = QPlainTextEdit()
  output.setReadOnly(True)
  messages = []

  def report(message):
    print(message, flush=True)
    messages.append(message)

  def drain():
    while messages:
      output.appendPlainText(messages.pop(0))

  core = ListSwitchboardCore(window, lambda **kw: None)
  core.debug_camoufox = report
  core.status_message = report

  def show_prefs():
    report('PREFERENCES ' + json.dumps({key: prefs.get(key) for key in (
      'debug_browser_fallback_level', 'debug_force_fallback_level',
      'debug_sections', 'camoufox_first_use_confirmed')}))

  def reset_consent():
    prefs['camoufox_first_use_confirmed'] = False
    report('First-use confirmation reset in temporary configuration only.')

  def fetch():
    try:
      core.import_progress = core.create_import_progress('Goodreads visual QA')
      core.begin_import_progress_phase(1, 3, 'Fetch, parse, and cache', 'Preparing Goodreads overview...')
      with browser_operation(core):
        parser = GoodreadsChoiceAwardsParser('Fiction')
        policy = GoodreadsChoiceFetchPolicy(core.fetch_url,
          lambda url: core.fetch_url(url, timeout=60), parser)
        html = policy.fetch(URL)
        report(f'FETCH accepted {len(html.encode("utf-8"))} bytes; '
          f'progress restored to {core.import_progress.minimum()}..{core.import_progress.maximum()}')
        if args.capture:
          args.capture.parent.mkdir(parents=True, exist_ok=True)
          args.capture.write_text(html, encoding='utf-8')
          report(f'Public HTML captured: {args.capture}')
      report('Browser operation closed. No metadata writes were available.')
    except ImportCancelledError as err:
      report('CANCELLED ' + str(err))
    except Exception as err:
      report('FETCH FAILED ' + str(err))
    finally:
      core.close_import_progress()
      show_prefs()
      drain()

  for text, callback in (
      ('Debug settings', core.show_debug_dialog),
      ('Fetch Goodreads overview', fetch),
      ('Reset first-use consent', reset_consent),
      ('Show saved preferences', show_prefs),
      ('Close QA', window.close)):
    button = QPushButton(text)
    button.clicked.connect(callback)
    layout.addWidget(button)
  layout.addWidget(output)
  timer = QTimer(window)
  timer.timeout.connect(drain)
  timer.start(150)
  if args.capture_only:
    prefs['camoufox_first_use_confirmed'] = True
    fetch()
    return 0
  show_prefs()
  window.show()
  try:
    return app.exec()
  finally:
    core.close_camoufox_transport()


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('--worker', help=argparse.SUPPRESS)
  parser.add_argument('--capture', type=Path, help='Opt-in public HTML capture outside runtime caches.')
  parser.add_argument('--capture-only', action='store_true')
  args = parser.parse_args()
  if args.worker:
    return worker(args)
  with tempfile.TemporaryDirectory(prefix='list-switchboard-ui-qa-') as folder:
    env = dict(os.environ)
    env['CALIBRE_CONFIG_DIRECTORY'] = str(Path(folder) / 'config')
    env['CALIBRE_CACHE_DIRECTORY'] = str(Path(folder) / 'cache')
    command = ['calibre-debug', '-e', str(Path(__file__).resolve()), '--', '--worker', folder]
    if args.capture:
      command.extend(('--capture', str(args.capture.resolve())))
    if args.capture_only:
      command.append('--capture-only')
    startupinfo = None
    if os.name == 'nt' and not args.capture_only:
      startupinfo = subprocess.STARTUPINFO()
      startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
      startupinfo.wShowWindow = 1
    return subprocess.call(command, env=env, cwd=ROOT, startupinfo=startupinfo)


if __name__ == '__main__':
  raise SystemExit(main())
