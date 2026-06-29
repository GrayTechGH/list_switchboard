#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
NSW Premier's Literary Awards parsers.

Maintenance notes:
- The State Library of NSW is the primary source. Category pages expose current
  winner/shortlist cards plus recent past-winner cards.
- V1 keeps book-like categories and rollups only. Poetry, playwriting,
  scriptwriting, scholarship, special, and person-only prize pages stay out of
  scope even when they share the same site shell.
- Wikipedia is used only as a winner-table replacement for rollup recipes whose
  official pages can be winner-only or recent-history oriented.
"""

import re
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


AWARD_NAME = "NSW Premier's Literary Awards"
OFFICIAL_URL = 'https://www.sl.nsw.gov.au/awards/nsw-literary-awards'
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/New_South_Wales_Premier%27s_Literary_Awards'

HEADER_ALIASES = {
  'year': 'year',
  'author': 'author',
  'authors': 'author',
  'writer': 'author',
  'writers': 'author',
  'title': 'title',
  'book': 'title',
  'work': 'title',
  'result': 'result',
  'status': 'result',
  'ref': 'ref',
}


def _category_key(value):
  value = normalize_heading(value)
  return value.replace('non fiction', 'nonfiction')


class NSWPremiersLiteraryAwardsMixin(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def __init__(self, category, category_aliases=()):
    self.category = category
    self.category_aliases = tuple(category_aliases or (category,))
    self.category_keys = {_category_key(alias) for alias in self.category_aliases}

  def clean_text(self, node):
    if node is None:
      return ''
    node = BeautifulSoup(str(node), 'html.parser')
    for removable in node.find_all(['script', 'style', 'sup']):
      removable.decompose()
    return normalize_line(node.get_text(' ', strip=True).replace('\xa0', ' '))

  def clean_title(self, value):
    value = strip_publication_notes(normalize_line(value))
    value = re.sub(r'^\s*winner\s*:\s*', '', value, flags=re.I)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def clean_author(self, value):
    value = strip_publication_notes(normalize_line(value))
    value = re.sub(r'^\s*(?:by|author|authors|writer)\s*:?\s*', '', value, flags=re.I)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True) if node is not None else None
    if link is None and getattr(node, 'name', None) == 'a' and node.get('href'):
      link = node
    return urljoin(base_url, link['href']) if link is not None else ''

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def category_matches(self, value):
    return _category_key(value) in self.category_keys

  def parse_title_author_line(self, text):
    text = normalize_line(text)
    text = re.sub(r'^\s*winner\s*:\s*', '', text, flags=re.I)
    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', text, re.I)
    if by_match is not None:
      return self.clean_title(by_match.group(1)), self.clean_author(by_match.group(2))
    dash_match = re.match(r'^(.+?)\s+[\u2013\u2014-]\s+(.+)$', text)
    if dash_match is not None:
      return self.clean_title(dash_match.group(1)), self.clean_author(dash_match.group(2))
    return '', ''

  def dedupe_rows(self, rows):
    deduped = []
    index_by_key = {}
    for row in rows:
      title_key = normalize_heading(row.get('title', ''))
      author_key = normalize_heading(row.get('author', ''))
      if not title_key or not author_key:
        continue
      key = (row.get('award_year'), _category_key(row.get('category', '')), title_key, author_key)
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


class NSWPremiersLiteraryAwardsOfficialParser(NSWPremiersLiteraryAwardsMixin):

  def parse(self, html, base_url=OFFICIAL_URL, name=AWARD_NAME, **_kwargs):
    rows = self.parse_rows(html, base_url)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    rows = self.card_rows(soup, base_url)
    rows.extend(self.announcement_rows(soup, base_url))
    return rows

  def card_rows(self, soup, base_url):
    rows = []
    seen_nodes = set()
    for card in soup.find_all(class_=lambda value: value and 'slnsw-card' in value):
      node_id = id(card)
      if node_id in seen_nodes:
        continue
      seen_nodes.add(node_id)
      row = self.card_row(card, base_url)
      if row is not None:
        rows.append(row)
    return rows

  def card_row(self, card, base_url):
    result = self.result_from_card(card)
    if result not in {RESULT_WINNER, RESULT_SHORTLISTED}:
      return None
    title_node = self.title_node(card)
    author_node = card.find(class_=lambda value: value and 'award-entry-author' in value)
    title = self.clean_title(self.clean_text(title_node))
    author = self.clean_author(self.clean_text(author_node))
    if not title or not author:
      return None
    year = self.year_from_card(card, title_node)
    if year is None:
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': self.first_link_url(title_node, base_url) or base_url,
      'category': self.category,
    }

  def result_from_card(self, card):
    for badge in card.find_all(class_=lambda value: value and 'badge__text' in value):
      key = normalize_heading(self.clean_text(badge))
      if key.startswith('winner'):
        return RESULT_WINNER
      if key.startswith('shortlisted') or key.startswith('shortlist'):
        return RESULT_SHORTLISTED
    href = ' '.join(link.get('href', '') for link in card.find_all('a', href=True))
    key = normalize_heading(href)
    if ' winner ' in f' {key} ':
      return RESULT_WINNER
    if ' shortlisted ' in f' {key} ':
      return RESULT_SHORTLISTED
    return None

  def title_node(self, card):
    title = card.find(['h5', 'h4', 'h3'])
    if title is not None:
      return title
    return card.find('a', href=True)

  def year_from_card(self, card, title_node):
    for value in (
        self.clean_text(card.find(class_=lambda item: item and 'current-year-label' in item)),
        ' '.join(link.get('href', '') for link in card.find_all('a', href=True)),
        self.clean_text(title_node),
        self.clean_text(card)):
      year = self.year_from_text(value)
      if year is not None:
        return year
    return None

  def announcement_rows(self, soup, base_url):
    page_year = self.year_from_text(self.clean_text(soup.find('title'))) or self.year_from_text(base_url)
    rows = []
    current_category = None
    for node in soup.find_all(['h2', 'h3', 'h4', 'p', 'li']):
      if node.find_parent(['nav', 'header', 'footer', 'script', 'style']):
        continue
      text = self.clean_text(node)
      if not text:
        continue
      if node.name in {'h2', 'h3', 'h4'}:
        current_category = self.category if self.category_matches(text) else None
        continue
      if current_category is None or page_year is None:
        continue
      result = RESULT_WINNER if re.match(r'^\s*winner\s*:', text, re.I) else RESULT_SHORTLISTED
      title, author = self.parse_title_author_line(text)
      if not title or not author:
        continue
      rows.append({
        'award_year': str(page_year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': self.first_link_url(node, base_url) or base_url,
        'category': self.category,
      })
    return rows


class NSWPremiersLiteraryAwardsWikipediaParser(NSWPremiersLiteraryAwardsMixin):

  def parse(self, html, base_url=WIKIPEDIA_URL, name=AWARD_NAME, **_kwargs):
    rows = self.parse_rows(html, base_url)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for table in soup.find_all('table'):
      if not self.table_matches_category(table):
        continue
      header_map = self.header_map(table)
      if not {'year', 'title', 'author'}.issubset(set(header_map)):
        continue
      rows.extend(self.table_rows(table, header_map, base_url))
    return rows

  def table_matches_category(self, table):
    caption = self.clean_text(table.find('caption'))
    if self.category_matches(caption):
      return True
    for heading in table.find_all_previous(['h2', 'h3', 'h4']):
      text = self.clean_text(heading)
      if self.category_matches(text):
        return True
      if text:
        return False
    return False

  def header_map(self, table):
    for tr in table.find_all('tr'):
      cells = tr.find_all(['th', 'td'], recursive=False)
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
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      if not cells or self.row_matches_header(cells, header_map):
        continue
      missing_year_cell = self.row_omits_year(cells, header_map, current_year)
      year = self.year_for_row(cells, header_map, missing_year_cell, current_year)
      if year is None:
        continue
      current_year = year
      result = self.result_for_row(cells, header_map, missing_year_cell)
      if result != RESULT_WINNER:
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
        'result': RESULT_WINNER,
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
    return len(cells) <= max(header_map.values())

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

  def result_for_row(self, cells, header_map, missing_year_cell):
    result_cell = self.cell_for_key(cells, header_map, 'result', missing_year_cell)
    if result_cell is None:
      return RESULT_WINNER
    result_key = normalize_heading(self.clean_text(result_cell))
    return RESULT_WINNER if result_key.startswith('winner') else None


def parse_nsw_premiers_literary_awards_official(
    html, category, category_aliases=(), url=OFFICIAL_URL, name=AWARD_NAME):
  return NSWPremiersLiteraryAwardsOfficialParser(
    category, category_aliases).parse(html, url, name)


def parse_nsw_premiers_literary_awards_wikipedia(
    html, category, category_aliases=(), url=WIKIPEDIA_URL, name=AWARD_NAME):
  return NSWPremiersLiteraryAwardsWikipediaParser(
    category, category_aliases).parse(html, url, name)
