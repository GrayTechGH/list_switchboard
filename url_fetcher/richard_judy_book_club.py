#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS, UrlFetcherGeneric


class UrlFetcherRichardJudyBookClub(UrlFetcherGeneric):

  source_id = 'richard_judy_book_club'
  NAME = 'Richard & Judy Book Club'
  URL = 'https://www.tgjonesonline.co.uk/books/book-club'
  order = 49
  FILTER_CATEGORIES = (CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,)
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.richard_judy_book_club import (
        RichardJudyBookClubParser,
      )
    except ImportError:
      from parser.richard_judy_book_club import RichardJudyBookClubParser
    return RichardJudyBookClubParser()

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME)
