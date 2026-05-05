#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Shared parser helpers for schema-driven list tables.

Schema contract:
- A schema is a dict with `headers` and `fields` in the same column order.
- `headers` are human-facing table labels and are normalized before matching.
- `fields` are canonical output keys such as position, title, author, votes,
  rank_change, and ratings.

Maintenance notes:
- These helpers intentionally accept several imperfect source shapes: real HTML
  tables, markdown tables, and text extracted from pages where table structure
  was flattened.
- row_entry() is deliberately strict: an entry must have numeric position,
  title, and author. This prevents table captions, totals, and prose from
  leaking into import matching.
"""

import re


def token_header_start(strings, headers):
  """
  Return the first index after a header sequence in flattened text tokens.

  Invariant:
  - `strings` is already stripped and empty tokens were removed.
  - Complexity: O(n * h), where n is token count and h is header width.
  """
  width = len(headers)
  for index in range(len(strings) - width + 1):
    if [normalize_header(value) for value in strings[index:index + width]] == [
        normalize_header(value) for value in headers]:
      return index + width
  return None


def matching_schema(headers, schemas):
  """
  Pick the first schema whose expected headers prefix-match the observed row.

  Maintenance note:
  - Prefix matching allows source tables to append extra columns without
    invalidating the import recipe.
  """
  normalized = [normalize_header(value) for value in headers]
  for schema in schemas:
    expected = [normalize_header(value) for value in schema['headers']]
    if normalized[:len(expected)] == expected:
      return schema
  return None


def normalize_header(value):
  """Normalize display headers so punctuation/case drift does not break recipes."""
  return re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip()


def row_entry(values, schema, source_url=''):
  """
  Convert one table row into the normalized recipe-entry shape.

  Invariant:
  - `values` and schema['fields'] must be in the same order.
  - Returns None for non-book rows rather than raising.
  """
  fields = schema['fields']
  data = {}
  for field, value in zip(fields, values):
    data[field] = strip_markdown_link(value).strip()
  rank, rank_change = split_rank_change(data.get('position', ''))
  data['position'] = rank or data.get('position', '')
  if rank_change and not data.get('rank_change'):
    data['rank_change'] = rank_change
  if not valid_entry(data):
    return None
  result = {
    'position': data.get('position', ''),
    'title': data.get('title', ''),
    'author': data.get('author', ''),
  }
  for key in ('votes', 'rank_change', 'ratings'):
    if data.get(key):
      result[key] = data[key]
  if source_url:
    result['source_url'] = source_url
  return result


def split_rank_change(value):
  """Split combined rank/change values such as "2 / +1" into separate fields."""
  value = value.strip()
  match = re.match(r'^(\d+)\s*/\s*(.+)$', value)
  if match:
    return match.group(1).strip(), match.group(2).strip()
  return value, ''


def valid_entry(data):
  """Reject totals, notes, and partial rows before they reach matching."""
  position = data.get('position', '').strip()
  title = data.get('title', '').strip()
  author = data.get('author', '').strip()
  if not position.isdigit() or not title or not author:
    return False
  votes = data.get('votes', '').strip()
  return not votes or bool(re.search(r'\d', votes))


def strip_markdown_link(value):
  """Return the label from a simple `[label](url)` markdown link."""
  value = value.strip()
  if '](' not in value or not value.startswith('['):
    return value
  close = value.find('](')
  return value[1:close].strip()


def position_sort_key(position):
  """Sort imported positions numerically while keeping invalid values stable at 0."""
  try:
    return float(position)
  except Exception:
    return 0.0
