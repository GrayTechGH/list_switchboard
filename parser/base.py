#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Common parser interface for imported list sources.

Maintenance notes:
- URL fetchers are the app-facing recipe wrappers; parser classes own source
  shape parsing and parser-level metadata.
- `get_filter_list()` is intentionally available on every parser so future UI
  code can ask parser objects for category filters without knowing the concrete
  parser family.
"""

import re


CATEGORY_UNKNOWN = 'Unknown'
CATEGORY_SCIENCE_FICTION = 'Science Fiction'
CATEGORY_FANTASY = 'Fantasy'
CATEGORY_HORROR_DARK_FICTION = 'Horror & Dark Fiction'
CATEGORY_CRIME_MYSTERY_THRILLER = 'Crime, Mystery & Thriller'
CATEGORY_ROMANCE = 'Romance'
CATEGORY_LITERARY_GENERAL_FICTION = 'Literary & General Fiction'
CATEGORY_NONFICTION = 'Nonfiction'
CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE = "Young Adult & Children's Literature"
CATEGORY_REGIONAL_NATIONAL_AWARDS = 'Regional & National Awards'
CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS = 'General Audience Book Clubs'
CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS = 'Online Community Book Clubs'

DEFAULT_FILTER_CATEGORIES = (CATEGORY_UNKNOWN,)


def author_list(value):
  if value is None:
    values = []
  elif isinstance(value, str):
    values = [value] if value.strip() else []
  elif isinstance(value, (list, tuple, set)):
    values = list(value)
  else:
    values = [value]
  authors = []
  for author in values:
    text = str(author or '').strip()
    if text and text not in authors:
      authors.append(text)
  return authors


def source_object(url='', name='', source_id=''):
  return {
    'url': str(url or ''),
    'name': str(name or ''),
    'source_id': str(source_id or ''),
  }


def entry_source_object(url='', name='', source_id='', list_source=None):
  source = source_object(url, name, source_id)
  if not source.get('url') and not source.get('name') and not source.get('source_id'):
    return None
  if list_source is not None:
    if (
        source.get('url') == list_source.get('url')
        and source.get('name') in ('', list_source.get('name'))
        and source.get('source_id') in ('', list_source.get('source_id'))):
      return None
  return source


def imported_entry(position, title, authors, source=None, **metadata):
  entry = {
    'position': str(position or ''),
    'title': str(title or ''),
    'authors': author_list(authors),
  }
  if source is not None:
    entry['source'] = source
  for key, value in metadata.items():
    if value is not None:
      entry[key] = value
  return entry


def parsed_source(name='', url='', source_id=''):
  return source_object(url, name, source_id)


def filter_id(value):
  value = re.sub(r'&', ' and ', value or '')
  value = re.sub(r'[^a-z0-9]+', '_', value.casefold())
  return value.strip('_')


def filter_object(value, selected=True):
  if isinstance(value, dict):
    label = value.get('label', '')
    aliases = tuple(value.get('aliases', ()))
    selected = bool(value.get('selected', selected))
    filter_key = value.get('id') or filter_id(label)
  else:
    label = str(value)
    aliases = ()
    filter_key = filter_id(label)
  return {
    'id': filter_key,
    'label': label,
    'aliases': aliases,
    'selected': selected,
  }


class ListParserBase:
  """
  Base class for list parser implementations.

  Invariants:
  - `parse()` remains parser-specific and must be implemented by concrete
    parsers.
  - `get_filter_list()` always returns normalized filter dictionaries with the
    same keys, even when a parser has no source-specific filters yet.
  """

  FILTER_CATEGORIES = DEFAULT_FILTER_CATEGORIES

  def __init__(self, filter_categories=None):
    self.filter_categories = (
      tuple(filter_categories)
      if filter_categories is not None
      else tuple(self.FILTER_CATEGORIES)
    )

  def configure_filter_categories(self, filter_categories):
    self.filter_categories = tuple(filter_categories or ())
    return self

  def get_filter_list(self):
    categories = getattr(self, 'filter_categories', tuple(self.FILTER_CATEGORIES))
    return [filter_object(category) for category in categories]

  def parse(self, *args, **kwargs):
    raise NotImplementedError
