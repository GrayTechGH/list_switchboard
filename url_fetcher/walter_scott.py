#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
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


OFFICIAL_URL = (
  'https://www.walterscottprize.co.uk/wp-content/uploads/2025/08/'
  'PREVIOUS-WINNERS-OF-THE-WALTER-SCOTT-PRIZE-FOR-HISTORICAL-FICTION.pdf')
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Walter_Scott_Prize'


class UrlFetcherWalterScottPrize(UrlFetcherGeneric):

  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'walter_scott_prize'
  NAME = 'Walter Scott Prize'
  URL = OFFICIAL_URL
  WIKIPEDIA_URL = WIKIPEDIA_URL
  order = 243
  options = {'match_series': False}

  def create_official_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.walter_scott import WalterScottOfficialParser
    except ImportError:
      from parser.walter_scott import WalterScottOfficialParser
    return WalterScottOfficialParser()

  def create_wikipedia_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.walter_scott import WalterScottWikipediaParser
    except ImportError:
      from parser.walter_scott import WalterScottWikipediaParser
    return WalterScottWikipediaParser()

  def source_attempts(self):
    return (
      SourceAttempt(
        'Walter Scott',
        self.URL,
        lambda html, url, fetch_url=None, log=None, progress=None: (
          self.create_official_parser().parse(
            html, url, self.NAME, fetch_url=fetch_url, log=log, progress=progress)),
        source_rank=0,
        max_response_bytes=32 * 1024 * 1024),
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

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.create_official_parser().parse(
      html,
      self.URL,
      self.NAME,
      fetch_url=fetch_url,
      log=log,
      progress=progress)
