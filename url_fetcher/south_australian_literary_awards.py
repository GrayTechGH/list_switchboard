#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherError,
  UrlFetcherGeneric,
)

try:
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
except ImportError:
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner


OFFICIAL_URL = 'https://stories.slsa.sa.gov.au/south-australian-literary-awards/'
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/South_Australian_Literary_Awards'


class UrlFetcherSouthAustralianLiteraryAwards(UrlFetcherGeneric):

  URL = OFFICIAL_URL
  WIKIPEDIA_URL = WIKIPEDIA_URL
  FETCH_URLS = ()
  order = 245
  options = {'match_series': False}
  AWARD_NAME = 'South Australian Literary Awards'
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_official_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.south_australian_literary_awards import (
        SouthAustralianLiteraryAwardsOfficialParser,
      )
    except ImportError:
      from parser.south_australian_literary_awards import (
        SouthAustralianLiteraryAwardsOfficialParser,
      )
    return SouthAustralianLiteraryAwardsOfficialParser(
      self.CATEGORY, self.CATEGORY_ALIASES)

  def create_wikipedia_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.south_australian_literary_awards import (
        SouthAustralianLiteraryAwardsWikipediaParser,
      )
    except ImportError:
      from parser.south_australian_literary_awards import (
        SouthAustralianLiteraryAwardsWikipediaParser,
      )
    return SouthAustralianLiteraryAwardsWikipediaParser(
      self.CATEGORY, self.CATEGORY_ALIASES)

  def source_attempts(self):
    return (
      SourceAttempt(
        'State Library of South Australia',
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


class UrlFetcherSouthAustralianLiteraryAwardsPremiersAward(
    UrlFetcherSouthAustralianLiteraryAwards):

  FILTER_CATEGORIES = (CATEGORY_REGIONAL_NATIONAL_AWARDS,)
  source_id = 'south_australian_literary_awards_premiers_award'
  NAME = "South Australian Literary Awards - Premier's Award"
  CATEGORY = "Premier's Award"
  CATEGORY_ALIASES = (
    "Premier's Award",
    "Premier’s Award",
    "Premier's Award for Overall Published Work",
    "Premier’s Award for Overall Published Work",
    "Premier's Award for the Best Overall Published Work",
    "Premier’s Award for the Best Overall Published Work",
  )


class UrlFetcherSouthAustralianLiteraryAwardsFiction(
    UrlFetcherSouthAustralianLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'south_australian_literary_awards_fiction'
  NAME = 'South Australian Literary Awards - Fiction'
  CATEGORY = 'Fiction'
  CATEGORY_ALIASES = (
    'Fiction Award',
    'Fiction',
  )


class UrlFetcherSouthAustralianLiteraryAwardsNonfiction(
    UrlFetcherSouthAustralianLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'south_australian_literary_awards_nonfiction'
  NAME = 'South Australian Literary Awards - Non-Fiction'
  CATEGORY = 'Non-Fiction'
  CATEGORY_ALIASES = (
    'Non-Fiction Award',
    'Nonfiction Award',
    'Non-Fiction',
    'Nonfiction',
  )


class UrlFetcherSouthAustralianLiteraryAwardsChildrens(
    UrlFetcherSouthAustralianLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'south_australian_literary_awards_childrens'
  NAME = "South Australian Literary Awards - Children's Literature"
  CATEGORY = "Children's Literature"
  CATEGORY_ALIASES = (
    "Children's Literature Award",
    "Children’s Literature Award",
    "Children's Literature",
    "Children’s Literature",
  )


class UrlFetcherSouthAustralianLiteraryAwardsYoungAdult(
    UrlFetcherSouthAustralianLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'south_australian_literary_awards_young_adult'
  NAME = 'South Australian Literary Awards - Young Adult Fiction'
  CATEGORY = 'Young Adult Fiction'
  CATEGORY_ALIASES = (
    'Young Adult Fiction Award',
    'Young Adult Fiction',
    'Young Adult Award',
    'Young Adult',
  )
