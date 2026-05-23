#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_CRIME_MYSTERY_THRILLER, UrlFetcherError, UrlFetcherGeneric

try:
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
except ImportError:
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner


GUMSHOE_URL = 'https://www.librarything.com/award/1785/Gumshoe-Award'
GUMSHOE_WIKI_URL = 'https://en.wikipedia.org/wiki/Gumshoe_Awards'


class UrlFetcherGumshoeAward(UrlFetcherGeneric):

  FILTER_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER,)
  FETCH_URLS = ()
  order = 234
  options = {'match_series': False}
  URL = GUMSHOE_URL
  WIKIPEDIA_URL = GUMSHOE_WIKI_URL
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def source_attempts(self):
    try:
      from calibre_plugins.list_switchboard.parser.gumshoe import (
        GumshoeLibraryThingParser,
        GumshoeWikipediaParser,
      )
    except ImportError:
      from parser.gumshoe import GumshoeLibraryThingParser, GumshoeWikipediaParser
    return (
      SourceAttempt(
        'LibraryThing',
        self.URL,
        lambda html, url, **_kwargs: GumshoeLibraryThingParser().parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES),
        source_rank=0),
      SourceAttempt(
        'Wikipedia',
        self.WIKIPEDIA_URL,
        lambda html, url, **_kwargs: GumshoeWikipediaParser().parse(
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


class UrlFetcherGumshoeMystery(UrlFetcherGumshoeAward):
  source_id = 'gumshoe_award_mystery'
  NAME = 'Gumshoe Award - Mystery'
  CATEGORY = 'Mystery'
  CATEGORY_ALIASES = ('Best Mystery', 'Best Novel', 'Novel')


class UrlFetcherGumshoeThriller(UrlFetcherGumshoeAward):
  source_id = 'gumshoe_award_thriller'
  NAME = 'Gumshoe Award - Thriller'
  CATEGORY = 'Thriller'
  CATEGORY_ALIASES = ('Best Thriller',)


class UrlFetcherGumshoeFirstNovel(UrlFetcherGumshoeAward):
  source_id = 'gumshoe_award_first_novel'
  NAME = 'Gumshoe Award - First Novel'
  CATEGORY = 'First Novel'
  CATEGORY_ALIASES = ('Best First Novel',)


class UrlFetcherGumshoeEuropeanCrimeNovel(UrlFetcherGumshoeAward):
  source_id = 'gumshoe_award_european_crime_novel'
  NAME = 'Gumshoe Award - European Crime Novel'
  CATEGORY = 'European Crime Novel'
  CATEGORY_ALIASES = ('Best European Crime Novel',)
