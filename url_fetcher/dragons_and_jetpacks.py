#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""URL fetcher for the Dragons & Jetpacks Goodreads group-read shelf."""

from .generic import (
  CATEGORY_FANTASY,
  CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
  CATEGORY_SCIENCE_FICTION,
  UrlFetcherGeneric,
)


class UrlFetcherDragonsJetpacks(UrlFetcherGeneric):

  source_id = 'dragons_and_jetpacks'
  NAME = 'Dragons & Jetpacks'
  URL = (
    'https://www.goodreads.com/group/bookshelf/106876-dragons-jetpacks'
    '?per_page=100&shelf=group-read')
  order = 58
  FILTER_CATEGORIES = (
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    CATEGORY_SCIENCE_FICTION,
    CATEGORY_FANTASY,
  )
  options = {'match_series': False}

  def source_choices(self):
    return ({'label': 'Automatic', 'value': 'automatic'},)

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.dragons_and_jetpacks import ( # type: ignore
        DragonsJetpacksParser,
      )
    except ImportError:
      from parser.dragons_and_jetpacks import DragonsJetpacksParser
    return DragonsJetpacksParser()

  def parse(
      self, html, fetch_url=None, fetch_error=None, log=None, progress=None,
      **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      fetch_url=fetch_url,
      fetch_error=fetch_error,
      log=log,
      progress=progress)

