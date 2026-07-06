#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS, UrlFetcherGeneric


class UrlFetcherOprahBookClub(UrlFetcherGeneric):

  source_id = 'oprah_book_club'
  NAME = "Oprah's Book Club"
  URL = 'https://www.oprahdaily.com/entertainment/books/g23067476/oprah-book-club-list/'
  order = 41
  FILTER_CATEGORIES = (CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,)
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.oprah_book_club import OprahBookClubParser
    except ImportError:
      from parser.oprah_book_club import OprahBookClubParser
    return OprahBookClubParser()

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME)
