#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Shared helpers for general-audience book-club parsers.

Maintenance notes:
- These are list imports, not award imports. Entries use ordinary positions
  plus source-specific selection metadata.
- Book-club pages tend to be commerce/editorial card grids. The helpers accept
  explicit data attributes, tables, and repeated card/list/article blocks before
  falling back to small text-pattern parsing.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.base import (
    CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,
    author_list,
    entry_source_object,
    imported_entry,
    ListParserBase,
    parsed_source,
  )
  from calibre_plugins.list_switchboard.parser.award_base import normalize_line
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .base import (
    CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,
    author_list,
    entry_source_object,
    imported_entry,
    ListParserBase,
    parsed_source,
  )
  from .award_base import normalize_line
  from .generic import position_sort_key


MONTHS = {
  'january': '1',
  'february': '2',
  'march': '3',
  'april': '4',
  'may': '5',
  'june': '6',
  'july': '7',
  'august': '8',
  'september': '9',
  'october': '10',
  'november': '11',
  'december': '12',
}
MONTH_PATTERN = '|'.join(MONTHS)
YEAR_PATTERN = r'(?:19|20)\d{2}|\u2019?\d{2}|\'?\d{2}'
SEASONS = ('spring', 'summer', 'fall', 'autumn', 'winter')


def parse_year(value):
  value = normalize_line(str(value or '')).strip()
  if not value:
    return ''
  match = re.search(r'((?:19|20)\d{2})', value)
  if match:
    return match.group(1)
  match = re.search(r'(?:\u2019|\')(\d{2})\b', value)
  if match:
    year = int(match.group(1))
    return str(2000 + year if year < 70 else 1900 + year)
  return ''


def parse_month(value):
  match = re.search(r'\b(%s)\b' % MONTH_PATTERN, value or '', re.I)
  return MONTHS[match.group(1).casefold()] if match else ''


def parse_season(value):
  match = re.search(r'\b(%s)\b' % '|'.join(SEASONS), value or '', re.I)
  if not match:
    return ''
  season = match.group(1).casefold()
  return 'fall' if season == 'autumn' else season


def parse_iso_date(value):
  match = re.search(r'\b((?:19|20)\d{2}-\d{2}-\d{2})\b', value or '')
  return match.group(1) if match else ''


def strip_pick_label(value):
  value = normalize_line(value)
  value = re.sub(r'\b(?:book\s+club\s+)?(?:pick|selection|read)\b', '', value, flags=re.I)
  value = re.sub(r'\b(?:monthly|main|latest|current)\b', '', value, flags=re.I)
  return normalize_line(value.strip(' :-\u2013\u2014|'))


def split_title_author(text):
  text = normalize_line(text)
  text = re.sub(r'\bA\s+GMA\s+Book\s+Club\s+Pick\b', '', text, flags=re.I)
  text = re.sub(r'\b(?:A\s+)?Novel\b(?=\s+by\b)', '', text, flags=re.I)
  text = re.sub(r'\s+\|\s+', ' by ', text)
  text = re.sub(r'\s+\u2013\s+', ' by ', text)
  text = re.sub(r'\s+-\s+', ' by ', text)
  match = re.search(r'^(.+?),\s*(?:by\s+)?([^,]+(?:\s+(?:and|&)\s+[^,]+)*)$', text, re.I)
  if match:
    return clean_title(match.group(1)), clean_author(match.group(2))
  match = re.search(r'^(.+?)\s+(?:by|from)\s+(.+)$', text, re.I)
  if match:
    return clean_title(match.group(1)), clean_author(match.group(2))
  return '', ''


def clean_title(value):
  value = normalize_line(value)
  value = re.sub(r'^\W*(?:title|book)\W*', '', value, flags=re.I)
  value = re.sub(r'\s*:\s*A\s+GMA\s+Book\s+Club\s+Pick\s*$', '', value, flags=re.I)
  return value.strip(' "\'\u2018\u2019\u201c\u201d,.;:')


def clean_author(value):
  value = normalize_line(value)
  value = re.sub(r'^\W*(?:author|by)\W*', '', value, flags=re.I)
  return value.strip(' "\'\u2018\u2019\u201c\u201d,.;:')


def class_contains(node, words):
  classes = ' '.join(node.get('class', ())).casefold()
  return any(word in classes for word in words)


def text_blocks(soup):
  blocks = []
  for node in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'p', 'li', 'a', 'figcaption']):
    text = normalize_line(node.get_text(' ', strip=True))
    if text:
      blocks.append((node, text))
  if blocks:
    return blocks
  return [(None, normalize_line(text)) for text in soup.stripped_strings]


def image_alt_blocks(soup):
  blocks = []
  for image in soup.find_all('img'):
    text = normalize_line(image.get('alt', ''))
    if text:
      blocks.append((image, text))
  return blocks


class BookClubParserBase(ListParserBase):
  """
  Base class for card/table/list shaped book-club pages.

  Invariants:
  - Subclasses own source scope decisions through `accept_entry()`.
  - Duplicate source cards are collapsed by title/author/year/month/type.
  """

  FILTER_CATEGORIES = (CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,)
  CLUB_NAME = ''
  DEFAULT_SCOPE = 'main'
  DEFAULT_SELECTION_TYPE = 'monthly_pick'
  HOST = ''

  CANDIDATE_CLASSES = (
    'book', 'card', 'pick', 'selection', 'read', 'item', 'entry', 'product',
    'contender')
  TITLE_CLASSES = ('title', 'book-title', 'product-title', 'heading')
  AUTHOR_CLASSES = ('author', 'byline', 'creator')
  LABEL_CLASSES = ('label', 'date', 'month', 'season', 'pick', 'badge')

  def parse(self, html, base_url, name=None, scope=None):
    soup = BeautifulSoup(html or '<html></html>', 'html.parser')
    entries = self.entries_from_soup(soup, base_url, scope or self.DEFAULT_SCOPE)
    return {
      'name': name or self.CLUB_NAME,
      'source': parsed_source(name or self.CLUB_NAME, base_url),
      'entries': sorted(entries, key=self.entry_sort_key),
      'notes': self.notes_for_entries(entries),
      'match_series': False,
    }

  def entry_sort_key(self, entry):
    year = entry.get('selection_year') or '9999'
    try:
      year_key = int(year)
    except Exception:
      year_key = 9999
    try:
      month_key = int(entry.get('selection_month') or 99)
    except Exception:
      month_key = 99
    season_order = {
      'winter': 1,
      'spring': 2,
      'summer': 3,
      'fall': 4,
    }
    season_key = season_order.get(entry.get('season', ''), 99)
    return (
      year_key,
      month_key,
      season_key,
      position_sort_key(entry.get('position', '')),
    )

  def entries_from_soup(self, soup, base_url, scope):
    entries = []
    seen = set()
    for row in self.table_entries(soup, base_url, scope):
      key = self.entry_key(row)
      if key not in seen:
        seen.add(key)
        entries.append(row)
    for node in self.candidate_nodes(soup):
      entry = self.entry_from_node(node, base_url, scope, len(entries) + 1)
      if entry is None:
        continue
      key = self.entry_key(entry)
      if key in seen:
        continue
      seen.add(key)
      entries.append(entry)
    return self.finalize_entries(entries)

  def table_entries(self, soup, base_url, scope):
    entries = []
    for table in soup.find_all('table'):
      headers = [
        normalize_line(cell.get_text(' ', strip=True)).casefold()
        for cell in table.find_all(['th'])
      ]
      if 'title' not in ' '.join(headers) and 'book' not in ' '.join(headers):
        continue
      for row in table.find_all('tr'):
        cells = row.find_all(['td', 'th'])
        if len(cells) < 2:
          continue
        entry = self.entry_from_cells(cells, headers, base_url, scope, len(entries) + 1)
        if entry is not None:
          entries.append(entry)
    return entries

  def entry_from_cells(self, cells, headers, base_url, scope, index):
    values = [normalize_line(cell.get_text(' ', strip=True)) for cell in cells]
    entry_url = ''
    for cell in cells:
      link = cell.find('a', href=True)
      if link is not None:
        entry_url = urljoin(base_url, link['href'])
        break
    data = {}
    if len(headers) >= len(values):
      for header, value in zip(headers, values):
        if 'title' in header or header == 'book':
          data['title'] = value
        elif 'author' in header:
          data['author'] = value
        elif 'year' in header:
          data['selection_year'] = parse_year(value)
        elif 'month' in header:
          data['selection_month'] = parse_month(value)
          data['selection_label'] = value
        elif 'label' in header or 'pick' in header:
          data['selection_label'] = value
        elif 'defender' in header or 'advocate' in header:
          data['advocate_defender_host_selector'] = value
        elif 'type' in header or 'result' in header:
          data['selection_type'] = self.selection_type_from_text(value)
    if not data.get('title') or not data.get('author'):
      title, author = split_title_author(' '.join(values[:2]))
      data.setdefault('title', title)
      data.setdefault('author', author)
    return self.build_entry(data, ' '.join(values), entry_url, scope, index, base_url=base_url)

  def candidate_nodes(self, soup):
    nodes = []
    for node in soup.find_all(['article', 'li', 'section', 'div']):
      if node.find_parent(['article', 'li']) is not None and not self.explicit_node(node):
        continue
      if self.explicit_node(node) or class_contains(node, self.CANDIDATE_CLASSES):
        nodes.append(node)
    return nodes

  def explicit_node(self, node):
    return bool(node.get('data-title') or node.get('data-author') or node.get('data-book-title'))

  def entry_from_node(self, node, base_url, scope, index):
    text = normalize_line(node.get_text(' ', strip=True))
    data = self.data_from_node(node, text)
    link = node.find('a', href=True)
    entry_url = urljoin(base_url, link['href']) if link is not None else base_url
    return self.build_entry(data, text, entry_url, scope, index, base_url=base_url)

  def data_from_node(self, node, text):
    data = {}
    data['title'] = clean_title(
      node.get('data-title') or node.get('data-book-title') or
      self.descendant_text(node, self.TITLE_CLASSES))
    data['author'] = clean_author(
      node.get('data-author') or self.descendant_text(node, self.AUTHOR_CLASSES))
    data['selection_label'] = normalize_line(
      node.get('data-label') or node.get('data-selection-label') or
      self.descendant_text(node, self.LABEL_CLASSES))
    data['selection_year'] = (
      node.get('data-year') or parse_year(data.get('selection_label')) or parse_year(text))
    data['selection_month'] = (
      node.get('data-month') or parse_month(data.get('selection_label')) or parse_month(text))
    data['season'] = node.get('data-season') or parse_season(data.get('selection_label')) or parse_season(text)
    data['event_date'] = node.get('data-date') or parse_iso_date(text)
    data['rank_or_position'] = node.get('data-rank') or node.get('data-position') or ''
    data['selection_type'] = node.get('data-selection-type') or self.selection_type_from_text(text)
    data['advocate_defender_host_selector'] = (
      node.get('data-selector') or node.get('data-defender') or
      self.descendant_text(node, ('selector', 'defender', 'advocate', 'host')))
    if not data['title'] or not data['author']:
      title, author = split_title_author(self.text_without_label(text, data.get('selection_label', '')))
      data['title'] = data['title'] or title
      data['author'] = data['author'] or author
    return data

  def descendant_text(self, node, class_words):
    for child in node.find_all(True):
      if class_contains(child, class_words):
        return normalize_line(child.get_text(' ', strip=True))
    if 'title' in class_words:
      heading = node.find(['h1', 'h2', 'h3', 'h4'])
      if heading is not None:
        return normalize_line(heading.get_text(' ', strip=True))
    return ''

  def text_without_label(self, text, label):
    if label:
      text = text.replace(label, ' ', 1)
    return normalize_line(text)

  def build_entry(self, data, text, entry_url, scope, index, base_url=''):
    title = clean_title(data.get('title', ''))
    authors = data.get('authors') or clean_author(data.get('author', ''))
    if not title or not authors:
      return None
    if not data.get('selection_year'):
      data['selection_year'] = parse_year(data.get('selection_label', '')) or parse_year(text)
    if not data.get('selection_month'):
      data['selection_month'] = parse_month(data.get('selection_label', '')) or parse_month(text)
    if not data.get('season'):
      data['season'] = parse_season(data.get('selection_label', '')) or parse_season(text)
    selection_type = data.get('selection_type') or self.DEFAULT_SELECTION_TYPE
    list_source = parsed_source(self.CLUB_NAME, base_url)
    entry = imported_entry(
      data.get('rank_or_position') or str(index),
      title,
      authors,
      source=entry_source_object(entry_url, list_source=list_source),
      club=self.CLUB_NAME,
      club_scope=scope,
      selection_type=selection_type)
    for key in (
        'selection_year', 'selection_month', 'season', 'event_date',
        'selection_label', 'advocate_defender_host_selector', 'scope_flags'):
      if data.get(key):
        entry[key] = normalize_line(str(data[key]))
    entry = self.complete_entry(entry, text)
    return entry if self.accept_entry(entry, text) else None

  def selection_type_from_text(self, text):
    normalized = normalize_line(text).casefold()
    if 'winner' in normalized:
      return 'winner'
    if 'contender' in normalized:
      return 'contender'
    if 'finalist' in normalized:
      return 'finalist'
    if 'classic' in normalized:
      return 'classic_pick'
    if 'reread' in normalized or 'picked the same book twice' in normalized:
      return 'reread_pick'
    if 'ya pick' in normalized or 'young adult' in normalized:
      return 'YA_pick'
    if 'season' in normalized or parse_season(normalized):
      return 'seasonal_pick'
    if 'staff' in normalized or self.CLUB_NAME == 'LibraryReads':
      return 'staff_pick'
    if 'special' in normalized or 'bonus' in normalized:
      return 'special_pick'
    return self.DEFAULT_SELECTION_TYPE

  def complete_entry(self, entry, _text):
    return entry

  def accept_entry(self, _entry, _text):
    return True

  def finalize_entries(self, entries):
    return entries

  def notes_for_entries(self, _entries):
    return []

  def entry_key(self, entry):
    return (
      entry.get('title', '').casefold(),
      ' '.join(author.casefold() for author in author_list(entry.get('authors'))),
      entry.get('selection_year', ''),
      entry.get('selection_month', ''),
      entry.get('selection_type', ''),
      entry.get('club_scope', ''),
    )
