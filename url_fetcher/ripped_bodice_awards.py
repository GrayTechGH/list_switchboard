#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_ROMANCE,
  UrlFetcherGeneric,
)


class UrlFetcherRippedBodiceAwards(UrlFetcherGeneric):

  source_id = 'ripped_bodice_awards'
  NAME = 'Ripped Bodice Awards for Excellence in Romance Fiction'
  URL = (
    'https://en.wikipedia.org/w/api.php?action=parse&page=The_Ripped_Bodice'
    '&prop=wikitext&format=json&formatversion=2')
  ARTICLE_URL = 'https://en.wikipedia.org/wiki/The_Ripped_Bodice'
  order = 249
  options = {'match_series': False}
  FILTER_CATEGORIES = (CATEGORY_ROMANCE, CATEGORY_REGIONAL_NATIONAL_AWARDS)

  @property
  def display_url(self):
    return self.ARTICLE_URL

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.ripped_bodice_awards import ( # type: ignore
        RippedBodiceAwardsParser,
      )
    except ImportError:
      from parser.ripped_bodice_awards import RippedBodiceAwardsParser
    return RippedBodiceAwardsParser()

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.ARTICLE_URL, self.NAME)
