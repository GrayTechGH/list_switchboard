#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_CRIME_MYSTERY_THRILLER, UrlFetcherError, UrlFetcherGeneric

try:
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
except ImportError:
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner


class UrlFetcherDilysAward(UrlFetcherGeneric):

  FILTER_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER,)
  FETCH_URLS = ()
  order = 233
  options = {'match_series': False}
  URL = 'https://www.librarything.com/award/593/Dilys-Award'
  WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Dilys_Award'
  source_id = 'dilys_award'
  NAME = 'Dilys Award'
  CATEGORY = 'Dilys Award'
  CATEGORY_ALIASES = ()

  def source_attempts(self):
    try:
      from calibre_plugins.list_switchboard.parser.dilys import (
        DilysLibraryThingParser,
        DilysWikipediaParser,
      )
    except ImportError:
      from parser.dilys import DilysLibraryThingParser, DilysWikipediaParser
    return (
      SourceAttempt(
        'LibraryThing',
        self.URL,
        lambda html, url, **_kwargs: DilysLibraryThingParser().parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES),
        source_rank=0),
      SourceAttempt(
        'Wikipedia',
        self.WIKIPEDIA_URL,
        lambda html, url, **_kwargs: DilysWikipediaParser().parse(
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
