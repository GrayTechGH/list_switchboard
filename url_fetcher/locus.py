#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_FANTASY,
  CATEGORY_HORROR_DARK_FICTION,
  CATEGORY_NONFICTION,
  CATEGORY_SCIENCE_FICTION,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherGeneric,
)
from .isfdb_fallback import SFADBISFDYAwardFallbackMixin


LOCUS_AWARDS_URL = 'https://www.sfadb.com/Locus_Awards'
SPECULATIVE_CATEGORIES = (
  CATEGORY_SCIENCE_FICTION,
  CATEGORY_FANTASY,
)
FANTASY_HORROR_CATEGORIES = (
  CATEGORY_FANTASY,
  CATEGORY_HORROR_DARK_FICTION,
)


class UrlFetcherLocusAnnual(SFADBISFDYAwardFallbackMixin, UrlFetcherGeneric):

  URL = LOCUS_AWARDS_URL
  FETCH_URLS = (LOCUS_AWARDS_URL,)
  FILTER_CATEGORIES = SPECULATIVE_CATEGORIES
  order = 70
  options = {
    'match_series': False,
  }
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  AWARD_NAME = 'Locus Poll Award'
  ISFDB_AWARD_ID = '28'

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.locus import LocusAnnualAwardsParser
    except ImportError:
      from parser.locus import LocusAnnualAwardsParser

    return LocusAnnualAwardsParser()

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


class UrlFetcherLocusAllTime(UrlFetcherGeneric):

  FILTER_CATEGORIES = SPECULATIVE_CATEGORIES
  order = 80
  options = {
    'match_series': False,
  }
  POLL_YEAR = ''
  CATEGORY = ''

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.locus import LocusAllTimeAwardsParser
    except ImportError:
      from parser.locus import LocusAllTimeAwardsParser

    return LocusAllTimeAwardsParser()

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      self.POLL_YEAR,
      self.CATEGORY,
      log=log,
      progress=progress)


class UrlFetcherLocusAnnualSFNovel(UrlFetcherLocusAnnual):
  source_id = 'locus_annual_sf_novel'
  NAME = 'Locus - Annual SF Novel'
  FILTER_CATEGORIES = (CATEGORY_SCIENCE_FICTION,)
  CATEGORY = 'SF Novel'
  CATEGORY_ALIASES = ('novel', 'sf novel')
  ISFDB_CATEGORY_ALIASES = ('Best SF Novel',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherLocusAnnualFantasyNovel(UrlFetcherLocusAnnual):
  source_id = 'locus_annual_fantasy_novel'
  NAME = 'Locus - Annual Fantasy Novel'
  FILTER_CATEGORIES = (CATEGORY_FANTASY,)
  CATEGORY = 'Fantasy Novel'
  CATEGORY_ALIASES = ('fantasy novel',)
  ISFDB_CATEGORY_ALIASES = ('Best Fantasy Novel',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherLocusAnnualHorrorNovel(UrlFetcherLocusAnnual):
  source_id = 'locus_annual_horror_novel'
  NAME = 'Locus - Annual Horror Novel'
  FILTER_CATEGORIES = (CATEGORY_HORROR_DARK_FICTION,)
  CATEGORY = 'Horror Novel'
  CATEGORY_ALIASES = ('horror novel', 'horror/dark fantasy novel', 'dark fantasy horror novel')
  ISFDB_CATEGORY_ALIASES = ('Best Horror Novel',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherLocusAnnualYoungAdultNovel(UrlFetcherLocusAnnual):
  source_id = 'locus_annual_young_adult_novel'
  NAME = 'Locus - Annual Young Adult Novel'
  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  ) + SPECULATIVE_CATEGORIES
  CATEGORY = 'Young Adult Novel'
  CATEGORY_ALIASES = ('young adult novel', 'young adult book')


class UrlFetcherLocusAnnualFirstNovel(UrlFetcherLocusAnnual):
  source_id = 'locus_annual_first_novel'
  NAME = 'Locus - Annual First Novel'
  CATEGORY = 'First Novel'
  CATEGORY_ALIASES = ('first novel',)
  ISFDB_CATEGORY_ALIASES = ('Best First Novel',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherLocusAnnualTranslatedNovel(UrlFetcherLocusAnnual):
  source_id = 'locus_annual_translated_novel'
  NAME = 'Locus - Annual Translated Novel'
  CATEGORY = 'Translated Novel'
  CATEGORY_ALIASES = ('translated novel',)


class UrlFetcherLocusAnnualNovella(UrlFetcherLocusAnnual):
  source_id = 'locus_annual_novella'
  NAME = 'Locus - Annual Novella'
  CATEGORY = 'Novella'
  CATEGORY_ALIASES = ('novella',)
  ISFDB_CATEGORY_ALIASES = ('Best Novella',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherLocusAnnualAnthology(UrlFetcherLocusAnnual):
  source_id = 'locus_annual_anthology'
  NAME = 'Locus - Annual Anthology'
  CATEGORY = 'Anthology'
  CATEGORY_ALIASES = ('anthology',)
  ISFDB_CATEGORY_ALIASES = ('Best Anthology',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherLocusAnnualCollection(UrlFetcherLocusAnnual):
  source_id = 'locus_annual_collection'
  NAME = 'Locus - Annual Collection'
  CATEGORY = 'Collection'
  CATEGORY_ALIASES = ('collection',)
  ISFDB_CATEGORY_ALIASES = ('Best Collection', 'Best Single Author Collection')
  USE_ISFDB_FALLBACK = True


class UrlFetcherLocusAnnualNonfiction(UrlFetcherLocusAnnual):
  source_id = 'locus_annual_nonfiction'
  NAME = 'Locus - Annual Non-Fiction'
  FILTER_CATEGORIES = (CATEGORY_NONFICTION,) + SPECULATIVE_CATEGORIES
  CATEGORY = 'Non-Fiction'
  CATEGORY_ALIASES = ('non fiction', 'nonfiction')


class UrlFetcherLocusAnnualIllustratedAndArtBook(UrlFetcherLocusAnnual):
  source_id = 'locus_annual_illustrated_and_art_book'
  NAME = 'Locus - Annual Illustrated and Art Book'
  FILTER_CATEGORIES = (CATEGORY_NONFICTION,) + SPECULATIVE_CATEGORIES
  CATEGORY = 'Illustrated and Art Book'
  CATEGORY_ALIASES = ('illustrated and art book', 'art book')


class UrlFetcherLocusAllTime1975Novel(UrlFetcherLocusAllTime):
  source_id = 'locus_all_time_1975_novel'
  NAME = 'Locus - All-Time 1975 Novel'
  URL = 'https://www.sfadb.com/Locus_1975'
  FETCH_URLS = (URL,)
  POLL_YEAR = '1975'
  CATEGORY = 'All-Time Novel'


class UrlFetcherLocusAllTime1987SFNovel(UrlFetcherLocusAllTime):
  source_id = 'locus_all_time_1987_sf_novel'
  NAME = 'Locus - All-Time 1987 SF Novel'
  FILTER_CATEGORIES = (CATEGORY_SCIENCE_FICTION,)
  URL = 'https://www.sfadb.com/Locus_1987_SF'
  FETCH_URLS = (URL,)
  POLL_YEAR = '1987'
  CATEGORY = 'All-Time SF Novel'


class UrlFetcherLocusAllTime1987FantasyNovel(UrlFetcherLocusAllTime):
  source_id = 'locus_all_time_1987_fantasy_novel'
  NAME = 'Locus - All-Time 1987 Fantasy Novel'
  FILTER_CATEGORIES = (CATEGORY_FANTASY,)
  URL = 'https://www.sfadb.com/Locus_1987_Fantasy'
  FETCH_URLS = (URL,)
  POLL_YEAR = '1987'
  CATEGORY = 'All-Time Fantasy Novel'


class UrlFetcherLocusAllTime1998SFNovel(UrlFetcherLocusAllTime):
  source_id = 'locus_all_time_1998_sf_novel'
  NAME = 'Locus - All-Time 1998 SF Novel'
  FILTER_CATEGORIES = (CATEGORY_SCIENCE_FICTION,)
  URL = 'https://www.sfadb.com/Locus_1998_SF'
  FETCH_URLS = (URL,)
  POLL_YEAR = '1998'
  CATEGORY = 'All-Time SF Novel'


class UrlFetcherLocusAllTime1998FantasyNovel(UrlFetcherLocusAllTime):
  source_id = 'locus_all_time_1998_fantasy_novel'
  NAME = 'Locus - All-Time 1998 Fantasy Novel'
  FILTER_CATEGORIES = (CATEGORY_FANTASY,)
  URL = 'https://www.sfadb.com/Locus_1998_Fantasy'
  FETCH_URLS = (URL,)
  POLL_YEAR = '1998'
  CATEGORY = 'All-Time Fantasy Novel'


class UrlFetcherLocusAllTime2012SF20thNovel(UrlFetcherLocusAllTime):
  source_id = 'locus_all_time_2012_sf_20th_novel'
  NAME = 'Locus - All-Time 2012 20th Century SF Novel'
  FILTER_CATEGORIES = (CATEGORY_SCIENCE_FICTION,)
  URL = 'https://www.sfadb.com/Locus_2012_SF20th'
  FETCH_URLS = (URL,)
  POLL_YEAR = '2012'
  CATEGORY = 'All-Time 20th Century SF Novel'


class UrlFetcherLocusAllTime2012FH20thNovel(UrlFetcherLocusAllTime):
  source_id = 'locus_all_time_2012_fh_20th_novel'
  NAME = 'Locus - All-Time 2012 20th Century Fantasy/Horror Novel'
  FILTER_CATEGORIES = FANTASY_HORROR_CATEGORIES
  URL = 'https://www.sfadb.com/Locus_2012_FH20th'
  FETCH_URLS = (URL,)
  POLL_YEAR = '2012'
  CATEGORY = 'All-Time 20th Century Fantasy/Horror Novel'


class UrlFetcherLocusAllTime2012SF21stNovel(UrlFetcherLocusAllTime):
  source_id = 'locus_all_time_2012_sf_21st_novel'
  NAME = 'Locus - All-Time 2012 21st Century SF Novel'
  FILTER_CATEGORIES = (CATEGORY_SCIENCE_FICTION,)
  URL = 'https://www.sfadb.com/Locus_2012_SF21st'
  FETCH_URLS = (URL,)
  POLL_YEAR = '2012'
  CATEGORY = 'All-Time 21st Century SF Novel'


class UrlFetcherLocusAllTime2012FH21stNovel(UrlFetcherLocusAllTime):
  source_id = 'locus_all_time_2012_fh_21st_novel'
  NAME = 'Locus - All-Time 2012 21st Century Fantasy/Horror Novel'
  FILTER_CATEGORIES = FANTASY_HORROR_CATEGORIES
  URL = 'https://www.sfadb.com/Locus_2012_FH21st'
  FETCH_URLS = (URL,)
  POLL_YEAR = '2012'
  CATEGORY = 'All-Time 21st Century Fantasy/Horror Novel'
