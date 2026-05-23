#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_FANTASY,
  UrlFetcherGeneric,
)
from .isfdb_fallback import SFADBISFDYAwardFallbackMixin


WORLD_FANTASY_AWARDS_URL = 'https://www.sfadb.com/World_Fantasy_Awards'
WORLD_FANTASY_CATEGORIES = (CATEGORY_FANTASY,)


class UrlFetcherWorldFantasy(SFADBISFDYAwardFallbackMixin, UrlFetcherGeneric):

  URL = WORLD_FANTASY_AWARDS_URL
  FETCH_URLS = (WORLD_FANTASY_AWARDS_URL,)
  FILTER_CATEGORIES = WORLD_FANTASY_CATEGORIES
  order = 90
  options = {
    'match_series': False,
  }
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  AWARD_NAME = 'World Fantasy Award'
  ISFDB_AWARD_ID = '44'

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.world_fantasy import WorldFantasyParser
    except ImportError:
      from parser.world_fantasy import WorldFantasyParser

    return WorldFantasyParser()

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


class UrlFetcherWorldFantasyNovel(UrlFetcherWorldFantasy):
  source_id = 'world_fantasy_novel'
  NAME = 'World Fantasy - Novel'
  CATEGORY = 'Novel'
  CATEGORY_ALIASES = ('novel', 'novels')
  ISFDB_CATEGORY_ALIASES = ('Best Novel',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherWorldFantasyNovella(UrlFetcherWorldFantasy):
  source_id = 'world_fantasy_novella'
  NAME = 'World Fantasy - Novella'
  CATEGORY = 'Novella'
  CATEGORY_ALIASES = ('novella', 'long fiction')
  ISFDB_CATEGORY_ALIASES = ('Best Novella', 'Best Long Fiction')
  USE_ISFDB_FALLBACK = True


class UrlFetcherWorldFantasyAnthology(UrlFetcherWorldFantasy):
  source_id = 'world_fantasy_anthology'
  NAME = 'World Fantasy - Anthology'
  CATEGORY = 'Anthology'
  CATEGORY_ALIASES = ('anthology',)
  ISFDB_CATEGORY_ALIASES = ('Best Anthology',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherWorldFantasyCollection(UrlFetcherWorldFantasy):
  source_id = 'world_fantasy_collection'
  NAME = 'World Fantasy - Collection'
  CATEGORY = 'Collection'
  CATEGORY_ALIASES = ('collection',)
  ISFDB_CATEGORY_ALIASES = ('Best Collection',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherWorldFantasyCollectionAnthology(UrlFetcherWorldFantasy):
  source_id = 'world_fantasy_collection_anthology'
  NAME = 'World Fantasy - Collection/Anthology'
  CATEGORY = 'Collection/Anthology'
  CATEGORY_ALIASES = ('collection/anthology',)
  ISFDB_CATEGORY_ALIASES = ('Best Anthology/Collection (old)',)
  USE_ISFDB_FALLBACK = True
