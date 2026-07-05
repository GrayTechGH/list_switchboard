#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  UrlFetcherError,
  UrlFetcherGeneric,
)


ANDREW_CARNEGIE_URL = 'https://www.ala.org/carnegie-medals/2026-winners'
ANDREW_CARNEGIE_YEAR_URLS = tuple(
  'https://www.ala.org/carnegie-medals/%d-winners' % year
  for year in range(2026, 2011, -1)
)


class UrlFetcherAndrewCarnegieNonfiction(UrlFetcherGeneric):

  source_id = 'andrew_carnegie_medal_nonfiction'
  NAME = 'Andrew Carnegie Medal for Excellence in Nonfiction'
  URL = ANDREW_CARNEGIE_URL
  FETCH_URLS = (ANDREW_CARNEGIE_URL,)
  order = 178
  options = {'match_series': False}
  AWARD_NAME = NAME
  CATEGORY = 'Nonfiction'
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.andrew_carnegie import (
        AndrewCarnegieOfficialParser,
      )
    except ImportError:
      from parser.andrew_carnegie import AndrewCarnegieOfficialParser
    return AndrewCarnegieOfficialParser()

  def fetch_and_parse(
      self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
      before_fetch=None, after_fetch=None, before_parse=None,
      force_fallback_level=0, disable_fallbacks=False, source_choice=None):
    if source_choice not in (None, 'automatic', 0, '0'):
      raise UrlFetcherError(
        f'No URL fallback exists for selected source {source_choice}.')
    if int(force_fallback_level or 0) > 0 and not disable_fallbacks:
      raise UrlFetcherError(
        f'No URL fallback exists for forced level {force_fallback_level}.')

    pages = []
    notes = []
    urls = ANDREW_CARNEGIE_YEAR_URLS
    for index, url in enumerate(urls, start=1):
      try:
        if before_fetch is not None:
          before_fetch(url)
        html = self.fetch_url(fetch_url, url)
        if after_fetch is not None:
          after_fetch(url, html)
        pages.append((url, html))
        if progress is not None:
          progress(index, len(urls), 'Fetched Carnegie source %d of %d' % (
            index, len(urls)))
      except Exception as err:
        notes.append('Official ALA Carnegie page failed for %s: %s' % (url, err))
        if log is not None:
          log(notes[-1])

    if before_parse is not None:
      before_parse(self.URL)
    parsed = self.parser().parse(pages, self.URL, self.NAME, self.CATEGORY)
    parsed.setdefault('notes', [])
    parsed['notes'] = notes + parsed['notes']
    if not parsed.get('entries'):
      raise UrlFetcherError('Official ALA Carnegie produced no entries')
    parsed.setdefault('source_url', self.URL)
    parsed.setdefault('match_series', False)
    return parsed

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME, self.CATEGORY)
