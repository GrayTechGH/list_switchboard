#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_ROMANCE,
  UrlFetcherGeneric,
)


class UrlFetcherLambdaLiteraryAwardsRomance(UrlFetcherGeneric):

  source_id = 'lambda_literary_awards_romance'
  NAME = 'Lambda Literary Awards - Romance Categories'
  URL = 'https://lambdaliterary.org/awards/lammys-directory-1988-present/'
  order = 251
  options = {'match_series': False}
  FILTER_CATEGORIES = (
    CATEGORY_ROMANCE,
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.lambda_literary_awards import ( # type: ignore
        LambdaLiteraryAwardsRomanceParser,
      )
    except ImportError:
      from parser.lambda_literary_awards import LambdaLiteraryAwardsRomanceParser
    return LambdaLiteraryAwardsRomanceParser()

  def parse(self, html, fetch_url=None, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME, fetch_url=fetch_url)
