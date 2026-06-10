#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

import re

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
  UrlFetcherError,
  UrlFetcherGeneric,
)


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
    years = [
      int(match)
      for match in re.findall(r'/prize/((?:19|20)\d{2})/', html or '')
    ]
    completed = [year for year in years if year >= KIRKUS_FIRST_YEAR]
    return max(completed) if completed else KIRKUS_DEFAULT_LATEST_YEAR

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

    try:
      if before_fetch is not None:
        before_fetch(self.URL)
      landing_html = self.fetch_url(fetch_url, self.URL)
      if after_fetch is not None:
        after_fetch(self.URL, landing_html)
    except Exception as err:
      raise UrlFetcherError('Official Kirkus prize page failed: %s' % err)

    latest_year = self.latest_year_from_landing(landing_html)
    urls = tuple(
      self.year_url(year)
      for year in range(latest_year, KIRKUS_FIRST_YEAR - 1, -1)
    )
    pages = []
    notes = []
    for index, url in enumerate(urls, start=1):
      try:
        if before_fetch is not None:
          before_fetch(url)
        html = self.fetch_url(fetch_url, url)
        if after_fetch is not None:
          after_fetch(url, html)
        pages.append((url, html))
        if progress is not None:
          progress(index, len(urls), 'Fetched Kirkus source %d of %d' % (
            index, len(urls)))
      except Exception as err:
        notes.append('Official Kirkus page failed for %s: %s' % (url, err))
        if log is not None:
          log(notes[-1])

    if before_parse is not None:
      before_parse(self.URL)
    parsed = self.parser().parse(
      pages,
      self.URL,
      self.NAME,
      self.CATEGORY,
      self.CATEGORY_ALIASES)
    parsed.setdefault('notes', [])
    parsed['notes'] = notes + parsed['notes']
    if not parsed.get('entries'):
      raise UrlFetcherError('Official Kirkus produced no entries')
    parsed.setdefault('source_url', self.URL)
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

  source_id = 'kirkus_prize_fiction'
  NAME = 'Kirkus Prize - Fiction'
  CATEGORY = 'Fiction'
  CATEGORY_ALIASES = ('Fiction',)
  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )


class UrlFetcherKirkusPrizeNonfiction(UrlFetcherKirkusPrize):

  source_id = 'kirkus_prize_nonfiction'
  NAME = 'Kirkus Prize - Nonfiction'
  CATEGORY = 'Nonfiction'
  CATEGORY_ALIASES = ('Nonfiction',)
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )


class UrlFetcherKirkusPrizeYoungReadersLiterature(UrlFetcherKirkusPrize):

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
