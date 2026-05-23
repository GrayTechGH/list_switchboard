#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_SCIENCE_FICTION, UrlFetcherGeneric


class UrlFetcherPhilipKDickAwardNovel(UrlFetcherGeneric):

  source_id = 'philip_k_dick_award_novel'
  NAME = 'Philip K. Dick Award - Novel'
  FILTER_CATEGORIES = (CATEGORY_SCIENCE_FICTION,)
  URL = 'https://www.sfadb.com/Philip_K_Dick_Award'
  FETCH_URLS = (URL,)
  order = 120
  options = {
    'match_series': False,
  }

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.philip_k_dick import (
        PhilipKDickParser,
      )
    except ImportError:
      from parser.philip_k_dick import PhilipKDickParser

    return PhilipKDickParser()

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      fetch_url=fetch_url,
      log=log,
      progress=progress)
