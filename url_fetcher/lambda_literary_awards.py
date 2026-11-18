#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_ROMANCE,
  UrlFetcherGeneric,
)
from .lambda_transport import LambdaOfficialFetchPolicy

try:
  from calibre_plugins.list_switchboard.parser.lambda_updates import fetch_lambda
  from calibre_plugins.list_switchboard.parser.lambda_literary_awards import LAMBDA_CURRENT_FINALISTS_URL, LAMBDA_CURRENT_WINNERS_URL, ROMANCE_CATEGORY_ALIASES
except ImportError:
  from parser.lambda_updates import fetch_lambda
  from parser.lambda_literary_awards import LAMBDA_CURRENT_FINALISTS_URL, LAMBDA_CURRENT_WINNERS_URL, ROMANCE_CATEGORY_ALIASES


class UrlFetcherLambdaLiteraryAwardsRomance(UrlFetcherGeneric):

  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'lambda_literary_awards_romance'
  NAME = 'Lambda Literary Awards - Romance Categories'
  URL = 'https://lambdaliterary.org/awards/lammys-directory-1988-present/'
  order = 251
  options = {'match_series': False}
  FINALISTS_URL = LAMBDA_CURRENT_FINALISTS_URL
  WINNER_URLS = (LAMBDA_CURRENT_WINNERS_URL,)
  ROMANCE_CATEGORIES = ROMANCE_CATEGORY_ALIASES
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

  def fetch_and_parse(self, fetch_url, *args, **kwargs):
    policy = LambdaOfficialFetchPolicy(self, fetch_url, kwargs.get('log'))
    return super().fetch_and_parse(policy.fetch, *args, **kwargs)

  def parse(self, html, fetch_url=None, cached_parsed=None, incremental_update=False, **_kwargs):
    if fetch_url is None:
      return self.parser().parse(html, self.URL, self.NAME)
    return fetch_lambda(self, self.parser(), html, self.URL, fetch_url,
      cached_parsed, incremental_update)
