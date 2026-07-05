#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE, UrlFetcherGeneric

try:
  from calibre_plugins.list_switchboard.parser.yalsa_nonfiction import HISTORY_URL
except ImportError:
  from parser.yalsa_nonfiction import HISTORY_URL


class UrlFetcherYALSAExcellenceNonfictionYoungAdults(UrlFetcherGeneric):

  source_id = 'yalsa_excellence_nonfiction_young_adults'
  NAME = 'YALSA Award for Excellence in Nonfiction for Young Adults'
  URL = HISTORY_URL
  order = 261
  options = {'match_series': False}
  FILTER_CATEGORIES = (CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,)

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.yalsa_nonfiction import YALSANonfictionAwardParser # type: ignore
    except ImportError:
      from parser.yalsa_nonfiction import YALSANonfictionAwardParser
    return YALSANonfictionAwardParser()

  def parse(self, html, fetch_url=None, log=None, progress=None, **kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      fetch_url=fetch_url,
      current_year=kwargs.get('current_year'),
      log=log,
      progress=progress)
