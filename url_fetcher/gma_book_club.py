#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherGeneric,
)


class UrlFetcherGMABookClub(UrlFetcherGeneric):

  source_id = 'gma_book_club'
  NAME = 'GMA Book Club'
  URL = 'https://www.goodmorningamerica.com/culture/story/shop-gma-book-club-picks-list--81520726'
  order = 46
  FILTER_CATEGORIES = (CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,)
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.gma_book_club import GMABookClubParser
    except ImportError:
      from parser.gma_book_club import GMABookClubParser
    return GMABookClubParser()

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME)


class UrlFetcherGMABookClubYA(UrlFetcherGeneric):

  source_id = 'gma_book_club_ya'
  NAME = 'GMA Book Club YA'
  URL = 'https://www.goodmorningamerica.com/shop/story/shop-gma-book-club-ya-picks-114243858'
  order = 47
  FILTER_CATEGORIES = (
    CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  )
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.gma_book_club import GMAYABookClubParser
    except ImportError:
      from parser.gma_book_club import GMAYABookClubParser
    return GMAYABookClubParser()

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME)
