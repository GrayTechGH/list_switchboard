#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Victorian Premier's Literary Awards parser.

Maintenance notes:
- The Wheeler Centre is the live source for V1. Archive/current pages expose
  repeated book blocks under stage headings such as WINNERS and SHORTLIST.
- V1 keeps only configured core book categories and deliberately skips highly
  commended, longlist-like, overall, manuscript, poetry, drama, and humour
  sections.
"""

import json
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


AWARD_NAME = "Victorian Premier's Literary Awards"
OFFICIAL_URL = (
  'https://www.wheelercentre.com/'
  'victorian-premier-s-literary-awards/past-awards')

STAGE_RESULTS = {
  'winner': RESULT_WINNER,
  'winners': RESULT_WINNER,
  'shortlist': RESULT_SHORTLISTED,
  'shortlisted': RESULT_SHORTLISTED,
}

SKIP_STAGE_KEYS = {
  'highly commended',
  'longlist',
  'longlisted',
}

SKIP_CATEGORY_KEYS = {
  'victorian prize for literature',
  'prize for drama',
  'drama',
  'prize for poetry',
  'poetry',
  'prize for an unpublished manuscript',
  'unpublished manuscript',
  'peoples choice award',
  'people s choice award',
  'prize for humour writing',
  'humour writing',
}

CORE_CATEGORY_KEYS = {
  'prize for fiction',
  'fiction',
  'prize for nonfiction',
  'nonfiction',
  'prize for writing for young adults',
  'john marsden prize for writing for young adults',
  'writing for young adults',
  'prize for children s literature',
  'children s literature',
  'prize for indigenous writing',
  'indigenous writing',
}

NOISE_KEYS = {
  '',
  'learn more',
  'read more',
  'about the awards',
  'past awards',
  'people s choice award',
  'events and tickets',
  'watch listen read',
  'support us',
  'opportunities',
  'the centre',
  'donate',
  'cart',
  'favourites',
  'account',
  'search',
  'subscribe',
}


def _category_key(value):
  value = normalize_heading(value)
  return value.replace('non fiction', 'nonfiction')


class VictorianPremiersLiteraryAwardsOfficialParser(AwardParserBase):

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
      if year is None or year < 2011:
        continue
      key = normalize_heading(combined)
      if 'victorian premier' not in key or 'literary award' not in key:
        continue
      if 'past awards' not in key and f'{year} victorian premier' not in key:
        continue
      links[year] = urljoin(base_url, href)
    return tuple(url for _year, url in sorted(links.items()))

  def page_rows(self, html, page_url):
    soup = BeautifulSoup(html, 'html.parser')
    page_year = self.year_from_text(page_url) or self.year_from_text(self.clean_text(soup.find('title')))
    lines = self.dom_lines(soup, page_url)
    rows = self.rows_from_lines(lines, page_url, page_year=page_year)
    if rows:
      return rows
    return self.rows_from_lines(self.next_data_lines(soup), page_url, page_year=page_year)

  def dom_lines(self, soup, page_url):
    root = soup.find('main') or soup.body or soup
    lines = []
    for node in root.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'p', 'li']):
      if node.find_parent(['script', 'style', 'nav', 'header', 'footer']):
        continue
      text = self.clean_text(node)
      if not text:
        continue
      lines.append((text, self.first_link_url(node, page_url)))
    return lines

  def next_data_lines(self, soup):
    script = soup.find('script', id='__NEXT_DATA__')
    if script is None:
      return []
    try:
      data = json.loads(script.string or script.get_text())
    except Exception:
      return []
    values = []
    self.collect_json_strings(data, values)
    return [(value, '') for value in values]

  def collect_json_strings(self, value, values):
    if isinstance(value, dict):
      for key, child in value.items():
        if key in {'url', 'href', 'src', 'id', 'destinationId'}:
          continue
        self.collect_json_strings(child, values)
    elif isinstance(value, list):
      for child in value:
        self.collect_json_strings(child, values)
    elif isinstance(value, str):
      text = normalize_line(value)
      if text:
        values.append(text)

  def rows_from_lines(self, lines, page_url, page_year=None):
    year = page_year or self.year_from_text(page_url)
    rows = []
    current_result = None
    current_category = None
    pending_title = None
    pending_url = ''
    skip_possible_publisher = False

    for index, (text, link_url) in enumerate(lines):
      text = self.clean_line_text(text)
      key = normalize_heading(text)
      category_key = _category_key(text)
      if not text:
        continue
      line_year = self.year_from_text(text)
      if year is None and line_year is not None:
        year = line_year
      if key in NOISE_KEYS:
        pending_title = None
        pending_url = ''
        continue
      if key in STAGE_RESULTS:
        current_result = STAGE_RESULTS[key]
        current_category = None
        pending_title = None
        pending_url = ''
        skip_possible_publisher = False
        continue
      if key in SKIP_STAGE_KEYS:
        current_result = None
        current_category = None
        pending_title = None
        pending_url = ''
        skip_possible_publisher = False
        continue
      if category_key in self.category_keys:
        current_category = self.category
        pending_title = None
        pending_url = ''
        skip_possible_publisher = False
        continue
      if category_key in SKIP_CATEGORY_KEYS or category_key in CORE_CATEGORY_KEYS:
        current_category = None
        pending_title = None
        pending_url = ''
        skip_possible_publisher = False
        continue
      if current_result is None or current_category is None or year is None:
        continue
      if self.is_non_entry_line(text):
        continue
      if skip_possible_publisher and self.next_non_noise_key(lines, index) == 'learn more':
        continue
      skip_possible_publisher = False

      title, author = self.parse_title_author_line(text)
      if title and author:
        rows.append(self.row(year, title, author, current_result, link_url or page_url))
        pending_title = None
        pending_url = ''
        skip_possible_publisher = True
        continue

      if pending_title is None:
        pending_title = self.clean_title(text)
        pending_url = link_url or page_url
        continue

      author = self.clean_author(text)
      if author:
        rows.append(self.row(year, pending_title, author, current_result, pending_url or page_url))
        skip_possible_publisher = True
      pending_title = None
      pending_url = ''
    return rows

  def row(self, year, title, author, result, source_url):
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': source_url,
      'category': self.category,
      'award': self.AWARD_NAME,
    }

  def parse_title_author_line(self, text):
    text = normalize_line(text)
    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', text, re.I)
    if by_match is not None:
      return self.clean_title(by_match.group(1)), self.clean_author(by_match.group(2))
    dash_match = re.match(r'^(.+?)\s+[\u2013\u2014-]\s+(.+)$', text)
    if dash_match is not None:
      return self.clean_title(dash_match.group(1)), self.clean_author(dash_match.group(2))
    return '', ''

  def next_non_noise_key(self, lines, index):
    for text, _url in lines[index + 1:]:
      key = normalize_heading(text)
      if key and key not in NOISE_KEYS:
        return key
      if key == 'learn more':
        return key
    return ''

  def is_non_entry_line(self, text):
    key = normalize_heading(text)
    if key in NOISE_KEYS or key in STAGE_RESULTS or key in SKIP_STAGE_KEYS:
      return True
    if _category_key(text) in self.category_keys or _category_key(text) in SKIP_CATEGORY_KEYS:
      return True
    if re.match(r'^\d{4}\s+victorian premier', key):
      return True
    return False

  def clean_line_text(self, value):
    value = normalize_line(value)
    value = re.sub(r'\s+Learn More$', '', value, flags=re.I).strip()
    return value

  def clean_text(self, node):
    if node is None:
      return ''
    return normalize_line(node.get_text(' ', strip=True))

  def clean_title(self, value):
    value = strip_publication_notes(value)
    return re.sub(r'^[\s"\'\u201c\u201d\u2018\u2019]+|[\s"\'\u201c\u201d\u2018\u2019]+$', '', value)

  def clean_author(self, value):
    value = strip_publication_notes(value)
    value = re.sub(r'^(?:by|author)\s*:?\s*', '', value, flags=re.I).strip()
    return re.sub(r'^[\s"\'\u201c\u201d\u2018\u2019]+|[\s"\'\u201c\u201d\u2018\u2019]+$', '', value)

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True) if hasattr(node, 'find') else None
    if link is None and getattr(node, 'name', None) == 'a' and node.get('href'):
      link = node
    if link is None:
      return ''
    return urljoin(base_url, link['href'])

  def year_from_text(self, value):
    match = re.search(r'\b(20\d{2})\b', value or '')
    return int(match.group(1)) if match is not None else None

  def dedupe_rows(self, rows):
    deduped = {}
    order = []
    for row in rows:
      title_key = normalize_heading(row.get('title', ''))
      author_key = normalize_heading(row.get('author', ''))
      if not title_key or not author_key:
        continue
      key = (row.get('award_year'), row.get('category'), title_key, author_key)
      existing = deduped.get(key)
      if existing is None:
        deduped[key] = row
        order.append(key)
      elif existing.get('result') != RESULT_WINNER and row.get('result') == RESULT_WINNER:
        deduped[key] = row
    return [deduped[key] for key in order]

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
      entries.extend(assign_positions(
        by_year[year],
        year,
        tied_winners_share_position=True))
    return entries


def parse_victorian_premiers_literary_awards(
    html, category, category_aliases=(), url=OFFICIAL_URL, name=AWARD_NAME,
    fetch_url=None, log=None, progress=None):
  return VictorianPremiersLiteraryAwardsOfficialParser(
    category,
    category_aliases).parse(
      html,
      url,
      name,
      fetch_url=fetch_url,
      log=log,
      progress=progress)
