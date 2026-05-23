#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Reusable Stop, You're Killing Me award parser base.

Maintenance notes:
- SYKM award pages are long text/link archives grouped by year and category,
  not table pages. Parse line boundaries first, then parse only configured
  category rows.
- The parser targets book categories. Person-only, short-story, and award
  navigation lines should be ignored unless a future recipe configures them
  deliberately.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, assign_positions, normalize_heading, normalize_line,
    strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    AwardParserBase, assign_positions, normalize_heading, normalize_line,
    strip_publication_notes,
  )
  from .generic import position_sort_key


RESULT_MARKERS = {
  '*': 'winner',
  '\u2217': 'winner',
  '\u00b0': 'nominee',
}
YEAR_HEADING = re.compile(r'^((?:19|20)\d{2})(?:\s+Nominees?)?$')
BLOCK_TAGS = {
  'address', 'article', 'aside', 'blockquote', 'body', 'dd', 'div', 'dl', 'dt',
  'fieldset', 'figcaption', 'figure', 'footer', 'form', 'h1', 'h2', 'h3', 'h4',
  'h5', 'h6', 'header', 'hr', 'li', 'main', 'nav', 'ol', 'p', 'pre', 'section',
  'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr', 'ul',
}


class StopYoureKillingMeAwardParserBase(AwardParserBase):
  """
  Parse SYKM award pages into the shared award import entry schema.

  Invariants:
  - Category headings are accepted only when they match the recipe category or
    aliases, so unrelated book/person/story categories do not leak.
  - Winner/nominee markers must start the row after whitespace cleanup.
  """

  AWARD_NAME = ''

  def parse(self, html, base_url, name, category, category_aliases=(),
            award_name=None):
    rows = self.parse_rows(html, base_url, category, category_aliases, award_name)
    entries = self.entries_from_rows(rows, award_name=award_name)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url, category, category_aliases=(),
                 award_name=None):
    soup = BeautifulSoup(html, 'html.parser')
    accepted_categories = self.accepted_category_headings(category, category_aliases)
    current_year = None
    current_category = None
    rows = []

    for fragment in self.line_fragments(soup):
      text = normalize_line(fragment['text'])
      if not text:
        continue
      year = self.year_from_heading(text)
      if year is not None:
        current_year = year
        current_category = None
        continue
      heading_category = self.category_from_heading(
        text, category, accepted_categories)
      if heading_category is not None:
        current_category = heading_category
        continue
      if self.looks_like_category_heading(text):
        current_category = None
        continue
      if current_year is None or current_category is None:
        continue
      row = self.parse_entry_line(fragment, base_url, current_year, current_category)
      if row is not None:
        if award_name:
          row['award'] = award_name
        rows.append(row)

    return self.dedupe_rows(rows)

  def line_fragments(self, soup):
    root = soup.body or soup
    fragments = []
    current = []

    def flush():
      text = normalize_line(''.join(
        item for item in current
        if isinstance(item, str)
      ))
      if text:
        fragments.append({'text': text, 'nodes': tuple(current)})
      current.clear()

    def append_text(value):
      current.append(re.sub(r'\s*\r?\n\s*', ' ', str(value)))

    def walk(node):
      if isinstance(node, NavigableString):
        append_text(node)
        return
      if not isinstance(node, Tag):
        return
      if node.name == 'br':
        flush()
        return
      if node.name in {'script', 'style'}:
        return
      started_with_content = bool(current)
      if node.name in BLOCK_TAGS and started_with_content:
        flush()
      for child in node.children:
        walk(child)
      if node.name in BLOCK_TAGS:
        flush()
      elif node.name == 'a':
        current.append(node)

    for child in root.children:
      walk(child)
    flush()
    return fragments

  def accepted_category_headings(self, category, category_aliases):
    return {
      normalize_heading(value)
      for value in (category, *category_aliases)
      if value
    }

  def year_from_heading(self, text):
    match = YEAR_HEADING.match(text or '')
    return int(match.group(1)) if match is not None else None

  def category_from_heading(self, text, category, accepted_categories):
    cleaned = self.clean_category_heading(text)
    normalized = normalize_heading(cleaned)
    if normalized in accepted_categories:
      return category
    return None

  def clean_category_heading(self, text):
    text = normalize_line(text)
    for marker in ('Lefty for Best ', 'Best '):
      index = text.find(marker)
      if index > 0 and text[:index].casefold().startswith('image'):
        text = text[index:]
        break
    text = re.sub(r'^\s*Image:?\s+', '', text, flags=re.I)
    return normalize_line(text)

  def looks_like_category_heading(self, text):
    normalized = normalize_heading(self.clean_category_heading(text))
    return (
      normalized.startswith('best ') or
      normalized.startswith('lefty for best ') or
      normalized.endswith(' award')
    )

  def parse_entry_line(self, fragment, base_url, year, category):
    text = normalize_line(fragment['text'])
    match = re.match(r'^\s*([*\u2217\u00b0])\s*(.+)$', text)
    if match is None:
      return None
    result = RESULT_MARKERS[match.group(1)]
    title, author = self.title_author_from_text(match.group(2))
    if not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': self.first_work_url(fragment, base_url) or base_url,
      'category': category,
    }

  def title_author_from_text(self, text):
    text = self.strip_review_tail(text)
    parts = re.split(r'\s+(?:edited\s+by|by)\s+', text, flags=re.I)
    if len(parts) < 2:
      return '', ''
    title = ' by '.join(parts[:-1])
    author = parts[-1]
    return self.clean_title(title), self.clean_author(author)

  def strip_review_tail(self, text):
    return re.sub(r'\s*\[\s*review\s*\]\s*$', '', text or '', flags=re.I).strip()

  def clean_title(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    value = self.strip_review_tail(value)
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def first_work_url(self, fragment, base_url):
    for node in fragment.get('nodes', ()):
      if not isinstance(node, Tag):
        continue
      links = node.find_all('a', href=True) if node.name != 'a' else [node]
      for link in links:
        text = normalize_heading(link.get_text(' ', strip=True))
        href = link.get('href', '')
        if text == 'review' or 'review' in href.casefold():
          continue
        return urljoin(base_url, href)
    return ''

  def dedupe_rows(self, rows):
    deduped = []
    seen = set()
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['category']),
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      if key in seen:
        continue
      seen.add(key)
      deduped.append(row)
    return deduped

  def entries_from_rows(self, rows, award_name=None):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      award_rows = [
        self.build_award_entry(
          row, row['source_url'], year, row['category'],
          award=row.get('award') or award_name or self.AWARD_NAME)
        for row in by_year[year]
      ]
      entries.extend(assign_positions(award_rows, int(year)))
    return entries
