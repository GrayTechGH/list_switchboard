#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_LITERARY_GENERAL_FICTION,
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  UrlFetcherGeneric,
  UrlFetcherError,
)
from .writers_trust_transport import WritersTrustFetchPolicy

try:
  from calibre_plugins.list_switchboard.parser.writers_trust_updates import fetch_writers_trust
except ImportError:
  from parser.writers_trust_updates import fetch_writers_trust


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

  def fetch_and_parse(self,fetch_url,sleep=None,fetch_error=None,log=None,progress=None,
      before_fetch=None,after_fetch=None,before_parse=None,force_fallback_level=0,
      disable_fallbacks=False,source_choice=None,cached_parsed=None,incremental_update=False):
    if source_choice not in (None,'automatic',0,'0') or (int(force_fallback_level or 0)>0 and not disable_fallbacks):
      raise UrlFetcherError('No URL fallback exists for the selected source.')
    legacy=super().fetch_url
    self._trust_fetch_policy=WritersTrustFetchPolicy(fetch_url,lambda url:legacy(fetch_url,url),self.parser(),log)
    try:
      return fetch_writers_trust(self,fetch_url,cached_parsed,incremental_update,
        before_fetch,after_fetch,before_parse,progress)
    finally:self._trust_fetch_policy=None

  def fetch_url(self,fetch_url,url):
    policy=getattr(self,'_trust_fetch_policy',None)
    return policy.fetch(url) if policy is not None else super().fetch_url(fetch_url,url)

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

  SUPPORTS_INCREMENTAL_UPDATE = True
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

  SUPPORTS_INCREMENTAL_UPDATE = True
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

  SUPPORTS_INCREMENTAL_UPDATE = True
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

  SUPPORTS_INCREMENTAL_UPDATE = True
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
