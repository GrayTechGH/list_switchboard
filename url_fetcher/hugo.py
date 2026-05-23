#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_FANTASY,
  CATEGORY_NONFICTION,
  CATEGORY_SCIENCE_FICTION,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherGeneric,
)


SPECULATIVE_CATEGORIES = (
  CATEGORY_SCIENCE_FICTION,
  CATEGORY_FANTASY,
)


class UrlFetcherHugoAwards(UrlFetcherGeneric):

  URL = 'https://www.thehugoawards.org/hugo-history/'
  FETCH_URLS = (
    'https://www.thehugoawards.org/hugo-history/',
  )
  order = 50
  options = {
    'match_series': False,
  }
  PARSER_CLASS_NAME = ''

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser import hugo
    except ImportError:
      from parser import hugo

    return getattr(hugo, self.PARSER_CLASS_NAME)()

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      fetch_url=fetch_url,
      log=log,
      progress=progress)


class UrlFetcherHugoAwardsNovel(UrlFetcherHugoAwards):

  source_id = 'hugo_awards_novel'
  NAME = 'Hugo Awards - Novel'
  FILTER_CATEGORIES = SPECULATIVE_CATEGORIES
  PARSER_CLASS_NAME = 'HugoAwardsNovelParser'


class UrlFetcherHugoAwardsNovella(UrlFetcherHugoAwards):

  source_id = 'hugo_awards_novella'
  NAME = 'Hugo Awards - Novella'
  FILTER_CATEGORIES = SPECULATIVE_CATEGORIES
  PARSER_CLASS_NAME = 'HugoAwardsNovellaParser'


class UrlFetcherHugoAwardsSeries(UrlFetcherHugoAwards):

  source_id = 'hugo_awards_series'
  NAME = 'Hugo Awards - Series'
  REQUIRES_SERIES_MATCHING = True
  FILTER_CATEGORIES = SPECULATIVE_CATEGORIES
  PARSER_CLASS_NAME = 'HugoAwardsSeriesParser'
  options = {
    'match_series': True,
  }

  def parse(self, *args, **kwargs):
    parsed = super().parse(*args, **kwargs)
    parsed['match_series'] = True
    return parsed


class UrlFetcherHugoAwardsGraphicStory(UrlFetcherHugoAwards):

  source_id = 'hugo_awards_graphic_story_or_comic'
  NAME = 'Hugo Awards - Graphic Story or Comic'
  FILTER_CATEGORIES = SPECULATIVE_CATEGORIES
  PARSER_CLASS_NAME = 'HugoAwardsGraphicStoryParser'


class UrlFetcherHugoAwardsRelatedWork(UrlFetcherHugoAwards):

  source_id = 'hugo_awards_related_work'
  NAME = 'Hugo Awards - Related Work'
  FILTER_CATEGORIES = (CATEGORY_NONFICTION,) + SPECULATIVE_CATEGORIES
  PARSER_CLASS_NAME = 'HugoAwardsRelatedWorkParser'


class UrlFetcherLodestarAward(UrlFetcherHugoAwards):

  source_id = 'lodestar_award_young_adult_book'
  NAME = 'Lodestar Award - Young Adult Book'
  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  ) + SPECULATIVE_CATEGORIES
  PARSER_CLASS_NAME = 'LodestarAwardParser'
