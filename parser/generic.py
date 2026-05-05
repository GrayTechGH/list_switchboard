#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

import re


def token_header_start(strings, headers):
  width = len(headers)
  for index in range(len(strings) - width + 1):
    if [normalize_header(value) for value in strings[index:index + width]] == [
        normalize_header(value) for value in headers]:
      return index + width
  return None


def matching_schema(headers, schemas):
  normalized = [normalize_header(value) for value in headers]
  for schema in schemas:
    expected = [normalize_header(value) for value in schema['headers']]
    if normalized[:len(expected)] == expected:
      return schema
  return None


def normalize_header(value):
  return re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip()


def row_entry(values, schema, source_url=''):
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
  value = value.strip()
  match = re.match(r'^(\d+)\s*/\s*(.+)$', value)
  if match:
    return match.group(1).strip(), match.group(2).strip()
  return value, ''


def valid_entry(data):
  position = data.get('position', '').strip()
  title = data.get('title', '').strip()
  author = data.get('author', '').strip()
  if not position.isdigit() or not title or not author:
    return False
  votes = data.get('votes', '').strip()
  return not votes or bool(re.search(r'\d', votes))


def strip_markdown_link(value):
  value = value.strip()
  if '](' not in value or not value.startswith('['):
    return value
  close = value.find('](')
  return value[1:close].strip()


def position_sort_key(position):
  try:
    return float(position)
  except Exception:
    return 0.0
