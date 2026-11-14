#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Otherwise/Tiptree Award parser for SFADB pages.

Maintenance notes:
- SFADB stores current Otherwise winners and former James Tiptree, Jr. winners
  on separate overview pages.
- The all-nominees pages are author-sorted rather than year/category pages, so
  non-winner rows are sorted deterministically after parsing.
- Four pages are fetched in order: the two overview/winners pages, then the two
  all-nominees pages. All rows are deduplicated before position assignment.
"""

import re

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.base import (
    author_list, entry_source_object, imported_entry, ListParserBase,
    parsed_source)
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .base import (
    author_list, entry_source_object, imported_entry, ListParserBase,
    parsed_source)
  from .generic import position_sort_key


AWARD_NAME = 'Otherwise/Tiptree Award'
CATEGORY_NAME = 'Books and Series'
OTHERWISE_URL = 'https://www.sfadb.com/Otherwise_Award'
TIPTREE_URL = 'https://www.sfadb.com/James_Tiptree_Jr_Memorial_Award'
OTHERWISE_NOMINEES_URL = 'https://www.sfadb.com/Otherwise_Award_All_Nominees'
TIPTREE_NOMINEES_URL = 'https://www.sfadb.com/James_Tiptree_Jr_Memorial_Award_All_Nominees'
YEAR_WINNER = re.compile(r'^[-\u2014]\s*(\d{4})\s*[-\u2014]\s*(.*)$')
YEAR_LABEL = re.compile(r'^(\d{4})\s*:$')
AUTHOR_HEADING = re.compile(
  r'^(.+?)\s+\(\d+\s+nomination(?:s)?(?:;\s*\d+\s+win(?:s)?)?\)$', re.I)
RESULT_SPLIT = re.compile(r'\s+[-\u2014]\s+')
RESULT_ORDER = {
  'winner': 0,
  'honor-list': 1,
  'short-list': 2,
  'long-list': 3,
  'special-mention': 4,
}


class OtherwiseTiptreeAwardsParser(ListParserBase):
  """
  Parses Otherwise/Tiptree Award winners and nominees from four SFADB pages.

  Invariants:
  - Overview pages are parsed for winners only; all-nominees pages supply the
    full result spectrum (honor list, short list, long list, special mention).
  - Rows from all four pages are merged by (year, title) before position
    assignment; repeated author-scoped rows contribute canonical coauthors and
    the best result for each unique entry is kept.
  - Within each year, rows are sorted by result rank then title before positions
    are assigned, because the all-nominees pages are author-sorted, not
    result-sorted.
  - Every tied winner shares the base year position; suffixes are reserved for
    non-winner rows.
  """

  def parse(self, overview_html, base_url, fetch_url=None, log=None, progress=None):
    page_specs = [
      (OTHERWISE_URL, overview_html),
      (TIPTREE_URL, None),
      (OTHERWISE_NOMINEES_URL, None),
      (TIPTREE_NOMINEES_URL, None),
    ]
    rows = []
    notes = []
    _progress(progress, 0, len(page_specs), 'Preparing Otherwise/Tiptree pages...')
    for index, (url, html) in enumerate(page_specs, start=1):
      _progress(progress, index, len(page_specs), f'Fetching Otherwise/Tiptree page {index}...')
      try:
        page_html = html if html is not None else fetch_url(url)
      except Exception as err:
        notes.append(f'Otherwise/Tiptree page could not be fetched: {url}: {err}')
        _log(log, 'fetch-failed', {'url': url, 'error': str(err)})
        continue
      parsed_rows = _parse_otherwise_page(page_html, url)
      rows.extend(parsed_rows)
      _log(log, 'page-parsed', {'url': url, 'entries': len(parsed_rows)})
    entries = _otherwise_entries(rows)
    return {
      'name': 'Otherwise/Tiptree - Books and Series',
      'source': parsed_source('Otherwise/Tiptree - Books and Series', OTHERWISE_URL),
      'entries': sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      'notes': notes,
      'match_series': False,
    }


def _parse_otherwise_page(html, source_url):
  if source_url.endswith('_All_Nominees'):
    return _parse_all_nominees(html, source_url)
  return _parse_overview_winners(html, source_url)


def _parse_overview_winners(html, source_url):
  soup = BeautifulSoup(html, 'html.parser')
  rows, found_structured_rows = _parse_structured_overview_winners(
    soup, source_url)
  if found_structured_rows:
    return rows

  lines = _otherwise_text_lines(soup)
  rows = []
  current_year = None
  in_winners = False
  for line in lines:
    if _normalize_heading(line) == 'winners by year':
      in_winners = True
      continue
    if not in_winners:
      continue
    if _is_page_footer(line):
      break
    year_match = YEAR_WINNER.match(line)
    if year_match is not None:
      current_year = year_match.group(1)
      text = year_match.group(2).strip()
      if text:
        row = _parse_overview_item(text, current_year, source_url)
        if row is not None:
          rows.append(row)
      continue
    if current_year is None:
      continue
    row = _parse_overview_item(line, current_year, source_url)
    if row is not None:
      rows.append(row)
  return rows


def _parse_structured_overview_winners(soup, source_url):
  """
  Parse SFADB's two-cell winner rows.

  Refactor warning:
  - Whole-page text separates the year, title, comma, and linked author onto
    different lines. Parsing those lines independently makes comma-bearing
    titles look like complete ``title, author`` rows.
  - A blank left cell continues the preceding year for tied winners.
  """
  rows = []
  current_year = None
  found_rows = False
  for table_row in soup.find_all('tr'):
    left_cell = table_row.find(
      'td', class_=re.compile(r'^winslistleftcol(?:thin)?$'))
    right_cell = table_row.find(
      'td', class_=re.compile(r'^winslistrightcol(?:thin)?$'))
    if left_cell is None or right_cell is None:
      continue
    found_rows = True
    year_match = re.search(
      r'\b((?:19|20)\d{2})\b',
      left_cell.get_text(' ', strip=True))
    if year_match is not None:
      current_year = year_match.group(1)
    if current_year is None:
      continue
    row = _parse_overview_item(
      right_cell.get_text(' ', strip=True), current_year, source_url)
    if row is not None:
      rows.append(row)
  return rows, found_rows


def _parse_all_nominees(html, source_url):
  soup = BeautifulSoup(html, 'html.parser')
  blocks = soup.find_all('div', class_='nomineeblock')
  if blocks:
    return _parse_structured_nominee_blocks(blocks, source_url)

  lines = _otherwise_text_lines(soup)
  rows = []
  current_author = ''
  current_year = None
  for line in lines:
    author_match = AUTHOR_HEADING.match(line)
    if author_match is not None:
      current_author = _invert_author_name(author_match.group(1).strip())
      current_year = None
      continue
    year_match = YEAR_LABEL.match(line)
    if year_match is not None:
      current_year = year_match.group(1)
      continue
    if current_year is None or not current_author:
      continue
    row = _parse_nominee_item(line, current_year, current_author, source_url)
    if row is not None:
      rows.append(row)
  return rows


def _parse_structured_nominee_blocks(blocks, source_url):
  """
  Parse author-scoped nominee blocks and their repeated year/title pairs.

  SFADB may list one author under several years, so each ``dateleftindent``
  must be paired with its following ``titlemid`` sibling within the same block.
  """
  rows = []
  for block in blocks:
    author_node = block.find('div', class_='nominee')
    if author_node is None:
      continue
    author_match = AUTHOR_HEADING.match(
      _normalize_line(author_node.get_text(' ', strip=True)))
    if author_match is None:
      continue
    current_author = _invert_author_name(author_match.group(1).strip())
    for year_node in block.find_all('div', class_='dateleftindent'):
      year_match = re.search(
        r'\b((?:19|20)\d{2})\b', year_node.get_text(' ', strip=True))
      title_node = year_node.find_next_sibling('div', class_='titlemid')
      if year_match is None or title_node is None:
        continue
      row = _parse_nominee_item(
        title_node.get_text(' ', strip=True),
        year_match.group(1),
        current_author,
        source_url)
      if row is not None:
        rows.append(row)
  return rows


def _otherwise_entries(rows):
  unique = {}
  for row in rows:
    key = (row['award_year'], _normalize_identity(row['title']))
    existing = unique.get(key)
    if existing is None:
      existing = dict(row)
      existing['authors'] = author_list(existing.pop('author', ''))
      unique[key] = existing
      continue
    existing['authors'].extend(author_list(row.get('author', '')))
    if _result_rank(row['result']) < _result_rank(existing['result']):
      existing['result'] = row['result']
      existing['source_url'] = row['source_url']

  by_year = {}
  for row in unique.values():
    row['authors'] = _resolve_initial_authors(row['authors'])
    by_year.setdefault(row['award_year'], []).append(row)

  entries = []
  for year in sorted(by_year, key=lambda value: int(value)):
    year_rows = sorted(
      by_year[year],
      key=lambda row: (_result_rank(row['result']), _normalize_identity(row['title'])))
    suffix_index = 0
    for row in year_rows:
      if row['result'] == 'winner':
        position = str(year)
      else:
        suffix_index += 1
        position = f'{year}.{suffix_index:02d}'
      entries.append(imported_entry(
        position,
        row['title'],
        row['authors'],
        source=entry_source_object(row['source_url']),
        award_year=str(year),
        award=AWARD_NAME,
        category=CATEGORY_NAME,
        result=row['result']))
  return entries


def _parse_overview_item(text, year, source_url):
  text = _strip_tie_marker(_normalize_line(text))
  title, author = _split_title_author(text)
  if not title or not author:
    return None
  if _is_short_fiction_title(title):
    return None
  return {
    'award_year': str(year),
    'title': _strip_publication_notes(title).strip(' \"\u201c\u201d,'),
    'author': _strip_publication_notes(author).strip(),
    'source_url': source_url,
    'result': 'winner',
  }


def _parse_nominee_item(text, year, current_author, source_url):
  parts = RESULT_SPLIT.split(_normalize_line(text), maxsplit=1)
  if len(parts) != 2:
    return None
  title_text, result_text = parts
  result = _normalize_result(result_text)
  if result is None:
    return None
  if _normalize_heading(title_text) == 'special award':
    return None
  title, author = _title_author_from_nominee(title_text, current_author)
  if not title or not author or _is_short_fiction_title(title):
    return None
  return {
    'award_year': str(year),
    'title': _strip_publication_notes(title).strip(' \"\u201c\u201d,'),
    'author': _strip_publication_notes(author).strip(),
    'source_url': source_url,
    'result': result,
  }


def _title_author_from_nominee(text, current_author):
  text = _normalize_line(text)
  by_match = re.search(r'\(\s*by\s+(.+?)\s*\)\s*$', text, re.I)
  if by_match is not None:
    title = text[:by_match.start()].strip()
    author_text = by_match.group(1)
    author_text = re.split(
      r',\s*(?:translated|illustrated|art) by\s+|,\s*eds?\.?\s*$',
      author_text,
      maxsplit=1,
      flags=re.I)[0]
    author_text = re.sub(
      r'^(?:written|edited)\s+by\s+', '', author_text, flags=re.I)
    return title, _expand_initial_author(author_text.strip(), current_author)
  return text, current_author


def _resolve_initial_authors(authors):
  """
  Merge duplicate author-scoped rows into canonical contributor lists.

  SFADB repeats a coauthored work under every contributor and abbreviates the
  other names with initials in each copy. Keep the full names from the union
  and replace an initials-only placeholder when its expansion is present.
  """
  values = []
  for author in authors:
    author = _normalize_line(author)
    if author and _normalize_identity(author) not in {
        _normalize_identity(existing) for existing in values}:
      values.append(author)
  full_by_initials = {}
  for author in values:
    if not _is_initials_only(author):
      full_by_initials.setdefault(_author_initials(author).casefold(), author)
  resolved = []
  for author in values:
    if _is_initials_only(author):
      author = full_by_initials.get(_author_initials(author).casefold(), author)
    if _normalize_identity(author) not in {
        _normalize_identity(existing) for existing in resolved}:
      resolved.append(author)
  return resolved


def _is_initials_only(value):
  return bool(re.fullmatch(r'[A-Z]{2,5}', _normalize_line(value)))


def _author_initials(value):
  if _is_initials_only(value):
    return _normalize_line(value)
  return ''.join(
    part[0]
    for part in re.findall(r"[A-Za-z]+", value or '')
    if part)


def _split_title_author(text):
  work_text = _strip_publication_notes(text)
  work_text = re.sub(r',\s*translated by\s+.+$', '', work_text, flags=re.I).strip()
  if ',' not in work_text:
    return '', ''
  title, author = work_text.rsplit(',', 1)
  if _is_author_suffix(author):
    title, author_base = title.rsplit(',', 1) if ',' in title else ('', title)
    author = f'{author_base.strip()}, {author.strip()}'
  return title.strip(), author.strip()


def _normalize_result(text):
  heading = _normalize_heading(text)
  if heading == 'winner':
    return 'winner'
  if heading == 'honor list':
    return 'honor-list'
  if heading in {'short list', 'retrospective tiptree short list'}:
    return 'short-list'
  if heading == 'long list':
    return 'long-list'
  if heading == 'special mention':
    return 'special-mention'
  return None


def _result_rank(result):
  return RESULT_ORDER.get(result, 99)


def _is_short_fiction_title(text):
  text = _strip_tie_marker(_normalize_line(text))
  return (
    len(text) >= 2
    and text[0] in {'"', '\u201c'}
    and text[-1] in {'"', '\u201d'}
  )


def _is_author_suffix(value):
  return _normalize_line(value).casefold().rstrip('.') in {'jr', 'sr', 'ii', 'iii', 'iv', 'v'}


def _expand_initial_author(value, current_author):
  if not value or not current_author:
    return value
  initials = ''.join(part[0] for part in current_author.split() if part)
  compact = re.sub(r'[^A-Za-z]', '', value)
  if compact.casefold() == initials.casefold():
    return current_author
  return value


def _invert_author_name(value):
  if ',' not in value:
    return value
  last, rest = value.split(',', 1)
  return f'{rest.strip()} {last.strip()}'.strip()


def _strip_publication_notes(value):
  value = _normalize_line(value)
  while True:
    stripped = re.sub(r'\s*(?:\([^()]*\)|\[[^\[\]]*\])\s*$', '', value).strip()
    if stripped == value:
      return value
    value = stripped


def _strip_tie_marker(value):
  value = re.sub(r'^\s*\(tie\)\s*:?\s*', '', value, flags=re.I)
  value = re.sub(r'\s*\(tie\)\s*$', '', value, flags=re.I)
  return value.strip()


def _otherwise_text_lines(soup):
  text = soup.get_text('\n')
  return [_normalize_line(line) for line in text.splitlines() if _normalize_line(line)]


def _is_page_footer(line):
  heading = _normalize_heading(line)
  return heading.startswith('copyright') or heading.startswith('this page last updated')


def _normalize_line(value):
  return re.sub(r'\s+', ' ', value or '').strip()


def _normalize_heading(value):
  value = _normalize_line(value).casefold()
  value = value.replace('&', ' and ')
  value = re.sub(r'[^a-z0-9/]+', ' ', value)
  return re.sub(r'\s+', ' ', value).strip()


def _normalize_identity(value):
  return _normalize_heading(value)


def _log(log, label, data):
  if log is not None:
    log(f'Otherwise/Tiptree {label}: {data}')


def _progress(progress, done, total, message):
  if progress is not None:
    progress(done, total, message)


def parse_otherwise_tiptree_awards(overview_html, base_url, fetch_url=None, log=None, progress=None):
  return OtherwiseTiptreeAwardsParser().parse(
    overview_html, base_url, fetch_url=fetch_url, log=log, progress=progress)
