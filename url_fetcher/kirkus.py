#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

import re
import json
from urllib.parse import urlsplit
from bs4 import BeautifulSoup

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherError,
  UrlFetcherGeneric,
  parsed_source,
)

try:
  from calibre_plugins.list_switchboard.parser.annual_updates import read_annual_pages
  from calibre_plugins.list_switchboard.errors import ImportCancelledError,CamoufoxRequiredError
except ImportError:
  from parser.annual_updates import read_annual_pages
  from errors import ImportCancelledError,CamoufoxRequiredError


KIRKUS_PRIZE_URL = 'https://www.kirkusreviews.com/prize/'
KIRKUS_FIRST_YEAR = 2014
KIRKUS_DEFAULT_LATEST_YEAR = 2025


class UrlFetcherKirkusPrize(UrlFetcherGeneric):

  URL = KIRKUS_PRIZE_URL
  FETCH_URLS = (KIRKUS_PRIZE_URL,)
  order = 179
  options = {'match_series': False}
  AWARD_NAME = 'Kirkus Prize'
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  FILTER_CATEGORIES = (CATEGORY_REGIONAL_NATIONAL_AWARDS,)

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.kirkus import KirkusPrizeParser
    except ImportError:
      from parser.kirkus import KirkusPrizeParser
    return KirkusPrizeParser()

  def year_url(self, year):
    return 'https://www.kirkusreviews.com/prize/%d/' % int(year)

  def latest_year_from_landing(self, html):
    years=[]
    for link in BeautifulSoup(html or '', 'html.parser').find_all('a',href=True):
      match=re.fullmatch(r'/prize/((?:19|20)\d{2})/?',urlsplit(link['href']).path)
      if match:
        years.append(int(match.group(1)))
    completed = [year for year in years if year >= KIRKUS_FIRST_YEAR]
    return max(completed) if completed else KIRKUS_DEFAULT_LATEST_YEAR

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

    try:
      if before_fetch is not None:
        before_fetch(self.URL)
      landing_html = self.fetch_url(fetch_url, self.URL)
      if after_fetch is not None:
        after_fetch(self.URL, landing_html)
    except (ImportCancelledError,CamoufoxRequiredError):
      raise
    except Exception as err:
      raise UrlFetcherError('Official Kirkus prize page failed: %s' % err)

    latest_year = self.latest_year_from_landing(landing_html)
    urls = tuple(
      self.year_url(year)
      for year in range(latest_year, KIRKUS_FIRST_YEAR - 1, -1)
    )
    parser=self.parser()
    def fetch_year(url):
      if before_fetch is not None:
        before_fetch(url)
      html=self.fetch_url(fetch_url,url)
      if after_fetch is not None:
        after_fetch(url,html)
      return html
    def parse_year(html,url):
      if before_parse is not None:
        before_parse(url)
      return parser.parse(html,url,self.NAME,self.CATEGORY,self.CATEGORY_ALIASES)
    def failure_note(url,year,err):
      note='Official Kirkus page failed for %s: %s' % (url,err)
      if log is not None:
        log(note)
      return note
    result=read_annual_pages(json.dumps([self.source_id,self.URL,self.CATEGORY,self.CATEGORY_ALIASES,KIRKUS_FIRST_YEAR,type(parser).__name__]),
      [(url,int(url.rstrip('/').rsplit('/',1)[-1])) for url in urls],
      fetch_year,parse_year,cached_parsed=cached_parsed,incremental_update=incremental_update,
      progress=progress,allow_partial=True,failure_note=failure_note)
    parsed=parser.parsed_result(self.NAME,self.URL,result['entries'],result['notes'])
    parsed['incremental_state']=result['incremental_state']
    if not parsed.get('entries'):
      raise UrlFetcherError('Official Kirkus produced no entries')
    parsed.setdefault('source', parsed_source(self.NAME, self.URL, self.source_id))
    parsed.setdefault('match_series', False)
    return parsed

  def parse(self, html, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES)


class UrlFetcherKirkusPrizeFiction(UrlFetcherKirkusPrize):
  SUPPORTS_INCREMENTAL_UPDATE = True

  source_id = 'kirkus_prize_fiction'
  NAME = 'Kirkus Prize - Fiction'
  CATEGORY = 'Fiction'
  CATEGORY_ALIASES = ('Fiction',)
  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )


class UrlFetcherKirkusPrizeNonfiction(UrlFetcherKirkusPrize):
  SUPPORTS_INCREMENTAL_UPDATE = True

  source_id = 'kirkus_prize_nonfiction'
  NAME = 'Kirkus Prize - Nonfiction'
  CATEGORY = 'Nonfiction'
  CATEGORY_ALIASES = ('Nonfiction',)
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )


class UrlFetcherKirkusPrizeYoungReadersLiterature(UrlFetcherKirkusPrize):
  SUPPORTS_INCREMENTAL_UPDATE = True

  source_id = 'kirkus_prize_young_readers_literature'
  NAME = "Kirkus Prize - Young Readers' Literature"
  CATEGORY = "Young Readers' Literature"
  CATEGORY_ALIASES = (
    "Young Readers' Literature",
    'Young Readers Literature',
    'Young Readers',
    "Children's",
    'Childrens',
    'Teen',
  )
  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
