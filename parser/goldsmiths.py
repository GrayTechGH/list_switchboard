#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Goldsmiths Prize parsers for the official archive and Wikipedia fallback.

Maintenance notes:
- The official archive index records each year's winner and links to a year
  page. Modern and legacy year URLs both expose shortlist book cards.
- Wikipedia is a replacement source, not a supplement. Its winner rows are
  marked by visual ribbon/highlight cells rather than a result column.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key


AWARD_NAME = 'Goldsmiths Prize'
CATEGORY = 'Novel'
OFFICIAL_URL = 'https://www.gold.ac.uk/goldsmiths-prize/archive/'
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Goldsmiths_Prize'


class GoldsmithsOfficialParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def parse(
      self, html, base_url=OFFICIAL_URL, name=AWARD_NAME, fetch_url=None,
      log=None, progress=None):
    archive_rows, year_links = self.archive_index_rows(html, base_url)
    rows = list(archive_rows)
    notes = []

    if fetch_url is not None and year_links:
      total = len(year_links)
      for index, (year, url) in enumerate(year_links, 1):
        try:
          if progress is not None:
            progress(index, total, f'Fetching {name} archive page {index} of {total}')
          rows.extend(self.year_page_rows(fetch_url(url), url, year))
        except Exception as err:
          notes.append(f'{name} archive page could not be fetched: {url}: {err}')
          if log is not None:
            log(f'{name} archive page failed: {url}: {err}')

    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def archive_index_rows(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    rows_by_year = {}
    links_by_year = {}
    for heading in soup.find_all(['h2', 'h3']):
      parsed = self.parse_winner_heading(self.clean_text(heading))
      if parsed is None:
        continue
      year, title, author = parsed
      url = self.next_year_link(heading, base_url) or links_by_year.get(year) or base_url
      rows_by_year[year] = {
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': RESULT_WINNER,
        'source_url': url,
        'category': CATEGORY,
      }
      if url != base_url:
        links_by_year[year] = url

    for link in soup.find_all('a', href=True):
      year = self.year_from_url(link['href'])
      if year is not None:
        links_by_year.setdefault(year, urljoin(base_url, link['href']))

    return (
      [rows_by_year[year] for year in sorted(rows_by_year)],
      tuple((year, links_by_year[year]) for year in sorted(links_by_year)))

  def parse_winner_heading(self, text):
    match = re.match(r'^\s*((?:19|20)\d{2})\s+winner\s*:?\s*(.+)$', text, re.I)
    if match is None:
      return None
    year = int(match.group(1))
    title_author = normalize_line(match.group(2))
    by_match = re.match(r'^(.+)\s+by\s+(.+)$', title_author, re.I)
    if by_match is None:
      return None
    return (
      year,
      self.clean_title(by_match.group(1)),
      self.clean_author(by_match.group(2)))

  def next_year_link(self, heading, base_url):
    for sibling in heading.find_next_siblings():
      if getattr(sibling, 'name', None) in {'h2', 'h3'}:
        break
      link = sibling.find('a', href=True) if hasattr(sibling, 'find') else None
      if link is not None and self.year_from_url(link['href']) is not None:
        return urljoin(base_url, link['href'])
    link = heading.find_next('a', href=True)
    if link is not None and self.year_from_url(link['href']) is not None:
      return urljoin(base_url, link['href'])
    return ''

  def year_page_rows(self, html, page_url, fallback_year=None):
    soup = BeautifulSoup(html, 'html.parser')
    year = self.year_from_url(page_url) or self.year_from_text(self.clean_text(soup.find('title'))) or fallback_year
    if year is None:
      return []
    rows = []
    for card in soup.find_all('article'):
      classes = card.get('class', []) or []
      if 'prize-teaser' not in classes:
        continue
      title = self.clean_title(self.clean_text(card.find(class_='book_name')))
      author = self.clean_author(self.clean_text(card.find(class_='book_author')))
      if not title or not author:
        continue
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': RESULT_SHORTLISTED,
        'source_url': self.first_link_url(card, page_url) or page_url,
        'category': CATEGORY,
      })
    return rows

  def clean_text(self, node):
    if node is None:
      return ''
    node = BeautifulSoup(str(node), 'html.parser')
    for removable in node.find_all(['script', 'style', 'sup']):
      removable.decompose()
    return normalize_line(node.get_text(' ', strip=True).replace('\xa0', ' '))

  def clean_title(self, value):
    value = strip_publication_notes(normalize_line(value))
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def clean_author(self, value):
    value = strip_publication_notes(normalize_line(value))
    return value.strip(' "\'\u2018\u2019\u201c\u201d,')

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True) if node is not None else None
    return urljoin(base_url, link['href']) if link is not None else ''

  def year_from_url(self, value):
    match = re.search(r'/prize-?((?:19|20)\d{2})/?', value or '')
    return int(match.group(1)) if match is not None else None

  def year_from_text(self, value):
    match = re.search(r'(?:19|20)\d{2}', value or '')
    return int(match.group(0)) if match is not None else None

  def dedupe_rows(self, rows):
    deduped = []
    index_by_key = {}
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      existing_index = index_by_key.get(key)
      if existing_index is None:
        index_by_key[key] = len(deduped)
        deduped.append(row)
        continue
      existing = deduped[existing_index]
      if existing.get('result') == RESULT_WINNER and row.get('result') != RESULT_WINNER:
        promoted = dict(row)
        promoted['result'] = RESULT_WINNER
        deduped[existing_index] = promoted
      elif existing.get('result') != RESULT_WINNER and row.get('result') == RESULT_WINNER:
        promoted = dict(existing)
        promoted['result'] = RESULT_WINNER
        deduped[existing_index] = promoted
    return deduped

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      year_rows = sorted(
        by_year[year],
        key=lambda row: 0 if row.get('result') == RESULT_WINNER else 1)
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in year_rows
      ]
      entries.extend(assign_positions(
        award_rows, int(year), tied_winners_share_position=True))
    return entries


class GoldsmithsWikipediaParser(GoldsmithsOfficialParser):

  def parse(self, html, base_url=WIKIPEDIA_URL, name=AWARD_NAME):
    rows = self.dedupe_rows(self.parse_rows(html, base_url))
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    for table in soup.find_all('table'):
      caption = normalize_heading(self.clean_text(table.find('caption')))
      if 'shortlisted and winning books' not in caption:
        continue
      rows.extend(self.wikipedia_table_rows(table, base_url))
    return rows

  def wikipedia_table_rows(self, table, base_url):
    rows = []
    current_year = None
    for tr in table.find_all('tr'):
      cells = tr.find_all(['td', 'th'], recursive=False)
      if not cells or self.wikipedia_header_row(cells):
        continue
      year = self.year_from_text(self.clean_text(cells[0]))
      if year is not None:
        current_year = year
        author_cell = self.cell_at(cells, 1)
        title_cell = self.cell_at(cells, 2)
      elif current_year is not None:
        author_cell = self.cell_at(cells, 0)
        title_cell = self.cell_at(cells, 1)
      else:
        continue
      if author_cell is None or title_cell is None:
        continue
      title = self.clean_title(self.clean_text(title_cell))
      author = self.clean_author(self.clean_text(author_cell))
      if not title or not author:
        continue
      rows.append({
        'award_year': str(current_year),
        'title': title,
        'author': author,
        'result': (
          RESULT_WINNER
          if self.wikipedia_winner_row(tr) else RESULT_SHORTLISTED),
        'source_url': self.first_link_url(title_cell, base_url) or base_url,
        'category': CATEGORY,
      })
    return rows

  def wikipedia_header_row(self, cells):
    headings = {normalize_heading(self.clean_text(cell)) for cell in cells}
    return {'year', 'author', 'novel'}.issubset(headings)

  def wikipedia_winner_row(self, tr):
    markup = str(tr).casefold()
    return 'background:lightyellow' in markup or 'blueribbon_icon' in markup

  def cell_at(self, cells, index):
    return cells[index] if index < len(cells) else None


def parse_goldsmiths_official(
    html, base_url=OFFICIAL_URL, name=AWARD_NAME, fetch_url=None,
    log=None, progress=None):
  return GoldsmithsOfficialParser().parse(
    html, base_url, name, fetch_url=fetch_url, log=log, progress=progress)


def parse_goldsmiths_wikipedia(html, base_url=WIKIPEDIA_URL, name=AWARD_NAME):
  return GoldsmithsWikipediaParser().parse(html, base_url, name)
