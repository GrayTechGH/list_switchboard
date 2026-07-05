#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  UrlFetcherGeneric,
)


class UrlFetcherMilesFranklinLiteraryAward(UrlFetcherGeneric):

  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'miles_franklin_literary_award'
  NAME = 'Miles Franklin Literary Award'
  URL = 'https://en.wikipedia.org/wiki/Miles_Franklin_Award'
  order = 239
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.miles_franklin import (
        MilesFranklinWikipediaParser,
      )
    except ImportError:
      from parser.miles_franklin import MilesFranklinWikipediaParser
    return MilesFranklinWikipediaParser()

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME)
