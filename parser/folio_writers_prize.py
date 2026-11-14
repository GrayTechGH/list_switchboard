#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Folio/Writers' Prize parsers.

Maintenance notes:
- The official archive has several distinct HTML eras.  Every era is parsed
  from its book card or result heading; descriptive paragraphs are never
  treated as bylines.
- The prize has no 2016 award and its published archive ends in 2024.  The
  fetcher validates the finite history before allowing either live source to
  satisfy an import.
- Wikipedia is a replacement fallback only.  Bookshop.org list pages are
  intentionally ignored because direct fetches return Cloudflare challenges.
"""

import re
from collections import Counter
from urllib.parse import urljoin

from bs4 import BeautifulSoup, UnicodeDammit
from lxml import html as lxml_html

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, split_title_author_byline,
    strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, split_title_author_byline,
    strip_publication_notes,
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

KNOWN_CATEGORIES = (
  CATEGORY_FICTION,
  CATEGORY_NONFICTION,
  CATEGORY_POETRY,
)

HISTORY_YEARS = (2014, 2015, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024)
BOOK_OF_YEAR_COUNTS = {
  **{year: 8 for year in HISTORY_YEARS if year <= 2022},
  2023: 3,
  2024: 3,
}
CATEGORY_COUNTS = {2023: 5, 2024: 3}

HISTORY_NOTE = (
  'The published Writers\' Prize archive covers 2014-2015 and 2017-2024; '
  'no prize was awarded in 2016 and 2024 is the final published year.'
)

HEADER_ALIASES = {
  'year': 'year',
  'award year': 'year',
  'author': 'author',
  'authors': 'author',
  'writer': 'author',
  'writers': 'author',
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


def _title_key(value):
  return normalize_heading(value)


def _title_prefix(left, right):
  left_key = _title_key(left)
  right_key = _title_key(right)
  return bool(left_key and right_key and (
    left_key.startswith(right_key) or right_key.startswith(left_key)))


class FolioWritersPrizeBaseParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def __init__(self, category, category_aliases=()):
    self.category = category
    aliases = category_aliases or CATEGORY_ALIASES.get(category, (category,))
    self.category_aliases = tuple(aliases)
    self.category_keys = {_category_key(alias) for alias in self.category_aliases}

  def decode_html(self, html):
    if isinstance(html, bytes):
      decoded = UnicodeDammit(html, is_html=True).unicode_markup
      return decoded or html.decode('utf-8', 'replace')
    return html or ''

  def clean_text(self, node):
    if node is None:
      return ''
    if isinstance(node, str):
      text = node
    else:
      node = BeautifulSoup(str(node), 'html.parser')
      for removable in node.find_all(['script', 'style', 'sup']):
        removable.decompose()
      text = node.get_text(' ', strip=True)
    return normalize_line(text.replace('\xa0', ' '))

  def clean_title(self, value):
    value = normalize_line(value)
    value = re.sub(r'\s+\|\s+.*$', '', value).strip()
    value = re.sub(r'\s*\b(?:winner|shortlisted|longlisted)\b\s*$', '', value, flags=re.I).strip()
    value = strip_publication_notes(value)
    value = value.strip(' "\'\u2018\u2019\u201c\u201d,')
    return value[:-1].rstrip() if value.endswith('.') else value

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
    title, author = split_title_author_byline(text)
    if title and author:
      title, author = self.clean_title(title), self.clean_author(author)
      return (title, author) if self.plausible_card(title, author) else ('', '')
    # Official legacy cards use an en/em dash and occasionally omit the space
    # before it (``The Topeka School– Ben Lerner``).
    dash_match = re.match(r'^(.+?)\s*[-\u2013\u2014]\s+(.+)$', text)
    if dash_match is not None:
      title = self.clean_title(dash_match.group(1))
      author = self.clean_author(dash_match.group(2))
      return (title, author) if self.plausible_card(title, author) else ('', '')
    return '', ''

  def plausible_card(self, title, author):
    """Reject prose headings that happen to contain a dash or final ``by``."""
    if not title or not author or len(title) > 240 or len(author) > 160:
      return False
    prose = r'\b(?:is|was|were|has|have|born|author\s+of|judge|judges|'
    prose += r'shortlisted|longlisted|biograph(?:y|ical)|description)\b'
    return re.search(prose, author, re.I) is None

  def strip_result_suffix(self, text):
    text = normalize_line(text)
    winner = bool(re.search(r'\b(?:winner|book of the year)\b', text, re.I))
    text = re.sub(
      r'\s*[-\u2013\u2014]\s*(?:winner|shortlisted|longlisted|[^-]*category[^-]*)\b.*$',
      '', text, flags=re.I).strip()
    text = re.sub(
      r'\s*,?\s*\b(?:category\s+winner|book\s+of\s+the\s+year)\b.*$',
      '', text, flags=re.I).strip()
    return text, winner

  def row(self, year, title, author, result, source_url, category=None,
          source_category=None):
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
      'source_category': source_category or category or self.category,
    }

  def _merge_alias(self, row, title):
    if not title or _title_key(title) == _title_key(row.get('title', '')):
      return
    aliases = list(row.get('aliases') or [])
    if title not in aliases:
      aliases.append(title)
    row['aliases'] = aliases

  def dedupe_rows(self, rows):
    deduped = []
    index_by_key = {}
    for row in rows:
      title = row.get('title', '')
      author_key = normalize_heading(row.get('author', ''))
      title_key = _title_key(title)
      if not title_key or not author_key:
        continue
      exact_key = (
        row.get('award_year'), _category_key(row.get('category', '')),
        title_key, author_key)
      existing_index = index_by_key.get(exact_key)
      if existing_index is not None:
        existing = deduped[existing_index]
        if existing.get('result') != RESULT_WINNER and row.get('result') == RESULT_WINNER:
          deduped[existing_index] = row
        continue

      variant_index = None
      for index, existing in enumerate(deduped):
        if (
            existing.get('award_year') == row.get('award_year')
            and _category_key(existing.get('category', '')) == _category_key(row.get('category', ''))
            and normalize_heading(existing.get('author', '')) == author_key
            and _title_prefix(existing.get('title', ''), title)):
          variant_index = index
          break
      if variant_index is None:
        index_by_key[exact_key] = len(deduped)
        deduped.append(row)
        continue

      existing = deduped[variant_index]
      if len(title) > len(existing.get('title', '')):
        self._merge_alias(row, existing.get('title', ''))
        if existing.get('result') == RESULT_WINNER:
          row['result'] = RESULT_WINNER
        deduped[variant_index] = row
      else:
        self._merge_alias(existing, title)
        if row.get('result') == RESULT_WINNER:
          existing['result'] = RESULT_WINNER
    return deduped

  def expected_counts(self):
    return BOOK_OF_YEAR_COUNTS if self.category == CATEGORY_BOOK_OF_THE_YEAR else CATEGORY_COUNTS

  def validate_entries(self, entries):
    expected = self.expected_counts()
    counts = Counter()
    winners = Counter()
    for entry in entries:
      year = self.year_from_text(entry.get('award_year', ''))
      if year is None:
        raise ValueError(f'{self.category} contains an entry without an award year')
      counts[year] += 1
      if entry.get('result') == RESULT_WINNER:
        winners[year] += 1
    if dict(counts) != expected:
      raise ValueError(
        f'{self.category} coverage mismatch: expected {expected}, got {dict(counts)}')
    expected_winners = {year: 1 for year in expected}
    if dict(winners) != expected_winners:
      raise ValueError(
        f'{self.category} winner coverage mismatch: expected {expected_winners}, got {dict(winners)}')

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      try:
        year = int(row['award_year'])
      except Exception:
        continue
      by_year.setdefault(year, []).append(row)

    category_order = {
      CATEGORY_FICTION: 0,
      CATEGORY_NONFICTION: 1,
      CATEGORY_POETRY: 2,
    }
    entries = []
    for year in sorted(by_year):
      year_rows = sorted(
        by_year[year],
        key=lambda row: (
          0 if row.get('result') == RESULT_WINNER else 1,
          category_order.get(row.get('source_category'), 99)),
      )
      award_rows = []
      for row in year_rows:
        metadata_row = dict(row)
        metadata_row.pop('source_category', None)
        award_rows.append(self.build_award_entry(
          metadata_row, row['source_url'], year, row['category']))
      entries.extend(assign_positions(
        award_rows, year, tied_winners_share_position=False))
    return entries

  def history_notes(self):
    if self.category == CATEGORY_BOOK_OF_THE_YEAR:
      return [
        HISTORY_NOTE,
        'From 2023, Book of the Year contains the three category winners; the overall winner is promoted to the base-year position.',
      ]
    return [HISTORY_NOTE, f'{self.category} was introduced as a separate category in 2023.']


class FolioWritersPrizeOfficialParser(FolioWritersPrizeBaseParser):

  def parse(
      self, html, base_url=OFFICIAL_URL, name=AWARD_NAME, fetch_url=None,
      log=None, progress=None, validate=False):
    html = self.decode_html(html)
    if self.is_cloudflare_challenge(html):
      return self.parsed_result(name, base_url, [])
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    archive_links = self.archive_links(soup, base_url)

    if fetch_url is not None and archive_links:
      links = self.links_for_category(archive_links)
      total = len(links)
      for index, (kind, year, url) in enumerate(links, 1):
        try:
          if progress is not None:
            progress(index, total, f'Fetching {name} archive page {index} of {total}')
          page_html = fetch_url(url)
          page_html = self.decode_html(page_html)
          if self.is_cloudflare_challenge(page_html):
            raise ValueError(f'archive page was not parseable: {url}')
          rows.extend(self.rows_for_page(page_html, url, year, kind))
        except Exception as err:
          if log is not None:
            log(f'{name} archive page failed: {url}: {err}')
          raise
    else:
      year = self.year_from_text(self.clean_text(soup.find('title'))) or self.year_from_text(base_url)
      if year is not None:
        rows.extend(self.rows_for_soup(soup, base_url, year, 'year'))

    entries = self.entries_from_rows(self.dedupe_rows(rows))
    if validate:
      self.validate_entries(entries)
    return self.parsed_result(
      name, base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=self.history_notes())

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
      if year is None or year == 2016 or year > 2024:
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
      'judge', 'judging', 'news', 'press', 'reading guide', 'bookshop',
      'new writers prize', 'contact', 'about', 'terms',
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
    if year not in HISTORY_YEARS:
      return []
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
      if any(
          any(
            'menu' in token.casefold()
            or token.casefold() in {'et-l--header', 'et-l--footer'}
            for token in parent.get('class', []))
          for parent in node.parents):
        continue
      text = self.clean_text(node)
      if text:
        nodes.append(node)
    return nodes

  def _heading_index(self, nodes, text, start=0):
    key = normalize_heading(text)
    for index, node in enumerate(nodes[start:], start):
      if node.name in {'h1', 'h2', 'h3', 'h4'} and key in normalize_heading(self.clean_text(node)):
        return index
    return None

  def _first_shortlist_index(self, nodes):
    return self._heading_index(nodes, 'shortlist')

  def _last_shortlist_index(self, nodes):
    indexes = [
      index for index, node in enumerate(nodes)
      if node.name in {'h1', 'h2', 'h3'}
      and 'shortlist' in normalize_heading(self.clean_text(node))
    ]
    return indexes[-1] if indexes else None

  def _stop_index(self, nodes, start):
    for index, node in enumerate(nodes[start + 1:], start + 1):
      key = normalize_heading(self.clean_text(node))
      if node.name in {'h1', 'h2', 'h3'} and (
          'longlist' in key or 'judge' in key or 'about the prize' in key):
        return index
    return len(nodes)

  def rows_for_2024_category_page(self, soup, page_url, year):
    rows = []
    winner_next = False
    pending_title = None
    pending_url = page_url
    for node in self.content_nodes(soup):
      text = self.clean_text(node)
      key = normalize_heading(text)
      if 'category winner' in key:
        winner_next = True
        continue
      if node.name == 'h2':
        if key in {'read more', 'fiction', 'non fiction', 'nonfiction'} or not text:
          continue
        pending_title = self.clean_title(text)
        pending_url = self.first_link_url(node, page_url) or page_url
        continue
      if node.name == 'h3' and pending_title:
        result = RESULT_WINNER if winner_next else RESULT_SHORTLISTED
        row = self.row(
          year, pending_title, text, result, pending_url, self.category,
          self.category)
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
      if not text or 'category winner' not in key:
        continue
      title_text = re.sub(
        r'^\s*category\s+winner(?:\s*/\s*book\s+of\s+the\s+year)?\s*:\s*',
        '', text, flags=re.I)
      title, author = self.parse_title_author_line(title_text)
      if not title or not author or current_category is None:
        continue
      overall = 'book of the year' in key
      if self.category == CATEGORY_BOOK_OF_THE_YEAR:
        result = RESULT_WINNER if overall else RESULT_SHORTLISTED
        output_category = CATEGORY_BOOK_OF_THE_YEAR
      elif not self.category_matches(current_category):
        continue
      else:
        result = RESULT_WINNER
        output_category = self.category
      row = self.row(
        year, title, author, result,
        self.first_link_url(node, page_url) or page_url,
        output_category, current_category)
      if row is not None:
        rows.append(row)
    return rows

  def rows_for_2023_page(self, soup, page_url, year):
    nodes = self.content_nodes(soup)
    rows = []
    shortlist_index = self._first_shortlist_index(nodes)

    # The overall/category winners are announced before the shortlist heading.
    if shortlist_index is not None:
      current_category = None
      for node in nodes[:shortlist_index]:
        text = self.clean_text(node)
        key = normalize_heading(text)
        heading_category = self.category_for_heading(text)
        inline_category = self.inline_category(text)
        if (
            heading_category is not None
            and node.name in {'h1', 'h2', 'h3'}
            and ' by ' not in text.casefold()
        ):
          current_category = heading_category
          continue
        if node.name not in {'h1', 'h3', 'p'} or ' by ' not in text.casefold():
          continue
        title, author = self.parse_title_author_line(text)
        if not title or not author:
          continue
        winner = (
          'book of the year' in key
          or 'category winner' in key
          or (node.name == 'h1' and current_category is None))
        if not winner:
          continue
        if self.category == CATEGORY_BOOK_OF_THE_YEAR:
          output_category = CATEGORY_BOOK_OF_THE_YEAR
          result = RESULT_WINNER if 'book of the year' in key or node.name == 'h1' else RESULT_SHORTLISTED
        elif (
            (current_category is not None and self.category_matches(current_category))
            or (inline_category is not None and self.category_matches(inline_category))
        ):
          output_category = self.category
          result = RESULT_WINNER
        else:
          continue
        row = self.row(
          year, title, author, result, page_url, output_category,
          inline_category or current_category)
        if row is not None:
          rows.append(row)

    current_category = None
    if shortlist_index is None:
      shortlist_index = -1
    for node in nodes[shortlist_index + 1:]:
      text = self.clean_text(node)
      if node.name in {'h1', 'h2', 'h3'}:
        category = self.category_for_heading(text)
        if category is not None:
          current_category = category
          continue
      if current_category is None or node.name not in {'p', 'li', 'h3'}:
        continue
      title, author = self.parse_title_author_line(text)
      if not title or not author:
        continue
      _, winner_marker = self.strip_result_suffix(text)
      if self.category == CATEGORY_BOOK_OF_THE_YEAR:
        # Category-era Book of the Year contains only category winners; the
        # overall winner is promoted from the non-fiction category row.
        if not winner_marker:
          continue
        result = RESULT_WINNER if 'book of the year' in normalize_heading(text) else RESULT_SHORTLISTED
        output_category = CATEGORY_BOOK_OF_THE_YEAR
      elif not self.category_matches(current_category):
        continue
      else:
        result = RESULT_WINNER if winner_marker else RESULT_SHORTLISTED
        output_category = self.category
      row = self.row(year, title, author, result, page_url, output_category, current_category)
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

  def inline_category(self, text):
    """Return a category embedded in a result/byline heading."""
    key = _category_key(text)
    if 'nonfiction' in key:
      return CATEGORY_NONFICTION
    if 'fiction' in key:
      return CATEGORY_FICTION
    if 'poetry' in key:
      return CATEGORY_POETRY
    return None

  def rows_for_2022_page(self, soup, page_url, year):
    nodes = self.content_nodes(soup)
    rows = []
    shortlist_index = self._first_shortlist_index(nodes)
    if shortlist_index is None:
      return rows
    # The 2022 page places the longlist heading immediately after the
    # shortlist heading.  Unlike later eras, that heading is the container for
    # the cards we need, so begin the boundary scan at Longlist and stop only
    # at a later structural section (judges/about/navigation).
    longlist_index = next(
      (index for index, node in enumerate(nodes[shortlist_index + 1:], shortlist_index + 1)
       if node.name in {'h1', 'h2', 'h3'}
       and 'longlist' in normalize_heading(self.clean_text(node))),
      None)
    stop = self._stop_index(nodes, longlist_index or shortlist_index)
    shortlisted_next = False
    for node in nodes[shortlist_index + 1:stop]:
      text = self.clean_text(node)
      key = normalize_heading(text)
      if 'shortlisted' in key and node.name == 'h4':
        shortlisted_next = True
        continue
      if node.name != 'h4' or not shortlisted_next:
        continue
      title, author = self.parse_title_author_line(text)
      if not title or not author:
        continue
      row = self.row(year, title, author, RESULT_SHORTLISTED, page_url)
      if row is not None:
        rows.append(row)
      shortlisted_next = False

    winner = self.winner_row_from_nodes(nodes, page_url, year)
    if winner is not None:
      rows.append(winner)
    return rows

  def rows_for_single_prize_page(self, soup, page_url, year):
    nodes = self.content_nodes(soup)
    rows = []
    start = self._first_shortlist_index(nodes)
    if start is None:
      return rows
    stop = self._stop_index(nodes, start)
    if year in {2019, 2020, 2021}:
      start = self._last_shortlist_index(nodes) or start
      stop = self._stop_index(nodes, start)

    pending_title = ''
    for node in nodes[start + 1:stop]:
      if year in {2014, 2015}:
        if node.name == 'h1':
          pending_title = self.clean_title(self.clean_text(node))
          continue
        if node.name != 'h2' or not pending_title:
          continue
        row = self.row(
          year, pending_title, self.clean_text(node), RESULT_SHORTLISTED, page_url)
        if row is not None:
          rows.append(row)
        pending_title = ''
        continue
      if node.name == 'h3' and year == 2017:
        pending_title = self.clean_title(self.clean_text(node))
        continue
      if year == 2017:
        if node.name != 'h4':
          continue
        author = self.clean_author(self.clean_text(node))
        if pending_title and author:
          row = self.row(year, pending_title, author, RESULT_SHORTLISTED, page_url)
          if row is not None:
            rows.append(row)
          pending_title = ''
        continue
      if node.name != 'h4':
        continue
      title, author = self.parse_title_author_line(self.clean_text(node))
      if not title or not author:
        continue
      row = self.row(year, title, author, RESULT_SHORTLISTED, page_url)
      if row is not None:
        rows.append(row)

    winner = self.winner_row_from_nodes(nodes, page_url, year)
    if winner is not None:
      rows.append(winner)
    else:
      hint = self.winner_hint(nodes, year)
      if hint is not None:
        self.promote_winner(rows, hint[0], hint[1])
    return rows

  def winner_row_from_nodes(self, nodes, page_url, year):
    hint = self.winner_hint(nodes, year)
    if hint is None or not hint[0] or not hint[1]:
      return None
    return self.row(year, hint[0], hint[1], RESULT_WINNER, page_url)

  def winner_hint(self, nodes, year):
    for index, node in enumerate(nodes):
      text = self.clean_text(node)
      key = normalize_heading(text)
      if year in {2014, 2015, 2017}:
        match = re.search(
          r'\b(?:19|20)\d{2}\s+winner\s+was\s+(.+?),\s+for\s+(.+?)(?:\.\s|$)',
          text, re.I)
        if match is not None:
          return self.clean_title(match.group(2)), self.clean_author(match.group(1))
      if year in {2018, 2019} and 'winner' in key:
        match = re.search(r'(?:winner|wins).*?(?::|was)\s*(.+?),\s+for\s+(.+?)(?:\.\s|$)', text, re.I)
        if match is not None:
          return self.clean_title(match.group(2)), self.clean_author(match.group(1))
      if year == 2020 and node.name in {'h1', 'h2', 'h3'} and 'wins' in key:
        author = re.sub(r'\s+wins\b.*$', '', text, flags=re.I).strip()
        return '', self.clean_author(author)
      if year == 2021 and node.name == 'h1' and 'winner' in key:
        for following in nodes[index + 1:index + 4]:
          text2 = self.clean_text(following)
          if '’s ' in text2 or "'s " in text2:
            author, title = re.split(r'[’\']s\s+', text2, maxsplit=1)
            return self.clean_title(title), self.clean_author(author)
      if year == 2022 and ('awarded the' in key or 'has been awarded' in key):
        match = re.search(
          r'(?:many\s+)?congratulations to\s+(.+?),\s+who has been awarded .*? for (?:his|her|their)\s+(?:novel|book|memoir)\s+(.+?)(?:\s*,|\.)',
          text, re.I)
        if match is not None:
          return self.clean_title(match.group(2)), self.clean_author(match.group(1))
    return None

  def promote_winner(self, rows, title, author):
    for row in rows:
      if normalize_heading(row.get('author', '')) != normalize_heading(author):
        continue
      if not title or _title_prefix(row.get('title', ''), title):
        row['result'] = RESULT_WINNER
        return


class FolioWritersPrizeWikipediaParser(FolioWritersPrizeBaseParser):

  def parse(self, html, base_url=WIKIPEDIA_URL, name=AWARD_NAME,
            validate=False, **_kwargs):
    html = self.decode_html(html)
    rows = self.parse_rows(html, base_url)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    if validate:
      self.validate_entries(entries)
    return self.parsed_result(
      name, base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=self.history_notes())

  def parse_rows(self, html, base_url):
    root = lxml_html.fromstring(html or '<html></html>')
    rows = []
    for table in root.xpath('//table'):
      grid = self.table_grid(table)
      header_index, header_map = self.header_map(grid)
      if header_index is None or not {'year', 'title', 'author'}.issubset(header_map):
        continue
      current_year = None
      current_result = {}
      for cells in grid[header_index + 1:]:
        if not cells:
          continue
        if all(cell.tag == 'th' for cell in cells):
          continue
        year_cell = self.cell_for_key(cells, header_map, 'year')
        year_text = self.clean_cell_text(year_cell) if year_cell is not None else ''
        # A logical table grid still contains an empty continuation cell when
        # the source omits a year; carry the previous rowspan year forward.
        year = self.year_from_text(year_text) or current_year
        if year is None:
          continue
        current_year = year
        if year not in HISTORY_YEARS:
          continue
        result_cell = self.cell_for_key(cells, header_map, 'result')
        result_text = self.clean_cell_text(result_cell) if result_cell is not None else ''
        result_key = _category_key(result_text)
        if not result_key:
          result_key = current_result.get(year, '')
        else:
          current_result[year] = result_key
        result = self.result_for_row(year, result_key)
        if result is None:
          continue
        title_cell = self.cell_for_key(cells, header_map, 'title')
        author_cell = self.cell_for_key(cells, header_map, 'author')
        title = self.clean_title(self.clean_cell_text(title_cell)) if title_cell is not None else ''
        author = self.clean_author(self.clean_cell_text(author_cell)) if author_cell is not None else ''
        row = self.row(year, title, author, result, base_url, self.category)
        if row is not None:
          rows.append(row)
    return rows

  def result_for_row(self, year, key):
    key = key.replace('non fiction', 'nonfiction')
    if self.category == CATEGORY_BOOK_OF_THE_YEAR:
      if year >= 2023:
        if 'overall winner' in key or (
            'book of the year' in key and 'winner' in key):
          return RESULT_WINNER
        if any(
            f'{category} winner' in key
            for category in ('fiction', 'nonfiction', 'poetry')):
          return RESULT_SHORTLISTED
        return None
      if 'winner' in key or 'won' in key:
        return RESULT_WINNER
      if 'shortlist' in key or 'shortlisted' in key:
        return RESULT_SHORTLISTED
      return None
    if not self.result_matches_category(key):
      return None
    if 'winner' in key or 'won' in key:
      return RESULT_WINNER
    if 'shortlist' in key or 'shortlisted' in key or 'finalist' in key:
      return RESULT_SHORTLISTED
    return None

  def result_matches_category(self, key):
    if self.category == CATEGORY_FICTION and 'nonfiction' in key:
      return False
    return any(alias in key for alias in self.category_keys)

  def header_map(self, grid):
    for index, cells in enumerate(grid):
      mapped = {}
      for column, cell in enumerate(cells):
        key = HEADER_ALIASES.get(_category_key(self.clean_cell_text(cell)))
        if key is not None and key not in mapped:
          mapped[key] = column
      if {'year', 'title', 'author'}.issubset(mapped):
        return index, mapped
    return None, {}

  def cell_for_key(self, cells, header_map, key):
    index = header_map.get(key)
    if index is None or index >= len(cells):
      return None
    return cells[index]

  def clean_cell_text(self, cell):
    if cell is None:
      return ''
    text = normalize_line(' '.join(
      value.strip() for value in cell.xpath(
        './/text()[not(ancestor::sup or ancestor::style or ancestor::script)]')
      if value.strip()))
    text = re.sub(r'\s*\[\s*\d+\s*\]\s*', ' ', text)
    return normalize_line(text)

  def table_grid(self, table):
    grid = []
    rowspans = {}
    for tr in table.xpath('.//tr'):
      row = []
      column = 0
      for cell in tr.xpath('./td|./th'):
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


def parse_folio_writers_prize_official(
    html, category, category_aliases=(), url=OFFICIAL_URL, name=AWARD_NAME):
  return FolioWritersPrizeOfficialParser(
    category, category_aliases).parse(html, url, name)


def parse_folio_writers_prize_wikipedia(
    html, category, category_aliases=(), url=WIKIPEDIA_URL, name=AWARD_NAME):
  return FolioWritersPrizeWikipediaParser(
    category, category_aliases).parse(html, url, name)
