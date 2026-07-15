#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Parser for the Dragons & Jetpacks Goodreads group-read shelf.

Maintenance notes:
- The moderator-controlled ``group-read`` shelf is the inclusion boundary.
  Year, state, challenge, and other shelves are metadata only and never add
  records to the recipe.
- Goodreads lists group authors as ``Family, Given`` and appends series data to
  titles. Only terminal parentheticals containing a numbered-series marker are
  removed from matchable titles.
- Goodreads totals can change while pagination is in progress. Page-boundary
  overlap is therefore expected and is collapsed by stable group-book ID.
- Official discussion-topic month corrections are identity-bounded and apply
  only when a shelf row has no explicit start date. Later live dates win.
"""

from datetime import datetime
import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    is_author_suffix, normalize_line,
  )
  from calibre_plugins.list_switchboard.parser.base import ( # type: ignore
    CATEGORY_FANTASY,
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    CATEGORY_SCIENCE_FICTION,
    entry_source_object,
    imported_entry,
    ListParserBase,
    parsed_source,
  )
except ImportError:
  from .award_base import is_author_suffix, normalize_line
  from .base import (
    CATEGORY_FANTASY,
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    CATEGORY_SCIENCE_FICTION,
    entry_source_object,
    imported_entry,
    ListParserBase,
    parsed_source,
  )


NAME = 'Dragons & Jetpacks'
SOURCE_ID = 'dragons_and_jetpacks'
GROUP_SLUG = '106876-dragons-jetpacks'
SHELF_PATH = f'/group/bookshelf/{GROUP_SLUG}'
SHELF_URL = (
  f'https://www.goodreads.com{SHELF_PATH}?per_page=100&shelf=group-read')
MAX_PAGES = 100
CORE_LABELS = ('fantasy', 'sci-fi', 'horror', 'mod-special', 'buddy-read')
TRACK_PRECEDENCE = ('mod-special', 'buddy-read', 'horror', 'fantasy', 'sci-fi')
REQUIRED_HEADERS = {'title', 'author', 'shelves', 'date started', 'date finished'}
GROUP_BOOK_PATTERN = re.compile(r'^groupBook(\d+)$')
SERIES_SUFFIX_PATTERN = re.compile(r'\s+\((?=[^()]*#\s*\d)[^()]*\)\s*$')
OFFICIAL_DISCUSSION_MONTHS = {
  '2916139': {
    'title': 'A Game of Thrones',
    'authors': ('George R.R. Martin',),
    'year': '2021',
    'month': '10',
    'discussion_url': (
      'https://www.goodreads.com/topic/show/'
      '22097499-a-game-of-thrones-oct-2021-spoilers'),
  },
  '2916140': {
    'title': 'To Be Taught, If Fortunate',
    'authors': ('Becky Chambers',),
    'year': '2021',
    'month': '10',
    'discussion_url': (
      'https://www.goodreads.com/topic/show/'
      '22102303-to-be-taught-if-fortunate-overall-discussion-oct-2021-spoilers'),
  },
}


def natural_goodreads_author(value):
  """Normalize Goodreads' inverted display name without guessing odd commas."""
  value = normalize_line(value)
  parts = [part.strip() for part in value.split(',') if part.strip()]
  if len(parts) == 2:
    return normalize_line(f'{parts[1]} {parts[0]}')
  if len(parts) == 3 and is_author_suffix(parts[2]):
    return normalize_line(f'{parts[1]} {parts[0]}, {parts[2]}')
  return value


def clean_goodreads_title(value):
  value = normalize_line(value)
  return SERIES_SUFFIX_PATTERN.sub('', value).strip()


def parse_goodreads_date(value):
  value = normalize_line(value)
  if not value:
    return ''
  try:
    return datetime.strptime(value, '%Y/%m/%d').date().isoformat()
  except ValueError:
    return ''


class DragonsJetpacksParser(ListParserBase):
  """
  Parse and paginate the public Goodreads group shelf.

  Invariants:
  - Every fetched page must retain the exact group/shelf contract.
  - A linked-page failure aborts the refresh so a partial history is not cached.
  - Missing source dates remain missing; year shelves are not converted to
    invented months or days.
  """

  FILTER_CATEGORIES = (
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    CATEGORY_SCIENCE_FICTION,
    CATEGORY_FANTASY,
  )

  def parse(
      self, html, base_url=SHELF_URL, name=NAME, fetch_url=None,
      fetch_error=None, log=None, progress=None):
    page_url = self.validated_page_url(base_url)
    seen_pages = set()
    seen_records = set()
    rows = []
    notes = []
    page_number = 0
    estimated_pages = 1

    while True:
      page_number += 1
      if page_number > MAX_PAGES:
        raise ValueError(
          f'{NAME} pagination exceeded the {MAX_PAGES}-page safety limit.')
      page_key = self.page_key(page_url)
      if page_key in seen_pages:
        raise ValueError(f'{NAME} pagination looped at {page_url}.')
      seen_pages.add(page_key)

      soup, table, headers = self.require_real_shelf_page(html, page_url)
      estimated_pages = max(
        estimated_pages, self.pagination_page_count(soup, page_url))
      page_rows = table.find_all('tr', id=GROUP_BOOK_PATTERN)
      for row in page_rows:
        record_id = GROUP_BOOK_PATTERN.match(row.get('id', '')).group(1)
        if record_id in seen_records:
          continue
        try:
          parsed = self.parse_row(row, headers, page_url, record_id)
        except ValueError as err:
          notes.append(f'{NAME} skipped groupBook{record_id}: {err}')
          continue
        seen_records.add(record_id)
        rows.append(parsed)

      if progress is not None:
        progress(
          page_number,
          max(page_number, estimated_pages),
          f'Parsed {NAME} shelf page {page_number}')
      next_url = self.next_page_url(soup, page_url)
      if not next_url:
        break
      if fetch_url is None:
        raise ValueError(f'{NAME} pagination requires a fetch callback.')
      if page_number >= MAX_PAGES:
        raise ValueError(
          f'{NAME} pagination exceeded the {MAX_PAGES}-page safety limit.')
      try:
        html = fetch_url(next_url)
      except Exception as err:
        if fetch_error is not None:
          fetch_error(next_url, err, {'position': str(page_number + 1)})
        raise
      page_url = next_url

    if not rows:
      raise ValueError(f'No {NAME} group-read rows were parsed.')
    rows.sort(key=self.row_sort_key)
    for position, row in enumerate(rows, 1):
      row['position'] = str(position)
      row.pop('_group_book_id', None)

    list_source = parsed_source(name, base_url, SOURCE_ID)
    entries = [self.entry_from_row(row, list_source) for row in rows]
    parsed = {
      'name': name,
      'source': list_source,
      'entries': entries,
      'match_series': False,
    }
    if notes:
      parsed['notes'] = notes
    if log is not None:
      log(f'Parsed {len(entries)} {NAME} group-read selections from {page_number} page(s).')
    return parsed

  def require_real_shelf_page(self, html, page_url):
    self.validated_page_url(page_url)
    soup = BeautifulSoup(html or '', 'html.parser')
    title = normalize_line(soup.title.get_text(' ', strip=True) if soup.title else '')
    table = soup.select_one('table#groupBooks')
    if table is None:
      raise ValueError(
        f'{NAME} returned a login, challenge, empty, or unrecognized shelf page.')
    headers = self.header_indexes(table)
    if not REQUIRED_HEADERS.issubset(headers):
      missing = ', '.join(sorted(REQUIRED_HEADERS - set(headers)))
      raise ValueError(f'{NAME} shelf table is missing required columns: {missing}.')
    if not table.find('tr', id=GROUP_BOOK_PATTERN):
      raise ValueError(f'{NAME} shelf table did not contain group-book rows.')
    title_key = title.casefold()
    if 'dragons & jetpacks' not in title_key or 'group-read shelf' not in title_key:
      raise ValueError(f'{NAME} returned an unrecognized Goodreads shelf title.')
    return soup, table, headers

  def header_indexes(self, table):
    header_row = table.find('tr')
    if header_row is None:
      return {}
    return {
      normalize_line(cell.get_text(' ', strip=True)).casefold(): index
      for index, cell in enumerate(header_row.find_all(['th', 'td'], recursive=False))
      if normalize_line(cell.get_text(' ', strip=True))
    }

  def parse_row(self, row, headers, page_url, record_id):
    cells = row.find_all('td', recursive=False)
    required_index = max(headers[header] for header in REQUIRED_HEADERS)
    if len(cells) <= required_index:
      raise ValueError('row has fewer cells than the shelf header')

    book_link = self.first_text_link(row, r'/book/show/')
    author_links = self.text_links(row, r'/author/show/')
    activity_link = row.find('a', href=re.compile(r'/group/show_book/'))
    if book_link is None or not author_links or activity_link is None:
      raise ValueError('row is missing a book, author, or activity link')
    activity_url = urljoin(page_url, activity_link.get('href') or '')
    self.validate_activity_url(activity_url, record_id)

    raw_title = normalize_line(book_link.get_text(' ', strip=True))
    title = clean_goodreads_title(raw_title)
    authors = [
      natural_goodreads_author(link.get_text(' ', strip=True))
      for link in author_links
    ]
    authors = [author for author in authors if author]
    if not title or not authors:
      raise ValueError('row has an empty title or author')

    shelf_cell = cells[headers['shelves']]
    shelves = self.shelf_labels(shelf_cell)
    if 'group-read' not in shelves:
      raise ValueError('row is not explicitly on the group-read shelf')
    core_labels = [label for label in shelves if label in CORE_LABELS]
    primary_track = next(
      (label for label in TRACK_PRECEDENCE if label in core_labels), '')
    year_shelves = [label for label in shelves if re.fullmatch(r'\d{4}', label)]

    raw_start = normalize_line(cells[headers['date started']].get_text(' ', strip=True))
    raw_end = normalize_line(cells[headers['date finished']].get_text(' ', strip=True))
    start_date = parse_goodreads_date(raw_start)
    end_date = parse_goodreads_date(raw_end)
    if raw_start and not start_date:
      raise ValueError(f'row has an invalid start date: {raw_start}')
    if raw_end and not end_date:
      raise ValueError(f'row has an invalid finish date: {raw_end}')
    if start_date and end_date and end_date < start_date:
      raise ValueError('row finish date is earlier than its start date')

    discussion_month = self.official_discussion_month(
      record_id, title, authors, year_shelves)
    # Goodreads can leave an old year shelf on a row after moderators assign
    # explicit dates. The date is the higher-information source field.
    selection_year = (
      start_date[:4] if start_date
      else discussion_month.get('year') if discussion_month
      else year_shelves[0] if year_shelves else '')
    selection_type = (
      'mod_pick' if primary_track == 'mod-special'
      else 'buddy_read' if primary_track == 'buddy-read'
      else 'group_read')

    parsed = {
      'position': '',
      'title': title,
      'authors': authors,
      'activity_url': activity_url,
      'book_url': urljoin(page_url, book_link.get('href') or ''),
      'author_url': urljoin(page_url, author_links[0].get('href') or ''),
      'source_record_id': f'goodreads-group-book:{record_id}',
      'selection_type': selection_type,
      '_group_book_id': int(record_id),
    }
    if raw_title != title:
      parsed['raw_title'] = raw_title
    if core_labels:
      parsed['shelf_labels'] = core_labels
    if primary_track:
      parsed['theme_or_track'] = primary_track
    if start_date:
      parsed['discussion_start_date'] = start_date
      parsed['event_date'] = start_date
      parsed['selection_month'] = str(int(start_date[5:7]))
    elif discussion_month:
      # The topic title supports a month, but not an exact day.
      parsed['selection_month'] = str(int(discussion_month['month']))
    if discussion_month:
      parsed['discussion_url'] = discussion_month['discussion_url']
    if end_date:
      parsed['discussion_end_date'] = end_date
    if selection_year:
      parsed['selection_year'] = selection_year
    if start_date and primary_track:
      parsed['event_group_id'] = (
        f'dragons-jetpacks:{start_date}:{primary_track}')
    return parsed

  def shelf_labels(self, shelf_cell):
    labels = []
    for link in shelf_cell.find_all('a', href=True):
      href = urljoin(SHELF_URL, link.get('href') or '')
      query = parse_qs(urlparse(href).query)
      values = query.get('shelf') or []
      label = normalize_line(values[0] if values else link.get_text(' ', strip=True)).casefold()
      if label and label not in labels:
        labels.append(label)
    return labels

  def first_text_link(self, node, path_fragment):
    links = self.text_links(node, path_fragment)
    return links[0] if links else None

  def text_links(self, node, path_fragment):
    return [
      link for link in node.find_all('a', href=True)
      if path_fragment in (link.get('href') or '')
      and normalize_line(link.get_text(' ', strip=True))
    ]

  def validate_activity_url(self, url, record_id):
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if (
        parsed.scheme != 'https'
        or parsed.netloc.casefold() != 'www.goodreads.com'
        or parsed.path != f'/group/show_book/{GROUP_SLUG}'
        or query.get('group_book_id') != [str(record_id)]):
      raise ValueError('row activity link does not match its group-book ID')

  def official_discussion_month(self, record_id, title, authors, year_shelves):
    correction = OFFICIAL_DISCUSSION_MONTHS.get(str(record_id))
    if not correction:
      return {}
    if (
        title != correction['title']
        or tuple(authors) != correction['authors']
        or correction['year'] not in year_shelves):
      return {}
    return correction

  def next_page_url(self, soup, page_url):
    link = soup.select_one('a.next_page[rel~="next"]')
    if link is None or not link.get('href'):
      return ''
    return self.validated_page_url(urljoin(page_url, link['href']))

  def pagination_page_count(self, soup, page_url):
    """Return a numeric progress denominator from same-shelf page links."""
    page_count = self.page_key(page_url)[3]
    for link in soup.find_all('a', href=True):
      parsed = urlparse(urljoin(page_url, link.get('href') or ''))
      query = parse_qs(parsed.query)
      page_values = query.get('page') or []
      if (
          parsed.netloc.casefold() != 'www.goodreads.com'
          or parsed.path != SHELF_PATH
          or query.get('shelf') != ['group-read']
          or query.get('per_page') != ['100']
          or len(page_values) != 1
          or not page_values[0].isdigit()):
        continue
      page_count = max(page_count, int(page_values[0]))
    return min(page_count, MAX_PAGES)

  def validated_page_url(self, url):
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if (
        parsed.scheme != 'https'
        or parsed.netloc.casefold() != 'www.goodreads.com'
        or parsed.path != SHELF_PATH
        or query.get('shelf') != ['group-read']
        or query.get('per_page') != ['100']):
      raise ValueError(f'{NAME} pagination left the official group-read shelf: {url}')
    page_values = query.get('page', ['1'])
    if len(page_values) != 1 or not page_values[0].isdigit() or int(page_values[0]) < 1:
      raise ValueError(f'{NAME} returned an invalid pagination URL: {url}')
    return url

  def page_key(self, url):
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    return (
      parsed.scheme.casefold(), parsed.netloc.casefold(), parsed.path,
      int(query.get('page', ['1'])[0]), query.get('per_page', [''])[0],
      query.get('shelf', [''])[0])

  def row_sort_key(self, row):
    try:
      year = int(row.get('selection_year') or 9999)
    except ValueError:
      year = 9999
    start_date = row.get('discussion_start_date') or ''
    try:
      month = int(row.get('selection_month') or 13)
    except ValueError:
      month = 13
    return (
      year,
      month,
      0 if start_date else 1,
      start_date,
      row.get('_group_book_id', 0),
    )

  def entry_from_row(self, row, list_source):
    metadata = {
      key: value
      for key, value in row.items()
      if key not in {'position', 'title', 'authors', 'activity_url'}
    }
    return imported_entry(
      row['position'],
      row['title'],
      row['authors'],
      source=entry_source_object(
        row['activity_url'], NAME, SOURCE_ID, list_source=list_source),
      **metadata)
