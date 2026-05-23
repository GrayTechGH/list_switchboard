#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_CRIME_MYSTERY_THRILLER, UrlFetcherError, UrlFetcherGeneric

try:
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
except ImportError:
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner


class UrlFetcherTheakstonOldPeculierCrimeNovelOfTheYear(UrlFetcherGeneric):

  FILTER_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER,)
  FETCH_URLS = ()
  order = 237
  options = {'match_series': False}
  URL = 'https://www.librarything.com/award/2016/Theakston-Old-Peculier-Crime-Novel-of-the-Year'
  WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Theakston_Old_Peculier_Crime_Novel_of_the_Year_Award'
  source_id = 'theakston_old_peculier_crime_novel_of_the_year'
  NAME = 'Theakston Old Peculier Crime Novel of the Year'
  CATEGORY = 'Theakston Old Peculier Crime Novel of the Year'
  CATEGORY_ALIASES = ('Crime Novel of the Year',)

  def source_attempts(self):
    try:
      from calibre_plugins.list_switchboard.parser.theakston import (
        TheakstonLibraryThingParser,
        TheakstonWikipediaParser,
      )
    except ImportError:
      from parser.theakston import TheakstonLibraryThingParser, TheakstonWikipediaParser
    return (
      SourceAttempt(
        'LibraryThing',
        self.URL,
        lambda html, url, **_kwargs: TheakstonLibraryThingParser().parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES),
        source_rank=0),
      SourceAttempt(
        'Wikipedia',
        self.WIKIPEDIA_URL,
        lambda html, url, **_kwargs: TheakstonWikipediaParser().parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES,
          allowed_results=('winner', 'shortlisted')),
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
