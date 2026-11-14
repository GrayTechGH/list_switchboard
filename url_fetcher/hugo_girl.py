#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""URL fetcher for the Hugo, Girl! numbered book-discussion archive."""

from .generic import (
  CATEGORY_FANTASY,
  CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
  CATEGORY_SCIENCE_FICTION,
  UrlFetcherGeneric,
)


class UrlFetcherHugoGirl(UrlFetcherGeneric):

  source_id = 'hugo_girl'
  NAME = 'Hugo, Girl!'
  LIST_NAME = 'Hugo Girl!'
  URL = 'https://hugogirl.libsyn.com/rss'
  ARCHIVE_URL = 'https://www.hugogirlpodcast.com/all-episodes'
  order = 60
  FILTER_CATEGORIES = (
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    CATEGORY_SCIENCE_FICTION,
    CATEGORY_FANTASY,
  )
  options = {'match_series': False}

  @property
  def display_url(self):
    return self.ARCHIVE_URL

  def fallback_urls(self, url):
    return (self.ARCHIVE_URL,) if url == self.URL else ()

  def source_label_for_url(self, url, _index):
    return 'Libsyn RSS' if url == self.URL else 'All Episodes archive'

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.hugo_girl import HugoGirlParser
    except ImportError:
      from parser.hugo_girl import HugoGirlParser
    return HugoGirlParser()

  def parse(self, payload, **_kwargs):
    return self.parser().parse(payload, self.LIST_NAME)
