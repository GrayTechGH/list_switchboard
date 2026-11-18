#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_SCIENCE_FICTION,
  UrlFetcherGeneric,
)
from .isfdb_fallback import SFADBISFDYAwardFallbackMixin


SEIUN_AWARDS_URL = 'https://www.sfadb.com/Seiun_Awards'


class UrlFetcherSeiun(SFADBISFDYAwardFallbackMixin, UrlFetcherGeneric):

  FILTER_CATEGORIES = (CATEGORY_SCIENCE_FICTION, CATEGORY_REGIONAL_NATIONAL_AWARDS)
  URL = SEIUN_AWARDS_URL
  FETCH_URLS = (SEIUN_AWARDS_URL,)
  order = 200
  options = {
    'match_series': False,
  }
  AWARD_NAME = 'Seiun Award'
  ISFDB_AWARD_ID = '61'

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.seiun import SeiunParser
    except ImportError:
      from parser.seiun import SeiunParser

    return SeiunParser()

  def parse(self, html, fetch_url=None, log=None, progress=None, **kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      category=self.CATEGORY,
      category_aliases=self.CATEGORY_ALIASES,
      fetch_url=fetch_url,
      log=log,
      progress=progress, cached_parsed=kwargs.get('cached_parsed'),
      incremental_update=kwargs.get('incremental_update', False),
      enable_incremental=self.ENABLE_SFADB_INCREMENTAL)


class UrlFetcherSeiunTranslatedNovel(UrlFetcherSeiun):
  SUPPORTS_INCREMENTAL_UPDATE = True
  ENABLE_SFADB_INCREMENTAL = True

  source_id = 'seiun_translated_novel'
  NAME = 'Seiun - Translated Novel'
  CATEGORY = 'Translated Novel'
  CATEGORY_ALIASES = (
    'foreign novel',
    'translated novel',
    'translated long form',
    'translated long story',
    'foreign long form',
  )
  ISFDB_CATEGORY_ALIASES = ('Best Translated Long Story',)
  ISFDB_CATEGORY_ID = '635'
  ISFDB_SOURCE_LABEL = 'ISFDB (original works)'
  RESOLVE_ISFDB_ORIGINAL_WORKS = True
  USE_ISFDB_FALLBACK = True


class UrlFetcherSeiunJapaneseLongWork(UrlFetcherSeiun):
  SUPPORTS_INCREMENTAL_UPDATE = True
  ENABLE_ISFDB_INCREMENTAL = True

  source_id = 'seiun_japanese_long_work'
  NAME = 'Seiun - Japanese Long Work'
  # SFADB explicitly covers only Seiun's foreign novel and short-story awards.
  USE_SFADB_SOURCE = False
  URL = 'https://www.isfdb.org/cgi-bin/awardtype.cgi?61'
  FETCH_URLS = (URL,)
  CATEGORY = 'Japanese Long Work'
  CATEGORY_ALIASES = (
    'japanese novel',
    'japanese long work',
    'japanese long form',
    'japanese long story',
    'best japanese long work',
    'best japanese long story',
  )
  ISFDB_CATEGORY_ALIASES = ('Best Japanese Long Story',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherSeiunComic(UrlFetcherSeiun):

  source_id = 'seiun_comic'
  NAME = 'Seiun - Comic'
  USE_SFADB_SOURCE = False
  ISFDB_CATEGORY_ID = '1236'
  URL = 'https://www.isfdb.org/cgi-bin/award_category.cgi?1236+1'
  FETCH_URLS = (URL,)
  CATEGORY = 'Comic'
  CATEGORY_ALIASES = ('comic', 'comics')
  ISFDB_CATEGORY_ALIASES = ('Best Comics',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherSeiunNonfiction(UrlFetcherSeiun):

  source_id = 'seiun_nonfiction'
  NAME = 'Seiun - Nonfiction'
  # SFADB's two foreign-nonfiction records do not cover the full category.
  USE_SFADB_SOURCE = False
  ISFDB_CATEGORY_ID = '638'
  URL = 'https://www.isfdb.org/cgi-bin/award_category.cgi?638+1'
  FETCH_URLS = (URL,)
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_SCIENCE_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  CATEGORY = 'Nonfiction'
  CATEGORY_ALIASES = ('nonfiction', 'non fiction', 'non-fiction', 'foreign nonfiction')
  ISFDB_CATEGORY_ALIASES = ('Best Nonfiction',)
  USE_ISFDB_FALLBACK = True
