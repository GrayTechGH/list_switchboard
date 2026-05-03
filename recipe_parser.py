#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

import re
import json
from html import escape
from urllib.parse import quote
from urllib.parse import urljoin

from bs4 import BeautifulSoup


BLOCKED_MARKERS = (
  'Please wait for verification',
  'blocked by network security',
  'You have been blocked',
  'whoa there, pardner',
)


def parse_recipe_html(
    recipe, html, fetch_url=None, sleep=None, fetch_error=None, log=None, progress=None):
  parser = recipe.parser or 'reddit_results'
  if parser == 'reddit_results':
    return parse_reddit_results(html, recipe.NAME, recipe.URL, recipe.schemas)
  if parser == 'sword_and_laser_book_list':
    return parse_sword_and_laser_book_list(
      recipe, html, fetch_url=fetch_url, sleep=sleep, fetch_error=fetch_error,
      log=log, progress=progress)
  raise ValueError(f'Unknown recipe parser "{parser}".')


def blocked_message(text):
  for marker in BLOCKED_MARKERS:
    if marker.casefold() in text.casefold():
      return (
        'Reddit returned a verification or blocking page instead of the r/Fantasy results table. '
        'Enable List Switchboard debug logging and retry to record the fetched page preview.')
  return None


def parse_reddit_results(html, name, url, schemas):
  soup = BeautifulSoup(html, 'html.parser')
  text = soup.get_text('\n', strip=True)
  message = blocked_message(text)
  if message:
    raise ValueError(message)

  for parser in (parse_html_table, parse_token_table, parse_plain_text_table, parse_markdown_table):
    entries = parser(soup, text, url, schemas)
    if entries:
      return {
        'name': name,
        'url': url,
        'entries': entries,
      }
  raise ValueError('Could not find the r/Fantasy results table in the fetched page.')


def parse_html_table(soup, _text, url, schemas):
  for row in soup.select('table tr'):
    headers = [cell.get_text(' ', strip=True) for cell in row.find_all('th')]
    schema = matching_schema(headers, schemas)
    if not schema:
      continue
    entries = []
    table = row.find_parent('table')
    if table is None:
      continue
    for data_row in table.select('tr')[1:]:
      cells = data_row.find_all(['td', 'th'])
      if len(cells) < len(schema['headers']):
        continue
      values = [cell.get_text(' ', strip=True) for cell in cells]
      source_url = ''
      title_index = schema['fields'].index('title')
      link = cells[title_index].find('a', href=True)
      if link is not None:
        source_url = urljoin(url, link['href'])
      data = row_entry(values, schema, source_url=source_url)
      if data:
        entries.append(data)
    if entries:
      return entries
  return []


def parse_token_table(_soup, text, _url, schemas):
  strings = [line.strip() for line in text.splitlines() if line.strip()]
  for schema in schemas:
    start = token_header_start(strings, schema['headers'])
    if start is None:
      continue
    entries = []
    index = start
    width = len(schema['headers'])
    while index + width - 1 < len(strings):
      values = strings[index:index + width]
      data = row_entry(values, schema)
      if not data:
        break
      entries.append(data)
      index += width
    if entries:
      return entries
  return []


def parse_plain_text_table(_soup, text, _url, schemas):
  for schema in schemas:
    entries = []
    in_table = False
    for line in text.splitlines():
      line = line.strip()
      if not line:
        continue
      if not in_table:
        if normalize_header(line) == normalize_header(' '.join(schema['headers'])):
          in_table = True
        continue

      columns = re.split(r'\s{2,}', line)
      if len(columns) < len(schema['headers']):
        if entries:
          break
        continue
      data = row_entry(columns[:len(schema['headers'])], schema)
      if not data:
        if entries:
          break
        continue
      entries.append(data)
    if entries:
      return entries
  return []


def parse_markdown_table(_soup, text, _url, schemas):
  rows = []
  for line in text.splitlines():
    line = line.strip()
    if not line.startswith('|') or not line.endswith('|'):
      continue
    columns = [column.strip() for column in line.strip('|').split('|')]
    rows.append(columns)
  for index, row in enumerate(rows):
    schema = matching_schema(row, schemas)
    if not schema:
      continue
    entries = []
    for values in rows[index + 1:]:
      if len(values) < len(schema['headers']):
        continue
      data = row_entry([strip_markdown_link(value) for value in values], schema)
      if data:
        entries.append(data)
    if entries:
      return entries
  return []


def token_header_start(strings, headers):
  width = len(headers)
  for index in range(len(strings) - width + 1):
    if [normalize_header(value) for value in strings[index:index + width]] == [
        normalize_header(value) for value in headers]:
      return index + width
  return None


def matching_schema(headers, schemas):
  normalized = [normalize_header(value) for value in headers]
  for schema in schemas:
    expected = [normalize_header(value) for value in schema['headers']]
    if normalized[:len(expected)] == expected:
      return schema
  return None


def normalize_header(value):
  return re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip()


def row_entry(values, schema, source_url=''):
  fields = schema['fields']
  data = {}
  for field, value in zip(fields, values):
    data[field] = strip_markdown_link(value).strip()
  rank, rank_change = split_rank_change(data.get('position', ''))
  data['position'] = rank or data.get('position', '')
  if rank_change and not data.get('rank_change'):
    data['rank_change'] = rank_change
  if not valid_entry(data):
    return None
  result = {
    'position': data.get('position', ''),
    'title': data.get('title', ''),
    'author': data.get('author', ''),
  }
  for key in ('votes', 'rank_change', 'ratings'):
    if data.get(key):
      result[key] = data[key]
  if source_url:
    result['source_url'] = source_url
  return result


def split_rank_change(value):
  value = value.strip()
  match = re.match(r'^(\d+)\s*/\s*(.+)$', value)
  if match:
    return match.group(1).strip(), match.group(2).strip()
  return value, ''


def valid_entry(data):
  position = data.get('position', '').strip()
  title = data.get('title', '').strip()
  author = data.get('author', '').strip()
  if not position.isdigit() or not title or not author:
    return False
  votes = data.get('votes', '').strip()
  return not votes or bool(re.search(r'\d', votes))


def strip_markdown_link(value):
  value = value.strip()
  if '](' not in value or not value.startswith('['):
    return value
  close = value.find('](')
  return value[1:close].strip()


def parse_sword_and_laser_book_list(
    recipe, html, fetch_url=None, sleep=None, fetch_error=None, log=None, progress=None):
  html = fandom_api_html(html)
  if looks_like_wikitext(html):
    html = fandom_wikitext_table_to_html(html)
  soup = BeautifulSoup(html, 'html.parser')
  entries = parse_sword_and_laser_main_entries(recipe, soup)
  unavailable_march_pages = []
  march_summary = None
  notes = []
  if recipe.options.get('include_march_madness', False):
    entries, unavailable_march_pages, march_summary = add_sword_and_laser_march_entries(
      recipe, entries, fetch_url, sleep, fetch_error, log, progress)
    if fetch_url is not None and entries and not any(entry.get('source_url') for entry in entries):
      notes.append(
        'March Madness details were not fetched because the imported table did not include linked page URLs.')
    elif march_summary is not None:
      notes.append(march_madness_summary_note(march_summary))
  parsed = {
    'name': recipe.NAME,
    'url': recipe.URL,
    'entries': sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
  }
  if march_summary is not None:
    parsed['march_madness_summary'] = march_summary
  if unavailable_march_pages:
    parsed['march_madness_unavailable_pages'] = unavailable_march_pages
    notes.append(march_madness_unavailable_note(unavailable_march_pages))
  if notes:
    parsed['notes'] = notes
  return parsed


def parse_sword_and_laser_main_entries(recipe, soup):
  entries = []
  for table in soup.select('table'):
    headers = [cell.get_text(' ', strip=True) for cell in table.select('tr th')]
    schema = matching_schema(headers, recipe.schemas)
    if not schema:
      continue
    for row in table.select('tr')[1:]:
      cells = row.find_all(['td', 'th'])
      if len(cells) < len(schema['headers']):
        continue
      values = [cell.get_text(' ', strip=True) for cell in cells]
      data = sword_and_laser_entry(values, schema, recipe.URL, cells)
      if data:
        entries.append(data)
    if entries:
      return entries

  text = soup.get_text('\n', strip=True)
  return parse_sword_and_laser_text_entries(recipe, text)


def fandom_api_html(html):
  text = html.lstrip()
  if not text.startswith('{'):
    return html
  try:
    data = json.loads(html)
  except Exception:
    return html
  parsed = data.get('parse') or {}
  content = parsed.get('text') or ''
  if isinstance(content, dict):
    content = next(iter(content.values()), '')
  return content or html


def looks_like_wikitext(text):
  return '{| class=' in text or '\n|-' in text or '\n!' in text


def fandom_wikitext_table_to_html(text):
  rows = []
  current = []
  for line in text.splitlines():
    line = line.strip()
    if line.startswith('|-'):
      if current:
        rows.append(current)
        current = []
      continue
    if line.startswith('!') or line.startswith('|'):
      cells = [cell.strip() for cell in line[1:].split('!!' if line.startswith('!') else '||')]
      if len(cells) == 1 and not line.startswith('!'):
        cells = [cell.strip() for cell in line[1:].split('|')]
      current.extend(clean_wikitext_cell(cell) for cell in cells if cell.strip())
  if current:
    rows.append(current)
  parts = ['<table>']
  for row_index, row in enumerate(rows):
    tag = 'th' if row_index == 0 else 'td'
    parts.append('<tr>' + ''.join(f'<{tag}>{cell}</{tag}>' for cell in row) + '</tr>')
  parts.append('</table>')
  return ''.join(parts)


def clean_wikitext_cell(value):
  value = re.sub(r'<[^>]+>', '', value)
  value = re.sub(r'\[\[([^|\]#]+)(?:#[^|\]]*)?\|([^\]]+)\]\]', wikitext_link_to_html, value)
  value = re.sub(r'\[\[([^|\]#]+)(?:#[^\]]*)?\]\]', wikitext_link_to_html, value)
  value = re.sub(r'\[https?://[^\s\]]+\s+([^\]]+)\]', r'\1', value)
  value = value.replace("'''", '').replace("''", '')
  return value.strip()


def wikitext_link_to_html(match):
  page = match.group(1).strip()
  label = match.group(2).strip() if len(match.groups()) > 1 and match.group(2) else page
  href = '/wiki/' + quote(page.replace(' ', '_'), safe='')
  return f'<a href="{href}">{escape(label)}</a>'


def parse_sword_and_laser_text_entries(recipe, text):
  lines = [line.strip() for line in text.splitlines() if line.strip()]
  for schema in recipe.schemas:
    start = token_header_start(lines, schema['headers'])
    if start is None:
      continue
    entries = []
    index = start
    width = len(schema['headers'])
    while index + width - 1 < len(lines):
      values = lines[index:index + width]
      data = sword_and_laser_entry(values, schema, recipe.URL)
      if not data:
        break
      entries.append(data)
      index += width
    if entries:
      return entries
  return []


def sword_and_laser_entry(values, schema, url, cells=None):
  fields = schema['fields']
  data = {}
  for field, value in zip(fields, values):
    data[field] = value.strip()
  seq = data.get('position', '').strip()
  position = sword_and_laser_position(seq)
  title = clean_sword_and_laser_title(data.get('title', ''))
  author = data.get('author', '').strip()
  if not position or not title or not author:
    return None
  source_url = ''
  if cells:
    title_index = fields.index('title')
    link = cells[title_index].find('a', href=True)
    if link is not None:
      source_url = urljoin(url, link['href'])
  result = {
    'position': position,
    'title': title,
    'author': author,
  }
  if source_url:
    result['source_url'] = source_url
  return result


def sword_and_laser_position(seq):
  seq = seq.strip()
  if not seq:
    return ''
  match = re.match(r'^(\d+)([a-z])?$', seq, re.I)
  if not match:
    return ''
  number = match.group(1)
  suffix = (match.group(2) or '').casefold()
  if suffix == 'a':
    return f'{number}.5'
  if suffix:
    return ''
  return number


def clean_sword_and_laser_title(title):
  return re.sub(r'\s*\(Alternate Pick\)\s*$', '', title).strip()


def add_sword_and_laser_march_entries(
    recipe, entries, fetch_url, sleep, fetch_error=None, log=None, progress=None):
  summary = {
    'main_entries': len(entries),
    'linked_entries': len([entry for entry in entries if entry.get('source_url')]),
    'fetched_pages': 0,
    'failed_pages': 0,
    'pages_with_nominations': 0,
    'nominations_found': 0,
    'entries_added': 0,
    'duplicates_skipped': 0,
  }
  log_march(log, 'start', summary)
  progress_march(progress, 0, summary['linked_entries'], 'Preparing Sword & Laser March Madness pages...')
  if fetch_url is None:
    log_march(log, 'no-fetch-callback', summary)
    return entries, [], summary
  by_key = {
    (normalize_match_title(entry.get('title', '')), normalize_match_title(entry.get('author', ''))): entry
    for entry in entries
  }
  unavailable_pages = []
  delay = float(recipe.options.get('fetch_delay_seconds', 1.5))
  linked_index = 0
  for entry in list(entries):
    url = entry.get('source_url')
    if not url:
      log_march(log, 'skip-no-link', {
        'title': entry.get('title', ''),
        'position': entry.get('position', ''),
      })
      continue
    linked_index += 1
    log_march(log, 'fetch-linked-page', {
      'title': entry.get('title', ''),
      'position': entry.get('position', ''),
      'url': url,
    })
    progress_march(
      progress, linked_index, summary['linked_entries'],
      f'page {linked_index} of {summary["linked_entries"]}: '
      f'{entry.get("title", "")}')
    if sleep is not None:
      sleep(
        delay,
        f'page {linked_index} of {summary["linked_entries"]}: '
        f'{entry.get("title", "")}')
    try:
      html = fetch_url(url)
      summary['fetched_pages'] += 1
    except Exception as err:
      summary['failed_pages'] += 1
      unavailable_pages.append(march_madness_unavailable_page(entry, url, err))
      if fetch_error is not None:
        fetch_error(url, err, entry)
      continue
    soup = BeautifulSoup(html, 'html.parser')
    nominations = parse_sword_and_laser_march_page(soup, entry)
    summary['nominations_found'] += len(nominations)
    if nominations:
      summary['pages_with_nominations'] += 1
    log_march(log, 'parsed-linked-page', {
      'title': entry.get('title', ''),
      'url': url,
      'nominations': len(nominations),
    })
    for nomination in nominations:
      key = (
        normalize_match_title(nomination.get('title', '')),
        normalize_match_title(nomination.get('author', '')),
      )
      if key not in by_key:
        by_key[key] = nomination
        summary['entries_added'] += 1
      else:
        summary['duplicates_skipped'] += 1
  log_march(log, 'finished', summary)
  return list(by_key.values()), unavailable_pages, summary


def progress_march(progress, done, total, message):
  if progress is not None:
    progress(done, total, message)


def log_march(log, event, data):
  if log is not None:
    log(f'Sword & Laser March Madness {event}: {data}')


def march_madness_summary_note(summary):
  if summary.get('linked_entries', 0) == 0:
    return (
      'March Madness was enabled, but no linked Sword & Laser book pages were available '
      f'from {summary.get("main_entries", 0)} main entries.')
  return (
    'March Madness checked '
    f'{summary.get("fetched_pages", 0)} of {summary.get("linked_entries", 0)} linked pages; '
    f'found {summary.get("nominations_found", 0)} nomination entries; '
    f'added {summary.get("entries_added", 0)} new recipe entries; '
    f'skipped {summary.get("duplicates_skipped", 0)} duplicate entries.')


def march_madness_unavailable_page(entry, url, err):
  return {
    'title': entry.get('title', ''),
    'url': url,
    'error': str(err),
  }


def march_madness_unavailable_note(pages):
  count = len(pages)
  label = 'page' if count == 1 else 'pages'
  details = []
  for page in pages[:5]:
    title = page.get('title', '') or page.get('url', '')
    details.append(title)
  note = f'March Madness details were unavailable for {count} linked {label}'
  if details:
    note += ': ' + '; '.join(details)
    if count > len(details):
      note += f'; and {count - len(details)} more'
    note += ' (URLs are available in recipe debug logging)'
  return note + '.'


def parse_sword_and_laser_march_page(soup, official_entry):
  text = soup.get_text('\n', strip=True)
  if 'March Madness style knockout poll' not in text:
    return []
  lines = [line.strip() for line in text.splitlines() if line.strip()]
  first_round = first_round_vote_lines(lines)
  base = float(official_entry.get('position', ''))
  nominations = []
  for index, line in enumerate(first_round, start=1):
    parsed = parse_vote_line(line)
    if not parsed:
      continue
    votes, percent, title, author = parsed
    nominations.append({
      'position': f'{base + (index / 100.0):g}',
      'title': title,
      'author': author,
      'votes': votes,
      'percent': percent,
    })
  return nominations


def first_round_vote_lines(lines):
  rows = []
  in_round_one = False
  for line in lines:
    if line.startswith('Round 1 Match'):
      in_round_one = True
      continue
    if in_round_one and line.startswith('Round 2 '):
      break
    if not in_round_one or line.startswith('Match ') or line.endswith(' Total'):
      continue
    if parse_vote_line(line):
      rows.append(line)
  return rows


def parse_vote_line(line):
  match = re.match(r'^(\d+)\s+([0-9.]+%)\s+(.+?)\s{2,}(.+)$', line)
  if not match:
    match = re.match(r'^(\d+)\s+([0-9.]+%)\s+(.+)\s+([A-Z][^0-9]+)$', line)
  if not match:
    return None
  return (
    match.group(1).strip(),
    match.group(2).strip(),
    match.group(3).strip(),
    match.group(4).strip(),
  )


def normalize_match_title(value):
  return re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip()


def position_sort_key(position):
  try:
    return float(position)
  except Exception:
    return 0.0
