#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_CRIME_MYSTERY_THRILLER,
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


CWA_CATEGORIES = (CATEGORY_CRIME_MYSTERY_THRILLER,)


class UrlFetcherCWADagger(LibraryThingAwardFallbackMixin, UrlFetcherGeneric):

  FILTER_CATEGORIES = CWA_CATEGORIES
  FETCH_URLS = ()
  order = 221
  options = {
    'match_series': False,
  }
  AWARD_NAME = 'CWA Dagger'
  LIBRARYTHING_AWARD_NAME = AWARD_NAME
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  LIBRARYTHING_URL = ''

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.cwa import CWADaggerParser
    except ImportError:
      from parser.cwa import CWADaggerParser

    return CWADaggerParser()

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

  def source_attempts(self):
    official_parser = self.parser()
    return (
      SourceAttempt(
        'Official CWA',
        self.URL,
        lambda html, url, **kwargs: official_parser.parse(
          html, url, self.NAME, self.CATEGORY, **kwargs),
        source_rank=0),
      self.librarything_attempt(source_rank=1),
    )

  def source_choices(self):
    return SourceFallbackRunner(self.source_attempts()).source_choices()

  def parse(self, html, fetch_url=None, log=None, progress=None, **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      self.CATEGORY,
      fetch_url=fetch_url,
      log=log,
      progress=progress)


class UrlFetcherCWAGoldDagger(UrlFetcherCWADagger):
  source_id = 'cwa_dagger_gold'
  NAME = 'CWA Dagger - Gold Dagger'
  URL = 'https://thecwa.co.uk/past-winners/?past_winners_awards[]=gold'
  CATEGORY = 'Gold Dagger'
  CATEGORY_ALIASES = ('gold dagger', 'kaa gold dagger')
  LIBRARYTHING_URL = (
    'https://www.librarything.com/award/668.0.4774/'
    'Crime-Writers-Association-Awards-Gold-Dagger')


class UrlFetcherCWAIanFlemingSteelDagger(UrlFetcherCWADagger):
  source_id = 'cwa_dagger_ian_fleming_steel'
  NAME = 'CWA Dagger - Ian Fleming Steel Dagger'
  URL = 'https://thecwa.co.uk/past-winners/?past_winners_awards[]=ian-fleming-steel'
  CATEGORY = 'Ian Fleming Steel Dagger'
  CATEGORY_ALIASES = ('ian fleming steel dagger', 'steel dagger')
  LIBRARYTHING_URL = (
    'https://www.librarything.com/award/668.0.4784/'
    'Crime-Writers-Association-Awards-Ian-Fleming-Steel-Dagger')


class UrlFetcherCWAHistoricalDagger(UrlFetcherCWADagger):
  source_id = 'cwa_dagger_historical'
  NAME = 'CWA Dagger - Historical Dagger'
  URL = 'https://thecwa.co.uk/past-winners/?past_winners_awards[]=historical'
  CATEGORY = 'Historical Dagger'
  CATEGORY_ALIASES = (
    'historical dagger',
    'endeavour historical dagger',
    'ellis peters historical dagger',
  )
  LIBRARYTHING_URL = (
    'https://www.librarything.com/award/668.0.4798/'
    'Crime-Writers-Association-Awards-Endeavour-Historical-Dagger')


class UrlFetcherCWACrimeFictionInTranslationDagger(UrlFetcherCWADagger):
  source_id = 'cwa_dagger_crime_fiction_in_translation'
  NAME = 'CWA Dagger - Crime Fiction in Translation'
  URL = 'https://thecwa.co.uk/past-winners/?past_winners_awards[]=international'
  CATEGORY = 'Crime Fiction in Translation Dagger'
  CATEGORY_ALIASES = (
    'crime fiction in translation dagger',
    'international dagger',
    'duncan lawrie international dagger',
  )
  LIBRARYTHING_URL = (
    'https://www.librarything.com/award/668.0.4787/'
    'Crime-Writers-Association-Awards-International-Dagger')
