#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
CWA Dagger parser for the official past-winners archive.

Maintenance notes:
- The CWA archive exposes result cards rather than a stable data table. Parse
  one isolated card at a time, then use narrow text matching inside that card.
- Translator credits are useful display context on the source page, but should
  not become part of the work author used for matching.
"""

import re
from urllib.parse import urljoin

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

  def parse(self, html, base_url, name, category,
            fetch_url=None, log=None, progress=None):
    notes = []
    rows = self.parse_page(html, base_url, category)
    pages_seen = {base_url}
    page_number = 1
    next_url = self.next_page_url(html, base_url)
    self._progress(progress, page_number, None, f'Parsed {name} page {page_number}...')

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
      page_rows = self.parse_page(page_html, next_url, category)
      if not page_rows:
        break
      rows.extend(page_rows)
      self._progress(progress, page_number, None, f'Parsed {name} page {page_number}...')
      next_url = self.next_page_url(page_html, next_url)

    entries = self.entries_from_rows(self.dedupe_rows(rows))
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes)

  def parse_page(self, html, source_url, category):
    root = lxml_html.fromstring(html or '<html></html>')
    rows = []
    for card in self.result_cards(root, category):
      row = self.parse_card(card, source_url, category)
      if row is not None:
        rows.append(row)
    return rows

  def result_cards(self, root, category):
    seen = set()
    for link in root.xpath('//a[@href]'):
      text = self.node_text(link)
      if self.looks_like_result_text(text, category):
        ident = id(link)
        if ident not in seen:
          seen.add(ident)
          yield link
    for node in root.xpath('//article|//div|//li'):
      text = self.node_text(node)
      if self.looks_like_result_text(text, category):
        if node.xpath('.//a[@href]'):
          continue
        ident = id(node)
        if ident not in seen:
          seen.add(ident)
          yield node

  def looks_like_result_text(self, text, category):
    return (
      self.year_result_match(text) is not None and
      normalize_heading(category) in normalize_heading(text)
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
      re.escape(label).replace(r'\ ', r'\s+')
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
      key = (
        row['award_year'],
        normalize_heading(row['category']),
        normalize_heading(row['title']),
        normalize_heading(row['author']),
        row.get('result'),
      )
      if key in seen:
        continue
      seen.add(key)
      deduped.append(row)
    return deduped

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
    html, base_url, name, category, fetch_url=None, log=None, progress=None):
  return CWADaggerParser().parse(
    html,
    base_url,
    name,
    category,
    fetch_url=fetch_url,
    log=log,
    progress=progress)
