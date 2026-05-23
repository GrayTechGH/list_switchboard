#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_SCIENCE_FICTION,
  UrlFetcherError,
  UrlFetcherGeneric,
)

try:
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
except ImportError:
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner


OFFICIAL_URL = 'https://www.clarkeaward.com/'
SFADB_URL = 'https://www.sfadb.com/Arthur_C_Clarke_Award'


class UrlFetcherArthurCClarkeAwardNovel(UrlFetcherGeneric):

  source_id = 'arthur_c_clarke_award_novel'
  NAME = 'Arthur C. Clarke Award - Novel'
  FILTER_CATEGORIES = (CATEGORY_SCIENCE_FICTION, CATEGORY_REGIONAL_NATIONAL_AWARDS)
  URL = OFFICIAL_URL
  SFADB_URL = SFADB_URL
  FETCH_URLS = ()
  order = 100
  options = {
    'match_series': False,
  }

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.clarke import OfficialClarkeParser
    except ImportError:
      from parser.clarke import OfficialClarkeParser

    return OfficialClarkeParser()

  def create_sfadb_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.clarke import ClarkeParser
    except ImportError:
      from parser.clarke import ClarkeParser

    return ClarkeParser()

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

  def source_attempts(self):
    return (
      SourceAttempt(
        'Official Arthur C. Clarke Award',
        self.URL,
        self.parser(),
        source_rank=0),
      SourceAttempt(
        'SFADB',
        self.SFADB_URL,
        self.create_sfadb_parser(),
        source_rank=1),
    )

  def source_choices(self):
    return SourceFallbackRunner(self.source_attempts()).source_choices()

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      fetch_url=fetch_url,
      log=log,
      progress=progress)
