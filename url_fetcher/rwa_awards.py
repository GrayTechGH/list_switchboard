#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_ROMANCE,
  UrlFetcherGeneric,
)


class UrlFetcherRWARITAAwards(UrlFetcherGeneric):

  source_id = 'rwa_rita_awards'
  NAME = 'RWA RITA Awards'
  URL = 'https://en.wikipedia.org/wiki/RITA_Award'
  order = 247
  options = {'match_series': False}
  FILTER_CATEGORIES = (CATEGORY_ROMANCE, CATEGORY_REGIONAL_NATIONAL_AWARDS)

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.rwa_awards import ( # type: ignore
        RWARITAAwardsParser,
      )
    except ImportError:
      from parser.rwa_awards import RWARITAAwardsParser
    return RWARITAAwardsParser()

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME)


class UrlFetcherRWAVivianAwards(UrlFetcherRWARITAAwards):

  source_id = 'rwa_vivian_awards'
  NAME = 'RWA Vivian Awards'
  order = 248

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.rwa_awards import ( # type: ignore
        RWAVivianAwardsParser,
      )
    except ImportError:
      from parser.rwa_awards import RWAVivianAwardsParser
    return RWAVivianAwardsParser()
