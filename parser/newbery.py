#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
John Newbery Medal parser for official ALSC/ALA sources.

Maintenance notes:
- Newbery does not publish a public pre-award shortlist for this import scope.
  Public non-winner rows are Honor Books, formerly called runners-up and
  retroactively renamed. The import schema maps honors to `shortlisted` so the
  existing award review filters work.
- Runtime sources stay official-only: the ALSC award page, the linked complete
  PDF list, and annual ALA Youth Media Award posts when the PDF lags.
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


AWARD_NAME = 'John Newbery Medal'
CATEGORY = "Children's Literature"
ALSC_URL = 'https://www.ala.org/alsc/awardsgrants/bookmedia/newbery'
PDF_URL = 'https://www.ala.org/sites/default/files/2026-03/newbery-medals-honors-1922-present.pdf'
YMA_URL_TEMPLATE = (
  'https://www.ala.org/news/{year}/01/'
  'american-library-association-announces-{year}-youth-media-award-winners')

SEMANTIC_TAGS = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li')
YEAR_RE = re.compile(r'\b((?:19|20)\d{2})\b')
STAGE_RE = re.compile(
  r'^\s*((?:19|20)\d{2})?\s*(?:Newbery\s+)?'
  r'(Medal\s+Winner|Winner|Honor\s+Books?|Honour\s+Books?|Honors?|Runners?-?up)'
  r'\s*:?\s*(.*)$',
  re.I)
PUBLISHER_RE = re.compile(
  r'\s*(?:,?\s+(?:and\s+)?published by|\.?\s+(?:and\s+)?published by|'
  r',?\s+published by an imprint of)\s+.+$',
  re.I)
CREATOR_PREFIX_RE = re.compile(
  r'^\s*(?:'
  r'written and illustrated by|illustrated and written by|written by|'
  r'illustrated by|retold by|adapted by|by'
  r')\s+',
  re.I)


def yma_awards_url(year):
  return YMA_URL_TEMPLATE.format(year=int(year))


class NewberyMedalParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def parse(
      self, source, base_url=ALSC_URL, name=AWARD_NAME, fetch_url=None,
      current_year=None, pdf_page=None, supplement_pages=(), log=None,
      progress=None):
    notes = []
    rows = []
    pdf_source = pdf_page
    pdf_url = PDF_URL

    if pdf_source is None and self.looks_like_landing_page(source, base_url):
      pdf_url = self.pdf_url_from_landing_page(source, base_url) or PDF_URL
      if fetch_url is not None:
        try:
          if progress is not None:
            progress(1, 1, 'Fetching Newbery complete PDF list')
          pdf_source = fetch_url(pdf_url)
        except Exception as err:
          notes.append(f'Newbery complete PDF could not be fetched: {pdf_url}: {err}')
          if log is not None:
            log(f'Newbery complete PDF failed: {pdf_url}: {err}')
      else:
        pdf_source = source
    elif pdf_source is None:
      pdf_source = source
      if (base_url or '').lower().endswith('.pdf'):
        pdf_url = base_url

    if pdf_source is not None:
      rows.extend(self.pdf_rows(pdf_source, pdf_url))

    max_pdf_year = max((int(row['award_year']) for row in rows), default=None)
    current_year = int(current_year or date.today().year)

    for page_url, page_html in supplement_pages or ():
      rows.extend(self.yma_page_rows(page_html, page_url))

    if fetch_url is not None and max_pdf_year is not None and max_pdf_year < current_year:
      years = range(max_pdf_year + 1, current_year + 1)
      total = max(1, len(tuple(years)))
      for index, year in enumerate(range(max_pdf_year + 1, current_year + 1), 1):
        url = yma_awards_url(year)
        try:
          if progress is not None:
            progress(index, total, f'Fetching {year} ALA Youth Media Awards')
          rows.extend(self.yma_page_rows(fetch_url(url), url))
        except Exception as err:
          notes.append(f'ALA Youth Media Awards page could not be fetched: {url}: {err}')
          if log is not None:
            log(f'ALA Youth Media Awards page failed: {url}: {err}')

    entries = self.entries_from_rows(self.dedupe_rows(rows))
    if not entries:
      raise ValueError('No John Newbery Medal entries found on official ALSC/ALA sources.')
    notes.append(
      'Newbery Honor Books are imported as shortlisted entries; '
      'the award does not publish public pre-award shortlists for this import scope.')
    notes.append(
      'Historical runners-up are treated as Honor Books, following official ALSC terminology.')
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def pdf_rows(self, pdf_or_text, source_url=PDF_URL):
    return self.rows_from_text(extract_pdf_text(pdf_or_text), source_url)

  def rows_from_text(self, text, source_url):
    rows = []
    current_year = None
    current_result = None
    pending = ''

    for line in self.source_lines(text):
      stage = self.stage_from_line(line, current_year)
      if stage is not None:
        pending = self.flush_pending(rows, pending, current_year, current_result, source_url)
        current_year, current_result, remainder = stage
        if self.none_recorded(remainder):
          current_result = None
          pending = ''
          continue
        if remainder:
          pending = self.consume_entry_line(
            rows, pending, remainder, current_year, current_result, source_url)
        continue

      if current_year is not None and current_result in {RESULT_WINNER, RESULT_SHORTLISTED}:
        if self.none_recorded(line):
          pending = self.flush_pending(rows, pending, current_year, current_result, source_url)
          current_result = None
          continue
        pending = self.consume_entry_line(
          rows, pending, line, current_year, current_result, source_url)

    self.flush_pending(rows, pending, current_year, current_result, source_url)
    return rows

  def source_lines(self, text):
    text = (text or '').replace('\r', '\n')
    text = re.sub(
      r'\b((?:19|20)\d{2})\s+(Newbery\s+)?(Medal\s+Winner|Honor\s+Books?|Honour\s+Books?|Runners?-?up)\b',
      r'\n\1 \2\3\n',
      text,
      flags=re.I)
    lines = []
    for raw_line in text.splitlines():
      line = normalize_line(raw_line)
      if not line or self.skip_line(line):
        continue
      lines.append(line)
    return lines

  def stage_from_line(self, line, current_year=None):
    match = STAGE_RE.match(line)
    if match is None:
      return None
    year = int(match.group(1) or current_year or 0)
    if not year:
      return None
    stage = normalize_heading(match.group(2))
    result = RESULT_WINNER if 'winner' in stage else RESULT_SHORTLISTED
    return year, result, normalize_line(match.group(3))

  def consume_entry_line(self, rows, pending, line, year, result, source_url):
    pending = normalize_line(f'{pending} {line}' if pending else line)
    parsed = self.row_from_text(pending, year, result, source_url)
    if parsed is None:
      return pending
    rows.append(parsed)
    return ''

  def flush_pending(self, rows, pending, year, result, source_url):
    if pending and year is not None and result in {RESULT_WINNER, RESULT_SHORTLISTED}:
      parsed = self.row_from_text(pending, year, result, source_url)
      if parsed is not None:
        rows.append(parsed)
    return ''

  def row_from_text(self, text, year, result, source_url):
    parsed = self.title_author_from_text(text)
    if parsed is None:
      return None
    title, author = parsed
    if not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': source_url,
      'category': CATEGORY,
    }

  def title_author_from_text(self, value):
    value = self.clean_entry_text(value)
    if not value:
      return None
    quoted = re.match(r'^[“"]([^”"]+)[”"]\s*,?\s*(.+)$', value)
    if quoted is not None:
      return quoted.group(1).strip(' ,'), self.clean_author(quoted.group(2))

    match = re.match(
      r'^(.+?)\s*,?\s+(?:written and illustrated by|illustrated and written by|'
      r'written by|illustrated by|retold by|adapted by|by)\s+(.+)$',
      value,
      re.I)
    if match is not None:
      return self.clean_title(match.group(1)), self.clean_author(match.group(2))

    dash_match = re.match(r'^(.+?)\s+[\u2013\u2014-]\s+(.+)$', value)
    if dash_match is not None:
      return self.clean_title(dash_match.group(1)), self.clean_author(dash_match.group(2))
    return None

  def clean_entry_text(self, value):
    value = normalize_line(value)
    value = re.sub(r'^\s*[*\-\u2022]\s*', '', value)
    value = re.sub(r'^\s*(?:winner|honou?r books?|runners?-?up)\s*:?\s*', '', value, flags=re.I)
    value = re.sub(r'\bb\s+y\b', 'by', value)
    return value.strip(' ,.;:')

  def clean_title(self, value):
    value = strip_publication_notes(normalize_line(value))
    return value.strip(' "\'\u2018\u2019\u201c\u201d,.;:')

  def clean_author(self, value):
    value = normalize_line(value)
    value = PUBLISHER_RE.sub('', value)
    value = CREATOR_PREFIX_RE.sub('', value)
    value = strip_publication_notes(value)
    value = re.sub(r'\.\s+The book is published by .+$', '', value, flags=re.I)
    value = re.sub(r'\s+and\s+$', '', value, flags=re.I)
    return normalize_line(value).strip(' "\'\u2018\u2019\u201c\u201d,.;:')

  def yma_page_rows(self, html, base_url):
    lines = self.newbery_section_lines(html)
    year = self.year_from_url_or_lines(base_url, lines)
    if year is None:
      return []
    rows = []
    current_result = None
    for line in lines:
      key = normalize_heading(line)
      if 'newbery medal' in key and not re.search(r'["“]', line):
        current_result = RESULT_WINNER
        continue
      if key in {'newbery honor books', 'four newbery honor books', 'newbery honors'}:
        current_result = RESULT_SHORTLISTED
        continue
      if current_result not in {RESULT_WINNER, RESULT_SHORTLISTED}:
        continue
      for entry_text in self.yma_entry_texts(line):
        row = self.row_from_text(entry_text, year, current_result, base_url)
        if row is not None:
          rows.append(row)
      if current_result == RESULT_WINNER and rows:
        current_result = None
    return rows

  def newbery_section_lines(self, html):
    lines = self.text_lines(html)
    section = []
    in_section = False
    for line in lines:
      key = normalize_heading(line)
      if not in_section and 'newbery medal' in key:
        in_section = True
      elif in_section and self.is_next_yma_award_heading(key):
        break
      if in_section:
        section.append(line)
    return section

  def is_next_yma_award_heading(self, key):
    if 'newbery medal' in key or key in {'newbery honor books', 'four newbery honor books'}:
      return False
    next_awards = (
      'caldecott',
      'randolph caldecott',
      'coretta scott king',
      'schneider family book award',
      'michael l printz award',
      'alex awards',
    )
    return any(key.startswith(item) for item in next_awards)

  def yma_entry_texts(self, text):
    text = normalize_line(text)
    if not text:
      return []
    if re.search(r'["“]', text):
      pieces = []
      for match in re.finditer(r'["“][^"”]+["”]', text):
        start = match.start()
        end = match.end()
        next_match = re.search(r'\s*(?:;|,)?\s*(?:and\s+)?["“]', text[end:])
        piece_end = end + next_match.start() if next_match is not None else len(text)
        pieces.append(text[start:piece_end].strip(' ,.;'))
      return pieces or [text]
    return [part.strip(' ,.;') for part in re.split(r'\s*;\s*(?:and\s+)?', text) if part.strip()]

  def text_lines(self, html):
    soup = BeautifulSoup(html or '', 'html.parser')
    for removable in soup.find_all(['script', 'style', 'sup']):
      removable.decompose()
    lines = []
    for node in soup.find_all(SEMANTIC_TAGS):
      text = normalize_line(node.get_text(' ', strip=True))
      if text:
        lines.append(text)
    if lines:
      return lines
    text = soup.get_text('\n')
    return [normalize_line(line) for line in text.splitlines() if normalize_line(line)]

  def pdf_url_from_landing_page(self, html, base_url=ALSC_URL):
    soup = BeautifulSoup(html or '', 'html.parser')
    for link in soup.find_all('a', href=True):
      text = normalize_heading(link.get_text(' ', strip=True))
      href = link['href']
      combined = normalize_heading(f'{text} {href}')
      if 'pdf' in href.lower() and (
          '1922 present' in combined
          or 'complete list' in combined
          or 'newbery medals honors' in combined):
        return urljoin(base_url, href)
    return None

  def looks_like_landing_page(self, source, base_url):
    text = source.decode('latin-1', 'ignore') if isinstance(source, bytes) else str(source or '')
    if '%PDF' in text[:1024] or (base_url or '').lower().endswith('.pdf'):
      return False
    return '<a ' in text.lower() or '<html' in text.lower()

  def year_from_url_or_lines(self, url, lines):
    match = YEAR_RE.search(url or '')
    if match is not None:
      return int(match.group(1))
    for line in lines:
      match = YEAR_RE.search(line)
      if match is not None:
        return int(match.group(1))
    return None

  def none_recorded(self, value):
    return normalize_heading(value) in {'none recorded', 'none', 'no honor books'}

  def skip_line(self, line):
    key = normalize_heading(line)
    return (
      key in {
        'john newbery medal',
        'newbery medal',
        'newbery medal and honor books',
        'newbery medals and honor books',
        'medal winner',
        'honor book',
        'honor books',
      }
      or key.startswith('page ')
      or key.startswith('association for library service to children')
      or key.startswith('american library association')
      or key.startswith('compiled by'))

  def dedupe_rows(self, rows):
    by_key = {}
    for row in rows:
      key = (row.get('award_year', ''), normalize_heading(row.get('title', '')))
      current = by_key.get(key)
      if current is None:
        by_key[key] = row
        continue
      if row.get('result') == RESULT_WINNER and current.get('result') != RESULT_WINNER:
        by_key[key] = row
      elif row.get('result') == current.get('result') and len(row.get('author', '')) > len(current.get('author', '')):
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
          0 if row.get('result') == RESULT_WINNER else 1,
          normalize_heading(row.get('title', ''))))
      positioned = assign_positions(year_rows, year, tied_winners_share_position=True)
      for row in positioned:
        entries.append(self.build_award_entry(
          row,
          row.get('source_url') or PDF_URL,
          year,
          row.get('category') or CATEGORY,
          award=AWARD_NAME))
    return entries


def parse_newbery_medal(source, base_url=ALSC_URL, name=AWARD_NAME, **kwargs):
  return NewberyMedalParser().parse(source, base_url, name, **kwargs)
