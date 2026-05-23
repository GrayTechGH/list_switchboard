#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
r/Fantasy result parsers.

Maintenance notes:
- Reddit output is unstable: the same post may arrive as structured HTML,
  flattened text, old markdown, or a network/security interstitial.
- RedditResultsParser.parse() tries strategies from most structured to least
  structured so we preserve source links when available.
- Strategy helpers return [] when they do not recognise a table; only parse()
  raises a user-facing error after all strategies fail.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.base import ListParserBase
  from calibre_plugins.list_switchboard.parser.generic import (
    matching_schema, normalize_header, row_entry, strip_markdown_link,
    token_header_start,
  )
except ImportError:
  from .base import ListParserBase
  from .generic import (
    matching_schema, normalize_header, row_entry, strip_markdown_link,
    token_header_start,
  )


BLOCKED_MARKERS = (
  'Please wait for verification',
  'blocked by network security',
  'You have been blocked',
  'whoa there, pardner',
)


class RedditResultsParser(ListParserBase):
  """
  Parses r/Fantasy ranked-results tables from Reddit posts.

  Invariants:
  - Strategies are tried in fidelity order: HTML table (preserves source URLs),
    token table, plain-text table, markdown table.
  - The first strategy that returns entries wins; remaining strategies are not
    attempted.
  - A blocked/verification page raises ValueError before any strategy runs.
  """

  def parse(self, html, name, url, schemas):
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text('\n', strip=True)
    message = _blocked_message(text)
    if message:
      raise ValueError(message)
    for strategy in (
        _parse_html_table,
        _parse_token_table,
        _parse_plain_text_table,
        _parse_markdown_table,
    ):
      entries = strategy(soup, text, url, schemas)
      if entries:
        return {
          'name': name,
          'url': url,
          'entries': entries,
        }
    raise ValueError('Could not find the r/Fantasy results table in the fetched page.')


def _blocked_message(text):
  for marker in BLOCKED_MARKERS:
    if marker.casefold() in text.casefold():
      return (
        'Reddit returned a verification or blocking page instead of the r/Fantasy results table. '
        'Enable List Switchboard debug logging and retry to record the fetched page preview.')
  return None


def _parse_html_table(soup, _text, url, schemas):
  """Parse real table markup and preserve title links as Goodreads source URLs."""
  for row in soup.select('table tr'):
    headers = [cell.get_text(' ', strip=True) for cell in row.find_all('th')]
    schema = matching_schema(headers, schemas)
    if not schema:
      continue
    table = row.find_parent('table')
    if table is None:
      continue
    entries = []
    for data_row in table.select('tr')[1:]:
      cells = data_row.find_all(['td', 'th'])
      if len(cells) < len(schema['headers']):
        continue
      values = [cell.get_text(' ', strip=True) for cell in cells]
      source_url = ''
      title_index = schema['fields'].index('title')
      link = cells[title_index].find('a', href=True)
      if link is not None:
        source_url = urljoin(url, link['href'])
      data = row_entry(values, schema, source_url=source_url)
      if data:
        entries.append(data)
    if entries:
      return entries
  return []


def _parse_token_table(_soup, text, _url, schemas):
  """Parse pages where the table was flattened into one text token per cell."""
  strings = [line.strip() for line in text.splitlines() if line.strip()]
  for schema in schemas:
    start = token_header_start(strings, schema['headers'])
    if start is None:
      continue
    entries = []
    index = start
    width = len(schema['headers'])
    while index + width - 1 < len(strings):
      values = strings[index:index + width]
      data = row_entry(values, schema)
      if not data:
        break
      entries.append(data)
      index += width
    if entries:
      return entries
  return []


def _parse_plain_text_table(_soup, text, _url, schemas):
  """Parse fixed-ish text tables where columns are separated by 2+ spaces."""
  for schema in schemas:
    entries = []
    in_table = False
    for line in text.splitlines():
      line = line.strip()
      if not line:
        continue
      if not in_table:
        if normalize_header(line) == normalize_header(' '.join(schema['headers'])):
          in_table = True
        continue
      columns = re.split(r'\s{2,}', line)
      if len(columns) < len(schema['headers']):
        if entries:
          break
        continue
      data = row_entry(columns[:len(schema['headers'])], schema)
      if not data:
        if entries:
          break
        continue
      entries.append(data)
    if entries:
      return entries
  return []


def _parse_markdown_table(_soup, text, _url, schemas):
  """Parse old Reddit markdown tables after BeautifulSoup exposes raw text."""
  rows = []
  for line in text.splitlines():
    line = line.strip()
    if not line.startswith('|') or not line.endswith('|'):
      continue
    columns = [column.strip() for column in line.strip('|').split('|')]
    rows.append(columns)
  for index, row in enumerate(rows):
    schema = matching_schema(row, schemas)
    if not schema:
      continue
    entries = []
    for values in rows[index + 1:]:
      if len(values) < len(schema['headers']):
        continue
      data = row_entry([strip_markdown_link(value) for value in values], schema)
      if data:
        entries.append(data)
    if entries:
      return entries
  return []


def parse_reddit_results(html, name, url, schemas):
  return RedditResultsParser().parse(html, name, url, schemas)
