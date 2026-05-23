#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Ngaio Marsh Award parsers.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.librarything_base import (
    LibraryThingAwardParserBase,
  )
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase,
    assign_positions,
    normalize_heading,
    normalize_line,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .librarything_base import LibraryThingAwardParserBase
  from .award_base import AwardParserBase, assign_positions, normalize_heading, normalize_line
  from .generic import position_sort_key


AWARD_NAME = 'Ngaio Marsh Award'


class NgaioMarshLibraryThingParser(LibraryThingAwardParserBase):

  AWARD_NAME = AWARD_NAME

  def result_from_heading(self, heading):
    text = normalize_heading(heading.get_text(' ', strip=True))
    if text.startswith('winner'):
      return 'winner'
    if text.startswith('shortlist'):
      return 'nominee'
    return None


class NgaioMarshWikipediaParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def parse(self, html, base_url, name, category, category_aliases=()):
    soup = BeautifulSoup(html, 'html.parser')
    accepted = {
      normalize_heading(value) for value in (category, *category_aliases) if value
    }
    rows = []
    current_year = None
    current_category = None
    winner_depth = 0
    for node in soup.find_all(['h2', 'h3', 'h4', 'li']):
      text = normalize_line(node.get_text(' ', strip=True))
      if not text:
        continue
      year = self._year_from_heading(node.name, text)
      if year is not None:
        current_year = year
        current_category = None
        continue
      if node.name == 'h4':
        normalized = normalize_heading(text)
        current_category = category if normalized in accepted else None
        continue
      if node.name != 'li' or current_year is None or current_category is None:
        continue
      depth = len(list(node.parents))
      if node.find_parent('li') is None:
        rows.append(self._build_row(node, base_url, current_year, category, 'winner'))
        winner_depth = depth
      elif depth > winner_depth:
        rows.append(self._build_row(node, base_url, current_year, category, 'nominee'))
    rows = [row for row in rows if row is not None]
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def _year_from_heading(self, tag_name, text):
    if tag_name != 'h3':
      return None
    match = re.match(r'^((?:19|20)\d{2})$', text)
    return int(match.group(1)) if match is not None else None

  def _build_row(self, item, base_url, year, category, result):
    clone = BeautifulSoup(str(item), 'html.parser').find('li')
    if clone is None:
      return None
    for nested in clone.find_all(['ul', 'ol']):
      nested.decompose()
    text = normalize_line(clone.get_text(' ', strip=True))
    text = re.sub(r'\[\s*\d+\s*\]', '', text).strip()
    if ' by ' not in text:
      return None
    title, author = text.rsplit(' by ', 1)
    link = item.find('a', href=True)
    return {
      'award_year': str(year),
      'title': title.strip(' "\u201c\u201d,'),
      'author': author.strip(),
      'result': result,
      'source_url': urljoin(base_url, link['href']) if link is not None else base_url,
      'category': category,
    }

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


def parse_ngaio_marsh_librarything(html, base_url, name, category, category_aliases=()):
  return NgaioMarshLibraryThingParser().parse(
    html, base_url, name, category, category_aliases)


def parse_ngaio_marsh_wikipedia(html, base_url, name, category, category_aliases=()):
  return NgaioMarshWikipediaParser().parse(
    html, base_url, name, category, category_aliases)
