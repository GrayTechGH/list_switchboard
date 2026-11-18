#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  UrlFetcherGeneric,
)

try:
  from calibre_plugins.list_switchboard.parser.pen_faulkner_foundation import (
    PENFaulknerAwardParser, PENHemingwayAwardParser,
  )
  from calibre_plugins.list_switchboard.parser.pen_foundation_updates import fetch_foundation
except ImportError:
  from parser.pen_faulkner_foundation import (
    PENFaulknerAwardParser, PENHemingwayAwardParser,
  )
  from parser.pen_foundation_updates import fetch_foundation


class UrlFetcherPENFaulknerFoundationAward(UrlFetcherGeneric):

  order = 175
  options = {'match_series': False}
  URL = ''
  POST_URLS = ()
  PARSER_CLASS = PENFaulknerAwardParser
  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )

  def source_choices(self):
    return ({'label': 'Automatic', 'value': 'automatic'},)

  def primary_urls(self):
    return (self.URL,) + tuple(url for url, _kind in self.POST_URLS)

  def fetch_and_parse(
      self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
      before_fetch=None, after_fetch=None, before_parse=None,
      force_fallback_level=0, disable_fallbacks=False, source_choice=None,
      cached_parsed=None, incremental_update=False):
    return fetch_foundation(self,fetch_url,cached_parsed=cached_parsed,
      incremental_update=incremental_update,before_fetch=before_fetch,
      after_fetch=after_fetch,progress=progress)

  def parse(self, html, fetch_url=None, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME, fetch_url=fetch_url)


class UrlFetcherPENFaulknerAward(UrlFetcherPENFaulknerFoundationAward):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'pen_faulkner_award_fiction'
  NAME = 'PEN/Faulkner Award for Fiction'
  URL = 'https://www.penfaulkner.org/our-awards/pen-faulkner-award/'
  PARSER_CLASS = PENFaulknerAwardParser
  POST_URLS = (
    ('https://www.penfaulkner.org/2026/03/02/announcing-the-finalists-for-the-2026-pen-faulkner-award-for-fiction/', 'finalist_post'),
    ('https://www.penfaulkner.org/2026/04/06/announcing-the-winner-of-the-2026-pen-faulkner-award-for-fiction/', 'winner_post'),
    ('https://www.penfaulkner.org/2025/03/03/announcing-the-finalists-for-the-2025-pen-faulkner-award-for-fiction/', 'finalist_post'),
    ('https://www.penfaulkner.org/2025/04/07/announcing-the-winner-of-the-2025-pen-faulkner-award-for-fiction/', 'winner_post'),
  )


class UrlFetcherPENHemingwayAward(UrlFetcherPENFaulknerFoundationAward):
  SUPPORTS_INCREMENTAL_UPDATE = True
  source_id = 'pen_hemingway_award_debut_novel'
  NAME = 'PEN/Hemingway Award for Debut Novel'
  URL = 'https://www.penfaulkner.org/our-awards/the-pen-hemingway-award/'
  PARSER_CLASS = PENHemingwayAwardParser
  POST_URLS = (
    ('https://www.penfaulkner.org/2026/03/16/announcing-the-winner-of-the-pen-hemingway-award-for-debut-novel/', 'current'),
  )
