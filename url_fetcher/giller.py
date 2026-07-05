#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  UrlFetcherGeneric,
)


class UrlFetcherGillerPrize(UrlFetcherGeneric):

  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'giller_prize'
  NAME = 'Giller Prize'
  URL = 'https://en.wikipedia.org/wiki/Giller_Prize'
  order = 238
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.giller import GillerWikipediaParser
    except ImportError:
      from parser.giller import GillerWikipediaParser
    return GillerWikipediaParser()

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME)
