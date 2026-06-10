#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Andrew Carnegie Medal for Excellence in Nonfiction parser.

Maintenance notes:
- ALA Carnegie pages mix fiction and nonfiction, and may expose winners,
  finalists, longlists, press-kit copy, reviews, and social assets together.
  Keep parsing bounded to nonfiction winner/finalist sections.
- V1 imports winners and finalists only. Longlists are intentionally ignored.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, RESULT_WINNER, assign_positions, normalize_heading,
    normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_WINNER, assign_positions, normalize_heading,
    normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key


AWARD_NAME = 'Andrew Carnegie Medal for Excellence in Nonfiction'
CATEGORY = 'Nonfiction'
RESULT_FINALIST = 'finalist'
RESULT_ORDER = {
  RESULT_WINNER: 0,
  RESULT_FINALIST: 1,
}


class AndrewCarnegieOfficialParser(AwardParserBase):
  """
  Parse official ALA Carnegie year pages.

  Accepted source shapes:
  - Current year pages with Nonfiction Winner/Finalists headings.
  - Older ALA blocks where author/title/publisher appear as adjacent lines.
  - Link/italic rows using "Title by Author" or "Title, Author" text.
  """

  AWARD_NAME = AWARD_NAME

  def parse(self, pages, base_url, name, category=CATEGORY):
    if isinstance(pages, (str, bytes)):
      pages = ((base_url, pages),)
    rows = []
    for page_url, page_html in pages:
      rows.extend(self.parse_rows(page_html, page_url, category))
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url, category):
    soup = BeautifulSoup(html or '', 'html.parser')
    rows = []
    for heading in self.nonfiction_result_headings(soup):
      result = self.result_from_heading(self.node_text(heading))
      if result is None:
        continue
      for node in self.section_nodes(heading):
        for item in self.row_nodes(node):
          row = self.row_from_node(item, base_url, category, result)
          if row is not None:
            rows.append(row)
    return rows

  def nonfiction_result_headings(self, soup):
    return [
      node for node in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong'])
      if self.is_nonfiction_result_heading(self.node_text(node))
    ]

  def is_nonfiction_result_heading(self, value):
    text = normalize_heading(value)
    return (
      'nonfiction' in text
      and not self.is_excluded_heading_text(text)
      and ('winner' in text or 'finalist' in text or 'shortlist' in text))

  def is_excluded_heading_text(self, text):
    return any(boundary in text for boundary in (
      'fiction',
      'longlist',
      'long list',
      'press kit',
      'resources',
      'social media',
    )) and 'nonfiction' not in text or any(boundary in text for boundary in (
      'nonfiction longlist',
      'nonfiction long list',
    ))

  def result_from_heading(self, value):
    text = normalize_heading(value)
    if 'winner' in text:
      return RESULT_WINNER
    if 'finalist' in text or 'shortlist' in text:
      return RESULT_FINALIST
    return None

  def section_nodes(self, heading):
    nodes = []
    for sibling in heading.next_siblings:
      if not isinstance(sibling, Tag):
        continue
      if self.is_boundary_heading(sibling):
        break
      nodes.append(sibling)
    return nodes

  def is_boundary_heading(self, node):
    if not self.is_heading_node(node):
      return False
    text = normalize_heading(self.node_text(node))
    if self.is_nonfiction_result_heading(text):
      return True
    return any(boundary in text for boundary in (
      'fiction',
      'longlist',
      'long list',
      'press kit',
      'resources',
      'social media',
      'about the',
    ))

  def is_heading_node(self, node):
    return (getattr(node, 'name', '') or '').lower() in {
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong'}

  def row_nodes(self, node):
    list_items = node.find_all('li', recursive=False)
    if list_items:
      return list_items
    cards = [
      child for child in node.find_all(['article', 'section', 'div'], recursive=False)
      if self.looks_like_work_card(child)
    ]
    return cards or [node]

  def looks_like_work_card(self, node):
    text = normalize_heading(self.node_text(node))
    return (
      bool(text)
      and not self.is_ignored_text(text)
      and (
        node.find(['a', 'em', 'i', 'h2', 'h3', 'h4']) is not None
        or ' by ' in text
        or 'author' in text))

  def row_from_node(self, node, base_url, category, result):
    text = self.clean_row_text(self.node_text(node))
    if self.is_ignored_text(text):
      return None
    year = self.year_from_text(base_url) or self.year_from_text(text)
    title, author = self.title_author_from_node(node)
    if not title or not author:
      title, author = self.title_author_from_text(text)
    if year is None or not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': self.clean_title(title),
      'author': self.clean_author(author),
      'result': result,
      'source_url': self.first_link_url(node, base_url) or base_url,
      'category': category,
    }

  def title_author_from_node(self, node):
    if not isinstance(node, Tag):
      return '', ''
    title_node = self.title_node(node)
    if title_node is not None:
      title = self.node_text(title_node)
      author = self.author_near_title(node, title_node, title)
      if author:
        return title, author
    lines = self.work_lines(node)
    return self.title_author_from_lines(lines)

  def title_node(self, node):
    candidates = node.find_all(['em', 'i', 'h2', 'h3', 'h4', 'a'])
    for candidate in candidates:
      text = self.clean_title(self.node_text(candidate))
      if text and not self.is_ignored_text(text) and not self.looks_like_author_line(text):
        return candidate
    return None

  def author_near_title(self, node, title_node, title):
    for line in self.work_lines(node):
      if normalize_heading(line) == normalize_heading(title):
        continue
      label, value = self.label_value(line)
      if label == 'author':
        return value
      by_match = re.search(r'\bby\s+(.+)$', line, re.I)
      if by_match is not None:
        return by_match.group(1)
    full_text = self.node_text(node)
    if title in full_text:
      after_title = full_text.split(title, 1)[1]
      return self.author_from_text_after_title(after_title)
    return ''

  def work_lines(self, node):
    lines = []
    for item in node.find_all(['h2', 'h3', 'h4', 'p', 'li', 'a', 'em', 'i'], recursive=True):
      text = self.clean_row_text(self.node_text(item))
      if not text or self.is_ignored_text(text):
        continue
      if lines and normalize_heading(lines[-1]) == normalize_heading(text):
        continue
      lines.append(text)
    if not lines:
      text = self.clean_row_text(self.node_text(node))
      if text and not self.is_ignored_text(text):
        lines.append(text)
    return lines

  def title_author_from_lines(self, lines):
    cleaned = [line for line in lines if line and not self.is_ignored_text(line)]
    for line in cleaned:
      title, author = self.title_author_from_text(line)
      if title and author:
        return title, author
    for index, line in enumerate(cleaned):
      label, value = self.label_value(line)
      if label == 'author':
        for other in cleaned[index + 1:] + cleaned[:index]:
          if not self.looks_like_author_line(other):
            return other, value
    if len(cleaned) >= 2:
      if self.looks_like_author_line(cleaned[0]):
        return cleaned[1], self.strip_author_label(cleaned[0])
      return cleaned[0], self.strip_author_label(cleaned[1])
    return '', ''

  def title_author_from_text(self, value):
    text = strip_publication_notes(self.strip_result_prefix(value))
    text = re.sub(r'^\s*(?:\d{4}\s*)+', '', text).strip()
    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', text, re.I)
    if by_match is not None:
      return by_match.group(1).strip(), self.author_before_publisher(by_match.group(2))
    for separator in (' | ', ' - ', ' \u2013 ', ' \u2014 '):
      if separator in text:
        title, author = text.split(separator, 1)
        return title.strip(), self.author_before_publisher(author)
    if ',' in text:
      title, author = text.rsplit(',', 1)
      if self.looks_like_author_fragment(author):
        return title.strip(), author.strip()
    return '', ''

  def author_from_text_after_title(self, value):
    text = normalize_line(value).strip(' ,:-\u2013\u2014|')
    text = re.sub(r'^\s*by\s+', '', text, flags=re.I)
    return self.author_before_publisher(text)

  def author_before_publisher(self, value):
    text = normalize_line(value)
    text = re.sub(r'\s*\([^()]*\)\s*$', '', text).strip()
    if ',' in text:
      author, _publisher = text.rsplit(',', 1)
      return author.strip()
    return text.strip()

  def looks_like_author_fragment(self, value):
    text = normalize_line(value).strip()
    normalized = normalize_heading(text)
    if not text or normalized.startswith(('and ', 'the ', 'a ', 'an ')):
      return False
    if any(value in normalized for value in (
        'publisher',
        'press',
        'books',
        'company',
        'inc',
        'memoir',
        'history',
        'america')):
      return False
    return len(text.split()) <= 6

  def label_value(self, text):
    match = re.match(r'^\s*([A-Za-z ]+)\s*:\s*(.+)$', text or '')
    if match is None:
      return '', text
    return normalize_heading(match.group(1)), match.group(2).strip()

  def looks_like_author_line(self, value):
    text = normalize_line(value)
    return bool(re.match(r'^(?:by\s+|author\s*:)', text, re.I))

  def strip_author_label(self, value):
    text = normalize_line(value)
    text = re.sub(r'^\s*author\s*:\s*', '', text, flags=re.I)
    text = re.sub(r'^\s*by\s+', '', text, flags=re.I)
    return text

  def strip_result_prefix(self, value):
    return re.sub(
      r'^\s*(?:winner|finalists?|shortlist(?:ed)?)\s*:?\s*',
      '',
      value or '',
      flags=re.I).strip()

  def is_ignored_text(self, value):
    text = normalize_heading(value)
    if not text:
      return True
    return any(ignored in text for ignored in (
      'no medal was awarded',
      'read the booklist review',
      'booklist review',
      'learn more',
      'download',
      'press kit',
      'social media',
      'about the andrew carnegie',
      'longlist',
      'long list',
    ))

  def clean_row_text(self, value):
    text = normalize_line(value)
    text = re.sub(r'\s*\[\s*\d+\s*\]\s*', ' ', text)
    return normalize_line(text)

  def clean_title(self, value):
    text = strip_publication_notes(normalize_line(value))
    text = re.sub(r'^\s*(?:winner|finalist)\s*:?\s*', '', text, flags=re.I)
    return text.strip(' "\u201c\u201d,')

  def clean_author(self, value):
    text = self.strip_author_label(value)
    text = re.sub(r'\s*,?\s*(?:translated|translation|edited|ed\.?|eds?\.?)\b.*$', '', text, flags=re.I)
    return strip_publication_notes(text).strip(' "\u201c\u201d,')

  def first_link_url(self, node, base_url):
    if not isinstance(node, Tag):
      return ''
    link = node.find('a', href=True)
    return urljoin(base_url, link['href']) if link is not None else ''

  def node_text(self, node):
    if node is None:
      return ''
    if isinstance(node, Tag):
      return normalize_line(node.get_text(' ', strip=True))
    return normalize_line(str(node))

  def year_from_text(self, value):
    match = re.search(r'(19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def dedupe_rows(self, rows):
    best_by_key = {}
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['category']),
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      current = best_by_key.get(key)
      if current is None or RESULT_ORDER.get(row['result'], 99) < RESULT_ORDER.get(current['result'], 99):
        best_by_key[key] = row
    return list(best_by_key.values())

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      award_rows = sorted(
        by_year[year],
        key=lambda row: RESULT_ORDER.get(row.get('result'), 99))
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in award_rows
      ]
      entries.extend(assign_positions(
        award_rows,
        int(year),
        tied_winners_share_position=True))
    return entries
