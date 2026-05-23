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


BARRY_URL = 'https://www.stopyourekillingme.com/Awards/Barry_Awards.html'
LIBRARYTHING_BARRY_URL = 'https://www.librarything.com/award/467/Barry-Award'
BARRY_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER,)


class UrlFetcherBarryAward(LibraryThingAwardFallbackMixin, UrlFetcherGeneric):

  FILTER_CATEGORIES = BARRY_CATEGORIES
  FETCH_URLS = ()
  order = 227
  options = {
    'match_series': False,
  }
  URL = BARRY_URL
  AWARD_NAME = 'Barry Award'
  LIBRARYTHING_AWARD_NAME = AWARD_NAME
  LIBRARYTHING_URL = LIBRARYTHING_BARRY_URL
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.barry import BarryAwardsParser
    except ImportError:
      from parser.barry import BarryAwardsParser

    return BarryAwardsParser()

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


class UrlFetcherBarryMysteryNovel(UrlFetcherBarryAward):
  source_id = 'barry_award_mystery_novel'
  NAME = 'Barry Award - Mystery Novel'
  CATEGORY = 'Best Mystery Novel'
  CATEGORY_ALIASES = (
    'Best Mystery',
    'Best Mystery/Crime Novel',
    'Best Novel',
    'Novel',
  )


class UrlFetcherBarryFirstMysteryNovel(UrlFetcherBarryAward):
  source_id = 'barry_award_first_mystery_novel'
  NAME = 'Barry Award - First Mystery Novel'
  CATEGORY = 'Best First Mystery Novel'
  CATEGORY_ALIASES = (
    'Best First Mystery',
    'Best First Mystery/Crime Novel',
    'Best First Novel',
    'First Mystery',
    'First Mystery Novel',
    'First Novel',
  )


class UrlFetcherBarryPaperbackOriginal(UrlFetcherBarryAward):
  source_id = 'barry_award_paperback_original'
  NAME = 'Barry Award - Paperback Original'
  CATEGORY = 'Best Paperback Original Mystery Novel'
  CATEGORY_ALIASES = (
    'Best Paperback Original',
    'Best Paperback Original Mystery',
    'Best Paperback Original Mystery/Crime Novel',
    'Paperback Original',
  )


class UrlFetcherBarryThriller(UrlFetcherBarryAward):
  source_id = 'barry_award_thriller'
  NAME = 'Barry Award - Thriller'
  CATEGORY = 'Best Thriller'
  CATEGORY_ALIASES = (
    'Best Action Thriller',
    'Thriller',
  )


class UrlFetcherBarryBritishCrimeNovel(UrlFetcherBarryAward):
  source_id = 'barry_award_british_crime_novel'
  NAME = 'Barry Award - British Crime Novel'
  CATEGORY = 'Best British Crime Novel'
  CATEGORY_ALIASES = (
    'Best British Novel',
    'British Crime Novel',
    'British Novel',
  )
