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


OFFICIAL_URL = 'https://creative.gov.au/news-events/events/prime-ministers-literary-awards'
WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Prime_Minister%27s_Literary_Awards'


class UrlFetcherPrimeMinistersLiteraryAwards(UrlFetcherGeneric):

  URL = OFFICIAL_URL
  WIKIPEDIA_URL = WIKIPEDIA_URL
  FETCH_URLS = ()
  order = 240
  options = {'match_series': False}
  AWARD_NAME = "Prime Minister's Literary Awards"
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_official_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.prime_ministers_literary_awards import (
        PrimeMinistersLiteraryAwardsOfficialParser,
      )
    except ImportError:
      from parser.prime_ministers_literary_awards import (
        PrimeMinistersLiteraryAwardsOfficialParser,
      )
    return PrimeMinistersLiteraryAwardsOfficialParser(
      self.CATEGORY, self.CATEGORY_ALIASES)

  def create_wikipedia_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.prime_ministers_literary_awards import (
        PrimeMinistersLiteraryAwardsWikipediaParser,
      )
    except ImportError:
      from parser.prime_ministers_literary_awards import (
        PrimeMinistersLiteraryAwardsWikipediaParser,
      )
    return PrimeMinistersLiteraryAwardsWikipediaParser(
      self.CATEGORY, self.CATEGORY_ALIASES)

  def source_attempts(self):
    return (
      SourceAttempt(
        'Creative Australia',
        self.URL,
        lambda html, url, fetch_url=None, log=None, progress=None: (
          self.create_official_parser().parse(
            html, url, self.NAME, fetch_url=fetch_url, log=log, progress=progress)),
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

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.create_official_parser().parse(
      html, self.URL, self.NAME, fetch_url=fetch_url, log=log, progress=progress)


class UrlFetcherPrimeMinistersLiteraryAwardsFiction(
    UrlFetcherPrimeMinistersLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'prime_ministers_literary_awards_fiction'
  NAME = "Prime Minister's Literary Awards - Fiction"
  CATEGORY = 'Fiction'
  CATEGORY_ALIASES = ('Fiction',)


class UrlFetcherPrimeMinistersLiteraryAwardsNonfiction(
    UrlFetcherPrimeMinistersLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'prime_ministers_literary_awards_nonfiction'
  NAME = "Prime Minister's Literary Awards - Non-fiction"
  CATEGORY = 'Non-fiction'
  CATEGORY_ALIASES = ('Non-fiction', 'Nonfiction')


class UrlFetcherPrimeMinistersLiteraryAwardsAustralianHistory(
    UrlFetcherPrimeMinistersLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'prime_ministers_literary_awards_australian_history'
  NAME = "Prime Minister's Literary Awards - Australian History"
  CATEGORY = 'Australian History'
  CATEGORY_ALIASES = ('Australian History',)


class UrlFetcherPrimeMinistersLiteraryAwardsYoungAdultLiterature(
    UrlFetcherPrimeMinistersLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'prime_ministers_literary_awards_young_adult_literature'
  NAME = "Prime Minister's Literary Awards - Young Adult Literature"
  CATEGORY = 'Young Adult Literature'
  CATEGORY_ALIASES = (
    'Young Adult Literature',
    'Young adult literature',
    'Young adult fiction',
    'Young adult',
  )


class UrlFetcherPrimeMinistersLiteraryAwardsChildrensLiterature(
    UrlFetcherPrimeMinistersLiteraryAwards):

  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'prime_ministers_literary_awards_childrens_literature'
  NAME = "Prime Minister's Literary Awards - Children's Literature"
  CATEGORY = "Children's Literature"
  CATEGORY_ALIASES = (
    "Children's Literature",
    "Children's literature",
    "Children's fiction",
    "Children's Fiction",
  )
