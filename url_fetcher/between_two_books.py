#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""URL fetchers for the two official Between Two Books page sections."""

from .generic import (
  CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
  UrlFetcherError,
  UrlFetcherGeneric,
)


class PackagedBetweenTwoBooksFallbackMixin:

  def fetch_and_parse(self, *args, **kwargs):
    try:
      return super().fetch_and_parse(*args, **kwargs)
    except UrlFetcherError as err:
      return self.parser().parse_ledger(str(err))

  def source_choices(self):
    return ({'label': 'Automatic', 'value': 'automatic'},)


class UrlFetcherBetweenTwoBooksNumbered(
    PackagedBetweenTwoBooksFallbackMixin, UrlFetcherGeneric):

  source_id = 'between_two_books_numbered_archive'
  NAME = 'Between Two Books - Official Book List'
  URL = 'https://betweentwobooks.co.uk/'
  order = 61
  FILTER_CATEGORIES = (CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,)
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.between_two_books import (  # type: ignore
        BetweenTwoBooksNumberedParser,
      )
    except ImportError:
      from parser.between_two_books import BetweenTwoBooksNumberedParser
    return BetweenTwoBooksNumberedParser()

  def parse(self, payload, **_kwargs):
    return self.parser().parse(payload)


class UrlFetcherBetweenTwoBooksIsolation(
    PackagedBetweenTwoBooksFallbackMixin, UrlFetcherGeneric):

  source_id = 'between_two_books_isolation_reading_lists'
  NAME = 'Between Two Books - Isolation & Themed Lists'
  URL = 'https://betweentwobooks.co.uk/'
  order = 62
  FILTER_CATEGORIES = (CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,)
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.between_two_books import (  # type: ignore
        BetweenTwoBooksIsolationParser,
      )
    except ImportError:
      from parser.between_two_books import BetweenTwoBooksIsolationParser
    return BetweenTwoBooksIsolationParser()

  def parse(self, payload, **_kwargs):
    return self.parser().parse(payload)
