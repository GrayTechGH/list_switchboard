#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_CRIME_MYSTERY_THRILLER, UrlFetcherError, UrlFetcherGeneric

try:
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
except ImportError:
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner


NERO_FINALISTS_URL = (
  'https://wp.nerowolfe.org/htm/literary_awards/nero_award/Nero_Award_Finalists.htm'
)
NERO_WINNERS_URL = (
  'https://wp.nerowolfe.org/htm/literary_awards/nero_award/awardees_chron.htm'
)
LIBRARYTHING_NERO_URL = 'https://www.librarything.com/bookaward/Nero%2BAward'
WIKIPEDIA_NERO_URL = 'https://en.wikipedia.org/wiki/Nero_Award'
NERO_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER,)


class UrlFetcherNeroAward(UrlFetcherGeneric):

  FILTER_CATEGORIES = NERO_CATEGORIES
  FETCH_URLS = ()
  order = 230
  options = {'match_series': False}
  URL = NERO_FINALISTS_URL
  AWARD_NAME = 'Nero Award'
  CATEGORY = 'Nero Award'
  CATEGORY_ALIASES = ()
  NAME = 'Nero Award'
  source_id = 'nero_award'
  LIBRARYTHING_URL = LIBRARYTHING_NERO_URL
  WIKIPEDIA_URL = WIKIPEDIA_NERO_URL

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.nero import NeroAwardOfficialParser
    except ImportError:
      from parser.nero import NeroAwardOfficialParser
    return NeroAwardOfficialParser()

  def create_librarything_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.nero import NeroAwardLibraryThingParser
    except ImportError:
      from parser.nero import NeroAwardLibraryThingParser
    return NeroAwardLibraryThingParser()

  def create_wikipedia_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.nero import NeroAwardWikipediaParser
    except ImportError:
      from parser.nero import NeroAwardWikipediaParser
    return NeroAwardWikipediaParser()

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
    librarything_parser = self.create_librarything_parser()
    wikipedia_parser = self.create_wikipedia_parser()
    return (
      SourceAttempt(
        'Official Wolfe Pack',
        self.URL,
        lambda html, url, **kwargs: official_parser.parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES, **kwargs),
        source_rank=0),
      SourceAttempt(
        'LibraryThing',
        self.LIBRARYTHING_URL,
        lambda html, url, **_kwargs: librarything_parser.parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES),
        source_rank=1),
      SourceAttempt(
        'Wikipedia',
        self.WIKIPEDIA_URL,
        lambda html, url, **_kwargs: wikipedia_parser.parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES),
        source_rank=2),
    )

  def source_choices(self):
    return SourceFallbackRunner(self.source_attempts()).source_choices()

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES,
      fetch_url=fetch_url,
      log=log,
      progress=progress)
