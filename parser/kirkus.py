#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Kirkus Prize parsers.

Maintenance notes:
- Kirkus year pages mix Fiction, Nonfiction, and Young Readers' Literature in
  shared winner/finalist sections. Keep rows bounded to the configured category
  aliases so sibling prize categories do not leak into a recipe.
- V1 imports winners and finalists only. Prize rules, jurors, and article/news
  validation pages are intentionally out of import scope.
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


AWARD_NAME = 'Kirkus Prize'
RESULT_FINALIST = 'finalist'
RESULT_ORDER = {
  RESULT_WINNER: 0,
  RESULT_FINALIST: 1,
}


class KirkusPrizeParser(AwardParserBase):
  """
  Parse official Kirkus Prize year pages.

  Accepted source shapes:
  - Year pages with Winners and Finalists sections.
  - Category headings followed by linked title cards and byline text.
  - Compact rows using "Title by Author" text.
  """

  AWARD_NAME = AWARD_NAME

  def parse(self, pages, base_url, name, category, category_aliases=()):
    if isinstance(pages, (str, bytes)):
      pages = ((base_url, pages),)
    aliases = self.normalized_category_aliases(category, category_aliases)
    rows = []
    for page_url, page_html in pages:
      rows.extend(self.parse_rows(page_html, page_url, category, aliases))
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url, category, category_aliases):
    soup = BeautifulSoup(html or '', 'html.parser')
    rows = []
    for heading in self.result_headings(soup):
      result = self.result_from_heading(self.node_text(heading))
      current_category = ''
      for node in self.section_nodes(heading):
        node_category = self.category_from_heading(node, category_aliases)
        if node_category:
          current_category = node_category
          continue
        nested_rows, current_category = self.rows_from_node(
          node,
          base_url,
          category,
          category_aliases,
          current_category,
          result)
        rows.extend(nested_rows)
    return rows

  def result_headings(self, soup):
    return [
      node for node in soup.find_all(['h1', 'h2', 'h3'])
      if self.result_from_heading(self.node_text(node)) is not None
    ]

  def result_from_heading(self, value):
    text = normalize_heading(value)
    if 'finalist' in text:
      return RESULT_FINALIST
    if 'winner' in text:
      return RESULT_WINNER
    return None

  def section_nodes(self, heading):
    nodes = []
    for sibling in heading.next_siblings:
      if not isinstance(sibling, Tag):
        continue
      if self.is_result_boundary(sibling):
        break
      nodes.append(sibling)
    return nodes

  def is_result_boundary(self, node):
    return (
      self.is_heading_node(node)
      and self.result_from_heading(self.node_text(node)) is not None)

  def rows_from_node(
      self, node, base_url, category, category_aliases, current_category, result):
    rows = []
    if self.is_heading_node(node):
      node_category = self.category_from_heading(node, category_aliases)
      return rows, node_category or current_category
    for child in node.find_all(['h3', 'h4', 'h5', 'h6', 'strong', 'p', 'li', 'article', 'section', 'div'], recursive=False):
      child_category = self.category_from_heading(child, category_aliases)
      if child_category:
        current_category = child_category
        continue
      if self.is_other_category_heading(child, category_aliases):
        current_category = ''
        continue
      if self.looks_like_work_card(child) and current_category:
        row = self.row_from_node(child, base_url, category, result)
        if row is not None:
          rows.append(row)
        continue
      child_rows, current_category = self.rows_from_node(
        child,
        base_url,
        category,
        category_aliases,
        current_category,
        result)
      rows.extend(child_rows)
    if (
        not rows
        and current_category
        and not self.contains_category_heading(node)
        and self.looks_like_work_card(node)):
      row = self.row_from_node(node, base_url, category, result)
      if row is not None:
        rows.append(row)
    return rows, current_category

  def category_from_heading(self, node, category_aliases):
    if not self.is_heading_node(node):
      return ''
    text = normalize_heading(self.node_text(node))
    if text in category_aliases:
      return text
    return ''

  def is_other_category_heading(self, node, category_aliases):
    if not self.is_heading_node(node):
      return False
    text = normalize_heading(self.node_text(node))
    if text in category_aliases:
      return False
    return text in {
      'fiction',
      'nonfiction',
      'young readers literature',
      'young readers',
      'children s',
      'childrens',
      'teen',
    }

  def contains_category_heading(self, node):
    if not isinstance(node, Tag):
      return False
    for child in node.find_all(['h3', 'h4', 'h5', 'h6', 'strong']):
      text = normalize_heading(self.node_text(child))
      if text in {
          'fiction',
          'nonfiction',
          'young readers literature',
          'young readers',
          'children s',
          'childrens',
          'teen'}:
        return True
    return False

  def is_heading_node(self, node):
    return (getattr(node, 'name', '') or '').lower() in {
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong'}

  def looks_like_work_card(self, node):
    text = normalize_heading(self.node_text(node))
    return (
      bool(text)
      and not self.is_ignored_text(text)
      and (
        node.find('a', href=True) is not None
        or node.find(['em', 'i']) is not None
        or ' by ' in text))

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
    title_node = self.title_node(node)
    if title_node is not None:
      title = self.node_text(title_node)
      author = self.author_near_title(node, title)
      if author:
        return title, author
    return self.title_author_from_lines(self.work_lines(node))

  def title_node(self, node):
    for candidate in node.find_all(['a', 'em', 'i', 'h3', 'h4', 'h5']):
      text = self.clean_title(self.node_text(candidate))
      if text and not self.is_ignored_text(text) and not self.looks_like_author_line(text):
        return candidate
    return None

  def author_near_title(self, node, title):
    for line in self.work_lines(node):
      if normalize_heading(line) == normalize_heading(title):
        continue
      if self.looks_like_author_line(line):
        return self.strip_author_label(line)
      by_match = re.search(r'\bby\s+(.+)$', line, re.I)
      if by_match is not None:
        return by_match.group(1)
    full_text = self.node_text(node)
    if title in full_text:
      return self.author_from_text_after_title(full_text.split(title, 1)[1])
    return ''

  def work_lines(self, node):
    lines = []
    for item in node.find_all(['h3', 'h4', 'h5', 'p', 'li', 'a', 'em', 'i', 'span'], recursive=True):
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
      if self.looks_like_author_line(line):
        for other in cleaned[index + 1:] + cleaned[:index]:
          if not self.looks_like_author_line(other):
            return other, self.strip_author_label(line)
    if len(cleaned) >= 2:
      if self.looks_like_author_line(cleaned[0]):
        return cleaned[1], self.strip_author_label(cleaned[0])
      return cleaned[0], self.strip_author_label(cleaned[1])
    return '', ''

  def title_author_from_text(self, value):
    text = strip_publication_notes(self.strip_result_prefix(value))
    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', text, re.I)
    if by_match is not None:
      return by_match.group(1).strip(), by_match.group(2).strip()
    for separator in (' | ', ' - ', ' \u2013 ', ' \u2014 '):
      if separator in text:
        title, author = text.split(separator, 1)
        return title.strip(), author.strip()
    return '', ''

  def author_from_text_after_title(self, value):
    text = normalize_line(value).strip(' ,:-\u2013\u2014|')
    return self.strip_author_label(text)

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
      r'^\s*(?:winner|finalists?)\s*:?\s*',
      '',
      value or '',
      flags=re.I).strip()

  def is_ignored_text(self, value):
    text = normalize_heading(value)
    if not text:
      return True
    return any(ignored in text for ignored in (
      'kirkus prize',
      'rules',
      'eligibility',
      'juror',
      'judge',
      'sponsor',
      'submit',
      'previous winners',
    ))

  def clean_row_text(self, value):
    text = normalize_line(value)
    text = re.sub(r'\s*\[\s*\d+\s*\]\s*', ' ', text)
    return normalize_line(text)

  def clean_title(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    text = self.strip_author_label(value)
    return strip_publication_notes(text).strip(' "\u201c\u201d,')

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True) if isinstance(node, Tag) else None
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

  def normalized_category_aliases(self, category, aliases):
    return {
      normalize_heading(value)
      for value in (category,) + tuple(aliases or ())
      if value
    }

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
