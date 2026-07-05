#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Splatterpunk Awards parser for KillerCon official pages plus Goodreads.

Maintenance notes:
- KillerCon's official WordPress REST pages are authoritative for current
  nominees and past winners, but the past-winners page is winner-only.
- Goodreads is intentionally a live historical nominee supplement for V1.
- File 770 and founder reposts are reference-only because they are secondary
  post archives rather than an authoritative all-years nominee source.
"""

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, UnicodeDammit

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, split_title_author, strip_editor_marker,
    strip_publication_notes, strip_square_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, split_title_author, strip_editor_marker,
    strip_publication_notes, strip_square_notes,
  )
  from .generic import position_sort_key


AWARD_NAME = 'Splatterpunk Award'
OFFICIAL_AWARDS_URL = 'https://killerconatx.com/awards/'
OFFICIAL_AWARDS_API_URL = (
  'https://killerconatx.com/wp-json/wp/v2/pages?slug=awards')
OFFICIAL_PAST_WINNERS_URL = 'https://killerconatx.com/awards/past-award-winners/'
OFFICIAL_PAST_WINNERS_API_URL = (
  'https://killerconatx.com/wp-json/wp/v2/pages?slug=past-award-winners')
GOODREADS_URL = 'https://www.goodreads.com/award/show/38981-splatterpunk-award'

YEAR_RE = re.compile(r'(?:19|20)\d{2}')
SEMANTIC_TAGS = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li')

EXCLUDED_CATEGORY_FRAGMENTS = (
  'gonzalez',
  'lifetime',
  'short story',
)


def category_key(value):
  return normalize_heading(value).replace('non fiction', 'nonfiction')


def clean_source_text(value):
  value = normalize_line(value).replace('\x00', ' ').replace('\xa0', ' ')
  replacements = {
    '\u2018': "'",
    '\u2019': "'",
    '\u201c': '"',
    '\u201d': '"',
    '\u2013': '-',
    '\u2014': '-',
    '\u2026': '...',
  }
  for old, new in replacements.items():
    value = value.replace(old, new)
  return normalize_line(value)


class SplatterpunkParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def parse_official_current(
      self, source, base_url, name, category, category_aliases=()):
    rows = []
    notes = [
      'Official KillerCon awards page exposes current-cycle nominees only.',
      'As of July 5, 2026, the official page lists 2026 nominees and states '
      'winners will be announced at KillerCon 2026, November 6-8, 2026.',
    ]
    for html, title, link in self.official_current_documents(source):
      year = self.award_year(html, title)
      target_category = False
      for node in self.semantic_nodes(html):
        text = self.node_text(node)
        if not text:
          continue
        if node.name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
          target_category = self.category_matches(text, category, category_aliases)
          continue
        if not target_category or node.name != 'p' or year is None:
          continue
        parsed = self.parse_work_text(text, RESULT_SHORTLISTED)
        if parsed is None:
          notes.append(
            f'Official current nominee {year} {category} row could not be '
            f'parsed: {text}')
          continue
        rows.append(self.build_award_entry(
          parsed,
          self.first_link_url(node, link or base_url) or link or base_url,
          year,
          category))
      if year is None:
        notes.append('Official current nominee award year could not be determined.')
    return self.parsed_from_rows(name, base_url, rows, notes)

  def parse_official_winners(
      self, source, base_url, name, category, category_aliases=()):
    rows = []
    notes = [
      'Official KillerCon past-winners page is winner-only and covers 2018 '
      'forward; historical shortlist rows come from Goodreads where present.',
    ]
    target_category = False
    for html, _title, link in self.source_documents(source):
      for node in self.semantic_nodes(html):
        text = self.node_text(node)
        if not text:
          continue
        if node.name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p'):
          if self.looks_like_category_heading(text):
            target_category = self.category_matches(text, category, category_aliases)
          continue
        if node.name != 'li' or not target_category:
          continue
        row = self.parse_official_winner_row(text, category)
        if row is None:
          notes.append(f'Official winner row could not be parsed: {text}')
          continue
        rows.append(self.build_award_entry(
          row,
          self.first_link_url(node, link or base_url) or link or base_url,
          row.pop('year'),
          category))
    return self.parsed_from_rows(name, base_url, rows, notes)

  def parse_goodreads(self, html, base_url, name, category, category_aliases=()):
    rows = []
    notes = [
      'Goodreads is used as the V1 historical nominee supplement; official '
      'KillerCon winner rows are preferred when they overlap.',
      'Goodreads coverage is imported where present and is not treated as a '
      'guaranteed complete shortlist for every category/year.',
    ]
    soup = BeautifulSoup(self.decode_source(html), 'html.parser')
    for book_row in soup.find_all('tr', itemtype='http://schema.org/Book'):
      title_node = book_row.find(class_='bookTitle')
      author_node = book_row.find(class_='authorName')
      if title_node is None or author_node is None:
        continue
      title = self.clean_title(title_node.get_text(' ', strip=True))
      author = self.clean_author(author_node.get_text(' ', strip=True))
      for label_node in book_row.find_all('i'):
        label = self.node_text(label_node)
        parsed_label = self.parse_goodreads_label(label, category, category_aliases)
        if parsed_label is None:
          continue
        year, result = parsed_label
        rows.append(self.build_award_entry(
          {'title': title, 'author': author, 'result': result},
          self.first_link_url(title_node, base_url) or base_url,
          year,
          category))
    return self.parsed_from_rows(name, base_url, rows, notes)

  def combine_results(self, name, base_url, *parsed_results):
    rows = []
    notes = [
      'Splatterpunk official KillerCon sources provide current nominees and '
      'winner-only history; Goodreads supplies historical nominee rows.',
      'File 770 is reference-only in V1, not a live fallback.',
      'If neither official nor Goodreads sources expose a category/year '
      'shortlist, no shortlist rows are invented.',
    ]
    for parsed in parsed_results:
      if not parsed:
        continue
      notes.extend(parsed.get('notes', ()))
      rows.extend(dict(entry) for entry in parsed.get('entries', ()))
    return self.parsed_from_rows(name, base_url, rows, notes)

  def discover_goodreads_page_urls(self, html, base_url=GOODREADS_URL):
    soup = BeautifulSoup(self.decode_source(html), 'html.parser')
    urls = [base_url]
    for link in soup.find_all('a', href=True):
      href = link.get('href') or ''
      text = self.node_text(link)
      if 'award/show/38981-splatterpunk-award' not in href:
        continue
      if 'page=' not in href and not text.isdigit():
        continue
      url = urljoin(base_url, href)
      if url not in urls:
        urls.append(url)
    return tuple(urls)

  def parse_official_winner_row(self, text, category):
    match = re.match(r'^((?:19|20)\d{2})\s*[-]\s*(.+)$', clean_source_text(text))
    if match is None:
      return None
    parsed = self.parse_work_text(match.group(2), RESULT_WINNER)
    if parsed is None:
      return None
    parsed['year'] = int(match.group(1))
    return parsed

  def parse_work_text(self, text, result):
    text = self.clean_work_text(text)
    if not text:
      return None
    parsed = self.parse_edited_by(text)
    if parsed is None:
      parsed = self.parse_by(text)
    if parsed is None:
      parsed = self.parse_comma(text)
    if parsed is None:
      return None
    title, author = parsed
    title = self.clean_title(title)
    author = self.clean_author(author)
    if not title or not author:
      return None
    return {'title': title, 'author': author, 'result': result}

  def parse_edited_by(self, text):
    match = re.match(r'^(.*?)\s*,?\s+edited\s+by\s+(.+)$', text, re.I)
    if match is None:
      return None
    return match.group(1), match.group(2)

  def parse_by(self, text):
    match = re.match(r'^(.*?)\s*,?\s+by\s+(.+)$', text, re.I)
    if match is None:
      return None
    return match.group(1), match.group(2)

  def parse_comma(self, text):
    title, author = split_title_author(text)
    if title and author:
      return title, author
    return None

  def parse_goodreads_label(self, label, category, category_aliases):
    match = re.search(r'\(((?:19|20)\d{2})\)\s*$', label)
    if match is None or 'Splatterpunk Award' not in label:
      return None
    year = int(match.group(1))
    label_key = category_key(label[:match.start()])
    target_keys = self.category_keys(category, category_aliases)
    if (
        label_key.startswith('splatterpunk award nominee for') and
        any(key in label_key for key in target_keys)):
      return year, RESULT_SHORTLISTED
    if any(f'nominee for {key}' in label_key for key in target_keys):
      return year, RESULT_SHORTLISTED
    if any(f'splatterpunk award for {key}' in label_key for key in target_keys):
      return year, RESULT_WINNER
    return None

  def clean_work_text(self, text):
    text = strip_square_notes(clean_source_text(text))
    text = re.sub(r'^\s*(?:[-*]|\u2022)+\s*', '', text)
    return normalize_line(text.strip(' "\'.,;'))

  def clean_title(self, value):
    value = strip_publication_notes(clean_source_text(value))
    return value.strip(' "\'.,;')

  def clean_author(self, value):
    value = clean_source_text(value)
    value = re.sub(r'^\s*(?:by|edited\s+by)\s+', '', value, flags=re.I)
    value = re.sub(r'\s*\((?:Goodreads Author|Author|Editor|Editors?)\)\s*',
                   ' ', value, flags=re.I)
    value = re.sub(r'\s*,?\s*(?:eds?|editors?)\.?$', '', value, flags=re.I)
    return strip_editor_marker(strip_publication_notes(value)).strip(' "\'.,;')

  def official_current_documents(self, source):
    return tuple(
      (html, title, link)
      for html, title, link in self.source_documents(source)
      if self.is_official_awards_page(title, link, html))

  def source_documents(self, source):
    text = self.decode_source(source)
    parsed = self.parse_json_source(text)
    if parsed is None:
      return ((text, '', ''),)
    if isinstance(parsed, dict):
      parsed = (parsed,)
    documents = []
    for item in parsed:
      if not isinstance(item, dict):
        continue
      content = item.get('content') or {}
      title = item.get('title') or ''
      content_html = content.get('rendered') if isinstance(content, dict) else ''
      title_html = title.get('rendered') if isinstance(title, dict) else title
      title_text = self.html_text(title_html)
      link = item.get('link') or item.get('url') or ''
      if content_html:
        documents.append((content_html, title_text, link))
    return tuple(documents) or ((text, '', ''),)

  def parse_json_source(self, text):
    stripped = (text or '').lstrip()
    if not stripped.startswith(('[', '{')):
      return None
    try:
      return json.loads(stripped)
    except Exception:
      return None

  def decode_source(self, source):
    if isinstance(source, bytes):
      return UnicodeDammit(source).unicode_markup
    return source or ''

  def semantic_nodes(self, html):
    soup = BeautifulSoup(self.decode_source(html), 'html.parser')
    for removable in soup.find_all(['script', 'style', 'sup']):
      removable.decompose()
    for br in soup.find_all('br'):
      br.replace_with('\n')
    return soup.find_all(SEMANTIC_TAGS)

  def node_text(self, node):
    return clean_source_text(node.get_text(' ', strip=True))

  def html_text(self, html):
    return clean_source_text(
      BeautifulSoup(self.decode_source(html), 'html.parser').get_text(' ', strip=True))

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True)
    return urljoin(base_url, link['href']) if link is not None else ''

  def award_year(self, html, title=''):
    for value in (title, self.html_text(html)):
      match = re.search(r'Splatterpunk\s+Awards?\s+((?:19|20)\d{2})',
                        value, re.I)
      if match is not None:
        return int(match.group(1))
    match = YEAR_RE.search(title or '')
    return int(match.group(0)) if match is not None else None

  def is_official_awards_page(self, title, link, html):
    normalized_link = (link or '').rstrip('/') + '/' if link else ''
    if normalized_link == OFFICIAL_AWARDS_URL:
      return True
    text = f'{title} {self.html_text(html)}'
    return 'Splatterpunk Award nominees' in text

  def looks_like_category_heading(self, text):
    key = category_key(text)
    return key.startswith('best ') or any(
      fragment in key for fragment in EXCLUDED_CATEGORY_FRAGMENTS)

  def clean_category_label(self, label):
    label = clean_source_text(label)
    label = re.sub(r'\s*\([^)]*\)\s*$', '', label)
    return normalize_line(label.strip(' :'))

  def category_matches(self, label, category, category_aliases):
    label_key = category_key(self.clean_category_label(label))
    if any(fragment in label_key for fragment in EXCLUDED_CATEGORY_FRAGMENTS):
      return False
    return label_key in self.category_keys(category, category_aliases)

  def category_keys(self, category, category_aliases):
    aliases = {category, *(category_aliases or ())}
    keys = {category_key(alias) for alias in aliases if alias}
    keys.update(f'best {key}' for key in tuple(keys) if not key.startswith('best '))
    return keys

  def parsed_from_rows(self, name, base_url, rows, notes):
    rows = self.dedupe_rows(rows)
    by_year = {}
    for row in rows:
      year = str(row.get('award_year', ''))
      if not year:
        continue
      clean_row = dict(row)
      clean_row.pop('position', None)
      by_year.setdefault(year, []).append(clean_row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      year_rows = sorted(
        by_year[year],
        key=lambda row: 0 if row.get('result') == RESULT_WINNER else 1)
      entries.extend(assign_positions(
        year_rows, int(year), tied_winners_share_position=True))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=self.unique_notes(notes))

  def dedupe_rows(self, rows):
    ordered = []
    by_key = {}
    for row in rows:
      key = self.row_key(row)
      existing = by_key.get(key)
      if existing is None:
        by_key[key] = row
        ordered.append(row)
        continue
      if existing.get('result') != RESULT_WINNER and row.get('result') == RESULT_WINNER:
        existing.update(row)
    return ordered

  def row_key(self, row):
    return (
      str(row.get('award_year', '')),
      category_key(row.get('category', '')),
      category_key(row.get('title', '')),
      category_key(row.get('author', '')),
    )

  def unique_notes(self, notes):
    unique = []
    for note in notes:
      if note and note not in unique:
        unique.append(note)
    return unique
