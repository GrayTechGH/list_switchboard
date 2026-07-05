#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_ROMANCE,
  UrlFetcherGeneric,
)


class UrlFetcherBooksellersBestAward(UrlFetcherGeneric):

  source_id = 'booksellers_best_award'
  NAME = "Booksellers' Best Award"
  URL = (
    'https://web.archive.org/cdx?url=www.gdrwa.org/contests.html'
    '&output=json&fl=timestamp,original,statuscode,mimetype,digest'
    '&filter=statuscode:200&collapse=digest')
  DISPLAY_URL = 'https://web.archive.org/web/*/http://www.gdrwa.org/contests.html'
  order = 255
  options = {'match_series': False}
  FILTER_CATEGORIES = (CATEGORY_ROMANCE, CATEGORY_REGIONAL_NATIONAL_AWARDS)

  @property
  def display_url(self):
    return self.DISPLAY_URL

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.booksellers_best import ( # type: ignore
        BooksellersBestAwardParser,
      )
    except ImportError:
      from parser.booksellers_best import BooksellersBestAwardParser
    return BooksellersBestAwardParser()

  def parse(self, html, fetch_url=None, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME, fetch_url=fetch_url)
