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


BSFA_AWARDS_URL = 'https://www.sfadb.com/British_SF_Association_Awards'
BSFA_SPECULATIVE_REGIONAL_CATEGORIES = (
  CATEGORY_SCIENCE_FICTION,
  CATEGORY_FANTASY,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
)


class UrlFetcherBSFA(SFADBISFDYAwardFallbackMixin, UrlFetcherGeneric):

  URL = BSFA_AWARDS_URL
  FETCH_URLS = (BSFA_AWARDS_URL,)
  FILTER_CATEGORIES = BSFA_SPECULATIVE_REGIONAL_CATEGORIES
  order = 110
  options = {
    'match_series': False,
  }
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  AWARD_NAME = 'British Science Fiction Award'
  ISFDB_AWARD_ID = '9'

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.bsfa import BSFAParser
    except ImportError:
      from parser.bsfa import BSFAParser

    return BSFAParser()

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


class UrlFetcherBSFANovel(UrlFetcherBSFA):
  source_id = 'bsfa_novel'
  NAME = 'BSFA - Novel'
  CATEGORY = 'Novel'
  CATEGORY_ALIASES = ('novel', 'novels')
  ISFDB_CATEGORY_ALIASES = ('Best Novel',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherBSFAShorterFiction(UrlFetcherBSFA):
  source_id = 'bsfa_shorter_fiction'
  NAME = 'BSFA - Shorter Fiction'
  CATEGORY = 'Shorter Fiction'
  CATEGORY_ALIASES = (
    'shorter fiction',
    'shorter fiction (novelette or novella)',
    'short fiction',
  )
  ISFDB_CATEGORY_ALIASES = ('Best Short Fiction', 'Best Shorter Fiction')
  USE_ISFDB_FALLBACK = True


class UrlFetcherBSFACollectionAnthology(UrlFetcherBSFA):
  source_id = 'bsfa_collection_anthology'
  NAME = 'BSFA - Collection/Anthology'
  CATEGORY = 'Collection/Anthology'
  CATEGORY_ALIASES = ('collection', 'collection or anthology', 'collection/anthology')
  ISFDB_CATEGORY_ALIASES = ('Best Collection',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherBSFAFictionForYoungerReaders(UrlFetcherBSFA):
  source_id = 'bsfa_fiction_for_younger_readers'
  NAME = 'BSFA - Fiction for Younger Readers'
  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  ) + BSFA_SPECULATIVE_REGIONAL_CATEGORIES
  CATEGORY = 'Fiction for Younger Readers'
  CATEGORY_ALIASES = ('fiction for younger readers', 'best fiction for younger readers')
  ISFDB_CATEGORY_ALIASES = ('Best Fiction for Younger Readers',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherBSFALongNonfiction(UrlFetcherBSFA):
  source_id = 'bsfa_long_nonfiction'
  NAME = 'BSFA - Long Non-Fiction'
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
  ) + BSFA_SPECULATIVE_REGIONAL_CATEGORIES
  CATEGORY = 'Long Non-Fiction'
  CATEGORY_ALIASES = ('long nonfiction', 'long non fiction', 'nonfiction long', 'non fiction long')
  ISFDB_CATEGORY_ALIASES = ('Best Long Non-Fiction', 'Best Non-Fiction')
  USE_ISFDB_FALLBACK = True
