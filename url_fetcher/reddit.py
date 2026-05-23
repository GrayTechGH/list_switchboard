#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_FANTASY,
  CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
  UrlFetcherGeneric,
)


class UrlFetcherReddit(UrlFetcherGeneric):

  FILTER_CATEGORIES = (
    CATEGORY_FANTASY,
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
  )

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.reddit import RedditResultsParser
    except ImportError:
      from parser.reddit import RedditResultsParser

    return RedditResultsParser()

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.NAME, self.URL, self.schemas)
