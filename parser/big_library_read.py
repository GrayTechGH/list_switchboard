#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Parsers for the global Big Library Read and Libby Reads programs.

Maintenance notes:
- Remote results are accepted only as complete replacements. A partial remote
  parse must never be combined with the packaged history ledger.
- Big Library Read first tries the live official archive, then a complete,
  time-bounded union of archived official pages from the Internet Archive.
  The JSON ledger is used only if both remote paths fail validation.
- Big Library Read ended in July 2025. Libby Reads Global starts with the
  November 2025 Libby & Sora Reads event; regional Libby Reads cards are out of
  scope.
- The packaged ledger is a source-unavailable fallback, not an enrichment
  layer. Its per-entry URLs retain the official provenance used to verify it.
"""

import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, UnicodeDammit

try:
  from calibre_plugins.list_switchboard.parser.base import (
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    entry_source_object,
    imported_entry,
    ListParserBase,
    parsed_source,
  )
except ImportError:
  from .base import (
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    entry_source_object,
    imported_entry,
    ListParserBase,
    parsed_source,
  )


HISTORY_FILE = 'big_library_read_history.json'
BIG_LIBRARY_READ_URL = 'https://www.biglibraryread.com/past-titles/'
LIBBY_READS_URL = 'https://www.libbylife.com/libby-reads'
BIG_LIBRARY_READ_WAYBACK_SPECS = (
  (
    'https://web.archive.org/web/20190717184423id_/'
    'https://biglibraryread.com/past-titles/',
    '2014-01-01', '2019-07-01'),
  (
    'https://web.archive.org/web/20231206134935id_/'
    'https://biglibraryread.com/past-titles/',
    '2019-07-02', '2023-12-31'),
  (
    'https://web.archive.org/web/20250805020440id_/'
    'https://www.biglibraryread.com/past-titles/',
    '2024-01-01', '2025-07-31'),
)
BIG_LIBRARY_READ_LAUNCH_SPECS = (
  {
    'title': 'The Four Corners of the Sky',
    'authors': ['Michael Malone'],
    'start_date': '2013-05-15',
    'end_date': '2013-06-01',
    'source_url': (
      'https://company.overdrive.com/2013/05/16/'
      'big-library-read-ebook-event-rolls-out/'),
  },
  {
    'title': 'Nancy Clancy: Super Sleuth',
    'authors': ["Jane O'Connor"],
    'start_date': '2013-09-16',
    'end_date': '2013-09-30',
    'source_url': (
      'https://company.overdrive.com/2013/09/18/'
      '2nd-big-library-read-launches-with-popular-childrens-ebook/'),
  },
)
BLOCKED_MARKERS = (
  'attention required',
  'browser update required',
  'enable javascript and cookies to continue',
  'please wait for verification',
  'security verification',
  'you have been blocked',
)
MONTHS = {
  'january': 1, 'february': 2, 'march': 3, 'april': 4,
  'may': 5, 'june': 6, 'july': 7, 'august': 8,
  'september': 9, 'october': 10, 'november': 11, 'december': 12,
}
MONTH_PATTERN = '|'.join(MONTHS)
DATE_RANGE_RE = re.compile(
  rf'\b(?P<start_month>{MONTH_PATTERN})\s+(?P<start_day>\d{{1,2}})'
  r'(?:st|nd|rd|th)?\s*[-\u2013\u2014]\s*'
  rf'(?:(?P<end_month>{MONTH_PATTERN})\s+)?(?P<end_day>\d{{1,2}})'
  r'(?:st|nd|rd|th)?(?:\s*,\s*|\s+)?(?P<year>(?:19|20)\d{2})?\b',
  re.I)
AUTHOR_SPLIT_RE = re.compile(r'\s*(?:&|\band\b)\s*', re.I)
LIBBY_ARCHIVE_SPECS = (
  ('https://pages.libbylife.com/LibbySoraReads', 2025),
  ('https://www.libbylife.com/events/libby-reads-meet-the-neighbors', None),
  ('https://www.libbylife.com/events/libby-reads-i-see-youve-called-in-dead', None),
  ('https://www.libbylife.com/events/libby-reads-secrets-of-the-broken-house', None),
)
LIBBY_REQUIRED_TITLES = frozenset((
  'the village beyond the mist',
  'meet the neighbors',
  'i see you ve called in dead',
  'secrets of the broken house',
))


def normalize_text(value):
  return re.sub(r'\s+', ' ', str(value or '').replace('\xa0', ' ')).strip()


def normalize_identity(value):
  value = normalize_text(value).replace('\u2018', "'").replace('\u2019', "'")
  return re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip()


def clean_title(value):
  return normalize_text(value).strip(' "\'\u2018\u2019\u201c\u201d,.;:')


def slug(value):
  return re.sub(r'[^a-z0-9]+', '-', normalize_identity(value)).strip('-')


def source_url_from(base_url, href):
  if 'web.archive.org/web/' in base_url and 'id_/' in base_url:
    prefix, original_url = base_url.split('id_/', 1)
    return prefix + 'id_/' + urljoin(original_url, href)
  return urljoin(base_url, href)


def split_authors(value):
  value = normalize_text(value)
  value = re.sub(r'^(?:written\s+)?by\s+', '', value, flags=re.I)
  value = re.sub(r'\s+Authors?\b', '', value, flags=re.I)
  authors = []
  for part in AUTHOR_SPLIT_RE.split(value):
    author = normalize_text(part).strip(' ,.;')
    if author and author not in authors:
      authors.append(author)
  return authors


def parse_date_range(value, fallback_year=None):
  match = DATE_RANGE_RE.search(normalize_text(value))
  if match is None:
    return '', ''
  year = int(match.group('year') or fallback_year or 0)
  if not year:
    return '', ''
  start_month = MONTHS[match.group('start_month').casefold()]
  end_month = MONTHS[(match.group('end_month') or match.group('start_month')).casefold()]
  start_day = int(match.group('start_day'))
  end_day = int(match.group('end_day'))
  end_year = year + 1 if end_month < start_month else year
  try:
    return (
      date(year, start_month, start_day).isoformat(),
      date(end_year, end_month, end_day).isoformat(),
    )
  except ValueError:
    return '', ''


def reject_interstitial(html, source_name):
  markup = html or ''
  if isinstance(markup, bytes):
    markup = UnicodeDammit(markup).unicode_markup
  soup = BeautifulSoup(markup, 'html.parser')
  text = normalize_text(soup.get_text(' ', strip=True))
  if not text:
    raise ValueError(f'{source_name} returned an empty page.')
  lowered = text.casefold()
  # Some legitimate campaign pages include a generic JavaScript/cookie warning
  # in their footer. Treat a marker as a blocking response only when the page
  # has no substantive rendered body.
  if (
      any(marker in lowered for marker in BLOCKED_MARKERS)
      and (len(text) < 1000 or soup.find(['h1', 'h2']) is None)):
    raise ValueError(f'{source_name} returned a verification or blocking page.')
  return soup


def load_history_ledger():
  try:
    from importlib import resources
    package = 'calibre_plugins.list_switchboard.parser.data'
    text = resources.files(package).joinpath(HISTORY_FILE).read_text(encoding='utf-8')
  except Exception:
    text = (Path(__file__).with_name('data') / HISTORY_FILE).read_text(encoding='utf-8')
  data = json.loads(text)
  if data.get('schema_version') != 1 or not isinstance(data.get('collections'), dict):
    raise ValueError('The packaged community-read ledger has an unsupported schema.')
  for collection_name, rows in data['collections'].items():
    if not isinstance(rows, list) or not rows:
      raise ValueError(f'The packaged {collection_name} ledger is empty.')
    seen = set()
    for row in rows:
      required = (
        'event_group_id', 'source_record_id', 'title', 'authors', 'start_date',
        'end_date', 'program_era', 'region', 'source_url')
      if any(not row.get(field) for field in required):
        raise ValueError(f'The packaged {collection_name} ledger has an incomplete row.')
      if row['source_record_id'] in seen:
        raise ValueError(f'The packaged {collection_name} ledger has duplicate record IDs.')
      seen.add(row['source_record_id'])
      if row['region'] != 'Global':
        raise ValueError(f'The packaged {collection_name} ledger contains a regional row.')
      try:
        if date.fromisoformat(row['end_date']) < date.fromisoformat(row['start_date']):
          raise ValueError
      except (TypeError, ValueError):
        raise ValueError(f'The packaged {collection_name} ledger has invalid dates.')
  return data


class CommunityReadParserBase(ListParserBase):

  FILTER_CATEGORIES = (CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,)
  COLLECTION = ''
  CLUB_NAME = ''
  SOURCE_ID = ''
  PROGRAM_ERA = ''

  def ledger_rows(self):
    return [dict(row) for row in load_history_ledger()['collections'][self.COLLECTION]]

  def parse_ledger(self, reason):
    reason = normalize_text(reason).split('\n', 1)[0]
    notes = [
      'Packaged history used because the complete official remote list could '
      f'not be scraped: {reason or "source unavailable"}'
    ]
    return self.result_from_rows(
      self.ledger_rows(), self.CLUB_NAME, self.ledger_source_url(), notes)

  def ledger_source_url(self):
    return BIG_LIBRARY_READ_URL if self.COLLECTION == 'big_library_read' else LIBBY_READS_URL

  def result_from_rows(self, rows, name, source_url, notes=None):
    rows = list(rows)
    rows.sort(key=lambda row: row['start_date'])
    list_source = parsed_source(name, source_url, self.SOURCE_ID)
    entries = []
    for position, row in enumerate(rows, 1):
      start_date = row['start_date']
      entry_source = entry_source_object(
        row.get('source_url'), name, self.SOURCE_ID, list_source=list_source)
      entries.append(imported_entry(
        position,
        row['title'],
        row['authors'],
        source=entry_source,
        club_name=name,
        selection_type='global_read',
        region='Global',
        program_era=row.get('program_era') or self.PROGRAM_ERA,
        event_date=start_date,
        discussion_start_date=start_date,
        discussion_end_date=row['end_date'],
        selection_year=start_date[:4],
        selection_month=str(int(start_date[5:7])),
        event_group_id=row['event_group_id'],
        source_record_id=row['source_record_id'],
        selection_url=row.get('source_url'),
      ))
    return {
      'name': name,
      'source': list_source,
      'entries': entries,
      'notes': list(notes or ()),
      'match_series': False,
    }

  def remote_row(self, title, authors, start_date, end_date, source_url):
    prefix = 'blr' if self.COLLECTION == 'big_library_read' else 'libby-global'
    return {
      'event_group_id': f'{prefix}-{start_date}',
      'source_record_id': f'{prefix}-{start_date}-{slug(title)}',
      'title': clean_title(title),
      'authors': list(authors),
      'start_date': start_date,
      'end_date': end_date,
      'program_era': self.PROGRAM_ERA,
      'region': 'Global',
      'source_url': source_url,
    }


class BigLibraryReadParser(CommunityReadParserBase):
  """Parse live or archived-official Big Library Read history.

  The live archive is authoritative when complete. Its known incomplete and
  retroactively malformed states are rejected. Archived snapshots are sliced
  by capture era so a later bad edit cannot replace a contemporaneous record.
  """

  COLLECTION = 'big_library_read'
  CLUB_NAME = 'Big Library Read'
  SOURCE_ID = 'big_library_read'
  PROGRAM_ERA = 'Big Library Read'
  REQUIRED_REMOTE_COUNT = 36

  def parse(self, html, base_url=BIG_LIBRARY_READ_URL, name=None, fetch_url=None):
    if fetch_url is None:
      raise ValueError('Big Library Read detail-page fetching is unavailable.')
    live_error = None
    try:
      rows = self.archive_rows(reject_interstitial(html, self.CLUB_NAME), base_url)
      self.validate_complete(rows)
      for row in rows:
        detail = reject_interstitial(
          fetch_url(row['source_url']), 'Big Library Read detail page')
        detail_title = self.detail_title(detail)
        if normalize_identity(detail_title) != normalize_identity(row['title']):
          raise ValueError(
            f'Big Library Read detail page did not confirm {row["title"]}.')
      return self.result_from_rows(rows, name or self.CLUB_NAME, base_url)
    except Exception as err:
      if err.__class__.__name__ == 'ImportCancelledError':
        raise
      live_error = err

    try:
      rows = self.archived_remote_rows(fetch_url)
      self.validate_complete(rows)
      notes = [
        'Internet Archive snapshots of the official Big Library Read archive '
        'were used because the live archive failed completeness validation: '
        f'{normalize_text(live_error)}'
      ]
      return self.result_from_rows(
        rows, name or self.CLUB_NAME, BIG_LIBRARY_READ_WAYBACK_SPECS[-1][0], notes)
    except Exception as archive_error:
      if archive_error.__class__.__name__ == 'ImportCancelledError':
        raise
      raise ValueError(
        f'Live archive failed ({normalize_text(live_error)}); Internet Archive '
        f'union failed ({normalize_text(archive_error)}).')

  def archived_remote_rows(self, fetch_url):
    rows = []
    for spec in BIG_LIBRARY_READ_LAUNCH_SPECS:
      soup = reject_interstitial(
        fetch_url(spec['source_url']), 'Big Library Read launch article')
      text = normalize_identity(soup.get_text(' ', strip=True))
      required = [normalize_identity(spec['title'])]
      required.extend(normalize_identity(author) for author in spec['authors'])
      if any(value not in text for value in required):
        raise ValueError('A 2013 official launch article failed identity validation.')
      rows.append(self.remote_row(
        spec['title'], spec['authors'], spec['start_date'], spec['end_date'],
        spec['source_url']))

    for source_url, first_date, last_date in BIG_LIBRARY_READ_WAYBACK_SPECS:
      soup = reject_interstitial(
        fetch_url(source_url), 'Internet Archive Big Library Read snapshot')
      snapshot_rows = self.archive_rows(soup, source_url)
      bounded = [
        row for row in snapshot_rows
        if first_date <= row['start_date'] <= last_date]
      if not bounded:
        raise ValueError(
          f'Internet Archive snapshot exposed no rows in {first_date[:4]}-'
          f'{last_date[:4]}.')
      rows.extend(bounded)
    return rows

  def archive_rows(self, soup, base_url):
    rows = []
    seen_urls = set()
    cards = list(soup.select('div.posts-item-no-button'))
    cards.extend(soup.select('div.col-md-3.col-sm-6.over-auto'))
    # This final shape supports both older official markup and focused fixture
    # pages; anchors already enclosed by a recognized card are skipped.
    cards.extend(
      anchor for anchor in soup.find_all('a', href=True)
      if anchor.find_parent(
        'div', class_=lambda value: value and (
          'posts-item-no-button' in value or 'over-auto' in value)) is None)
    for card in cards:
      anchor = card if card.name == 'a' else card.find('a', href=True)
      if anchor is None:
        continue
      source_url = source_url_from(base_url, anchor.get('href', ''))
      if '/past-titles/' not in urlparse(source_url).path.rstrip('/') + '/':
        continue
      if source_url.rstrip('/') == base_url.rstrip('/') or source_url in seen_urls:
        continue
      heading = card.find(['h2', 'h6'])
      title = clean_title(heading.get_text(' ', strip=True) if heading else '')
      text = normalize_text(card.get_text(' ', strip=True))
      start_date, end_date = parse_date_range(text)
      author_node = heading.find_next_sibling(['h3', 'p']) if heading else None
      if author_node is not None:
        authors = split_authors(author_node.get_text(' ', strip=True))
      else:
        author_match = re.search(
          r'\bby\s+(.+?)(?=\s+(?:' + MONTH_PATTERN + r')\s+\d{1,2}\b)',
          text, re.I)
        authors = split_authors(author_match.group(1)) if author_match else []
      if card.name == 'a' and (not title or not start_date or not end_date):
        continue
      if not title or not authors or not start_date or not end_date:
        raise ValueError('Big Library Read archive contains a malformed required card.')
      seen_urls.add(source_url)
      rows.append(self.remote_row(title, authors, start_date, end_date, source_url))
    if not rows:
      raise ValueError('Big Library Read archive did not expose past-title cards.')
    return rows

  def detail_title(self, soup):
    for heading in soup.find_all(['h1', 'h2']):
      title = clean_title(heading.get_text(' ', strip=True))
      if title and title.casefold() not in ('past titles', 'big library read'):
        return title
    return ''

  def validate_complete(self, rows):
    identities = {(row['start_date'], normalize_identity(row['title'])) for row in rows}
    if len(rows) != self.REQUIRED_REMOTE_COUNT or len(identities) != self.REQUIRED_REMOTE_COUNT:
      raise ValueError(
        f'Big Library Read archive exposed {len(identities)} unique selections; '
        f'exactly {self.REQUIRED_REMOTE_COUNT} are required.')
    if any(
        not row['title'] or not row['authors']
        or date.fromisoformat(row['end_date']) < date.fromisoformat(row['start_date'])
        for row in rows):
      raise ValueError('Big Library Read archive contains invalid required metadata.')
    starts = {row['start_date'] for row in rows}
    if '2013-05-15' not in starts or '2025-07-17' not in starts:
      raise ValueError('Big Library Read archive is missing an earliest or latest boundary.')


class LibbyReadsGlobalParser(CommunityReadParserBase):
  """Parse global-only Libby Reads landing, archive, and event pages."""

  COLLECTION = 'libby_reads_global'
  CLUB_NAME = 'Libby Reads Global'
  SOURCE_ID = 'libby_reads_global'
  PROGRAM_ERA = 'Libby Reads'

  def parse(self, html, base_url=LIBBY_READS_URL, name=None, fetch_url=None):
    soup = reject_interstitial(html, self.CLUB_NAME)
    if fetch_url is None:
      raise ValueError('Libby Reads event-page fetching is unavailable.')
    specs = list(LIBBY_ARCHIVE_SPECS)
    known_urls = {url for url, _year in specs}
    for anchor in soup.find_all('a', href=True):
      url = urljoin(base_url, anchor.get('href', ''))
      if '/events/' not in urlparse(url).path or url in known_urls:
        continue
      container = anchor.find_parent('li') or anchor
      text = normalize_text(container.get_text(' ', strip=True))
      if not re.search(r'\bLibby\s+Reads\s*\(?GLOBAL\)?\b', text, re.I):
        continue
      specs.append((url, None))
      known_urls.add(url)

    rows = []
    seen = set()
    for source_url, fallback_year in specs:
      detail = reject_interstitial(fetch_url(source_url), 'Libby Reads event page')
      row = self.detail_row(detail, source_url, fallback_year=fallback_year)
      key = (row['start_date'], normalize_identity(row['title']))
      if key not in seen:
        seen.add(key)
        rows.append(row)
    self.validate_complete(rows)
    return self.result_from_rows(rows, name or self.CLUB_NAME, base_url)

  def detail_row(self, soup, source_url, fallback_year=None):
    heading = soup.find('h1')
    if heading is None:
      heading = soup.find(['h2', 'h3'])
    title = clean_title(heading.get_text(' ', strip=True) if heading else '')
    text = normalize_text(soup.get_text(' ', strip=True))
    author_match = re.search(
      r'Written\s+by\s+(.+?)(?=\s+(?:Translated\s+by|LIBBY\s+READS|'
      + MONTH_PATTERN + r')\b)', text, re.I)
    authors = split_authors(author_match.group(1)) if author_match else []
    start_date, end_date = parse_date_range(text, fallback_year=fallback_year)
    is_global = bool(
      re.search(r'\bLIBBY\s+(?:&\s*SORA\s+)?READS\s*\(?GLOBAL\)?\b', text, re.I)
      or re.search(r'\bglobal\s+(?:ebook|digital)\s+club\b', text, re.I))
    if not title or not authors or not start_date or not end_date or not is_global:
      raise ValueError('Libby Reads event page lacks required global event metadata.')
    return self.remote_row(title, authors, start_date, end_date, source_url)

  def validate_complete(self, rows):
    titles = {normalize_identity(row['title']) for row in rows}
    if not LIBBY_REQUIRED_TITLES <= titles:
      raise ValueError('Libby Reads remote sources are missing a completed or announced global event.')
    if not any(row['start_date'] == '2025-11-18' for row in rows):
      raise ValueError('Libby Reads remote sources are missing the first branded global event.')


def parse_big_library_read(html, base_url=BIG_LIBRARY_READ_URL, name=None, fetch_url=None):
  return BigLibraryReadParser().parse(html, base_url, name=name, fetch_url=fetch_url)


def parse_libby_reads_global(html, base_url=LIBBY_READS_URL, name=None, fetch_url=None):
  return LibbyReadsGlobalParser().parse(html, base_url, name=name, fetch_url=fetch_url)
