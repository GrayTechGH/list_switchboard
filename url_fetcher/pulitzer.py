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


PULITZER_FICTION_URL = 'https://www.pulitzer.org/prize-winners-by-category/219'
PULITZER_GENERAL_NONFICTION_URL = (
  'https://www.pulitzer.org/prize-winners-by-category/223'
)
PULITZER_FICTION_WIKIPEDIA_URL = (
  'https://en.wikipedia.org/wiki/Pulitzer_Prize_for_Fiction'
)
PULITZER_GENERAL_NONFICTION_WIKIPEDIA_URL = (
  'https://en.wikipedia.org/wiki/Pulitzer_Prize_for_General_Nonfiction'
)
PULITZER_FICTION_BRITANNICA_URL = (
  'https://www.britannica.com/topic/winners-of-the-Pulitzer-Prize-for-fiction-2227349'
)
PULITZER_BRITANNICA_URL = 'https://www.britannica.com/topic/Pulitzer-Prize'


class UrlFetcherPulitzerAward(UrlFetcherGeneric):

  FETCH_URLS = ()
  order = 170
  options = {'match_series': False}
  AWARD_NAME = 'Pulitzer Prize'
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  WIKIPEDIA_URL = ''
  BRITANNICA_URL = ''
  BRITANNICA_TABLE_HEADING = ''
  WIKIPEDIA_TIED_WINNER_YEARS = {}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.pulitzer import (
        PulitzerAwardParser,
      )
    except ImportError:
      from parser.pulitzer import PulitzerAwardParser
    return PulitzerAwardParser()

  def source_attempts(self):
    try:
      from calibre_plugins.list_switchboard.parser.pulitzer import (
        PulitzerAwardParser,
        PulitzerBritannicaParser,
        PulitzerWikipediaParser,
      )
    except ImportError:
      from parser.pulitzer import (
        PulitzerAwardParser,
        PulitzerBritannicaParser,
        PulitzerWikipediaParser,
      )
    return (
      SourceAttempt(
        'Official Pulitzer',
        self.URL,
        lambda html, url, **_kwargs: PulitzerAwardParser().parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES),
        source_rank=0),
      SourceAttempt(
        'Wikipedia',
        self.WIKIPEDIA_URL,
        lambda html, url, **_kwargs: PulitzerWikipediaParser().parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES,
          tied_winner_years=self.WIKIPEDIA_TIED_WINNER_YEARS),
        source_rank=1),
      SourceAttempt(
        'Britannica',
        self.BRITANNICA_URL,
        lambda html, url, **_kwargs: PulitzerBritannicaParser().parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES,
          table_heading=self.BRITANNICA_TABLE_HEADING),
        source_rank=2),
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
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES)


class UrlFetcherPulitzerFiction(UrlFetcherPulitzerAward):
  source_id = 'pulitzer_prize_fiction'
  NAME = 'Pulitzer Prize - Fiction'
  URL = PULITZER_FICTION_URL
  CATEGORY = 'Fiction'
  WIKIPEDIA_URL = PULITZER_FICTION_WIKIPEDIA_URL
  BRITANNICA_URL = PULITZER_FICTION_BRITANNICA_URL
  WIKIPEDIA_TIED_WINNER_YEARS = {2023: 2}
  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )


class UrlFetcherPulitzerGeneralNonfiction(UrlFetcherPulitzerAward):
  source_id = 'pulitzer_prize_general_nonfiction'
  NAME = 'Pulitzer Prize - General Nonfiction'
  URL = PULITZER_GENERAL_NONFICTION_URL
  CATEGORY = 'General Nonfiction'
  WIKIPEDIA_URL = PULITZER_GENERAL_NONFICTION_WIKIPEDIA_URL
  BRITANNICA_URL = PULITZER_BRITANNICA_URL
  BRITANNICA_TABLE_HEADING = 'General Nonfiction'
  WIKIPEDIA_TIED_WINNER_YEARS = {
    1969: 2,
    1973: 2,
    1986: 2,
    2020: 2,
  }
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
