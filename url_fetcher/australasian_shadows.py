#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_HORROR_DARK_FICTION,
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  UrlFetcherError,
  UrlFetcherGeneric,
)

try:
  from calibre_plugins.list_switchboard.parser.australasian_shadows import (
    OFFICIAL_CURRENT_API_URL, OFFICIAL_CURRENT_URL, WIKIPEDIA_URL,
  )
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
except ImportError:
  from parser.australasian_shadows import (
    OFFICIAL_CURRENT_API_URL, OFFICIAL_CURRENT_URL, WIKIPEDIA_URL,
  )
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner


AUSTRALASIAN_SHADOWS_CATEGORIES = (
  CATEGORY_HORROR_DARK_FICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
)
AUSTRALASIAN_SHADOWS_NONFICTION_CATEGORIES = (
  CATEGORY_HORROR_DARK_FICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_NONFICTION,
)


class UrlFetcherAustralasianShadows(UrlFetcherGeneric):

  URL = OFFICIAL_CURRENT_URL
  FETCH_URLS = ()
  FILTER_CATEGORIES = AUSTRALASIAN_SHADOWS_CATEGORIES
  order = 142
  options = {'match_series': False}
  AWARD_NAME = 'Australasian Shadows Award'
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.australasian_shadows import (
        AustralasianShadowsParser,
      )
    except ImportError:
      from parser.australasian_shadows import AustralasianShadowsParser
    return AustralasianShadowsParser()

  def fetch_and_parse(
      self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
      before_fetch=None, after_fetch=None, before_parse=None,
      force_fallback_level=0, disable_fallbacks=False, source_choice=None,
      cached_parsed=None, incremental_update=False):
    parsed = SourceFallbackRunner(
      self.source_attempts(),
      error_class=UrlFetcherError).run(
        fetch_url,
        log=log,
        progress=progress,
        before_fetch=before_fetch,
        after_fetch=after_fetch,
        before_parse=before_parse,
        force_fallback_level=force_fallback_level,
        disable_fallbacks=disable_fallbacks,
        source_choice=source_choice)
    parsed.setdefault('match_series', self.options.get('match_series', True))
    return parsed

  def source_attempts(self):
    parser = self.parser()
    return (
      SourceAttempt(
        'Australasian Horror Writers Association',
        OFFICIAL_CURRENT_API_URL,
        lambda html, url, fetch_url=None, log=None, progress=None: (
          parser.parse_official(
            html,
            url,
            self.NAME,
            self.CATEGORY,
            self.CATEGORY_ALIASES,
            fetch_url=fetch_url,
            log=log,
            progress=progress)),
        source_rank=0),
      SourceAttempt(
        'Wikipedia',
        WIKIPEDIA_URL,
        lambda html, url, fetch_url=None, log=None, progress=None: (
          parser.parse_wikipedia(
            html,
            url,
            self.NAME,
            self.CATEGORY,
            self.CATEGORY_ALIASES,
            fetch_url=fetch_url,
            log=log,
            progress=progress)),
        source_rank=1),
    )

  def source_choices(self):
    return SourceFallbackRunner(self.source_attempts()).source_choices()

  def parse(self, html, **_kwargs):
    return self.parser().parse_official(
      html,
      OFFICIAL_CURRENT_API_URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES)


class UrlFetcherAustralasianShadowsNovel(UrlFetcherAustralasianShadows):
  source_id = 'australasian_shadows_novel'
  NAME = 'Australasian Shadows - Novel'
  CATEGORY = 'Novel'
  CATEGORY_ALIASES = ('novel',)


class UrlFetcherAustralasianShadowsLongFiction(UrlFetcherAustralasianShadows):
  source_id = 'australasian_shadows_long_fiction'
  NAME = 'Australasian Shadows - Long Fiction'
  CATEGORY = 'Long Fiction'
  CATEGORY_ALIASES = (
    'long fiction',
    'paul haines award for long fiction',
  )


class UrlFetcherAustralasianShadowsCollectedWork(UrlFetcherAustralasianShadows):
  source_id = 'australasian_shadows_collected_work'
  NAME = 'Australasian Shadows - Collected Work'
  CATEGORY = 'Collected Work'
  CATEGORY_ALIASES = ('collected work', 'collection')


class UrlFetcherAustralasianShadowsEditedWork(UrlFetcherAustralasianShadows):
  source_id = 'australasian_shadows_edited_work'
  NAME = 'Australasian Shadows - Edited Work'
  CATEGORY = 'Edited Work'
  CATEGORY_ALIASES = ('edited work', 'edited publication')


class UrlFetcherAustralasianShadowsGraphicNovel(UrlFetcherAustralasianShadows):
  source_id = 'australasian_shadows_graphic_novel'
  NAME = 'Australasian Shadows - Graphic Novel/Comic'
  CATEGORY = 'Graphic Novel/Comic'
  CATEGORY_ALIASES = (
    'graphic novel',
    'graphic novel comic',
    'graphic novel comics',
    'graphic novel or comic',
    'graphic novels comic',
    'graphic novels comics',
    'comic',
    'comics',
  )


class UrlFetcherAustralasianShadowsNonfiction(UrlFetcherAustralasianShadows):
  source_id = 'australasian_shadows_nonfiction'
  NAME = 'Australasian Shadows - Non-Fiction'
  FILTER_CATEGORIES = AUSTRALASIAN_SHADOWS_NONFICTION_CATEGORIES
  CATEGORY = 'Non-Fiction'
  CATEGORY_ALIASES = (
    'non-fiction',
    'non fiction',
    'nonfiction',
    'rocky wood award for non-fiction and criticism',
    'rocky wood award for non fiction and criticism',
    'rocky wood award for nonfiction and criticism',
  )
