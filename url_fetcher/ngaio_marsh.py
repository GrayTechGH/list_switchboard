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
except ImportError:
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner


NGAIO_URL = 'https://www.librarything.com/award/5348.0.2427/Ngaio-Marsh-Award-First-Novel'
NGAIO_WIKI_URL = 'https://en.wikipedia.org/wiki/Ngaio_Marsh_Awards'


class UrlFetcherNgaioMarshAward(UrlFetcherGeneric):

  FILTER_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER,)
  FETCH_URLS = ()
  order = 236
  options = {'match_series': False}
  URL = NGAIO_URL
  WIKIPEDIA_URL = NGAIO_WIKI_URL
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def source_attempts(self):
    try:
      from calibre_plugins.list_switchboard.parser.ngaio_marsh import (
        NgaioMarshLibraryThingParser,
        NgaioMarshWikipediaParser,
      )
    except ImportError:
      from parser.ngaio_marsh import NgaioMarshLibraryThingParser, NgaioMarshWikipediaParser
    return (
      SourceAttempt(
        'LibraryThing',
        self.URL,
        lambda html, url, **_kwargs: NgaioMarshLibraryThingParser().parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES),
        source_rank=0),
      SourceAttempt(
        'Wikipedia',
        self.WIKIPEDIA_URL,
        lambda html, url, **_kwargs: NgaioMarshWikipediaParser().parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES),
        source_rank=1),
    )

  def source_choices(self):
    return SourceFallbackRunner(self.source_attempts()).source_choices()

  def fetch_and_parse(self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
                      before_fetch=None, after_fetch=None, before_parse=None,
                      force_fallback_level=0, disable_fallbacks=False, source_choice=None):
    parsed = SourceFallbackRunner(self.source_attempts(), error_class=UrlFetcherError).run(
      fetch_url,
      log=log,
      progress=progress,
      before_fetch=before_fetch,
      after_fetch=after_fetch,
      before_parse=before_parse,
      force_fallback_level=force_fallback_level,
      disable_fallbacks=disable_fallbacks,
      source_choice=source_choice)
    parsed.setdefault('match_series', False)
    return parsed


class UrlFetcherNgaioMarshCrimeNovel(UrlFetcherNgaioMarshAward):
  source_id = 'ngaio_marsh_award_crime_novel'
  NAME = 'Ngaio Marsh Award - Crime Novel'
  CATEGORY = 'Crime Novel'
  CATEGORY_ALIASES = ('Novel',)


class UrlFetcherNgaioMarshFirstNovel(UrlFetcherNgaioMarshAward):
  source_id = 'ngaio_marsh_award_first_novel'
  NAME = 'Ngaio Marsh Award - First Novel'
  CATEGORY = 'First Novel'
  CATEGORY_ALIASES = ()


class UrlFetcherNgaioMarshNonFiction(UrlFetcherNgaioMarshAward):
  source_id = 'ngaio_marsh_award_non_fiction'
  NAME = 'Ngaio Marsh Award - Non-Fiction'
  FILTER_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER, CATEGORY_NONFICTION)
  CATEGORY = 'Non Fiction'
  CATEGORY_ALIASES = ('Non-Fiction',)


class UrlFetcherNgaioMarshYoungerReaders(UrlFetcherNgaioMarshAward):
  source_id = 'ngaio_marsh_award_younger_readers'
  NAME = 'Ngaio Marsh Award - Younger Readers'
  FILTER_CATEGORIES = (
    CATEGORY_CRIME_MYSTERY_THRILLER,
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  )
  CATEGORY = 'Younger Readers'
  CATEGORY_ALIASES = ('Kids / YA',)
