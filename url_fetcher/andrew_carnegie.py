#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  UrlFetcherError,
  UrlFetcherGeneric,
  parsed_source,
)

import json

try:
  from calibre_plugins.list_switchboard.parser.annual_updates import read_annual_pages
except ImportError:
  from parser.annual_updates import read_annual_pages


ANDREW_CARNEGIE_URL = 'https://www.ala.org/carnegie-medals/2026-winners'
ANDREW_CARNEGIE_YEAR_URLS = tuple(
  'https://www.ala.org/carnegie-medals/%d-winners' % year
  for year in range(2026, 2011, -1)
)


class UrlFetcherAndrewCarnegieNonfiction(UrlFetcherGeneric):
  SUPPORTS_INCREMENTAL_UPDATE = True

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
      force_fallback_level=0, disable_fallbacks=False, source_choice=None,
      cached_parsed=None, incremental_update=False):
    if source_choice not in (None, 'automatic', 0, '0'):
      raise UrlFetcherError(
        f'No URL fallback exists for selected source {source_choice}.')
    if int(force_fallback_level or 0) > 0 and not disable_fallbacks:
      raise UrlFetcherError(
        f'No URL fallback exists for forced level {force_fallback_level}.')

    urls = ANDREW_CARNEGIE_YEAR_URLS
    parser = self.parser()
    def fetch_year(url):
      if before_fetch is not None:
        before_fetch(url)
      html = self.fetch_url(fetch_url,url)
      if after_fetch is not None:
        after_fetch(url,html)
      return html
    def parse_year(html,url):
      if before_parse is not None:
        before_parse(url)
      return parser.parse(html,url,self.NAME,self.CATEGORY)
    def failure_note(url,year,err):
      note='Official ALA Carnegie page failed for %s: %s' % (url,err)
      if log is not None:
        log(note)
      return note
    result = read_annual_pages(json.dumps([self.source_id,self.URL.rsplit('/',1)[0],self.CATEGORY,type(parser).__name__]),
      [(url,int(url.rsplit('/',1)[-1].split('-',1)[0])) for url in urls],
      fetch_year,parse_year,cached_parsed=cached_parsed,incremental_update=incremental_update,
      progress=progress,allow_partial=True,failure_note=failure_note)
    parsed = parser.parsed_result(self.NAME,self.URL,result['entries'],result['notes'])
    parsed['incremental_state'] = result['incremental_state']
    if not parsed.get('entries'):
      raise UrlFetcherError('Official ALA Carnegie produced no entries')
    parsed.setdefault('source', parsed_source(self.NAME, self.URL, self.source_id))
    parsed.setdefault('match_series', False)
    return parsed

  def parse(self, html, **_kwargs):
    return self.parser().parse(html, self.URL, self.NAME, self.CATEGORY)
