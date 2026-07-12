#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""URL fetcher for the r/bookclub Previous Selections wiki."""

from .generic import CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS, UrlFetcherGeneric


class UrlFetcherRBookclub(UrlFetcherGeneric):

  source_id = 'r_bookclub_previous_selections'
  NAME = 'r/bookclub Previous Selections'
  URL = 'https://www.reddit.com/r/bookclub/wiki/previous/'
  OLD_REDDIT_URL = 'https://old.reddit.com/r/bookclub/wiki/previous/'
  WAYBACK_URL = (
    'https://web.archive.org/web/20250405185632id_/'
    'https://www.reddit.com/r/bookclub/wiki/previous/'
  )
  WAYBACK_MARKER = '<!-- list-switchboard-r-bookclub-wayback-20250405 -->'
  JSON_URL = 'https://www.reddit.com/r/bookclub/wiki/previous.json?raw_json=1'
  SOURCE_VIEW_URL = 'https://www.reddit.com/r/bookclub/wiki/previous/?show_source='
  API_URL = 'https://api.reddit.com/r/bookclub/wiki/previous'
  FETCH_URLS = (
    OLD_REDDIT_URL, WAYBACK_URL, JSON_URL, SOURCE_VIEW_URL, URL, API_URL)
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

  def fetch_url(self, fetch_url, url):
    payload = super().fetch_url(fetch_url, url)
    if url == self.WAYBACK_URL and str(payload or '').lstrip().startswith('<'):
      return self.WAYBACK_MARKER + str(payload)
    return payload

  def parse(self, payload, **_kwargs):
    archived = self.WAYBACK_MARKER in str(payload or '')
    parsed = self.parser().parse(
      payload, self.WAYBACK_URL if archived else self.URL, self.NAME)
    if archived:
      parsed.setdefault('notes', []).append(
        'Internet Archive snapshot captured 2025-04-05; selections added '
        'after the snapshot date are not included.')
    return parsed
