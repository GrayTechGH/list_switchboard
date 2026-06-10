#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Download LibraryThing award pages into the local scraps cache.

Maintenance notes:
- LibraryThing may return a Cloudflare challenge to curl. Keep those responses
  with status metadata instead of pretending the scrape succeeded; they still
  document the exact URL attempted.
- Implemented URLs are discovered from fetcher modules so this cache follows
  the code. Future-award URLs are generated from the planning list below.
"""

import argparse
import datetime as _datetime
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import quote_plus


ROOT = Path(__file__).resolve().parents[1]
FETCHER_DIR = ROOT / 'url_fetcher'
DEFAULT_OUTPUT = ROOT / '_dev_tools' / 'Scraps Cache' / 'librarything'
USER_AGENT = (
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
  'AppleWebKit/537.36 Chrome/125 Safari/537.36'
)


FUTURE_AWARDS = (
  'Strand Critics Award',
  'Nero Award',
  'Pulitzer Prize for General Nonfiction',
  'National Book Award for Nonfiction',
  'Baillie Gifford Prize',
  'National Book Critics Circle Award for Nonfiction',
  'National Book Critics Circle Award for Criticism',
  'PEN/John Kenneth Galbraith Award',
  'PEN/Diamonstein-Spielvogel Award for the Art of the Essay',
  'PEN/Jean Stein Book Award',
  'J. Anthony Lukas Book Prize',
  'Orwell Prize for Political Writing',
  'Andrew Carnegie Medal for Excellence in Nonfiction',
  'Kirkus Prize for Nonfiction',
  "Women's Prize for Non-Fiction",
  'PEN Open Book Award',
  'Royal Society Trivedi Science Book Prize',
  'Mark Lynton History Prize',
  'Booker Prize',
  'Pulitzer Prize for Fiction',
  'National Book Award for Fiction',
  'International Booker Prize',
  "Women's Prize for Fiction",
  'National Book Critics Circle Award for Fiction',
  'PEN/Faulkner Award for Fiction',
  'Dublin Literary Award',
  'Walter Scott Prize',
  'PEN/Hemingway Award',
  'Center for Fiction First Novel Prize',
  'James Tait Black Memorial Prize for Fiction',
  'Costa Book Award',
  'Whitbread Book Award',
  'Folio Prize',
  "Governor General's Literary Award for Fiction",
  'Giller Prize',
  'Miles Franklin Award',
  'Stella Prize',
  'John Leonard Prize',
  'National Book Critics Circle Gregg Barrios Book in Translation Prize',
  'RITA Award',
  'Romantic Novel of the Year Award',
  'RoNA Award',
  'Ripped Bodice Award',
  'Romantic Times Reviewers Choice Award',
  'Lambda Literary Award for Romance',
  'Romance Writers of Australia RUBY Award',
  'Australian Romance Readers Award',
  'HOLT Medallion',
  'Booksellers Best Award',
  'Goodreads Choice Award for Romance',
  'Goodreads Choice Award for Romantasy',
  'Vivian Award',
  'Joan Hessayon Award',
  "Governor General's Literary Awards",
  'Prime Minister Literary Awards',
  'Goldsmiths Prize',
  "Writers' Trust Fiction Prize",
  "Victorian Premier's Literary Award",
  "New South Wales Premier's Literary Awards",
  "Queensland Literary Awards",
  "Western Australian Premier's Book Awards",
  "South Australian Literary Awards",
  'ACT Book of the Year',
  'Michael L. Printz Award',
  "National Book Award for Young People's Literature",
  'Carnegie Medal for Writing',
  'Newbery Medal',
  "Governor General's Literary Award for Young People's Literature",
  'CBCA Book of the Year Award',
  'Andre Norton Nebula Award',
  'Lodestar Award',
  'William C. Morris YA Debut Award',
  'YALSA Award for Excellence in Nonfiction for Young Adults',
  'Goodreads Choice Award for Young Adult Fiction',
  'Goodreads Choice Award for Young Adult Fantasy',
  'British Fantasy Award for Best Horror Novel',
  'August Derleth Award',
  'International Horror Guild Award',
  'Aurealis Award for Best Horror Novel',
  'Aurealis Award for Best Horror Novella',
  'Australasian Shadows Award',
  'This Is Horror Award',
  'Splatterpunk Award',
  'Ladies of Horror Fiction Award',
  'Goodreads Choice Award for Horror',
)


KNOWN_FUTURE_AWARD_URLS = {
  'ACT Book of the Year': (
    'https://www.librarything.com/award/6234/ACT-Book-of-the-Year-Award'),
  'Andre Norton Nebula Award': (
    'https://www.librarything.com/award/265/'
    'Andre-Norton-Nebula-Award-for-Middle-Grade-and-Young-Adult-Fiction'),
  'Andrew Carnegie Medal for Excellence in Nonfiction': (
    'https://www.librarything.com/award/1403/'
    'Andrew-Carnegie-Medals-for-Excellence-in-Fiction-and-Nonfiction'),
  'August Derleth Award': 'https://www.librarything.com/award/740/British-Fantasy-Award',
  'Aurealis Award for Best Horror Novel': (
    'https://www.librarything.com/award/1348/Aurealis-Award'),
  'Aurealis Award for Best Horror Novella': (
    'https://www.librarything.com/award/1348/Aurealis-Award'),
  'Australasian Shadows Award': (
    'https://www.librarything.com/award/5495/Australasian-Shadows-Award'),
  'Australian Romance Readers Award': (
    'https://www.librarything.com/award/9120/'
    'Australian-Romance-Readers-Association-Award'),
  'Baillie Gifford Prize': (
    'https://www.librarything.com/award/1149/'
    'Baillie-Gifford-Prize-for-Non-Fiction'),
  'Booker Prize': 'https://www.librarything.com/award/253/Booker-Prize',
  'Booksellers Best Award': (
    'https://www.librarything.com/award/4040/Booksellers-Best-Award'),
  'British Fantasy Award for Best Horror Novel': (
    'https://www.librarything.com/award/740/British-Fantasy-Award'),
  'CBCA Book of the Year Award': (
    'https://www.librarything.com/award/2229/CBCA-Book-of-the-Year'),
  'Center for Fiction First Novel Prize': (
    'https://www.librarything.com/award/1074/Center-for-Fiction-First-Novel-Prize'),
  'Costa Book Award': 'https://www.librarything.com/award/1068/Costa-Book-Awards',
  'Dublin Literary Award': 'https://www.librarything.com/award/945/Dublin-Literary-Award',
  'Folio Prize': 'https://www.librarything.com/award/2082/The-Writers-Prize',
  'Giller Prize': 'https://www.librarything.com/award/1209/Giller-Prize',
  'Goldsmiths Prize': 'https://www.librarything.com/award/2511/Goldsmiths-Prize',
  'Goodreads Choice Award for Horror': (
    'https://www.librarything.com/award/230/Goodreads-Choice-Awards'),
  'Goodreads Choice Award for Romance': (
    'https://www.librarything.com/award/230/Goodreads-Choice-Awards'),
  'Goodreads Choice Award for Romantasy': (
    'https://www.librarything.com/award/230/Goodreads-Choice-Awards'),
  'Goodreads Choice Award for Young Adult Fantasy': (
    'https://www.librarything.com/award/230/Goodreads-Choice-Awards'),
  'Goodreads Choice Award for Young Adult Fiction': (
    'https://www.librarything.com/award/230/Goodreads-Choice-Awards'),
  "Governor General's Literary Award for Fiction": (
    'https://www.librarything.com/award/975/Governor-Generals-Literary-Award'),
  "Governor General's Literary Award for Young People's Literature": (
    'https://www.librarything.com/award/975/Governor-Generals-Literary-Award'),
  "Governor General's Literary Awards": (
    'https://www.librarything.com/award/975/Governor-Generals-Literary-Award'),
  'HOLT Medallion': 'https://www.librarything.com/award/2400/HOLT-Medallion',
  'International Booker Prize': (
    'https://www.librarything.com/award/1989/The-International-Booker-Prize'),
  'International Horror Guild Award': (
    'https://www.librarything.com/award/1337/International-Horror-Guild-Award'),
  'J. Anthony Lukas Book Prize': (
    'https://www.librarything.com/award/1863/J-Anthony-Lukas-Book-Prize'),
  'James Tait Black Memorial Prize for Fiction': (
    'https://www.librarything.com/award/525/James-Tait-Black-Memorial-Prize'),
  'Joan Hessayon Award': (
    'https://www.librarything.com/award/2679/Romantic-Novel-of-the-Year-Award'),
  'John Leonard Prize': (
    'https://www.librarything.com/award/371/National-Book-Critics-Circle-Award'),
  'Kirkus Prize for Nonfiction': 'https://www.librarything.com/award/1516/Kirkus-Prize',
  'Ladies of Horror Fiction Award': (
    'https://www.librarything.com/award/14407/Ladies-of-Horror-Fiction-Award'),
  'Lambda Literary Award for Romance': (
    'https://www.librarything.com/award/879/Lambda-Literary-Award'),
  'Lodestar Award': 'https://www.librarything.com/award/1910/Lodestar-Award',
  'Mark Lynton History Prize': (
    'https://www.librarything.com/award/1778/Mark-Lynton-History-Prize'),
  'Michael L. Printz Award': 'https://www.librarything.com/award/890/Printz-Award',
  'Miles Franklin Award': 'https://www.librarything.com/award/1964/Miles-Franklin-Award',
  'National Book Award for Fiction': (
    'https://www.librarything.com/award/238/National-Book-Award'),
  'National Book Award for Nonfiction': (
    'https://www.librarything.com/award/238/National-Book-Award'),
  "National Book Award for Young People's Literature": (
    'https://www.librarything.com/award/238/National-Book-Award'),
  'Carnegie Medal for Writing': (
    'https://www.librarything.com/award/393/Yoto-Carnegie-Medal-for-Writing'),
  'National Book Critics Circle Award for Criticism': (
    'https://www.librarything.com/award/371/National-Book-Critics-Circle-Award'),
  'National Book Critics Circle Award for Fiction': (
    'https://www.librarything.com/award/371/National-Book-Critics-Circle-Award'),
  'National Book Critics Circle Award for Nonfiction': (
    'https://www.librarything.com/award/371/National-Book-Critics-Circle-Award'),
  'National Book Critics Circle Gregg Barrios Book in Translation Prize': (
    'https://www.librarything.com/award/371/National-Book-Critics-Circle-Award'),
  'Nero Award': 'https://www.librarything.com/award/1347/Nero-Award',
  "New South Wales Premier's Literary Awards": (
    'https://www.librarything.com/award/2259/'
    'New-South-Wales-Premiers-Literary-Award'),
  'Newbery Medal': 'https://www.librarything.com/award/204/Newbery-Medal',
  'Orwell Prize for Political Writing': (
    'https://www.librarything.com/award/2451/Orwell-Prize'),
  'PEN Open Book Award': 'https://www.librarything.com/award/3522/PEN-Open-Book-Award',
  'PEN/Diamonstein-Spielvogel Award for the Art of the Essay': (
    'https://www.librarything.com/award/3191/'
    'PEN%25252FDiamonstein-Spielvogel-Award-for-the-Art-of-the-Essay'),
  'PEN/Faulkner Award for Fiction': (
    'https://www.librarything.com/award/706/PEN%25252FFaulkner-Award-for-Fiction'),
  'PEN/Hemingway Award': (
    'https://www.librarything.com/award/1145/PEN%25252FHemingway-Award'),
  'PEN/Jean Stein Book Award': (
    'https://www.librarything.com/award/1590/PEN%25252FJean-Stein-Book-Award'),
  'PEN/John Kenneth Galbraith Award': (
    'https://www.librarything.com/award/1746/'
    'PEN%25252FJohn-Kenneth-Galbraith-Award-for-Nonfiction'),
  'Prime Minister Literary Awards': (
    'https://www.librarything.com/award/4128/Prime-Ministers-Literary-Award'),
  'Pulitzer Prize for Fiction': 'https://www.librarything.com/award/76/Pulitzer-Prize',
  'Pulitzer Prize for General Nonfiction': (
    'https://www.librarything.com/award/76/Pulitzer-Prize'),
  "Queensland Literary Awards": (
    'https://www.librarything.com/award/5923/Queensland-Literary-Awards'),
  'RITA Award': 'https://www.librarything.com/award/1826/RITA-Award',
  'RoNA Award': (
    'https://www.librarything.com/award/2679/Romantic-Novel-of-the-Year-Award'),
  'Romance Writers of Australia RUBY Award': (
    'https://www.librarything.com/award/6550/R%2ABY-Award'),
  'Romantic Novel of the Year Award': (
    'https://www.librarything.com/award/2679/Romantic-Novel-of-the-Year-Award'),
  'Romantic Times Reviewers Choice Award': (
    'https://www.librarything.com/award/451/Romantic-Times-Reviewers-Choice-Award'),
  'Royal Society Trivedi Science Book Prize': (
    'https://www.librarything.com/award/759/Royal-Society-Trivedi-Science-Book-Prize'),
  "South Australian Literary Awards": (
    'https://www.librarything.com/award/2688/South-Australian-Literary-Awards'),
  'Splatterpunk Award': 'https://www.librarything.com/award/9387/Splatterpunk-Awards',
  'Stella Prize': 'https://www.librarything.com/award/4132/Stella-Prize',
  'Strand Critics Award': (
    'https://www.librarything.com/award/1380/The-Strand-Critics-Award'),
  "Victorian Premier's Literary Award": (
    'https://www.librarything.com/award/2822/Victorian-Premiers-Literary-Award'),
  'Vivian Award': 'https://www.librarything.com/award/5888/The-Vivian',
  'Walter Scott Prize': (
    'https://www.librarything.com/award/1049/'
    'Walter-Scott-Prize-for-Historical-Fiction'),
  "Western Australian Premier's Book Awards": (
    'https://www.librarything.com/award/2689/Western-Australian-Premiers-Book-Awards'),
  'Whitbread Book Award': 'https://www.librarything.com/award/1068/Costa-Book-Awards',
  'William C. Morris YA Debut Award': (
    'https://www.librarything.com/award/1462/William-C-Morris-YA-Debut-Award'),
  "Women's Prize for Fiction": (
    'https://www.librarything.com/award/1353/Womens-Prize-for-Fiction'),
  "Women's Prize for Non-Fiction": (
    'https://www.librarything.com/award/13719/Womens-Prize-for-Non-Fiction'),
  "Writers' Trust Fiction Prize": (
    'https://www.librarything.com/award/1223/'
    'Atwood-Gibson-Writers-Trust-Fiction-Prize'),
  'YALSA Award for Excellence in Nonfiction for Young Adults': (
    'https://www.librarything.com/award/2635/'
    'YALSA-Award-for-Excellence-in-Nonfiction'),
}


def slug(value):
  value = re.sub(r'&', ' and ', value or '')
  value = re.sub(r'[^A-Za-z0-9]+', '_', value)
  return value.strip('_').casefold() or 'librarything_award'


def bookaward_url(name):
  return 'https://www.librarything.com/bookaward/' + quote_plus(name)


def implemented_award_urls():
  urls = {}
  for path in sorted(FETCHER_DIR.glob('*.py')):
    text = path.read_text(encoding='utf-8')
    for match in re.finditer(
        r'https://www\.librarything\.com/(?:award|bookaward)/[^\'"\s)]+',
        text):
      url = match.group(0)
      urls.setdefault(url, set()).add(path.name)
  return [
    {
      'name': source_name_from_url(url),
      'url': url,
      'source_files': sorted(files),
      'status': 'implemented',
    }
    for url, files in sorted(urls.items())
  ]


def source_name_from_url(url):
  tail = url.rstrip('/').rsplit('/', 1)[-1]
  tail = re.sub(r'^\d+(?:\.\d+)*-', '', tail)
  tail = tail.replace('%2B', ' ').replace('+', ' ')
  tail = re.sub(r'[-_]+', ' ', tail)
  return re.sub(r'\s+', ' ', tail).strip() or url


def future_award_urls():
  items = []
  seen = set()
  for name in FUTURE_AWARDS:
    normalized = name.casefold()
    if normalized in seen:
      continue
    seen.add(normalized)
    items.append({
      'name': name,
      'url': KNOWN_FUTURE_AWARD_URLS.get(name, bookaward_url(name)),
      'source_files': ['_docs/TASKS.md'],
      'status': 'future',
    })
  return items


def target_file(item, used):
  folder = item['status']
  base = slug(item['name'])
  candidate = f'{folder}/{base}.html'
  if candidate not in used:
    used.add(candidate)
    return candidate
  index = 2
  while True:
    candidate = f'{folder}/{base}_{index}.html'
    if candidate not in used:
      used.add(candidate)
      return candidate
    index += 1


def detect_result(path, returncode):
  text = path.read_text(encoding='utf-8', errors='ignore') if path.exists() else ''
  if returncode != 0:
    return 'curl_error'
  if 'Just a moment...' in text or 'challenge-platform' in text:
    return 'cloudflare_challenge'
  if '<html' in text.casefold() or '<!doctype html' in text.casefold():
    return 'html'
  return 'unknown'


def curl_download(url, output_path):
  command = [
    'curl.exe',
    '-L',
    '--silent',
    '--show-error',
    '--compressed',
    '-A',
    USER_AGENT,
    '--output',
    str(output_path),
    url,
  ]
  return subprocess.run(command, cwd=str(ROOT), text=True, capture_output=True)


def build_manifest():
  items = implemented_award_urls() + future_award_urls()
  by_key = {}
  for item in items:
    if item['status'] == 'future':
      key = (item['status'], item['name'].casefold())
    else:
      key = (item['status'], item['url'])
    existing = by_key.get(key)
    if existing is None:
      by_key[key] = item
      continue
    existing['source_files'] = sorted(set(
      existing.get('source_files', ()) + item.get('source_files', ())))
  used = set()
  manifest = []
  for item in sorted(by_key.values(), key=lambda row: (row['status'], row['name'])):
    item = dict(item)
    item['file'] = target_file(item, used)
    manifest.append(item)
  return manifest


def write_json(path, data):
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def read_json(path, default):
  if not path.exists():
    return default
  return json.loads(path.read_text(encoding='utf-8'))


def write_summary(output, results):
  by_status = {}
  for item in results:
    by_status[item['result']] = by_status.get(item['result'], 0) + 1

  write_json(output / 'scrape_summary.json', {
    'downloaded_at_utc': _datetime.datetime.now(
      _datetime.UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
    'files': len(results),
    'folder': 'librarything',
    'results': by_status,
  })


def refresh_existing_manifest(output):
  awards_path = output / 'awards.json'
  existing = read_json(awards_path, [])
  planned = {
    (item['status'], item['name']): item
    for item in build_manifest()
  }
  seen = set()
  results = []
  for item in existing:
    key = (item.get('status'), item.get('name'))
    planned_item = planned.get(key)
    if planned_item is None:
      results.append(item)
      continue
    seen.add(key)
    old_url = item.get('url')
    new_url = planned_item['url']
    item['url'] = new_url
    item['source_files'] = planned_item.get('source_files', item.get('source_files', []))
    if old_url != new_url and item.get('browser_final_url') != new_url:
      item['result'] = 'cloudflare_challenge'
      for field in (
          'browser_capture_method',
          'browser_captured_at_utc',
          'browser_final_url',
          'browser_status',
          'browser_title'):
        item.pop(field, None)
    results.append(item)

  used_files = {item.get('file') for item in results}
  for key, planned_item in planned.items():
    if key in seen:
      continue
    item = dict(planned_item)
    if item.get('file') in used_files:
      item['file'] = target_file(item, used_files)
    item['result'] = 'pending'
    results.append(item)

  write_json(awards_path, results)
  write_json(output / 'source_urls.json', {
    item['file']: item['url']
    for item in results
    if item.get('file') and item.get('url')
  })
  write_summary(output, results)
  return results


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--output', default=str(DEFAULT_OUTPUT))
  parser.add_argument('--skip-download', action='store_true')
  parser.add_argument(
    '--refresh-manifest-urls',
    action='store_true',
    help='Update an existing awards.json from current URL discovery without downloading.')
  args = parser.parse_args()

  output = Path(args.output)
  output.mkdir(parents=True, exist_ok=True)
  if args.refresh_manifest_urls:
    refresh_existing_manifest(output)
    return

  manifest = build_manifest()
  source_urls = {}
  results = []

  for item in manifest:
    relative = item['file']
    target = output / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    returncode = 0
    stderr = ''
    if not args.skip_download:
      result = curl_download(item['url'], target)
      returncode = result.returncode
      stderr = result.stderr.strip()
    source_urls[relative] = item['url']
    results.append({
      **item,
      'result': detect_result(target, returncode),
      'curl_returncode': returncode,
      'curl_stderr': stderr,
    })

  write_json(output / 'source_urls.json', source_urls)
  write_json(output / 'awards.json', results)
  write_summary(output, results)


if __name__ == '__main__':
  main()
