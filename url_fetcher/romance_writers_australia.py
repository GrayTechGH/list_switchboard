#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_ROMANCE,
  UrlFetcherGeneric,
)


class UrlFetcherRomanceWritersAustraliaRubyAwards(UrlFetcherGeneric):

  source_id = 'romance_writers_australia_ruby_awards'
  NAME = 'Romance Writers of Australia RUBY Awards'
  URL = (
    'https://romanceaustralia.com/search/suggest.json?q=RUBY'
    '&resources%5Btype%5D=article,page&resources%5Blimit%5D=50')
  ARTICLE_URL = 'https://romanceaustralia.com/search?q=RUBY&type=article%2Cpage'
  order = 252
  options = {'match_series': False}
  FILTER_CATEGORIES = (CATEGORY_ROMANCE, CATEGORY_REGIONAL_NATIONAL_AWARDS)

  @property
  def display_url(self):
    return self.ARTICLE_URL

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.romance_writers_australia import ( # type: ignore
        RomanceWritersAustraliaRubyParser,
      )
    except ImportError:
      from parser.romance_writers_australia import RomanceWritersAustraliaRubyParser
    return RomanceWritersAustraliaRubyParser()

  def parse(self, html, fetch_url=None, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME, fetch_url=fetch_url)
