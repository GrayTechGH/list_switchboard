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


SHAMUS_URL = 'https://www.stopyourekillingme.com/Awards/Shamus_Awards.html'
LIBRARYTHING_SHAMUS_URL = 'https://www.librarything.com/award/1733/Shamus-Award'
SHAMUS_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER,)


class UrlFetcherShamusAward(LibraryThingAwardFallbackMixin, UrlFetcherGeneric):

  FILTER_CATEGORIES = SHAMUS_CATEGORIES
  FETCH_URLS = ()
  order = 226
  options = {
    'match_series': False,
  }
  URL = SHAMUS_URL
  AWARD_NAME = 'Shamus Award'
  LIBRARYTHING_AWARD_NAME = AWARD_NAME
  LIBRARYTHING_URL = LIBRARYTHING_SHAMUS_URL
  CATEGORY = ''
  CATEGORY_ALIASES = ()

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.shamus import ShamusAwardsParser
    except ImportError:
      from parser.shamus import ShamusAwardsParser

    return ShamusAwardsParser()

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


class UrlFetcherShamusPINovel(UrlFetcherShamusAward):
  source_id = 'shamus_award_pi_novel'
  NAME = 'Shamus Award - P.I. Novel'
  CATEGORY = 'Best P.I. Novel'
  CATEGORY_ALIASES = (
    'Best PI Novel',
    'Best Hardcover P.I. Novel',
    'Best Hardcover PI Novel',
    'Best Hardcover Novel',
    'P.I. Novel',
    'PI Novel',
  )


class UrlFetcherShamusPaperbackOriginal(UrlFetcherShamusAward):
  source_id = 'shamus_award_paperback_original'
  NAME = 'Shamus Award - Paperback Original'
  CATEGORY = 'Best P.I. Paperback Original'
  CATEGORY_ALIASES = (
    'Best PI Paperback Original',
    'Best Paperback Original P.I. Novel',
    'Best Paperback Original PI Novel',
    'Best Paperback Original',
    'Paperback Original',
  )


class UrlFetcherShamusFirstPINovel(UrlFetcherShamusAward):
  source_id = 'shamus_award_first_pi_novel'
  NAME = 'Shamus Award - First P.I. Novel'
  CATEGORY = 'Best First P.I. Novel'
  CATEGORY_ALIASES = (
    'Best First PI Novel',
    'Best First P.I. Novel',
    'Best First PI',
    'First P.I. Novel',
    'First PI Novel',
  )
