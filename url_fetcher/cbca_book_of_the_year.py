#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherGeneric,
)
from .cbca_transport import CBCAOfficialFetchPolicy

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

  def fetch_and_parse(self, fetch_url, *args, **kwargs):
    policy = CBCAOfficialFetchPolicy(self, fetch_url, kwargs.get('log'))
    return super().fetch_and_parse(policy.fetch, *args, **kwargs)

  def parse(self, html, fetch_url=None, log=None, progress=None, **kwargs):
    try:
      from calibre_plugins.list_switchboard.parser.cbca_sources import soup_for
      from calibre_plugins.list_switchboard.parser.cbca_updates import fetch_cbca
    except ImportError:
      from parser.cbca_sources import soup_for
      from parser.cbca_updates import fetch_cbca
    if fetch_url is not None and soup_for(html).find('details') is not None:
      return fetch_cbca(self, self.parser(), html, fetch_url,
        kwargs.get('cached_parsed'), kwargs.get('incremental_update', False),
        kwargs.get('current_year'), progress)
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      fetch_url=fetch_url,
      current_year=kwargs.get('current_year'),
      log=log,
      progress=progress)


class UrlFetcherCBCABookOfTheYearOlderReaders(UrlFetcherCBCABookOfTheYear):

  SUPPORTS_INCREMENTAL_UPDATE = True
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

  SUPPORTS_INCREMENTAL_UPDATE = True
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

  """Unregistered prototype; future implementation is tracked in local TASKS.md."""

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

  SUPPORTS_INCREMENTAL_UPDATE = True
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

  SUPPORTS_INCREMENTAL_UPDATE = True
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

  SUPPORTS_INCREMENTAL_UPDATE = True
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

  SUPPORTS_INCREMENTAL_UPDATE = True
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
