#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
PEN/Faulkner Foundation award parsers.

Maintenance notes:
- PEN/Faulkner and PEN/Hemingway are official Foundation/Society sources, not
  PEN America Literary Awards pages.
- V1 imports winners and finalists/semi-finalists only. Longlists and broader
  article context are intentionally ignored.
"""

import re
from urllib.parse import urljoin

from lxml import html as lxml_html

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, RESULT_NOMINEE, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_NOMINEE, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key


class PENFaulknerAwardParser(AwardParserBase):
  """Parse official PEN/Faulkner Award for Fiction pages and posts."""

  AWARD_NAME = 'PEN/Faulkner Award for Fiction'
  CATEGORY = 'Fiction'

  def parse(self, pages, base_url, name=None, category=None):
    if isinstance(pages, (str, bytes)):
      pages = ((base_url, pages, 'history'),)
    rows = []
    for page_url, page_html, page_kind in pages:
      root = self.html_root(page_html)
      if page_kind == 'winner_post':
        rows.extend(self.parse_current_winner_post(root, page_url))
      elif page_kind == 'finalist_post':
        rows.extend(self.parse_current_finalist_post(root, page_url))
      else:
        rows.extend(self.parse_history(root, page_url))
    entries = self.entries_from_rows(self.dedupe_rows(rows), category or self.CATEGORY)
    return self.parsed_result(
      name or self.AWARD_NAME,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_history(self, root, base_url):
    rows = []
    current_year = None
    current_result = None
    for node in root.xpath('//h1|//h2|//h3|//h4|//p|//li'):
      text = self.node_text(node)
      if not text:
        continue
      year = self.year_from_text(text)
      if year is not None and normalize_heading(text) == str(year):
        current_year = year
        current_result = None
        continue
      prefix_result = self.result_prefix(text)
      if year is not None and prefix_result is not None:
        current_year = year
      if prefix_result is not None:
        current_result = prefix_result
        text = self.strip_result_prefix(text)
      elif current_result is None:
        continue
      for work_text in self.split_possible_rows(text):
        row = self.row_from_text(work_text, current_year, current_result, node, base_url)
        if row:
          rows.append(row)
    return rows

  def parse_current_finalist_post(self, root, base_url):
    rows = []
    year = self.year_from_text(self.node_text(root))
    in_finalists = False
    for node in root.xpath('//h1|//h2|//h3|//h4|//p|//li'):
      text = self.node_text(node)
      result = (
        self.result_from_heading(text)
        if self.is_heading_node(node)
        else None
      )
      if result == RESULT_NOMINEE:
        in_finalists = True
        continue
      if result == 'longlist':
        in_finalists = False
        continue
      if in_finalists:
        row = self.row_from_text(text, year, RESULT_NOMINEE, node, base_url)
        if row:
          rows.append(row)
    return rows

  def parse_current_winner_post(self, root, base_url):
    rows = []
    year = self.year_from_text(self.node_text(root))
    winner_keys = set()
    for node in root.xpath('//p|//li'):
      text = self.node_text(node)
      if not re.search(r'\bwins?\b|\bwinner\b', text, re.I):
        continue
      row = self.row_from_text(
        self.strip_result_prefix(text), year, RESULT_WINNER, node, base_url)
      if row:
        rows.append(row)
        winner_keys.add(self.work_key(row))
        break
    finalist_mode = False
    for node in root.xpath('//h1|//h2|//h3|//h4|//p|//li'):
      text = self.node_text(node)
      result = (
        self.result_from_heading(text)
        if self.is_heading_node(node)
        else None
      )
      if result == RESULT_NOMINEE:
        finalist_mode = True
        continue
      if result == RESULT_WINNER:
        finalist_mode = False
        continue
      if finalist_mode:
        row = self.row_from_text(text, year, RESULT_NOMINEE, node, base_url)
        if row and self.work_key(row) not in winner_keys:
          rows.append(row)
    return rows

  def row_from_text(self, text, year, result, node, base_url):
    if year is None:
      year = self.year_from_text(text)
    if year is None:
      year = self.year_from_text(base_url)
    if year is None:
      return None
    text = self.strip_year_prefix(self.strip_result_prefix(text))
    title, author = self.split_title_author(text)
    if not title or not author or self.is_ignored_row(text):
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': self.first_link_url(node, base_url),
      'category': self.CATEGORY,
    }

  def split_title_author(self, value):
    text = strip_publication_notes(normalize_line(value))
    text = re.sub(r'\s+has won\b.*$', '', text, flags=re.I).strip()
    text = re.sub(r'\s+is the winner\b.*$', '', text, flags=re.I).strip()
    if re.search(r'\s+by\s+', text, re.I):
      title, author = re.split(r'\s+by\s+', text, maxsplit=1, flags=re.I)
      return self.clean_title(title), self.clean_author(author)
    if ',' in text:
      title, author = text.rsplit(',', 1)
      return self.clean_title(title), self.clean_author(author)
    return '', ''

  def entries_from_rows(self, rows, category):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, category)
        for row in by_year[year]
      ]
      entries.extend(assign_positions(
        award_rows, int(year), tied_winners_share_position=True))
    return entries

  def dedupe_rows(self, rows):
    deduped = []
    seen = set()
    for row in rows:
      key = (
        row['award_year'], row['result'],
        normalize_heading(row['title']), normalize_heading(row['author']))
      if key in seen:
        continue
      seen.add(key)
      deduped.append(row)
    return deduped

  def split_possible_rows(self, text):
    text = re.sub(r'^\s*(?:winner|finalists?)\s*:\s*', '', text, flags=re.I)
    return [
      normalize_line(part)
      for part in re.split(r'\s*;\s*', text)
      if normalize_line(part)
    ]

  def result_from_heading(self, text):
    heading = normalize_heading(text)
    if 'longlist' in heading:
      return 'longlist'
    if 'winner' in heading:
      return RESULT_WINNER
    if 'finalist' in heading or 'shortlist' in heading:
      return RESULT_NOMINEE
    return None

  def is_heading_node(self, node):
    return (node.tag or '').lower() in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}

  def result_prefix(self, text):
    if re.match(r'^\s*winner\s*:', text, re.I):
      return RESULT_WINNER
    if re.match(r'^\s*finalists?\s*:', text, re.I):
      return RESULT_NOMINEE
    return None

  def strip_result_prefix(self, text):
    return re.sub(
      r'^\s*(?:winner|finalists?|semi-finalists?)\s*:\s*',
      '', text, flags=re.I)

  def strip_year_prefix(self, text):
    return re.sub(r'^\s*(?:19|20)\d{2}\s*[:\-–,/]*\s*', '', text)

  def is_ignored_row(self, text):
    heading = normalize_heading(text)
    return not heading or heading in {'winner', 'finalist', 'finalists'}

  def work_key(self, row):
    return (normalize_heading(row.get('title', '')), normalize_heading(row.get('author', '')))

  def clean_title(self, value):
    return normalize_line(value).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def html_root(self, html):
    return lxml_html.fromstring(html or '<html></html>')

  def node_text(self, node):
    if node is None:
      return ''
    return normalize_line(' '.join(
      text.strip()
      for text in node.xpath('.//text()[not(ancestor::script or ancestor::style)]')
      if text.strip()))

  def first_link_url(self, node, base_url):
    hrefs = node.xpath('(.//a[@href])[1]/@href')
    return urljoin(base_url, hrefs[0]) if hrefs else base_url

  def year_from_text(self, value):
    match = re.search(r'(19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None


class PENHemingwayAwardParser(PENFaulknerAwardParser):
  """Parse official PEN/Hemingway winner, semi-finalist, and history pages."""

  AWARD_NAME = 'PEN/Hemingway Award for Debut Novel'
  CATEGORY = 'Debut Novel'

  def parse(self, pages, base_url, name=None, category=None):
    if isinstance(pages, (str, bytes)):
      pages = ((base_url, pages, 'history'),)
    rows = []
    for page_url, page_html, page_kind in pages:
      root = self.html_root(page_html)
      if page_kind == 'current':
        rows.extend(self.parse_current(root, page_url))
      else:
        rows.extend(self.parse_history(root, page_url))
    entries = self.entries_from_rows(self.dedupe_rows(rows), category or self.CATEGORY)
    return self.parsed_result(
      name or self.AWARD_NAME,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_current(self, root, base_url):
    rows = []
    year = self.year_from_text(self.node_text(root))
    current_result = None
    for node in root.xpath('//h1|//h2|//h3|//h4|//p|//li'):
      text = self.node_text(node)
      heading_result = (
        self.hemingway_result_from_heading(text)
        if self.is_heading_node(node)
        else None
      )
      if heading_result is not None:
        current_result = heading_result
        continue
      if current_result is None:
        continue
      row = self.row_from_text(text, year, current_result, node, base_url)
      if row:
        rows.append(row)
    return rows

  def parse_history(self, root, base_url):
    rows = []
    current_year = None
    current_result = None
    for node in root.xpath('//h1|//h2|//h3|//h4|//p|//li'):
      text = self.node_text(node)
      year = self.year_from_text(text)
      if year is not None:
        current_year = year
      heading_result = (
        self.hemingway_result_from_heading(text)
        if self.is_heading_node(node)
        else None
      )
      prefix_result = self.result_prefix(text)
      if heading_result is not None:
        current_result = heading_result
        text = self.strip_result_prefix(text)
      elif prefix_result is not None:
        current_result = prefix_result
        text = self.strip_result_prefix(text)
      if current_result is None:
        continue
      for work_text in self.split_possible_rows(text):
        row = self.row_from_text(work_text, current_year, current_result, node, base_url)
        if row:
          rows.append(row)
    return rows

  def hemingway_result_from_heading(self, text):
    heading = normalize_heading(text)
    if 'winner' in heading:
      return RESULT_WINNER
    if 'semi finalist' in heading or 'semifinalist' in heading or 'finalist' in heading:
      return RESULT_NOMINEE
    return None
