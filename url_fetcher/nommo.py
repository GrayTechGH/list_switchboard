#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_FANTASY,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_SCIENCE_FICTION,
  UrlFetcherGeneric,
)


NOMMO_AWARDS_URL = 'https://en.wikipedia.org/wiki/Nommo_Awards'
NOMMO_WIKIMEDIA_HTML_URL = (
  'https://api.wikimedia.org/core/v1/wikipedia/en/page/Nommo_Awards/html'
)
NOMMO_CATEGORIES = (
  CATEGORY_SCIENCE_FICTION,
  CATEGORY_FANTASY,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
)


class UrlFetcherNommo(UrlFetcherGeneric):

  URL = NOMMO_AWARDS_URL
  FETCH_URLS = (NOMMO_AWARDS_URL,)
  FILTER_CATEGORIES = NOMMO_CATEGORIES
  order = 210
  options = {
    'match_series': False,
  }
  CATEGORY = ''

  def fallback_urls(self, url):
    if url == NOMMO_AWARDS_URL:
      return (NOMMO_WIKIMEDIA_HTML_URL,)
    return ()

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.nommo import NommoAwardsParser
    except ImportError:
      from parser.nommo import NommoAwardsParser

    return NommoAwardsParser()

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      self.CATEGORY,
      fetch_url=fetch_url,
      log=log,
      progress=progress)


class UrlFetcherNommoNovel(UrlFetcherNommo):
  source_id = 'nommo_novel'
  NAME = 'Nommo - Novel'
  CATEGORY = 'Novel'


class UrlFetcherNommoNovella(UrlFetcherNommo):
  source_id = 'nommo_novella'
  NAME = 'Nommo - Novella'
  CATEGORY = 'Novella'


class UrlFetcherNommoGraphicNovel(UrlFetcherNommo):
  source_id = 'nommo_graphic_novel'
  NAME = 'Nommo - Graphic Novel'
  CATEGORY = 'Graphic Novel'
