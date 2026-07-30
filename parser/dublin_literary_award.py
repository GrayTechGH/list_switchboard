#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Dublin Literary Award parsers.

Maintenance notes:
- V1 imports winners and shortlists only. Official longlist/nominated sections
  are intentionally excluded.
- The official WordPress API returns every prize-year record and embeds the
  rendered winner and shortlist cards. Those named card classes are the source
  contract; surrounding headings, prose, controls, judges, and related features
  must not be interpreted as award rows.
- The official 2000 prize-year page lost one shortlist card during migration.
  ``Charming Billy`` is restored through one source-grounded correction.
- Wikipedia is a replacement fallback and is not merged into a successful
  official parse. Translated title cells retain both title forms for display
  and automatic matching.
"""

import json
import re
import unicodedata

from bs4 import BeautifulSoup, NavigableString

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key


AWARD_NAME = 'Dublin Literary Award'
OFFICIAL_URL = 'https://dublinliteraryaward.ie/the-library/prize-years/'
OFFICIAL_API_URL = (
  'https://dublinliteraryaward.ie/wp-json/wp/v2/prize_years_type'
  '?per_page=100&orderby=date&order=desc&_fields=link,slug,title,content'
)
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Dublin_Literary_Award'
CATEGORY = 'Novel'
BASELINE_FIRST_YEAR = 1996
BASELINE_LAST_YEAR = 2026

# These totals count the winner once even when the official shortlist cards
# repeat it. They lock the completed historical baseline against partial API
# payloads or truncated rendered content.
EXPECTED_BASELINE_COUNTS = {
  1996: 7,
  1997: 8,
  1998: 10,
  1999: 8,
  2000: 7,
  2001: 6,
  2002: 7,
  2003: 8,
  2004: 10,
  2005: 10,
  2006: 10,
  2007: 8,
  2008: 8,
  2009: 8,
  2010: 8,
  2011: 10,
  2012: 10,
  2013: 10,
  2014: 10,
  2015: 10,
  2016: 10,
  2017: 10,
  2018: 10,
  2019: 10,
  2020: 10,
  2021: 6,
  2022: 6,
  2023: 6,
  2024: 6,
  2025: 6,
  2026: 6,
}

CHARMING_BILLY_CORRECTION = {
  'award_year': '2000',
  'title': 'Charming Billy',
  'author': 'Alice McDermott',
  'result': RESULT_SHORTLISTED,
  'source_url': (
    'https://www.irishtimes.com/news/'
    'dublin-novelist-shortlisted-for-literary-award-1.252807'
  ),
  'category': CATEGORY,
  'award': AWARD_NAME,
}

TITLE_CORRECTIONS = {
  (
    '2025',
    normalize_heading('We Are light'),
    normalize_heading('Gerda Blees'),
  ): 'We Are Light',
}

HEADER_ALIASES = {
  'author': 'author',
  'authors': 'author',
  'writer': 'author',
  'writers': 'author',
  'title': 'title',
  'book': 'title',
  'novel': 'title',
  'work': 'title',
  'winner': 'title',
  'result': 'result',
  'status': 'result',
  'year': 'year',
}


def _normalized_text(value):
  value = unicodedata.normalize('NFKC', value or '')
  return value.replace('\xa0', ' ')


def _key(value):
  return normalize_heading(_normalized_text(value))


class DublinLiteraryAwardMixin(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def clean_text(self, node):
    if node is None:
      return ''
    soup = BeautifulSoup(str(node), 'html.parser')
    for removable in soup.find_all(['script', 'style', 'sup']):
      removable.decompose()
    return normalize_line(_normalized_text(soup.get_text(' ', strip=True)))

  def clean_title(self, value):
    value = normalize_line(_normalized_text(value))
    value = re.sub(r'\s*\[[^\[\]]*\]\s*$', '', value).strip()
    value = re.sub(r'^\s*(?:title|book|novel|work)\s*:?\s*', '', value, flags=re.I)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def clean_author(self, value):
    value = strip_publication_notes(normalize_line(_normalized_text(value)))
    value = re.sub(r'^\s*(?:by|author|authors|writer|writers)\s*:?\s*', '', value, flags=re.I)
    value = re.sub(r'\s+translated\s+by\s+.+$', '', value, flags=re.I).strip()
    value = re.sub(r'\s+nominated\s+by\s+.+$', '', value, flags=re.I).strip()
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def result_from_text(self, value):
    key = _key(value)
    if re.search(r'\b(?:nominated|nominees?|long\s*list(?:ed)?|longlist(?:ed)?)\b', key):
      return 'longlisted'
    if re.search(r'\b(?:short\s*list|shortlist|shortlisted|finalist|finalists)\b', key):
      return RESULT_SHORTLISTED
    if re.search(r'\b(?:winner|winners|winning)\b', key):
      return RESULT_WINNER
    return ''

  def year_from_url(self, value):
    match = re.search(r'/prize-years/((?:19|20)\d{2})(?:[-/]|$)', value or '')
    return int(match.group(1)) if match is not None else None

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def row(self, year, title, author, result, source_url, aliases=None):
    if result == 'longlisted' or not title or not author:
      return None
    row = {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': source_url,
      'category': CATEGORY,
      'award': AWARD_NAME,
    }
    if aliases:
      row['aliases'] = list(aliases)
    return row

  def dedupe_rows(self, rows):
    deduped = []
    index_by_key = {}
    for row in rows:
      if not row:
        continue
      title_key = normalize_heading(row.get('title', ''))
      author_key = normalize_heading(row.get('author', ''))
      if not title_key or not author_key:
        continue
      key = (row.get('award_year'), title_key, author_key)
      existing_index = index_by_key.get(key)
      if existing_index is None:
        index_by_key[key] = len(deduped)
        deduped.append(row)
        continue
      existing = deduped[existing_index]
      if existing.get('result') != RESULT_WINNER and row.get('result') == RESULT_WINNER:
        promoted = dict(existing)
        promoted['result'] = RESULT_WINNER
        promoted['source_url'] = row.get('source_url') or existing.get('source_url')
        deduped[existing_index] = promoted
    return deduped

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      try:
        year = int(row['award_year'])
      except Exception:
        continue
      by_year.setdefault(year, []).append(row)
    entries = []
    for year in sorted(by_year):
      year_rows = sorted(
        by_year[year],
        key=lambda row: 0 if row.get('result') == RESULT_WINNER else 1)
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in year_rows
      ]
      entries.extend(assign_positions(award_rows, year))
    return entries

  def parsed_from_rows(self, rows, name, base_url, notes=None):
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def table_grid(self, table):
    grid = []
    rowspans = {}
    for tr in table.find_all('tr'):
      row = []
      column = 0
      for cell in tr.find_all(['th', 'td'], recursive=False):
        while column in rowspans:
          span_cell, remaining = rowspans[column]
          row.append(span_cell)
          if remaining <= 1:
            del rowspans[column]
          else:
            rowspans[column] = (span_cell, remaining - 1)
          column += 1
        colspan = self.span_value(cell, 'colspan')
        rowspan = self.span_value(cell, 'rowspan')
        for _index in range(colspan):
          row.append(cell)
          if rowspan > 1:
            rowspans[column] = (cell, rowspan - 1)
          column += 1
      while column in rowspans:
        span_cell, remaining = rowspans[column]
        row.append(span_cell)
        if remaining <= 1:
          del rowspans[column]
        else:
          rowspans[column] = (span_cell, remaining - 1)
        column += 1
      if row:
        grid.append(row)
    return grid

  def span_value(self, cell, attr):
    try:
      return max(1, int(cell.get(attr, 1)))
    except Exception:
      return 1

  def header_map(self, grid):
    for index, row in enumerate(grid):
      mapped = {}
      for cell_index, cell in enumerate(row):
        key = HEADER_ALIASES.get(_key(self.clean_text(cell)))
        if key is not None and key not in mapped:
          mapped[key] = cell_index
      if {'year', 'title', 'author'}.issubset(set(mapped)):
        return index, mapped
    return -1, {}

  def cell_at(self, row, header_map, key):
    index = header_map.get(key)
    return row[index] if index is not None and index < len(row) else None


class DublinLiteraryAwardOfficialParser(DublinLiteraryAwardMixin):

  def parse(
      self, payload, base_url=OFFICIAL_URL, name=AWARD_NAME, fetch_url=None,
      log=None, progress=None):
    del fetch_url, log, progress
    records = self.load_records(payload)
    rows = []
    completed_years = set()
    declared_counts = {}
    notes = []

    for record in records:
      year = self.record_year(record)
      if year is None:
        continue
      record_rows, declared_count, complete = self.parse_record(record, year)
      if not complete:
        if year <= BASELINE_LAST_YEAR:
          raise ValueError(
            f'Official Dublin Literary Award {year} is missing its winner or shortlist.')
        notes.append(
          f'{year} Dublin Literary Award is not complete yet and was not imported.')
        continue
      rows.extend(record_rows)
      completed_years.add(year)
      if declared_count is not None:
        declared_counts[year] = declared_count

    rows = self.apply_corrections(rows)
    deduped = self.dedupe_rows(rows)
    self.validate_coverage(deduped, completed_years, declared_counts)
    notes.append(
      'The migrated official 2000 page omits Charming Billy; a verified '
      'contemporary shortlist record was added.')
    return self.parsed_from_rows(deduped, name, OFFICIAL_URL, notes=notes)

  def load_records(self, payload):
    try:
      records = json.loads(payload) if isinstance(payload, str) else payload
    except Exception as err:
      raise ValueError('Official Dublin Literary Award API returned invalid JSON.') from err
    if not isinstance(records, list) or not records:
      raise ValueError('Official Dublin Literary Award API returned no prize years.')
    if not all(isinstance(record, dict) for record in records):
      raise ValueError('Official Dublin Literary Award API returned invalid prize-year records.')
    return records

  def record_year(self, record):
    title = record.get('title')
    title = title.get('rendered', '') if isinstance(title, dict) else title
    return (
      self.year_from_text(str(title or '')) or
      self.year_from_text(str(record.get('slug', ''))) or
      self.year_from_url(str(record.get('link', ''))))

  def record_content(self, record):
    content = record.get('content')
    content = content.get('rendered', '') if isinstance(content, dict) else content
    return str(content or '')

  def parse_record(self, record, year):
    source_url = str(record.get('link') or '')
    if not source_url:
      raise ValueError(f'Official Dublin Literary Award {year} has no prize-year URL.')
    soup = BeautifulSoup(self.record_content(record), 'html.parser')
    winner_cards = [
      card
      for card in soup.select('.books-single-cover-item')
      if self.result_from_text(self.clean_text(
        card.select_one('.books-single-cover-item-classification'))) == RESULT_WINNER
    ]
    shortlist_block = next((
      block
      for block in soup.select('.fxb-books-list-block')
      if _key(self.clean_text(block.select_one('.block-heading'))) == 'shortlist'
    ), None)
    if len(winner_cards) != 1 or shortlist_block is None:
      return [], None, False

    rows = []
    winner = self.row_from_card(
      winner_cards[0],
      year,
      RESULT_WINNER,
      source_url,
      '.books-single-cover-item-title',
      '.books-single-cover-item-author')
    if winner is None:
      return [], None, False
    rows.append(winner)

    shortlist_cards = [
      card
      for card in shortlist_block.select('.books-list-item')
      if 'fxb-mod-list-footer-button-wrap' not in card.get('class', ())
    ]
    if not shortlist_cards:
      return [], None, False
    for card in shortlist_cards:
      parsed = self.row_from_card(
        card,
        year,
        RESULT_SHORTLISTED,
        source_url,
        '.books-list-item-title',
        '.books-list-item-author')
      if parsed is None:
        return [], None, False
      rows.append(parsed)

    declared_count = self.declared_shortlist_count(shortlist_block)
    return rows, declared_count, True

  def row_from_card(
      self, card, year, result, source_url, title_selector, author_selector):
    title_node = card.select_one(title_selector)
    author_node = card.select_one(author_selector)
    if title_node is None or author_node is None:
      return None
    title = self.clean_title(self.clean_text(title_node))
    author = self.clean_author(self.clean_text(author_node))
    corrected_title = TITLE_CORRECTIONS.get(
      (str(year), normalize_heading(title), normalize_heading(author)))
    return self.row(
      year,
      corrected_title or title,
      author,
      result,
      source_url)

  def declared_shortlist_count(self, block):
    intro = self.clean_text(block.select_one('.fxb-books-list-intro'))
    match = re.search(r'\b(\d{1,2})\s+books?\b', intro, re.I)
    return int(match.group(1)) if match is not None else None

  def apply_corrections(self, rows):
    correction_key = (
      CHARMING_BILLY_CORRECTION['award_year'],
      normalize_heading(CHARMING_BILLY_CORRECTION['title']),
      normalize_heading(CHARMING_BILLY_CORRECTION['author']),
    )
    existing_keys = {
      (
        row.get('award_year'),
        normalize_heading(row.get('title', '')),
        normalize_heading(row.get('author', '')),
      )
      for row in rows
    }
    if correction_key in existing_keys:
      return rows

    corrected = list(rows)
    insert_at = next((
      index
      for index, row in enumerate(corrected)
      if (
        row.get('award_year') == CHARMING_BILLY_CORRECTION['award_year']
        and row.get('result') != RESULT_WINNER)
    ), len(corrected))
    corrected.insert(insert_at, dict(CHARMING_BILLY_CORRECTION))
    return corrected

  def validate_coverage(self, rows, completed_years, declared_counts):
    expected_years = set(range(BASELINE_FIRST_YEAR, BASELINE_LAST_YEAR + 1))
    if set(EXPECTED_BASELINE_COUNTS) != expected_years:
      raise ValueError(
        'Dublin Literary Award baseline configuration is invalid.')

    missing_years = sorted(expected_years - completed_years)
    if missing_years:
      raise ValueError(
        'Official Dublin Literary Award history is incomplete; missing years: ' +
        ', '.join(str(year) for year in missing_years))

    by_year = {}
    for row in rows:
      by_year.setdefault(int(row['award_year']), []).append(row)
    for year, expected_count in EXPECTED_BASELINE_COUNTS.items():
      year_rows = by_year.get(year, ())
      winners = sum(row.get('result') == RESULT_WINNER for row in year_rows)
      if len(year_rows) != expected_count or winners != 1:
        raise ValueError(
          f'Official Dublin Literary Award {year} coverage is incomplete '
          f'(expected {expected_count} rows and one winner).')

    later_completed = sorted(year for year in completed_years if year > BASELINE_LAST_YEAR)
    if later_completed:
      expected_later = list(range(BASELINE_LAST_YEAR + 1, later_completed[-1] + 1))
      if later_completed != expected_later:
        raise ValueError('Official Dublin Literary Award completed years are not contiguous.')
    for year in later_completed:
      year_rows = by_year.get(year, ())
      winners = sum(row.get('result') == RESULT_WINNER for row in year_rows)
      if not year_rows or winners != 1:
        raise ValueError(
          f'Official Dublin Literary Award {year} is missing usable completed rows.')

    for year, declared_count in declared_counts.items():
      actual_count = len(by_year.get(year, ()))
      if actual_count != declared_count:
        raise ValueError(
          f'Official Dublin Literary Award {year} declared {declared_count} '
          f'shortlist books but produced {actual_count}.')


class DublinLiteraryAwardWikipediaParser(DublinLiteraryAwardMixin):

  def parse(self, html, base_url=WIKIPEDIA_URL, name=AWARD_NAME, **_kwargs):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for table in soup.find_all('table'):
      grid = self.table_grid(table)
      header_index, header_map = self.header_map(grid)
      if header_index < 0:
        continue
      rows.extend(self.table_rows(grid[header_index + 1:], header_map, base_url))
    return self.parsed_from_rows(rows, name, base_url)

  def title_parts(self, cell):
    if cell is None:
      return []
    soup = BeautifulSoup(str(cell), 'html.parser')
    root = soup.find(['td', 'th']) or soup
    for removable in root.find_all(['script', 'style', 'sup']):
      removable.decompose()

    parts = []
    text_nodes = []

    def flush():
      text = self.clean_title(normalize_line(' '.join(text_nodes)))
      text_nodes.clear()
      if text and text not in parts:
        parts.append(text)

    for descendant in root.descendants:
      if getattr(descendant, 'name', None) == 'br':
        flush()
      elif isinstance(descendant, NavigableString):
        text_nodes.append(_normalized_text(str(descendant)))
    flush()
    return parts

  def table_rows(self, grid, header_map, base_url):
    rows = []
    current_year = None
    current_result = ''
    for row in grid:
      year = self.year_from_text(self.clean_text(self.cell_at(row, header_map, 'year')))
      if year is not None:
        current_year = year
      result = self.result_from_text(self.clean_text(self.cell_at(row, header_map, 'result')))
      if result:
        current_result = result
      else:
        result = current_result or RESULT_WINNER
      if result == 'longlisted' or current_year is None:
        continue
      title_cell = self.cell_at(row, header_map, 'title')
      author_cell = self.cell_at(row, header_map, 'author')
      title_parts = self.title_parts(title_cell)
      author = self.clean_author(self.clean_text(author_cell))
      title = ' / '.join(title_parts)
      parsed = self.row(
        current_year,
        title,
        author,
        result,
        base_url,
        aliases=title_parts if len(title_parts) > 1 else None)
      if parsed is not None:
        rows.append(parsed)
    return rows
