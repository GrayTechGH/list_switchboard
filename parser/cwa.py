#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
CWA Dagger parser for the official past-winners archive.

Maintenance notes:
- The CWA archive exposes result cards rather than a stable data table. Parse
  one isolated card at a time, then use narrow text matching inside that card.
- Pagination progress requires the numeric `Page X of Y` total exposed by the
  archive; Calibre's progress adapter does not accept an unknown denominator.
- Historical and Translation use narrow year windows. Gold and Steel use
  full-history accolade streams whose duplicate boundary pages are retried to
  the pagination-derived expected count. The site randomizes equal-year cards,
  so ordinary one-pass pagination can silently omit rows.
- Translator credits are useful display context on the source page, but should
  not become part of the work author used for matching.
"""

import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from lxml import html as lxml_html

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, assign_positions, normalize_heading, normalize_line,
    strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    AwardParserBase, assign_positions, normalize_heading, normalize_line,
    strip_publication_notes,
  )
  from .generic import position_sort_key


AWARD_NAME = 'CWA Dagger'
MAX_PAGES = 50
ARCHIVE_PAGE_SIZE = 12
MAX_STABILITY_RETRIES = 4


class CWADaggerParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME
  RESULT_LABELS = {
    'winner': 'winner',
    'shortlisted': 'shortlisted',
    'longlisted': 'longlisted',
    'highly commended': 'nominee',
    'runner up': 'nominee',
    'commended': 'nominee',
    'special mention': 'nominee',
    'merit': 'nominee',
  }
  ACCOLADE_GROUPS = (
    ('winner', 'highly commended', 'runner up', 'commended',
     'special mention', 'merit'),
    ('shortlisted',),
    ('longlisted',),
  )

  def parse(self, html, base_url, name, category,
            fetch_url=None, log=None, progress=None, start_year=None,
            category_aliases=(), archive_by_accolade=False):
    if fetch_url is not None and start_year is not None:
      if archive_by_accolade:
        return self.parse_accolade_archives(
          html, base_url, name, category, start_year, fetch_url, log, progress,
          category_aliases)
      return self.parse_year_archives(
        html, base_url, name, category, start_year, fetch_url, log, progress,
        category_aliases)

    notes = []
    rows = self.parse_page(html, base_url, category, category_aliases)
    pages_seen = {base_url}
    page_number = 1
    next_url = self.next_page_url(html, base_url)
    page_count = self.page_count(html)
    self._progress(
      progress, page_number, page_count, f'Parsed {name} page {page_number}...')

    while fetch_url is not None and next_url and page_number < MAX_PAGES:
      if next_url in pages_seen:
        break
      pages_seen.add(next_url)
      page_number += 1
      try:
        page_html = fetch_url(next_url)
      except Exception as err:
        notes.append(f'{AWARD_NAME} page {page_number} could not be fetched: {err}')
        self._log(log, 'fetch-failed', {'url': next_url, 'error': str(err)})
        break
      page_rows = self.parse_page(
        page_html, next_url, category, category_aliases)
      if not page_rows:
        break
      rows.extend(page_rows)
      self._progress(
        progress, page_number, page_count, f'Parsed {name} page {page_number}...')
      next_url = self.next_page_url(page_html, next_url)

    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes)

  def parse_accolade_archives(
      self, html, base_url, name, category, start_year, fetch_url, log, progress,
      category_aliases=()):
    initial_rows = self.parse_page(
      html, base_url, category, category_aliases)
    if not initial_rows:
      raise ValueError(f'{AWARD_NAME} did not expose any {category} entries.')
    latest_year = max(int(row['award_year']) for row in initial_rows)
    states = []

    # Discover each stream first so subsequent progress has one stable numeric
    # denominator. Reaching 100% early can make QProgressDialog reset visually.
    for labels in self.ACCOLADE_GROUPS:
      accolades = tuple(label.replace(' ', '-') for label in labels)
      url = self.year_archive_url(
        base_url, start_year, latest_year, accolades=accolades)
      try:
        page_html = fetch_url(url)
      except Exception as err:
        self._log(log, 'fetch-failed', {'url': url, 'error': str(err)})
        raise ValueError(
          f'{AWARD_NAME} {", ".join(labels)} archive could not be fetched: '
          f'{err}') from err
      states.append({
        'labels': labels,
        'url': url,
        'html': page_html,
        'pages': self.page_count(page_html),
      })

    total_pages = sum(state['pages'] for state in states)
    completed_pages = len(states)
    rows = []
    for state in states:
      stream_rows, stream_urls, page_rows = self.fetch_accolade_pages(
        state, category, category_aliases, fetch_url, log,
        lambda page_number, message: self._progress(
          progress,
          min(
            completed_pages + page_number - 1,
            max(total_pages - 1, 0)),
          total_pages,
          message))
      completed_pages += max(state['pages'] - 1, 0)
      expected_count = self.expected_archive_count(page_rows)
      stream_rows = self.complete_unstable_archive(
        stream_rows, stream_urls, page_rows, expected_count,
        category, category_aliases,
        fetch_url, log, state['labels'], start_year, latest_year, progress,
        total_pages)
      rows.extend(stream_rows)

    expected_years = {
      str(year) for year in range(int(start_year), latest_year + 1)
    }
    parsed_years = {row['award_year'] for row in rows}
    if not rows or parsed_years != expected_years:
      raise ValueError(
        f'{AWARD_NAME} years {start_year}-{latest_year} '
        'did not return the expected entries.')
    self._progress(
      progress, total_pages, total_pages,
      f'Parsed {name} official accolade archives...')
    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      [])

  def fetch_accolade_pages(
      self, state, category, category_aliases, fetch_url, log,
      progress_message):
    labels = state['labels']
    group_label = self.accolade_group_label(labels)
    expected_results = {self.result_from_label(label) for label in labels}
    page_urls = [state['url']]
    page_rows = [self.parse_page(
      state['html'], state['url'], category, category_aliases)]
    next_url = self.next_page_url(state['html'], state['url'])
    for page_number in range(2, state['pages'] + 1):
      if not next_url:
        raise ValueError(
          f'{AWARD_NAME} {", ".join(labels)} archive omitted page '
          f'{page_number} of {state["pages"]}.')
      page_urls.append(next_url)
      try:
        page_html = fetch_url(next_url)
      except Exception as err:
        self._log(log, 'fetch-failed', {'url': next_url, 'error': str(err)})
        raise ValueError(
          f'{AWARD_NAME} {", ".join(labels)} archive page {page_number} '
          f'could not be fetched: {err}') from err
      page_rows.append(self.parse_page(
        page_html, next_url, category, category_aliases))
      next_url = self.next_page_url(page_html, next_url)
      progress_message(
        page_number,
        f'Parsed {category} {group_label} page '
        f'{page_number} of {state["pages"]}...')
    for row in (item for group in page_rows for item in group):
      if row['result'] not in expected_results:
        raise ValueError(
          f'{AWARD_NAME} {", ".join(labels)} archive returned an '
          'unexpected result type.')
    return self.dedupe_rows(
      item for group in page_rows for item in group), page_urls, page_rows

  def expected_archive_count(self, page_rows):
    # The archive fixes every full page at 12 cards. The final page therefore
    # supplies an exact count without another API request or a brittle fixture.
    if len(page_rows) == 1:
      return len(page_rows[0])
    if any(len(rows) != ARCHIVE_PAGE_SIZE for rows in page_rows[:-1]):
      raise ValueError(
        f'{AWARD_NAME} archive pagination did not expose '
        f'{ARCHIVE_PAGE_SIZE} entries per full page.')
    if not page_rows[-1] or len(page_rows[-1]) > ARCHIVE_PAGE_SIZE:
      raise ValueError(f'{AWARD_NAME} archive final page was malformed.')
    return ((len(page_rows) - 1) * ARCHIVE_PAGE_SIZE) + len(page_rows[-1])

  def complete_unstable_archive(
      self, rows, page_urls, page_rows, expected_count, category, category_aliases,
      fetch_url, log, labels, start_year, latest_year, progress, total_pages):
    rows = self.dedupe_rows(rows)
    group_label = self.accolade_group_label(labels)
    retry_urls = self.overlap_page_urls(page_rows, page_urls) or list(page_urls)
    for retry in range(1, MAX_STABILITY_RETRIES + 1):
      if len(rows) >= expected_count:
        break
      for url in retry_urls:
        try:
          retry_html = fetch_url(url)
        except Exception as err:
          self._log(log, 'fetch-failed', {'url': url, 'error': str(err)})
          continue
        rows = self.dedupe_rows(
          rows + self.parse_page(
            retry_html, url, category, category_aliases))
        self._progress(
          progress,
          max(total_pages - 1, 0),
          total_pages,
          f'Checking {category} {group_label} for pagination overlap '
          f'(pass {retry})...')
        if len(rows) >= expected_count:
          break
    if len(rows) != expected_count:
      raise ValueError(
        f'{AWARD_NAME} {", ".join(labels)} archive returned '
        f'{len(rows)} of {expected_count} expected entries for '
        f'{start_year}-{latest_year}.')
    return rows

  def accolade_group_label(self, labels):
    labels = tuple(labels or ())
    if len(labels) > 1:
      return 'winners and commendations'
    if labels == ('shortlisted',):
      return 'shortlist'
    if labels == ('longlisted',):
      return 'longlist'
    return labels[0] if labels else 'results'

  def overlap_page_urls(self, page_rows, page_urls):
    # Randomization affects the pages on either side of an equal-year boundary.
    # Retry just those pages so completeness does not require another full pass.
    first_page_by_key = {}
    retry_indexes = set()
    for page_index, rows in enumerate(page_rows):
      for row in rows:
        key = self.row_key(row)
        previous_page = first_page_by_key.get(key)
        if previous_page is not None and previous_page != page_index:
          retry_indexes.update((previous_page, page_index))
        else:
          first_page_by_key[key] = page_index
    return [page_urls[index] for index in sorted(retry_indexes)]

  def parse_year_archives(
      self, html, base_url, name, category, start_year, fetch_url, log, progress,
      category_aliases=()):
    initial_rows = self.parse_page(
      html, base_url, category, category_aliases)
    if not initial_rows:
      raise ValueError(f'{AWARD_NAME} did not expose any {category} entries.')
    latest_year = max(int(row['award_year']) for row in initial_rows)
    years = list(range(latest_year, int(start_year) - 1, -1))
    year_groups = [years[index:index + 2] for index in range(0, len(years), 2)]
    rows = []

    for index, year_group in enumerate(year_groups, start=1):
      newest_year = year_group[0]
      oldest_year = year_group[-1]
      url = self.year_archive_url(base_url, oldest_year, newest_year)
      try:
        group_html = fetch_url(url)
      except Exception as err:
        self._log(log, 'fetch-failed', {'url': url, 'error': str(err)})
        raise ValueError(
          f'{AWARD_NAME} years {oldest_year}-{newest_year} '
          f'could not be fetched: {err}') from err
      if self.page_count(group_html) == 1:
        group_rows = self.parse_page(
          group_html, url, category, category_aliases)
      elif len(year_group) == 1:
        group_rows = self.fetch_year_accolades(
          base_url, category, newest_year, fetch_url, log, category_aliases)
      else:
        group_rows = self.fetch_individual_years(
          base_url, category, year_group, fetch_url, log, category_aliases)
      expected_years = {str(year) for year in year_group}
      parsed_years = {row['award_year'] for row in group_rows}
      if not group_rows or parsed_years != expected_years:
        raise ValueError(
          f'{AWARD_NAME} years {oldest_year}-{newest_year} '
          'did not return the expected entries.')
      rows.extend(group_rows)
      self._progress(
        progress, index, len(year_groups),
        f'Parsed {name} years {oldest_year}-{newest_year}...')

    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      [])

  def fetch_individual_years(
      self, base_url, category, years, fetch_url, log, category_aliases=()):
    rows = []
    for year in years:
      url = self.year_archive_url(base_url, year)
      try:
        year_html = fetch_url(url)
      except Exception as err:
        self._log(log, 'fetch-failed', {'url': url, 'error': str(err)})
        raise ValueError(
          f'{AWARD_NAME} year {year} could not be fetched: {err}') from err
      if self.page_count(year_html) == 1:
        year_rows = self.parse_page(
          year_html, url, category, category_aliases)
      else:
        year_rows = self.fetch_year_accolades(
          base_url, category, year, fetch_url, log, category_aliases)
      if not year_rows or {row['award_year'] for row in year_rows} != {str(year)}:
        raise ValueError(
          f'{AWARD_NAME} year {year} did not return the expected entries.')
      rows.extend(year_rows)
    return rows

  def fetch_year_accolades(
      self, base_url, category, year, fetch_url, log, category_aliases=()):
    rows = []
    for labels in self.ACCOLADE_GROUPS:
      accolades = tuple(label.replace(' ', '-') for label in labels)
      url = self.year_archive_url(base_url, year, accolades=accolades)
      label_text = ', '.join(labels)
      try:
        accolade_html = fetch_url(url)
      except Exception as err:
        self._log(log, 'fetch-failed', {'url': url, 'error': str(err)})
        raise ValueError(
          f'{AWARD_NAME} year {year} {label_text} entries could not be fetched: '
          f'{err}') from err
      if self.page_count(accolade_html) != 1:
        raise ValueError(
          f'{AWARD_NAME} year {year} {label_text} entries unexpectedly span '
          'multiple pages.')
      accolade_rows = self.parse_page(
        accolade_html, url, category, category_aliases)
      expected_results = {self.result_from_label(label) for label in labels}
      if any(
          row['award_year'] != str(year) or row['result'] not in expected_results
          for row in accolade_rows):
        raise ValueError(
          f'{AWARD_NAME} year {year} {label_text} did not return the expected '
          'entries.')
      rows.extend(accolade_rows)
    return self.dedupe_rows(rows)

  def parse_page(self, html, source_url, category, category_aliases=()):
    root = lxml_html.fromstring(html or '<html></html>')
    rows = []
    for card in self.result_cards(root, category, category_aliases):
      row = self.parse_card(card, source_url, category)
      if row is not None:
        rows.append(row)
    return rows

  def result_cards(self, root, category, category_aliases=()):
    seen = set()
    for link in root.xpath('//a[@href]'):
      text = self.node_text(link)
      if self.looks_like_result_text(text, category, category_aliases):
        ident = id(link)
        if ident not in seen:
          seen.add(ident)
          yield link
    for node in root.xpath('//article|//div|//li'):
      text = self.node_text(node)
      if self.looks_like_result_text(text, category, category_aliases):
        if node.xpath('.//a[@href]'):
          continue
        ident = id(node)
        if ident not in seen:
          seen.add(ident)
          yield node

  def looks_like_result_text(self, text, category, category_aliases=()):
    categories = (category,) + tuple(category_aliases or ())
    return (
      self.year_result_match(text) is not None and
      any(
        normalize_heading(candidate) in normalize_heading(text)
        for candidate in categories)
    )

  def parse_card(self, card, source_url, category):
    lines = self.card_lines(card)
    text = normalize_line(' '.join(lines))
    year_result = self.year_result_match(text)
    if year_result is None:
      return None
    year = year_result.group('year')
    result = self.result_from_label(year_result.group('result'))
    prefix = text[:year_result.start()].strip()
    prefix = self.strip_category_suffix(prefix, category)
    title, author = self.title_author_from_card(card, prefix, category)
    if not title or not author:
      return None
    return {
      'award_year': year,
      'title': self.clean_title(title),
      'author': self.clean_author(author),
      'result': result,
      'source_url': self.card_url(card, source_url),
      'category': category,
    }

  def card_lines(self, card):
    return [
      line for line in (
        normalize_line(text)
        for text in card.xpath('.//text()')
      )
      if line
    ]

  def year_result_match(self, text):
    labels = '|'.join(
      re.escape(label).replace(r'\ ', r'[\s-]+')
      for label in sorted(self.RESULT_LABELS, key=len, reverse=True)
    )
    return re.search(
      r'(?P<year>(?:19|20)\d{2})\s*\|\s*(?P<result>' + labels + r')\b',
      text or '',
      re.I)

  def result_from_label(self, label):
    return self.RESULT_LABELS.get(normalize_heading(label), 'nominee')

  def strip_category_suffix(self, value, category):
    pattern = re.compile(r'\s+' + re.escape(category) + r'\s*$', re.I)
    stripped = pattern.sub('', value).strip()
    if stripped != value:
      return stripped
    normalized_category = normalize_heading(category)
    lines = value.split('\n')
    if lines and normalize_heading(lines[-1]) == normalized_category:
      return '\n'.join(lines[:-1]).strip()
    return value

  def title_author_from_card(self, card, prefix, category):
    title = self.text_by_class(card, ('title', 'book-title', 'work-title'))
    author = self.text_by_class(card, ('author', 'book-author', 'work-author'))
    if title and author:
      return title, author

    meaningful = [
      line for line in self.card_lines(card)
      if not self.line_is_metadata(line, category)
    ]
    if len(meaningful) >= 2:
      return meaningful[0], meaningful[1]

    match = re.match(r'^(.+?)\s+by\s+(.+)$', prefix, re.I)
    if match is not None:
      return match.group(1), match.group(2)
    return '', ''

  def text_by_class(self, card, class_names):
    for node in card.xpath('.//*'):
      classes = node.get('class') or ''
      normalized_classes = normalize_heading(classes)
      if any(normalize_heading(name) in normalized_classes for name in class_names):
        return self.node_text(node)
    return ''

  def line_is_metadata(self, line, category):
    text = normalize_heading(line)
    return (
      text == normalize_heading(category) or
      self.year_result_match(line) is not None or
      text in {'bookshop org', 'amazon', 'hive', 'website', 'instagram', 'threads'}
    )

  def card_url(self, card, source_url):
    href = card.get('href') if card.tag == 'a' else None
    if not href:
      hrefs = card.xpath('(.//a[@href])[1]/@href')
      href = hrefs[0] if hrefs else ''
    return urljoin(source_url, href) if href else source_url

  def next_page_url(self, html, source_url):
    root = lxml_html.fromstring(html or '<html></html>')
    rel_hrefs = root.xpath(
      '//a[@href and contains(concat(" ", normalize-space(@rel), " "), " next ")]/@href')
    if rel_hrefs:
      return urljoin(source_url, rel_hrefs[0])
    for link in root.xpath('//a[@href]'):
      text = self.node_text(link).casefold()
      if text in {'next', 'next »', '»'}:
        return urljoin(source_url, link.get('href'))
    return ''

  def page_count(self, html):
    root = lxml_html.fromstring(html or '<html></html>')
    match = re.search(
      r'\bPage\s+\d+\s+of\s+(\d+)\b', self.node_text(root), re.I)
    if match is None:
      return 1
    return min(max(int(match.group(1)), 1), MAX_PAGES)

  def year_archive_url(
      self, base_url, from_year, to_year=None, accolade=None, accolades=()):
    to_year = from_year if to_year is None else to_year
    parts = urlsplit(base_url)
    query = [
      (key, value) for key, value in parse_qsl(
        parts.query, keep_blank_values=True)
      if key not in {'from_year', 'to_year', 'past_winners_accolades[]'}
    ]
    query.extend((('from_year', str(from_year)), ('to_year', str(to_year))))
    if accolade:
      accolades = (accolade,) + tuple(accolades or ())
    for accolade_value in accolades or ():
      query.append(('past_winners_accolades[]', accolade_value))
    return urlunsplit((
      parts.scheme,
      parts.netloc,
      parts.path,
      urlencode(query),
      parts.fragment,
    ))

  def node_text(self, node):
    return normalize_line(' '.join(
      text.strip() for text in node.xpath('.//text()') if text.strip()))

  def clean_title(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    value = re.sub(r'\s+tr\.\s+.*$', '', normalize_line(value), flags=re.I)
    return strip_publication_notes(value).strip()

  def dedupe_rows(self, rows):
    deduped = []
    seen = set()
    for row in rows:
      key = self.row_key(row)
      if key in seen:
        continue
      seen.add(key)
      deduped.append(row)
    return deduped

  def row_key(self, row):
    return (
      row['award_year'],
      normalize_heading(row['category']),
      normalize_heading(row['title']),
      normalize_heading(row['author']),
      row.get('result'),
    )

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in by_year[year]
      ]
      entries.extend(assign_positions(award_rows, int(year)))
    return entries

  def _log(self, log, label, data):
    if log is not None:
      log(f'{AWARD_NAME} {label}: {data}')

  def _progress(self, progress, done, total, message):
    if progress is not None:
      progress(done, total, message)


def parse_cwa_dagger_awards(
    html, base_url, name, category, fetch_url=None, log=None, progress=None,
    start_year=None, category_aliases=(), archive_by_accolade=False):
  return CWADaggerParser().parse(
    html,
    base_url,
    name,
    category,
    fetch_url=fetch_url,
    log=log,
    progress=progress,
    start_year=start_year,
    category_aliases=category_aliases,
    archive_by_accolade=archive_by_accolade)
