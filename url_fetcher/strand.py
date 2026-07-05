#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_CRIME_MYSTERY_THRILLER, UrlFetcherGeneric


STRAND_URL = 'https://www.librarything.com/award/1380/The-Strand-Critics-Award'


class UrlFetcherStrandAward(UrlFetcherGeneric):

  FILTER_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER,)
  FETCH_URLS = ()
  order = 232
  options = {'match_series': False}
  URL = STRAND_URL
  AWARD_NAME = 'The Strand Critics Award'
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.strand import (
        StrandLibraryThingParser,
      )
    except ImportError:
      from parser.strand import StrandLibraryThingParser
    return StrandLibraryThingParser()

  def parse(self, html, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES)


class UrlFetcherStrandMysteryNovel(UrlFetcherStrandAward):
  source_id = 'strand_critics_award_mystery_novel'
  NAME = 'Strand Critics Award - Mystery Novel'
  CATEGORY = 'Best Mystery Novel'
  CATEGORY_ALIASES = (
    'Mystery Novel',
    'Best Novel',
  )


class UrlFetcherStrandDebutMystery(UrlFetcherStrandAward):
  source_id = 'strand_critics_award_debut_mystery'
  NAME = 'Strand Critics Award - Debut Mystery'
  CATEGORY = 'Best Debut Mystery'
  CATEGORY_ALIASES = (
    'Best Debut Novel',
    'Debut Mystery',
    'Debut Novel',
    'Best First Novel',
  )
