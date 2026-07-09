#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  UrlFetcherError,
  UrlFetcherGeneric,
  parsed_source,
)

try:
  from calibre_plugins.list_switchboard.parser.pen_america import (
    PENAwardConfig, PENAmericaAwardParser,
  )
except ImportError:
  from parser.pen_america import PENAwardConfig, PENAmericaAwardParser


PEN_ANNUAL_POST_URLS = (
  ('https://pen.org/2026-pen-america-literary-awards-finalists/', 'annual'),
  ('https://pen.org/announcing-the-2025-pen-america-literary-awards-winners/', 'annual'),
  ('https://pen.org/2025-pen-america-literary-awards-finalists/', 'annual'),
  ('https://pen.org/announcing-the-2024-pen-america-literary-awards-winners/', 'annual'),
  ('https://pen.org/2024-pen-america-literary-awards-finalists/', 'annual'),
  ('https://pen.org/2023-pen-america-literary-awards-finalists/', 'annual'),
)


class UrlFetcherPENAmericaAward(UrlFetcherGeneric):

  order = 174
  options = {'match_series': False}
  AWARD_NAME = ''
  CATEGORY = ''
  HEADING_ALIASES = ()
  LANDING_URL = ''
  SPLIT_MODE = 'auto'
  ANNUAL_POST_URLS = PEN_ANNUAL_POST_URLS

  @property
  def URL(self):
    return self.LANDING_URL

  def create_parser(self):
    return PENAmericaAwardParser()

  def config(self):
    return PENAwardConfig(
      self.AWARD_NAME, self.CATEGORY, self.HEADING_ALIASES, self.SPLIT_MODE)

  def source_choices(self):
    return ({'label': 'Automatic', 'value': 'automatic'},)

  def primary_urls(self):
    return (self.LANDING_URL,) + tuple(url for url, _kind in self.ANNUAL_POST_URLS)

  def fetch_and_parse(
      self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
      before_fetch=None, after_fetch=None, before_parse=None,
      force_fallback_level=0, disable_fallbacks=False, source_choice=None):
    pages = []
    urls = [(self.LANDING_URL, 'landing')] + list(self.ANNUAL_POST_URLS)
    for index, (url, page_kind) in enumerate(urls, start=1):
      if before_fetch is not None:
        before_fetch(url)
      html = self.fetch_url(fetch_url, url)
      if after_fetch is not None:
        after_fetch(url, html)
      if progress is not None:
        progress(index, len(urls), 'Fetched PEN America source %d of %d' % (
          index, len(urls)))
      pages.append((url, html, page_kind))
    parsed = self.parser().parse(pages, self.LANDING_URL, self.NAME, self.config())
    if not parsed.get('entries'):
      raise UrlFetcherError('%s produced no entries' % self.NAME)
    parsed.setdefault('source', parsed_source(self.NAME, self.LANDING_URL, self.source_id))
    parsed.setdefault('match_series', False)
    return parsed

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.LANDING_URL, self.NAME, self.config())


class UrlFetcherPENGalbraithAward(UrlFetcherPENAmericaAward):
  source_id = 'pen_galbraith_award_nonfiction'
  NAME = 'PEN/John Kenneth Galbraith Award for Nonfiction'
  AWARD_NAME = NAME
  CATEGORY = 'Nonfiction'
  LANDING_URL = 'https://pen.org/literary-awards/pen-galbraith-award-for-nonfiction/'
  HEADING_ALIASES = (
    'PEN/John Kenneth Galbraith Award for Nonfiction',
    'PEN/Galbraith Award for Nonfiction',
    'Galbraith Award for Nonfiction',
  )
  SPLIT_MODE = 'title_author'
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )


class UrlFetcherPENDiamonsteinSpielvogelAward(UrlFetcherPENAmericaAward):
  source_id = 'pen_diamonstein_spielvogel_award_essay'
  NAME = 'PEN/Diamonstein-Spielvogel Award for the Art of the Essay'
  AWARD_NAME = NAME
  CATEGORY = 'Essay'
  LANDING_URL = (
    'https://pen.org/literary-awards/'
    'pen-diamonstein-spielvogel-award-for-the-art-of-the-essay/'
  )
  HEADING_ALIASES = (
    'PEN/Diamonstein-Spielvogel Award for the Art of the Essay',
    'Diamonstein-Spielvogel Award for the Art of the Essay',
  )
  SPLIT_MODE = 'title_author'
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )


class UrlFetcherPENJeanSteinBookAward(UrlFetcherPENAmericaAward):
  source_id = 'pen_jean_stein_book_award'
  NAME = 'PEN/Jean Stein Book Award'
  AWARD_NAME = NAME
  CATEGORY = 'Book'
  LANDING_URL = 'https://pen.org/literary-awards/pen-jean-stein-book-award/'
  HEADING_ALIASES = (
    'PEN/Jean Stein Book Award',
    'Jean Stein Book Award',
  )
  SPLIT_MODE = 'title_author'
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )


class UrlFetcherPENOpenBookAward(UrlFetcherPENAmericaAward):
  source_id = 'pen_open_book_award'
  NAME = 'PEN Open Book Award'
  AWARD_NAME = NAME
  CATEGORY = 'Book'
  LANDING_URL = 'https://pen.org/literary-awards/pen-open-book-award/'
  HEADING_ALIASES = (
    'PEN Open Book Award',
    'Open Book Award',
  )
  SPLIT_MODE = 'title_author'
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
