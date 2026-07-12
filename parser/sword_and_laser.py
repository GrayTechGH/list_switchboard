#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Sword & Laser parser, including optional March Madness nomination recovery.

Maintenance notes:
- Main list entries come from the Fandom book-list table. Optional March Madness
  entries come from each linked book page and are inserted at fractional
  positions after the official pick.
- Fandom responses are normalized before parsing because fallback URLs may return
  API JSON, Special:Export XML, raw wikitext, or HTML.
- March Madness parsing is best-effort. Failed linked pages are reported in
  notes instead of aborting the main import.
"""

import re
from urllib.parse import quote, unquote, urljoin, urlparse

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.base import (
    CATEGORY_FANTASY,
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    CATEGORY_SCIENCE_FICTION,
    entry_source_object,
    imported_entry,
    ListParserBase,
    parsed_source,
  )
except ImportError:
  from .base import (
    CATEGORY_FANTASY,
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    CATEGORY_SCIENCE_FICTION,
    entry_source_object,
    imported_entry,
    ListParserBase,
    parsed_source,
  )

from .fandom import fandom_api_html, fandom_wikitext_table_to_html, looks_like_wikitext
from .generic import matching_schema, position_sort_key, token_header_start


class SwordAndLaserParser(ListParserBase):
  """
  Parser for the main Sword & Laser list and optional March Madness recovery.

  Invariant:
  - Returned entries are sorted by numeric position, including fractional
    positions for alternates and nominations.
  """

  FILTER_CATEGORIES = (
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    CATEGORY_SCIENCE_FICTION,
    CATEGORY_FANTASY,
  )

  def parse(self, recipe, html, fetch_url=None, sleep=None, fetch_error=None,
            log=None, progress=None, cached_parsed=None, incremental_update=False):
    html = fandom_api_html(html)
    if looks_like_wikitext(html):
      html = fandom_wikitext_table_to_html(html)
    soup = BeautifulSoup(html, 'html.parser')
    entries = self.parse_main_entries(recipe, soup)
    cached_entries = list((cached_parsed or {}).get('entries') or [])
    incremental_pages = []
    if incremental_update and cached_entries:
      entries, incremental_pages = merge_incremental_sword_and_laser_entries(
        entries, cached_entries, cached_parsed)
    unavailable_march_pages = []
    march_summary = None
    notes = []
    if recipe.options.get('include_march_madness', False):
      entries, unavailable_march_pages, march_summary = self.add_march_entries(
        recipe, entries, fetch_url, sleep, fetch_error, log, progress,
        linked_entries=incremental_pages if incremental_update else None)
      if fetch_url is not None and entries and not any(entry_source_url(entry) for entry in entries):
        notes.append(
          'March Madness details were not fetched because the imported table did not include linked page URLs.')
      elif march_summary is not None:
        notes.append(march_madness_summary_note(march_summary))
    parsed = {
      'name': recipe.NAME,
      'source': parsed_source(recipe.NAME, recipe.URL, getattr(recipe, 'source_id', '')),
      'entries': sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
    }
    if march_summary is not None:
      parsed['march_madness_summary'] = march_summary
    if unavailable_march_pages:
      parsed['march_madness_unavailable_pages'] = unavailable_march_pages
      notes.append(march_madness_unavailable_note(unavailable_march_pages))
    if notes:
      parsed['notes'] = notes
    if incremental_update:
      parsed['incremental_update'] = True
    return parsed

  def parse_main_entries(self, recipe, soup):
    return parse_sword_and_laser_main_entries(recipe, soup)

  def add_march_entries(self, recipe, entries, fetch_url, sleep, fetch_error=None,
                        log=None, progress=None, linked_entries=None):
    return add_sword_and_laser_march_entries(
      recipe, entries, fetch_url, sleep, fetch_error, log, progress,
      linked_entries=linked_entries)

  def parse_march_page(self, soup, official_entry):
    return parse_sword_and_laser_march_page(soup, official_entry)


def parse_sword_and_laser_book_list(
    recipe, html, fetch_url=None, sleep=None, fetch_error=None, log=None, progress=None):
  return SwordAndLaserParser().parse(
    recipe,
    html,
    fetch_url=fetch_url,
    sleep=sleep,
    fetch_error=fetch_error,
    log=log,
    progress=progress)


def entry_author_text(entry):
  return ' '.join(str(author) for author in (entry.get('authors') or []))


def entry_source_url(entry):
  source = entry.get('source') if isinstance(entry.get('source'), dict) else {}
  return source.get('url', '')


def parse_sword_and_laser_main_entries(recipe, soup):
  """Parse the official book-list table, with flattened text as a fallback."""
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


def merge_incremental_sword_and_laser_entries(main_entries, cached_entries, cache):
  """
  Retain saved results and return just the linked pages that need refreshing.

  The main Book List table is still fetched every run so a new monthly pick is
  discovered.  Its linked page is fetched only when that page is new or the
  cache explicitly marks it unfinished.  This keeps the cache useful without
  treating raw page content as persistent data.
  """
  cached_urls = {
    entry_source_url(entry) for entry in cached_entries
    if entry_source_url(entry)
  }
  pending_urls = set(
    ((cache or {}).get('incremental_state') or {}).get('pending_page_urls') or ())
  pages_to_fetch = [
    entry for entry in main_entries
    if entry_source_url(entry)
    and (entry_source_url(entry) not in cached_urls or entry_source_url(entry) in pending_urls)
  ]
  cached_by_position = {
    str(entry.get('position', '')): entry
    for entry in cached_entries
    if entry_source_url(entry)
  }
  merged = list(cached_entries)
  known_main_positions = set(cached_by_position)
  for entry in main_entries:
    position = str(entry.get('position', ''))
    if position not in known_main_positions:
      merged.append(entry)
  return merged, pages_to_fetch


def parse_sword_and_laser_text_entries(recipe, text):
  """Recover entries from flattened Fandom text when table tags are unavailable."""
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
  """Normalize one official Sword & Laser row into a recipe entry."""
  fields = schema['fields']
  data = {}
  for field, value in zip(fields, values):
    data[field] = value.strip()
  seq = data.get('position', '').strip()
  position = sword_and_laser_position(seq)
  title = clean_sword_and_laser_title(data.get('title', ''))
  author = data.get('author', '').strip()
  if title is None:
    return None
  if not position or not title or not author:
    return None
  source_url = ''
  if cells:
    title_index = fields.index('title')
    link = cells[title_index].find('a', href=True)
    if link is not None:
      source_url = urljoin(url, link['href'])
  return imported_entry(
    position,
    title,
    author,
    source=entry_source_object(source_url))


def sword_and_laser_position(seq):
  """
  Convert Sword & Laser sequence labels into sortable numeric positions.

  Maintenance note:
  - The historical alternate-pick suffix "a" sorts halfway after the official
    pick, so "139a" becomes "139.5".
  """
  seq = seq.strip()
  if not seq:
    return ''
  match = re.match(r'^(\d+)(?:\.(\d*))?([a-z])?$', seq, re.I)
  if not match:
    return ''
  number = match.group(1)
  decimal = match.group(2) or ''
  suffix = (match.group(3) or '').casefold()
  if suffix == 'a':
    return f'{number}.5'
  if suffix:
    return ''
  if decimal and set(decimal) != {'0'}:
    return f'{number}.{decimal}'
  return number


def clean_sword_and_laser_title(title):
  """
  Normalize title text and reject rows that represent a whole series.

  Refactor warning:
  - The series-word check is intentionally conservative. "book", "volume", and
    similar indicators allow titles that contain words like "Chronicles" but are
    still individual books.
  """
  title = re.sub(r'\s*\(Alternate Pick\)\s*$', '', title).strip()
  if re.search(r'\bSeries\b', title, re.I):
    return None
  series_indicators = ('chronicles', 'saga', 'cycle', 'trilogy', 'tetralogy', 'quintet')
  book_indicators = ('book', 'volume', 'part', '#', 'vol.')
  title_key = title.casefold()
  has_series_word = any(word in title_key for word in series_indicators)
  has_book_indicator = any(indicator in title_key for indicator in book_indicators)
  if has_series_word and not has_book_indicator:
    return None
  return title


def fetch_sword_and_laser_page(url, fetch_url):
  """
  Fetch a linked Fandom page through fallback URL shapes.

  Maintenance note:
  - API parse is tried before normal HTML/raw/export because it is usually the
    most stable representation for modern Fandom pages.
  """
  parsed = urlparse(url)
  if '/wiki/' not in parsed.path:
    return fetch_url(url), url
  page = unquote(parsed.path.split('/wiki/', 1)[1]).replace('_', ' ')
  base = f'{parsed.scheme}://{parsed.netloc}'
  fallback_urls = (
    f'{base}/api.php?action=parse&page={quote(page)}&prop=text&format=json',
    f'{base}/wiki/Special:Export/{quote(page)}',
    url,
    f'{url}?action=raw',
  )
  for fallback_url in fallback_urls:
    try:
      html = fandom_api_html(fetch_url(fallback_url))
      if looks_like_wikitext(html):
        html = fandom_wikitext_table_to_html(html)
      return html, fallback_url
    except Exception:
      continue
  raise ValueError(f'All fallback URLs failed for {url}')


def add_sword_and_laser_march_entries(
    recipe, entries, fetch_url, sleep, fetch_error=None, log=None, progress=None,
    linked_entries=None):
  """
  Add first-round March Madness nominations from linked book pages.

  Invariants:
  - Duplicate title/author pairs are skipped.
  - Network/page failures are collected and reported without discarding the main
    Sword & Laser list.
  """
  linked_entries = list(linked_entries) if linked_entries is not None else list(entries)
  summary = {
    'main_entries': len(entries),
    'linked_entries': len([entry for entry in linked_entries if entry_source_url(entry)]),
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
    (normalize_match_title(entry.get('title', '')), normalize_match_title(entry_author_text(entry))): entry
    for entry in entries
  }
  unavailable_pages = []
  delay = float(recipe.options.get('fetch_delay_seconds', 1.5))
  linked_index = 0
  for entry in linked_entries:
    url = entry_source_url(entry)
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
      f'Fetching March Madness page {linked_index} of {summary["linked_entries"]}: '
      f'{entry.get("title", "")}')
    if sleep is not None:
      sleep(
        delay,
        f'page {linked_index} of {summary["linked_entries"]}: '
        f'{entry.get("title", "")}')
    try:
      html, fetched_url = fetch_sword_and_laser_page(url, fetch_url)
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
      'fetched_url': fetched_url,
      'nominations': len(nominations),
    })
    for nomination in nominations:
      key = (
        normalize_match_title(nomination.get('title', '')),
        normalize_match_title(entry_author_text(nomination)),
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
  """
  Parse March Madness nominations for one official entry.

  Strategy order:
  - Structured poll tables.
  - Fandom pages with a "from:" nominations section.
  - Plain first-round vote lines.
  """
  base = float(official_entry.get('position', '') or 0)
  rows = parse_sword_and_laser_march_table_rows(soup)
  if rows:
    nominations = []
    for index, (votes, percent, title, author) in enumerate(rows, start=1):
      nominations.append(imported_entry(
        f'{base + (index / 100.0):g}',
        title,
        author,
        votes=votes,
        percent=percent))
    return nominations

  text = soup.get_text('\n', strip=True)
  if 'from:' in text.casefold():
    nominations = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    in_poll = False
    for line in lines:
      line = re.sub(r'[\u200b\u200c\u200d]+', '', line).strip()
      if not line:
        continue
      lower_line = line.casefold()
      if 'from:' in lower_line:
        in_poll = True
        continue
      if not in_poll:
        continue
      if lower_line.startswith(('this book', 'it was decided')):
        continue
      if lower_line.startswith(('sword and laser podcasts:', 'kick off:', 'wrap up:', 'other books in', 'external link:')):
        break
      if 'podcast' in lower_line:
        break
      if line.startswith(official_entry.get('title', '')):
        break
      title = line
      author = entry_author_text(official_entry)
      if ' by ' in line:
        title, author = line.rsplit(' by ', 1)
      nominations.append(imported_entry(
        f'{base + ((len(nominations) + 1) / 100.0):g}',
        title.strip(),
        author.strip(),
        votes='0',
        percent='0%'))
    return nominations

  lines = [line.strip() for line in text.splitlines() if line.strip()]
  first_round = first_round_vote_lines(lines)
  nominations = []
  for index, line in enumerate(first_round, start=1):
    parsed = parse_vote_line(line)
    if not parsed:
      continue
    votes, percent, title, author = parsed
    nominations.append(imported_entry(
      f'{base + (index / 100.0):g}',
      title,
      author,
      votes=votes,
      percent=percent))
  return nominations


def parse_sword_and_laser_march_table_rows(soup):
  """
  Parse table-based March Madness poll rows.

  Maintenance note:
  - Some tables repeat authors with quote marks. `last_author` carries the most
    recent explicit author through those rows.
  """
  all_rows = []
  for table in soup.select('table'):
    rows = []
    last_author = None
    for row in table.select('tr')[1:]:
      cells = row.find_all(['td', 'th'])
      if len(cells) < 4:
        continue
      values = [cell.get_text(' ', strip=True) for cell in cells]
      if any('total' in value.casefold() for value in values):
        continue

      vote_col = None
      percent_col = None
      for index, value in enumerate(values):
        stripped = value.strip()
        if vote_col is None and re.match(r'^\d+', stripped):
          vote_col = index
        if percent_col is None and re.search(r'\d+\.?\d*%?', stripped):
          if '%' in stripped or (index != vote_col and re.match(r'^\d+\.?\d*$', stripped)):
            percent_col = index
      if vote_col is not None and percent_col is None and vote_col + 1 < len(values):
        next_value = values[vote_col + 1].strip()
        if re.match(r'^\d+\.?\d*$', next_value):
          percent_col = vote_col + 1
      if vote_col is None or percent_col is None:
        continue

      title_col = max(vote_col, percent_col) + 1
      author_col = title_col + 1
      if author_col >= len(values):
        continue
      title = clean_sword_and_laser_title(values[title_col].strip())
      if title is None:
        continue

      votes_match = re.search(r'^\d+', values[vote_col].strip())
      percent_match = re.search(r'(\d+\.?\d*)(%)?', values[percent_col].strip())
      if not votes_match or not percent_match:
        continue
      percent = percent_match.group(1)
      if not percent_match.group(2):
        percent += '%'

      author = values[author_col].strip()
      if re.fullmatch(r'["\u201c\u201d\s]+', author):
        author = last_author or author
      else:
        last_author = author

      rows.append((votes_match.group(0), percent, title, author))
    all_rows.extend(rows)
  return all_rows


def first_round_vote_lines(lines):
  """Return vote lines from the first March Madness round only."""
  def looks_like_vote_line_start(value):
    return bool(re.match(r'^(\d+\s+)?(votes\s+)?\d+\.?\d*%', value.strip(), re.I))

  reassembled = []
  index = 0
  while index < len(lines):
    line = lines[index]
    if re.match(r'^\d+\s+votes\s+\d+\.?\d*%', line, re.I) and index + 1 < len(lines):
      next_line = lines[index + 1]
      # Load-bearing: some Fandom exports split "votes/percent" and
      # "Title by Author" onto separate lines. Reassemble before round parsing.
      if (
          ' by ' in next_line.casefold()
          and not looks_like_vote_line_start(next_line)
          and not next_line.startswith('Round ')
          and not next_line.startswith('Match ')
          and not next_line.endswith(' Total')):
        reassembled.append(line + ' ' + next_line)
        index += 2
        continue
    reassembled.append(line)
    index += 1

  lines = reassembled
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
  if not rows:
    for line in lines:
      if line.startswith('Round 2 ') or line.startswith('Semi') or line.startswith('Final'):
        break
      if (
          line.startswith('Round ')
          or line.startswith('Match ')
          or line.endswith(' Total')
          or len(line) < 15
          or '===' in line):
        continue
      if parse_vote_line(line):
        rows.append(line)
  return rows


def parse_vote_line(line):
  """
  Parse one poll result line into votes, percent, title, and author.

  Maintenance note:
  - Fandom pages use both aligned columns and collapsed whitespace. The first
    pattern preserves aligned title/author columns; the later patterns recover
    from collapsed text.
  """
  original_line = line
  match = re.match(r'^(\d+)\s+([0-9.]+%)\s+(.+?)\s{2,}(.+)$', original_line)
  if match:
    return (
      match.group(1).strip(),
      match.group(2).strip(),
      match.group(3).strip(),
      match.group(4).strip(),
    )
  line = re.sub(r'[\s\u00a0]+', ' ', line).strip()
  for pattern in (
      r'^(\d+)\s+votes\s+([0-9.]+%)\s+(.+)$',
      r'^(\d+)\s+([0-9.]+%)\s+(.+)$'):
    match = re.match(pattern, line, re.I)
    if not match:
      continue
    votes = match.group(1).strip()
    percent = match.group(2).strip()
    remainder = match.group(3).strip()
    if ' by ' in remainder:
      title, author = remainder.rsplit(' by ', 1)
      return votes, percent, title.strip(), author.strip()
    fallback = re.match(r'^(.+)\s+([A-Z][^0-9]+)$', remainder)
    if fallback:
      return votes, percent, fallback.group(1).strip(), fallback.group(2).strip()
  return None


def normalize_match_title(value):
  """Normalize title/author pairs for duplicate detection within one import."""
  return re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip()
