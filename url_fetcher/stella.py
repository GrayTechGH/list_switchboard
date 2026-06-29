#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  UrlFetcherError,
  UrlFetcherGeneric,
)

try:
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
except ImportError:
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner


OFFICIAL_URL = 'https://stella.org.au/past-prize-winners/'
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Stella_Prize'


class UrlFetcherStellaPrize(UrlFetcherGeneric):

  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'stella_prize'
  NAME = 'Stella Prize'
  URL = OFFICIAL_URL
  WIKIPEDIA_URL = WIKIPEDIA_URL
  order = 240
  options = {'match_series': False}

  def create_official_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.stella import StellaOfficialParser
    except ImportError:
      from parser.stella import StellaOfficialParser
    return StellaOfficialParser()

  def create_wikipedia_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.stella import StellaWikipediaParser
    except ImportError:
      from parser.stella import StellaWikipediaParser
    return StellaWikipediaParser()

  def source_attempts(self):
    return (
      SourceAttempt(
        'Stella',
        self.URL,
        lambda html, url, **_kwargs: self.create_official_parser().parse(
          html, url, self.NAME),
        source_rank=0),
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
      force_fallback_level=0, disable_fallbacks=False, source_choice=None):
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

  def parse(self, html, **_kwargs):
    return self.create_official_parser().parse(html, self.URL, self.NAME)
