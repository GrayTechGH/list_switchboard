#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  UrlFetcherGeneric,
)


ATWOOD_HISTORY_URL = (
  'https://www.writerstrust.com/writers-books/awards/'
  'atwood-gibson-writers-trust-fiction-prize')
ATWOOD_CURRENT_URL = (
  'https://www.writerstrust.com/awards/'
  'atwood-gibson-writers-trust-fiction-prize')
HILARY_WESTON_HISTORY_URL = (
  'https://www.writerstrust.com/writers-books/awards/'
  'hilary-weston-writers-trust-prize-for-nonfiction')
HILARY_WESTON_CURRENT_URL = (
  'https://www.writerstrust.com/awards/'
  'hilary-weston-writers-trust-prize-for-nonfiction')
BALSILLIE_HISTORY_URL = (
  'https://www.writerstrust.com/writers-books/awards/'
  'balsillie-prize-for-public-policy')
BALSILLIE_CURRENT_URL = (
  'https://www.writerstrust.com/awards/balsillie-prize-for-public-policy')
SHAUGHNESSY_COHEN_HISTORY_URL = (
  'https://www.writerstrust.com/writers-books/awards/'
  'shaughnessy-cohen-prize-for-political-writing')
SHAUGHNESSY_COHEN_CURRENT_URL = (
  'https://www.writerstrust.com/awards/'
  'shaughnessy-cohen-prize-for-political-writing')


class UrlFetcherWritersTrustAward(UrlFetcherGeneric):

  order = 242
  options = {'match_series': False}
  AWARD_NAME = "Writers' Trust Award"
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  CURRENT_URL = ''

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.writers_trust import (
        WritersTrustOfficialParser,
      )
    except ImportError:
      from parser.writers_trust import WritersTrustOfficialParser
    return WritersTrustOfficialParser(
      self.AWARD_NAME, self.CATEGORY, self.CATEGORY_ALIASES, self.CURRENT_URL)

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      fetch_url=fetch_url,
      current_url=self.CURRENT_URL,
      log=log,
      progress=progress)


class UrlFetcherWritersTrustAtwoodGibsonFiction(UrlFetcherWritersTrustAward):

  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'writers_trust_atwood_gibson_fiction'
  NAME = "Writers' Trust - Atwood Gibson Fiction Prize"
  AWARD_NAME = "Atwood Gibson Writers' Trust Fiction Prize"
  URL = ATWOOD_HISTORY_URL
  CURRENT_URL = ATWOOD_CURRENT_URL
  CATEGORY = 'Fiction'
  CATEGORY_ALIASES = ('Fiction',)


class UrlFetcherWritersTrustHilaryWestonNonfiction(UrlFetcherWritersTrustAward):

  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'writers_trust_hilary_weston_nonfiction'
  NAME = "Writers' Trust - Hilary Weston Nonfiction Prize"
  AWARD_NAME = "Hilary Weston Writers' Trust Prize for Nonfiction"
  URL = HILARY_WESTON_HISTORY_URL
  CURRENT_URL = HILARY_WESTON_CURRENT_URL
  CATEGORY = 'Nonfiction'
  CATEGORY_ALIASES = ('Nonfiction', 'Non-fiction')


class UrlFetcherWritersTrustBalsilliePublicPolicy(UrlFetcherWritersTrustAward):

  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'writers_trust_balsillie_public_policy'
  NAME = "Writers' Trust - Balsillie Prize for Public Policy"
  AWARD_NAME = 'Balsillie Prize for Public Policy'
  URL = BALSILLIE_HISTORY_URL
  CURRENT_URL = BALSILLIE_CURRENT_URL
  CATEGORY = 'Public Policy'
  CATEGORY_ALIASES = ('Public Policy',)


class UrlFetcherWritersTrustShaughnessyCohenPoliticalWriting(
    UrlFetcherWritersTrustAward):

  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
  source_id = 'writers_trust_shaughnessy_cohen_political_writing'
  NAME = "Writers' Trust - Shaughnessy Cohen Political Writing Prize"
  AWARD_NAME = 'Shaughnessy Cohen Prize for Political Writing'
  URL = SHAUGHNESSY_COHEN_HISTORY_URL
  CURRENT_URL = SHAUGHNESSY_COHEN_CURRENT_URL
  CATEGORY = 'Political Writing'
  CATEGORY_ALIASES = ('Political Writing',)
