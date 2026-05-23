#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_CRIME_MYSTERY_THRILLER,
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


LEFTY_URL = 'https://www.stopyourekillingme.com/Awards/Lefty_Awards.html'
LIBRARYTHING_LEFTY_URL = 'https://www.librarything.com/award/2357/Lefty-Award'
LEFTY_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER,)


class UrlFetcherLeftyAward(LibraryThingAwardFallbackMixin, UrlFetcherGeneric):

  FILTER_CATEGORIES = LEFTY_CATEGORIES
  FETCH_URLS = ()
  order = 228
  options = {
    'match_series': False,
  }
  URL = LEFTY_URL
  AWARD_NAME = 'Lefty Award'
  LIBRARYTHING_AWARD_NAME = AWARD_NAME
  LIBRARYTHING_URL = LIBRARYTHING_LEFTY_URL
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.lefty import LeftyAwardsParser
    except ImportError:
      from parser.lefty import LeftyAwardsParser

    return LeftyAwardsParser()

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
    sykm_parser = self.parser()
    return (
      SourceAttempt(
        "Stop, You're Killing Me",
        self.URL,
        lambda html, url, **_kwargs: sykm_parser.parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES,
          award_name=self.AWARD_NAME),
        source_rank=0),
      self.librarything_attempt(source_rank=1),
    )

  def source_choices(self):
    return SourceFallbackRunner(self.source_attempts()).source_choices()

  def parse(self, html, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES,
      award_name=self.AWARD_NAME)


class UrlFetcherLeftyHumorousMysteryNovel(UrlFetcherLeftyAward):
  source_id = 'lefty_award_humorous_mystery_novel'
  NAME = 'Lefty Award - Humorous Mystery Novel'
  CATEGORY = 'Best Humorous Mystery Novel'
  CATEGORY_ALIASES = (
    'Lefty for Best Humorous Mystery Novel',
    'Humorous Mystery Novel',
  )


class UrlFetcherLeftyHistoricalMysteryNovel(UrlFetcherLeftyAward):
  source_id = 'lefty_award_historical_mystery_novel'
  NAME = 'Lefty Award - Historical Mystery Novel'
  CATEGORY = 'Best Historical Mystery Novel'
  CATEGORY_ALIASES = (
    'Lefty for Best Historical Mystery Novel',
    'Historical Mystery Novel',
  )


class UrlFetcherLeftyMysteryNovel(UrlFetcherLeftyAward):
  source_id = 'lefty_award_mystery_novel'
  NAME = 'Lefty Award - Mystery Novel'
  CATEGORY = 'Best Mystery Novel'
  CATEGORY_ALIASES = (
    'Lefty for Best Mystery Novel',
    'Mystery Novel',
  )


class UrlFetcherLeftyDebutMysteryNovel(UrlFetcherLeftyAward):
  source_id = 'lefty_award_debut_mystery_novel'
  NAME = 'Lefty Award - Debut Mystery Novel'
  CATEGORY = 'Best Debut Mystery Novel'
  CATEGORY_ALIASES = (
    'Lefty for Best Debut Mystery Novel',
    'Debut Mystery',
    'Debut Mystery Novel',
  )
