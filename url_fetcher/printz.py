#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE, UrlFetcherGeneric

try:
  from calibre_plugins.list_switchboard.parser.printz import HISTORY_URL
except ImportError:
  from parser.printz import HISTORY_URL


class UrlFetcherMichaelLPrintzAward(UrlFetcherGeneric):

  source_id = 'michael_l_printz_award'
  NAME = 'Michael L. Printz Award'
  URL = HISTORY_URL
  order = 261
  options = {'match_series': False}
  FILTER_CATEGORIES = (CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,)

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.printz import PrintzAwardParser # type: ignore
    except ImportError:
      from parser.printz import PrintzAwardParser
    return PrintzAwardParser()

  def parse(self, html, fetch_url=None, log=None, progress=None, **kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      fetch_url=fetch_url,
      current_year=kwargs.get('current_year'),
      log=log,
      progress=progress)
