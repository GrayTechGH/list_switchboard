#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_SCIENCE_FICTION, UrlFetcherGeneric
from .spsfc_transport import SPSFCFetchPolicy


SPSFC_AWARDS_URL = 'https://spsfc.space/2026/10/08/the-spsfc-5-winner-is/'


class UrlFetcherSPSFCNovelFinalists(UrlFetcherGeneric):

  source_id = 'spsfc_novel_finalists'
  NAME = 'SPSFC - Novel Finalists'
  URL = SPSFC_AWARDS_URL
  FETCH_URLS = (SPSFC_AWARDS_URL,)
  FILTER_CATEGORIES = (CATEGORY_SCIENCE_FICTION,)
  order = 206
  options = {
    'match_series': False,
  }

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.spsfc import SPSFCAwardsParser
    except ImportError:
      from parser.spsfc import SPSFCAwardsParser

    return SPSFCAwardsParser()

  def fetch_and_parse(self, fetch_url, *args, **kwargs):
    policy = SPSFCFetchPolicy(fetch_url, self.parser(), log=kwargs.get('log'))
    return super().fetch_and_parse(policy.fetch, *args, **kwargs)

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      fetch_url=fetch_url,
      log=log,
      progress=progress)
