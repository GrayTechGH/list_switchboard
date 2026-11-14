#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Ned Kelly Award parsers.
"""

import re

try:
  from calibre_plugins.list_switchboard.parser.librarything_base import (
    LibraryThingAwardParserBase,
  )
  from calibre_plugins.list_switchboard.parser.wikipedia_base import (
    WikipediaAwardTableParserBase,
  )
  from calibre_plugins.list_switchboard.parser.award_base import (
    assign_positions, normalize_heading, normalize_line,
  )
except ImportError:
  from .librarything_base import LibraryThingAwardParserBase
  from .wikipedia_base import WikipediaAwardTableParserBase
  from .award_base import assign_positions, normalize_heading, normalize_line


AWARD_NAME = 'Ned Kelly Award'


class NedKellyLibraryThingParser(LibraryThingAwardParserBase):

  AWARD_NAME = AWARD_NAME

  def result_from_heading(self, heading):
    text = normalize_heading(heading.get_text(' ', strip=True))
    if text.startswith('winner'):
      return 'winner'
    if text.startswith('shortlist') or text.startswith('finalist'):
      return 'nominee'
    return None


class NedKellyWikipediaParser(WikipediaAwardTableParserBase):

  AWARD_NAME = AWARD_NAME

  def clean_author(self, value):
    """Split bounded Wikipedia coauthor credits into schema author values."""
    value = super().clean_author(value)
    authors = [
      part.strip(' ,;')
      for part in re.split(r'\s*(?:;|&|\band\b)\s*', value, flags=re.I)
      if part.strip(' ,;')
    ]
    return ' & '.join(authors)

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
      entries.extend(assign_positions(
        award_rows, int(year), tied_winners_share_position=True))
    return entries

  def parse(self, html, base_url, name, category, category_aliases=()):
    root = self.html_root(html)
    detailed_rows = []
    for _heading, table in self.tables_under_category_headings(
        root, category, category_aliases, match='exact'):
      detailed_rows.extend(self._table_rows_standard(
        table,
        self.header_map(table),
        base_url,
        category,
        category_aliases,
        {'winner', 'shortlisted'}))
      break
    summary_rows = self._summary_rows(root, base_url, category, category_aliases)
    rows = self._merge_rows(summary_rows, detailed_rows)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(name, base_url, entries)

  def _summary_rows(self, root, base_url, category, category_aliases):
    target = normalize_heading(category)
    aliases = {normalize_heading(value) for value in category_aliases}
    rows = []
    for table in self.all_tables(root):
      table_rows = self._table_grid(table)
      if not table_rows:
        continue
      first_row = table_rows[0]
      headers = [normalize_heading(self.clean_cell_text(cell)) for cell in first_row]
      if not headers or headers[0] != 'year':
        continue
      column = None
      for index, header in enumerate(headers):
        if header == target or header in aliases:
          column = index
          break
      if column is None:
        continue
      current_year = None
      for cells in table_rows[1:]:
        if not cells or column >= len(cells):
          continue
        year = self.year_from_text(self.clean_cell_text(cells[0])) or current_year
        current_year = year
        if year is None:
          continue
        for value in self._summary_cell_values(cells[column]):
          if not value or value in {'—', 'NA'}:
            continue
          title, author = self._split_summary_value(value)
          if not title or not author:
            continue
          rows.append({
            'award_year': str(year),
            'title': title,
            'author': author,
            'result': 'winner',
            'source_url': base_url,
            'category': category,
          })
    return rows

  def _table_grid(self, table):
    """Expand summary-table rowspans so continuation winners keep their year."""
    grid = []
    rowspans = {}
    for tr in self.all_rows(table):
      row = []
      column = 0
      for cell in self.direct_cells(tr, include_headers=True):
        while column in rowspans:
          span_cell, remaining = rowspans[column]
          row.append(span_cell)
          if remaining <= 1:
            del rowspans[column]
          else:
            rowspans[column] = (span_cell, remaining - 1)
          column += 1
        colspan = self._span_value(cell, 'colspan')
        rowspan = self._span_value(cell, 'rowspan')
        for _index in range(colspan):
          row.append(cell)
          if rowspan > 1:
            rowspans[column] = (cell, rowspan - 1)
          column += 1
      while column in rowspans:
        span_cell, remaining = rowspans[column]
        row.append(span_cell)
        if remaining <= 1:
          del rowspans[column]
        else:
          rowspans[column] = (span_cell, remaining - 1)
        column += 1
      if row:
        grid.append(row)
    return grid

  def _span_value(self, cell, attribute):
    try:
      return max(1, int(cell.get(attribute, 1)))
    except Exception:
      return 1

  def _summary_cell_values(self, cell):
    """Split structurally separate co-winners without splitting title text."""
    fragments = []
    parts = []

    def flush():
      nonlocal parts
      text = normalize_line(' '.join(parts))
      if fragments and text.casefold().startswith('and '):
        text = text[4:].strip()
      if text:
        fragments.append(text)
      parts = []

    for node in cell.xpath('./node()'):
      if isinstance(node, str):
        if node.strip():
          parts.append(str(node))
        continue
      tag = str(getattr(node, 'tag', '')).casefold()
      if tag == 'br':
        flush()
        continue
      if tag in {'sup', 'style', 'script'}:
        continue
      text = self.node_text(node)
      if text:
        parts.append(text)
    flush()
    return fragments

  def _split_summary_value(self, value):
    text = value.replace('(tie)', '').strip()
    if ' by ' not in text:
      return '', ''
    title, author = text.rsplit(' by ', 1)
    return self.clean_title(title), self.clean_author(author)

  def _merge_rows(self, summary_rows, detailed_rows):
    # Detailed shortlist tables are sparse even within years they cover. Keep
    # summary winners and let the normal work-identity dedupe remove overlaps.
    return list(summary_rows) + list(detailed_rows)


def parse_ned_kelly_librarything(html, base_url, name, category, category_aliases=()):
  return NedKellyLibraryThingParser().parse(
    html, base_url, name, category, category_aliases)


def parse_ned_kelly_wikipedia(html, base_url, name, category, category_aliases=()):
  return NedKellyWikipediaParser().parse(
    html, base_url, name, category, category_aliases)
