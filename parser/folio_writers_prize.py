#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Folio/Writers' Prize parsers.

Maintenance notes:
- The official Writers' Prize archive spans several branding and page-shape
  eras: older single-prize shortlists, a 2022 longlist page with explicit
  shortlist markers, and 2023+ category-era pages.
- Wikipedia is a replacement fallback only. Bookshop.org list pages are
  intentionally ignored because direct fetches return Cloudflare challenge
  pages instead of parseable award data.
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


AWARD_NAME = "Folio/Writers' Prize"
OFFICIAL_URL = 'https://thewritersprize.com/'
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/The_Writers%27_Prize'

CATEGORY_BOOK_OF_THE_YEAR = 'Book of the Year'
CATEGORY_FICTION = 'Fiction'
CATEGORY_NONFICTION = 'Non-Fiction'
CATEGORY_POETRY = 'Poetry'

CATEGORY_ALIASES = {
  CATEGORY_BOOK_OF_THE_YEAR: (
    CATEGORY_BOOK_OF_THE_YEAR,
    'The Writers Prize Book of the Year',
    'Rathbones Folio Prize Book of the Year',
    'Overall',
    'Winner',
  ),
  CATEGORY_FICTION: (CATEGORY_FICTION,),
  CATEGORY_NONFICTION: (CATEGORY_NONFICTION, 'Nonfiction', 'Non Fiction'),
}

OFFICIAL_CATEGORY_LINKS = {
  CATEGORY_FICTION: ('fiction shortlist',),
  CATEGORY_NONFICTION: ('non fiction shortlist', 'nonfiction shortlist'),
}

KNOWN_CATEGORIES = (
  CATEGORY_FICTION,
  CATEGORY_NONFICTION,
  CATEGORY_POETRY,
)

HEADER_ALIASES = {
  'year': 'year',
  'award year': 'year',
  'author': 'author',
  'authors': 'author',
  'writer': 'author',
  'title': 'title',
  'book': 'title',
  'work': 'title',
  'result': 'result',
  'status': 'result',
  'category': 'result',
  'award': 'result',
  'prize': 'result',
}


def _category_key(value):
  return normalize_heading(value).replace('non fiction', 'nonfiction')


class FolioWritersPrizeBaseParser(AwardParserBase):

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
    value = re.sub(r'\s+\|\s+.*$', '', value).strip()
    value = re.sub(r'\s*\b(?:winner|shortlisted|longlisted)\b\s*$', '', value, flags=re.I).strip()
    value = strip_publication_notes(value)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def clean_author(self, value):
    value = normalize_line(value)
    value = re.sub(r'^\s*by\s+', '', value, flags=re.I)
    value = re.sub(r'\s+illustrated\s+by\s+.+$', '', value, flags=re.I).strip()
    value = strip_publication_notes(value)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True) if node is not None else None
    if link is None and getattr(node, 'name', None) == 'a' and node.get('href'):
      link = node
    return urljoin(base_url, link['href']) if link is not None else ''

  def category_matches(self, value):
    return _category_key(value) in self.category_keys

  def known_category(self, value):
    key = _category_key(value)
    return any(key == _category_key(category) for category in KNOWN_CATEGORIES)

  def parse_title_author_line(self, text):
    text = normalize_line(text)
    text = self.strip_result_suffix(text)[0]
    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', text, re.I)
    if by_match is not None:
      return self.clean_title(by_match.group(1)), self.clean_author(by_match.group(2))
    dash_match = re.match(r'^(.+?)\s+[-\u2013\u2014]\s+(.+)$', text)
    if dash_match is not None:
      return self.clean_title(dash_match.group(1)), self.clean_author(dash_match.group(2))
    return '', ''

  def strip_result_suffix(self, text):
    text = normalize_line(text)
    winner = bool(re.search(r'\bwinner\b|\bbook of the year\b', text, re.I))
    text = re.sub(
      r'\s+[-\u2013\u2014]\s*(?:winner|shortlisted|longlisted|[^-]*category[^-]*)\b.*$',
      '',
      text,
      flags=re.I).strip()
    text = re.sub(
      r'\s*\b(?:category\s+winner|book\s+of\s+the\s+year)\b.*$',
      '',
      text,
      flags=re.I).strip()
    return text, winner

  def row(self, year, title, author, result, source_url, category=None):
    title = self.clean_title(title)
    author = self.clean_author(author)
    if not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': source_url,
      'category': category or self.category,
    }

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


class FolioWritersPrizeOfficialParser(FolioWritersPrizeBaseParser):

  def parse(
      self, html, base_url=OFFICIAL_URL, name=AWARD_NAME, fetch_url=None,
      log=None, progress=None):
    if self.is_cloudflare_challenge(html):
      return self.parsed_result(name, base_url, [])
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
          if self.is_cloudflare_challenge(page_html):
            notes.append(f'{name} archive page was not parseable: {url}')
            continue
          rows.extend(self.rows_for_page(page_html, url, year, kind))
        except Exception as err:
          notes.append(f'{name} archive page could not be fetched: {url}: {err}')
          if log is not None:
            log(f'{name} archive page failed: {url}: {err}')
    else:
      year = self.year_from_text(self.clean_text(soup.find('title'))) or self.year_from_text(base_url)
      if year is not None:
        rows.extend(self.rows_for_soup(soup, base_url, year, 'year'))

    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def is_cloudflare_challenge(self, html):
    key = normalize_heading(html[:2000] if html else '')
    return 'cloudflare' in key and (
      'checking your browser' in key
      or 'just a moment' in key
      or 'cf challenge' in key)

  def archive_links(self, soup, base_url):
    links = []
    seen = set()
    for link in soup.find_all('a', href=True):
      text = self.clean_text(link)
      key = normalize_heading(text)
      href_key = normalize_heading(link.get('href', ''))
      if not text or self.navigation_noise(key, href_key):
        continue
      year = self.year_from_text(text) or self.year_from_text(link.get('href', ''))
      if year is None or year == 2016:
        continue
      kind = None
      if 'fiction shortlist' in key and 'non fiction' not in key and 'nonfiction' not in key:
        kind = CATEGORY_FICTION
      elif 'non fiction shortlist' in key or 'nonfiction shortlist' in key:
        kind = CATEGORY_NONFICTION
      elif re.fullmatch(r'(?:19|20)\d{2}', text.strip()) or ' prize' in key:
        kind = 'year'
      if kind is None:
        continue
      url = urljoin(base_url, link['href'])
      dedupe_key = (kind, year, url)
      if dedupe_key in seen:
        continue
      seen.add(dedupe_key)
      links.append((kind, year, url))
    return tuple(sorted(links, key=lambda item: (item[1], item[0], item[2])))

  def navigation_noise(self, key, href_key):
    noise = (
      'judge',
      'judging',
      'news',
      'press',
      'reading guide',
      'bookshop',
      'new writers prize',
      'contact',
      'about',
      'terms',
    )
    return any(value in key or value in href_key for value in noise)

  def links_for_category(self, archive_links):
    if self.category == CATEGORY_BOOK_OF_THE_YEAR:
      return tuple(link for link in archive_links if link[0] == 'year')
    accepted = {'year', self.category}
    return tuple(link for link in archive_links if link[0] in accepted)

  def rows_for_page(self, html, page_url, year, kind):
    soup = BeautifulSoup(html, 'html.parser')
    return self.rows_for_soup(soup, page_url, year, kind)

  def rows_for_soup(self, soup, page_url, year, kind):
    if self.category != CATEGORY_BOOK_OF_THE_YEAR and kind == self.category:
      return self.rows_for_2024_category_page(soup, page_url, year)
    if year == 2024:
      return self.rows_for_2024_main_page(soup, page_url, year)
    if year == 2023:
      return self.rows_for_2023_page(soup, page_url, year)
    if self.category != CATEGORY_BOOK_OF_THE_YEAR:
      return []
    if year == 2022:
      return self.rows_for_2022_page(soup, page_url, year)
    return self.rows_for_single_prize_page(soup, page_url, year)

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
    for node in root.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'li']):
      if node.find_parent(['nav', 'header', 'footer', 'script', 'style']):
        continue
      nodes.append(node)
    return nodes

  def rows_for_2024_category_page(self, soup, page_url, year):
    rows = []
    winner_next = False
    pending_title = None
    pending_url = page_url
    for node in self.content_nodes(soup):
      text = self.clean_text(node)
      key = normalize_heading(text)
      if not text:
        continue
      if 'category winner' in key:
        winner_next = True
        continue
      if node.name == 'h2':
        if key in {'read more', 'fiction', 'non fiction', 'nonfiction'}:
          continue
        pending_title = self.clean_title(text)
        pending_url = self.first_link_url(node, page_url) or page_url
        continue
      if node.name == 'h3' and pending_title:
        result = RESULT_WINNER if winner_next else RESULT_SHORTLISTED
        row = self.row(year, pending_title, text, result, pending_url, self.category)
        if row is not None:
          rows.append(row)
        winner_next = False
        pending_title = None
    return rows

  def rows_for_2024_main_page(self, soup, page_url, year):
    rows = []
    current_category = None
    for node in self.content_nodes(soup):
      text = self.clean_text(node)
      key = normalize_heading(text)
      if node.name in {'h1', 'h2', 'h3'} and self.known_category(text):
        current_category = self.category_for_heading(text)
        continue
      if not text:
        continue
      if 'category winner' not in key and 'book of the year' not in key:
        continue
      title_text = re.sub(
        r'^\s*category\s+winner(?:\s*/\s*book\s+of\s+the\s+year)?\s*:\s*',
        '',
        text,
        flags=re.I)
      title, author = self.parse_title_author_line(title_text)
      if not title or not author:
        continue
      if self.category == CATEGORY_BOOK_OF_THE_YEAR:
        if 'book of the year' not in key:
          continue
        category = CATEGORY_BOOK_OF_THE_YEAR
      else:
        if not current_category or not self.category_matches(current_category):
          continue
        category = self.category
      row = self.row(
        year, title, author, RESULT_WINNER,
        self.first_link_url(node, page_url) or page_url,
        category)
      if row is not None:
        rows.append(row)
    return rows

  def rows_for_2023_page(self, soup, page_url, year):
    rows = []
    current_category = None
    for node in self.content_nodes(soup):
      text = self.clean_text(node)
      if not text:
        continue
      if node.name in {'h1', 'h2', 'h3'}:
        category = self.category_for_heading(text)
        if category is not None:
          current_category = category
          continue
      if current_category is None or node.name not in {'p', 'li', 'h3'}:
        continue
      cleaned_text, winner_marker = self.strip_result_suffix(text)
      title, author = self.parse_title_author_line(cleaned_text)
      if not title or not author:
        continue
      text_key = normalize_heading(text)
      if self.category == CATEGORY_BOOK_OF_THE_YEAR:
        result = RESULT_WINNER if 'book of the year' in text_key else RESULT_SHORTLISTED
        category = CATEGORY_BOOK_OF_THE_YEAR
      else:
        if not self.category_matches(current_category):
          continue
        result = RESULT_WINNER if winner_marker else RESULT_SHORTLISTED
        category = self.category
      row = self.row(
        year, title, author, result,
        self.first_link_url(node, page_url) or page_url,
        category)
      if row is not None:
        rows.append(row)
    return rows

  def category_for_heading(self, text):
    key = _category_key(text)
    if key == _category_key(CATEGORY_FICTION) or key.endswith(' fiction'):
      return CATEGORY_FICTION
    if key in {'nonfiction', 'nonfiction category'} or 'nonfiction' in key:
      return CATEGORY_NONFICTION
    if key == _category_key(CATEGORY_POETRY) or 'poetry' in key:
      return CATEGORY_POETRY
    return None

  def rows_for_2022_page(self, soup, page_url, year):
    nodes = self.content_nodes(soup)
    rows = []
    pending = None
    in_list = False
    winner = self.winner_from_page(nodes, page_url, year)
    if winner is not None:
      rows.append(winner)
    for node in nodes:
      text = self.clean_text(node)
      key = normalize_heading(text)
      if 'longlist' in key:
        in_list = True
        continue
      if in_list and ('judges' in key or 'about the prize' in key):
        break
      if not in_list or node.name != 'h4':
        continue
      if 'shortlisted' in key:
        if pending is not None:
          rows.append(pending)
          pending = None
        continue
      title, author = self.parse_title_author_line(text)
      if title and author:
        pending = self.row(year, title, author, RESULT_SHORTLISTED, page_url)
    return rows

  def rows_for_single_prize_page(self, soup, page_url, year):
    nodes = self.content_nodes(soup)
    rows = []
    winner = self.winner_from_page(nodes, page_url, year)
    if winner is not None:
      rows.append(winner)
    rows.extend(self.shortlist_rows_from_pairs(nodes, page_url, year))
    rows.extend(self.shortlist_rows_from_dash_lines(nodes, page_url, year))
    return rows

  def winner_from_page(self, nodes, page_url, year):
    for node in nodes:
      text = self.clean_text(node)
      if not text:
        continue
      title, author = self.winner_title_author_from_text(text)
      if title and author:
        return self.row(year, title, author, RESULT_WINNER, self.first_link_url(node, page_url) or page_url)
    return None

  def winner_title_author_from_text(self, text):
    match = re.search(
      r'winner\s+(?:was|is)\s+(.+?),\s+for\s+(?:his|her|their)?\s*(?:novel|book|collection|memoir)?\s*(.+)$',
      text,
      re.I)
    if match is not None:
      title = re.sub(r'\.\s*$', '', match.group(2))
      return self.clean_title(title), self.clean_author(match.group(1))
    match = re.search(r'(.+?)[\u2019\']s\s+(.+)$', text)
    if 'winner' in normalize_heading(text) and match is not None:
      return self.clean_title(match.group(2)), self.clean_author(match.group(1))
    return '', ''

  def shortlist_rows_from_pairs(self, nodes, page_url, year):
    rows = []
    in_shortlist = False
    pending_title = None
    pending_url = page_url
    for node in nodes:
      text = self.clean_text(node)
      key = normalize_heading(text)
      if 'shortlist' in key:
        in_shortlist = True
        continue
      if in_shortlist and 'longlist' in key:
        break
      if not in_shortlist or not text:
        continue
      if node.name == 'h1':
        pending_title = self.clean_title(text)
        pending_url = self.first_link_url(node, page_url) or page_url
      elif node.name == 'h2' and pending_title:
        row = self.row(year, pending_title, text, RESULT_SHORTLISTED, pending_url)
        if row is not None:
          rows.append(row)
        pending_title = None
    return rows

  def shortlist_rows_from_dash_lines(self, nodes, page_url, year):
    rows = []
    in_shortlist = False
    for node in nodes:
      text = self.clean_text(node)
      key = normalize_heading(text)
      if 'shortlist' in key:
        in_shortlist = True
        continue
      if in_shortlist and 'longlist' in key:
        break
      if not in_shortlist or node.name not in {'h4', 'p', 'li'}:
        continue
      title, author = self.parse_title_author_line(text)
      row = self.row(year, title, author, RESULT_SHORTLISTED, self.first_link_url(node, page_url) or page_url)
      if row is not None:
        rows.append(row)
    return rows


class FolioWritersPrizeWikipediaParser(FolioWritersPrizeBaseParser):

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
    current_result_text = ''
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
      if result_text:
        current_result_text = result_text
      result = self.result_from_text(result_text or current_result_text)
      if result is None:
        continue
      title_cell = self.cell_for_key(cells, header_map, 'title', missing_year_cell)
      author_cell = self.cell_for_key(cells, header_map, 'author', missing_year_cell)
      title = self.clean_title(self.clean_text(title_cell))
      author = self.clean_author(self.clean_text(author_cell))
      row = self.row(
        year, title, author, result,
        self.first_link_url(title_cell, base_url) or base_url,
        self.category)
      if row is not None:
        rows.append(row)
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
    year = self.year_from_text(self.clean_text(year_cell)) if year_cell is not None else None
    return year if year is not None else current_year

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
    cell = self.cell_for_key(cells, header_map, 'result', missing_year_cell)
    return self.clean_text(cell) if cell is not None else ''

  def result_from_text(self, text):
    key = normalize_heading(text)
    if self.category == CATEGORY_BOOK_OF_THE_YEAR:
      if (
          any(value in key for value in ('fiction', 'nonfiction', 'poetry'))
          and 'book of the year' not in key
          and 'overall' not in key):
        return None
      if 'winner' in key or 'won' in key:
        return RESULT_WINNER
      if 'shortlist' in key or 'shortlisted' in key or not key:
        return RESULT_SHORTLISTED
      return None
    if not self.result_matches_category(key):
      return None
    if 'winner' in key or 'won' in key:
      return RESULT_WINNER
    if 'shortlist' in key or 'shortlisted' in key or 'finalist' in key:
      return RESULT_SHORTLISTED
    return RESULT_SHORTLISTED

  def result_matches_category(self, key):
    key = key.replace('non fiction', 'nonfiction')
    if self.category == CATEGORY_FICTION and 'nonfiction' in key:
      return False
    return any(alias in key for alias in self.category_keys)


def parse_folio_writers_prize_official(
    html, category, category_aliases=(), url=OFFICIAL_URL, name=AWARD_NAME):
  return FolioWritersPrizeOfficialParser(
    category, category_aliases).parse(html, url, name)


def parse_folio_writers_prize_wikipedia(
    html, category, category_aliases=(), url=WIKIPEDIA_URL, name=AWARD_NAME):
  return FolioWritersPrizeWikipediaParser(
    category, category_aliases).parse(html, url, name)
