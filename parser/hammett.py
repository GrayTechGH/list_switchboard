#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Hammett Prize parser for official IACW archive pages.

Maintenance notes:
- The official Hammett archive is split across one overview page plus four
  year-range pages. Some 2017-2019 rows collapse winner, nominees, and judges
  into one heading block instead of separate lines.
- LibraryThing remains the replacement fallback because it currently disagrees
  with the official 2024 winner.
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


YEAR_HEADING = re.compile(r'^(19|20)\d{2}$')
YEAR_PAGE_URL = re.compile(
  r'/(?:hammett-prize-past-winners-nominees-j|copy-of-hammett-prize-past-winners-n(?:-[12])?)$',
  re.I)
ENTRY_END = re.compile(r',?\s+by\s+.+?(?:\([^()]*\)|$)', re.I)


class HammettPrizeParser(AwardParserBase):

  AWARD_NAME = 'Hammett Prize'

  def parse(
      self, html, base_url, name, category, category_aliases=(),
      fetch_url=None, log=None, progress=None):
    page_urls = self.discover_page_urls(html, base_url)
    page_roots = []
    if self.page_has_year_sections(html):
      page_roots.append((base_url, self.html_root(html)))
    elif not page_urls:
      raise ValueError('official Hammett source did not expose any year pages')

    for page_url in page_urls:
      if fetch_url is None:
        raise ValueError('official Hammett parser requires fetch_url for linked year pages')
      if log is not None:
        log(f'Hammett: fetching year page {page_url}')
      page_roots.append((page_url, self.html_root(fetch_url(page_url))))

    rows = []
    for page_url, root in page_roots:
      rows.extend(self.parse_year_page(root, page_url, category))
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def discover_page_urls(self, html, base_url):
    root = self.html_root(html)
    urls = []
    seen = set()
    for href in root.xpath('//a[@href]/@href'):
      page_url = urljoin(base_url, href)
      if not YEAR_PAGE_URL.search(page_url):
        continue
      if page_url in seen:
        continue
      seen.add(page_url)
      urls.append(page_url)
    return tuple(urls)

  def page_has_year_sections(self, html):
    root = self.html_root(html)
    return any(self.year_from_heading(self.node_text(node)) for node in root.xpath('//h2'))

  def parse_year_page(self, root, base_url, category):
    rows = []
    for heading in root.xpath('//h2'):
      year = self.year_from_heading(self.node_text(heading))
      if year is None:
        continue
      section_nodes = []
      for node in heading.itersiblings():
        if getattr(node, 'tag', None) == 'h2' and self.year_from_heading(self.node_text(node)):
          break
        section_nodes.append(node)
      rows.extend(self.parse_year_section(year, section_nodes, base_url, category))
    return rows

  def parse_year_section(self, year, nodes, base_url, category):
    rows = []
    current_result = None
    for node in nodes:
      text = self.node_text(node)
      if not text:
        continue
      normalized = normalize_heading(text)
      if normalized.startswith('winner'):
        if 'nominees' in normalized:
          rows.extend(self.parse_collapsed_winner_block(
            text, year, base_url, category, node))
          current_result = None
          continue
        row = self.parse_entry_text(
          self.after_label(text, 'winner'),
          RESULT_WINNER,
          year,
          base_url,
          category,
          node)
        if row is not None:
          rows.append(row)
        continue
      if normalized.startswith('special mention'):
        continue
      if normalized.startswith('nominees'):
        current_result = RESULT_NOMINEE
        nominees_text = self.after_label(text, 'nominees')
        if nominees_text:
          row = self.parse_entry_text(
            nominees_text,
            RESULT_NOMINEE,
            year,
            base_url,
            category,
            node)
          if row is not None:
            rows.append(row)
        continue
      if normalized.startswith('judges'):
        break
      if current_result == RESULT_NOMINEE:
        row = self.parse_entry_text(
          text,
          RESULT_NOMINEE,
          year,
          base_url,
          category,
          node)
        if row is not None:
          rows.append(row)
    return rows

  def parse_collapsed_winner_block(self, text, year, base_url, category, node):
    match = re.search(
      r'Winner:\s*(.+?)\s+Nominees:\s*(.+?)(?:\s+Judges:\s+.*)?$',
      normalize_line(text),
      re.I)
    if match is None:
      return ()
    rows = []
    winner_row = self.parse_entry_text(
      match.group(1),
      RESULT_WINNER,
      year,
      base_url,
      category,
      node)
    if winner_row is not None:
      rows.append(winner_row)
    for nominee_text in self.split_inline_entries(match.group(2)):
      nominee_row = self.parse_entry_text(
        nominee_text,
        RESULT_NOMINEE,
        year,
        base_url,
        category,
        node)
      if nominee_row is not None:
        rows.append(nominee_row)
    return tuple(rows)

  def split_inline_entries(self, text):
    text = normalize_line(text)
    entries = []
    start = 0
    for match in ENTRY_END.finditer(text):
      candidate = normalize_line(text[start:match.end()])
      if candidate:
        entries.append(candidate)
      start = match.end()
    if not entries and text:
      entries.append(text)
    return tuple(entries)

  def parse_entry_text(self, text, result, year, base_url, category, node):
    title, author = self.title_author_from_text(text)
    if not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': self.first_link_url(node, base_url) or base_url,
      'category': category,
    }

  def title_author_from_text(self, text):
    text = strip_publication_notes(normalize_line(text))
    parts = re.split(r',?\s+by\s+', text, maxsplit=1, flags=re.I)
    if len(parts) != 2:
      return '', ''
    return self.clean_title(parts[0]), self.clean_author(parts[1])

  def clean_title(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def after_label(self, text, label):
    match = re.match(r'^\s*' + re.escape(label) + r'\s*:\s*(.*)$', text, re.I)
    return match.group(1).strip() if match is not None else ''

  def year_from_heading(self, text):
    text = normalize_line(text)
    return int(text) if YEAR_HEADING.match(text or '') else None

  def first_link_url(self, node, base_url):
    hrefs = node.xpath('(.//a[@href])[1]/@href')
    return urljoin(base_url, hrefs[0]) if hrefs else ''

  def html_root(self, html):
    return lxml_html.fromstring(html or '<html></html>')

  def node_text(self, node):
    return normalize_line(' '.join(
      text.strip()
      for text in node.xpath('.//text()[not(ancestor::script) and not(ancestor::style)]')
      if text.strip()))

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


def parse_hammett_prize(
    html, base_url, name, category, category_aliases=(), fetch_url=None,
    log=None, progress=None):
  return HammettPrizeParser().parse(
    html,
    base_url,
    name,
    category,
    category_aliases,
    fetch_url=fetch_url,
    log=log,
    progress=progress)
