#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Ned Kelly Award parsers.
"""

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.librarything_base import (
    LibraryThingAwardParserBase,
  )
  from calibre_plugins.list_switchboard.parser.wikipedia_base import (
    WikipediaAwardTableParserBase,
  )
  from calibre_plugins.list_switchboard.parser.award_base import normalize_heading
except ImportError:
  from .librarything_base import LibraryThingAwardParserBase
  from .wikipedia_base import WikipediaAwardTableParserBase
  from .award_base import normalize_heading


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

  def parse(self, html, base_url, name, category, category_aliases=()):
    soup = BeautifulSoup(html, 'html.parser')
    detailed_rows = []
    accepted = {
      normalize_heading(value) for value in (category, *category_aliases) if value
    }
    for heading in soup.find_all(['h2', 'h3', 'h4']):
      if normalize_heading(heading.get_text(' ', strip=True)) not in accepted:
        continue
      table = heading.find_next('table')
      if table is None:
        continue
      detailed_rows.extend(super().table_rows(
        table,
        self.header_map(table),
        base_url,
        category,
        category_aliases,
        {'winner', 'shortlisted'}))
      break
    summary_rows = self._summary_rows(soup, base_url, category, category_aliases)
    rows = self._merge_rows(summary_rows, detailed_rows)
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(name, base_url, entries)

  def _summary_rows(self, soup, base_url, category, category_aliases):
    target = normalize_heading(category)
    aliases = {normalize_heading(value) for value in category_aliases}
    rows = []
    for table in soup.find_all('table'):
      first_row = table.find('tr')
      if first_row is None:
        continue
      headers = [normalize_heading(self.clean_cell_text(cell))
                 for cell in first_row.find_all(['th', 'td'], recursive=False)]
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
      for tr in table.find_all('tr')[1:]:
        cells = tr.find_all(['td', 'th'], recursive=False)
        if not cells or column >= len(cells):
          continue
        year = self.year_from_text(self.clean_cell_text(cells[0])) or current_year
        current_year = year
        if year is None:
          continue
        value = self.clean_cell_text(cells[column])
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

  def _split_summary_value(self, value):
    text = value.replace('(tie)', '').strip()
    if ' by ' not in text:
      return '', ''
    title, author = text.rsplit(' by ', 1)
    return self.clean_title(title), self.clean_author(author)

  def _merge_rows(self, summary_rows, detailed_rows):
    covered_years = {row['award_year'] for row in detailed_rows}
    rows = [row for row in summary_rows if row['award_year'] not in covered_years]
    rows.extend(detailed_rows)
    return rows


def parse_ned_kelly_librarything(html, base_url, name, category, category_aliases=()):
  return NedKellyLibraryThingParser().parse(
    html, base_url, name, category, category_aliases)


def parse_ned_kelly_wikipedia(html, base_url, name, category, category_aliases=()):
  return NedKellyWikipediaParser().parse(
    html, base_url, name, category, category_aliases)
