#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherGeneric,
)


class UrlFetcherCostaWhitbreadBase(UrlFetcherGeneric):

  order = 243
  options = {'match_series': False}
  CATEGORY = ''
  FILTER_CATEGORIES = (CATEGORY_REGIONAL_NATIONAL_AWARDS,)

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.costa_whitbread import (
        CostaWhitbreadCategoryParser,
      )
    except ImportError:
      from parser.costa_whitbread import CostaWhitbreadCategoryParser
    return CostaWhitbreadCategoryParser(self.NAME, self.CATEGORY)

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME)


class UrlFetcherCostaWhitbreadNovel(UrlFetcherCostaWhitbreadBase):

  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'costa_whitbread_novel'
  NAME = 'Costa/Whitbread Book Award - Novel (discontinued)'
  URL = 'https://en.wikipedia.org/wiki/Costa_Book_Award_for_Novel'
  CATEGORY = 'Novel'


class UrlFetcherCostaWhitbreadFirstNovel(UrlFetcherCostaWhitbreadBase):

  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'costa_whitbread_first_novel'
  NAME = 'Costa/Whitbread Book Award - First Novel (discontinued)'
  URL = 'https://en.wikipedia.org/wiki/Costa_Book_Award_for_First_Novel'
  CATEGORY = 'First Novel'


class UrlFetcherCostaWhitbreadBiography(UrlFetcherCostaWhitbreadBase):

  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'costa_whitbread_biography'
  NAME = 'Costa/Whitbread Book Award - Biography (discontinued)'
  URL = 'https://en.wikipedia.org/wiki/Costa_Book_Award_for_Biography'
  CATEGORY = 'Biography'


class UrlFetcherCostaWhitbreadChildrensBook(UrlFetcherCostaWhitbreadBase):

  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'costa_whitbread_childrens_book'
  NAME = "Costa/Whitbread Book Award - Children's Book (discontinued)"
  URL = 'https://en.wikipedia.org/wiki/Costa_Book_Award_for_Children%27s_Book'
  CATEGORY = "Children's Book"


class UrlFetcherCostaWhitbreadBookOfTheYear(UrlFetcherCostaWhitbreadBase):

  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_NONFICTION,
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'costa_whitbread_book_of_the_year'
  NAME = 'Costa/Whitbread Book of the Year (discontinued)'
  URL = 'https://en.wikipedia.org/wiki/Costa_Book_Awards'
  CATEGORY = 'Book of the Year'

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.costa_whitbread import (
        CostaWhitbreadBookOfTheYearParser,
      )
    except ImportError:
      from parser.costa_whitbread import CostaWhitbreadBookOfTheYearParser
    return CostaWhitbreadBookOfTheYearParser()
