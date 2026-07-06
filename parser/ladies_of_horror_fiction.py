#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Ladies of Horror Fiction Awards parser.

Maintenance notes:
- Goodreads is the V1 primary source because it exposes the most stable
  machine-readable winner and nominee rows for this award.
- Goodreads labels non-winner rows as nominees. The plugin imports those rows
  as `shortlisted`, but this is Goodreads nominee coverage, not an official
  consolidated shortlist archive.
- File 770's 2021 winners post is a narrow winner-correction supplement only;
  it must not be treated as a shortlist source.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, UnicodeDammit

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key


AWARD_NAME = 'Ladies of Horror Fiction Award'
GOODREADS_URL = (
  'https://www.goodreads.com/award/show/35484-ladies-of-horror-fiction-award')
FILE770_2021_WINNERS_URL = (
  'https://file770.com/2021-ladies-of-horror-fiction-awards/')

ALL_CATEGORIES = {
  'collection': ('collection', 'best collection'),
  'debut': ('debut', 'best debut'),
  'graphic novel': ('graphic novel', 'best graphic novel'),
  'middle grade': ('middle grade', 'best middle grade'),
  'novel': ('novel', 'best novel'),
  'novella': ('novella', 'best novella'),
  'poetry collection': ('poetry', 'best poetry', 'poetry collection',
                        'best poetry collection'),
  'young adult': ('young adult', 'best young adult'),
}

EXCLUDED_CATEGORY_KEYS = {
  'short fiction',
  'best short fiction',
}


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


class LadiesOfHorrorFictionParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def parse_goodreads(self, html, base_url, name, category, category_aliases=()):
    notes = [
      'Goodreads is the V1 primary source for LOHF winners and nominees.',
      'Goodreads nominee rows are imported as shortlisted rows; this is not an '
      'official consolidated shortlist archive.',
      'Public parseable coverage is source-limited, with strongest coverage '
      'for 2019-2021; no 2022+ rows are invented.',
    ]
    soup = BeautifulSoup(self.decode_source(html), 'html.parser')
    rows = []
    rows.extend(self.goodreads_table_rows(soup, base_url, category, category_aliases))
    rows.extend(self.goodreads_line_rows(
      soup, base_url, category, category_aliases, start_order=len(rows)))
    if not rows:
      notes.append(f'No Goodreads LOHF rows were parsed for {category}.')
    return self.parsed_from_rows(name, base_url, rows, notes)

  def parse_file770_winners(
      self, html, base_url, name, category, category_aliases=()):
    notes = [
      'File 770 2021 LOHF winner mirror is used only to promote or append '
      'winner rows; it is not a shortlist source.',
    ]
    soup = BeautifulSoup(self.decode_source(html), 'html.parser')
    rows = []
    current_category = ''
    current_source_url = base_url
    for node in soup.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'li', 'a']):
      text = self.node_text(node)
      if not text:
        continue
      heading_category = self.category_from_official_heading(text)
      if heading_category:
        current_category = heading_category
        current_source_url = self.first_link_url(node, base_url) or base_url
        continue
      if not current_category or not self.category_matches(
          current_category, category, category_aliases):
        continue
      if self.skip_file770_work_line(text):
        continue
      parsed = self.parse_work_text(text)
      if parsed is None:
        continue
      rows.append(self.build_award_entry(
        {
          'title': parsed[0],
          'author': parsed[1],
          'result': RESULT_WINNER,
          '_source_order': len(rows),
        },
        current_source_url,
        2021,
        category))
    return self.parsed_from_rows(name, base_url, rows, notes)

  def combine_results(self, name, base_url, *parsed_results):
    rows = []
    notes = [
      'Ladies of Horror Fiction uses Goodreads as the primary source and a '
      'narrow File 770 2021 winner correction.',
      'Shortlisted rows are Goodreads nominee rows where present, not guaranteed '
      'complete official shortlists.',
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
      if 'award/show/35484-ladies-of-horror-fiction-award' not in href:
        continue
      if 'page=' not in href and not text.isdigit():
        continue
      url = urljoin(base_url, href)
      if url not in urls:
        urls.append(url)
    return tuple(urls)

  def goodreads_table_rows(self, soup, base_url, category, category_aliases):
    rows = []
    for book_row in soup.find_all('tr'):
      if 'Book' not in (book_row.get('itemtype') or ''):
        continue
      title_node = book_row.find(class_='bookTitle')
      author_node = book_row.find(class_='authorName')
      if title_node is None or author_node is None:
        continue
      title = self.clean_title(title_node.get_text(' ', strip=True))
      author = self.clean_author(author_node.get_text(' ', strip=True))
      if not title or not author:
        continue
      labels = self.goodreads_label_texts(book_row)
      for label in labels:
        parsed_label = self.parse_goodreads_label(label, category, category_aliases)
        if parsed_label is None:
          continue
        year, result = parsed_label
        rows.append(self.build_award_entry(
          {
            'title': title,
            'author': author,
            'result': result,
            '_source_order': len(rows),
          },
          self.first_link_url(title_node, base_url) or base_url,
          year,
          category))
    return rows

  def goodreads_label_texts(self, node):
    labels = []
    for label_node in node.find_all('i'):
      text = self.node_text(label_node)
      if 'Ladies of Horror Fiction Award' in text:
        labels.append(text)
    for text_node in node.find_all(string=True):
      text = clean_source_text(str(text_node))
      if 'Ladies of Horror Fiction Award' in text and text not in labels:
        labels.append(text)
    return labels

  def goodreads_line_rows(
      self, soup, base_url, category, category_aliases, start_order=0):
    rows = []
    lines = self.goodreads_lines(soup)
    previous_label_index = -1
    for index, line in enumerate(lines):
      parsed_label = self.parse_goodreads_label(line, category, category_aliases)
      if parsed_label is None:
        continue
      year, result = parsed_label
      work = self.goodreads_work_from_buffer(lines[previous_label_index + 1:index])
      previous_label_index = index
      if work is None:
        continue
      rows.append(self.build_award_entry(
        {
          'title': self.clean_title(work[0]),
          'author': self.clean_author(work[1]),
          'result': result,
          '_source_order': start_order + len(rows),
        },
        base_url,
        year,
        category))
    return rows

  def parse_goodreads_label(self, label, category, category_aliases):
    match = re.match(
      r'^Ladies\s+of\s+Horror\s+Fiction\s+Award\s+'
      r'(Nominee\s+)?for\s+(.+?)\s*\(((?:19|20)\d{2})\)$',
      clean_source_text(label),
      re.I)
    if match is None:
      return None
    source_category = self.clean_category_label(match.group(2))
    if source_category is None:
      return None
    if not self.category_matches(source_category, category, category_aliases):
      return None
    result = RESULT_SHORTLISTED if match.group(1) else RESULT_WINNER
    return int(match.group(3)), result

  def category_from_official_heading(self, text):
    key = category_key(text)
    if 'award for' not in key:
      return ''
    candidates = []
    for canonical, aliases in ALL_CATEGORIES.items():
      candidates.extend(
        (canonical, category_key(alias))
        for alias in aliases
        if alias)
    for canonical, alias_key in sorted(
        candidates, key=lambda item: len(item[1]), reverse=True):
      if re.search(rf'\b{re.escape(alias_key)}\b', key):
        return canonical
    return ''

  def category_matches(self, label, category, category_aliases):
    label_category = self.clean_category_label(label)
    if label_category is None:
      return False
    aliases = {category, *(category_aliases or ())}
    alias_keys = {
      self.clean_category_label(alias)
      for alias in aliases
      if alias
    }
    return label_category in alias_keys

  def clean_category_label(self, label):
    key = category_key(label)
    key = re.sub(r'^best\s+', '', key)
    if key in EXCLUDED_CATEGORY_KEYS:
      return None
    if key in ('poetry', 'poetry collection'):
      return 'poetry collection'
    for canonical, aliases in ALL_CATEGORIES.items():
      if key == canonical or key in {category_key(alias) for alias in aliases}:
        return canonical
    return key

  def parse_work_text(self, text):
    text = self.clean_work_text(text)
    match = re.match(r'^(.+?)\s+by\s+(.+)$', text, re.I)
    if match is None:
      return None
    title = self.clean_title(match.group(1))
    author = self.clean_author(match.group(2))
    if not title or not author:
      return None
    return title, author

  def clean_work_text(self, text):
    text = clean_source_text(text)
    text = re.sub(r'^\s*(?:[-*]|\u2022|[·])+\s*', '', text)
    text = re.sub(r'^\s*\[?\s*TIE\s*\]?\s*', '', text, flags=re.I)
    return text.strip(' "\'.,;')

  def skip_file770_work_line(self, text):
    key = category_key(text)
    return (
      not key or
      key in {'tie', 'share this', 'like this'} or
      key.startswith('discover more') or
      key.startswith('posted on') or
      'award for' in key)

  def goodreads_work_from_buffer(self, lines):
    lines = [line for line in lines if not self.is_goodreads_noise(line)]
    if not lines:
      return None
    by_indexes = [
      index for index, line in enumerate(lines)
      if category_key(line) == 'by'
    ]
    if by_indexes:
      by_index = by_indexes[-1]
      title = self.previous_goodreads_line(lines, by_index)
      author = self.next_goodreads_line(lines, by_index)
      if title and author:
        return title, author
    if len(lines) >= 2:
      return lines[-2], lines[-1]
    return None

  def previous_goodreads_line(self, lines, index):
    for line in reversed(lines[:index]):
      if not self.is_goodreads_noise(line):
        return line
    return ''

  def next_goodreads_line(self, lines, index):
    for line in lines[index + 1:]:
      if not self.is_goodreads_noise(line):
        return line
    return ''

  def is_goodreads_noise(self, line):
    key = category_key(line)
    if not key:
      return True
    return (
      key in {'winners', 'winner', 'nominees', 'nominee', 'by'} or
      key.startswith('score ') or
      key.startswith('rating ') or
      key.startswith('avg rating') or
      'ratings' in key or
      'want to read' in key or
      'rate this book' in key or
      'error rating book' in key or
      'clear rating' in key or
      'currently reading' in key or
      'did not finish' in key)

  def goodreads_lines(self, soup):
    for removable in soup.find_all(['script', 'style']):
      removable.decompose()
    text = soup.get_text('\n')
    return [
      clean_source_text(line)
      for line in text.splitlines()
      if clean_source_text(line)
    ]

  def decode_source(self, source):
    if isinstance(source, bytes):
      return UnicodeDammit(source).unicode_markup
    return source or ''

  def node_text(self, node):
    return clean_source_text(node.get_text(' ', strip=True))

  def first_link_url(self, node, base_url):
    link = node if getattr(node, 'name', None) == 'a' else node.find('a', href=True)
    return urljoin(base_url, link['href']) if link is not None and link.get('href') else ''

  def clean_title(self, value):
    value = strip_publication_notes(clean_source_text(value))
    return value.strip(' "\'.,;')

  def clean_author(self, value):
    value = clean_source_text(value)
    value = re.sub(r'^\s*by\s+', '', value, flags=re.I)
    value = re.sub(r'\s*\((?:Goodreads Author|Author|Editor|Editors?)\)\s*',
                   ' ', value, flags=re.I)
    return strip_publication_notes(value).strip(' "\'.,;')

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
        key=lambda row: (
          0 if row.get('result') == RESULT_WINNER else 1,
          row.get('_source_order', 0)))
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
