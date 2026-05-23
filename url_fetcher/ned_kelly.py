#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_CRIME_MYSTERY_THRILLER, CATEGORY_NONFICTION, UrlFetcherError, UrlFetcherGeneric

try:
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
except ImportError:
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner


NED_KELLY_URL = 'https://www.librarything.com/award/2492/Ned-Kelly-Award'
NED_KELLY_WIKI_URL = 'https://en.wikipedia.org/wiki/Ned_Kelly_Awards'


class UrlFetcherNedKellyAward(UrlFetcherGeneric):

  FILTER_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER,)
  FETCH_URLS = ()
  order = 235
  options = {'match_series': False}
  URL = NED_KELLY_URL
  WIKIPEDIA_URL = NED_KELLY_WIKI_URL
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def source_attempts(self):
    try:
      from calibre_plugins.list_switchboard.parser.ned_kelly import (
        NedKellyLibraryThingParser,
        NedKellyWikipediaParser,
      )
    except ImportError:
      from parser.ned_kelly import NedKellyLibraryThingParser, NedKellyWikipediaParser
    return (
      SourceAttempt(
        'LibraryThing',
        self.URL,
        lambda html, url, **_kwargs: NedKellyLibraryThingParser().parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES),
        source_rank=0),
      SourceAttempt(
        'Wikipedia',
        self.WIKIPEDIA_URL,
        lambda html, url, **_kwargs: NedKellyWikipediaParser().parse(
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


class UrlFetcherNedKellyCrimeFiction(UrlFetcherNedKellyAward):
  source_id = 'ned_kelly_award_crime_fiction'
  NAME = 'Ned Kelly Award - Crime Fiction'
  CATEGORY = 'Best Crime Novel'
  CATEGORY_ALIASES = ('Crime Fiction', 'Best Novel')


class UrlFetcherNedKellyDebutCrimeFiction(UrlFetcherNedKellyAward):
  source_id = 'ned_kelly_award_debut_crime_fiction'
  NAME = 'Ned Kelly Award - Debut Crime Fiction'
  CATEGORY = 'Best Debut Crime Novel'
  CATEGORY_ALIASES = ('Best First Novel', 'Debut Crime Fiction', 'First Novel')


class UrlFetcherNedKellyTrueCrime(UrlFetcherNedKellyAward):
  source_id = 'ned_kelly_award_true_crime'
  NAME = 'Ned Kelly Award - True Crime'
  FILTER_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER, CATEGORY_NONFICTION)
  CATEGORY = 'Best True Crime'
  CATEGORY_ALIASES = ('True Crime',)


class UrlFetcherNedKellyInternationalCrimeFiction(UrlFetcherNedKellyAward):
  source_id = 'ned_kelly_award_international_crime_fiction'
  NAME = 'Ned Kelly Award - International Crime Fiction'
  CATEGORY = 'Best International Crime Novel'
  CATEGORY_ALIASES = ('Best International Crime', 'International Crime Fiction')
