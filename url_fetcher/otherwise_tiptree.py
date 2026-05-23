#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_FANTASY,
  CATEGORY_SCIENCE_FICTION,
  UrlFetcherGeneric,
)


OTHERWISE_TIPTREE_URL = 'https://www.sfadb.com/Otherwise_Award'


class UrlFetcherOtherwiseTiptreeBooksAndSeries(UrlFetcherGeneric):

  source_id = 'otherwise_tiptree_books_and_series'
  NAME = 'Otherwise/Tiptree - Books and Series'
  FILTER_CATEGORIES = (
    CATEGORY_SCIENCE_FICTION,
    CATEGORY_FANTASY,
  )
  URL = OTHERWISE_TIPTREE_URL
  FETCH_URLS = (OTHERWISE_TIPTREE_URL,)
  order = 160
  options = {
    'match_series': False,
  }

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.otherwise_tiptree import (
        OtherwiseTiptreeAwardsParser,
      )
    except ImportError:
      from parser.otherwise_tiptree import OtherwiseTiptreeAwardsParser

    return OtherwiseTiptreeAwardsParser()

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      fetch_url=fetch_url,
      log=log,
      progress=progress)
