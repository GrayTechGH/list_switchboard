#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Parser for LibraryReads monthly list entries.

Maintenance notes:
- The official archive page links month PDFs plus a public Google Sheet. The
  sheet is the preferred V1 source because it exposes the monthly-list rows and
  explicit Top Pick / Hall of Fame / Bonus Pick flags as structured data.
- Hall of Fame and Bonus Pick rows are intentionally excluded from this main
  monthly-list recipe; those can become separate follow-up fetchers.
"""

import csv
import io
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .book_club_base import BookClubParserBase, MONTHS, normalize_line, parse_month
from .base import parsed_source


SHEET_CSV_URL = (
  'https://docs.google.com/spreadsheets/d/'
  '1sPZhPu2HFFngko2fD4k3n3D5HBqExZQnvaNzV41nOUM/'
  'export?format=csv&gid=1246985966')


class LibraryReadsParser(BookClubParserBase):

  CLUB_NAME = 'LibraryReads'
  DEFAULT_SCOPE = 'monthly_list'
  DEFAULT_SELECTION_TYPE = 'staff_pick'

  def parse(self, html, base_url, name=None, scope=None, fetch_url=None, **_kwargs):
    scope = scope or self.DEFAULT_SCOPE
    notes = []
    entries = self.entries_from_source(html, base_url, scope)
    if not entries and fetch_url is not None and self.looks_like_archive(html):
      try:
        csv_text = fetch_url(SHEET_CSV_URL)
        entries = self.entries_from_source(csv_text, SHEET_CSV_URL, scope)
        notes.append(
          'LibraryReads imported from the official public archive spreadsheet linked from the archive page.')
      except Exception as err:
        notes.append(f'LibraryReads public archive spreadsheet could not be fetched: {err}')
    if not entries and self.looks_like_archive(html):
      notes.append(
        'LibraryReads archive page exposes month/document links; no monthly rows were available in the fetched source.')
    notes.extend(self.notes_for_entries(entries))
    return {
      'name': name or self.CLUB_NAME,
      'source': parsed_source(name or self.CLUB_NAME, base_url),
      'entries': sorted(entries, key=self.entry_sort_key),
      'notes': notes,
      'match_series': False,
    }

  def entries_from_source(self, source, base_url, scope):
    if self.looks_like_csv(source):
      return self.csv_entries(source, base_url, scope)
    return super().parse(source, base_url, self.CLUB_NAME, scope)['entries']

  def looks_like_csv(self, source):
    first_line = (source or '').lstrip('\ufeff\r\n ').splitlines()[:1]
    return bool(first_line and 'Month,' in first_line[0] and 'Title' in first_line[0])

  def looks_like_archive(self, source):
    text = normalize_line(BeautifulSoup(source or '', 'html.parser').get_text(' ', strip=True))
    normalized = text.casefold()
    return (
      'archive' in normalized and (
        'libraryreads' in normalized or
        'sortable text list of all past titles' in normalized or
        'all past titles' in normalized))

  def csv_entries(self, source, base_url, scope):
    entries = []
    month_counts = {}
    reader = csv.DictReader(io.StringIO(source.lstrip('\ufeff')))
    for row in reader:
      entry = self.entry_from_csv_row(row, base_url, scope, month_counts)
      if entry is not None:
        entries.append(entry)
    return entries

  def entry_from_csv_row(self, row, base_url, scope, month_counts):
    title = normalize_line(row.get('Title', ''))
    author = self.display_author(row.get('Author (Last, First)', ''))
    month_value = normalize_line(row.get('Month', ''))
    year, month = self.year_month_from_csv(month_value)
    if not title or not author or not year or not month:
      return None
    if normalize_line(row.get('HoF', '')) or normalize_line(row.get('Bonus Pick', '')):
      return None
    text = ' '.join(normalize_line(str(value)) for value in row.values())
    if not self.accept_entry({}, text):
      return None
    month_key = f'{year}-{month}'
    month_counts[month_key] = month_counts.get(month_key, 0) + 1
    data = {
      'title': title,
      'authors': [author],
      'selection_year': year,
      'selection_month': month,
      'selection_label': self.selection_label(year, month),
      'rank_or_position': str(month_counts[month_key]),
      'selection_type': 'top_pick' if normalize_line(row.get('Top Pick', '')) else 'staff_pick',
      'advocate_defender_host_selector': 'library staff voters',
    }
    flags = self.scope_flags(row)
    if flags:
      data['scope_flags'] = ', '.join(flags)
    return self.build_entry(data, text, base_url, scope, month_counts[month_key], base_url=base_url)

  def year_month_from_csv(self, value):
    match = re.match(r'^((?:19|20)\d{2})/(\d{1,2})$', normalize_line(value))
    if not match:
      return '', ''
    return match.group(1), str(int(match.group(2)))

  def selection_label(self, year, month):
    for name, value in MONTHS.items():
      if value == month:
        return f'{name.title()} {year}'
    return year

  def display_author(self, value):
    value = normalize_line(value)
    if ',' not in value:
      return value
    last, rest = [part.strip() for part in value.split(',', 1)]
    return normalize_line(f'{rest} {last}')

  def scope_flags(self, row):
    flags = []
    genre = normalize_line(row.get('Genre', '')).casefold()
    title = normalize_line(row.get('Title', '')).casefold()
    annotation = normalize_line(row.get('Annotation', '')).casefold()
    if 'nonfiction' in genre:
      flags.append('nonfiction')
    if 'memoir' in genre or 'memoir' in title:
      flags.append('memoir')
    if 'stories' in title or 'short story' in annotation:
      flags.append('short_story_collection')
    return list(dict.fromkeys(flags))

  def archive_links(self, html, base_url):
    soup = BeautifulSoup(html or '', 'html.parser')
    links = []
    current_year = ''
    for node in soup.find_all(['h3', 'a']):
      text = normalize_line(node.get_text(' ', strip=True))
      if node.name == 'h3' and re.fullmatch(r'(?:19|20)\d{2}', text):
        current_year = text
        continue
      if node.name != 'a' or not current_year or not parse_month(text):
        continue
      href = node.get('href')
      if href:
        links.append((current_year, text, urljoin(base_url, href)))
    return links

  def accept_entry(self, _entry, text):
    normalized = text.casefold()
    blocked = ('bonus pick', 'notable nonfiction', 'hall of fame')
    return not any(value in normalized for value in blocked)

  def complete_entry(self, entry, _text):
    if entry.get('selection_type') != 'top_pick':
      entry['selection_type'] = 'staff_pick'
    entry['advocate_defender_host_selector'] = (
      entry.get('advocate_defender_host_selector') or 'library staff voters')
    return entry
