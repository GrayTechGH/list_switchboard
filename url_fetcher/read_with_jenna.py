#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherGeneric,
)


class UrlFetcherReadWithJenna(UrlFetcherGeneric):

  source_id = 'read_with_jenna'
  NAME = 'Read With Jenna'
  URL = 'https://www.today.com/shop/read-jenna-book-club-list-today-s-jenna-bush-hager-t164652'
  order = 44
  FILTER_CATEGORIES = (CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,)
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.read_with_jenna import ReadWithJennaParser
    except ImportError:
      from parser.read_with_jenna import ReadWithJennaParser
    return ReadWithJennaParser()

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME)


class UrlFetcherReadWithJennaJr(UrlFetcherGeneric):

  source_id = 'read_with_jenna_jr'
  NAME = 'Read With Jenna Jr.'
  URL = 'https://www.today.com/shop/read-with-jenna'
  BOOTSTRAP_URL = (
    'https://www.today.com/popculture/books/'
    'read-with-jenna-junior-book-list-2026-rcna348963'
  )
  order = 45
  FILTER_CATEGORIES = (
    CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  )
  options = {'match_series': False}

  def fallback_urls(self, url):
    return (self.BOOTSTRAP_URL,) if url == self.URL else ()

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.read_with_jenna import ReadWithJennaJuniorParser
    except ImportError:
      from parser.read_with_jenna import ReadWithJennaJuniorParser
    return ReadWithJennaJuniorParser()

  def source_label_for_url(self, url, index):
    if url == self.URL:
      return 'TODAY Jenna hub'
    if url == self.BOOTSTRAP_URL:
      return 'TODAY 2026 Jr. archive bootstrap'
    return super().source_label_for_url(url, index)

  def parse(self, html, **kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      fetch_url=kwargs.get('fetch_url'),
      bootstrap_url=self.BOOTSTRAP_URL,
    )
