#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Reusable Worlds Without End award parser base.

Maintenance notes:
- WWEnd award pages are source-scoped pages grouped by award year. Within each
  year, book entries appear as alternating novel.asp title links and author.asp
  author links; the first book in the year is the winner.
- The parser intentionally targets the award-page shape, not arbitrary WWEnd
  search/list pages. Fetchers should choose a specific WWEnd award URL and pass
  the recipe category they want written into parsed entries.
"""

import re
from urllib.parse import urljoin

from lxml import html as lxml_html

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, assign_positions, normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    AwardParserBase, assign_positions, normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key


YEAR_TEXT = re.compile(r'^(19|20)\d{2}$')
NOVEL_URL = re.compile(r'/(?:books/)?novel\.asp\?id=\d+', re.I)
AUTHOR_URL = re.compile(r'/(?:authors/)?author\.asp\?id=\d+', re.I)


class WWEndAwardParserBase(AwardParserBase):
  """
  Parse WWEnd award pages into the shared award import entry schema.

  Invariants:
  - A year section without book/author pairs is ignored. This skips the page's
    jump navigation, which also contains year links.
  - The first book in a parsed year section is marked winner; all subsequent
    books are nominees. WWEnd does not expose final placement on award pages.
  """

  AWARD_NAME = ''

  def parse(self, html, base_url, name, category, category_aliases=()):
    rows = self.parse_rows(html, base_url, category, category_aliases)
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url, category, _category_aliases=()):
    root = lxml_html.fromstring(html or '<html></html>')
    rows = []
    links = root.xpath('//a[@href]')
    for index, link in enumerate(links):
      year = self.year_from_link(link)
      if year is None:
        continue
      section_links = self.links_until_next_year(links, index + 1)
      year_rows = self.rows_from_year_links(section_links, base_url, year, category)
      if year_rows:
        rows.extend(year_rows)
    return rows

  def links_until_next_year(self, links, start_index):
    section = []
    for link in links[start_index:]:
      if self.year_from_link(link) is not None:
        break
      section.append(link)
    return section

  def rows_from_year_links(self, links, base_url, year, category):
    rows = []
    index = 0
    while index < len(links):
      title_link = links[index]
      if not self.is_title_link(title_link):
        index += 1
        continue
      author_link, next_index = self.next_author_link(links, index + 1)
      index = next_index
      if author_link is None:
        continue
      row = self.row_from_links(title_link, author_link, base_url, year, category, rows)
      if row is not None:
        rows.append(row)
    return rows

  def row_from_links(self, title_link, author_link, base_url, year, category, rows):
    title = self.clean_title(self.node_text(title_link))
    author = self.clean_author(self.node_text(author_link))
    if not title or not author:
      return None
    row = {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': 'winner' if not rows else 'nominee',
      'source_url': urljoin(base_url, self.link_href(title_link)),
      'category': category,
      'award': self.AWARD_NAME,
    }
    return row if self.include_row(row, title_link, author_link) else None

  def include_row(self, _row, _title_link, _author_link):
    return True

  def next_author_link(self, links, start_index):
    for index, link in enumerate(links[start_index:], start=start_index):
      if self.year_from_link(link) is not None or self.is_title_link(link):
        return None, index
      if self.is_author_link(link):
        return link, index + 1
    return None, len(links)

  def year_from_link(self, link):
    text = self.node_text(link)
    if not YEAR_TEXT.match(text):
      return None
    return int(text)

  def is_title_link(self, link):
    return bool(NOVEL_URL.search(self.link_href(link)))

  def is_author_link(self, link):
    return bool(AUTHOR_URL.search(self.link_href(link)))

  def link_href(self, link):
    return link.get('href') or ''

  def node_text(self, node):
    return normalize_line(' '.join(
      text.strip() for text in node.xpath('.//text()') if text.strip()))

  def clean_title(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    return strip_publication_notes(normalize_line(value)).strip()

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      award_rows = [
        self.build_award_entry(
          row, row['source_url'], year, row['category'], award=row.get('award'))
        for row in by_year[year]
      ]
      entries.extend(assign_positions(award_rows, int(year)))
    return entries
