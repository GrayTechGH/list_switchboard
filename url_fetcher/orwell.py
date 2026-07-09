#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  UrlFetcherError,
  UrlFetcherGeneric,
  parsed_source,
)

try:
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
except ImportError:
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner


ORWELL_URL = 'https://www.orwellfoundation.com/the-orwell-prizes/previous-winners/'
ORWELL_OFFICIAL_EXTRA_URLS = (
  'https://www.orwellfoundation.com/the-orwell-foundation/news-events/news-events/news/finalists-announced-for-the-orwell-prizes-in-political-writing-and-political-fiction/',
  'https://www.orwellfoundation.com/the-orwell-foundation/news-events/news-events/news/the-orwell-prizes-2025-finalists-announced/',
  'https://www.orwellfoundation.com/the-orwell-foundation/news-events/news-events/news/the-winners-of-the-orwell-prizes-2025/',
)
ORWELL_WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/Orwell_Prize'


class UrlFetcherOrwellPrizePoliticalWriting(UrlFetcherGeneric):

  source_id = 'orwell_prize_political_writing'
  NAME = 'Orwell Prize for Political Writing'
  URL = ORWELL_URL
  FETCH_URLS = (ORWELL_URL,)
  order = 177
  options = {'match_series': False}
  AWARD_NAME = NAME
  CATEGORY = 'Political Writing'
  CATEGORY_ALIASES = (
    'Political Writing Book Prize',
    'The Orwell Prize for Political Writing',
  )
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.orwell import OrwellOfficialParser
    except ImportError:
      from parser.orwell import OrwellOfficialParser
    return OrwellOfficialParser()

  def source_attempts(self):
    try:
      from calibre_plugins.list_switchboard.parser.orwell import (
        OrwellOfficialParser,
        OrwellWikipediaParser,
      )
    except ImportError:
      from parser.orwell import OrwellOfficialParser, OrwellWikipediaParser

    return (
      SourceAttempt(
        'Official Orwell',
        self.URL,
        lambda html, url, fetch_url=None, progress=None, **_kwargs:
          self.parse_official_pages(
            html,
            url,
            fetch_url,
            OrwellOfficialParser(),
            progress=progress),
        source_rank=0),
      SourceAttempt(
        'Wikipedia',
        ORWELL_WIKIPEDIA_URL,
        lambda html, url, **_kwargs: OrwellWikipediaParser().parse(
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
    urls = (base_url,) + tuple(ORWELL_OFFICIAL_EXTRA_URLS)
    if fetch_url is not None:
      for index, url in enumerate(ORWELL_OFFICIAL_EXTRA_URLS, start=2):
        pages.append((url, fetch_url(url)))
        if progress is not None:
          progress(index, len(urls), 'Fetched Orwell source %d of %d' % (
            index, len(urls)))
    parsed = parser.parse(pages, base_url, self.NAME, self.CATEGORY)
    if not parsed.get('entries'):
      raise UrlFetcherError('Official Orwell produced no entries')
    parsed.setdefault('source', parsed_source(self.NAME, base_url, self.source_id))
    parsed.setdefault('match_series', False)
    return parsed

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME, self.CATEGORY)
