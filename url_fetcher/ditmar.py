#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_FANTASY,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_SCIENCE_FICTION,
  UrlFetcherGeneric,
)
from .isfdb_fallback import SFADBISFDYAwardFallbackMixin


DITMAR_AWARDS_URL = 'https://www.sfadb.com/Ditmar_Awards'
SPECULATIVE_REGIONAL_CATEGORIES = (
  CATEGORY_SCIENCE_FICTION,
  CATEGORY_FANTASY,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
)


class UrlFetcherDitmar(SFADBISFDYAwardFallbackMixin, UrlFetcherGeneric):

  FILTER_CATEGORIES = SPECULATIVE_REGIONAL_CATEGORIES
  URL = DITMAR_AWARDS_URL
  FETCH_URLS = (DITMAR_AWARDS_URL,)
  order = 205
  options = {
    'match_series': False,
  }
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  AWARD_NAME = 'Ditmar Award'
  ISFDB_AWARD_ID = '16'

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.ditmar import DitmarParser
    except ImportError:
      from parser.ditmar import DitmarParser

    return DitmarParser()

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      category=self.CATEGORY,
      category_aliases=self.CATEGORY_ALIASES,
      fetch_url=fetch_url,
      log=log,
      progress=progress)


class UrlFetcherDitmarNovel(UrlFetcherDitmar):

  source_id = 'ditmar_novel'
  NAME = 'Ditmar - Novel'
  CATEGORY = 'Novel'
  CATEGORY_ALIASES = (
    'novel',
    'best novel',
    'australian novel',
    'australian sf novel',
    'australian sf or fantasy novel',
    'australian long fiction',
    'australian long sf or fantasy',
    'long fiction',
  )
  ISFDB_CATEGORY_ALIASES = (
    'Best Novel',
    'Best Australian Novel',
    'Best Australian Long Fiction',
    'Australian Science Fiction, Best Novel',
  )
  USE_ISFDB_FALLBACK = True


class UrlFetcherDitmarNovellaNovelette(UrlFetcherDitmar):

  source_id = 'ditmar_novella_novelette'
  NAME = 'Ditmar - Novella/Novelette'
  CATEGORY = 'Novella Or Novelette'
  CATEGORY_ALIASES = (
    'novella or novelette',
    'novella',
    'novelette',
  )
  ISFDB_CATEGORY_ALIASES = ('Best Novella or Novelette',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherDitmarCollectedWork(UrlFetcherDitmar):

  source_id = 'ditmar_collected_work'
  NAME = 'Ditmar - Collected Work'
  CATEGORY = 'Collected Work'
  CATEGORY_ALIASES = (
    'collected work',
    'australian collected work',
    'collection',
    'anthology',
  )
  ISFDB_CATEGORY_ALIASES = ('Best Collected Work', 'Best Australian Collected Work')
  USE_ISFDB_FALLBACK = True
