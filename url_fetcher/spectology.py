#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""URL fetcher for the finite Spectology book-club podcast archive."""

from .generic import (
  CATEGORY_FANTASY,
  CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
  CATEGORY_SCIENCE_FICTION,
  UrlFetcherGeneric,
)


class UrlFetcherSpectology(UrlFetcherGeneric):

  source_id = 'spectology'
  NAME = 'Spectology (discontinued)'
  URL = 'https://www.spectology.com/feed.xml'
  order = 59
  FILTER_CATEGORIES = (
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    CATEGORY_SCIENCE_FICTION,
    CATEGORY_FANTASY,
  )
  options = {'match_series': False}

  def source_choices(self):
    return ({'label': 'Automatic', 'value': 'automatic'},)

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.spectology import SpectologyParser
    except ImportError:
      from parser.spectology import SpectologyParser
    return SpectologyParser()

  def parse(self, payload, **_kwargs):
    return self.parser().parse(payload, self.URL, self.NAME)
