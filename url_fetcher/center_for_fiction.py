#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  UrlFetcherError,
  UrlFetcherGeneric,
)
from .center_for_fiction_transport import CenterForFictionOfficialAttempt

try:
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
  from calibre_plugins.list_switchboard.parser.center_for_fiction_updates import fetch_center_official
  from calibre_plugins.list_switchboard.parser.center_for_fiction_sources import WINNERS_URL
except ImportError:
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner
  from parser.center_for_fiction_updates import fetch_center_official
  from parser.center_for_fiction_sources import WINNERS_URL


OFFICIAL_URL = 'https://centerforfiction.org/grants-awards/the-first-novel-prize/'
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Center_for_Fiction_First_Novel_Prize'


class UrlFetcherCenterForFictionFirstNovelPrize(UrlFetcherGeneric):

  SUPPORTS_INCREMENTAL_UPDATE = True
  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'center_for_fiction_first_novel_prize'
  NAME = 'Center for Fiction First Novel Prize'
  URL = OFFICIAL_URL
  WIKIPEDIA_URL = WIKIPEDIA_URL
  WINNERS_URL = WINNERS_URL
  FIRST_YEAR = 2006
  order = 243
  options = {'match_series': False}

  def create_parser(self):
    return self.create_official_parser()

  def create_official_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.center_for_fiction import ( # type: ignore
        CenterForFictionFirstNovelOfficialParser,
      )
    except ImportError:
      from parser.center_for_fiction import CenterForFictionFirstNovelOfficialParser
    return CenterForFictionFirstNovelOfficialParser()

  def create_wikipedia_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.center_for_fiction import ( # type: ignore
        CenterForFictionFirstNovelWikipediaParser,
      )
    except ImportError:
      from parser.center_for_fiction import CenterForFictionFirstNovelWikipediaParser
    return CenterForFictionFirstNovelWikipediaParser()

  def source_attempts(self):
    return (
      CenterForFictionOfficialAttempt(self,
        'Center for Fiction',
        self.URL,
        lambda html, url, fetch_url=None, progress=None, cached_parsed=None, incremental_update=False, **_kwargs:
          fetch_center_official(self, self.parser(), html, url, fetch_url,
            cached_parsed, incremental_update, progress),
        source_rank=0, supports_incremental=True),
      SourceAttempt(
        'Wikipedia',
        self.WIKIPEDIA_URL,
        lambda html, url, **_kwargs: self.create_wikipedia_parser().parse(
          html, url, self.NAME),
        source_rank=1),
    )

  def source_choices(self):
    return SourceFallbackRunner(self.source_attempts()).source_choices()

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
        source_choice=source_choice, cached_parsed=cached_parsed,
        incremental_update=incremental_update)
    parsed.setdefault('match_series', self.options.get('match_series', True))
    return parsed

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.create_official_parser().parse(
      html, self.URL, self.NAME, fetch_url=fetch_url, log=log, progress=progress)
