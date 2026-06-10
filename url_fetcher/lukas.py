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
  from calibre_plugins.list_switchboard.url_fetcher.librarything_fallback import (
    LibraryThingAwardFallbackMixin,
  )
except ImportError:
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner
  from url_fetcher.librarything_fallback import LibraryThingAwardFallbackMixin


LUKAS_URL = 'https://journalism.columbia.edu/lukas'
LUKAS_OFFICIAL_EXTRA_URLS = (
  'https://journalism.columbia.edu/news/lukas-prize-winners-2026',
  'https://journalism.columbia.edu/news/lukas-shortlists-2026',
)
LUKAS_LIBRARYTHING_URL = (
  'https://www.librarything.com/award/1863/J-Anthony-Lukas-Book-Prize'
)
LUKAS_WIKIPEDIA_URL = (
  'https://en.wikipedia.org/wiki/J._Anthony_Lukas_Book_Prize'
)
MARK_LYNTON_WIKIPEDIA_URL = (
  'https://en.wikipedia.org/wiki/Mark_Lynton_History_Prize'
)


class UrlFetcherJAnthonyLukasBookPrize(
    LibraryThingAwardFallbackMixin, UrlFetcherGeneric):

  source_id = 'j_anthony_lukas_book_prize'
  NAME = 'J. Anthony Lukas Book Prize'
  URL = LUKAS_URL
  FETCH_URLS = (LUKAS_URL,)
  order = 176
  options = {'match_series': False}
  AWARD_NAME = NAME
  CATEGORY = 'Book Prize'
  CATEGORY_ALIASES = ('J. Anthony Lukas Book Prize',)
  LIBRARYTHING_URL = LUKAS_LIBRARYTHING_URL
  LIBRARYTHING_AWARD_NAME = AWARD_NAME
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.lukas import LukasOfficialParser
    except ImportError:
      from parser.lukas import LukasOfficialParser
    return LukasOfficialParser()

  def create_librarything_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.lukas import LukasLibraryThingParser
    except ImportError:
      from parser.lukas import LukasLibraryThingParser
    return LukasLibraryThingParser()

  def source_attempts(self):
    try:
      from calibre_plugins.list_switchboard.parser.lukas import (
        LukasOfficialParser,
        LukasWikipediaParser,
      )
    except ImportError:
      from parser.lukas import LukasOfficialParser, LukasWikipediaParser

    return (
      SourceAttempt(
        'Official Columbia',
        self.URL,
        lambda html, url, fetch_url=None, progress=None, **_kwargs:
          self.parse_official_pages(
            html,
            url,
            fetch_url,
            LukasOfficialParser(),
            progress=progress),
        source_rank=0),
      self.librarything_attempt(source_rank=1),
      SourceAttempt(
        'Wikipedia',
        LUKAS_WIKIPEDIA_URL,
        lambda html, url, **_kwargs: LukasWikipediaParser().parse(
          html, url, self.NAME, self.CATEGORY),
        source_rank=2),
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

  def parse_official_pages(self, html, base_url, fetch_url, parser, progress=None):
    pages = [(base_url, html)]
    urls = (base_url,) + tuple(LUKAS_OFFICIAL_EXTRA_URLS)
    if fetch_url is not None:
      for index, url in enumerate(LUKAS_OFFICIAL_EXTRA_URLS, start=2):
        pages.append((url, fetch_url(url)))
        if progress is not None:
          progress(index, len(urls), 'Fetched Lukas source %d of %d' % (
            index, len(urls)))
    parsed = parser.parse(pages, base_url, self.NAME, self.CATEGORY)
    if not parsed.get('entries'):
      raise UrlFetcherError('Official Columbia produced no entries')
    parsed.setdefault('source_url', base_url)
    parsed.setdefault('match_series', False)
    return parsed

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME, self.CATEGORY)


class UrlFetcherMarkLyntonHistoryPrize(UrlFetcherGeneric):

  source_id = 'mark_lynton_history_prize'
  NAME = 'Mark Lynton History Prize'
  URL = LUKAS_URL
  FETCH_URLS = (LUKAS_URL,)
  order = 177
  options = {'match_series': False}
  AWARD_NAME = NAME
  CATEGORY = 'History Prize'
  CATEGORY_ALIASES = ('Mark Lynton History Prize', 'Lynton History Prize')
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.lukas import (
        MarkLyntonHistoryPrizeParser,
      )
    except ImportError:
      from parser.lukas import MarkLyntonHistoryPrizeParser
    return MarkLyntonHistoryPrizeParser()

  def create_wikipedia_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.lukas import (
        MarkLyntonHistoryPrizeWikipediaParser,
      )
    except ImportError:
      from parser.lukas import MarkLyntonHistoryPrizeWikipediaParser
    return MarkLyntonHistoryPrizeWikipediaParser()

  def source_attempts(self):
    return (
      SourceAttempt(
        'Official Columbia',
        self.URL,
        lambda html, url, fetch_url=None, progress=None, **_kwargs:
          self.parse_official_pages(
            html,
            url,
            fetch_url,
            self.parser(),
            progress=progress),
        source_rank=0),
      SourceAttempt(
        'Wikipedia',
        MARK_LYNTON_WIKIPEDIA_URL,
        lambda html, url, **_kwargs: self.create_wikipedia_parser().parse(
          html, url, self.NAME, self.CATEGORY),
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

  def parse_official_pages(self, html, base_url, fetch_url, parser, progress=None):
    pages = [(base_url, html)]
    urls = (base_url,) + tuple(LUKAS_OFFICIAL_EXTRA_URLS)
    if fetch_url is not None:
      for index, url in enumerate(LUKAS_OFFICIAL_EXTRA_URLS, start=2):
        pages.append((url, fetch_url(url)))
        if progress is not None:
          progress(index, len(urls), 'Fetched Lukas source %d of %d' % (
            index, len(urls)))
    parsed = parser.parse(pages, base_url, self.NAME, self.CATEGORY)
    if not parsed.get('entries'):
      raise UrlFetcherError('Official Columbia produced no entries')
    parsed.setdefault('source_url', base_url)
    parsed.setdefault('match_series', False)
    return parsed

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME, self.CATEGORY)
