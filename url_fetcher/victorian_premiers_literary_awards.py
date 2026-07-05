#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherGeneric,
)


OFFICIAL_URL = (
  'https://www.wheelercentre.com/'
  'victorian-premier-s-literary-awards/past-awards')


class UrlFetcherVictorianPremiersLiteraryAwards(UrlFetcherGeneric):

  URL = OFFICIAL_URL
  FETCH_URLS = ()
  order = 241
  options = {'match_series': False}
  AWARD_NAME = "Victorian Premier's Literary Awards"
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.victorian_premiers_literary_awards import (
        VictorianPremiersLiteraryAwardsOfficialParser,
      )
    except ImportError:
      from parser.victorian_premiers_literary_awards import (
        VictorianPremiersLiteraryAwardsOfficialParser,
      )
    return VictorianPremiersLiteraryAwardsOfficialParser(
      self.CATEGORY, self.CATEGORY_ALIASES)

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.create_parser().parse(
      html, self.URL, self.NAME, fetch_url=fetch_url, log=log, progress=progress)


class UrlFetcherVictorianPremiersLiteraryAwardsFiction(
    UrlFetcherVictorianPremiersLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'victorian_premiers_literary_awards_fiction'
  NAME = "Victorian Premier's Literary Awards - Fiction"
  CATEGORY = 'Fiction'
  CATEGORY_ALIASES = ('Prize for Fiction', 'Fiction')


class UrlFetcherVictorianPremiersLiteraryAwardsNonfiction(
    UrlFetcherVictorianPremiersLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'victorian_premiers_literary_awards_nonfiction'
  NAME = "Victorian Premier's Literary Awards - Non-fiction"
  CATEGORY = 'Non-fiction'
  CATEGORY_ALIASES = (
    'Prize for Non-fiction',
    'Prize for Nonfiction',
    'Non-fiction',
    'Nonfiction',
  )


class UrlFetcherVictorianPremiersLiteraryAwardsWritingForYoungAdults(
    UrlFetcherVictorianPremiersLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'victorian_premiers_literary_awards_writing_for_young_adults'
  NAME = "Victorian Premier's Literary Awards - Writing for Young Adults"
  CATEGORY = 'Writing for Young Adults'
  CATEGORY_ALIASES = (
    'Prize for Writing for Young Adults',
    'John Marsden Prize for Writing for Young Adults',
    'Writing for Young Adults',
  )


class UrlFetcherVictorianPremiersLiteraryAwardsChildrensLiterature(
    UrlFetcherVictorianPremiersLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'victorian_premiers_literary_awards_childrens_literature'
  NAME = "Victorian Premier's Literary Awards - Children's Literature"
  CATEGORY = "Children's Literature"
  CATEGORY_ALIASES = (
    "Prize for Children's Literature",
    "Children's Literature",
  )


class UrlFetcherVictorianPremiersLiteraryAwardsIndigenousWriting(
    UrlFetcherVictorianPremiersLiteraryAwards):

  FILTER_CATEGORIES = (CATEGORY_REGIONAL_NATIONAL_AWARDS,)
  source_id = 'victorian_premiers_literary_awards_indigenous_writing'
  NAME = "Victorian Premier's Literary Awards - Indigenous Writing"
  CATEGORY = 'Indigenous Writing'
  CATEGORY_ALIASES = (
    'Prize for Indigenous Writing',
    'Indigenous Writing',
  )
