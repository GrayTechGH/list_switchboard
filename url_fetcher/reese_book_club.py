#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherGeneric,
)


class UrlFetcherReeseBookClub(UrlFetcherGeneric):

  source_id = 'reese_book_club'
  NAME = "Reese's Book Club"
  URL = 'https://reesesbookclub.com/our-picks/'
  order = 42
  FILTER_CATEGORIES = (CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,)
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.reese_book_club import ReeseBookClubParser
    except ImportError:
      from parser.reese_book_club import ReeseBookClubParser
    return ReeseBookClubParser()

  def parse(self, html, **kwargs):
    return self.parser().parse(
      html, self.URL, self.NAME, fetch_url=kwargs.get('fetch_url'))


class UrlFetcherReeseBookClubYA(UrlFetcherReeseBookClub):

  source_id = 'reese_book_club_ya'
  NAME = "Reese's Book Club - YA Picks"
  order = 43
  FILTER_CATEGORIES = (
    CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  )

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.reese_book_club import ReeseBookClubYAParser
    except ImportError:
      from parser.reese_book_club import ReeseBookClubYAParser
    return ReeseBookClubYAParser()
