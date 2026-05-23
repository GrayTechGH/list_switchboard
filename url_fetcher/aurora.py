#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_FANTASY,
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_SCIENCE_FICTION,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherGeneric,
)
from .isfdb_fallback import SFADBISFDYAwardFallbackMixin


AURORA_AWARDS_URL = 'https://www.sfadb.com/Aurora_Awards'
SPECULATIVE_REGIONAL_CATEGORIES = (
  CATEGORY_SCIENCE_FICTION,
  CATEGORY_FANTASY,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
)


class UrlFetcherAurora(SFADBISFDYAwardFallbackMixin, UrlFetcherGeneric):

  URL = AURORA_AWARDS_URL
  FETCH_URLS = (AURORA_AWARDS_URL,)
  order = 180
  options = {
    'match_series': False,
  }
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  BOOKS_ONLY = False
  AWARD_NAME = 'Prix Aurora Awards'
  ISFDB_AWARD_ID = '5'

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.aurora import AuroraParser
    except ImportError:
      from parser.aurora import AuroraParser

    return AuroraParser(books_only=self.BOOKS_ONLY)

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


class UrlFetcherAuroraNovel(UrlFetcherAurora):
  source_id = 'aurora_novel'
  NAME = 'Aurora - Novel'
  FILTER_CATEGORIES = SPECULATIVE_REGIONAL_CATEGORIES
  CATEGORY = 'Novel'
  CATEGORY_ALIASES = ('novel',)
  ISFDB_CATEGORY_ALIASES = ('Best Novel - English',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherAuroraYANovel(UrlFetcherAurora):
  source_id = 'aurora_ya_novel'
  NAME = 'Aurora - YA Novel'
  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  ) + SPECULATIVE_REGIONAL_CATEGORIES
  CATEGORY = 'YA Novel'
  CATEGORY_ALIASES = ('ya novel', 'young adult novel')
  ISFDB_CATEGORY_ALIASES = ('Best YA Novel - English',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherAuroraNoveletteNovella(UrlFetcherAurora):
  source_id = 'aurora_novelette_novella'
  NAME = 'Aurora - Novelette/Novella'
  FILTER_CATEGORIES = SPECULATIVE_REGIONAL_CATEGORIES
  CATEGORY = 'Novelette/Novella'
  CATEGORY_ALIASES = ('novelette/novella', 'novella', 'novelette')
  ISFDB_CATEGORY_ALIASES = ('Best Novelette/Novella',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherAuroraRelatedWork(UrlFetcherAurora):
  source_id = 'aurora_related_work'
  NAME = 'Aurora - Related Work'
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
  ) + SPECULATIVE_REGIONAL_CATEGORIES
  CATEGORY = 'Related Work'
  CATEGORY_ALIASES = ('related work',)
  BOOKS_ONLY = True


class UrlFetcherAuroraGraphicNovel(UrlFetcherAurora):
  source_id = 'aurora_graphic_novel'
  NAME = 'Aurora - Graphic Novel'
  FILTER_CATEGORIES = SPECULATIVE_REGIONAL_CATEGORIES
  CATEGORY = 'Graphic Novel'
  CATEGORY_ALIASES = ('graphic novel',)
  ISFDB_CATEGORY_ALIASES = ('Best Graphic Novel - English',)
  USE_ISFDB_FALLBACK = True
