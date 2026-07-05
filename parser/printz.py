#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Michael L. Printz Award parser for official ALA/YALSA pages.

Maintenance notes:
- Printz does not expose a public pre-award shortlist. Committee nominations
  are confidential; public non-winner rows are Honor Books. The import schema
  maps those honors to `shortlisted` so existing award review filters work.
- Runtime sources stay official-only: the YALSA historical winners/honor page,
  the current YALSA award page, and ALA Youth Media Award news posts.
"""

from datetime import date
import re

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


AWARD_NAME = 'Michael L. Printz Award'
CATEGORY = 'Young Adult Literature'
HISTORY_URL = (
  'https://www.ala.org/yalsa/booklistsawards/bookawards/'
  'printzaward/previouswinners/winners')
CURRENT_URL = 'https://www.ala.org/yalsa/printz-award'
YMA_URL_TEMPLATE = (
  'https://www.ala.org/news/{year}/01/'
  'american-library-association-announces-{year}-youth-media-award-winners')

SEMANTIC_TAGS = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li')
YEAR_RE = re.compile(r'^\s*((?:19|20)\d{2})\s*:?\s*$')
PUBLISHER_RE = re.compile(
  r'\s*(?:,?\s+(?:and\s+)?(?:co-)?published by|\.?\s+The book is published by)\s+.+$',
  re.I)
CREATOR_PREFIX_RE = re.compile(
  r'^\s*(?:'
  r'written and illustrated by|illustrated and written by|'
  r'written by|edited by|illustrated by|created by'
  r')\s+',
  re.I)


def yma_awards_url(year):
  return YMA_URL_TEMPLATE.format(year=int(year))


class PrintzAwardParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def parse(
      self, html, base_url=HISTORY_URL, name=AWARD_NAME, fetch_url=None,
      current_year=None, current_page=None, supplement_pages=(),
      log=None, progress=None):
    rows = self.history_rows(html, base_url)
    notes = []
    max_history_year = max((int(row['award_year']) for row in rows), default=None)

    current_year = int(current_year or date.today().year)
    if current_page is not None:
      rows.extend(self.current_page_rows(current_page, CURRENT_URL))
    elif fetch_url is not None:
      try:
        if progress is not None:
          progress(1, 1, 'Fetching current Printz Award page')
        rows.extend(self.current_page_rows(fetch_url(CURRENT_URL), CURRENT_URL))
      except Exception as err:
        notes.append(f'Current Printz Award page could not be fetched: {CURRENT_URL}: {err}')
        if log is not None:
          log(f'Current Printz Award page failed: {CURRENT_URL}: {err}')

    for page_url, page_html in supplement_pages or ():
      rows.extend(self.yma_page_rows(page_html, page_url))

    if fetch_url is not None and max_history_year is not None:
      years = range(max_history_year + 1, current_year + 1)
      total = max(1, len(tuple(years)))
      for index, year in enumerate(range(max_history_year + 1, current_year + 1), 1):
        url = yma_awards_url(year)
        try:
          if progress is not None:
            progress(index, total, f'Fetching {year} ALA Youth Media Awards')
          rows.extend(self.yma_page_rows(fetch_url(url), url))
        except Exception as err:
          notes.append(f'ALA Youth Media Awards page could not be fetched: {url}: {err}')
          if log is not None:
            log(f'ALA Youth Media Awards page failed: {url}: {err}')

    rows = self.dedupe_rows(rows)
    entries = self.entries_from_rows(rows)
    if not entries:
      raise ValueError('No Michael L. Printz Award entries found on official ALA/YALSA pages.')
    notes.append(
      'Printz Honor Books are imported as shortlisted entries; '
      'the award does not publish public pre-award shortlists.')
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def history_rows(self, html, base_url=HISTORY_URL):
    lines = self.text_lines(html)
    rows = []
    current_year = None
    current_result = None

    for line in lines:
      year_match = YEAR_RE.match(line)
      if year_match is not None:
        year = int(year_match.group(1))
        if year >= 2000:
          current_year = year
          current_result = None
        continue

      if current_year is None:
        continue
      lower = normalize_heading(line)
      if lower in {'winner', 'winners'}:
        current_result = RESULT_WINNER
        continue
      if lower in {'honor books', 'honour books'}:
        current_result = RESULT_SHORTLISTED
        continue
      if lower.startswith('winner '):
        line = re.sub(r'^\s*winner\s*:?\s*', '', line, flags=re.I).strip()
        rows.extend(self.rows_from_text(current_year, line, RESULT_WINNER, base_url))
        current_result = RESULT_WINNER
        continue
      if lower.startswith(('honor books ', 'honour books ')):
        line = re.sub(r'^\s*honou?r books\s*:?\s*', '', line, flags=re.I).strip()
        rows.extend(self.rows_from_text(current_year, line, RESULT_SHORTLISTED, base_url))
        current_result = RESULT_SHORTLISTED
        continue
      if current_result not in {RESULT_WINNER, RESULT_SHORTLISTED}:
        continue
      if self.skip_history_line(line):
        continue
      rows.extend(self.rows_from_text(current_year, line, current_result, base_url))
    return rows

  def current_page_rows(self, html, base_url=CURRENT_URL):
    rows = []
    current_year = None
    winner_pending = False
    for line in self.text_lines(html):
      match = re.match(
        r'^\s*((?:19|20)\d{2})\s+Michael L\. Printz Award Winner\s*:?\s*(.+)$',
        line,
        re.I)
      if match is not None:
        current_year = int(match.group(1))
        winner_pending = True
        if re.search(r'["“]', match.group(2)):
          rows.extend(self.rows_from_text(current_year, match.group(2), RESULT_WINNER, base_url))
          winner_pending = False
        continue
      if winner_pending and current_year is not None:
        parsed = self.rows_from_text(current_year, line, RESULT_WINNER, base_url)
        if parsed:
          rows.extend(parsed)
          winner_pending = False
    return rows

  def yma_page_rows(self, html, base_url):
    lines = self.printz_section_lines(html)
    year = self.year_from_url_or_lines(base_url, lines)
    if year is None:
      return []
    rows = []
    current_result = None
    for line in lines:
      lower = normalize_heading(line)
      if 'michael l printz award' in lower and not re.search(r'["“]', line):
        current_result = RESULT_WINNER
        continue
      if lower in {'printz honor books', 'four printz honor books'}:
        current_result = RESULT_SHORTLISTED
        continue
      if current_result not in {RESULT_WINNER, RESULT_SHORTLISTED}:
        continue
      rows.extend(self.rows_from_text(year, line, current_result, base_url))
      if current_result == RESULT_WINNER and rows:
        current_result = None
    return rows

  def printz_section_lines(self, html):
    lines = self.text_lines(html)
    section = []
    in_section = False
    for line in lines:
      key = normalize_heading(line)
      if not in_section and 'michael l printz award' in key:
        in_section = True
      elif in_section and self.is_next_yma_award_heading(key):
        break
      if in_section:
        section.append(line)
    return section

  def is_next_yma_award_heading(self, key):
    if 'michael l printz award' in key or key in {'printz honor books', 'four printz honor books'}:
      return False
    next_awards = (
      'schneider family book award',
      'alex awards',
      'william c morris award',
      'newbery',
      'caldecott',
      'coretta scott king',
    )
    return any(key.startswith(item) for item in next_awards)

  def rows_from_text(self, year, text, result, source_url):
    rows = []
    for part in self.entry_texts(text):
      parsed = self.parse_entry_text(part)
      if parsed is None:
        continue
      title, author = parsed
      if not title or not author:
        continue
      rows.append({
        'award_year': str(year),
        'title': title,
        'author': author,
        'result': result,
        'source_url': source_url,
        'category': CATEGORY,
      })
    return rows

  def entry_texts(self, text):
    text = normalize_line(text)
    if not text:
      return []
    if re.search(r'["“]', text):
      return self.quoted_entry_texts(text)
    if ';' in text:
      return [part.strip(' ,.;') for part in re.split(r'\s*;\s*(?:and\s+)?', text) if part.strip()]
    return [text]

  def quoted_entry_texts(self, text):
    pieces = []
    for match in re.finditer(r'["“][^"”]+["”]', text):
      start = match.start()
      end = match.end()
      next_match = re.search(r'\s*(?:;|,)?\s*(?:and\s+)?["“]', text[end:])
      piece_end = end + next_match.start() if next_match is not None else len(text)
      pieces.append(text[start:piece_end].strip(' ,.;'))
    return pieces or [text]

  def parse_entry_text(self, text):
    text = self.clean_entry_text(text)
    if not text:
      return None
    quote_offsets = [offset for offset in (text.find('"'), text.find('“')) if offset >= 0]
    if quote_offsets:
      text = text[min(quote_offsets):].strip()
    quoted = re.match(r'^[“"]([^”"]+)[”"]\s*,?\s*(.+)$', text)
    if quoted is not None:
      title = quoted.group(1).strip(' ,')
      author = self.clean_creator_text(quoted.group(2))
      return title, author

    match = re.match(
      r'^(.+?)\s*,?\s+(?:b\s*y|written by|edited by|illustrated by)\s+(.+)$',
      text,
      re.I)
    if match is None:
      return None
    return (
      strip_publication_notes(match.group(1).strip()),
      self.clean_creator_text(match.group(2)))

  def clean_entry_text(self, text):
    text = normalize_line(text)
    text = re.sub(r'^\s*(?:winner|honou?r books?)\s*:?\s*', '', text, flags=re.I)
    text = re.sub(r'\bb\s+y\b', 'by', text)
    text = PUBLISHER_RE.sub('', text).strip()
    text = re.sub(r'\s+\.$', '', text).strip()
    return text

  def clean_creator_text(self, text):
    text = normalize_line(text)
    text = PUBLISHER_RE.sub('', text).strip(' .')
    text = CREATOR_PREFIX_RE.sub('', text)
    text = re.sub(r'\.\s+Written by .+$', '', text, flags=re.I)
    text = re.sub(r'\s+and\s+$', '', text, flags=re.I)
    return normalize_line(text).strip(' ,.;')

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

  def skip_history_line(self, line):
    key = normalize_heading(line)
    return (
      key in {'email', 'print', 'cite', 'share this page'}
      or key.startswith('back to ')
      or key.startswith('more information')
      or key.startswith('previous winners'))

  def year_from_url_or_lines(self, url, lines):
    match = re.search(r'(?:19|20)\d{2}', url or '')
    if match is not None:
      return int(match.group(0))
    for line in lines:
      match = re.search(r'(?:19|20)\d{2}', line)
      if match is not None:
        return int(match.group(0))
    return None

  def dedupe_rows(self, rows):
    by_key = {}
    for row in rows:
      key = (
        row.get('award_year', ''),
        normalize_heading(row.get('title', '')),
        row.get('result', ''),
      )
      current = by_key.get(key)
      if current is None or len(row.get('author', '')) > len(current.get('author', '')):
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
        key=lambda row: 0 if row.get('result') == RESULT_WINNER else 1)
      positioned = assign_positions(year_rows, year, tied_winners_share_position=True)
      for row in positioned:
        entries.append(self.build_award_entry(
          row,
          row.get('source_url') or HISTORY_URL,
          year,
          row.get('category') or CATEGORY,
          award=AWARD_NAME))
    return entries


def parse_printz_award(html, base_url=HISTORY_URL, name=AWARD_NAME, **kwargs):
  return PrintzAwardParser().parse(html, base_url, name, **kwargs)
