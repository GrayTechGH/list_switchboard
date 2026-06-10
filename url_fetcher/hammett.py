#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import CATEGORY_CRIME_MYSTERY_THRILLER, UrlFetcherError, UrlFetcherGeneric

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


HAMMETT_URL = 'https://www.crimewritersna.org/hammett-prize'
LIBRARYTHING_HAMMETT_URL = 'https://www.librarything.com/award/1253/Hammett-Prize'
HAMMETT_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER,)


class UrlFetcherHammettPrize(LibraryThingAwardFallbackMixin, UrlFetcherGeneric):

  FILTER_CATEGORIES = HAMMETT_CATEGORIES
  FETCH_URLS = ()
  order = 229
  options = {'match_series': False}
  URL = HAMMETT_URL
  source_id = 'hammett_prize'
  NAME = 'Hammett Prize'
  AWARD_NAME = 'Hammett Prize'
  CATEGORY = 'Hammett Prize'
  CATEGORY_ALIASES = ('Best Crime Book',)
  LIBRARYTHING_URL = LIBRARYTHING_HAMMETT_URL
  LIBRARYTHING_AWARD_NAME = AWARD_NAME

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.hammett import HammettPrizeParser
    except ImportError:
      from parser.hammett import HammettPrizeParser
    return HammettPrizeParser()

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
        'Official IACW',
        self.URL,
        lambda html, url, **kwargs: official_parser.parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES, **kwargs),
        source_rank=0),
      self.librarything_attempt(source_rank=1),
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
