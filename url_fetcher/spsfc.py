#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_SCIENCE_FICTION, UrlFetcherGeneric


SPSFC_AWARDS_URL = 'https://spsfc.space/2025/08/07/and-the-spsfc-4-winner-is/'


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

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      fetch_url=fetch_url,
      log=log,
      progress=progress)
