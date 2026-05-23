#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_CRIME_MYSTERY_THRILLER,
  CATEGORY_NONFICTION,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherGeneric,
  UrlFetcherError,
)

AGATHA_URL = 'https://www.stopyourekillingme.com/Awards/Agatha_Awards.html'
AGATHA_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER,)
AGATHA_NONFICTION_CATEGORIES = (
  CATEGORY_CRIME_MYSTERY_THRILLER,
  CATEGORY_NONFICTION,
)
AGATHA_YA_CATEGORIES = (
  CATEGORY_CRIME_MYSTERY_THRILLER,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
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


class UrlFetcherAgathaAward(LibraryThingAwardFallbackMixin, UrlFetcherGeneric):

  FILTER_CATEGORIES = AGATHA_CATEGORIES
  FETCH_URLS = ()
  order = 224
  options = {
    'match_series': False,
  }
  URL = AGATHA_URL
  AWARD_NAME = 'Agatha Award'
  LIBRARYTHING_AWARD_NAME = AWARD_NAME
  LIBRARYTHING_URL = 'https://www.librarything.com/award/1390/Agatha-Award'
  CATEGORY = ''
  CATEGORY_ALIASES = ()

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

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.agatha import (
        AgathaAwardsParser,
      )
    except ImportError:
      from parser.agatha import AgathaAwardsParser

    return AgathaAwardsParser()

  def parse(self, html, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES,
      award_name=self.AWARD_NAME)


class UrlFetcherAgathaBestNovel(UrlFetcherAgathaAward):
  source_id = 'agatha_award_best_novel'
  NAME = 'Agatha Award - Contemporary Novel'
  CATEGORY = 'Best Contemporary Novel'
  CATEGORY_ALIASES = (
    'Contemporary Novel',
    'Best Novel',
    'Best Mystery Novel',
    'Novel',
  )


class UrlFetcherAgathaFirstNovel(UrlFetcherAgathaAward):
  source_id = 'agatha_award_first_novel'
  NAME = 'Agatha Award - Best First Novel'
  CATEGORY = 'Best First Novel'
  CATEGORY_ALIASES = (
    'First Novel',
  )


class UrlFetcherAgathaHistoricalNovel(UrlFetcherAgathaAward):
  source_id = 'agatha_award_historical_novel'
  NAME = 'Agatha Award - Historical Novel'
  CATEGORY = 'Best Historical Novel'
  CATEGORY_ALIASES = (
    'Historical Novel',
  )


class UrlFetcherAgathaNonFiction(UrlFetcherAgathaAward):
  source_id = 'agatha_award_non_fiction'
  NAME = 'Agatha Award - Non-Fiction'
  FILTER_CATEGORIES = AGATHA_NONFICTION_CATEGORIES
  CATEGORY = 'Best Non-Fiction'
  CATEGORY_ALIASES = (
    'Best Non-fiction',
    'Best Nonfiction',
    'Non-Fiction',
    'Non-fiction',
    'Nonfiction',
  )


class UrlFetcherAgathaChildrensYA(UrlFetcherAgathaAward):
  source_id = 'agatha_award_childrens_ya'
  NAME = 'Agatha Award - Children\'s/YA'
  FILTER_CATEGORIES = AGATHA_YA_CATEGORIES
  CATEGORY = 'Best Children\'s/YA'
  CATEGORY_ALIASES = (
    'Best Children\'s/YA Novel',
    'Best Children’s/YA',
    'Best Children’s/YA Novel',
    'Best Children\'s/Young Adult',
    'Best Children’s/Young Adult',
    'Best Children\'s/Young Adult Novel',
    'Best Children’s/Young Adult Novel',
    'Best Children\'s/Young Adult Mystery',
    'Best Children’s/Young Adult Mystery',
    'Children\'s / YA',
    'Children’s / YA',
    'Children\'s/YA',
    'Children’s/YA',
  )
