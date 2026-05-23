#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_FANTASY,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherGeneric,
)
from .isfdb_fallback import SFADBISFDYAwardFallbackMixin


MYTHOPOEIC_AWARDS_URL = 'https://www.sfadb.com/Mythopoeic_Awards'
YOUNG_READER_FANTASY_CATEGORIES = (
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  CATEGORY_FANTASY,
)


class UrlFetcherMythopoeic(SFADBISFDYAwardFallbackMixin, UrlFetcherGeneric):

  URL = MYTHOPOEIC_AWARDS_URL
  FETCH_URLS = (MYTHOPOEIC_AWARDS_URL,)
  order = 130
  options = {
    'match_series': False,
  }
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  AWARD_NAME = 'Mythopoeic Award'
  ISFDB_AWARD_ID = '30'

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.mythopoeic import MythopoeicParser
    except ImportError:
      from parser.mythopoeic import MythopoeicParser

    return MythopoeicParser()

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


class UrlFetcherMythopoeicFantasy(UrlFetcherMythopoeic):
  source_id = 'mythopoeic_fantasy'
  NAME = 'Mythopoeic - Fantasy'
  FILTER_CATEGORIES = YOUNG_READER_FANTASY_CATEGORIES
  CATEGORY = 'Fantasy'
  CATEGORY_ALIASES = ('fantasy',)


class UrlFetcherMythopoeicAdultLiterature(UrlFetcherMythopoeic):
  source_id = 'mythopoeic_adult_literature'
  NAME = 'Mythopoeic - Adult Literature'
  FILTER_CATEGORIES = (CATEGORY_FANTASY,)
  CATEGORY = 'Adult Literature'
  CATEGORY_ALIASES = ('adult literature',)


class UrlFetcherMythopoeicYoungAdultLiterature(UrlFetcherMythopoeic):
  source_id = 'mythopoeic_young_adult_literature'
  NAME = 'Mythopoeic - Young Adult Literature'
  FILTER_CATEGORIES = YOUNG_READER_FANTASY_CATEGORIES
  CATEGORY = 'Young Adult Literature'
  CATEGORY_ALIASES = ('young adult literature', 'ya literature')


class UrlFetcherMythopoeicChildrensLiterature(UrlFetcherMythopoeic):
  source_id = 'mythopoeic_childrens_literature'
  NAME = "Mythopoeic - Children's Literature"
  FILTER_CATEGORIES = YOUNG_READER_FANTASY_CATEGORIES
  CATEGORY = "Children's Literature"
  CATEGORY_ALIASES = ("children's literature", 'childrens literature', 'children literature')
