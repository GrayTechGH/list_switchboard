#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Macavity Award parser for the Mystery Readers International awards page.

Maintenance notes:
- The official page groups one long archive by award year, then category. The
  winner is the first work line after each category heading; nominee rows are
  list items.
- Official rows use "Author: Title (publisher)" order. LibraryThing fallback
  keeps using the shared LibraryThing award parser because its rows use the
  normal "Title by Author" shape.
"""

import re

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


AWARD_NAME = 'Macavity Award'
YEAR_HEADING = re.compile(r'^((?:19|20)\d{2})$')
BLOCK_TAGS = {
  'address', 'article', 'aside', 'blockquote', 'body', 'dd', 'div', 'dl', 'dt',
  'fieldset', 'figcaption', 'figure', 'footer', 'form', 'h1', 'h2', 'h3', 'h4',
  'h5', 'h6', 'header', 'hr', 'li', 'main', 'nav', 'ol', 'p', 'pre', 'section',
  'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr', 'ul',
}


class MacavityAwardsParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def parse(self, html, base_url, name, category, category_aliases=()):
    rows = self.parse_rows(html, base_url, category, category_aliases)
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, source_url, category, category_aliases=()):
    soup = BeautifulSoup(html, 'html.parser')
    accepted_categories = self.accepted_category_headings(category, category_aliases)
    current_year = None
    current_category = None
    category_index = 0
    rows = []

    for fragment in self.line_fragments(soup):
      text = normalize_line(fragment['text'])
      if not text:
        continue
      if fragment['tag'] == 'h3':
        current_year = self.year_from_heading(text)
        current_category = None
        category_index = 0
        continue
      if fragment['tag'] == 'h4':
        heading_category = self.category_from_heading(text, category, accepted_categories)
        current_category = heading_category
        category_index = 0
        continue
      if current_year is None or current_category is None:
        continue
      if self.looks_like_category_heading(text):
        current_category = None
        category_index = 0
        continue
      row = self.parse_entry_line(
        text,
        source_url,
        current_year,
        current_category,
        'winner' if category_index == 0 else 'nominee')
      if row is not None:
        rows.append(row)
        category_index += 1

    return self.dedupe_rows(rows)

  def line_fragments(self, soup):
    root = soup.body or soup
    fragments = []
    current = []
    current_tag = ''

    def flush():
      nonlocal current_tag
      text = normalize_line(''.join(current))
      if text:
        fragments.append({'text': text, 'tag': current_tag})
      current.clear()
      current_tag = ''

    def append_text(value, tag_name=''):
      nonlocal current_tag
      if tag_name and not current_tag:
        current_tag = tag_name
      current.append(re.sub(r'\s*\r?\n\s*', ' ', str(value)))

    def walk(node, block_name=''):
      if isinstance(node, NavigableString):
        append_text(node, block_name)
        return
      if not isinstance(node, Tag):
        return
      if node.name in {'script', 'style'}:
        return
      if node.name == 'br':
        flush()
        return
      tag_name = node.name if node.name in BLOCK_TAGS else block_name
      if node.name in BLOCK_TAGS and current:
        flush()
      for child in node.children:
        walk(child, tag_name)
      if node.name in BLOCK_TAGS:
        flush()

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
    cleaned = normalize_line((text or '').rstrip(':'))
    if normalize_heading(cleaned) in accepted_categories:
      return category
    return None

  def looks_like_category_heading(self, text):
    normalized = normalize_heading((text or '').rstrip(':'))
    return normalized.startswith('best ') or normalized.startswith('sue feder ')

  def parse_entry_line(self, text, source_url, year, category, result):
    title, author = self.title_author_from_text(text)
    if not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': source_url,
      'category': category,
    }

  def title_author_from_text(self, text):
    text = normalize_line(text).lstrip('*').strip()
    if ':' not in text:
      return '', ''
    author, title = text.split(':', 1)
    return self.clean_title(title), self.clean_author(author)

  def clean_title(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    value = normalize_line(value)
    value = re.sub(r'\s*,?\s*editors?$', '', value, flags=re.I)
    value = re.sub(r'\s*,?\s*eds?\.?$', '', value, flags=re.I)
    return strip_publication_notes(value).strip(' "\u201c\u201d,')

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

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in by_year[year]
      ]
      entries.extend(assign_positions(award_rows, int(year)))
    return entries


def parse_macavity_awards(html, base_url, name, category, category_aliases=()):
  return MacavityAwardsParser().parse(
    html,
    base_url,
    name,
    category,
    category_aliases=category_aliases)
