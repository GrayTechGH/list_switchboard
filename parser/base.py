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
