#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Prime Minister's Literary Awards parsers.

Maintenance notes:
- Creative Australia is the primary source. The archive page links annual pages
  whose book blocks expose title, author, year, category, and winner markers.
- Wikipedia is a replacement fallback for the same configured category only.
- V1 imports winners and shortlisted/finalist books from core book categories;
  Poetry and judging-panel/biography sections stay outside the recipe scope.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, RESULT_LONGLISTED, RESULT_SHORTLISTED, RESULT_WINNER,
    assign_positions, normalize_heading, normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_LONGLISTED, RESULT_SHORTLISTED, RESULT_WINNER,
    assign_positions, normalize_heading, normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key


AWARD_NAME = "Prime Minister's Literary Awards"
OFFICIAL_URL = 'https://creative.gov.au/news-events/events/prime-ministers-literary-awards'
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Prime_Minister%27s_Literary_Awards'

HEADER_ALIASES = {
  'year': 'year',
  'author': 'author',
  'authors': 'author',
  'title': 'title',
  'work': 'title',
  'book': 'title',
  'result': 'result',
  'status': 'result',
  'ref': 'ref',
}

AUTHOR_STOP_HEADINGS = {
  'about the author',
  'about the illustrator',
  'judges comments',
  'judges comment',
}


def _category_key(value):
  return normalize_heading(value).replace('non fiction', 'nonfiction')


class PrimeMinistersLiteraryAwardsOfficialParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def __init__(self, category, category_aliases=()):
    self.category = category
    self.category_aliases = tuple(category_aliases or (category,))
    self.category_keys = {_category_key(alias) for alias in self.category_aliases}

  def parse(
      self, html, base_url=OFFICIAL_URL, name=AWARD_NAME, fetch_url=None,
      log=None, progress=None):
    pages = [(base_url, html)]
    notes = []
    archive_links = self.archive_links(html, base_url)
    if fetch_url is not None and archive_links:
      total = len(archive_links)
      for index, url in enumerate(archive_links, 1):
        if url == base_url:
          continue
        try:
          if progress is not None:
            progress(index, total, f'Fetching {name} archive page {index} of {total}')
          pages.append((url, fetch_url(url)))
        except Exception as err:
          notes.append(f'{name} archive page could not be fetched: {url}: {err}')
          if log is not None:
            log(f'{name} archive page failed: {url}: {err}')

    rows = []
    for url, page_html in pages:
      rows.extend(self.page_rows(page_html, url))

    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def archive_links(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    links = {}
    for link in soup.find_all('a', href=True):
      text = self.clean_text(link)
      href = link['href']
      combined = f'{text} {href}'
      year = self.year_from_text(combined)
      if year is None:
        continue
      if year < 2008:
        continue
      if 'pmla' not in href and 'prime-ministers-literary-awards' not in href:
        continue
      links[year] = urljoin(base_url, href)
    return tuple(url for _year, url in sorted(links.items()))

  def page_rows(self, html, page_url):
    soup = BeautifulSoup(html, 'html.parser')
    rows = self.detail_rows(soup, page_url)
    rows.extend(self.card_rows(soup, page_url))
    return rows

  def detail_rows(self, soup, page_url):
    rows = []
    for container in soup.find_all(['p', 'li']):
      text = self.clean_text(container)
      if 'Shortlist year' not in text:
        continue
      metadata_text = self.metadata_text(container)
      year = self.year_from_text(metadata_text)
      category = self.category_from_text(metadata_text)
      if year is None or not self.category_matches(category):
        continue

      title_node = self.previous_title_heading(container)
      if title_node is None:
        continue
      title = self.clean_title(self.clean_text(title_node))
      author = self.author_before_info(title_node, container)
      if not title or not author:
        continue

      result = self.result_for_detail(container, title_node)
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': self.first_link_url(title_node, page_url) or page_url,
        'category': self.category,
      })
    return rows

  def metadata_text(self, node):
    parts = [self.clean_text(node)]
    for sibling in node.find_next_siblings():
      if getattr(sibling, 'name', None) in {'h2', 'h3'}:
        break
      text = self.clean_text(sibling)
      if not text:
        continue
      if text.startswith('Shortlist category') or text.startswith('Published by') or text.startswith('Publisher'):
        parts.append(text)
      if text.startswith('Published by') or text.startswith('Publisher'):
        break
    return normalize_line(' '.join(parts))

  def card_rows(self, soup, page_url):
    rows = []
    page_year = self.year_from_text(self.clean_text(soup.find('title'))) or self.year_from_text(page_url)
    if page_year is None:
      return rows
    for heading in soup.find_all(['h2', 'h3']):
      category = self.clean_text(heading)
      if not self.category_matches(category):
        continue
      for node in self.section_nodes(heading):
        if not self.has_class(node, 'card-portrait--content-title'):
          continue
        text = self.clean_text(node)
        title, author, result = self.parse_card_title(text)
        if not title or not author:
          continue
        rows.append({
          'award_year': str(page_year),
          'title': title,
          'author': author,
          'result': result,
          'source_url': self.first_link_url(node, page_url) or page_url,
          'category': self.category,
        })
    return rows

  def section_nodes(self, heading):
    for node in heading.find_all_next():
      if node is heading:
        continue
      if node.name in {'h2'}:
        break
      yield node

  def previous_title_heading(self, node):
    for candidate in node.find_all_previous(['h2', 'h3']):
      text = self.clean_text(candidate)
      if not text or _category_key(text) in self.category_keys:
        continue
      if normalize_heading(text) in AUTHOR_STOP_HEADINGS:
        continue
      return candidate
    return None

  def author_before_info(self, title_node, info_node):
    for sibling in title_node.find_next_siblings():
      if sibling is info_node:
        break
      if getattr(sibling, 'name', None) in {'h2', 'h3'}:
        break
      text = self.clean_text(sibling)
      if not text or self.is_metadata_line(text):
        continue
      return self.clean_author(text)
    card = self.previous_card_title(info_node)
    if card is not None:
      title, author, _result = self.parse_card_title(self.clean_text(card))
      if normalize_heading(title) == normalize_heading(self.clean_text(title_node)):
        return author
    return ''

  def result_for_detail(self, info_node, title_node):
    for sibling in title_node.find_next_siblings():
      if sibling is info_node:
        break
      if normalize_heading(self.clean_text(sibling)) == 'winner':
        return RESULT_WINNER
    card = self.previous_card_title(info_node)
    if card is not None and self.clean_text(card).casefold().startswith('winner'):
      card_title, _author, _result = self.parse_card_title(self.clean_text(card))
      if normalize_heading(card_title) != normalize_heading(self.clean_text(title_node)):
        return RESULT_SHORTLISTED
      return RESULT_WINNER
    return RESULT_SHORTLISTED

  def previous_card_title(self, node):
    for candidate in node.find_all_previous(['p', 'div']):
      if self.has_class(candidate, 'card-portrait--content-title'):
        return candidate
    return None

  def parse_card_title(self, text):
    result = RESULT_SHORTLISTED
    text = normalize_line(text)
    match = re.match(r'^winner\s*:\s*(.+)$', text, re.I)
    if match is not None:
      result = RESULT_WINNER
      text = match.group(1).strip()
    text = text.strip(' "\u201c\u201d')
    dash_match = re.match(r'^(.+?)\s+[\u2013\u2014-]\s+(.+)$', text)
    if dash_match is not None:
      return (
        self.clean_title(dash_match.group(1)),
        self.clean_author(dash_match.group(2)),
        result)
    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', text, re.I)
    if by_match is not None:
      return (
        self.clean_title(by_match.group(1)),
        self.clean_author(by_match.group(2)),
        result)
    if ',' in text:
      title, author = text.rsplit(',', 1)
      return self.clean_title(title), self.clean_author(author), result
    return '', '', result

  def category_from_text(self, value):
    match = re.search(
      r'Shortlist category:\s*(.+?)(?:\s+Published by:|\s+Publisher:|$)',
      value,
      re.I)
    return normalize_line(match.group(1)) if match is not None else ''

  def category_matches(self, value):
    return _category_key(value) in self.category_keys

  def is_metadata_line(self, value):
    heading = normalize_heading(value)
    return (
      heading == 'winner'
      or heading.startswith('shortlist year')
      or heading.startswith('shortlist category')
      or heading.startswith('published by')
      or heading.startswith('publisher'))

  def has_class(self, node, class_name):
    return class_name in (getattr(node, 'get', lambda _name, _default=None: [])('class', []) or [])

  def clean_text(self, node):
    if node is None:
      return ''
    node = BeautifulSoup(str(node), 'html.parser')
    for removable in node.find_all(['script', 'style', 'sup']):
      removable.decompose()
    return normalize_line(node.get_text(' ', strip=True).replace('\xa0', ' '))

  def clean_title(self, value):
    value = strip_publication_notes(normalize_line(value))
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def clean_author(self, value):
    value = strip_publication_notes(normalize_line(value))
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True) if node is not None else None
    return urljoin(base_url, link['href']) if link is not None else ''

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def dedupe_rows(self, rows):
    deduped = []
    seen = set()
    for row in rows:
      key = (
        row['award_year'],
        _category_key(row['category']),
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      if key in seen:
        continue
      seen.add(key)
      deduped.append(row)
    return deduped

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      year_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in by_year[year]
      ]
      entries.extend(assign_positions(
        year_rows, int(year), tied_winners_share_position=True))
    return entries


class PrimeMinistersLiteraryAwardsWikipediaParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def __init__(self, category, category_aliases=()):
    self.category = category
    self.category_aliases = tuple(category_aliases or (category,))
    self.category_keys = {_category_key(alias) for alias in self.category_aliases}

  def parse(self, html, base_url=WIKIPEDIA_URL, name=AWARD_NAME):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for table in soup.find_all('table'):
      if not self.table_matches_category(table):
        continue
      header_map = self.header_map(table)
      if not {'year', 'author', 'title', 'result'}.issubset(set(header_map)):
        continue
      rows.extend(self.table_rows(table, header_map, base_url))
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def table_matches_category(self, table):
    caption = self.clean_text(table.find('caption'))
    if self.category_matches(caption):
      return True
    for heading in table.find_all_previous(['h2', 'h3', 'h4']):
      text = self.clean_text(heading)
      if self.category_matches(text):
        return True
      if getattr(heading, 'name', None) in {'h3', 'h4'} and text:
        return False
      if normalize_heading(text) in {'winners', 'winners and shortlists'}:
        break
    return False

  def header_map(self, table):
    for tr in table.find_all('tr'):
      cells = tr.find_all(['th', 'td'], recursive=False)
      mapped = {}
      for index, cell in enumerate(cells):
        key = HEADER_ALIASES.get(normalize_heading(self.clean_text(cell)))
        if key is not None and key not in mapped:
          mapped[key] = index
      if {'year', 'author', 'title', 'result'}.issubset(set(mapped)):
        return mapped
    return {}

  def table_rows(self, table, header_map, base_url):
    rows = []
    current_year = None
    current_result = None
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      if not cells or self.row_matches_header(cells, header_map):
        continue
      missing_year_cell = self.row_omits_year(cells, header_map, current_year)
      year = self.year_for_row(cells, header_map, missing_year_cell, current_year)
      if year is None:
        continue
      current_year = year

      result_cell = self.cell_for_key(cells, header_map, 'result', missing_year_cell)
      result = self.result_from_cell(result_cell) or current_result
      if result is not None:
        current_result = result
      if result not in {RESULT_WINNER, RESULT_SHORTLISTED, RESULT_LONGLISTED}:
        continue
      if result == RESULT_LONGLISTED:
        continue

      title_cell = self.cell_for_key(cells, header_map, 'title', missing_year_cell)
      author_cell = self.cell_for_key(cells, header_map, 'author', missing_year_cell)
      title = self.clean_title(self.clean_text(title_cell))
      author = self.clean_author(self.clean_text(author_cell))
      if not title or not author:
        continue
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': self.first_link_url(title_cell, base_url) or base_url,
        'category': self.category,
      })
    return rows

  def row_matches_header(self, cells, header_map):
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

  def year_for_row(self, cells, header_map, missing_year_cell, current_year):
    if missing_year_cell:
      return current_year
    year_cell = self.cell_for_key(cells, header_map, 'year', False)
    return self.year_from_text(self.clean_text(year_cell)) if year_cell is not None else current_year

  def cell_for_key(self, cells, header_map, key, missing_year_cell):
    index = header_map.get(key)
    if index is None:
      return None
    if missing_year_cell and index > header_map['year']:
      index -= 1
    if index < 0 or index >= len(cells):
      return None
    return cells[index]

  def result_from_cell(self, cell):
    text = normalize_heading(self.clean_text(cell))
    if text.startswith('winner'):
      return RESULT_WINNER
    if text.startswith('shortlist') or text.startswith('finalist'):
      return RESULT_SHORTLISTED
    if text.startswith('longlist'):
      return RESULT_LONGLISTED
    return None

  def category_matches(self, value):
    return _category_key(value) in self.category_keys

  def clean_text(self, node):
    if node is None:
      return ''
    node = BeautifulSoup(str(node), 'html.parser')
    for removable in node.find_all(['script', 'style', 'sup']):
      removable.decompose()
    return normalize_line(node.get_text(' ', strip=True).replace('\xa0', ' '))

  def clean_title(self, value):
    value = strip_publication_notes(normalize_line(value))
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def clean_author(self, value):
    value = strip_publication_notes(normalize_line(value))
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def first_link_url(self, cell, base_url):
    link = cell.find('a', href=True) if cell is not None else None
    return urljoin(base_url, link['href']) if link is not None else ''

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def dedupe_rows(self, rows):
    deduped = []
    seen = set()
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      if key in seen:
        continue
      seen.add(key)
      deduped.append(row)
    return deduped

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      year_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in by_year[year]
      ]
      entries.extend(assign_positions(
        year_rows, int(year), tied_winners_share_position=True))
    return entries


def parse_prime_ministers_literary_awards_official(
    html, base_url=OFFICIAL_URL, name=AWARD_NAME, category='Fiction',
    category_aliases=(), fetch_url=None, log=None, progress=None):
  return PrimeMinistersLiteraryAwardsOfficialParser(
    category, category_aliases).parse(
      html, base_url, name, fetch_url=fetch_url, log=log, progress=progress)


def parse_prime_ministers_literary_awards_wikipedia(
    html, base_url=WIKIPEDIA_URL, name=AWARD_NAME, category='Fiction',
    category_aliases=()):
  return PrimeMinistersLiteraryAwardsWikipediaParser(
    category, category_aliases).parse(html, base_url, name)
