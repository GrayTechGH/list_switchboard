#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_CRIME_MYSTERY_THRILLER,
  CATEGORY_NONFICTION,
  UrlFetcherError,
  UrlFetcherGeneric,
)

try:
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
  from calibre_plugins.list_switchboard.url_fetcher.librarything_fallback import (
    LibraryThingAwardFallbackMixin,
  )
except ImportError:
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner
  from url_fetcher.librarything_fallback import LibraryThingAwardFallbackMixin


MACAVITY_URL = 'https://mysteryreaders.org/macavity-awards/'
MACAVITY_SYKM_URL = 'https://www.stopyourekillingme.com/Awards/Macavity_Awards.html'
LIBRARYTHING_MACAVITY_URL = 'https://www.librarything.com/award/681/Macavity-Award'
MACAVITY_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER,)
MACAVITY_NONFICTION_CATEGORIES = (
  CATEGORY_CRIME_MYSTERY_THRILLER,
  CATEGORY_NONFICTION,
)


class UrlFetcherMacavityAward(LibraryThingAwardFallbackMixin, UrlFetcherGeneric):

  FILTER_CATEGORIES = MACAVITY_CATEGORIES
  FETCH_URLS = ()
  order = 225
  options = {
    'match_series': False,
  }
  URL = MACAVITY_URL
  AWARD_NAME = 'Macavity Award'
  LIBRARYTHING_AWARD_NAME = AWARD_NAME
  LIBRARYTHING_URL = LIBRARYTHING_MACAVITY_URL
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_sykm_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.stopyourekillingme_base import (
        StopYoureKillingMeAwardParserBase,
      )
    except ImportError:
      from parser.stopyourekillingme_base import StopYoureKillingMeAwardParserBase

    return StopYoureKillingMeAwardParserBase()

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.macavity import (
        MacavityAwardsParser,
      )
    except ImportError:
      from parser.macavity import MacavityAwardsParser

    return MacavityAwardsParser()

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
    official_parser = self.parser()
    return (
      SourceAttempt(
        'Official Macavity',
        self.URL,
        lambda html, url, **_kwargs: official_parser.parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES),
        source_rank=0),
      SourceAttempt(
        "Stop, You're Killing Me",
        MACAVITY_SYKM_URL,
        lambda html, url, **_kwargs: self.create_sykm_parser().parse(
          html,
          url,
          self.NAME,
          self.CATEGORY,
          self.CATEGORY_ALIASES,
          award_name=self.AWARD_NAME),
        source_rank=1),
      self.librarything_attempt(source_rank=2),
    )

  def source_choices(self):
    return SourceFallbackRunner(self.source_attempts()).source_choices()

  def parse(self, html, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES)


class UrlFetcherMacavityMysteryNovel(UrlFetcherMacavityAward):
  source_id = 'macavity_award_mystery_novel'
  NAME = 'Macavity Award - Mystery Novel'
  CATEGORY = 'Best Mystery Novel'
  CATEGORY_ALIASES = (
    'Best Mystery',
    'Best Novel',
    'Mystery Novel',
    'Novel',
  )


class UrlFetcherMacavityFirstMystery(UrlFetcherMacavityAward):
  source_id = 'macavity_award_first_mystery'
  NAME = 'Macavity Award - First Mystery'
  CATEGORY = 'Best First Mystery'
  CATEGORY_ALIASES = (
    'Best First Mystery Novel',
    'Best First Novel',
    'First Mystery',
    'First Mystery Novel',
    'First Novel',
  )


class UrlFetcherMacavityHistoricalMystery(UrlFetcherMacavityAward):
  source_id = 'macavity_award_historical_mystery'
  NAME = 'Macavity Award - Historical Mystery'
  CATEGORY = 'Sue Feder Memorial Award for Best Historical Mystery'
  CATEGORY_ALIASES = (
    'Sue Feder Memorial Award for Best Historical Novel',
    'Sue Feder Historical Mystery Award',
    'Best Historical Mystery',
    'Best Historical Novel',
    'Historical Mystery',
  )


class UrlFetcherMacavityNonfictionCritical(UrlFetcherMacavityAward):
  source_id = 'macavity_award_nonfiction_critical'
  NAME = 'Macavity Award - Nonfiction/Critical'
  FILTER_CATEGORIES = MACAVITY_NONFICTION_CATEGORIES
  CATEGORY = 'Best Nonfiction/Critical'
  CATEGORY_ALIASES = (
    'Best Mystery-related Nonfiction/Critical',
    'Best Mystery Nonfiction/Critical',
    'Best Mystery-Related Nonfiction',
    'Best Mystery-Related Nonfiction/Critical',
    'Best Nonfiction',
    'Best Non-Fiction',
    'Best Mystery Critical/Biographical',
    'Nonfiction / Critical',
    'Non-Fiction',
    'Nonfiction',
    'Critical / Biographical',
  )
