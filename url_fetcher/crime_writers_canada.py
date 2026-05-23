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


CWC_URL = 'https://www.librarything.com/award/1612/Crime-Writers-of-Canada-Awards-of-Excellence'
CWC_WIKI_URL = 'https://en.wikipedia.org/wiki/Crime_Writers_of_Canada_Awards_of_Excellence'
CWC_BEST_NOVEL_WIKI_URL = 'https://en.wikipedia.org/wiki/Crime_Writers_of_Canada_Award_for_Best_Novel'
CWC_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER,)
CWC_NONFICTION_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER, CATEGORY_NONFICTION)
CWC_YA_CATEGORIES = (
  CATEGORY_CRIME_MYSTERY_THRILLER,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
)


class UrlFetcherCrimeWritersOfCanadaAward(UrlFetcherGeneric):

  FILTER_CATEGORIES = CWC_CATEGORIES
  FETCH_URLS = ()
  order = 231
  options = {'match_series': False}
  URL = CWC_URL
  WIKIPEDIA_URL = CWC_WIKI_URL
  AWARD_NAME = 'Crime Writers of Canada Award'
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_librarything_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.crime_writers_canada import (
        CrimeWritersOfCanadaLibraryThingParser,
      )
    except ImportError:
      from parser.crime_writers_canada import CrimeWritersOfCanadaLibraryThingParser
    return CrimeWritersOfCanadaLibraryThingParser()

  def create_wikipedia_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.crime_writers_canada import (
        CrimeWritersOfCanadaWikipediaParser,
      )
    except ImportError:
      from parser.crime_writers_canada import CrimeWritersOfCanadaWikipediaParser
    return CrimeWritersOfCanadaWikipediaParser()

  def source_attempts(self):
    return (
      SourceAttempt(
        'LibraryThing',
        self.URL,
        lambda html, url, **_kwargs: self.create_librarything_parser().parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES),
        source_rank=0),
      SourceAttempt(
        'Wikipedia',
        self.WIKIPEDIA_URL,
        lambda html, url, **_kwargs: self.create_wikipedia_parser().parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES),
        source_rank=1),
    )

  def source_choices(self):
    return SourceFallbackRunner(self.source_attempts()).source_choices()

  def fetch_and_parse(self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
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
    parsed.setdefault('match_series', False)
    return parsed


class UrlFetcherCrimeWritersOfCanadaNovel(UrlFetcherCrimeWritersOfCanadaAward):
  source_id = 'crime_writers_of_canada_award_novel'
  NAME = 'Crime Writers of Canada Award - Novel'
  WIKIPEDIA_URL = CWC_BEST_NOVEL_WIKI_URL
  CATEGORY = 'Novel'
  CATEGORY_ALIASES = ('Best Novel',)


class UrlFetcherCrimeWritersOfCanadaFirstNovel(UrlFetcherCrimeWritersOfCanadaAward):
  source_id = 'crime_writers_of_canada_award_first_novel'
  NAME = 'Crime Writers of Canada Award - First Novel'
  CATEGORY = 'First Novel'
  CATEGORY_ALIASES = ('Best First Novel',)


class UrlFetcherCrimeWritersOfCanadaNonfiction(UrlFetcherCrimeWritersOfCanadaAward):
  source_id = 'crime_writers_of_canada_award_nonfiction'
  NAME = 'Crime Writers of Canada Award - Nonfiction'
  FILTER_CATEGORIES = CWC_NONFICTION_CATEGORIES
  CATEGORY = 'True Crime'
  CATEGORY_ALIASES = ('Nonfiction', 'Non-Fiction', 'Best Nonfiction Crime Book')


class UrlFetcherCrimeWritersOfCanadaJuvenileYA(UrlFetcherCrimeWritersOfCanadaAward):
  source_id = 'crime_writers_of_canada_award_juvenile_young_adult'
  NAME = 'Crime Writers of Canada Award - Juvenile/Young Adult'
  FILTER_CATEGORIES = CWC_YA_CATEGORIES
  CATEGORY = 'Juvenile or Young Adult'
  CATEGORY_ALIASES = ('Juvenile/Young Adult', 'Young Adult', 'Best Juvenile or Young Adult')


class UrlFetcherCrimeWritersOfCanadaFrenchCrimeBook(UrlFetcherCrimeWritersOfCanadaAward):
  source_id = 'crime_writers_of_canada_award_french_language_crime_book'
  NAME = 'Crime Writers of Canada Award - French Language Crime Book'
  CATEGORY = 'French Crime Book'
  CATEGORY_ALIASES = ('French Language Crime Book', 'Best French Crime Book')
