#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  UrlFetcherError,
  UrlFetcherGeneric,
)

try:
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
except ImportError:
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner


ROYAL_SOCIETY_SCIENCE_BOOK_PRIZE_URL = (
  'https://www.royalsociety.org/medals-and-prizes/science-book-prize/'
)
ROYAL_SOCIETY_SCIENCE_BOOK_PRIZE_WIKIPEDIA_URL = (
  'https://en.wikipedia.org/wiki/Royal_Society_Science_Book_Prize'
)


class UrlFetcherRoyalSocietyScienceBookPrize(UrlFetcherGeneric):

  source_id = 'royal_society_science_book_prize'
  NAME = 'Royal Society Trivedi Science Book Prize'
  URL = ROYAL_SOCIETY_SCIENCE_BOOK_PRIZE_URL
  FETCH_URLS = (ROYAL_SOCIETY_SCIENCE_BOOK_PRIZE_URL,)
  order = 180
  options = {'match_series': False}
  CATEGORY = 'Science Book Prize'
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.royal_society import (
        RoyalSocietyScienceBookPrizeParser,
      )
    except ImportError:
      from parser.royal_society import RoyalSocietyScienceBookPrizeParser
    return RoyalSocietyScienceBookPrizeParser()

  def create_wikipedia_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.royal_society import (
        RoyalSocietyScienceBookPrizeWikipediaParser,
      )
    except ImportError:
      from parser.royal_society import RoyalSocietyScienceBookPrizeWikipediaParser
    return RoyalSocietyScienceBookPrizeWikipediaParser()

  def source_attempts(self):
    return (
      SourceAttempt(
        'Official Royal Society',
        self.URL,
        lambda html, url, fetch_url=None, **_kwargs: self.parser().parse(
          html,
          url,
          self.NAME,
          self.CATEGORY,
          fetch_url=fetch_url),
        source_rank=0),
      SourceAttempt(
        'Wikipedia',
        ROYAL_SOCIETY_SCIENCE_BOOK_PRIZE_WIKIPEDIA_URL,
        lambda html, url, **_kwargs: self.create_wikipedia_parser().parse(
          html,
          url,
          self.NAME,
          self.CATEGORY),
        source_rank=1),
    )

  def source_choices(self):
    return SourceFallbackRunner(self.source_attempts()).source_choices()

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

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME, self.CATEGORY)
