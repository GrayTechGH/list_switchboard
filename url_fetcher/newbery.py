#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE, UrlFetcherGeneric

try:
  from calibre_plugins.list_switchboard.parser.newbery import ALSC_URL
except ImportError:
  from parser.newbery import ALSC_URL


class UrlFetcherJohnNewberyMedal(UrlFetcherGeneric):

  source_id = 'john_newbery_medal'
  NAME = 'John Newbery Medal'
  URL = ALSC_URL
  order = 263
  options = {'match_series': False}
  FILTER_CATEGORIES = (CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,)

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.newbery import NewberyMedalParser # type: ignore
    except ImportError:
      from parser.newbery import NewberyMedalParser
    return NewberyMedalParser()

  def parse(self, html, fetch_url=None, log=None, progress=None, **kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      fetch_url=fetch_url,
      current_year=kwargs.get('current_year'),
      log=log,
      progress=progress)
