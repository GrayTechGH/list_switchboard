#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_FANTASY,
  CATEGORY_SCIENCE_FICTION,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherGeneric,
)
from .isfdb_fallback import SFADBISFDYAwardFallbackMixin


PROMETHEUS_AWARDS_URL = 'https://www.sfadb.com/Prometheus_Awards'
PROMETHEUS_CATEGORIES = (CATEGORY_SCIENCE_FICTION, CATEGORY_FANTASY)


class UrlFetcherPrometheus(SFADBISFDYAwardFallbackMixin, UrlFetcherGeneric):

  URL = PROMETHEUS_AWARDS_URL
  FETCH_URLS = (PROMETHEUS_AWARDS_URL,)
  FILTER_CATEGORIES = PROMETHEUS_CATEGORIES
  order = 170
  options = {
    'match_series': False,
  }
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  BOOKS_ONLY = False
  AWARD_NAME = 'Prometheus Award'
  ISFDB_AWARD_ID = '33'

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.prometheus import PrometheusParser
    except ImportError:
      from parser.prometheus import PrometheusParser

    return PrometheusParser(books_only=self.BOOKS_ONLY)

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


class UrlFetcherPrometheusNovel(UrlFetcherPrometheus):
  source_id = 'prometheus_novel'
  NAME = 'Prometheus - Novel'
  CATEGORY = 'Novel'
  CATEGORY_ALIASES = ('novel',)
  ISFDB_CATEGORY_ALIASES = ('Prometheus Award for Best Libertarian SF Novel',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherPrometheusHallOfFame(UrlFetcherPrometheus):
  source_id = 'prometheus_hall_of_fame'
  NAME = 'Prometheus - Hall of Fame'
  CATEGORY = 'Hall of Fame'
  CATEGORY_ALIASES = ('hall of fame',)
  BOOKS_ONLY = True
  ISFDB_CATEGORY_ALIASES = ('Prometheus Hall of Fame Award',)
  USE_ISFDB_FALLBACK = True


class UrlFetcherPrometheusYoungAdultHonorRoll(UrlFetcherPrometheus):
  source_id = 'prometheus_young_adult_honor_roll'
  NAME = 'Prometheus - Young Adult Honor Roll'
  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  ) + PROMETHEUS_CATEGORIES
  CATEGORY = 'Young Adult Honor Roll'
  CATEGORY_ALIASES = ('young adult honor roll',)


class UrlFetcherPrometheusSpecialAwards(UrlFetcherPrometheus):
  source_id = 'prometheus_special_awards'
  NAME = 'Prometheus - Special Awards'
  CATEGORY = 'Special Awards'
  CATEGORY_ALIASES = ('special awards', 'special award')
  BOOKS_ONLY = True
