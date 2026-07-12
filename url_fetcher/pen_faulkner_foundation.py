#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  UrlFetcherError,
  UrlFetcherGeneric,
  parsed_source,
)

try:
  from calibre_plugins.list_switchboard.parser.pen_faulkner_foundation import (
    PENFaulknerAwardParser, PENHemingwayAwardParser,
  )
except ImportError:
  from parser.pen_faulkner_foundation import (
    PENFaulknerAwardParser, PENHemingwayAwardParser,
  )


class UrlFetcherPENFaulknerFoundationAward(UrlFetcherGeneric):

  order = 175
  options = {'match_series': False}
  URL = ''
  POST_URLS = ()
  PARSER_CLASS = PENFaulknerAwardParser
  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )

  def source_choices(self):
    return ({'label': 'Automatic', 'value': 'automatic'},)

  def primary_urls(self):
    return (self.URL,) + tuple(url for url, _kind in self.POST_URLS)

  def fetch_and_parse(
      self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
      before_fetch=None, after_fetch=None, before_parse=None,
      force_fallback_level=0, disable_fallbacks=False, source_choice=None):
    pages = []
    urls = [(self.URL, 'history')] + list(self.POST_URLS)
    for index, (url, page_kind) in enumerate(urls, start=1):
      if before_fetch is not None:
        before_fetch(url)
      html = self.fetch_url(fetch_url, url)
      if after_fetch is not None:
        after_fetch(url, html)
      if progress is not None:
        progress(index, len(urls), 'Fetched PEN/Faulkner source %d of %d' % (
          index, len(urls)))
      pages.append((url, html, page_kind))
    parsed = self.parser().parse(pages, self.URL, self.NAME)
    if not parsed.get('entries'):
      raise UrlFetcherError('%s produced no entries' % self.NAME)
    parsed.setdefault('source', parsed_source(self.NAME, self.URL, self.source_id))
    parsed.setdefault('match_series', False)
    return parsed

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME)


class UrlFetcherPENFaulknerAward(UrlFetcherPENFaulknerFoundationAward):
  source_id = 'pen_faulkner_award_fiction'
  NAME = 'PEN/Faulkner Award for Fiction'
  URL = 'https://www.penfaulkner.org/our-awards/pen-faulkner-award/'
  PARSER_CLASS = PENFaulknerAwardParser
  POST_URLS = (
    ('https://www.penfaulkner.org/2026-pen-faulkner-award-finalists/', 'finalist_post'),
    ('https://www.penfaulkner.org/2026-pen-faulkner-award-winner/', 'winner_post'),
    ('https://www.penfaulkner.org/2025-pen-faulkner-award-finalists/', 'finalist_post'),
    ('https://www.penfaulkner.org/2025-pen-faulkner-award-winner/', 'winner_post'),
  )


class UrlFetcherPENHemingwayAward(UrlFetcherPENFaulknerFoundationAward):
  source_id = 'pen_hemingway_award_debut_novel'
  NAME = 'PEN/Hemingway Award for Debut Novel'
  URL = 'https://www.penfaulkner.org/our-awards/pen-hemingway-award/'
  PARSER_CLASS = PENHemingwayAwardParser
  POST_URLS = (
    ('https://www.penfaulkner.org/pen-hemingway-award-current-winner/', 'current'),
  )
