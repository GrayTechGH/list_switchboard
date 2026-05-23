#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_CRIME_MYSTERY_THRILLER,
  CATEGORY_NONFICTION,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
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


ANTHONY_URL = 'https://www.stopyourekillingme.com/Awards/Anthony_Awards.html'
LIBRARYTHING_ANTHONY_URL = 'https://www.librarything.com/award/339/Anthony-Award'
ANTHONY_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER,)
ANTHONY_YA_CATEGORIES = (
  CATEGORY_CRIME_MYSTERY_THRILLER,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
)
ANTHONY_NONFICTION_CATEGORIES = (
  CATEGORY_CRIME_MYSTERY_THRILLER,
  CATEGORY_NONFICTION,
)


class UrlFetcherAnthonyAward(LibraryThingAwardFallbackMixin, UrlFetcherGeneric):

  FILTER_CATEGORIES = ANTHONY_CATEGORIES
  FETCH_URLS = ()
  order = 223
  options = {
    'match_series': False,
  }
  URL = ANTHONY_URL
  AWARD_NAME = 'Anthony Award'
  LIBRARYTHING_AWARD_NAME = AWARD_NAME
  LIBRARYTHING_URL = LIBRARYTHING_ANTHONY_URL
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.anthony import AnthonyAwardsParser
    except ImportError:
      from parser.anthony import AnthonyAwardsParser

    return AnthonyAwardsParser()

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
        'Stop, You\'re Killing Me',
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


class UrlFetcherAnthonyMysteryNovel(UrlFetcherAnthonyAward):
  source_id = 'anthony_award_mystery_novel'
  NAME = 'Anthony Award - Mystery Novel'
  CATEGORY = 'Best Mystery Novel'
  CATEGORY_ALIASES = (
    'Best Hardcover Novel',
    'Best Hardcover Mystery Novel',
    'Novel',
    'Hardcover Novel',
  )


class UrlFetcherAnthonyFirstMystery(UrlFetcherAnthonyAward):
  source_id = 'anthony_award_first_mystery'
  NAME = 'Anthony Award - First Mystery'
  CATEGORY = 'Best First Mystery'
  CATEGORY_ALIASES = (
    'Best First Novel',
    'First Novel',
    'Best First Mystery',
  )


class UrlFetcherAnthonyPaperbackEBookAudiobook(UrlFetcherAnthonyAward):
  source_id = 'anthony_award_paperback_e_book_audiobook'
  NAME = 'Anthony Award - Paperback/E-book/Audiobook'
  CATEGORY = 'Best Paperback/E-book/Audiobook'
  CATEGORY_ALIASES = (
    'Best Paperback Original',
    'Best Paperback Original/E-Book/Audiobook Novel',
    'Paperback Original',
    'Paperback/E-book/Audiobook',
  )


class UrlFetcherAnthonyHistoricalMystery(UrlFetcherAnthonyAward):
  source_id = 'anthony_award_historical_mystery'
  NAME = 'Anthony Award - Historical Mystery'
  CATEGORY = 'Best Historical Mystery'
  CATEGORY_ALIASES = (
    'Best Historical',
    'Best Historical Mystery',
    'Historical',
  )


class UrlFetcherAnthonyCozyHumorousMystery(UrlFetcherAnthonyAward):
  source_id = 'anthony_award_cozy_humorous_mystery'
  NAME = 'Anthony Award - Cozy/Humorous Mystery'
  CATEGORY = 'Best Cozy/Humorous Mystery'
  CATEGORY_ALIASES = (
    'Best Cozy/Humorous',
    'Best Humorous',
    'Cozy/Humorous',
  )


class UrlFetcherAnthonyParanormalMystery(UrlFetcherAnthonyAward):
  source_id = 'anthony_award_paranormal_mystery'
  NAME = 'Anthony Award - Paranormal Mystery'
  CATEGORY = 'Best Paranormal Mystery'
  CATEGORY_ALIASES = (
    'Best Paranormal',
    'Paranormal',
  )


class UrlFetcherAnthonyChildrensYA(UrlFetcherAnthonyAward):
  source_id = 'anthony_award_childrens_ya'
  NAME = 'Anthony Award - Children\'s/YA'
  FILTER_CATEGORIES = ANTHONY_YA_CATEGORIES
  CATEGORY = 'Best Children\'s/YA'
  CATEGORY_ALIASES = (
    'Best Children\'s/YA Novel',
    'Best Children’s/YA Novel',
    'Best Juvenile/Young Adult',
    'Children\'s / YA',
    'Children’s / YA',
  )


class UrlFetcherAnthonyCriticalNonfictionWork(UrlFetcherAnthonyAward):
  source_id = 'anthony_award_critical_nonfiction_work'
  NAME = 'Anthony Award - Critical/Nonfiction Work'
  FILTER_CATEGORIES = ANTHONY_NONFICTION_CATEGORIES
  CATEGORY = 'Best Critical/Nonfiction Work'
  CATEGORY_ALIASES = (
    'Best Critical or Nonfiction Work',
    'Best Critical/Nonfiction Work',
    'Critical/Non-Fiction',
  )


class UrlFetcherAnthonyAnthologyCollection(UrlFetcherAnthonyAward):
  source_id = 'anthony_award_anthology_collection'
  NAME = 'Anthony Award - Anthology/Collection'
  CATEGORY = 'Best Anthology/Collection'
  CATEGORY_ALIASES = (
    'Best Anthology or Collection',
    'Best Anthology',
    'Anthology / Collection',
  )
