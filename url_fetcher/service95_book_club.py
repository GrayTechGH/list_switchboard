#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS, UrlFetcherGeneric


class UrlFetcherService95BookClub(UrlFetcherGeneric):

  source_id = 'service95_book_club'
  NAME = 'Service95 Book Club'
  URL = 'https://www.service95.com/book-club'
  order = 48
  FILTER_CATEGORIES = (CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,)
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.service95_book_club import Service95BookClubParser
    except ImportError:
      from parser.service95_book_club import Service95BookClubParser
    return Service95BookClubParser()

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME)
