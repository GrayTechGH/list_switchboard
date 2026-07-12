#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherGeneric,
)

try:
  from calibre_plugins.list_switchboard.parser.cbca_book_of_the_year import (
    ARCHIVE_URL,
    CATEGORY_EARLY_CHILDHOOD,
    CATEGORY_EVE_POWNALL,
    CATEGORY_MIDDLE_READERS,
    CATEGORY_NEW_ILLUSTRATOR,
    CATEGORY_OLDER_READERS,
    CATEGORY_PICTURE_BOOK,
    CATEGORY_YOUNGER_READERS,
  )
except ImportError:
  from parser.cbca_book_of_the_year import (
    ARCHIVE_URL,
    CATEGORY_EARLY_CHILDHOOD,
    CATEGORY_EVE_POWNALL,
    CATEGORY_MIDDLE_READERS,
    CATEGORY_NEW_ILLUSTRATOR,
    CATEGORY_OLDER_READERS,
    CATEGORY_PICTURE_BOOK,
    CATEGORY_YOUNGER_READERS,
  )


class UrlFetcherCBCABookOfTheYear(UrlFetcherGeneric):

  URL = ARCHIVE_URL
  MAX_RESPONSE_BYTES = 32 * 1024 * 1024
  FETCH_URLS = (ARCHIVE_URL,)
  order = 264
  options = {'match_series': False}
  AWARD_NAME = 'CBCA Book of the Year'
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.cbca_book_of_the_year import (
        CBCABookOfTheYearParser,
      )
    except ImportError:
      from parser.cbca_book_of_the_year import CBCABookOfTheYearParser
    return CBCABookOfTheYearParser(self.CATEGORY, self.CATEGORY_ALIASES)

  def parse(self, html, fetch_url=None, log=None, progress=None, **kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      fetch_url=fetch_url,
      current_year=kwargs.get('current_year'),
      log=log,
      progress=progress)


class UrlFetcherCBCABookOfTheYearOlderReaders(UrlFetcherCBCABookOfTheYear):

  source_id = 'cbca_book_of_the_year_older_readers'
  NAME = 'CBCA Book of the Year - Older Readers'
  CATEGORY = CATEGORY_OLDER_READERS
  CATEGORY_ALIASES = (
    'Book of the Year Award for Older Readers',
    'Book of the Year Award: Older Readers',
    'Book of the Year: Older Readers',
    'Book of the Year Award 1946 - 1981',
    'Older Readers',
  )


class UrlFetcherCBCABookOfTheYearYoungerReaders(UrlFetcherCBCABookOfTheYear):

  source_id = 'cbca_book_of_the_year_younger_readers'
  NAME = 'CBCA Book of the Year - Younger Readers'
  order = 265
  CATEGORY = CATEGORY_YOUNGER_READERS
  CATEGORY_ALIASES = (
    'Book of the Year Award for Younger Readers',
    'Book of the Year Award: Younger Readers',
    'Book of the Year: Younger Readers',
    'Younger Readers',
  )


class UrlFetcherCBCABookOfTheYearMiddleReaders(UrlFetcherCBCABookOfTheYear):

  source_id = 'cbca_book_of_the_year_middle_readers'
  NAME = 'CBCA Book of the Year - Middle Readers'
  order = 266
  CATEGORY = CATEGORY_MIDDLE_READERS
  CATEGORY_ALIASES = (
    'Book of the Year Award for Middle Readers',
    'Book of the Year Award: Middle Readers',
    'Book of the Year: Middle Readers',
    'Middle Readers',
  )


class UrlFetcherCBCABookOfTheYearEarlyChildhood(UrlFetcherCBCABookOfTheYear):

  source_id = 'cbca_book_of_the_year_early_childhood'
  NAME = 'CBCA Book of the Year - Early Childhood'
  order = 267
  CATEGORY = CATEGORY_EARLY_CHILDHOOD
  CATEGORY_ALIASES = (
    'Book of the Year Award for Early Childhood',
    'Book of the Year Award: Early Childhood',
    'Book of the Year: Early Childhood',
    'Early Childhood',
  )


class UrlFetcherCBCABookOfTheYearPictureBook(UrlFetcherCBCABookOfTheYear):

  source_id = 'cbca_book_of_the_year_picture_book'
  NAME = 'CBCA Book of the Year - Picture Book'
  order = 268
  CATEGORY = CATEGORY_PICTURE_BOOK
  CATEGORY_ALIASES = (
    'Picture Book of the Year Award',
    'Picture Book of the Year',
    'Picture Book',
  )


class UrlFetcherCBCABookOfTheYearEvePownall(UrlFetcherCBCABookOfTheYear):

  source_id = 'cbca_book_of_the_year_eve_pownall'
  NAME = 'CBCA Book of the Year - Eve Pownall'
  order = 269
  CATEGORY = CATEGORY_EVE_POWNALL
  CATEGORY_ALIASES = (
    'Book of the Year Award: Eve Pownall Award for Information Books',
    'Eve Pownall Award for Information Books',
    'Eve Pownall Award',
    'Eve Pownall',
  )


class UrlFetcherCBCABookOfTheYearNewIllustrator(UrlFetcherCBCABookOfTheYear):

  source_id = 'cbca_book_of_the_year_new_illustrator'
  NAME = 'CBCA Book of the Year - New Illustrator'
  order = 270
  CATEGORY = CATEGORY_NEW_ILLUSTRATOR
  CATEGORY_ALIASES = (
    'Book of the Year Award for New Illustrator',
    'Book of the Year Award: New Illustrator',
    'CBCA Award for New Illustrator',
    'Crichton Award for New Illustrator',
    'New Illustrator',
  )
