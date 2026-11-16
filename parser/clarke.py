#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Arthur C. Clarke Award parsers.

Maintenance notes:
- The official Clarke page is the primary source. It exposes winners and
  shortlists in its #about section as year groups with "Title - Author" rows.
  Preserve that navigation fragment in provenance so browsers reveal the list.
- SFADB exposes one page per award year with categoryblock sections for Winner,
  optional Runner-up/Third Place, and Shortlist. Read title/person boundaries
  structurally and exclude translator credits. Plain heading/row pages remain
  a legacy fallback only when no category blocks exist. SFADB stays the
  replacement source and preserves its historical placing labels.
- The award is always for a novel, so there is no category-selection layer.
  Clarke configures the shared SFADB result-section model (headings map to
  result strings) rather than selecting one award-category block. Year parsing,
  canonical entry construction and positioning stay in SFADBParser.
"""

import re

from lxml import html as lxml_html

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, split_title_author as award_split_title_author,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
  from calibre_plugins.list_switchboard.parser.sfadb_base import (
    SFADBParser,
    normalize_heading, normalize_line, strip_publication_notes,
    node_text, assign_positions,
  )
except ImportError:
  from .award_base import AwardParserBase, split_title_author as award_split_title_author
  from .generic import position_sort_key
  from .sfadb_base import (
    SFADBParser,
    normalize_heading, normalize_line, strip_publication_notes,
    node_text, assign_positions,
  )


AWARD_NAME = 'Arthur C. Clarke Award'
CATEGORY_NAME = 'Novel'
RECIPE_NAME = 'Arthur C. Clarke Award - Novel'
YEAR_PAGE_URL = re.compile(r'/Arthur_C_Clarke_Award_(\d{4})$')
OFFICIAL_YEAR = re.compile(r'^((?:19|20)\d{2})(.*)$')
OFFICIAL_DASH_SEPARATOR = re.compile(r'\s+[-\u2013\u2014]\s*|\s*[-\u2013\u2014]\s+')
OFFICIAL_WINNER_SUFFIX = re.compile(r'\s*(?:[-\u2013\u2014]\s*)?winner\s*$', re.I)
OFFICIAL_TRANSLATOR_CREDIT = re.compile(
  r'(?:^|\s*[,;]\s*|\s+)translated\s+by\b.*$', re.I)
OFFICIAL_STOP_TEXT = re.compile(
  r'\s*[-\u2013\u2014_]*\s*(?:to submit titles|contact|submissions for the '
  r'publishing year|the arthur c\.?\s*clarke award is administered).*$',
  re.I)
SECTION_RESULTS = {
  'winner': 'winner',
  'runner up': 'runner-up',
  'runner-up': 'runner-up',
  'third place': 'third-place',
  'shortlist': 'nominee',
}
BOUNDARY_HEADINGS = frozenset({
  'where and when', 'eligibility year', 'judges', 'copyright',
})
OFFICIAL_STOP_HEADINGS = (
  'to submit titles',
  'contact',
  'submissions for the publishing year',
  'the arthur c clarke award is administered',
)


def _split_title_author(text):
  work_text = strip_publication_notes(text)
  work_text = re.sub(r',\s*translated\s+by\b.*$', '', work_text, flags=re.I).strip()
  return award_split_title_author(work_text)


def _split_official_row(text):
  matches = list(OFFICIAL_DASH_SEPARATOR.finditer(text))
  if not matches:
    return '', ''
  match = matches[-1]
  return text[:match.start()].strip(), text[match.end():].strip()


def _official_tokens(root):
  started = False
  for token in root.xpath('//text()[normalize-space()]'):
    text = normalize_line(token)
    if not text:
      continue
    heading = normalize_heading(text)
    if not started:
      marker = heading.find('winners and shortlists')
      if marker < 0:
        continue
      started = True
      text = re.sub(r'^.*?winners\s+and\s+shortlists', '', text, flags=re.I).strip()
      if not text:
        continue
      heading = normalize_heading(text)
    trimmed = OFFICIAL_STOP_TEXT.sub('', text).strip()
    if trimmed != text:
      if trimmed:
        yield trimmed
      break
    if any(heading.startswith(stop) for stop in OFFICIAL_STOP_HEADINGS):
      break
    yield text


class OfficialClarkeParser(AwardParserBase):
  """
  Parser for the official Arthur C. Clarke Award winners/shortlists page.

  Invariants:
  - The official page does not identify runner-up rows. Only explicit WINNER
    markers become winners; all other rows in the year group are nominees.
  - Parsing starts at the "Winners and shortlists" marker so homepage copy,
    judges, and contact text do not become import rows.
  - Explicit trailing translator credits are excluded after isolating the
    work author; translator wording inside a title must remain intact.
  """

  AWARD_NAME = AWARD_NAME

  def parse(self, html, base_url, name=None, category=None,
            category_aliases=None, fetch_url=None, log=None, progress=None):
    root = lxml_html.fromstring(html or '<html></html>')
    rows_by_year = {}
    current_year = None
    for token in _official_tokens(root):
      token_parts = self.year_token_parts(token)
      for year, row_text in token_parts:
        if year is not None:
          current_year = year
          rows_by_year.setdefault(current_year, [])
        if not row_text or current_year is None:
          continue
        parsed = self.parse_item(row_text)
        if parsed is not None:
          rows_by_year.setdefault(current_year, []).append(parsed)

    entries = []
    for year in sorted(rows_by_year):
      rows = [
        self.build_award_entry(row, base_url, year, CATEGORY_NAME)
        for row in rows_by_year[year]
      ]
      entries.extend(assign_positions(rows, year))
    return self.parsed_result(
      name or RECIPE_NAME,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def year_token_parts(self, token):
    parts = []
    remaining = token
    while remaining:
      match = OFFICIAL_YEAR.match(remaining)
      if match is not None:
        year = int(match.group(1))
        rest = match.group(2).strip()
        parts.append((year, rest))
        break
      embedded = re.search(r'\s((?:19|20)\d{2})\s*', remaining)
      if embedded is None:
        parts.append((None, remaining))
        break
      prefix = remaining[:embedded.start()].strip()
      if prefix:
        parts.append((None, prefix))
      remaining = remaining[embedded.start():].strip()
    return parts

  def parse_item(self, text):
    text = normalize_line(text)
    if normalize_heading(text) in ('about us', 'winners and shortlists'):
      return None
    result = 'winner' if OFFICIAL_WINNER_SUFFIX.search(text) else 'nominee'
    text = OFFICIAL_WINNER_SUFFIX.sub('', text).strip(' -\u2013\u2014')
    title, author = _split_official_row(text)
    author = OFFICIAL_TRANSLATOR_CREDIT.sub('', author).strip()
    if not title or not author:
      return None
    return {
      'title': strip_publication_notes(title).strip(' "\u201c\u201d,'),
      'author': strip_publication_notes(author).strip(),
      'result': result,
    }


class ClarkeParser(SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = BOUNDARY_HEADINGS
  RESULT_SECTIONS = SECTION_RESULTS

  def parse(self, overview_html, base_url, name=None, category=None,
            category_aliases=None, fetch_url=None, log=None, progress=None):
    # Clarke has a fixed name and category; callers do not pass them.
    return super().parse(
      overview_html, base_url,
      name=RECIPE_NAME,
      category=CATEGORY_NAME,
      category_aliases=(),
      fetch_url=fetch_url, log=log, progress=progress)

  def parse_item_node(self, node):
    title_nodes = node.xpath('(./b | ./strong)[1]')
    if not title_nodes:
      return self.parse_item(node_text(node))
    title_node = title_nodes[0]
    title = strip_publication_notes(node_text(title_node)).strip(' "\u201c\u201d,')
    authors = []
    credit = title_node.tail or ''
    for sibling in title_node.itersiblings():
      if re.search(r'\btranslated\s+by\b', credit, re.I):
        break
      if sibling.tag == 'a':
        author = normalize_line(node_text(sibling)).strip(' ,')
        if author and author not in authors:
          authors.append(author)
      credit += ' ' + node_text(sibling) + ' ' + (sibling.tail or '')
    if not title or not authors:
      return self.parse_item(node_text(node))
    return {'title': title, 'authors': authors}

  def parse_item(self, text):
    text = normalize_line(text)
    title, author = _split_title_author(text)
    if not title or not author:
      return None
    return {
      'title': strip_publication_notes(title).strip(' \"\u201c\u201d,'),
      'author': strip_publication_notes(author).strip(),
      'result': 'nominee',  # overwritten by parse_year after section detection
    }


def parse_clarke_award_novel(
    overview_html, base_url, fetch_url=None, log=None, progress=None):
  return ClarkeParser().parse(
    overview_html, base_url,
    fetch_url=fetch_url, log=log, progress=progress)
