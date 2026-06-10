#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Nommo Award parser for Wikipedia and narrow official-page fallback shapes.

Maintenance notes:
- Nommo is not available in SFADB, unlike the neighboring award importers.
- Wikipedia's consolidated tables are the primary source for v1.
- Official ASFS pages are used only as a narrow fallback for missing
  year/category rows and are intentionally parsed conservatively.
"""

import re
from urllib.parse import urljoin

from lxml import html as lxml_html

try:
  from calibre_plugins.list_switchboard.parser.base import ListParserBase
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .base import ListParserBase
  from .generic import position_sort_key


AWARD_NAME = 'Nommo Award'
NOMMO_AWARDS_URL = 'https://en.wikipedia.org/wiki/Nommo_Awards'
OFFICIAL_FALLBACK_URLS = (
  'https://www.africansfs.com/nommo-awards/2024-nommo-awards-winners',
)
CATEGORY_ALIASES = {
  'Novel': {'novel', 'ilube nommo award for best speculative fiction novel'},
  'Novella': {'novella', 'best novella'},
  'Graphic Novel': {'graphic novel', 'best graphic novel'},
}
CATEGORY_BOUNDARIES = frozenset({
  'novel', 'novella', 'short story', 'graphic novel',
  'winners and short list nominees',
})


class NommoAwardsParser(ListParserBase):
  """
  Parses Nommo Award winners and nominees from Wikipedia tables with optional
  official-page fallback for missing year/category rows.

  Invariants:
  - Wikipedia rows are always loaded first; fallback rows are only added for
    year/category combinations not already present in the Wikipedia data.
  - Winner rows are identified by a '*' marker in the author cell.
  """

  def parse(self, html, base_url, name, category,
            fetch_url=None, official_urls=None, log=None, progress=None):
    rows = _parse_nommo_wikipedia_rows(html, base_url, category)
    notes = []
    urls = official_urls if official_urls is not None else OFFICIAL_FALLBACK_URLS
    if fetch_url is not None:
      _progress(progress, 0, len(urls), f'Checking {name} official fallback pages...')
      for index, url in enumerate(urls, start=1):
        _progress(progress, index, len(urls), f'Fetching Nommo fallback page {index}...')
        try:
          fallback_html = fetch_url(url)
        except Exception as err:
          notes.append(f'Nommo fallback page could not be fetched: {url}: {err}')
          _log(log, 'fallback-fetch-failed', {'url': url, 'error': str(err)})
          continue
        fallback_rows = _parse_nommo_official_rows(fallback_html, url, category)
        rows = _merge_rows(rows, fallback_rows)
        if fallback_rows:
          _log(log, 'fallback-parsed', {'url': url, 'entries': len(fallback_rows)})
    entries = _nommo_entries(rows)
    return {
      'name': name,
      'url': base_url,
      'entries': sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      'notes': notes,
      'match_series': False,
    }


def _parse_nommo_wikipedia_rows(html, base_url, category):
  root = _html_root(html)
  rows = []
  for heading in root.xpath('//h2|//h3|//h4'):
    if _normalize_nommo_heading(_node_text(heading)) not in _normalized_aliases(category):
      continue
    tables = heading.xpath('following::table[1]')
    if not tables:
      continue
    rows.extend(_parse_nommo_table(tables[0], base_url, category))
  return rows


def _parse_nommo_table(table, base_url, category):
  rows = []
  current_year = None
  for tr in table.xpath('.//tr'):
    cells = tr.xpath('./th|./td')
    if len(cells) < 2:
      continue
    cell_texts = [_clean_cell_text(cell) for cell in cells]
    if _normalize_nommo_heading(cell_texts[0]) == 'year':
      continue
    year = _year_from_text(cell_texts[0])
    if year is None:
      year = current_year
      title_index = 0
      author_index = 1
    else:
      current_year = year
      title_index = 1
      author_index = 2
    if year is None or len(cell_texts) <= author_index:
      continue
    title = _strip_publication_notes(cell_texts[title_index]).strip(' \"\u201c\u201d,')
    author = _strip_winner_marker(_strip_publication_notes(cell_texts[author_index])).strip()
    if not title or not author:
      continue
    result = 'winner' if _cell_has_winner_marker(cells[author_index]) else 'nominee'
    rows.append({
      'award_year': str(year),
      'title': title,
      'author': author,
      'source_url': _first_link_url(cells[title_index], base_url) or base_url,
      'result': result,
      'category': category,
    })
  return rows


def _parse_nommo_official_rows(html, source_url, category):
  lines = _nommo_text_lines(_html_root(html))
  rows = []
  current_year = _first_year(lines, source_url)
  in_category = False
  for line in lines:
    year = _year_from_text(line)
    if year is not None:
      current_year = year
    heading = _normalize_nommo_heading(line)
    if heading in _normalized_aliases(category):
      in_category = True
      continue
    if in_category and heading in CATEGORY_BOUNDARIES:
      break
    if not in_category or current_year is None:
      continue
    parsed = _parse_official_item(line)
    if parsed is not None:
      parsed.update({
        'award_year': str(current_year),
        'source_url': source_url,
        'category': category,
      })
      rows.append(parsed)
  return rows


def _parse_official_item(line):
  text = _normalize_nommo_line(line)
  result = 'nominee'
  winner_match = re.match(r'^winner(?:\s*\(\s*tie\s*\))?\s*:\s*(.+)$', text, re.I)
  if winner_match is not None:
    result = 'winner'
    text = winner_match.group(1).strip()
  elif re.search(r'\(\s*winner\s*\)\s*$', text, re.I):
    result = 'winner'
    text = re.sub(r'\s*\(\s*winner\s*\)\s*$', '', text, flags=re.I).strip()
  split_match = re.match(r'^(.+?)\s+(?:/+\s*)?by\s+(.+)$', text, re.I)
  if split_match is None:
    return None
  title = _strip_publication_notes(split_match.group(1)).strip(' \"\u201c\u201d,')
  author = _strip_publication_notes(split_match.group(2)).strip()
  if not title or not author:
    return None
  return {'title': title, 'author': author, 'result': result}


def _nommo_entries(rows):
  by_year = {}
  for row in rows:
    by_year.setdefault(row['award_year'], []).append(row)
  entries = []
  for year in sorted(by_year, key=lambda v: int(v)):
    suffix_index = 0
    winner_seen = False
    for row in by_year[year]:
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
        'category': row['category'],
        'result': row['result'],
      })
  return entries


def _merge_rows(rows, fallback_rows):
  merged = list(rows)
  seen = {
    (r['award_year'], _normalize_nommo_heading(r['category']),
     _normalize_nommo_heading(r['title']), _normalize_nommo_heading(r['author']))
    for r in merged
  }
  existing_years = {
    (r['award_year'], _normalize_nommo_heading(r['category']))
    for r in merged
  }
  for row in fallback_rows:
    year_category = (row['award_year'], _normalize_nommo_heading(row['category']))
    key = (
      row['award_year'], _normalize_nommo_heading(row['category']),
      _normalize_nommo_heading(row['title']), _normalize_nommo_heading(row['author']),
    )
    if year_category in existing_years or key in seen:
      continue
    merged.append(row)
    seen.add(key)
  return merged


def _clean_cell_text(cell):
  return _normalize_nommo_line(' '.join(
    text.strip()
    for text in cell.xpath(
      './/text()[not(ancestor::sup) and not(ancestor::script) and not(ancestor::style)]')
    if text.strip()))


def _cell_has_winner_marker(cell):
  return '*' in _node_text(cell)


def _strip_winner_marker(value):
  return _normalize_nommo_line(value).replace('*', '').strip()


def _first_link_url(cell, base_url):
  hrefs = cell.xpath('(.//a[@href])[1]/@href')
  return urljoin(base_url, hrefs[0]) if hrefs else ''


def _first_year(lines, source_url):
  for value in (source_url, ' '.join(lines[:5])):
    year = _year_from_text(value)
    if year is not None:
      return year
  return None


def _year_from_text(value):
  match = re.search(r'(19|20)\d{2}', value or '')
  return int(match.group(0)) if match is not None else None


def _strip_publication_notes(value):
  value = _normalize_nommo_line(value)
  value = re.sub(r'\s*\[[^\[\]]*\]\s*$', '', value).strip()
  while True:
    stripped = re.sub(r'\s*(?:\([^()]*\)|\[[^\[\]]*\])\s*$', '', value).strip()
    if stripped == value:
      return value
    value = stripped


def _html_root(html):
  return lxml_html.fromstring(html or '<html></html>')


def _node_text(node):
  return _normalize_nommo_line(' '.join(
    text.strip()
    for text in node.xpath('.//text()[not(ancestor::script) and not(ancestor::style)]')
    if text.strip()))


def _nommo_text_lines(root):
  block_lines = [
    _node_text(node)
    for node in root.xpath('//h1|//h2|//h3|//h4|//p|//li')
  ]
  return [line for line in block_lines if line]


def _normalized_aliases(category):
  return {_normalize_nommo_heading(a) for a in CATEGORY_ALIASES.get(category, {category})}


def _normalize_nommo_line(value):
  return re.sub(r'\s+', ' ', value or '').strip()


def _normalize_nommo_heading(value):
  value = _normalize_nommo_line(value).casefold()
  value = value.replace('&', ' and ')
  value = re.sub(r'[^a-z0-9/]+', ' ', value)
  return re.sub(r'\s+', ' ', value).strip()


def _log(log, label, data):
  if log is not None:
    log(f'Nommo Awards {label}: {data}')


def _progress(progress, done, total, message):
  if progress is not None:
    progress(done, total, message)


def parse_nommo_awards(
    html, base_url, name, category,
    fetch_url=None, official_urls=None, log=None, progress=None):
  return NommoAwardsParser().parse(
    html, base_url, name, category,
    fetch_url=fetch_url, official_urls=official_urls, log=log, progress=progress)
