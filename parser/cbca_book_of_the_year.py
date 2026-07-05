#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
CBCA Book of the Year parser for official CBCA sources.

Maintenance notes:
- Runtime sources stay official-only: the CBCA archive page, the linked
  1946-on PDF, the awards landing page, and annual shortlist/winner posts.
- CBCA has both pre-award shortlists and post-award Honour Books. Both are
  mapped to `shortlisted` so existing award review filters work.
- Historical PDF labels include Commended, Highly Commended, and Special
  Mention rows. They are imported as non-winners, but are not literal modern
  shortlists.
"""

from datetime import date
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
  from calibre_plugins.list_switchboard.parser.pdf_text import extract_pdf_text # pyright: ignore[reportMissingImports]
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key
  from .pdf_text import extract_pdf_text


AWARD_NAME = 'CBCA Book of the Year'
ARCHIVE_URL = 'https://cbca.org.au/awards-archive/'
AWARDS_URL = 'https://cbca.org.au/awards/'
PDF_URL = (
  'https://cbca.blob.core.windows.net/documents/National/'
  'CBCA%20Awards%201946%20on.pdf')

CATEGORY_OLDER_READERS = 'Older Readers'
CATEGORY_YOUNGER_READERS = 'Younger Readers'
CATEGORY_MIDDLE_READERS = 'Middle Readers'
CATEGORY_EARLY_CHILDHOOD = 'Early Childhood'
CATEGORY_PICTURE_BOOK = 'Picture Book'
CATEGORY_EVE_POWNALL = 'Eve Pownall'
CATEGORY_NEW_ILLUSTRATOR = 'New Illustrator'

ALL_CATEGORY_ALIASES = {
  CATEGORY_OLDER_READERS: (
    'Book of the Year Award for Older Readers',
    'Book of the Year Award: Older Readers',
    'Book of the Year: Older Readers',
    'Book of the Year Older Readers',
    'Book of the Year Award 1946 - 1981',
    'Book of the Year Awards 1946 - 1981',
    'Older Readers',
  ),
  CATEGORY_YOUNGER_READERS: (
    'Book of the Year Award for Younger Readers',
    'Book of the Year Award: Younger Readers',
    'Book of the Year: Younger Readers',
    'Book of the Year Younger Readers',
    'Younger Readers',
  ),
  CATEGORY_MIDDLE_READERS: (
    'Book of the Year Award for Middle Readers',
    'Book of the Year Award: Middle Readers',
    'Book of the Year: Middle Readers',
    'Book of the Year Middle Readers',
    'Middle Readers',
  ),
  CATEGORY_EARLY_CHILDHOOD: (
    'Book of the Year Award for Early Childhood',
    'Book of the Year Award: Early Childhood',
    'Book of the Year: Early Childhood',
    'Early Childhood',
  ),
  CATEGORY_PICTURE_BOOK: (
    'Picture Book of the Year Award',
    'Picture Book of the Year',
    'Picture Book',
  ),
  CATEGORY_EVE_POWNALL: (
    'Book of the Year Award: Eve Pownall Award for Information Books',
    'Eve Pownall Award for Information Books',
    'Eve Pownall Award',
    'Eve Pownall',
  ),
  CATEGORY_NEW_ILLUSTRATOR: (
    'Book of the Year Award for New Illustrator',
    'Book of the Year Award: New Illustrator',
    'CBCA Award for New Illustrator',
    'The CBCA Award for New Illustrator',
    'Crichton Award for New Illustrator',
    'The Crichton Award for New Illustrator',
    'New Illustrator',
  ),
}

RESULT_ORDER = {RESULT_WINNER: 0, RESULT_SHORTLISTED: 1}
SEMANTIC_TAGS = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li')
YEAR_RE = re.compile(r'\b((?:19|20)\d{2})\b')
STAGE_PREFIX_RE = re.compile(
  r'^\s*(Winner|Winners|Joint Winners|Honou?r(?:\s+Books?)?|'
  r'Short\s*List|Shortlist|Shortlisted|Highly Commended|Commended|'
  r'Special Mention|Favo[u]?rable Mention)\s*(?:\||:|-)?\s*(.*)$',
  re.I)
PDF_STAGE_RE = re.compile(
  r'^\s*(?:[-\u2013\u2014]\s*)?(WINNER|WINNERS|JOINT WINNERS|'
  r'HONOU?R BOOKS?|SHORT\s*LIST|SHORTLIST|HIGHLY COMMENDED|COMMENDED|'
  r'SPECIAL MENTION|FAVOU?RABLE MENTION)\s*:?\s*(.*)$',
  re.I)
CREATOR_PREFIX_RE = re.compile(
  r'^\s*(?:'
  r'illustrated by|illus\.?\s*by|ill\.?\s*by|ill\.?|'
  r'written by|text by|by'
  r')\s+',
  re.I)
PUBLISHER_TAILS = (
  'Allen & Unwin', 'Angus & Robertson', 'Australasian Publishing',
  'Berbay Publishing', 'Black Dog Books', 'Bright Light', 'Collins',
  'CSIRO Publishing', 'Ford Street', 'Fremantle', 'Hachette',
  'Hardie Grant Children\'s Publishing', 'HarperCollins', 'Heinemann',
  'Hodder & Stoughton', 'Hutchinson', 'John Sands', 'Lansdowne',
  'Little Hare', 'Lothian', 'Macmillan', 'Magabala Books', 'NLA',
  'Omnibus', 'Oxford University Press', 'Pan Macmillan', 'Penguin',
  'Puffin', 'Rigby', 'Scholastic', 'Text', 'UQP',
  'University of Queensland Press', 'Viking', 'Walker', 'Walker Books',
  'Wild Dog', 'Wild Dog Books',
)
TITLE_START_WORDS = {
  'a', 'an', 'and', 'everything', 'how', 'if', 'once', 'the', 'this',
  'what', 'when', 'where', 'who', 'why',
}


def shortlist_url(year):
  return f'https://cbca.org.au/{int(year)}-shortlist/'


def winners_url(year):
  return f'https://cbca.org.au/{int(year)}-book-of-the-year-award-winners/'


def _category_key(value):
  key = normalize_heading(value)
  key = key.replace('childrens', 'children s')
  return key


class CBCABookOfTheYearParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def __init__(self, category, category_aliases=()):
    self.category = category
    aliases = tuple(category_aliases or ALL_CATEGORY_ALIASES.get(category, (category,)))
    self.category_aliases = aliases
    self.category_keys = {_category_key(alias) for alias in aliases}

  def parse(
      self, html, base_url=ARCHIVE_URL, name=AWARD_NAME, fetch_url=None,
      current_year=None, pdf_page=None, annual_pages=(), awards_page=None,
      log=None, progress=None):
    rows = []
    notes = []
    rows.extend(self.html_rows(html, base_url))
    if self.looks_like_pdf_text(html, base_url):
      rows.extend(self.pdf_rows(html, base_url))

    pdf_url = self.pdf_url_from_archive(html, base_url) or PDF_URL
    if pdf_page is not None:
      rows.extend(self.pdf_rows(pdf_page, pdf_url))
    elif fetch_url is not None:
      try:
        if progress is not None:
          progress(1, 1, 'Fetching CBCA 1946-on PDF')
        rows.extend(self.pdf_rows(fetch_url(pdf_url), pdf_url))
      except Exception as err:
        notes.append(f'CBCA 1946-on PDF could not be fetched: {pdf_url}: {err}')
        if log is not None:
          log(f'CBCA PDF failed: {pdf_url}: {err}')

    for page_url, page_html in annual_pages or ():
      rows.extend(self.html_rows(page_html, page_url))

    current_year = int(current_year or date.today().year)
    if fetch_url is not None:
      for index, page_url in enumerate(self.annual_fetch_targets(
          html, base_url, awards_page, fetch_url, current_year, rows, notes, log), 1):
        try:
          if progress is not None:
            progress(index, 1, f'Fetching CBCA annual page {index}')
          rows.extend(self.html_rows(fetch_url(page_url), page_url))
        except Exception as err:
          notes.append(f'CBCA annual page could not be fetched: {page_url}: {err}')
          if log is not None:
            log(f'CBCA annual page failed: {page_url}: {err}')

    entries = self.entries_from_rows(self.dedupe_rows(rows))
    if not entries:
      raise ValueError(f'No {name} entries found on official CBCA sources.')
    notes.extend(self.coverage_notes(entries, current_year))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def annual_fetch_targets(
      self, archive_html, base_url, awards_page, fetch_url, current_year,
      rows, notes, log):
    links = list(self.annual_links(archive_html, base_url))
    if awards_page is None:
      try:
        awards_page = fetch_url(AWARDS_URL)
      except Exception as err:
        notes.append(f'CBCA awards page could not be fetched: {AWARDS_URL}: {err}')
        if log is not None:
          log(f'CBCA awards page failed: {AWARDS_URL}: {err}')
        awards_page = ''
    links.extend(self.annual_links(awards_page, AWARDS_URL))

    max_year = max((int(row['award_year']) for row in rows), default=current_year - 1)
    for year in range(max_year + 1, current_year + 1):
      links.append(shortlist_url(year))
      links.append(winners_url(year))
    return tuple(dict.fromkeys(links))

  def html_rows(self, html, base_url):
    year = self.year_from_text(base_url)
    default_result = RESULT_SHORTLISTED if 'shortlist' in normalize_heading(base_url) else None
    rows = []
    current_year = year
    current_category = None
    current_result = default_result

    for line in self.text_lines(html):
      line_year = self.standalone_year(line)
      if line_year is not None:
        current_year = line_year
        current_result = default_result
        continue
      category = self.category_from_text(line)
      if category is not None:
        current_category = category
        current_result = default_result
        continue
      result, remainder = self.stage_from_line(line)
      if result is not None:
        current_result = result
        line = remainder
        if not line:
          continue
      if self.is_non_entry_line(line):
        continue
      if (
          current_year is None
          or current_category is None
          or current_result not in {RESULT_WINNER, RESULT_SHORTLISTED}
          or not self.category_matches(current_category)):
        continue
      row = self.row_from_entry_text(
        current_year, current_category, line, current_result, base_url)
      if row is not None:
        rows.append(row)
    return rows

  def pdf_rows(self, pdf_or_text, source_url=PDF_URL):
    return self.rows_from_pdf_text(extract_pdf_text(pdf_or_text), source_url)

  def rows_from_pdf_text(self, text, source_url):
    rows = []
    current_year = None
    current_category = None
    current_result = None

    for line in self.pdf_lines(text):
      category = self.category_from_text(line)
      if category is not None:
        current_category = category
        current_result = None
        continue

      year_match = re.match(r'^\s*((?:19|20)\d{2})\s*(.*)$', line)
      if year_match is not None:
        current_year = int(year_match.group(1))
        line = normalize_line(year_match.group(2).lstrip('-\u2013\u2014 '))
        current_result = None
        if not line or self.none_recorded(line):
          continue

      result, remainder = self.pdf_stage_from_line(line)
      if result is not None:
        current_result = result
        line = remainder
        if not line or self.none_recorded(line):
          continue

      if (
          current_year is None
          or current_category is None
          or current_result not in {RESULT_WINNER, RESULT_SHORTLISTED}
          or not self.category_matches(current_category)):
        continue
      row = self.row_from_pdf_entry(
        current_year, current_category, line, current_result, source_url)
      if row is not None:
        rows.append(row)
    return rows

  def text_lines(self, html):
    soup = BeautifulSoup(html or '', 'html.parser')
    for removable in soup.find_all(['script', 'style', 'sup']):
      removable.decompose()
    for br in soup.find_all('br'):
      br.replace_with('\n')
    lines = []
    for node in soup.find_all(SEMANTIC_TAGS):
      text = node.get_text('\n', strip=True).replace('\xa0', ' ')
      for line in text.splitlines():
        line = normalize_line(line)
        if line:
          lines.append(line)
    if lines:
      return lines
    return [normalize_line(line) for line in soup.get_text('\n').splitlines()
            if normalize_line(line)]

  def pdf_lines(self, text):
    text = (text or '').replace('\r', '\n')
    text = re.sub(r'CBCA Book of the Year Awards 1946\s*-\s*\d+', '\n', text)
    text = re.sub(
      r'\b((?:19|20)\d{2})\s*[-\u2013\u2014]?\s*'
      r'(WINNER|WINNERS|JOINT WINNERS|HONOU?R BOOKS?|SHORT\s*LIST|'
      r'HIGHLY COMMENDED|COMMENDED|SPECIAL MENTION|FAVOU?RABLE MENTION)\b',
      r'\n\1 \2',
      text,
      flags=re.I)
    lines = []
    for raw_line in text.splitlines():
      line = normalize_line(raw_line)
      if not line or self.skip_pdf_line(line):
        continue
      lines.append(line)
    return lines

  def stage_from_line(self, line):
    match = STAGE_PREFIX_RE.match(line)
    if match is None:
      return None, line
    return self.result_from_stage(match.group(1)), normalize_line(match.group(2))

  def pdf_stage_from_line(self, line):
    match = PDF_STAGE_RE.match(line)
    if match is None:
      return None, line
    return self.result_from_stage(match.group(1)), normalize_line(match.group(2))

  def result_from_stage(self, stage):
    key = normalize_heading(stage)
    if 'winner' in key:
      return RESULT_WINNER
    return RESULT_SHORTLISTED

  def category_from_text(self, value):
    key = _category_key(value)
    if not key:
      return None
    for category, aliases in ALL_CATEGORY_ALIASES.items():
      for alias in aliases:
        alias_key = _category_key(alias)
        if key == alias_key or key.startswith(alias_key + ' '):
          return category
    return None

  def category_matches(self, category):
    return _category_key(category) in self.category_keys

  def row_from_entry_text(self, year, category, text, result, source_url):
    parsed = self.title_author_from_html_text(text)
    if parsed is None:
      return None
    title, author = parsed
    return self.build_row(year, category, title, author, result, source_url)

  def row_from_pdf_entry(self, year, category, text, result, source_url):
    parsed = self.title_author_from_pdf_text(text)
    if parsed is None:
      parsed = self.title_author_from_html_text(text)
    if parsed is None:
      return None
    title, author = parsed
    return self.build_row(year, category, title, author, result, source_url)

  def title_author_from_html_text(self, value):
    value = self.clean_entry_text(value)
    if not value:
      return None
    by_match = re.match(r'^(.+?)\s+by\s+(.+)$', value, re.I)
    first_comma = value.find(',')
    by_is_primary_separator = (
      by_match is not None
      and (first_comma < 0 or by_match.start(0) < first_comma)
      and not re.search(r'\b(?:illus|ill|illustrated|written|text)\s+by\b',
                        value[:by_match.start(2)], re.I))
    if by_is_primary_separator:
      return (
        self.clean_title(by_match.group(1)),
        self.clean_author(by_match.group(2)))
    dash_match = re.match(r'^(.+?)\s+[-\u2013\u2014]\s+(.+)$', value)
    if dash_match is not None:
      return (
        self.clean_title(dash_match.group(1)),
        self.clean_author(dash_match.group(2)))
    comma_split = self.split_comma_entry(value)
    if comma_split is not None:
      title, author = comma_split
      return self.clean_title(title), self.clean_author(author)
    return None

  def title_author_from_pdf_text(self, value):
    value = self.clean_entry_text(value)
    match = re.match(r'^([A-Z][A-Z .\'&-]+),\s+(.+)$', value)
    if match is None:
      return None
    surname = self.name_case(match.group(1))
    given, title = self.split_given_names_from_title(match.group(2))
    if not given or not title:
      return None
    author = normalize_line(f'{given} {surname}')
    return self.clean_title(self.strip_publisher_tail(title)), self.clean_author(author)

  def split_given_names_from_title(self, value):
    parts = value.split()
    if len(parts) < 2:
      return '', value
    given = [parts[0]]
    index = 1
    while index < len(parts):
      token = parts[index]
      previous = parts[index - 1]
      if token in {'&', 'and'} or re.match(r'^[A-Z]\.?$', token):
        given.append(token)
        index += 1
        continue
      if previous in {'&', 'and'}:
        given.append(token)
        index += 1
        continue
      break
    return normalize_line(' '.join(given)), normalize_line(' '.join(parts[index:]))

  def split_comma_entry(self, value):
    comma_offsets = [match.start() for match in re.finditer(',', value)]
    for offset in comma_offsets:
      title = value[:offset]
      author = value[offset + 1:]
      first = (author.strip().split() or [''])[0].strip(' "\'').casefold()
      if first in TITLE_START_WORDS:
        continue
      if self.looks_like_creator_text(author):
        return title, author
    if comma_offsets:
      offset = comma_offsets[-1]
      return value[:offset], value[offset + 1:]
    return None

  def looks_like_creator_text(self, value):
    text = normalize_line(value)
    if re.search(r'\b(?:illus|illustrated|written|text)\b', text, re.I):
      return True
    return re.match(r'^[A-ZÀ-ÖØ-Þ][\w\'\u2019.-]+(?:\s+[A-ZÀ-ÖØ-Þ&][\w\'\u2019.-]+){0,5}', text) is not None

  def build_row(self, year, category, title, author, result, source_url):
    title = self.clean_title(title)
    author = self.clean_author(author)
    if not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': source_url,
      'category': category,
    }

  def clean_entry_text(self, value):
    value = normalize_line(value)
    value = re.sub(r'^\s*[*\-\u2022]\s*', '', value)
    value = strip_publication_notes(value)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,.;:')

  def clean_title(self, value):
    value = self.strip_publisher_tail(strip_publication_notes(normalize_line(value)))
    return value.strip(' "\'\u2018\u2019\u201c\u201d,.;:')

  def clean_author(self, value):
    value = normalize_line(value)
    value = CREATOR_PREFIX_RE.sub('', value)
    value = strip_publication_notes(value)
    value = self.strip_publisher_tail(value)
    value = re.sub(r'\billus\.?\s+by\b', 'illustrated by', value, flags=re.I)
    value = re.sub(r'\bill\.?\s+', 'illustrated ', value, flags=re.I)
    return normalize_line(value).strip(' "\'\u2018\u2019\u201c\u201d,.;:')

  def strip_publisher_tail(self, value):
    value = normalize_line(value)
    for publisher in sorted(PUBLISHER_TAILS, key=len, reverse=True):
      if value.casefold().endswith(publisher.casefold()):
        return value[:-len(publisher)].strip(' ,.;')
    return value

  def name_case(self, value):
    parts = []
    for part in normalize_line(value).split():
      if len(part) <= 3 and part.replace('.', '').isupper():
        parts.append(part)
      else:
        parts.append(part.capitalize())
    return ' '.join(parts)

  def dedupe_rows(self, rows):
    by_key = {}
    for row in rows:
      key = (
        row['award_year'],
        _category_key(row['category']),
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      current = by_key.get(key)
      if current is None:
        by_key[key] = row
      elif RESULT_ORDER.get(row['result'], 99) < RESULT_ORDER.get(current['result'], 99):
        by_key[key] = row
    return list(by_key.values())

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(int(row['award_year']), []).append(row)
    entries = []
    for year in sorted(by_year):
      year_rows = sorted(
        by_year[year],
        key=lambda row: (
          RESULT_ORDER.get(row.get('result'), 99),
          normalize_heading(row.get('title', ''))))
      positioned = assign_positions(year_rows, year, tied_winners_share_position=True)
      for row in positioned:
        entries.append(self.build_award_entry(
          row,
          row.get('source_url') or ARCHIVE_URL,
          year,
          row.get('category') or self.category,
          award=AWARD_NAME))
    return entries

  def coverage_notes(self, entries, current_year):
    notes = [
      'CBCA Honour Books and official shortlists are imported as shortlisted entries.',
      'Historical CBCA non-winner labels such as Commended, Highly Commended, '
      'and Special Mention are not literal modern shortlists.',
    ]
    current_entries = [
      entry for entry in entries
      if entry.get('award_year') == str(current_year)
    ]
    if current_entries and not any(entry.get('result') == RESULT_WINNER for entry in current_entries):
      notes.append(
        f'CBCA {current_year} winner and Honour Book rows were not available; '
        'imported current-year shortlist rows only.')
    return notes

  def annual_links(self, html, base_url):
    soup = BeautifulSoup(html or '', 'html.parser')
    urls = []
    for link in soup.find_all('a', href=True):
      href = link['href']
      combined = normalize_heading(f'{link.get_text(" ", strip=True)} {href}')
      if not YEAR_RE.search(combined):
        continue
      if 'shortlist' not in combined and 'book of the year award winners' not in combined:
        continue
      urls.append(urljoin(base_url, href))
    return tuple(urls)

  def looks_like_pdf_text(self, source, base_url):
    if (base_url or '').lower().endswith('.pdf'):
      return True
    if isinstance(source, bytes):
      sample = source[:1024].decode('latin-1', 'ignore')
      return '%PDF' in sample
    text = str(source or '')
    if '<html' in text.lower() or '<main' in text.lower():
      return False
    key = normalize_heading(text[:2000])
    return 'book of the year award' in key and 'winner' in key

  def pdf_url_from_archive(self, html, base_url=ARCHIVE_URL):
    soup = BeautifulSoup(html or '', 'html.parser')
    for link in soup.find_all('a', href=True):
      text = normalize_heading(link.get_text(' ', strip=True))
      href = link['href']
      combined = normalize_heading(f'{text} {href}')
      if href.lower().endswith('.pdf') and (
          '1946' in combined
          or 'prior winners' in combined
          or 'awards 1946' in combined):
        return urljoin(base_url, href)
    return ''

  def standalone_year(self, value):
    match = re.match(r'^\s*((?:19|20)\d{2})\s*$', value or '')
    return int(match.group(1)) if match is not None else None

  def year_from_text(self, value):
    match = YEAR_RE.search(value or '')
    return int(match.group(1)) if match is not None else None

  def none_recorded(self, value):
    key = normalize_heading(value)
    return key in {'no award', 'no competition', 'none', 'none recorded'}

  def is_non_entry_line(self, line):
    key = normalize_heading(line)
    return (
      not key
      or key in {
        'winner',
        'winners',
        'honour books',
        'honor books',
        'shortlist',
        'shortlisted',
      }
      or key.startswith('download ')
      or key.startswith('presenting the ')
      or key.startswith('introducing the ')
      or key.startswith('watch the ')
      or key.startswith('see the ')
      or key.startswith('back to awards')
      or key.startswith('previous post')
      or key.startswith('next post'))

  def skip_pdf_line(self, line):
    key = normalize_heading(line)
    return (
      key.startswith('the children s book council of australia')
      or key.startswith('contents page')
      or key.startswith('this publication copyright')
      or key.startswith('reproduction of information')
      or key.startswith('edited and typeset')
      or key.startswith('cbca book week slogans')
      or key.startswith('illus ')
      or key.startswith('illustrated by')
      or key.startswith('text by')
      or key.startswith('published by'))


def parse_cbca_book_of_the_year(
    html, base_url=ARCHIVE_URL, name=AWARD_NAME, category=CATEGORY_OLDER_READERS,
    category_aliases=(), **kwargs):
  return CBCABookOfTheYearParser(category, category_aliases).parse(
    html, base_url, name, **kwargs)
