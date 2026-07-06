#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS, UrlFetcherGeneric


class UrlFetcherLibraryReads(UrlFetcherGeneric):

  source_id = 'library_reads'
  NAME = 'LibraryReads'
  URL = 'https://libraryreads.org/archive'
  order = 46
  FILTER_CATEGORIES = (CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,)
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.library_reads import LibraryReadsParser
    except ImportError:
      from parser.library_reads import LibraryReadsParser
    return LibraryReadsParser()

  def parse(self, html, fetch_url=None, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME, fetch_url=fetch_url)
