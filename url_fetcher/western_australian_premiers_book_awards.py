#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherGeneric,
)


WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Western_Australian_Premier%27s_Book_Awards'
OFFICIAL_REFERENCE_URL = (
  'https://slwa.wa.gov.au/whats-on/awards-fellowships/'
  'wa-premiers-book-awards/awards-archive')


class UrlFetcherWesternAustralianPremiersBookAwards(UrlFetcherGeneric):

  URL = WIKIPEDIA_URL
  OFFICIAL_REFERENCE_URL = OFFICIAL_REFERENCE_URL
  FETCH_URLS = ()
  order = 244
  options = {'match_series': False}
  AWARD_NAME = "Western Australian Premier's Book Awards"
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.western_australian_premiers_book_awards import (
        WesternAustralianPremiersBookAwardsWikipediaParser,
      )
    except ImportError:
      from parser.western_australian_premiers_book_awards import (
        WesternAustralianPremiersBookAwardsWikipediaParser,
      )
    return WesternAustralianPremiersBookAwardsWikipediaParser(
      self.CATEGORY, self.CATEGORY_ALIASES)

  def parse(self, html, **_kwargs):
    return self.create_parser().parse(html, self.URL, self.NAME)


class UrlFetcherWesternAustralianPremiersBookAwardsBookOfTheYear(
    UrlFetcherWesternAustralianPremiersBookAwards):

  FILTER_CATEGORIES = (CATEGORY_REGIONAL_NATIONAL_AWARDS,)
  source_id = 'western_australian_premiers_book_awards_book_of_the_year'
  NAME = "Western Australian Premier's Book Awards - Book of the Year"
  CATEGORY = 'Book of the Year'
  CATEGORY_ALIASES = (
    'Book of the Year',
    'Overall',
    'Overall Winner',
    'Premier\'s Prize',
    'Premier’s Prize',
    'Premier\'s Prize for Book of the Year',
    'Premier’s Prize for Book of the Year',
  )


class UrlFetcherWesternAustralianPremiersBookAwardsFiction(
    UrlFetcherWesternAustralianPremiersBookAwards):

  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'western_australian_premiers_book_awards_fiction'
  NAME = "Western Australian Premier's Book Awards - Fiction"
  CATEGORY = 'Fiction'
  CATEGORY_ALIASES = (
    'Fiction',
    'Fiction Book of the Year',
  )


class UrlFetcherWesternAustralianPremiersBookAwardsNonfiction(
    UrlFetcherWesternAustralianPremiersBookAwards):

  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'western_australian_premiers_book_awards_nonfiction'
  NAME = "Western Australian Premier's Book Awards - Nonfiction"
  CATEGORY = 'Nonfiction'
  CATEGORY_ALIASES = (
    'Nonfiction',
    'Non-fiction',
    'Nonfiction Book of the Year',
    'Non-Fiction Book of the Year',
  )


class UrlFetcherWesternAustralianPremiersBookAwardsEmergingWriter(
    UrlFetcherWesternAustralianPremiersBookAwards):

  FILTER_CATEGORIES = (CATEGORY_REGIONAL_NATIONAL_AWARDS,)
  source_id = 'western_australian_premiers_book_awards_emerging_writer'
  NAME = "Western Australian Premier's Book Awards - Emerging Writer"
  CATEGORY = 'Emerging Writer'
  CATEGORY_ALIASES = (
    'Emerging Writer',
    'Emerging Writer Book of the Year',
    'Emerging Writer Award',
  )


class UrlFetcherWesternAustralianPremiersBookAwardsChildrens(
    UrlFetcherWesternAustralianPremiersBookAwards):

  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'western_australian_premiers_book_awards_childrens'
  NAME = "Western Australian Premier's Book Awards - Children's Book"
  CATEGORY = "Children's Book"
  CATEGORY_ALIASES = (
    "Children's Book",
    "Children's Book of the Year",
    "Children's Books",
    "Children's book",
    "Children's books",
  )


class UrlFetcherWesternAustralianPremiersBookAwardsYoungAdult(
    UrlFetcherWesternAustralianPremiersBookAwards):

  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'western_australian_premiers_book_awards_young_adult'
  NAME = "Western Australian Premier's Book Awards - Young Adult Book"
  CATEGORY = 'Young Adult Book'
  CATEGORY_ALIASES = (
    'Young Adult Book',
    'Young Adult Book of the Year',
    'Writing for Young Adults',
    'Young Adult',
  )
