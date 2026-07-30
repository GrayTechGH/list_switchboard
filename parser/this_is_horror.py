#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
This Is Horror Awards parser for official WordPress ballots and results.

Maintenance notes:
- The fixed official ballot manifest is the historical shortlist spine.
- The 2011-2013 ballots store numbered nominees in one paragraph; later
  ballots use list items. Parsing first isolates a category section, then
  splits the legacy numbered fragment.
- Result pages only promote ballot rows to winner or runner-up. They never
  replace an official ballot or introduce a second title variant.
- Goodreads is a paginated diagnostic supplement. Its rows are ignored when
  the corresponding official ballot is present.
"""

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, UnicodeDammit

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, split_title_author,
    strip_editor_marker, strip_publication_notes, strip_square_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, split_title_author,
    strip_editor_marker, strip_publication_notes, strip_square_notes,
  )
  from .generic import position_sort_key


AWARD_NAME = 'This Is Horror Award'
OFFICIAL_AWARDS_URL = 'https://www.thisishorror.co.uk/awards/'
GOODREADS_URL = 'https://www.goodreads.com/award/show/23539-this-is-horror-award'

OFFICIAL_BALLOTS = (
  (2011, 800, 'https://www.thisishorror.co.uk/this-is-horror-awards-2011/'),
  (2012, 6752, 'https://www.thisishorror.co.uk/this-is-horror-awards-2012/'),
  (2013, 11039, 'https://www.thisishorror.co.uk/horror-awards-2013/'),
  (2014, 13519,
   'https://www.thisishorror.co.uk/this-is-horror-awards-2014-vote-now/'),
  (2015, 16159,
   'https://www.thisishorror.co.uk/this-is-horror-awards-2015-vote-now/'),
  (2016, 21034,
   'https://www.thisishorror.co.uk/this-is-horror-awards-2016-vote-now/'),
  (2017, 24612,
   'https://www.thisishorror.co.uk/this-is-horror-awards-2017-vote-now/'),
  (2018, 27788,
   'https://www.thisishorror.co.uk/this-is-horror-awards-2018-vote-now/'),
  (2019, 30813,
   'https://www.thisishorror.co.uk/this-is-horror-awards-2019-vote-now/'),
  (2020, 33558,
   'https://www.thisishorror.co.uk/this-is-horror-awards-2020-vote-now/'),
  (2021, 37316,
   'https://www.thisishorror.co.uk/this-is-horror-awards-2021-vote-now/'),
  (2024, 42416,
   'https://www.thisishorror.co.uk/this-is-horror-awards-2024-vote-now/'),
)
OFFICIAL_RESULTS = (
  (2011, 'pages', 1209,
   'https://www.thisishorror.co.uk/features/'
   'this-is-horror-awards-2011-the-winners/'),
  (2012, 'posts', 7550,
   'https://www.thisishorror.co.uk/horror-awards-2012-winners/'),
  (2013, 'posts', 11416,
   'https://www.thisishorror.co.uk/horror-awards-2013-winners/'),
  (2014, 'posts', 13851,
   'https://www.thisishorror.co.uk/this-is-horror-awards-2014-winners/'),
  (2015, 'posts', 16464,
   'https://www.thisishorror.co.uk/this-is-horror-awards-2015-the-winners/'),
  (2016, 'posts', 21702,
   'https://www.thisishorror.co.uk/this-is-horror-awards-2016-the-winners/'),
  (2017, 'posts', 25087,
   'https://www.thisishorror.co.uk/this-is-horror-awards-2017-the-winners/'),
  (2018, 'posts', 27948,
   'https://www.thisishorror.co.uk/this-is-horror-awards-2018-the-winners/'),
  (2019, 'pages', 31694,
   'https://www.thisishorror.co.uk/awards/'
   'this-is-horror-awards-2019-the-winners/'),
  (2020, 'pages', 34408,
   'https://www.thisishorror.co.uk/awards/'
   'this-is-horror-awards-2020-the-winners/'),
  (2021, 'pages', 39003,
   'https://www.thisishorror.co.uk/awards/'
   'this-is-horror-awards-2021-the-winners/'),
  (2024, 'posts', 43497,
   'https://www.thisishorror.co.uk/this-is-horror-awards-2024-the-winners/'),
)


def wordpress_include_url(kind, ids):
  joined = ','.join(str(value) for value in ids)
  return (
    f'https://www.thisishorror.co.uk/wp-json/wp/v2/{kind}'
    f'?include={joined}&orderby=include&per_page=100')


OFFICIAL_BALLOTS_API_URL = wordpress_include_url(
  'posts', [item[1] for item in OFFICIAL_BALLOTS])
# Compatibility alias retained for callers that used the former current-page
# constant. It now intentionally resolves to the complete official history.
OFFICIAL_AWARDS_API_URL = OFFICIAL_BALLOTS_API_URL
OFFICIAL_RESULT_POSTS_API_URL = wordpress_include_url(
  'posts', [item[2] for item in OFFICIAL_RESULTS if item[1] == 'posts'])
OFFICIAL_RESULT_PAGES_API_URL = wordpress_include_url(
  'pages', [item[2] for item in OFFICIAL_RESULTS if item[1] == 'pages'])
OFFICIAL_RESULTS_API_URLS = (
  OFFICIAL_RESULT_POSTS_API_URL,
  OFFICIAL_RESULT_PAGES_API_URL,
)
# Retained as a public import alias while fetchers migrate from search to the
# deterministic result manifest.
OFFICIAL_WINNERS_SEARCH_API_URL = OFFICIAL_RESULT_POSTS_API_URL

YEAR_RE = re.compile(r'(?:19|20)\d{2}')
HEADING_TAGS = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6')

CATEGORY_BOUNDARIES = frozenset({
  'anthology',
  'anthology of the year',
  'best anthology',
  'best novel',
  'best novella',
  'chapbook',
  'comic',
  'comic graphic novel',
  'cover art',
  'event',
  'fiction magazine',
  'fiction podcast',
  'film',
  'graphic novel',
  'magazine',
  'novel',
  'novel of the year',
  'nonfiction podcast',
  'non fiction podcast',
  'publisher',
  'short fiction',
  'short fiction of the year',
  'short story collection',
  'short story collection of the year',
  'soundtrack',
  'tv',
  'television',
  'video game',
})

EXCLUDED_CATEGORY_FRAGMENTS = (
  'artist',
  'chapbook',
  'comic',
  'cover art',
  'event',
  'film',
  'graphic novel',
  'magazine',
  'podcast',
  'publisher',
  'short fiction',
  'soundtrack',
  'tattoo',
  'television',
  'tv',
  'video game',
)

EXPECTED_BALLOT_COUNTS = {
  'novel': {
    2011: 9, 2012: 5, 2013: 5, 2014: 5, 2015: 6, 2016: 6,
    2017: 5, 2018: 5, 2019: 5, 2020: 5, 2021: 5, 2024: 5,
  },
  'novella': {
    2015: 6, 2016: 6, 2017: 5, 2018: 5, 2019: 5, 2020: 5,
    2021: 5, 2024: 5,
  },
  'short story collection': {
    2011: 6, 2012: 5, 2013: 5, 2014: 5, 2015: 6, 2016: 6,
    2017: 5, 2018: 5, 2019: 5, 2020: 5, 2021: 5, 2024: 5,
  },
  'anthology': {
    2011: 9, 2012: 5, 2013: 5, 2014: 5, 2015: 6, 2016: 6,
    2017: 5, 2018: 5, 2019: 5, 2020: 5, 2021: 5,
  },
}

# The 2011 ballot supplied publisher names rather than editor credits for
# several anthologies. These narrow corrections keep all official nominees
# matchable without treating publishers or individual contributors as editors.
CREDIT_CORRECTIONS = {
  (2011, 'anthology', 'holiday of the dead'): (
    'Holiday of the Dead', ('David Dunwoody',)),
  (2011, 'anthology', 'undead tales'): (
    'Undead Tales', ('Armand Rosamilia',)),
  (2011, 'anthology', 'alt dead the alternative dead anthology'): (
    'Alt-Dead: The Alternative Dead Anthology', ('Peter Mark May',)),
  (2011, 'anthology', 'fogbound from 5'): (
    'Fogbound From 5', ('Peter Mark May',)),
  (2011, 'anthology', '13 tales of dark fiction'): (
    '13: Tales of Dark Fiction', ('Adam Bradley',)),
  (2011, 'anthology', 'the spectrum collection'): (
    'The Spectrum Collection', ('John Prescott',)),
  (2012, 'anthology',
   'the weird a compendium of strange and dark stories'): (
    'The Weird: A Compendium of Strange and Dark Stories',
    ('Ann VanderMeer', 'Jeff VanderMeer')),
  (2013, 'anthology', 'the booked anthology'): (
    'The Booked. Anthology', ('Pela Via', 'Robb Olson', 'Livius Nedin')),
  (2020, 'novella', 'ring shout'): (
    'Ring Shout', ('P. Djèlí Clark',)),
}

TITLE_IDENTITY_ALIASES = {
  'the nameless dark a collection': 'the nameless dark',
  'burnt tongues': (
    'burnt tongues an anthology of transgressive short stories'),
}


def category_key(value):
  return normalize_heading(value).replace('non fiction', 'nonfiction')


def clean_source_text(value):
  value = normalize_line(value).replace('\x00', ' ').replace('\xa0', ' ')
  replacements = {
    '\u2018': "'",
    '\u2019': "'",
    '\u201c': '"',
    '\u201d': '"',
    '\u2013': '-',
    '\u2014': '-',
    '\u2026': '...',
  }
  for old, new in replacements.items():
    value = value.replace(old, new)
  return normalize_line(value)


class ThisIsHorrorParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def parse_official_ballots(
      self, source, base_url, name, category, category_aliases=()):
    rows = []
    notes = [
      'Official This Is Horror ballot pages provide the complete historical '
      'nominee set for each available award cycle.',
    ]
    for html, title, link in self.source_documents(source):
      year = self.award_year(html, title)
      if year is None:
        notes.append(f'Official ballot has no parseable award year: {title}')
        continue
      soup = self.soup(html)
      source_order = 0
      matched_heading = False
      for heading in soup.find_all(HEADING_TAGS):
        if not self.category_matches(
            self.node_text(heading), category, category_aliases):
          continue
        matched_heading = True
        for text in self.category_work_texts(heading):
          parsed = self.parse_work_text(
            text, RESULT_SHORTLISTED, year=year, category=category)
          if parsed is None:
            if text:
              notes.append(
                f'Official ballot {year} {category} row could not be parsed: '
                f'{text}')
            continue
          parsed.update({
            '_source_kind': 'ballot',
            '_source_order': source_order,
          })
          rows.append(self.build_award_entry(
            parsed, link or base_url, year, category))
          source_order += 1
      if not matched_heading and self.category_expected_in_year(category, year):
        notes.append(
          f'Official ballot {year} did not expose the {category} heading.')
    return self.parsed_from_rows(name, base_url, rows, notes)

  def parse_official_current(
      self, source, base_url, name, category, category_aliases=()):
    """Compatibility wrapper; the source may contain one or all ballots."""
    return self.parse_official_ballots(
      source, base_url, name, category, category_aliases)

  def parse_official_winners(
      self, source, base_url, name, category, category_aliases=(),
      award_year=None):
    rows = []
    notes = [
      'Official This Is Horror result pages identify the winner and runner-up '
      'within each complete official ballot.',
    ]
    for html, title, link in self.source_documents(source):
      year = award_year or self.award_year(html, title)
      if year is None:
        continue
      soup = self.soup(html)
      for heading in soup.find_all(HEADING_TAGS):
        if not self.category_matches(
            self.node_text(heading), category, category_aliases):
          continue
        for node in heading.find_all_next():
          if node is not heading and node.name in HEADING_TAGS:
            break
          if node.name not in ('p', 'li'):
            continue
          for result_label, work_text in self.result_segments(
              self.node_text(node)):
            parsed = self.parse_work_text(
              work_text,
              RESULT_WINNER if result_label == 'winner'
              else RESULT_SHORTLISTED,
              year=year,
              category=category)
            if parsed is None:
              notes.append(
                f'Official results {year} {category} row could not be parsed: '
                f'{work_text}')
              continue
            parsed.update({
              '_source_kind': 'result',
              '_runner_up': result_label == 'runner-up',
            })
            rows.append(self.build_award_entry(
              parsed, link or base_url, year, category))
    return self.parsed_from_rows(name, base_url, rows, notes)

  def parse_goodreads(self, html, base_url, name, category, category_aliases=()):
    rows = []
    notes = [
      'Goodreads is checked as a paginated diagnostic supplement; official '
      'This Is Horror ballots remain authoritative.',
    ]
    soup = self.soup(html)
    for book_row in soup.find_all('tr', itemtype='http://schema.org/Book'):
      title_node = book_row.find(class_='bookTitle')
      author_node = book_row.find(class_='authorName')
      if title_node is None or author_node is None:
        continue
      title = self.clean_title(self.node_text(title_node))
      authors = self.split_contributors(self.node_text(author_node))
      for label_node in book_row.find_all('i'):
        parsed_label = self.parse_goodreads_label(
          self.node_text(label_node), category, category_aliases)
        if parsed_label is None:
          continue
        year, result = parsed_label
        rows.append(self.build_award_entry(
          {
            'title': title,
            'authors': authors,
            'result': result,
            '_source_kind': 'goodreads',
          },
          base_url,
          year,
          category))
    if not rows:
      rows.extend(self.parse_goodreads_lines(
        soup, base_url, category, category_aliases))
    return self.parsed_from_rows(name, base_url, rows, notes)

  def parse_goodreads_lines(
      self, soup, base_url, category, category_aliases):
    rows = []
    lines = self.goodreads_lines(soup)
    previous_label_index = -1
    for index, line in enumerate(lines):
      parsed_label = self.parse_goodreads_label(
        line, category, category_aliases)
      if parsed_label is None:
        continue
      year, result = parsed_label
      work = self.goodreads_work_from_buffer(
        lines[previous_label_index + 1:index])
      previous_label_index = index
      if work is None:
        continue
      title, author = work
      rows.append(self.build_award_entry(
        {
          'title': self.clean_title(title),
          'authors': self.split_contributors(author),
          'result': result,
          '_source_kind': 'goodreads',
        },
        base_url,
        year,
        category))
    return rows

  def combine_results(self, name, base_url, *parsed_results):
    notes = [
      'Official ballot order is retained after winner and runner-up '
      'promotion.',
      'The 2022 and 2023 cycles are explicit empty gaps pending official '
      'Legacy Awards shortlists or results.',
      'No completed official 2025 ballot or result page is available.',
    ]
    rows = []
    for parsed in parsed_results:
      if not parsed:
        continue
      notes.extend(parsed.get('notes', ()))
      rows.extend(dict(entry) for entry in parsed.get('entries', ()))

    ballots = [row for row in rows if row.get('_source_kind') == 'ballot']
    results = [row for row in rows if row.get('_source_kind') == 'result']
    goodreads = [row for row in rows if row.get('_source_kind') == 'goodreads']
    if ballots:
      rows = self.reconcile_official_results(ballots, results, notes)
      covered_years = {row.get('award_year') for row in rows}
      ignored = sum(
        1 for row in goodreads if row.get('award_year') in covered_years)
      if ignored:
        notes.append(
          'Goodreads overlaps were excluded in favor of official ballot rows.')
    else:
      rows = results + goodreads

    if self.category_name(rows) == 'anthology':
      notes.append(
        'This Is Horror - Anthology is discontinued after the 2021 cycle; '
        'the resumed 2024 awards did not include an anthology category.')
    parsed = self.parsed_from_rows(name, base_url, rows, notes)
    for entry in parsed.get('entries', ()):
      entry.pop('_source_kind', None)
      entry.pop('_source_order', None)
      entry.pop('_runner_up', None)
    return parsed

  def reconcile_official_results(self, ballots, results, notes):
    rows = self.dedupe_rows(ballots)
    by_key = {self.row_key(row): row for row in rows}
    for result in results:
      existing = by_key.get(self.row_key(result))
      if existing is None:
        notes.append(
          'Official result did not match its ballot row and was not added: '
          f"{result.get('award_year')} {result.get('title')}")
        continue
      existing['result'] = result.get('result', existing.get('result'))
      existing['_runner_up'] = bool(result.get('_runner_up'))
      if result.get('source'):
        existing['source'] = result['source']
    return rows

  def discover_result_detail_urls(
      self, source, category, category_aliases=()):
    urls = []
    for html, title, link in self.source_documents(source):
      year = self.award_year(html, title)
      if year not in (2011, 2012, 2013):
        continue
      soup = self.soup(html)
      for anchor in soup.find_all('a', href=True):
        if not self.category_matches(
            self.node_text(anchor), category, category_aliases):
          continue
        url = urljoin(link or OFFICIAL_AWARDS_URL, anchor.get('href') or '')
        item = (year, url)
        if url and item not in urls:
          urls.append(item)
    return tuple(urls)

  def discover_winner_api_urls(self, source):
    """Compatibility helper for older callers of winner-search results."""
    urls = []
    text = self.decode_source(source)
    parsed = self.parse_json_source(text)
    if not isinstance(parsed, list):
      return tuple(urls)
    for item in parsed:
      if not isinstance(item, dict):
        continue
      title = self.html_text(item.get('title') or '')
      if not self.looks_like_winners_title(title):
        continue
      href = self.first_self_href(item)
      if href and href not in urls:
        urls.append(href)
    return tuple(urls)

  def validate_official_ballot_result(self, parsed, category):
    expected = self.expected_counts(category)
    actual = {}
    for entry in (parsed or {}).get('entries', ()):
      year = int(entry.get('award_year', 0) or 0)
      actual[year] = actual.get(year, 0) + 1
    if actual != expected:
      details = ', '.join(
        f'{year}: expected {count}, got {actual.get(year, 0)}'
        for year, count in expected.items()
        if actual.get(year) != count)
      extras = sorted(set(actual) - set(expected))
      if extras:
        details += f'; unexpected years: {extras}'
      raise ValueError(
        f'This Is Horror official {category} ballot coverage is incomplete: '
        f'{details}')

  def validate_combined_result(self, parsed, category):
    expected_years = set(self.expected_counts(category))
    winners = {}
    runners_up = {}
    for entry in (parsed or {}).get('entries', ()):
      year = int(entry.get('award_year', 0) or 0)
      if entry.get('result') == RESULT_WINNER:
        winners[year] = winners.get(year, 0) + 1
      if (
          entry.get('_runner_up') or
          entry.get('position') == f'{year}.01'):
        runners_up[year] = runners_up.get(year, 0) + 1
    bad_winners = {
      year: winners.get(year, 0)
      for year in expected_years
      if winners.get(year, 0) != 1
    }
    bad_runners = {
      year: runners_up.get(year, 0)
      for year in expected_years
      if runners_up.get(year, 0) != 1
    }
    if bad_winners or bad_runners:
      raise ValueError(
        'This Is Horror official result coverage is incomplete: '
        f'winners={bad_winners}, runner-ups={bad_runners}')

  def validate_goodreads_page(self, html):
    soup = self.soup(html)
    structural = soup.find_all('tr', itemtype='http://schema.org/Book')
    has_label = any(
      'This is Horror Award' in self.node_text(label)
      for row in structural
      for label in row.find_all('i'))
    if not has_label and 'This is Horror Award' not in self.html_text(html):
      raise ValueError(
        'This Is Horror Goodreads source did not contain award book rows.')

  def discover_goodreads_page_urls(self, html, base_url=GOODREADS_URL):
    soup = self.soup(html)
    urls = [GOODREADS_URL]
    for link in soup.find_all('a', href=True):
      href = link.get('href') or ''
      text = self.node_text(link)
      if 'award/show/23539-this-is-horror-award' not in href:
        continue
      if 'page=' not in href and not text.isdigit():
        continue
      url = urljoin(base_url, href)
      if re.search(r'[?&]page=1(?:&|$)', url):
        url = GOODREADS_URL
      if url not in urls:
        urls.append(url)
    return tuple(urls)

  def parse_work_text(self, text, result, year=None, category=None):
    text = self.clean_work_text(text)
    if not text:
      return None
    parsed = self.parse_parenthetical_editor(text)
    if parsed is None:
      parsed = self.parse_edited_by(text)
    if parsed is None:
      parsed = self.parse_by(text)
    if parsed is None:
      parsed = self.parse_dash(text)
    if parsed is None:
      parsed = self.parse_comma(text)

    if parsed is None:
      title = self.clean_title(text)
      authors = []
    else:
      title, credit = parsed
      title = self.clean_title(title)
      authors = self.split_contributors(credit)

    correction = self.credit_correction(year, category, title)
    if correction is not None:
      title, corrected_authors = correction
      authors = list(corrected_authors)
    if not title or not authors:
      return None
    return {'title': title, 'authors': authors, 'result': result}

  def parse_parenthetical_editor(self, text):
    match = re.match(
      r'^(.*?)\s*\(\s*(?:co-)?edited\s+by\s+(.+?)\s*\)\s*$',
      text,
      re.I)
    return (match.group(1), match.group(2)) if match is not None else None

  def parse_edited_by(self, text):
    match = re.match(
      r'^(.*?)\s*,?\s+(?:co-)?edited\s+by\s+(.+)$', text, re.I)
    return (match.group(1), match.group(2)) if match is not None else None

  def parse_by(self, text):
    # Greedy title capture intentionally selects the final byline delimiter;
    # "by" may occur inside a title or an editor parenthetical.
    match = re.match(r'^(.*)\s*,?\s+by\s+(.+)$', text, re.I)
    return (match.group(1), match.group(2)) if match is not None else None

  def parse_dash(self, text):
    match = re.match(r'^(.*?)\s+[-]\s+(.+)$', text)
    return (match.group(1), match.group(2)) if match is not None else None

  def parse_comma(self, text):
    title, author = split_title_author(text)
    return (title, author) if title and author else None

  def split_contributors(self, value):
    value = self.clean_author(value)
    parts = [
      part.strip(' "\'.,;')
      for part in re.split(r'\s*(?:,|&|\band\b)\s*', value, flags=re.I)
      if part.strip(' "\'.,;')
    ]
    authors = []
    for part in parts:
      if authors and re.fullmatch(r'(?:Jr|Sr|II|III|IV|V)\.?', part, re.I):
        authors[-1] = f'{authors[-1]}, {part}'
      elif part not in authors:
        authors.append(part)
    return authors

  def credit_correction(self, year, category, title):
    if year is None or not category or not title:
      return None
    return CREDIT_CORRECTIONS.get((
      int(year),
      self.canonical_category(category),
      category_key(title),
    ))

  def clean_work_text(self, text):
    text = strip_square_notes(clean_source_text(text))
    text = re.sub(
      r'^\s*(?:winner|runner-up|runner up|nominee|finalist)s?\s*:\s*',
      '',
      text,
      flags=re.I)
    text = re.sub(r'^\s*(?:[-*]|\u2022)\s*', '', text)
    text = re.sub(
      r'\s*\((?:winner|runner-up|runner up|finalist)\)\s*$',
      '',
      text,
      flags=re.I)
    return normalize_line(text.strip(' "\'.,;'))

  def clean_title(self, value):
    value = strip_publication_notes(clean_source_text(value))
    value = re.sub(r'\s*,?\s*published\s+by\s+.+$', '', value, flags=re.I)
    return value.strip(' "\'.,;')

  def clean_author(self, value):
    value = clean_source_text(value)
    value = re.sub(
      r'^\s*(?:by|(?:co-)?edited\s+by)\s+', '', value, flags=re.I)
    value = re.sub(
      r'\s*\((?:Goodreads Author|Author|Editor|Editors?)\)\s*',
      ' ',
      value,
      flags=re.I)
    value = re.sub(
      r'\s*,?\s*(?:eds?|editors?)\.?$', '', value, flags=re.I)
    return strip_editor_marker(
      strip_publication_notes(value)).strip(' "\'.,;')

  def result_segments(self, text):
    matches = list(re.finditer(
      r'\b(Winner|Runner(?:-|\s)?up)\s*:\s*', text, re.I))
    segments = []
    for index, match in enumerate(matches):
      end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
      label = category_key(match.group(1)).replace('runner up', 'runner-up')
      work_text = clean_source_text(text[match.end():end]).strip(' .;')
      if work_text:
        segments.append((label, work_text))
    return segments

  def parse_goodreads_label(self, line, category, category_aliases):
    match = re.match(
      r'^This\s+is\s+Horror\s+Award\s+(Nominee\s+)?for\s+(.+?)\s*'
      r'(?:\((?:finalist|runner-up|runner up|nominee)\))?\s*'
      r'\(((?:19|20)\d{2})\)$',
      line,
      re.I)
    if match is None or not self.category_matches(
        match.group(2), category, category_aliases):
      return None
    return (
      int(match.group(3)),
      RESULT_SHORTLISTED if match.group(1) else RESULT_WINNER,
    )

  def goodreads_work_from_buffer(self, lines):
    lines = [line for line in lines if not self.is_goodreads_noise(line)]
    if not lines:
      return None
    by_indexes = [
      index for index, line in enumerate(lines)
      if category_key(line) == 'by'
    ]
    if by_indexes:
      by_index = by_indexes[-1]
      title = self.previous_goodreads_line(lines, by_index)
      author = self.next_goodreads_line(lines, by_index)
      if title and author:
        return title, author
    if len(lines) >= 2:
      return lines[-2], lines[-1]
    return None

  def previous_goodreads_line(self, lines, index):
    for line in reversed(lines[:index]):
      if not self.is_goodreads_noise(line):
        return line
    return ''

  def next_goodreads_line(self, lines, index):
    for line in lines[index + 1:]:
      if not self.is_goodreads_noise(line):
        return line
    return ''

  def is_goodreads_noise(self, line):
    key = category_key(line)
    return (
      not key or
      key in {'winners', 'nominees', 'winner', 'nominee', 'finalist'} or
      key.startswith('score ') or
      key.startswith('rating ') or
      key.startswith('avg rating') or
      'ratings' in key or
      'want to read' in key or
      'rate this book' in key)

  def category_work_texts(self, heading):
    list_rows = []
    paragraphs = []
    for node in heading.find_all_next():
      if node is not heading and node.name in HEADING_TAGS:
        break
      if node.name == 'li':
        text = self.node_text(node)
        if text:
          list_rows.append(text)
      elif node.name == 'p':
        text = self.node_text(node)
        if text:
          paragraphs.append(text)
    if list_rows:
      return tuple(list_rows)
    rows = []
    for paragraph in paragraphs:
      rows.extend(self.split_numbered_rows(paragraph))
    return tuple(rows)

  def split_numbered_rows(self, text):
    matches = list(re.finditer(r'(?<!\S)\d{1,2}\.\s+', text))
    if not matches:
      return (text,)
    rows = []
    for index, match in enumerate(matches):
      end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
      row = clean_source_text(text[match.end():end])
      if row:
        rows.append(row)
    return tuple(rows)

  def source_documents(self, source):
    text = self.decode_source(source)
    parsed = self.parse_json_source(text)
    if parsed is None:
      return ((text, '', ''),)
    if isinstance(parsed, dict):
      parsed = (parsed,)
    documents = []
    for item in parsed:
      if not isinstance(item, dict):
        continue
      content = item.get('content') or {}
      title = item.get('title') or item.get('title_text') or ''
      content_html = content.get('rendered') if isinstance(content, dict) else ''
      title_html = title.get('rendered') if isinstance(title, dict) else title
      title_text = self.html_text(title_html)
      link = item.get('link') or item.get('url') or ''
      if content_html:
        documents.append((content_html, title_text, link))
    return tuple(documents) or ((text, '', ''),)

  def parse_json_source(self, text):
    stripped = (text or '').lstrip()
    if not stripped.startswith(('[', '{')):
      return None
    try:
      return json.loads(stripped)
    except Exception:
      return None

  def decode_source(self, source):
    if isinstance(source, bytes):
      return UnicodeDammit(source).unicode_markup
    return source or ''

  def soup(self, html):
    soup = BeautifulSoup(self.decode_source(html), 'html.parser')
    for removable in soup.find_all(['script', 'style', 'sup']):
      removable.decompose()
    for br in soup.find_all('br'):
      br.replace_with('\n')
    return soup

  def goodreads_lines(self, soup):
    text = soup.get_text('\n')
    return [
      clean_source_text(line)
      for line in text.splitlines()
      if clean_source_text(line)
    ]

  def node_text(self, node):
    return clean_source_text(node.get_text(' ', strip=True))

  def html_text(self, html):
    return clean_source_text(
      BeautifulSoup(
        self.decode_source(html), 'html.parser').get_text(' ', strip=True))

  def award_year(self, html, title=''):
    for value in (title, self.html_text(html)):
      match = re.search(
        r'This\s+Is\s+Horror\s+Awards?\s+((?:19|20)\d{2})',
        value,
        re.I)
      if match is not None:
        return int(match.group(1))
    match = YEAR_RE.search(title or '')
    return int(match.group(0)) if match is not None else None

  def first_self_href(self, item):
    links = item.get('_links') or {}
    self_links = links.get('self') if isinstance(links, dict) else None
    if isinstance(self_links, list) and self_links:
      href = self_links[0].get('href') if isinstance(self_links[0], dict) else ''
      if href:
        return href
    return item.get('url') or item.get('link') or ''

  def looks_like_winners_title(self, title):
    key = category_key(title)
    return 'this is horror awards' in key and 'winner' in key

  def clean_category_label(self, label):
    label = clean_source_text(label)
    label = re.sub(r'\s*\([^)]*\)\s*$', '', label)
    return normalize_line(label.strip(' :'))

  def category_matches(self, label, category, category_aliases):
    label_key = category_key(self.clean_category_label(label))
    if any(fragment in label_key for fragment in EXCLUDED_CATEGORY_FRAGMENTS):
      return False
    aliases = {category, *(category_aliases or ())}
    alias_keys = {category_key(alias) for alias in aliases if alias}
    if label_key in alias_keys:
      return True
    return label_key.replace(' of the year', '') in alias_keys

  def canonical_category(self, category):
    key = category_key(category).replace(' of the year', '')
    if key == 'collection':
      return 'short story collection'
    return key

  def expected_counts(self, category):
    key = self.canonical_category(category)
    return dict(EXPECTED_BALLOT_COUNTS.get(key, {}))

  def category_expected_in_year(self, category, year):
    return year in self.expected_counts(category)

  def canonical_title_key(self, title):
    key = category_key(title)
    return TITLE_IDENTITY_ALIASES.get(key, key)

  def category_name(self, rows):
    for row in rows:
      category = row.get('category')
      if category:
        return self.canonical_category(category)
    return ''

  def parsed_from_rows(self, name, base_url, rows, notes):
    rows = self.dedupe_rows(rows)
    by_year = {}
    for row in rows:
      year = str(row.get('award_year', ''))
      if not year:
        continue
      clean_row = dict(row)
      clean_row.pop('position', None)
      by_year.setdefault(year, []).append(clean_row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      year_rows = sorted(
        by_year[year],
        key=lambda row: (
          0 if row.get('result') == RESULT_WINNER else
          1 if row.get('_runner_up') else 2,
          row.get('_source_order', 0)))
      entries.extend(assign_positions(
        year_rows, int(year), tied_winners_share_position=True))
    return self.parsed_result(
      name,
      base_url,
      sorted(
        entries,
        key=lambda item: position_sort_key(item.get('position', ''))),
      notes=self.unique_notes(notes))

  def dedupe_rows(self, rows):
    ordered = []
    by_key = {}
    for row in rows:
      key = self.row_key(row)
      existing = by_key.get(key)
      if existing is None:
        existing = dict(row)
        by_key[key] = existing
        ordered.append(existing)
        continue
      if (
          existing.get('result') != RESULT_WINNER and
          row.get('result') == RESULT_WINNER):
        existing.update(row)
    return ordered

  def row_key(self, row):
    return (
      str(row.get('award_year', '')),
      self.canonical_category(row.get('category', '')),
      self.canonical_title_key(row.get('title', '')),
    )

  def unique_notes(self, notes):
    unique = []
    for note in notes:
      if note and note not in unique:
        unique.append(note)
    return unique
