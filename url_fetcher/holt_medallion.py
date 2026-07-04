#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_ROMANCE,
  UrlFetcherGeneric,
)


class UrlFetcherHOLTMedallion(UrlFetcherGeneric):

  source_id = 'holt_medallion'
  NAME = 'HOLT Medallion'
  URL = 'https://virginiaromancewriters.com/holt-medallion/'
  order = 254
  options = {'match_series': False}
  FILTER_CATEGORIES = (CATEGORY_ROMANCE, CATEGORY_REGIONAL_NATIONAL_AWARDS)

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.holt_medallion import ( # type: ignore
        HOLTMedallionParser,
      )
    except ImportError:
      from parser.holt_medallion import HOLTMedallionParser
    return HOLTMedallionParser()

  def parse(self, html, fetch_url=None, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME, fetch_url=fetch_url)
