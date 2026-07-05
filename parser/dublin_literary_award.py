#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Dublin Literary Award parsers.

Maintenance notes:
- V1 imports winners and shortlists only. Official longlist/nominated sections
  are intentionally treated as boundaries, not parsed rows.
- Official pages have used year pages with result headings and title/author
  blocks. The parser accepts heading-pair rows such as `h3 Title` followed by
  `h4 Author`, plus compact `Title by Author` and linked-title paragraphs.
- Wikipedia is a replacement fallback for winner/shortlist rows and is not
  merged into successful official parses.
"""

import re
import unicodedata
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, split_title_author, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, split_title_author, strip_publication_notes,
  )
  from .generic import position_sort_key


AWARD_NAME = 'Dublin Literary Award'
OFFICIAL_URL = 'https://dublinliteraryaward.ie/the-library/prize-years/'
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Dublin_Literary_Award'
CATEGORY = 'Novel'

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
    match = re.search(r'/prize-years/((?:19|20)\d{2})(?:/|$)', value or '')
    return int(match.group(1)) if match is not None else None

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True) if node is not None else None
    if link is None and getattr(node, 'name', None) == 'a' and node.get('href'):
      link = node
    return urljoin(base_url, link['href']) if link is not None else ''

  def title_link_text(self, node):
    if node is None:
      return ''
    for link in node.find_all('a', href=True):
      text = self.clean_text(link)
      key = _key(text)
      if text and self.year_from_text(text) is None and key not in {
          'read more', 'more', 'winner', 'shortlist', 'longlist', 'nominated'}:
        return text
    return ''

  def ignorable_author_line(self, text):
    key = _key(text)
    return (
      not key or
      key in {'winner', 'shortlist', 'shortlisted', 'longlist', 'nominated'} or
      key.startswith('translated by ') or
      key.startswith('published by ') or
      key.startswith('publisher ') or
      key.startswith('nominated by ') or
      key.startswith('library ') or
      key.startswith('libraries '))

  def parse_text_entry(self, text):
    text = normalize_line(_normalized_text(text))
    text = re.sub(r'^\s*(?:winner|shortlist(?:ed)?|longlist(?:ed)?|nominated)\s*:?\s*', '', text, flags=re.I)
    if not text or self.result_from_text(text) == 'longlisted':
      return '', ''
    by_match = re.match(r'^(.+?)\s+(?:by|written\s+by)\s+(.+)$', text, re.I)
    if by_match is not None:
      return self.clean_title(by_match.group(1)), self.clean_author(by_match.group(2))
    dash_match = re.match(r'^(.+?)\s+[\u2013\u2014-]\s+(.+)$', text)
    if dash_match is not None:
      return self.clean_title(dash_match.group(1)), self.clean_author(dash_match.group(2))
    title, author = split_title_author(text)
    if title and author:
      return self.clean_title(title), self.clean_author(author)
    return '', ''

  def parse_node_entry(self, node, base_url):
    text = self.clean_text(node)
    title = self.title_link_text(node)
    if title:
      remainder = normalize_line(text.replace(title, ' ', 1))
      by_match = re.search(r'(?:^|\s)(?:by|written\s+by)\s+(.+)$', remainder, re.I)
      author_text = by_match.group(1) if by_match is not None else remainder
      if not self.ignorable_author_line(author_text):
        author = self.clean_author(author_text)
        if author:
          return self.clean_title(title), author, self.first_link_url(node, base_url) or base_url
    title, author = self.parse_text_entry(text)
    return title, author, self.first_link_url(node, base_url) or base_url

  def row(self, year, title, author, result, source_url):
    if result == 'longlisted' or not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': source_url,
      'category': CATEGORY,
      'award': AWARD_NAME,
    }

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
      self, html, base_url=OFFICIAL_URL, name=AWARD_NAME, fetch_url=None,
      log=None, progress=None):
    rows = self.parse_page_rows(html, base_url)
    notes = []
    links = self.year_links(html, base_url)
    if fetch_url is not None and links:
      total = len(links)
      for index, (year, url) in enumerate(links, 1):
        try:
          if progress is not None:
            progress(index, total, f'Fetching {name} prize year {index} of {total}')
          rows.extend(self.parse_page_rows(fetch_url(url), url, fallback_year=year))
        except Exception as err:
          notes.append(f'{name} prize year could not be fetched: {url}: {err}')
          if log is not None:
            log(f'{name} prize year failed: {url}: {err}')
    return self.parsed_from_rows(rows, name, base_url, notes=notes)

  def year_links(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    links = {}
    for link in soup.find_all('a', href=True):
      url = urljoin(base_url, link['href'])
      year = self.year_from_url(url)
      if year is not None:
        links.setdefault(year, url)
    return tuple((year, links[year]) for year in sorted(links))

  def parse_page_rows(self, html, base_url, fallback_year=None):
    soup = BeautifulSoup(html, 'html.parser')
    root = soup.find('main') or soup.find('article') or soup.body or soup
    year = (
      self.year_from_url(base_url) or
      self.year_from_text(self.clean_text(soup.find('h1'))) or
      self.year_from_text(self.clean_text(soup.find('title'))) or
      fallback_year)
    rows = []
    current_result = ''
    pending_title = ''
    pending_url = ''

    for node in root.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li']):
      if node.find_parent(['script', 'style', 'nav', 'header', 'footer', 'table']):
        continue
      text = self.clean_text(node)
      if not text:
        continue
      node_year = self.year_from_text(text)
      if node_year is not None:
        year = node_year
      stage = self.result_from_text(text)
      if node.name in {'h1', 'h2'} and stage:
        current_result = stage
        pending_title = ''
        pending_url = ''
        continue
      if node.name in {'h1', 'h2'} and not stage:
        pending_title = ''
        pending_url = ''
        continue
      if current_result not in {RESULT_WINNER, RESULT_SHORTLISTED} or year is None:
        continue
      if stage == 'longlisted':
        current_result = 'longlisted'
        pending_title = ''
        pending_url = ''
        continue
      if self.ignorable_author_line(text):
        continue
      if node.name in {'h3', 'h4', 'h5', 'h6'}:
        if stage in {RESULT_WINNER, RESULT_SHORTLISTED}:
          current_result = stage
          pending_title = ''
          pending_url = ''
          continue
        if pending_title and node.name in {'h4', 'h5', 'h6'} and not self.ignorable_author_line(text):
          row = self.row(year, pending_title, self.clean_author(text), current_result, pending_url or base_url)
          if row is not None:
            rows.append(row)
          pending_title = ''
          pending_url = ''
          continue
        pending_title = self.clean_title(self.title_link_text(node) or text)
        pending_url = self.first_link_url(node, base_url) or base_url
        continue
      if pending_title:
        if self.ignorable_author_line(text):
          continue
        row = self.row(year, pending_title, self.clean_author(text), current_result, pending_url or base_url)
        if row is not None:
          rows.append(row)
        pending_title = ''
        pending_url = ''
        continue
      title, author, source_url = self.parse_node_entry(node, base_url)
      row = self.row(year, title, author, current_result, source_url)
      if row is not None:
        rows.append(row)
    return rows


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
      title = self.clean_title(self.clean_text(title_cell))
      author = self.clean_author(self.clean_text(author_cell))
      parsed = self.row(
        current_year,
        title,
        author,
        result,
        self.first_link_url(title_cell, base_url) or base_url)
      if parsed is not None:
        rows.append(parsed)
    return rows
