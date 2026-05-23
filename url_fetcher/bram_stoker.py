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


class UrlFetcherBramStokerNovel(UrlFetcherBramStoker):
  source_id = 'bram_stoker_novel'
  NAME = 'Bram Stoker - Novel'
  CATEGORY = 'Novel'
  CATEGORY_ALIASES = ('novel',)
  ISFDB_CATEGORY_ALIASES = ('Superior Achievement in a Novel',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherBramStokerFirstNovel(UrlFetcherBramStoker):
  source_id = 'bram_stoker_first_novel'
  NAME = 'Bram Stoker - First Novel'
  CATEGORY = 'First Novel'
  CATEGORY_ALIASES = ('first novel',)
  ISFDB_CATEGORY_ALIASES = ('Superior Achievement in a First Novel',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherBramStokerYoungAdultNovel(UrlFetcherBramStoker):
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
  source_id = 'bram_stoker_long_fiction'
  NAME = 'Bram Stoker - Long Fiction'
  CATEGORY = 'Long Fiction'
  CATEGORY_ALIASES = ('long fiction',)
  ISFDB_CATEGORY_ALIASES = ('Superior Achievement in Long Fiction',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherBramStokerFictionCollection(UrlFetcherBramStoker):
  source_id = 'bram_stoker_fiction_collection'
  NAME = 'Bram Stoker - Fiction Collection'
  CATEGORY = 'Fiction Collection'
  CATEGORY_ALIASES = ('fiction collection', 'collection')


class UrlFetcherBramStokerAnthology(UrlFetcherBramStoker):
  source_id = 'bram_stoker_anthology'
  NAME = 'Bram Stoker - Anthology'
  CATEGORY = 'Anthology'
  CATEGORY_ALIASES = ('anthology',)
  ISFDB_CATEGORY_ALIASES = ('Superior Achievement in an Anthology',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherBramStokerPoetryCollection(UrlFetcherBramStoker):
  source_id = 'bram_stoker_poetry_collection'
  NAME = 'Bram Stoker - Poetry Collection'
  CATEGORY = 'Poetry Collection'
  CATEGORY_ALIASES = ('poetry collection',)
  ISFDB_CATEGORY_ALIASES = ('Superior Achievement in a Poetry Collection',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherBramStokerGraphicNovel(UrlFetcherBramStoker):
  source_id = 'bram_stoker_graphic_novel'
  NAME = 'Bram Stoker - Graphic Novel'
  CATEGORY = 'Graphic Novel'
  CATEGORY_ALIASES = ('graphic novel',)
  ISFDB_CATEGORY_ALIASES = (
    'Superior Achievement in a Graphic Novel',
    'Superior Achievement in a Comic Book, Graphic Novel or Other Illustrated Narrative',
  )
  USE_ISFDB_FALLBACK = True


class UrlFetcherBramStokerNonfiction(UrlFetcherBramStoker):
  source_id = 'bram_stoker_nonfiction'
  NAME = 'Bram Stoker - Nonfiction'
  FILTER_CATEGORIES = (CATEGORY_HORROR_DARK_FICTION, CATEGORY_NONFICTION)
  CATEGORY = 'Nonfiction'
  CATEGORY_ALIASES = ('nonfiction', 'non fiction', 'non-fiction')
  ISFDB_CATEGORY_ALIASES = ('Superior Achievement in Non-Fiction',)
  USE_ISFDB_FALLBACK = True
