#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_CRIME_MYSTERY_THRILLER,
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


ITW_URL = 'https://thrillerwriters.org/past-nominees-and-winners'
LIBRARYTHING_ITW_URL = 'https://www.librarything.com/bookaward/Thriller%2BAward'
ITW_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER,)
ITW_YA_CATEGORIES = (
  CATEGORY_CRIME_MYSTERY_THRILLER,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
)


class UrlFetcherITWThrillerAward(LibraryThingAwardFallbackMixin, UrlFetcherGeneric):

  FILTER_CATEGORIES = ITW_CATEGORIES
  FETCH_URLS = ()
  order = 222
  options = {
    'match_series': False,
  }
  URL = ITW_URL
  AWARD_NAME = 'ITW Thriller Award'
  LIBRARYTHING_AWARD_NAME = 'International Thriller Writers Award'
  LIBRARYTHING_URL = LIBRARYTHING_ITW_URL
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.itw import ITWThrillerAwardsParser
    except ImportError:
      from parser.itw import ITWThrillerAwardsParser

    return ITWThrillerAwardsParser()

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
        'Official ITW',
        self.URL,
        lambda html, url, **_kwargs: official_parser.parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES),
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
      self.CATEGORY_ALIASES)


class UrlFetcherITWBestStandaloneThrillerNovel(UrlFetcherITWThrillerAward):
  source_id = 'itw_thriller_award_standalone_thriller_novel'
  NAME = 'ITW Thriller Award - Standalone Thriller Novel'
  CATEGORY = 'Best Standalone Thriller Novel'
  CATEGORY_ALIASES = (
    'standalone thriller novel',
    'standalone thriller',
    'best standalone thriller',
  )


class UrlFetcherITWBestStandaloneMysteryNovel(UrlFetcherITWThrillerAward):
  source_id = 'itw_thriller_award_standalone_mystery_novel'
  NAME = 'ITW Thriller Award - Standalone Mystery Novel'
  CATEGORY = 'Best Standalone Mystery Novel'
  CATEGORY_ALIASES = (
    'standalone mystery novel',
    'standalone mystery',
    'best standalone mystery',
  )


class UrlFetcherITWBestSeriesNovel(UrlFetcherITWThrillerAward):
  source_id = 'itw_thriller_award_series_novel'
  NAME = 'ITW Thriller Award - Series Novel'
  CATEGORY = 'Best Series Novel'
  CATEGORY_ALIASES = ('series novel', 'best series')


class UrlFetcherITWBestFirstNovel(UrlFetcherITWThrillerAward):
  source_id = 'itw_thriller_award_first_novel'
  NAME = 'ITW Thriller Award - First Novel'
  CATEGORY = 'Best First Novel'
  CATEGORY_ALIASES = ('first novel',)


class UrlFetcherITWBestYoungAdultNovel(UrlFetcherITWThrillerAward):
  source_id = 'itw_thriller_award_young_adult_novel'
  NAME = 'ITW Thriller Award - Young Adult Novel'
  FILTER_CATEGORIES = ITW_YA_CATEGORIES
  CATEGORY = 'Best Young Adult Novel'
  CATEGORY_ALIASES = ('young adult novel', 'young adult')


class UrlFetcherITWBestHardcoverNovel(UrlFetcherITWThrillerAward):
  source_id = 'itw_thriller_award_hardcover_novel'
  NAME = 'ITW Thriller Award - Hardcover Novel'
  CATEGORY = 'Best Hardcover Novel'
  CATEGORY_ALIASES = (
    'hardcover novel',
    'hard cover novel',
    'best hard cover novel',
    'best novel',
    'novel',
    'best thriller of the year',
    'thriller of the year',
  )


class UrlFetcherITWBestPaperbackOriginalNovel(UrlFetcherITWThrillerAward):
  source_id = 'itw_thriller_award_paperback_original_novel'
  NAME = 'ITW Thriller Award - Paperback Original Novel'
  CATEGORY = 'Best Paperback Original Novel'
  CATEGORY_ALIASES = (
    'paperback original novel',
    'paperback original',
    'original paperback novel',
    'original paperback',
    'best original paperback novel',
  )


class UrlFetcherITWBestEBookOriginalNovel(UrlFetcherITWThrillerAward):
  source_id = 'itw_thriller_award_e_book_original_novel'
  NAME = 'ITW Thriller Award - E-Book Original Novel'
  CATEGORY = 'Best E-Book Original Novel'
  CATEGORY_ALIASES = (
    'e-book original novel',
    'ebook original novel',
    'e-book original',
    'ebook original',
  )


class UrlFetcherITWBestAudiobook(UrlFetcherITWThrillerAward):
  source_id = 'itw_thriller_award_audiobook'
  NAME = 'ITW Thriller Award - Audiobook'
  CATEGORY = 'Best Audiobook'
  CATEGORY_ALIASES = ('audiobook',)
