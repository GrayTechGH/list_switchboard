#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS, UrlFetcherGeneric


class UrlFetcherCanadaReads(UrlFetcherGeneric):

  source_id = 'canada_reads'
  NAME = 'Canada Reads'
  URL = 'https://www.cbc.ca/books/canadareads'
  order = 45
  FILTER_CATEGORIES = (CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,)
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.canada_reads import CanadaReadsParser
    except ImportError:
      from parser.canada_reads import CanadaReadsParser
    return CanadaReadsParser()

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME)
