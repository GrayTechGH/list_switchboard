#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_ROMANCE,
  UrlFetcherGeneric,
)


class UrlFetcherRNARomanticNovelAwards(UrlFetcherGeneric):

  source_id = 'rna_romantic_novel_awards'
  NAME = 'RNA Romantic Novel of the Year Awards'
  URL = 'https://romanticnovelistsassociation.org/past-winners'
  order = 248
  options = {'match_series': False}
  FILTER_CATEGORIES = (CATEGORY_ROMANCE, CATEGORY_REGIONAL_NATIONAL_AWARDS)

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.rna_awards import ( # type: ignore
        RNARomanticNovelAwardsParser,
      )
    except ImportError:
      from parser.rna_awards import RNARomanticNovelAwardsParser
    return RNARomanticNovelAwardsParser()

  def parse(self, html, fetch_url=None, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME, fetch_url=fetch_url)


class UrlFetcherRNAJoanHessayonAward(UrlFetcherRNARomanticNovelAwards):

  source_id = 'rna_joan_hessayon_award'
  NAME = 'RNA Joan Hessayon Award for New Writers'

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.rna_awards import ( # type: ignore
        RNAJoanHessayonAwardParser,
      )
    except ImportError:
      from parser.rna_awards import RNAJoanHessayonAwardParser
    return RNAJoanHessayonAwardParser()
