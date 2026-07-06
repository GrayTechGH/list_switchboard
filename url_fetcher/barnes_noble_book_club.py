#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS, UrlFetcherGeneric


class UrlFetcherBarnesNobleBookClub(UrlFetcherGeneric):

  source_id = 'barnes_noble_book_club'
  NAME = 'Barnes & Noble Book Club'
  URL = 'https://www.barnesandnoble.com/blog/'
  order = 47
  FILTER_CATEGORIES = (CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,)
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.barnes_noble_book_club import (
        BarnesNobleBookClubParser,
      )
    except ImportError:
      from parser.barnes_noble_book_club import BarnesNobleBookClubParser
    return BarnesNobleBookClubParser()

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME)
