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
  from calibre_plugins.list_switchboard.parser.base import ListParserBase, parsed_source
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .base import ListParserBase, parsed_source
  from .generic import position_sort_key


AWARD_NAME = 'Otherwise/Tiptree Award'
CATEGORY_NAME = 'Books and Series'
OTHERWISE_URL = 'https://www.sfadb.com/Otherwise_Award'
TIPTREE_URL = 'https://www.sfadb.com/James_Tiptree_Jr_Memorial_Award'
OTHERWISE_NOMINEES_URL = 'https://www.sfadb.com/Otherwise_Award_All_Nominees'
TIPTREE_NOMINEES_URL = 'https://www.sfadb.com/James_Tiptree_Jr_Memorial_Award_All_Nominees'
YEAR_WINNER = re.compile(r'^[-\u2014]\s*(\d{4})\s*[-\u2014]\s*(.*)$')
YEAR_LABEL = re.compile(r'^(\d{4}):$')
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
  - Rows from all four pages are deduplicated by (year, title, author) before
    position assignment; the best result for each unique entry is kept.
  - Within each year, rows are sorted by result rank then title before positions
    are assigned, because the all-nominees pages are author-sorted, not
    result-sorted.
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
  lines = _otherwise_text_lines(BeautifulSoup(html, 'html.parser'))
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


def _parse_all_nominees(html, source_url):
  lines = _otherwise_text_lines(BeautifulSoup(html, 'html.parser'))
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


def _otherwise_entries(rows):
  unique = {}
  for row in rows:
    key = (row['award_year'], _normalize_identity(row['title']), _normalize_identity(row['author']))
    existing = unique.get(key)
    if existing is None or _result_rank(row['result']) < _result_rank(existing['result']):
      unique[key] = row

  by_year = {}
  for row in unique.values():
    by_year.setdefault(row['award_year'], []).append(row)

  entries = []
  for year in sorted(by_year, key=lambda value: int(value)):
    year_rows = sorted(
      by_year[year],
      key=lambda row: (_result_rank(row['result']), _normalize_identity(row['title'])))
    suffix_index = 0
    winner_seen = False
    for row in year_rows:
      if row['result'] == 'winner' and not winner_seen:
        position = str(year)
        winner_seen = True
      else:
        suffix_index += 1
        position = f'{year}.{suffix_index:02d}'
      entries.append({
        'position': position,
        'title': row['title'],
        'author': row['author'],
        'source_url': row['source_url'],
        'award_year': str(year),
        'award': AWARD_NAME,
        'category': CATEGORY_NAME,
        'result': row['result'],
      })
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
  if _is_short_fiction_title(title_text) or _normalize_heading(title_text) == 'special award':
    return None
  title, author = _title_author_from_nominee(title_text, current_author)
  if not title or not author:
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
      r',\s*translated by\s+|,\s*eds?\.?\s*$', author_text, maxsplit=1, flags=re.I)[0]
    return title, _expand_initial_author(author_text.strip(), current_author)
  return text, current_author


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
