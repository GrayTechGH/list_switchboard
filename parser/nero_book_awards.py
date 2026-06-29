#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Nero Book Awards parsers.

Maintenance notes:
- The official Nero site is a WordPress archive. The reliable entry point is
  the archive navigation, whose link text identifies shortlist, category-winner,
  and Gold Prize pages even when annual slugs vary.
- Category winner pages list only the winning books, without stable category
  headings, so category recipes use them to promote matching shortlist rows.
- Wikipedia is a replacement fallback only; it is useful for a consolidated
  winner/shortlist table but is not the authoritative source.
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


AWARD_NAME = 'Nero Book Awards'
OFFICIAL_URL = 'https://nerobookawards.com/key-dates/'
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Nero_Book_Awards'

CATEGORY_FICTION = 'Fiction'
CATEGORY_DEBUT_FICTION = 'Debut Fiction'
CATEGORY_NONFICTION = 'Non-Fiction'
CATEGORY_CHILDRENS_FICTION = "Children's Fiction"
CATEGORY_GOLD_PRIZE = 'Nero Gold Prize'

OFFICIAL_CATEGORIES = (
  CATEGORY_CHILDRENS_FICTION,
  CATEGORY_DEBUT_FICTION,
  CATEGORY_FICTION,
  CATEGORY_NONFICTION,
)

CATEGORY_ALIASES = {
  CATEGORY_FICTION: (CATEGORY_FICTION,),
  CATEGORY_DEBUT_FICTION: (CATEGORY_DEBUT_FICTION, 'Debut'),
  CATEGORY_NONFICTION: (CATEGORY_NONFICTION, 'Nonfiction', 'Non Fiction'),
  CATEGORY_CHILDRENS_FICTION: (
    CATEGORY_CHILDRENS_FICTION,
    "Children's Fiction",
    'Children’s Fiction',
    'Childrens Fiction',
  ),
  CATEGORY_GOLD_PRIZE: (
    CATEGORY_GOLD_PRIZE,
    'Nero Gold Prize',
    'Overall winner',
    'Book of the Year',
  ),
}

HEADER_ALIASES = {
  'year': 'year',
  'award year': 'year',
  'author': 'author',
  'authors': 'author',
  'writer': 'author',
  'title': 'title',
  'book': 'title',
  'work': 'title',
  'publisher': 'publisher',
  'result': 'result',
  'status': 'result',
  'category': 'result',
  'award': 'result',
  'prize': 'result',
}


def _category_key(value):
  return normalize_heading(value).replace('non fiction', 'nonfiction')


class NeroBookAwardsBaseParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def __init__(self, category, category_aliases=()):
    self.category = category
    aliases = category_aliases or CATEGORY_ALIASES.get(category, (category,))
    self.category_aliases = tuple(aliases)
    self.category_keys = {_category_key(alias) for alias in self.category_aliases}

  def clean_text(self, node):
    if node is None:
      return ''
    node = BeautifulSoup(str(node), 'html.parser')
    for removable in node.find_all(['script', 'style', 'sup']):
      removable.decompose()
    return normalize_line(node.get_text(' ', strip=True).replace('\xa0', ' '))

  def clean_title(self, value):
    value = normalize_line(value)
    value = re.sub(r'\s*\bREAD MORE\b.*$', '', value, flags=re.I).strip()
    value = re.sub(r'\s+illustrated\s+by\s+.+$', '', value, flags=re.I).strip()
    value = strip_publication_notes(value)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def clean_author(self, value):
    value = normalize_line(value)
    value = re.sub(r'^\s*by\s+', '', value, flags=re.I)
    value = re.sub(r'\s+illustrated\s+by\s+.+$', '', value, flags=re.I).strip()
    value = strip_publication_notes(value)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def category_matches(self, value):
    key = _category_key(value)
    return key in self.category_keys

  def known_category(self, value):
    key = _category_key(value)
    return any(
      key == _category_key(alias)
      for category in OFFICIAL_CATEGORIES
      for alias in CATEGORY_ALIASES.get(category, (category,)))

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True) if node is not None else None
    if link is None and getattr(node, 'name', None) == 'a' and node.get('href'):
      link = node
    return urljoin(base_url, link['href']) if link is not None else ''

  def parse_title_author_line(self, text):
    text = normalize_line(text)
    if not text or normalize_heading(text).startswith('read more'):
      return '', ''
    # Use the last BY marker; titles such as "We Came by Sea" contain "by".
    match = re.match(r'^(.+)\s+by\s+(.+)$', text, re.I)
    if match is None:
      return '', ''
    return (
      self.clean_title(match.group(1)),
      self.clean_author(match.group(2)))

  def title_author_rows_from_nodes(self, nodes, year, result, page_url, category):
    rows = []
    pending_title = None
    pending_url = page_url
    for node in nodes:
      text = self.clean_text(node)
      if not text or normalize_heading(text).startswith('read more'):
        continue
      title, author = self.parse_title_author_line(text)
      if title and author:
        rows.append({
          'award_year': str(year),
          'title': title,
          'author': author,
          'result': result,
          'source_url': self.first_link_url(node, page_url) or page_url,
          'category': category,
        })
        pending_title = None
        pending_url = page_url
        continue
      by_match = re.match(r'^\s*by\s+(.+)$', text, re.I)
      if by_match is not None and pending_title:
        rows.append({
          'award_year': str(year),
          'title': pending_title,
          'author': self.clean_author(by_match.group(1)),
          'result': result,
          'source_url': pending_url,
          'category': category,
        })
        pending_title = None
        pending_url = page_url
      elif node.name in {'h5', 'p', 'li'} and len(text) <= 180:
        pending_title = self.clean_title(text)
        pending_url = self.first_link_url(node, page_url) or page_url
    return rows

  def dedupe_rows(self, rows):
    deduped = []
    index_by_key = {}
    for row in rows:
      title_key = normalize_heading(row.get('title', ''))
      author_key = normalize_heading(row.get('author', ''))
      if not title_key or not author_key:
        continue
      key = (
        row.get('award_year'),
        _category_key(row.get('category', '')),
        title_key,
        author_key,
      )
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


class NeroBookAwardsOfficialParser(NeroBookAwardsBaseParser):

  def parse(
      self, html, base_url=OFFICIAL_URL, name=AWARD_NAME, fetch_url=None,
      log=None, progress=None):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    notes = []
    archive_links = self.archive_links(soup, base_url)

    if fetch_url is not None and archive_links:
      links = self.links_for_category(archive_links)
      total = len(links)
      for index, (kind, year, url) in enumerate(links, 1):
        try:
          if progress is not None:
            progress(index, total, f'Fetching {name} archive page {index} of {total}')
          page_html = fetch_url(url)
          rows.extend(self.rows_for_archive_page(kind, page_html, url, year))
        except Exception as err:
          notes.append(f'{name} archive page could not be fetched: {url}: {err}')
          if log is not None:
            log(f'{name} archive page failed: {url}: {err}')
    else:
      rows.extend(self.rows_for_direct_page(soup, base_url))

    if self.category != CATEGORY_GOLD_PRIZE:
      rows = self.promote_shortlist_winners(rows)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def archive_links(self, soup, base_url):
    links = []
    seen = set()
    for link in soup.find_all('a', href=True):
      text = self.clean_text(link)
      key = normalize_heading(text)
      if not text or self.navigation_noise(key):
        continue
      year = self.year_from_text(text)
      if year is None:
        continue
      kind = None
      if 'shortlist' in key:
        kind = 'shortlist'
      elif 'category winners' in key:
        kind = 'category_winners'
      elif 'nero gold prize' in key:
        kind = 'gold'
      if kind is None:
        continue
      url = urljoin(base_url, link['href'])
      dedupe_key = (kind, year, url)
      if dedupe_key in seen:
        continue
      seen.add(dedupe_key)
      links.append((kind, year, url))
    return tuple(links)

  def navigation_noise(self, key):
    return any(value in key for value in (
      'judge',
      'reading guide',
      'new writers prize',
      'news',
      'contact',
      'faq',
    ))

  def links_for_category(self, archive_links):
    if self.category == CATEGORY_GOLD_PRIZE:
      accepted = {'gold'}
    else:
      accepted = {'shortlist', 'category_winners'}
    return tuple(
      link for link in archive_links
      if link[0] in accepted)

  def rows_for_archive_page(self, kind, html, page_url, year):
    soup = BeautifulSoup(html, 'html.parser')
    if kind == 'shortlist':
      return self.shortlist_rows(soup, page_url, year)
    if kind == 'category_winners':
      return self.category_winner_rows(soup, page_url, year)
    if kind == 'gold':
      return self.gold_prize_rows(soup, page_url, year)
    return []

  def rows_for_direct_page(self, soup, page_url):
    year = self.year_from_text(self.clean_text(soup.find('title'))) or self.year_from_text(page_url)
    if year is None:
      return []
    rows = self.shortlist_rows(soup, page_url, year)
    if rows:
      return rows
    if self.category == CATEGORY_GOLD_PRIZE:
      return self.gold_prize_rows(soup, page_url, year)
    return self.category_winner_rows(soup, page_url, year)

  def content_root(self, soup):
    return (
      soup.select_one('.entry-content')
      or soup.select_one('.wp-block-post-content')
      or soup.find('main')
      or soup.find('body')
      or soup)

  def content_nodes(self, soup):
    root = self.content_root(soup)
    nodes = []
    for node in root.find_all(['h2', 'h3', 'h4', 'h5', 'p', 'li']):
      if node.find_parent(['nav', 'header', 'footer', 'script', 'style']):
        continue
      nodes.append(node)
    return nodes

  def shortlist_rows(self, soup, page_url, year):
    rows = []
    current_target = False
    for node in self.content_nodes(soup):
      text = self.clean_text(node)
      if not text:
        continue
      if node.name in {'h2', 'h3', 'h4'}:
        if self.known_category(text):
          current_target = self.category_matches(text)
        continue
      if not current_target:
        continue
      title, author = self.parse_title_author_line(text)
      if not title or not author:
        continue
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': RESULT_SHORTLISTED,
        'source_url': self.first_link_url(node, page_url) or page_url,
        'category': self.category,
      })
    return rows

  def category_winner_rows(self, soup, page_url, year):
    nodes = [
      node for node in self.content_nodes(soup)
      if node.name in {'h5', 'p', 'li'}
    ]
    return self.title_author_rows_from_nodes(
      nodes, year, RESULT_WINNER, page_url, '__winner_set__')

  def gold_prize_rows(self, soup, page_url, year):
    nodes = []
    for node in self.content_nodes(soup):
      text = self.clean_text(node)
      if normalize_heading(text).startswith('other books shortlisted'):
        break
      if node.name in {'h5', 'p', 'li'}:
        nodes.append(node)
    rows = self.title_author_rows_from_nodes(
      nodes, year, RESULT_WINNER, page_url, self.category)
    return rows[:1]

  def promote_shortlist_winners(self, rows):
    winner_keys = {
      (row['award_year'], normalize_heading(row['title']), normalize_heading(row['author']))
      for row in rows
      if row.get('category') == '__winner_set__'
    }
    promoted = []
    for row in rows:
      if row.get('category') == '__winner_set__':
        continue
      key = (
        row['award_year'],
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      if key in winner_keys:
        row = dict(row)
        row['result'] = RESULT_WINNER
      promoted.append(row)
    return promoted


class NeroBookAwardsWikipediaParser(NeroBookAwardsBaseParser):

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
      header_map = self.header_map(table)
      if not {'year', 'title', 'author'}.issubset(set(header_map)):
        continue
      rows.extend(self.table_rows(table, header_map, base_url))
    return rows

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
      result_text = self.result_text_for_row(cells, header_map, missing_year_cell)
      result = self.result_from_text(result_text)
      if result is None:
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

  def result_text_for_row(self, cells, header_map, missing_year_cell):
    values = []
    for key in ('result',):
      cell = self.cell_for_key(cells, header_map, key, missing_year_cell)
      if cell is not None:
        values.append(self.clean_text(cell))
    if not values:
      values.extend(self.clean_text(cell) for cell in cells)
    return ' '.join(values)

  def result_from_text(self, text):
    key = normalize_heading(text)
    if self.category == CATEGORY_GOLD_PRIZE:
      if 'overall winner' in key or 'book of the year' in key or 'gold prize' in key:
        return RESULT_WINNER
      return None
    if not self.result_matches_category(key):
      return None
    if 'winner' in key or 'won' in key:
      return RESULT_WINNER
    if 'shortlist' in key or 'shortlisted' in key or 'finalist' in key:
      return RESULT_SHORTLISTED
    return RESULT_SHORTLISTED

  def result_matches_category(self, key):
    if self.category == CATEGORY_FICTION and any(value in key for value in (
        _category_key(CATEGORY_DEBUT_FICTION),
        _category_key(CATEGORY_CHILDRENS_FICTION),
        'children s fiction',
        'childrens fiction',
      )):
      return False
    return any(alias in key for alias in self.category_keys)


def parse_nero_book_awards_official(
    html, category, category_aliases=(), url=OFFICIAL_URL, name=AWARD_NAME):
  return NeroBookAwardsOfficialParser(
    category, category_aliases).parse(html, url, name)


def parse_nero_book_awards_wikipedia(
    html, category, category_aliases=(), url=WIKIPEDIA_URL, name=AWARD_NAME):
  return NeroBookAwardsWikipediaParser(
    category, category_aliases).parse(html, url, name)
