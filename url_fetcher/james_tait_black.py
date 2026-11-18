#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  UrlFetcherGeneric,
)


FICTION_URL = 'https://james-tait-black.ed.ac.uk/winners/fiction'
BIOGRAPHY_URL = 'https://james-tait-black.ed.ac.uk/winners/biography'
SHORTLIST_URL_2026 = 'https://james-tait-black.ed.ac.uk/indie-talent-shines-on-book-prize-shortlist'
SHORTLIST_URL_2024 = 'https://www.ed.ac.uk/news/2024/love-and-loss-illuminates-book-prize-shortlist'


class UrlFetcherJamesTaitBlack(UrlFetcherGeneric):

  AWARD_NAME = 'James Tait Black Prize'
  CATEGORY = ''
  SHORTLIST_HEADING_ALIASES = ()
  SHORTLIST_URLS = (SHORTLIST_URL_2026, SHORTLIST_URL_2024)
  SHORTLIST_SPECS = {
    SHORTLIST_URL_2026: {'year': 2025, 'counts': {'Fiction': 5, 'Biography': 5}},
    SHORTLIST_URL_2024: {'year': 2023, 'counts': {'Fiction': 4, 'Biography': 6}},
  }
  order = 241
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.james_tait_black import (
        JamesTaitBlackOfficialParser,
      )
    except ImportError:
      from parser.james_tait_black import JamesTaitBlackOfficialParser
    return JamesTaitBlackOfficialParser(
      self.CATEGORY, self.SHORTLIST_HEADING_ALIASES)

  def parse(self, html, fetch_url=None, log=None, progress=None,
      cached_parsed=None,incremental_update=False,**_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      fetch_url=fetch_url,
      shortlist_urls=self.SHORTLIST_URLS,
      log=log,
      progress=progress,cached_parsed=cached_parsed,incremental_update=incremental_update,
      shortlist_specs=self.SHORTLIST_SPECS)


class UrlFetcherJamesTaitBlackFiction(UrlFetcherJamesTaitBlack):

  SUPPORTS_INCREMENTAL_UPDATE = True
  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'james_tait_black_fiction'
  NAME = 'James Tait Black Prize - Fiction'
  URL = FICTION_URL
  CATEGORY = 'Fiction'
  SHORTLIST_HEADING_ALIASES = ('Leading fiction', 'Fiction', 'Contemporary writing')


class UrlFetcherJamesTaitBlackBiography(UrlFetcherJamesTaitBlack):

  SUPPORTS_INCREMENTAL_UPDATE = True
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'james_tait_black_biography'
  NAME = 'James Tait Black Prize - Biography'
  URL = BIOGRAPHY_URL
  CATEGORY = 'Biography'
  SHORTLIST_HEADING_ALIASES = ('Lives reimagined', 'Biography', 'Illuminating biographies')
