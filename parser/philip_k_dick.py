#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Philip K. Dick Award parser for SFADB year pages.

Maintenance notes:
- SFADB exposes one page per award year with Winner, Special Citation, and
  Finalists sections.
- Like Clarke, year pages use a section-result model rather than the standard
  category/boundary model. parse_year() is overridden accordingly.
- Special citations use .5-style positions to match the user's preferred list
  indexing. assign_positions() from the base is not used here because special
  citations require a separate counter.
"""

import re

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.sfadb_base import (
    SFADBParser,
    normalize_heading, normalize_line,
    strip_publication_notes, strip_square_notes, strip_tie_marker,
    split_title_author as award_split_title_author, text_lines,
  )
except ImportError:
  from .sfadb_base import (
    SFADBParser,
    normalize_heading, normalize_line,
    strip_publication_notes, strip_square_notes, strip_tie_marker,
    split_title_author as award_split_title_author, text_lines,
  )


AWARD_NAME = 'Philip K. Dick Award'
CATEGORY_NAME = 'Novel'
YEAR_PAGE_URL = re.compile(r'/Philip_K_Dick_Award_(\d{4})$')
SECTION_RESULTS = {
  'winner': 'winner',
  'special citation': 'special-citation',
  'finalists': 'nominee',
}
BOUNDARY_HEADINGS = frozenset({
  'where and when', 'eligibility year', 'judges', 'copyright',
})


def _is_boundary(line):
  heading = normalize_heading(line)
  if not heading:
    return False
  if heading in BOUNDARY_HEADINGS:
    return True
  return heading.startswith('this page last updated')


def _special_citation_position(year, index):
  if index == 0:
    return f'{year}.5'
  return f'{year}.5{index}'


def _category_block_rows(soup):
  rows = []
  for block in soup.find_all('div', class_='categoryblock'):
    heading_node = block.find('div', class_='category')
    heading = normalize_heading(
      heading_node.get_text(' ', strip=True) if heading_node else '')
    result = SECTION_RESULTS.get(heading)
    if result is None:
      continue
    for item in block.find_all('li'):
      line = normalize_line(item.get_text(' ', strip=True))
      if line:
        rows.append((line, result))
  return rows


def _split_title_author(text):
  work_text = strip_publication_notes(text)
  work_text = re.sub(
    r'\s*,\s*translated\s+by\s+.+$', '', work_text, flags=re.I).strip()
  return award_split_title_author(work_text)


class PhilipKDickParser(SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = frozenset()  # not used; section model overrides parse_year

  def parse(self, overview_html, base_url, name=None, category=None,
            category_aliases=None, fetch_url=None, log=None, progress=None):
    return super().parse(
      overview_html, base_url,
      name='Philip K. Dick Award - Novel',
      category=CATEGORY_NAME,
      category_aliases=(),
      fetch_url=fetch_url, log=log, progress=progress)

  def parse_year(self, html, source_url, year, category, category_aliases):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    block_rows = _category_block_rows(soup)
    if block_rows:
      for line, result in block_rows:
        parsed = self.parse_item(line)
        if parsed is None:
          continue
        parsed['result'] = result
        rows.append(parsed)
    else:
      result = None
      for line in text_lines(soup):
        heading = normalize_heading(line)
        if heading in SECTION_RESULTS:
          result = SECTION_RESULTS[heading]
          continue
        if result is None:
          continue
        if _is_boundary(line):
          result = None
          continue
        parsed = self.parse_item(line)
        if parsed is None:
          continue
        parsed['result'] = result
        rows.append(parsed)

    entries = []
    suffix_index = 0
    citation_index = 0
    winner_seen = False
    for row in rows:
      result = row['result']
      if result == 'winner' and not winner_seen:
        position = str(year)
        winner_seen = True
      elif result == 'special-citation':
        position = _special_citation_position(year, citation_index)
        citation_index += 1
      else:
        suffix_index += 1
        position = f'{year}.{suffix_index:02d}'
      entries.append({
        'position': position,
        'title': row['title'],
        'author': row['author'],
        'source_url': source_url,
        'award_year': str(year),
        'award': self.AWARD_NAME,
        'category': CATEGORY_NAME,
        'result': result,
      })
    return entries

  def parse_item(self, text):
    text = strip_tie_marker(strip_square_notes(normalize_line(text)))
    title, author = _split_title_author(text)
    if not title or not author:
      return None
    return {
      'title': strip_publication_notes(title).strip(' \"\u201c\u201d,'),
      'author': strip_publication_notes(author).strip(),
      'result': 'nominee',  # overwritten by parse_year after section detection
    }


def parse_philip_k_dick_award_novel(
    overview_html, base_url, fetch_url=None, log=None, progress=None):
  return PhilipKDickParser().parse(
    overview_html, base_url,
    fetch_url=fetch_url, log=log, progress=progress)
