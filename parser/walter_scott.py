#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Walter Scott Prize parser for the official PDF/history pages and Wikipedia.

Maintenance notes:
- The official archive source is a PDF covering previous winners and
  shortlists. Keep the tiny PDF text extractor local to this source shape until
  another production recipe needs binary PDF parsing.
- V1 imports winners and shortlists only. Official longlists are deliberately
  ignored to match adjacent literary-award recipes.
"""

import re
import zlib
from urllib.parse import urljoin

from bs4 import BeautifulSoup

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


AWARD_NAME = 'Walter Scott Prize'
CATEGORY = 'Historical Fiction'
PDF_URL = (
  'https://www.walterscottprize.co.uk/wp-content/uploads/2025/08/'
  'PREVIOUS-WINNERS-OF-THE-WALTER-SCOTT-PRIZE-FOR-HISTORICAL-FICTION.pdf')
SHORTLIST_URL_2026 = 'https://www.walterscottprize.co.uk/the-2026-prize/the-2026-shortlist/'
WINNER_URL_2026 = 'https://www.walterscottprize.co.uk/alice-jolly-wins-2026-walter-scott-prize/'
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Walter_Scott_Prize'


HEADER_ALIASES = {
  'year': 'year',
  'author': 'author',
  'authors': 'author',
  'writer': 'author',
  'writers': 'author',
  'title': 'title',
  'book': 'title',
  'novel': 'title',
  'work': 'title',
  'result': 'result',
  'status': 'result',
  'stage': 'result',
}


class WalterScottParserMixin(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def clean_text(self, node):
    if node is None:
      return ''
    node = BeautifulSoup(str(node), 'html.parser')
    for removable in node.find_all(['script', 'style', 'sup']):
      removable.decompose()
    text = node.get_text(' ', strip=True).replace('\xa0', ' ')
    text = re.sub(r'\s*\[\s*\d+\s*\]\s*', ' ', text)
    return normalize_line(text)

  def clean_title(self, value):
    value = strip_publication_notes(normalize_line(value))
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def clean_author(self, value):
    value = strip_publication_notes(normalize_line(value))
    value = re.sub(r'^\s*(?:by|author|authors)\s*:\s*', '', value, flags=re.I)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True) if node is not None else None
    return urljoin(base_url, link['href']) if link is not None else ''

  def dedupe_rows(self, rows):
    deduped = []
    index_by_key = {}
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      existing_index = index_by_key.get(key)
      if existing_index is None:
        index_by_key[key] = len(deduped)
        deduped.append(row)
        continue
      if (
          deduped[existing_index].get('result') != RESULT_WINNER
          and row.get('result') == RESULT_WINNER):
        deduped[existing_index] = row
    return deduped

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      year_rows = sorted(
        by_year[year],
        key=lambda row: 0 if row.get('result') == RESULT_WINNER else 1)
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, CATEGORY)
        for row in year_rows
      ]
      entries.extend(assign_positions(
        award_rows, int(year), tied_winners_share_position=True))
    return entries


class WalterScottOfficialParser(WalterScottParserMixin):

  SUPPLEMENT_URLS = (
    (SHORTLIST_URL_2026, RESULT_SHORTLISTED),
    (WINNER_URL_2026, RESULT_WINNER),
  )

  def parse(
      self, pdf_or_text, base_url=PDF_URL, name=AWARD_NAME, fetch_url=None,
      current_pages=None, log=None, progress=None):
    rows = list(self.parse_pdf_rows(pdf_or_text, base_url))
    notes = []
    pages = list(current_pages or ())

    if fetch_url is not None and current_pages is None:
      total = len(self.SUPPLEMENT_URLS)
      for index, (url, result) in enumerate(self.SUPPLEMENT_URLS, 1):
        try:
          if progress is not None:
            progress(index, total, f'Fetching {name} supplement page {index} of {total}')
          pages.append((url, result, fetch_url(url)))
        except Exception as err:
          notes.append(f'{name} supplement page could not be fetched: {url}: {err}')
          if log is not None:
            log(f'{name} supplement page failed: {url}: {err}')

    for page in pages:
      if len(page) == 2:
        url, html = page
        result = RESULT_SHORTLISTED
      else:
        url, result, html = page
      rows.extend(self.parse_html_rows(html, url, result))

    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def parse_pdf_rows(self, pdf_or_text, base_url=PDF_URL):
    text = self.extract_pdf_text(pdf_or_text)
    return self.rows_from_text(text, base_url)

  def extract_pdf_text(self, value):
    if isinstance(value, bytes):
      data = value
      source_text = value.decode('latin-1', 'ignore')
    else:
      source_text = str(value or '')
      data = source_text.encode('latin-1', 'ignore')
    if '%PDF' not in source_text[:1024]:
      return source_text

    fragments = []
    for match in re.finditer(rb'stream\r?\n(.*?)\r?\nendstream', data, re.S):
      stream = match.group(1).strip(b'\r\n')
      try:
        stream = zlib.decompress(stream)
      except Exception:
        pass
      fragments.extend(self.pdf_text_fragments(stream))
    return '\n'.join(fragments)

  def pdf_text_fragments(self, stream):
    text = stream.decode('latin-1', 'ignore')
    fragments = []
    for array in re.finditer(r'\[(.*?)\]\s*TJ', text, re.S):
      fragments.append(''.join(self.pdf_literal_strings(array.group(1))))
    for item in re.finditer(r'(\((?:\\.|[^\\()])*\)|<[\da-fA-F\s]+>)\s*(?:Tj|\'|")', text, re.S):
      fragments.append(self.decode_pdf_string(item.group(1)))
    return [normalize_line(item) for item in fragments if normalize_line(item)]

  def pdf_literal_strings(self, value):
    return [
      self.decode_pdf_string(item.group(0))
      for item in re.finditer(r'\((?:\\.|[^\\()])*\)|<[\da-fA-F\s]+>', value, re.S)
    ]

  def decode_pdf_string(self, token):
    if token.startswith('<'):
      compact = re.sub(r'\s+', '', token.strip('<>'))
      try:
        return bytes.fromhex(compact).decode('utf-16-be', 'ignore')
      except Exception:
        try:
          return bytes.fromhex(compact).decode('latin-1', 'ignore')
        except Exception:
          return ''
    value = token[1:-1]
    value = re.sub(r'\\\r?\n', '', value)
    replacements = {
      r'\(': '(',
      r'\)': ')',
      r'\\': '\\',
      r'\n': '\n',
      r'\r': '\n',
      r'\t': ' ',
    }
    for source, target in replacements.items():
      value = value.replace(source, target)
    return value

  def rows_from_text(self, text, base_url):
    rows = []
    current_year = None
    current_result = None
    pending = ''

    for line in self.source_lines(text):
      line_year = self.line_year(line)
      if line_year is not None:
        pending = self.flush_pending(rows, pending, current_year, current_result, base_url)
        current_year = line_year
        current_result = None
        remainder = self.line_without_year(line, line_year)
        if remainder:
          result, remainder = self.result_prefix(remainder, current_result)
          current_result = result or current_result
          pending = self.consume_entry_line(rows, pending, remainder, current_year, current_result, base_url)
        continue

      result, remainder = self.result_prefix(line, current_result)
      if result is not None:
        pending = self.flush_pending(rows, pending, current_year, current_result, base_url)
        current_result = result
        if remainder:
          pending = self.consume_entry_line(rows, pending, remainder, current_year, current_result, base_url)
        continue

      if current_year is not None and current_result in {RESULT_WINNER, RESULT_SHORTLISTED}:
        pending = self.consume_entry_line(rows, pending, line, current_year, current_result, base_url)

    self.flush_pending(rows, pending, current_year, current_result, base_url)
    return rows

  def source_lines(self, text):
    text = (text or '').replace('\r', '\n')
    text = re.sub(r'\b(20[1-2]\d)\s+(Winner|Shortlist|Shortlisted)\b', r'\n\1\n\2', text, flags=re.I)
    text = re.sub(r'\b(Winner|Shortlist|Shortlisted)\s*:?(\s+)', r'\n\1 ', text, flags=re.I)
    text = re.sub(r'\b(Longlist|Longlisted)\s*:?(\s+)', r'\n\1 ', text, flags=re.I)
    lines = []
    for raw_line in re.split(r'[\n;]+', text):
      line = normalize_line(raw_line)
      if not line or self.is_noise_line(line):
        continue
      lines.append(line)
    return lines

  def is_noise_line(self, line):
    heading = normalize_heading(line)
    if not heading:
      return True
    if 'previous winners of the walter scott prize' in heading:
      return True
    if heading in {
        'winner',
        'winners',
        'shortlist',
        'shortlisted',
        'the shortlist',
        'longlist',
        'longlisted',
        'the longlist',
    }:
      return False
    return heading in {
      'walter scott prize',
      'walter scott prize for historical fiction',
      'historical fiction',
      'previous winners and shortlists',
    }

  def line_year(self, line):
    match = re.match(r'^\s*(20[1-2]\d)\b', line)
    if match is None:
      return None
    return int(match.group(1))

  def line_without_year(self, line, year):
    return normalize_line(re.sub(r'^\s*%s\b\s*' % year, '', line))

  def result_prefix(self, line, current_result=None):
    heading = normalize_heading(line)
    if heading in {'winner', 'winners'}:
      return RESULT_WINNER, ''
    if heading in {'shortlist', 'shortlisted', 'the shortlist'}:
      return RESULT_SHORTLISTED, ''
    if heading in {'longlist', 'longlisted', 'the longlist'}:
      return 'longlisted', ''
    match = re.match(
      r'^\s*(winner|winners|shortlist|shortlisted|the shortlist|longlist|longlisted|the longlist)\s*:?\s*(.+)$',
      line,
      re.I)
    if match is None:
      return None, line
    if normalize_heading(match.group(1)) in {'longlist', 'longlisted', 'the longlist'}:
      return 'longlisted', normalize_line(match.group(2))
    result = (
      RESULT_WINNER
      if normalize_heading(match.group(1)) in {'winner', 'winners'}
      else RESULT_SHORTLISTED)
    return result, normalize_line(match.group(2))

  def consume_entry_line(self, rows, pending, line, year, result, source_url):
    pending = normalize_line(f'{pending} {line}' if pending else line)
    parsed = self.row_from_text(pending, year, result, source_url)
    if parsed is None:
      return pending
    rows.append(parsed)
    return ''

  def flush_pending(self, rows, pending, year, result, source_url):
    if pending and year is not None and result in {RESULT_WINNER, RESULT_SHORTLISTED}:
      parsed = self.row_from_text(pending, year, result, source_url)
      if parsed is not None:
        rows.append(parsed)
    return ''

  def row_from_text(self, text, year, result, source_url):
    if year is None or result not in {RESULT_WINNER, RESULT_SHORTLISTED}:
      return None
    parsed = self.title_author_from_text(text)
    if parsed is None:
      return None
    title, author = parsed
    if not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': source_url,
      'category': CATEGORY,
    }

  def title_author_from_text(self, value):
    value = normalize_line(value)
    value = re.sub(r'^\s*[*\-\u2022]\s*', '', value)
    value = re.sub(r'\s+(winner|shortlisted)\s*$', '', value, flags=re.I)
    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', value, re.I)
    if by_match is not None:
      return (
        self.clean_title(by_match.group(1)),
        self.clean_author(by_match.group(2)))
    dash_match = re.match(r'^(.+?)\s+[\u2013\u2014-]\s+(.+)$', value)
    if dash_match is not None:
      return (
        self.clean_title(dash_match.group(1)),
        self.clean_author(dash_match.group(2)))
    compact = strip_publication_notes(value)
    parts = re.split(r'\s{2,}', compact)
    if len(parts) >= 2:
      return self.clean_title(parts[0]), self.clean_author(parts[1])
    if ',' in compact:
      title, author = compact.rsplit(',', 1)
      return self.clean_title(title), self.clean_author(author)
    return None

  def parse_html_rows(self, html, base_url, result):
    year = self.year_from_text(base_url) or self.year_from_text(html)
    if year is None:
      return []
    soup = BeautifulSoup(html or '', 'html.parser')
    rows = []
    for line in self.html_candidate_lines(soup):
      parsed = self.title_author_from_text(line)
      if parsed is None:
        continue
      title, author = parsed
      if not title or not author:
        continue
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': self.line_source_url(soup, line, base_url),
        'category': CATEGORY,
      })
    return rows

  def html_candidate_lines(self, soup):
    candidates = []
    for node in soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'li', 'strong']):
      text = self.clean_text(node)
      if self.title_author_from_text(text) is not None:
        candidates.append(text)
    return candidates

  def line_source_url(self, soup, line, base_url):
    normalized = normalize_heading(line)
    for node in soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'li', 'strong']):
      if normalize_heading(self.clean_text(node)) == normalized:
        return self.first_link_url(node, base_url) or base_url
    return base_url


class WalterScottWikipediaParser(WalterScottParserMixin):

  def parse(self, html, base_url=WIKIPEDIA_URL, name=AWARD_NAME):
    rows = self.dedupe_rows(self.parse_rows(html, base_url))
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for table in soup.find_all('table'):
      header_map = self.header_map(table)
      if not {'year', 'title', 'author'}.issubset(set(header_map)):
        continue
      rows.extend(self.table_rows(table, header_map, base_url))
    return rows

  def header_map(self, table):
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      mapped = {}
      for index, cell in enumerate(cells):
        key = HEADER_ALIASES.get(normalize_heading(self.clean_text(cell)))
        if key is not None and key not in mapped:
          mapped[key] = index
      if {'year', 'title', 'author'}.issubset(set(mapped)):
        return mapped
    return {}

  def table_rows(self, table, header_map, base_url):
    rows = []
    current_year = None
    current_result_by_year = {}
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      if not cells or self.is_header_row(cells, header_map):
        continue
      missing_year_cell = self.row_omits_year(cells, header_map, current_year)
      year_cell = self.cell_for_key(cells, header_map, 'year', missing_year_cell)
      year = current_year
      if year_cell is not None and not missing_year_cell:
        year = self.year_from_text(self.clean_text(year_cell)) or current_year
      if year is None:
        continue
      current_year = year

      result_cell = self.cell_for_key(cells, header_map, 'result', missing_year_cell)
      result = self.result_from_cell(result_cell)
      if result is None:
        result = (
          RESULT_SHORTLISTED
          if current_result_by_year.get(year) == RESULT_SHORTLISTED
          else None)
      if result not in {RESULT_WINNER, RESULT_SHORTLISTED}:
        continue

      title_cell = self.cell_for_key(cells, header_map, 'title', missing_year_cell)
      author_cell = self.cell_for_key(cells, header_map, 'author', missing_year_cell)
      title = self.clean_title(self.clean_text(title_cell))
      author = self.clean_author(self.clean_text(author_cell))
      if not title or not author:
        continue
      current_result_by_year[year] = result
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': self.first_link_url(title_cell, base_url) or base_url,
        'category': CATEGORY,
      })
    return rows

  def is_header_row(self, cells, header_map):
    for key, index in header_map.items():
      if index >= len(cells):
        return False
      if HEADER_ALIASES.get(normalize_heading(self.clean_text(cells[index]))) != key:
        return False
    return True

  def row_omits_year(self, cells, header_map, current_year):
    if current_year is None or header_map.get('year') != 0:
      return False
    if len(cells) > max(header_map.values()):
      return False
    return self.year_from_text(self.clean_text(cells[0])) is None

  def cell_for_key(self, cells, header_map, key, missing_year_cell):
    index = header_map.get(key)
    if index is None:
      return None
    if missing_year_cell and index > header_map['year']:
      index -= 1
    return cells[index] if 0 <= index < len(cells) else None

  def result_from_cell(self, cell):
    text = normalize_heading(self.clean_text(cell))
    if not text:
      return None
    if text.startswith('winner') or text.startswith('won'):
      return RESULT_WINNER
    if text.startswith('shortlist') or text.startswith('finalist'):
      return RESULT_SHORTLISTED
    if text.startswith('longlist'):
      return 'longlisted'
    return None


def parse_walter_scott_official(
    pdf_or_text, base_url=PDF_URL, name=AWARD_NAME, fetch_url=None,
    current_pages=None, log=None, progress=None):
  return WalterScottOfficialParser().parse(
    pdf_or_text,
    base_url,
    name,
    fetch_url=fetch_url,
    current_pages=current_pages,
    log=log,
    progress=progress)


def parse_walter_scott_wikipedia(html, base_url=WIKIPEDIA_URL, name=AWARD_NAME):
  return WalterScottWikipediaParser().parse(html, base_url, name)
