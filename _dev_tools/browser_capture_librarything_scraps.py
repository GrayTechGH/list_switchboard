#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Capture LibraryThing award pages with a real browser session.

Maintenance notes:
- This script reuses `_dev_tools/Scraps Cache/librarything/awards.json` from
  `download_librarything_scraps.py`.
- Use a dedicated persistent browser profile so any challenge/session state
  stays outside the repo. Do not copy cookies into manifests or source files.
- Captured HTML is marked `html_browser`; challenge pages remain explicitly
  marked as `cloudflare_challenge`.
"""

import argparse
import datetime as _datetime
import html as _html
import json
import re
import subprocess
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = ROOT / '_dev_tools' / 'Scraps Cache' / 'librarything'
DEFAULT_PROFILE = Path('C:/tmp/librarything-browser-profile')


def utc_now():
  return _datetime.datetime.now(
    _datetime.UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def read_json(path, default):
  if not path.exists():
    return default
  return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, data):
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', encoding='utf-8')


class AwardLinkCollector(HTMLParser):

  def __init__(self):
    super().__init__(convert_charrefs=True)
    self._current = None
    self.links = []

  def handle_starttag(self, tag, attrs):
    if tag != 'a':
      return
    attrs = dict(attrs)
    href = attrs.get('href') or ''
    if '/award/' not in href:
      return
    self._current = {
      'href': href,
      'text': [],
    }

  def handle_data(self, data):
    if self._current is not None:
      self._current['text'].append(data)

  def handle_endtag(self, tag):
    if tag != 'a' or self._current is None:
      return
    text = ' '.join(part.strip() for part in self._current['text'] if part.strip())
    self.links.append({
      'href': self._current['href'],
      'text': re.sub(r'\s+', ' ', _html.unescape(text)).strip(),
    })
    self._current = None


def result_from_html(html, title='', final_url=''):
  text = html or ''
  lowered = text.casefold()
  title = (title or '').casefold()
  parsed_final_url = urlsplit(final_url or '')
  if parsed_final_url.netloc.endswith('librarything.com'):
    normalized_path = parsed_final_url.path.rstrip('/') or '/'
    if normalized_path == '/award':
      return 'librarything_award_index'
  if 'just a moment' in title:
    return 'cloudflare_challenge'
  if 'challenge-platform' in lowered or '__cf_chl_' in lowered:
    return 'cloudflare_challenge'
  if 'enable javascript and cookies to continue' in lowered:
    return 'cloudflare_challenge'
  if '<html' in lowered and 'librarything' in (lowered + (final_url or '').casefold()):
    return 'html_browser'
  if '<html' in lowered:
    return 'html_browser'
  return 'unknown_browser'


def award_family_id(url):
  path = urlsplit(url or '').path
  match = re.match(r'/award/(\d+)', path)
  return match.group(1) if match else ''


def extract_award_links_from_html(html, base_url):
  family_id = award_family_id(base_url)
  collector = AwardLinkCollector()
  collector.feed(html or '')
  seen = set()
  links = []
  for link in collector.links:
    absolute_url = urljoin(base_url, link['href'])
    if family_id and award_family_id(absolute_url) != family_id:
      continue
    key = (absolute_url, link['text'])
    if key in seen:
      continue
    seen.add(key)
    links.append({
      'text': link['text'],
      'url': absolute_url,
    })
  return links


def extract_cached_award_links(cache, awards):
  extracted = {}
  for item in awards:
    if item.get('result') != 'html_browser':
      continue
    relative = item.get('file')
    if not relative:
      continue
    target = cache / relative
    if not target.exists():
      continue
    html = target.read_text(encoding='utf-8', errors='ignore')
    base_url = item.get('browser_final_url') or item.get('url') or ''
    links = extract_award_links_from_html(html, base_url)
    if not links:
      continue
    extracted[relative] = {
      'browser_final_url': item.get('browser_final_url'),
      'name': item.get('name'),
      'source_url': item.get('url'),
      'links': links,
    }
  return extracted


class CDPSession:

  def __init__(self, websocket_url):
    import websocket

    self.ws = websocket.create_connection(websocket_url, timeout=15)
    self.next_id = 1

  def close(self):
    self.ws.close()

  def send(self, method, params=None):
    message_id = self.next_id
    self.next_id += 1
    self.ws.send(json.dumps({
      'id': message_id,
      'method': method,
      'params': params or {},
    }))
    while True:
      message = json.loads(self.ws.recv())
      if message.get('id') == message_id:
        if 'error' in message:
          raise RuntimeError(message['error'])
        return message.get('result', {})

  def wait_for_event(self, method, timeout_seconds=15):
    deadline = time.time() + timeout_seconds
    original_timeout = self.ws.gettimeout()
    self.ws.settimeout(1)
    try:
      while time.time() < deadline:
        try:
          message = json.loads(self.ws.recv())
        except Exception:
          continue
        if message.get('method') == method:
          return message.get('params', {})
    finally:
      self.ws.settimeout(original_timeout)
    return {}


def http_json(url):
  with urllib.request.urlopen(url, timeout=10) as response:
    return json.loads(response.read().decode('utf-8'))


def connect_cdp_page(port):
  endpoint = f'http://127.0.0.1:{port}/json'
  last_error = None
  for _attempt in range(30):
    try:
      targets = http_json(endpoint)
      page_target = next(
        (target for target in targets if target.get('type') == 'page'),
        targets[0] if targets else None)
      if page_target and page_target.get('webSocketDebuggerUrl'):
        session = CDPSession(page_target['webSocketDebuggerUrl'])
        session.send('Page.enable')
        session.send('Runtime.enable')
        return session
    except Exception as err:
      last_error = err
    time.sleep(1)
  raise SystemExit(f'Could not connect to Chrome DevTools at {endpoint}: {last_error}')


def cdp_eval(session, expression):
  result = session.send('Runtime.evaluate', {
    'expression': expression,
    'returnByValue': True,
  })
  return result.get('result', {}).get('value', '')


def cdp_page_state(session):
  html = cdp_eval(session, 'document.documentElement.outerHTML')
  title = cdp_eval(session, 'document.title')
  final_url = cdp_eval(session, 'location.href')
  return html, title, final_url


def selected_items(items, statuses, results, limit, names=()):
  selected = []
  status_filter = set(statuses or ())
  result_filter = set(results or ())
  name_filter = {name.casefold() for name in (names or ())}
  for item in items:
    if status_filter and item.get('status') not in status_filter:
      continue
    if result_filter and item.get('result') not in result_filter:
      continue
    if name_filter and (item.get('name') or '').casefold() not in name_filter:
      continue
    selected.append(item)
    if limit and len(selected) >= limit:
      break
  return selected


def update_summary(cache, awards):
  counts = {}
  for item in awards:
    result = item.get('result') or 'unknown'
    counts[result] = counts.get(result, 0) + 1
  write_json(cache / 'scrape_summary.json', {
    'downloaded_at_utc': utc_now(),
    'files': len(awards),
    'folder': 'librarything',
    'results': counts,
  })


def classify_existing(cache, awards):
  for item in awards:
    relative = item.get('file')
    if not relative:
      continue
    target = cache / relative
    if not target.exists():
      item['result'] = 'missing_file'
      continue
    html = target.read_text(encoding='utf-8', errors='ignore')
    item['result'] = result_from_html(
      html,
      title=item.get('browser_title', ''),
      final_url=item.get('browser_final_url', item.get('url', '')))
  return awards


def reuse_same_url_captures(cache, awards):
  donor_by_url = {}
  for item in awards:
    relative = item.get('file')
    url = item.get('url')
    if not relative or not url:
      continue
    target = cache / relative
    if item.get('result') == 'html_browser' and target.exists():
      donor_by_url.setdefault(url, item)

  for item in awards:
    relative = item.get('file')
    url = item.get('url')
    if not relative or not url or item.get('result') == 'html_browser':
      continue
    donor = donor_by_url.get(url)
    if donor is None:
      continue
    donor_target = cache / donor['file']
    target = cache / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(donor_target.read_text(encoding='utf-8'), encoding='utf-8')
    for field in (
        'browser_capture_method',
        'browser_captured_at_utc',
        'browser_final_url',
        'browser_status',
        'browser_title',
        'result'):
      if field in donor:
        item[field] = donor[field]
  return awards


def launch_normal_chrome(executable_path, profile, port, start_url):
  if not executable_path:
    raise SystemExit('--cdp-port requires --executable-path')
  return subprocess.Popen([
    executable_path,
    f'--remote-debugging-port={port}',
    f'--remote-allow-origins=http://127.0.0.1:{port}',
    f'--user-data-dir={profile}',
    '--no-first-run',
    '--no-default-browser-check',
    start_url,
  ], cwd=str(ROOT))


def wait_for_cdp_clearance(session, timeout_seconds):
  deadline = time.time() + timeout_seconds
  while True:
    html, title, final_url = cdp_page_state(session)
    status = result_from_html(html, title=title, final_url=final_url)
    if status != 'cloudflare_challenge':
      return status
    if time.time() >= deadline:
      return status
    time.sleep(2)


def capture_page_cdp(session, item, target, timeout_seconds):
  started = utc_now()
  session.send('Page.navigate', {'url': item['url']})
  session.wait_for_event('Page.loadEventFired', timeout_seconds=timeout_seconds)
  html, title, final_url = cdp_page_state(session)
  target.write_text(html, encoding='utf-8')
  return {
    'result': result_from_html(html, title=title, final_url=final_url),
    'browser_captured_at_utc': started,
    'browser_final_url': final_url,
    'browser_title': title,
    'browser_status': None,
    'browser_capture_method': 'chrome_cdp',
  }


def run_cdp_capture(args, cache, awards, queue):
  browser_process = launch_normal_chrome(
    args.executable_path,
    Path(args.profile),
    args.cdp_port,
    queue[0]['url'])
  session = None
  try:
    session = connect_cdp_page(args.cdp_port)
    if not args.no_prompt:
      print('')
      print('Chrome is open on the first LibraryThing award page.')
      print('Complete any Cloudflare/browser check in that window.')
      print(f'Waiting up to {args.clearance_timeout} seconds for the page to clear...')
      clearance_result = wait_for_cdp_clearance(session, args.clearance_timeout)
      if clearance_result == 'cloudflare_challenge':
        print('The first page still looks like a Cloudflare challenge.')
        if not args.continue_if_challenged:
          print('Stopping before capture so challenge pages are not saved again.')
          return

    by_file = {item['file']: item for item in awards}
    captured_by_url = {}
    for index, item in enumerate(queue, start=1):
      relative = item['file']
      target = cache / relative
      target.parent.mkdir(parents=True, exist_ok=True)
      cached_capture = captured_by_url.get(item['url'])
      if cached_capture is not None:
        print(f'[{index}/{len(queue)}] Reusing {item["url"]}')
        donor_target = cache / cached_capture['file']
        target.write_text(donor_target.read_text(encoding='utf-8'), encoding='utf-8')
        by_file[relative].update(cached_capture['metadata'])
      else:
        print(f'[{index}/{len(queue)}] Capturing {item["url"]}')
        metadata = capture_page_cdp(
          session, item, target, max(1, int(args.timeout_ms / 1000)))
        by_file[relative].update(metadata)
        captured_by_url[item['url']] = {
          'file': relative,
          'metadata': metadata,
        }
      write_json(cache / 'awards.json', awards)
      write_json(cache / 'source_urls.json', source_urls_from_awards(awards))
      update_summary(cache, awards)
      if args.delay and index < len(queue):
        time.sleep(args.delay)
  finally:
    if session is not None:
      session.close()
    if browser_process.poll() is None:
      browser_process.terminate()


def source_urls_from_awards(awards):
  return {
    item['file']: item['url']
    for item in awards
    if item.get('file') and item.get('url')
  }


def capture_page(page, item, target, timeout_ms):
  started = utc_now()
  try:
    response = page.goto(
      item['url'],
      wait_until='domcontentloaded',
      timeout=timeout_ms)
    page.wait_for_load_state('networkidle', timeout=min(timeout_ms, 15000))
  except Exception as err:
    html = page.content() if not page.is_closed() else ''
    if html:
      target.write_text(html, encoding='utf-8')
    title = page.title() if not page.is_closed() else ''
    final_url = page.url if not page.is_closed() else ''
    return {
      'result': (
        result_from_html(html, title=title, final_url=final_url)
        if html else (
          'timeout' if 'Timeout' in err.__class__.__name__ else 'browser_error'
        )
      ),
      'browser_error': str(err),
      'browser_captured_at_utc': started,
      'browser_final_url': final_url,
      'browser_title': title,
    }

  html = page.content()
  title = page.title()
  target.write_text(html, encoding='utf-8')
  status_code = response.status if response is not None else None
  return {
    'result': result_from_html(html, title=title, final_url=page.url),
    'browser_captured_at_utc': started,
    'browser_final_url': page.url,
    'browser_title': title,
    'browser_status': status_code,
  }


def wait_for_clearance(page, timeout_seconds):
  deadline = time.time() + timeout_seconds
  while True:
    try:
      html = page.content()
      status = result_from_html(html, title=page.title(), final_url=page.url)
    except Exception:
      status = 'cloudflare_challenge'
    if status != 'cloudflare_challenge':
      return status
    if time.time() >= deadline:
      return status
    time.sleep(2)


def open_browser(profile, channel, executable_path, cdp_port):
  try:
    from playwright.sync_api import sync_playwright
  except ImportError as err:
    raise SystemExit(
      'Playwright is not installed in this interpreter. Install it in the repo '
      'venv, then run `python -m playwright install chromium`.') from err

  playwright = sync_playwright().start()
  if cdp_port:
    if not executable_path:
      raise SystemExit('--cdp-port requires --executable-path')
    browser_process = subprocess.Popen([
      executable_path,
      f'--remote-debugging-port={cdp_port}',
      f'--user-data-dir={profile}',
      '--no-first-run',
      '--no-default-browser-check',
      'about:blank',
    ], cwd=str(ROOT))
    endpoint = f'http://127.0.0.1:{cdp_port}'
    last_error = None
    for _attempt in range(30):
      try:
        browser = playwright.chromium.connect_over_cdp(endpoint)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        return playwright, context, browser, browser_process
      except Exception as err:
        last_error = err
        time.sleep(1)
    browser_process.terminate()
    raise SystemExit(f'Could not connect to Chrome DevTools at {endpoint}: {last_error}')

  launch_kwargs = {
    'headless': False,
    'viewport': {'width': 1280, 'height': 900},
  }
  if channel:
    launch_kwargs['channel'] = channel
  if executable_path:
    launch_kwargs['executable_path'] = executable_path
  context = playwright.chromium.launch_persistent_context(
    str(profile),
    **launch_kwargs)
  return playwright, context, None, None


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--cache', default=str(DEFAULT_CACHE))
  parser.add_argument('--profile', default=str(DEFAULT_PROFILE))
  parser.add_argument('--channel', default='')
  parser.add_argument('--executable-path', default='')
  parser.add_argument('--cdp-port', type=int, default=0)
  parser.add_argument('--limit', type=int, default=0)
  parser.add_argument(
    '--name',
    action='append',
    help='Limit by exact manifest award name. Can be passed more than once.')
  parser.add_argument('--delay', type=float, default=3.0)
  parser.add_argument('--timeout-ms', type=int, default=45000)
  parser.add_argument(
    '--status',
    action='append',
    choices=('implemented', 'future'),
    help='Limit by manifest status. Can be passed more than once.')
  parser.add_argument(
    '--result',
    action='append',
    default=['cloudflare_challenge'],
    help=(
      'Limit by current manifest result. Defaults to cloudflare_challenge; '
      'use librarything_award_index to retry generic /award redirects.'))
  parser.add_argument(
    '--all-results',
    action='store_true',
    help='Capture matching status entries regardless of current result.')
  parser.add_argument(
    '--no-prompt',
    action='store_true',
    help='Start the capture loop without waiting for manual challenge clearance.')
  parser.add_argument(
    '--continue-if-challenged',
    action='store_true',
    help='Continue capture even if the first page still looks like Cloudflare.')
  parser.add_argument(
    '--clearance-timeout',
    type=int,
    default=30,
    help='Seconds to wait for the first browser page to clear Cloudflare.')
  parser.add_argument(
    '--classify-existing',
    action='store_true',
    help='Reclassify existing cached HTML files without launching a browser.')
  parser.add_argument(
    '--extract-award-links',
    action='store_true',
    help=(
      'Extract same-award /award/... links from cached HTML into '
      'award_links.json without launching a browser.'))
  parser.add_argument(
    '--reuse-same-url-captures',
    action='store_true',
    help='Copy existing html_browser captures to uncaptured manifest entries with the same URL.')
  args = parser.parse_args()

  cache = Path(args.cache)
  awards_path = cache / 'awards.json'
  awards = read_json(awards_path, [])
  if not awards:
    raise SystemExit(f'No awards manifest found at {awards_path}')

  if args.classify_existing:
    classify_existing(cache, awards)
    write_json(awards_path, awards)
    write_json(cache / 'source_urls.json', source_urls_from_awards(awards))
    update_summary(cache, awards)
    return

  if args.extract_award_links:
    write_json(cache / 'award_links.json', extract_cached_award_links(cache, awards))
    return

  if args.reuse_same_url_captures:
    reuse_same_url_captures(cache, awards)
    write_json(awards_path, awards)
    write_json(cache / 'source_urls.json', source_urls_from_awards(awards))
    update_summary(cache, awards)
    return

  results = () if args.all_results else tuple(args.result or ())
  queue = selected_items(awards, args.status, results, args.limit, args.name)
  if not queue:
    raise SystemExit('No LibraryThing manifest entries matched the capture filters.')

  profile = Path(args.profile)
  profile.mkdir(parents=True, exist_ok=True)
  if args.cdp_port:
    run_cdp_capture(args, cache, awards, queue)
    return

  playwright, context, browser, browser_process = open_browser(
    profile, args.channel or None, args.executable_path or None, args.cdp_port)
  page = context.pages[0] if context.pages else context.new_page()

  try:
    if not args.no_prompt:
      first = queue[0]
      page.goto(first['url'], wait_until='domcontentloaded', timeout=args.timeout_ms)
      print('')
      print('A browser is open on the first LibraryThing award page.')
      print('Complete any Cloudflare/browser check in that window.')
      print(f'Waiting up to {args.clearance_timeout} seconds for the page to clear...')
      clearance_result = wait_for_clearance(page, args.clearance_timeout)
      if clearance_result == 'cloudflare_challenge':
        print('The first page still looks like a Cloudflare challenge.')
        if not args.continue_if_challenged:
          print('Stopping before capture so challenge pages are not saved again.')
          return

    by_file = {item['file']: item for item in awards}
    for index, item in enumerate(queue, start=1):
      relative = item['file']
      target = cache / relative
      target.parent.mkdir(parents=True, exist_ok=True)
      print(f'[{index}/{len(queue)}] Capturing {item["url"]}')
      update = capture_page(page, item, target, args.timeout_ms)
      by_file[relative].update(update)
      write_json(awards_path, awards)
      write_json(cache / 'source_urls.json', source_urls_from_awards(awards))
      update_summary(cache, awards)
      if args.delay and index < len(queue):
        time.sleep(args.delay)
  finally:
    if browser is not None:
      browser.close()
    else:
      context.close()
    if browser_process is not None and browser_process.poll() is None:
      browser_process.terminate()
    playwright.stop()


if __name__ == '__main__':
  main()
