#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
This Is Horror Awards parser for official WordPress pages plus Goodreads.

Maintenance notes:
- Official This Is Horror pages expose the current ballot and winner posts, but
  historical winner posts usually include winners plus runner-up rows rather
  than complete shortlists.
- Goodreads is intentionally a live historical nominee supplement for V1.
- Award years must come from award titles/content, not WordPress publication
  dates, because winner posts can lag the award year.
"""

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, UnicodeDammit

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, split_title_author,
    strip_editor_marker, strip_publication_notes, strip_square_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, split_title_author,
    strip_editor_marker, strip_publication_notes, strip_square_notes,
  )
  from .generic import position_sort_key


AWARD_NAME = 'This Is Horror Award'
OFFICIAL_AWARDS_URL = 'https://www.thisishorror.co.uk/awards/'
OFFICIAL_AWARDS_API_URL = (
  'https://www.thisishorror.co.uk/wp-json/wp/v2/pages?slug=awards')
OFFICIAL_WINNERS_SEARCH_API_URL = (
  'https://www.thisishorror.co.uk/wp-json/wp/v2/search?'
  'search=This%20Is%20Horror%20Awards%20Winners&per_page=20')
GOODREADS_URL = 'https://www.goodreads.com/award/show/23539-this-is-horror-award'

YEAR_RE = re.compile(r'(?:19|20)\d{2}')
SEMANTIC_TAGS = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li')

CATEGORY_BOUNDARIES = frozenset({
  'anthology',
  'anthology of the year',
  'best anthology',
  'best novel',
  'best novella',
  'chapbook',
  'comic',
  'comic graphic novel',
  'cover art',
  'event',
  'fiction magazine',
  'fiction podcast',
  'film',
  'graphic novel',
  'magazine',
  'novel',
  'novel of the year',
  'nonfiction podcast',
  'non fiction podcast',
  'publisher',
  'short fiction',
  'short fiction of the year',
  'short story collection',
  'short story collection of the year',
  'soundtrack',
  'tv',
  'television',
  'video game',
})

EXCLUDED_CATEGORY_FRAGMENTS = (
  'artist',
  'chapbook',
  'comic',
  'cover art',
  'event',
  'film',
  'graphic novel',
  'magazine',
  'podcast',
  'publisher',
  'short fiction',
  'soundtrack',
  'tattoo',
  'television',
  'tv',
  'video game',
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


class ThisIsHorrorParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def parse_official_current(
      self, source, base_url, name, category, category_aliases=()):
    rows = []
    notes = [
      'Official This Is Horror awards page exposes the current ballot as '
      'shortlisted rows.',
      'As of July 5, 2026, the official awards page still exposes the 2024 '
      'ballot and no official 2025 ballot or winners page was found.',
    ]
    for html, title, link in self.official_current_documents(source):
      year = self.award_year(html, title)
      current_category = None
      target_category = False
      for node in self.semantic_nodes(html):
        text = self.node_text(node)
        if not text:
          continue
        if node.name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
          if category_key(text).startswith('previous winners'):
            current_category = None
            target_category = False
            continue
          current_category = self.clean_category_label(text)
          target_category = self.category_matches(
            current_category, category, category_aliases)
          continue
        if node.name != 'li' or not target_category or year is None:
          continue
        parsed = self.parse_work_text(text, RESULT_SHORTLISTED)
        if parsed is None:
          notes.append(
            f'Official current ballot {year} {category} row could not be '
            f'parsed: {text}')
          continue
        rows.append(self.build_award_entry(
          parsed,
          self.first_link_url(node, link or base_url) or link or base_url,
          year,
          category))
      if year is None:
        notes.append('Official current ballot award year could not be determined.')
    return self.parsed_from_rows(name, base_url, rows, notes)

  def parse_official_winners(
      self, source, base_url, name, category, category_aliases=()):
    rows = []
    notes = [
      'Official This Is Horror winner posts usually expose winners and '
      'runner-ups, not complete historical shortlists.',
    ]
    runner_up_found = False
    for html, title, link in self.source_documents(source):
      year = self.award_year(html, title)
      current_category = None
      target_category = False
      for node in self.semantic_nodes(html):
        text = self.node_text(node)
        if not text:
          continue
        if node.name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
          current_category = self.clean_category_label(text)
          target_category = self.category_matches(
            current_category, category, category_aliases)
          continue
        if not target_category or year is None:
          continue
        for result_label, work_text in self.result_segments(text):
          result = (
            RESULT_WINNER if result_label == 'winner' else RESULT_SHORTLISTED)
          runner_up_found = runner_up_found or result_label == 'runner-up'
          parsed = self.parse_work_text(work_text, result)
          if parsed is None:
            notes.append(
              f'Official winners post {year} {category} row could not be '
              f'parsed: {work_text}')
            continue
          rows.append(self.build_award_entry(
            parsed,
            self.first_link_url(node, link or base_url) or link or base_url,
            year,
            category))
      if year is None and self.looks_like_awards_document(title, html):
        notes.append(f'Official winners page has no parseable award year: {title}')
    if runner_up_found:
      notes.append(
        'Official This Is Horror runner-up rows are imported as shortlisted '
        'rows; they are not full historical shortlists.')
    return self.parsed_from_rows(name, base_url, rows, notes)

  def parse_goodreads(self, html, base_url, name, category, category_aliases=()):
    rows = []
    notes = [
      'Goodreads is used as the V1 historical nominee/finalist supplement; '
      'official This Is Horror winner rows are preferred when they overlap.',
    ]
    lines = self.goodreads_lines(html)
    previous_label_index = -1
    for index, line in enumerate(lines):
      parsed_label = self.parse_goodreads_label(line, category, category_aliases)
      if parsed_label is None:
        continue
      year, result = parsed_label
      work = self.goodreads_work_from_buffer(lines[previous_label_index + 1:index])
      previous_label_index = index
      if work is None:
        notes.append(f'Goodreads {year} {category} row could not be parsed.')
        continue
      title, author = work
      rows.append(self.build_award_entry(
        {
          'title': self.clean_title(title),
          'author': self.clean_author(author),
          'result': result,
        },
        base_url,
        year,
        category))
    return self.parsed_from_rows(name, base_url, rows, notes)

  def combine_results(self, name, base_url, *parsed_results):
    rows = []
    notes = [
      'This Is Horror official sources provide current ballot rows and winner '
      'posts; Goodreads supplies historical nominee supplementation.',
      'If neither official nor Goodreads sources expose a category/year '
      'shortlist, no shortlist rows are invented.',
    ]
    for parsed in parsed_results:
      if not parsed:
        continue
      notes.extend(parsed.get('notes', ()))
      rows.extend(dict(entry) for entry in parsed.get('entries', ()))
    return self.parsed_from_rows(name, base_url, rows, notes)

  def discover_winner_api_urls(self, source):
    urls = []
    text = self.decode_source(source)
    parsed = self.parse_json_source(text)
    if not isinstance(parsed, list):
      return tuple(urls)
    for item in parsed:
      if not isinstance(item, dict):
        continue
      title = self.html_text(item.get('title') or '')
      if not self.looks_like_winners_title(title):
        continue
      href = self.first_self_href(item)
      if href and href not in urls:
        urls.append(href)
    return tuple(urls)

  def parse_work_text(self, text, result):
    text = self.clean_work_text(text)
    if not text:
      return None
    parsed = self.parse_edited_by(text)
    if parsed is None:
      parsed = self.parse_by(text)
    if parsed is None:
      parsed = self.parse_dash(text)
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

  def parse_dash(self, text):
    match = re.match(r'^(.*?)\s+[-]\s+(.+)$', text)
    if match is None:
      return None
    return match.group(1), match.group(2)

  def parse_comma(self, text):
    title, author = split_title_author(text)
    if title and author:
      return title, author
    return None

  def clean_work_text(self, text):
    text = strip_square_notes(clean_source_text(text))
    text = re.sub(r'^\s*(?:winner|runner-up|runner up|nominee|finalist)s?\s*:\s*',
                  '', text, flags=re.I)
    text = re.sub(r'^\s*(?:[-*]|\u2022)\s*', '', text)
    text = re.sub(r'\s*\((?:winner|runner-up|runner up|finalist)\)\s*$',
                  '', text, flags=re.I)
    return normalize_line(text.strip(' "\'.,;'))

  def clean_title(self, value):
    value = strip_publication_notes(clean_source_text(value))
    value = re.sub(r'\s*,?\s*published\s+by\s+.+$', '', value, flags=re.I)
    return value.strip(' "\'.,;')

  def clean_author(self, value):
    value = clean_source_text(value)
    value = re.sub(r'^\s*(?:by|edited\s+by)\s+', '', value, flags=re.I)
    value = re.sub(r'\s*\((?:Goodreads Author|Author|Editor|Editors?)\)\s*',
                   ' ', value, flags=re.I)
    value = re.sub(r'\s*,?\s*(?:eds?|editors?)\.?$', '', value, flags=re.I)
    return strip_editor_marker(strip_publication_notes(value)).strip(' "\'.,;')

  def result_segments(self, text):
    matches = list(re.finditer(r'\b(Winner|Runner-?up)\s*:\s*', text, re.I))
    if not matches:
      return []
    segments = []
    for index, match in enumerate(matches):
      end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
      label = category_key(match.group(1)).replace('runner up', 'runner-up')
      work_text = clean_source_text(text[match.end():end]).strip(' .;')
      if work_text:
        segments.append((label, work_text))
    return segments

  def parse_goodreads_label(self, line, category, category_aliases):
    match = re.match(
      r'^This\s+is\s+Horror\s+Award\s+(Nominee\s+)?for\s+(.+?)\s*'
      r'(?:\((?:finalist|runner-up|runner up|nominee)\))?\s*\(((?:19|20)\d{2})\)$',
      line,
      re.I)
    if match is None:
      return None
    if not self.category_matches(match.group(2), category, category_aliases):
      return None
    result = RESULT_SHORTLISTED if match.group(1) else RESULT_WINNER
    return int(match.group(3)), result

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
      key in {'winners', 'nominees', 'winner', 'nominee', 'finalist'} or
      key.startswith('score ') or
      key.startswith('rating ') or
      key.startswith('avg rating') or
      'ratings' in key or
      'want to read' in key or
      'rate this book' in key)

  def official_current_documents(self, source):
    documents = []
    for html, title, link in self.source_documents(source):
      if self.is_official_awards_page(title, link, html):
        documents.append((html, title, link))
    return tuple(documents)

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
      title = item.get('title') or item.get('title_text') or ''
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

  def goodreads_lines(self, html):
    soup = BeautifulSoup(self.decode_source(html), 'html.parser')
    for removable in soup.find_all(['script', 'style']):
      removable.decompose()
    text = soup.get_text('\n')
    return [
      clean_source_text(line)
      for line in text.splitlines()
      if clean_source_text(line)
    ]

  def node_text(self, node):
    return clean_source_text(node.get_text(' ', strip=True))

  def html_text(self, html):
    return clean_source_text(
      BeautifulSoup(self.decode_source(html), 'html.parser').get_text(' ', strip=True))

  def award_year(self, html, title=''):
    for value in (title, self.html_text(html)):
      match = re.search(r'This\s+Is\s+Horror\s+Awards?\s+((?:19|20)\d{2})',
                        value, re.I)
      if match is not None:
        return int(match.group(1))
    match = YEAR_RE.search(title or '')
    return int(match.group(0)) if match is not None else None

  def first_self_href(self, item):
    links = item.get('_links') or {}
    self_links = links.get('self') if isinstance(links, dict) else None
    if isinstance(self_links, list) and self_links:
      href = self_links[0].get('href') if isinstance(self_links[0], dict) else ''
      if href:
        return href
    return item.get('url') or item.get('link') or ''

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True)
    return urljoin(base_url, link['href']) if link is not None else ''

  def is_official_awards_page(self, title, link, html):
    normalized_link = (link or '').rstrip('/') + '/' if link else ''
    if normalized_link == OFFICIAL_AWARDS_URL:
      return True
    text = f'{title} {self.html_text(html)}'
    return (
      'This Is Horror Awards' in text and
      'Previous Winners' in text and
      'ballot' in text.casefold())

  def looks_like_winners_title(self, title):
    key = category_key(title)
    return 'this is horror awards' in key and 'winner' in key

  def looks_like_awards_document(self, title, html):
    text = f'{title} {self.html_text(html)}'
    return 'This Is Horror Awards' in text

  def clean_category_label(self, label):
    label = clean_source_text(label)
    label = re.sub(r'\s*\([^)]*\)\s*$', '', label)
    return normalize_line(label.strip(' :'))

  def category_matches(self, label, category, category_aliases):
    label_key = category_key(self.clean_category_label(label))
    if any(fragment in label_key for fragment in EXCLUDED_CATEGORY_FRAGMENTS):
      return False
    aliases = {category, *(category_aliases or ())}
    alias_keys = {category_key(alias) for alias in aliases if alias}
    if label_key in alias_keys:
      return True
    normalized = label_key.replace(' of the year', '')
    return normalized in alias_keys

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
