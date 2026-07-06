#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS, UrlFetcherGeneric


class UrlFetcherReadWithJenna(UrlFetcherGeneric):

  source_id = 'read_with_jenna'
  NAME = 'Read With Jenna'
  URL = 'https://www.today.com/shop/read-jenna-book-club-list-today-s-jenna-bush-hager-t164652'
  order = 43
  FILTER_CATEGORIES = (CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,)
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.read_with_jenna import ReadWithJennaParser
    except ImportError:
      from parser.read_with_jenna import ReadWithJennaParser
    return ReadWithJennaParser()

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME)
