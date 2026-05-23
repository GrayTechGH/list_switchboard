#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Reusable LibraryThing award fallback parser base.

Maintenance notes:
- LibraryThing award pages are fallback sources, not preferred sources.
- Category pages and root award pages can both expose staged rows; the parser
  accepts either rows with explicit Category + Year cells or category-filtered
  pages with only Work + Year.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

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


class LibraryThingAwardParserBase(AwardParserBase):
  """
  Parse LibraryThing award rows split into Winner/Nominee sections.

  Invariants:
  - Winners repeated in the nominee section are deduplicated and kept as winners.
  - Rows from root award pages must match the configured category; category-page
    rows without category cells are accepted as that configured category.
  """

  AWARD_NAME = ''

  def parse(self, html, base_url, name, category, category_aliases=()):
    rows = self.parse_rows(html, base_url, category, category_aliases)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url, category, category_aliases):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for heading in soup.find_all(['h2', 'h3']):
      result = self.result_from_heading(heading)
      if result is None:
        continue
      for row in self.section_rows(heading):
        parsed = self.parse_row(row, base_url, category, category_aliases, result)
        if parsed is not None:
          rows.append(parsed)
    return rows

  def result_from_heading(self, heading):
    text = normalize_heading(heading.get_text(' ', strip=True))
    if text.startswith('winner'):
      return 'winner'
    if text.startswith('nominee') or text.startswith('finalist'):
      return 'nominee'
    return None

  def section_rows(self, heading):
    rows = []
    for node in heading.next_siblings:
      name = getattr(node, 'name', None)
      if name in {'h2', 'h3'}:
        break
      if name == 'table':
        rows.extend(node.find_all('tr')[1:])
      elif name in {'ul', 'ol'}:
        rows.extend(node.find_all('li', recursive=False))
    return rows

  def parse_row(self, row, base_url, category, category_aliases, result):
    cells = row.find_all(['td', 'th'])
    if cells:
      work_cell = cells[0]
      year_cell = cells[-1]
      category_cell = cells[1] if len(cells) > 2 else None
    else:
      work_cell = row
      year_cell = row
      category_cell = None
    year = self.year_from_text(year_cell.get_text(' ', strip=True))
    title, author = self.title_author_from_work_cell(work_cell)
    row_category = (
      normalize_line(category_cell.get_text(' ', strip=True))
      if category_cell is not None else category
    )
    if year is None or not title or not author:
      return None
    if not self.category_matches(row_category, category, category_aliases):
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': self.first_work_url(work_cell, base_url) or base_url,
      'category': category,
    }

  def title_author_from_work_cell(self, cell):
    links = cell.find_all('a')
    if len(links) >= 2:
      title = self.clean_title(links[0].get_text(' ', strip=True))
      author = self.clean_author(links[1].get_text(' ', strip=True))
      return title, author
    text = normalize_line(cell.get_text(' ', strip=True))
    match = re.match(r'^(.+?)\s+by\s+(.+?)(?:\s+(?:19|20)\d{2})?$', text, re.I)
    if match is None:
      return '', ''
    return self.clean_title(match.group(1)), self.clean_author(match.group(2))

  def first_work_url(self, cell, base_url):
    link = cell.find('a', href=True)
    return urljoin(base_url, link['href']) if link is not None else ''

  def year_from_text(self, value):
    match = re.search(r'(19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def category_matches(self, row_category, category, category_aliases):
    aliases = {category, *category_aliases}
    normalized = {normalize_heading(alias) for alias in aliases}
    return normalize_heading(row_category) in normalized

  def clean_title(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    return strip_publication_notes(normalize_line(value)).strip()

  def dedupe_rows(self, rows):
    deduped = []
    seen = set()
    winners = set()
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['category']),
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      if row.get('result') == 'winner':
        winners.add(key)
      if key in seen:
        continue
      if row.get('result') == 'nominee' and key in winners:
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
