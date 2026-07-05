#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_ROMANCE,
  UrlFetcherGeneric,
)


class UrlFetcherAustralianRomanceReadersAwards(UrlFetcherGeneric):

  source_id = 'australian_romance_readers_awards'
  NAME = 'Australian Romance Readers Awards'
  URL = 'https://australianromancereaders.com.au/awards/'
  order = 253
  options = {'match_series': False}
  FILTER_CATEGORIES = (CATEGORY_ROMANCE, CATEGORY_REGIONAL_NATIONAL_AWARDS)

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.australian_romance_readers import ( # type: ignore
        AustralianRomanceReadersAwardsParser,
      )
    except ImportError:
      from parser.australian_romance_readers import AustralianRomanceReadersAwardsParser
    return AustralianRomanceReadersAwardsParser()

  def parse(self, html, fetch_url=None, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME, fetch_url=fetch_url)
