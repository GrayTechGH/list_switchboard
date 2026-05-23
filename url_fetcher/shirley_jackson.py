#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_HORROR_DARK_FICTION, UrlFetcherGeneric
from .isfdb_fallback import SFADBISFDYAwardFallbackMixin


SHIRLEY_JACKSON_AWARDS_URL = 'https://www.sfadb.com/Shirley_Jackson_Awards'
SHIRLEY_JACKSON_CATEGORIES = (CATEGORY_HORROR_DARK_FICTION,)


class UrlFetcherShirleyJackson(SFADBISFDYAwardFallbackMixin, UrlFetcherGeneric):

  URL = SHIRLEY_JACKSON_AWARDS_URL
  FETCH_URLS = (SHIRLEY_JACKSON_AWARDS_URL,)
  FILTER_CATEGORIES = SHIRLEY_JACKSON_CATEGORIES
  order = 150
  options = {
    'match_series': False,
  }
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  AWARD_NAME = 'Shirley Jackson Award'
  ISFDB_AWARD_ID = '58'

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.shirley_jackson import (
        ShirleyJacksonParser,
      )
    except ImportError:
      from parser.shirley_jackson import ShirleyJacksonParser

    return ShirleyJacksonParser()

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES,
      fetch_url=fetch_url,
      log=log,
      progress=progress)


class UrlFetcherShirleyJacksonNovel(UrlFetcherShirleyJackson):
  source_id = 'shirley_jackson_novel'
  NAME = 'Shirley Jackson - Novel'
  CATEGORY = 'Novel'
  CATEGORY_ALIASES = ('novel',)
  ISFDB_CATEGORY_ALIASES = ('Best Novel',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherShirleyJacksonNovella(UrlFetcherShirleyJackson):
  source_id = 'shirley_jackson_novella'
  NAME = 'Shirley Jackson - Novella'
  CATEGORY = 'Novella'
  CATEGORY_ALIASES = ('novella',)
  ISFDB_CATEGORY_ALIASES = ('Best Novella',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherShirleyJacksonSingleAuthorCollection(UrlFetcherShirleyJackson):
  source_id = 'shirley_jackson_single_author_collection'
  NAME = 'Shirley Jackson - Single-Author Collection'
  CATEGORY = 'Single-Author Collection'
  CATEGORY_ALIASES = ('single-author collection', 'single author collection', 'collection')
  ISFDB_CATEGORY_ALIASES = ('Best Collection',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherShirleyJacksonEditedAnthology(UrlFetcherShirleyJackson):
  source_id = 'shirley_jackson_edited_anthology'
  NAME = 'Shirley Jackson - Edited Anthology'
  CATEGORY = 'Edited Anthology'
  CATEGORY_ALIASES = ('edited anthology', 'anthology')
  ISFDB_CATEGORY_ALIASES = ('Best Anthology',)
  USE_ISFDB_FALLBACK = True
