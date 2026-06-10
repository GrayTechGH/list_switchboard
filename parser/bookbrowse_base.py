#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Reusable BookBrowse online book club parser base.

Maintenance notes:
- BookBrowse's public book club archive is grouped by year headings, followed
  by discussion headings in the shape "Title by Author".
- This is a book-club/list source, not an award source, so entries use ordinary
  list positions and include the discussion year as extra metadata.
- The parser intentionally targets the online book club archive shape, not
  BookBrowse reviews, reading guides, or recommendation pages.
"""

import re
from urllib.parse import urljoin

from lxml import html as lxml_html

try:
  from calibre_plugins.list_switchboard.parser.base import (
    CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    ListParserBase,
  )
  from calibre_plugins.list_switchboard.parser.award_base import normalize_line
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .base import (
    CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    ListParserBase,
  )
  from .award_base import normalize_line
  from .generic import position_sort_key


YEAR_HEADING = re.compile(r'^(?:More\s+)?((?:19|20)\d{2}) Book (?:Club )?Discussions$', re.I)
DISCUSSION_SUFFIX = re.compile(
  r'\s*(?::\s*BookBrowse Book Club|Book Club Discussions?|Book Discussion|Discussion)\s*$',
  re.I)


class BookBrowseBookClubParserBase(ListParserBase):
  """
  Parse BookBrowse online book club archive headings into list entries.

  Invariants:
  - Only headings after a recognized year section are considered book entries.
  - The title/author split uses the last " by " so titles containing "by" are
    less likely to be truncated.
  - Rows without a parseable author are skipped; some archive headings are
    generic forum categories rather than selected books.
  """

  FILTER_CATEGORIES = (
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,
  )

  def parse(self, html, base_url, name, category='BookBrowse Online Book Club'):
    root = lxml_html.fromstring(html or '<html></html>')
    entries = self.parse_entries(root, base_url, category)
    return {
      'name': name,
      'url': base_url,
      'entries': sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      'match_series': False,
    }

  def parse_entries(self, soup, base_url, category):
    entries = []
    current_year = None
    for heading in soup.xpath('//h1|//h2|//h3'):
      text = self.node_text(heading)
      year = self.year_from_heading(text)
      if year is not None:
        current_year = year
        continue
      if current_year is None:
        continue
      parsed = self.entry_from_heading(heading, base_url, current_year, category, len(entries) + 1)
      if parsed is not None:
        entries.append(parsed)
    return entries

  def year_from_heading(self, text):
    match = YEAR_HEADING.match(text)
    return match.group(1) if match is not None else None

  def entry_from_heading(self, heading, base_url, year, category, position):
    title, author = self.title_author_from_text(self.node_text(heading))
    if not title or not author:
      return None
    entry = {
      'position': str(position),
      'title': title,
      'author': author,
      'discussion_year': str(year),
      'category': category,
    }
    source_url = self.source_url_from_heading(heading, base_url)
    if source_url:
      entry['source_url'] = source_url
    return entry if self.include_entry(entry, heading) else None

  def title_author_from_text(self, text):
    text = DISCUSSION_SUFFIX.sub('', normalize_line(text)).strip()
    if ' by ' not in text.casefold():
      return '', ''
    parts = re.split(r'\s+by\s+', text, flags=re.I)
    title = ' by '.join(parts[:-1])
    author = parts[-1]
    return self.clean_title(title), self.clean_author(author)

  def clean_title(self, value):
    value = normalize_line(value)
    value = re.sub(r'\s+Book$', '', value, flags=re.I)
    value = re.sub(r'\s+by$', '', value, flags=re.I)
    return value.strip(' "\u201c\u201d,')

  def clean_author(self, value):
    value = normalize_line(value)
    value = re.sub(r'^by\s+', '', value, flags=re.I)
    return value.strip()

  def source_url_from_heading(self, heading, base_url):
    hrefs = heading.xpath('(.//a[@href])[1]/@href')
    return urljoin(base_url, hrefs[0]) if hrefs else ''

  def node_text(self, node):
    return normalize_line(' '.join(
      text.strip() for text in node.xpath('.//text()') if text.strip()))

  def include_entry(self, _entry, _heading):
    return True
