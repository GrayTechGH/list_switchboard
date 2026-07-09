#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
ACT Book of the Year Award parsers.

Maintenance notes:
- The official Libraries ACT archive is the primary source. It links one page
  per award year and those pages use result headings around title catalogue
  links.
- Wikipedia is a replacement source and a bounded winner supplement for years
  where the official page exposes shortlist rows but has not yet been updated
  with the winner.
"""

import re
import unicodedata
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


AWARD_NAME = 'ACT Book of the Year Award'
CATEGORY = 'Book of the Year'
OFFICIAL_URL = (
  'https://www.library.act.gov.au/find/history/frequentlyaskedquestions/'
  'Events/literaryawards/book_of_the_year')
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/ACT_Book_of_the_Year_Award'

HEADER_ALIASES = {
  'author': 'author',
  'authors': 'author',
  'writer': 'author',
  'title': 'title',
  'book': 'title',
  'work': 'title',
  'result': 'result',
  'status': 'result',
  'year': 'year',
}

NOISE_KEYS = {
  '',
  'act book of the year',
  'act book of the year award',
  'book of the year',
  'contents',
}


def _normalized_text(value):
  return unicodedata.normalize('NFKC', value or '')


class ACTBookOfTheYearParserMixin(AwardParserBase):

  AWARD_NAME = AWARD_NAME
  CATEGORY = CATEGORY

  def clean_text(self, node):
    if node is None:
      return ''
    node = BeautifulSoup(str(node), 'html.parser')
    for removable in node.find_all(['script', 'style', 'sup']):
      removable.decompose()
    return normalize_line(_normalized_text(node.get_text(' ', strip=True)).replace('\xa0', ' '))

  def clean_title(self, value):
    value = normalize_line(_normalized_text(value))
    value = re.sub(r'\s*\[[^\[\]]*\]\s*$', '', value).strip()
    value = re.sub(r'\s+\([^)]*$', '', value).strip()
    value = strip_publication_notes(value)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def clean_author(self, value):
    value = strip_publication_notes(normalize_line(_normalized_text(value)))
    value = re.sub(r'^\s*(?:by|author|authors)\s*:?\s*', '', value, flags=re.I)
    value = re.sub(r'\s*(?:,|;|:|[\u2013\u2014-])\s*$', '', value).strip()
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True) if node is not None else None
    if link is None and getattr(node, 'name', None) == 'a' and node.get('href'):
      link = node
    return urljoin(base_url, link['href']) if link is not None else ''

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def row(self, year, title, author, result, source_url):
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': source_url,
      'category': self.CATEGORY,
      'award': self.AWARD_NAME,
    }

  def dedupe_rows(self, rows):
    deduped = []
    index_by_key = {}
    for row in rows:
      title_key = normalize_heading(row.get('title', ''))
      author_key = normalize_heading(row.get('author', ''))
      if not title_key or not author_key:
        continue
      key = (row.get('award_year'), title_key, author_key)
      existing_index = index_by_key.get(key)
      if existing_index is None:
        index_by_key[key] = len(deduped)
        deduped.append(row)
      elif (
          deduped[existing_index].get('result') != RESULT_WINNER
          and row.get('result') == RESULT_WINNER):
        deduped[existing_index] = row
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
      entries.extend(assign_positions(
        award_rows, year, tied_winners_share_position=True))
    return entries

  def parsed_rows(self, rows, name, url, notes=None):
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)


class ACTBookOfTheYearOfficialParser(ACTBookOfTheYearParserMixin):

  def parse(
      self, html, base_url=OFFICIAL_URL, name=AWARD_NAME, fetch_url=None,
      year_pages=(), **_kwargs):
    rows = []
    notes = []
    discovered_pages = list(year_pages) or self.discover_year_pages(html, base_url)
    if discovered_pages and fetch_url is not None:
      for year, url in discovered_pages:
        try:
          page_html = fetch_url(url)
          rows.extend(self.parse_year_page(page_html, url, default_year=year))
        except Exception as err:
          notes.append(f'Libraries ACT year page {year} could not be fetched: {err}')
    else:
      rows.extend(self.parse_year_page(
        html, base_url, default_year=self.year_from_text(base_url or '')))
    return self.parsed_rows(rows, name, base_url, notes=notes)

  def discover_year_pages(self, html, base_url=OFFICIAL_URL):
    soup = BeautifulSoup(html, 'html.parser')
    pages = []
    seen = set()
    for link in soup.find_all('a', href=True):
      text = self.clean_text(link)
      href = link.get('href', '')
      haystack = f'{text} {href}'
      year = self.year_from_text(haystack)
      if year is None:
        continue
      key = normalize_heading(haystack)
      if 'book of the year' not in key and not re.search(r'/(?:19|20)\d{2}(?:$|[/?#])', href):
        continue
      url = urljoin(base_url, href)
      if url in seen:
        continue
      seen.add(url)
      pages.append((year, url))
    return tuple(sorted(pages, key=lambda item: item[0]))

  def parse_year_page(self, html, base_url=OFFICIAL_URL, default_year=None):
    soup = BeautifulSoup(html, 'html.parser')
    root = soup.find('main') or soup.find('article') or soup.body or soup
    year = default_year or self.year_from_text(self.clean_text(root)) or self.year_from_text(base_url)
    rows = []
    current_result = None
    for node in root.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li']):
      if node.find_parent(['script', 'style', 'nav', 'header', 'footer']):
        continue
      text = self.clean_text(node)
      if not text:
        continue
      if node.name in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}:
        result = self.result_from_heading(text)
        if result is not None:
          current_result = result
        elif normalize_heading(text) not in NOISE_KEYS and self.year_from_text(text) is None:
          current_result = None
        if year is None:
          year = self.year_from_text(text)
        continue
      if year is None or current_result is None:
        continue
      rows.extend(self.rows_from_entry_node(node, base_url, year, current_result))
    return rows

  def result_from_heading(self, value):
    key = normalize_heading(value)
    if not key:
      return None
    if key in {'winner', 'winners', 'joint winner', 'joint winners'}:
      return RESULT_WINNER
    if key in {
        'highly commended', 'commended', 'shortlist', 'shortlisted',
        'the shortlist', 'shortlisted titles'}:
      return RESULT_SHORTLISTED
    return None

  def rows_from_entry_node(self, node, base_url, year, result):
    rows = []
    for link in node.find_all('a', href=True):
      title = self.clean_title(self.clean_text(link))
      author = self.author_before_link(node, link)
      if not author:
        author = self.author_from_text(self.clean_text(node), title)
      if title and author:
        rows.append(self.row(
          year,
          title,
          author,
          result,
          urljoin(base_url, link['href'])))
    return rows

  def author_before_link(self, node, link):
    parts = []
    for child in node.children:
      if child is link:
        break
      if getattr(child, 'name', None) == 'a':
        continue
      if hasattr(child, 'get_text'):
        parts.append(child.get_text(' ', strip=True))
      else:
        parts.append(str(child))
    author = normalize_line(' '.join(parts))
    author = re.sub(r'^(?:winner|joint winners?|highly commended|shortlist(?:ed)?)\s*:?\s*', '', author, flags=re.I)
    return self.clean_author(author)

  def author_from_text(self, text, title):
    text = normalize_line(text)
    if title and title in text:
      before, _sep, after = text.partition(title)
      author = before or after
    else:
      author = text
    return self.clean_author(author)

  def supplement_missing_winners(self, official_parsed, wikipedia_parsed):
    rows = [dict(entry) for entry in official_parsed.get('entries', ())]
    wiki_rows = [dict(entry) for entry in wikipedia_parsed.get('entries', ())]
    official_by_year = {}
    for row in rows:
      official_by_year.setdefault(row.get('award_year'), []).append(row)
    for year, year_rows in list(official_by_year.items()):
      has_entries = bool(year_rows)
      has_winner = any(row.get('result') == RESULT_WINNER for row in year_rows)
      if not has_entries or has_winner:
        continue
      for wiki_row in wiki_rows:
        if wiki_row.get('award_year') == year and wiki_row.get('result') == RESULT_WINNER:
          rows.append(wiki_row)
    source = official_parsed.get('source') if isinstance(official_parsed.get('source'), dict) else {}
    return self.parsed_result(
      official_parsed.get('name') or AWARD_NAME,
      source.get('url') or OFFICIAL_URL,
      sorted(rows, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=official_parsed.get('notes', ()))


class ACTBookOfTheYearWikipediaParser(ACTBookOfTheYearParserMixin):

  def parse(self, html, base_url=WIKIPEDIA_URL, name=AWARD_NAME, **_kwargs):
    rows = self.parse_rows(html, base_url)
    return self.parsed_rows(rows, name, base_url)

  def parse_rows(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for table in soup.find_all('table'):
      grid = self.table_grid(table)
      header_index, header_map = self.header_map(grid)
      if not {'year', 'title', 'author'}.issubset(set(header_map)):
        continue
      rows.extend(self.table_rows(grid[header_index + 1:], header_map, base_url))
    return rows

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

  def span_value(self, cell, attribute):
    try:
      return max(1, int(cell.get(attribute, 1)))
    except Exception:
      return 1

  def header_map(self, grid):
    for row_index, row in enumerate(grid):
      mapped = {}
      for index, cell in enumerate(row):
        key = HEADER_ALIASES.get(normalize_heading(self.clean_text(cell)))
        if key is not None and key not in mapped:
          mapped[key] = index
      if {'year', 'title', 'author'}.issubset(set(mapped)):
        return row_index, mapped
    return 0, {}

  def table_rows(self, grid, header_map, base_url):
    rows = []
    current_year = None
    current_result = None
    for row in grid:
      year = self.year_from_text(self.cell_text(row, header_map, 'year')) or current_year
      if year is None:
        continue
      if year != current_year:
        current_result = None
      current_year = year
      result_text = self.cell_text(row, header_map, 'result')
      result = self.result_from_text(result_text)
      if result is None:
        result = current_result or RESULT_WINNER
      current_result = result
      title_cell = self.cell_for_key(row, header_map, 'title')
      title = self.clean_title(self.clean_text(title_cell))
      author = self.clean_author(self.cell_text(row, header_map, 'author'))
      if not title or not author:
        continue
      rows.append(self.row(
        year,
        title,
        author,
        result,
        self.first_link_url(title_cell, base_url) or base_url))
    return rows

  def cell_for_key(self, row, header_map, key):
    index = header_map.get(key)
    if index is None or index < 0 or index >= len(row):
      return None
    return row[index]

  def cell_text(self, row, header_map, key):
    return self.clean_text(self.cell_for_key(row, header_map, key))

  def result_from_text(self, value):
    key = normalize_heading(value)
    if not key:
      return None
    if key.startswith('winner') or key in {'won', 'joint winner', 'joint winners'}:
      return RESULT_WINNER
    if (
        key.startswith('highly commended') or key.startswith('commended')
        or key.startswith('shortlist') or key.startswith('shortlisted')):
      return RESULT_SHORTLISTED
    return None


def parse_act_book_of_the_year_official(
    html, url=OFFICIAL_URL, name=AWARD_NAME, fetch_url=None):
  return ACTBookOfTheYearOfficialParser().parse(
    html, url, name, fetch_url=fetch_url)


def parse_act_book_of_the_year_wikipedia(
    html, url=WIKIPEDIA_URL, name=AWARD_NAME):
  return ACTBookOfTheYearWikipediaParser().parse(html, url, name)
