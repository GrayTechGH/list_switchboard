#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""URL fetcher for the r/bookclub Previous Selections wiki."""

from .generic import CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS, UrlFetcherGeneric


class UrlFetcherRBookclub(UrlFetcherGeneric):

  source_id = 'r_bookclub_previous_selections'
  NAME = 'r/bookclub Previous Selections'
  URL = 'https://www.reddit.com/r/bookclub/wiki/previous/'
  JSON_URL = 'https://www.reddit.com/r/bookclub/wiki/previous.json?raw_json=1'
  SOURCE_VIEW_URL = 'https://www.reddit.com/r/bookclub/wiki/previous/?show_source='
  API_URL = 'https://api.reddit.com/r/bookclub/wiki/previous'
  FETCH_URLS = (JSON_URL, SOURCE_VIEW_URL, URL, API_URL)
  order = 54
  FILTER_CATEGORIES = (CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,)
  options = {'match_series': False}

  def source_choices(self):
    # These are transport representations of one official wiki, not separate
    # editorial sources that users need to choose between.
    return ({'label': 'Automatic', 'value': 'automatic'},)

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.r_bookclub import RBookclubParser
    except ImportError:
      from parser.r_bookclub import RBookclubParser
    return RBookclubParser()

  def parse(self, payload, **_kwargs):
    return self.parser().parse(payload, self.URL, self.NAME)
