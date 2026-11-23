#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_HORROR_DARK_FICTION,
  CATEGORY_NONFICTION,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherGeneric,
)
from .isfdb_fallback import SFADBISFDYAwardFallbackMixin


BRAM_STOKER_AWARDS_URL = 'https://www.sfadb.com/Bram_Stoker_Awards'


class UrlFetcherBramStoker(SFADBISFDYAwardFallbackMixin, UrlFetcherGeneric):

  ENABLE_SFADB_INCREMENTAL = True
  URL = BRAM_STOKER_AWARDS_URL
  FETCH_URLS = (BRAM_STOKER_AWARDS_URL,)
  FILTER_CATEGORIES = (CATEGORY_HORROR_DARK_FICTION,)
  order = 140
  options = {
    'match_series': False,
  }
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  AWARD_NAME = 'Bram Stoker Award'
  ISFDB_AWARD_ID = '40'

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.bram_stoker import BramStokerParser
    except ImportError:
      from parser.bram_stoker import BramStokerParser

    return BramStokerParser()

  def create_isfdb_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.bram_stoker import (
        BramStokerISFDBParser,
      )
    except ImportError:
      from parser.bram_stoker import BramStokerISFDBParser

    return BramStokerISFDBParser()

  def parse(self, html, fetch_url=None, log=None, progress=None, **kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES,
      fetch_url=fetch_url,
      log=log,
      progress=progress, cached_parsed=kwargs.get('cached_parsed'),
      incremental_update=kwargs.get('incremental_update', False), enable_incremental=True)


class UrlFetcherBramStokerNovel(UrlFetcherBramStoker):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'bram_stoker_novel'
  NAME = 'Bram Stoker - Novel'
  CATEGORY = 'Novel'
  CATEGORY_ALIASES = ('novel',)
  ISFDB_CATEGORY_ALIASES = ('Superior Achievement in a Novel',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherBramStokerFirstNovel(UrlFetcherBramStoker):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'bram_stoker_first_novel'
  NAME = 'Bram Stoker - First Novel'
  CATEGORY = 'First Novel'
  CATEGORY_ALIASES = ('first novel',)
  ISFDB_CATEGORY_ALIASES = ('Superior Achievement in a First Novel',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherBramStokerYoungAdultNovel(UrlFetcherBramStoker):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'bram_stoker_young_adult_novel'
  NAME = 'Bram Stoker - Young Adult Novel'
  FILTER_CATEGORIES = (
    CATEGORY_HORROR_DARK_FICTION,
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  )
  CATEGORY = 'Young Adult Novel'
  CATEGORY_ALIASES = ('young adult novel', 'young adult')
  ISFDB_CATEGORY_ALIASES = ('Superior Achievement in a Young Adult Novel',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherBramStokerMiddleGradeNovel(UrlFetcherBramStoker):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'bram_stoker_middle_grade_novel'
  NAME = 'Bram Stoker - Middle Grade Novel'
  FILTER_CATEGORIES = (
    CATEGORY_HORROR_DARK_FICTION,
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  )
  CATEGORY = 'Middle Grade Novel'
  CATEGORY_ALIASES = ('middle grade novel', 'middle grade')
  ISFDB_CATEGORY_ALIASES = ('Superior Achievement in a Middle Grade Novel',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherBramStokerLongFiction(UrlFetcherBramStoker):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'bram_stoker_long_fiction'
  NAME = 'Bram Stoker - Long Fiction'
  CATEGORY = 'Long Fiction'
  CATEGORY_ALIASES = ('long fiction',)
  ISFDB_CATEGORY_ALIASES = ('Superior Achievement in Long Fiction',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherBramStokerFictionCollection(UrlFetcherBramStoker):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'bram_stoker_fiction_collection'
  NAME = 'Bram Stoker - Fiction Collection'
  CATEGORY = 'Fiction Collection'
  CATEGORY_ALIASES = ('fiction collection', 'collection')


class UrlFetcherBramStokerAnthology(UrlFetcherBramStoker):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'bram_stoker_anthology'
  NAME = 'Bram Stoker - Anthology'
  CATEGORY = 'Anthology'
  CATEGORY_ALIASES = ('anthology',)
  ISFDB_CATEGORY_ALIASES = ('Superior Achievement in an Anthology',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherBramStokerPoetryCollection(UrlFetcherBramStoker):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'bram_stoker_poetry_collection'
  NAME = 'Bram Stoker - Poetry Collection'
  CATEGORY = 'Poetry Collection'
  CATEGORY_ALIASES = ('poetry collection', 'poetry')
  ISFDB_CATEGORY_ALIASES = ('Superior Achievement in a Poetry Collection',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherBramStokerGraphicNovel(UrlFetcherBramStoker):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'bram_stoker_graphic_novel'
  NAME = 'Bram Stoker - Graphic Novel'
  CATEGORY = 'Graphic Novel'
  CATEGORY_ALIASES = (
    'graphic novel',
    'illustrated narrative',
    'comic book, graphic novel, or other illustrated narrative',
  )


class UrlFetcherBramStokerNonfiction(UrlFetcherBramStoker):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'bram_stoker_nonfiction'
  NAME = 'Bram Stoker - Nonfiction'
  FILTER_CATEGORIES = (CATEGORY_HORROR_DARK_FICTION, CATEGORY_NONFICTION)
  CATEGORY = 'Nonfiction'
  CATEGORY_ALIASES = (
    'nonfiction',
    'non fiction',
    'non-fiction',
    'nonfiction book',
    'long nonfiction',
    'long non-fiction',
    'long non fiction',
  )
  ISFDB_CATEGORY_ALIASES = ('Superior Achievement in Non-Fiction',)
  USE_ISFDB_FALLBACK = True
