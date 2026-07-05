#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE, UrlFetcherGeneric

try:
  from calibre_plugins.list_switchboard.parser.carnegie_medal import WINNERS_URL
except ImportError:
  from parser.carnegie_medal import WINNERS_URL


class UrlFetcherCarnegieMedalForWriting(UrlFetcherGeneric):

  source_id = 'carnegie_medal_for_writing'
  NAME = 'Carnegie Medal for Writing'
  URL = WINNERS_URL
  order = 262
  options = {'match_series': False}
  FILTER_CATEGORIES = (CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,)

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.carnegie_medal import CarnegieMedalParser # type: ignore
    except ImportError:
      from parser.carnegie_medal import CarnegieMedalParser
    return CarnegieMedalParser()

  def parse(self, html, fetch_url=None, log=None, progress=None, **kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      fetch_url=fetch_url,
      current_year=kwargs.get('current_year'),
      log=log,
      progress=progress)
