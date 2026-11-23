#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from urllib.parse import urljoin, urlsplit
import json

from lxml import html as lxml_html

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
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
  from calibre_plugins.list_switchboard.parser.award_base import normalize_line
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
  from calibre_plugins.list_switchboard.parser.annual_updates import read_annual_pages
  from calibre_plugins.list_switchboard.parser.national_book_award_official import read_year, supplement_failed_years
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError, CamoufoxSkippedError
  from calibre_plugins.list_switchboard.transport.camoufox import is_challenge_payload
except ImportError:
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner
  from parser.award_base import normalize_line
  from parser.generic import position_sort_key
  from parser.annual_updates import read_annual_pages
  from parser.national_book_award_official import read_year, supplement_failed_years
  from errors import ImportCancelledError, CamoufoxRequiredError, CamoufoxSkippedError
  from transport.camoufox import is_challenge_payload


NATIONAL_BOOK_AWARD_YEARS_URL = (
  'https://www.nationalbook.org/national-book-awards/years/'
)
NATIONAL_BOOK_AWARD_FICTION_WIKIPEDIA_URL = (
  'https://en.wikipedia.org/wiki/National_Book_Award_for_Fiction'
)
NATIONAL_BOOK_AWARD_NONFICTION_WIKIPEDIA_URL = (
  'https://en.wikipedia.org/wiki/National_Book_Award_for_Nonfiction'
)
NATIONAL_BOOK_AWARD_YPL_WIKIPEDIA_URL = (
  'https://en.wikipedia.org/wiki/National_Book_Award_for_Young_People%27s_Literature'
)


class UrlFetcherNationalBookAward(UrlFetcherGeneric):

  URL = NATIONAL_BOOK_AWARD_YEARS_URL
  FETCH_URLS = (NATIONAL_BOOK_AWARD_YEARS_URL,)
  order = 171
  options = {'match_series': False}
  AWARD_NAME = 'National Book Award'
  CATEGORY = ''
  CATEGORY_SLUG = ''
  WIKIPEDIA_URL = ''

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.national_book_award import (
        NationalBookAwardParser,
      )
    except ImportError:
      from parser.national_book_award import NationalBookAwardParser
    return NationalBookAwardParser()

  def source_attempts(self, allow_wikipedia_supplement=True):
    try:
      from calibre_plugins.list_switchboard.parser.national_book_award import (
        NationalBookAwardParser,
        NationalBookAwardWikipediaParser,
      )
    except ImportError:
      from parser.national_book_award import (
        NationalBookAwardParser,
        NationalBookAwardWikipediaParser,
      )
    return (
      SourceAttempt(
        'Official National Book Foundation',
        self.URL,
        lambda html, url, fetch_url=None, **kwargs: self.parse_official_years(
          html,
          url,
          fetch_url,
          NationalBookAwardParser(), supplement_wikipedia=allow_wikipedia_supplement, **kwargs),
        source_rank=0, supports_incremental=True),
      SourceAttempt(
        'Wikipedia',
        self.WIKIPEDIA_URL,
        lambda html, url, **_kwargs: NationalBookAwardWikipediaParser().parse(
          html, url, self.NAME, self.CATEGORY),
        source_rank=1),
    )

  def source_choices(self):
    return SourceFallbackRunner(self.source_attempts()).source_choices()

  def fetch_and_parse(
      self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
      before_fetch=None, after_fetch=None, before_parse=None,
      force_fallback_level=0, disable_fallbacks=False, source_choice=None,
      cached_parsed=None, incremental_update=False):
    parsed = SourceFallbackRunner(
      self.source_attempts(allow_wikipedia_supplement=not disable_fallbacks),
      error_class=UrlFetcherError).run(
        lambda url: self.fetch_url(fetch_url, url),
        log=log,
        progress=progress,
        before_fetch=before_fetch,
        after_fetch=after_fetch,
        before_parse=before_parse,
        force_fallback_level=force_fallback_level,
        disable_fallbacks=disable_fallbacks,
        source_choice=source_choice, cached_parsed=cached_parsed,
        incremental_update=incremental_update)
    parsed.setdefault('match_series', self.options.get('match_series', True))
    return parsed

  def fetch_url(self, fetch_url, url):
    if urlsplit(url).hostname not in ('nationalbook.org', 'www.nationalbook.org'):
      return super().fetch_url(fetch_url, url)
    payload = self.fetch_official_legacy(fetch_url, url)
    if not self.official_challenge_payload(payload):
      return payload
    legacy_error = 'Foundation returned a bot-verification page instead of award data'
    owner = getattr(fetch_url, '__self__', None)
    report = getattr(owner, 'debug_camoufox', None)
    if report is not None:
      report(f'Foundation legacy request blocked at {url}; trying Camoufox')
    try:
      try:
        payload = fetch_url(url, transport='camoufox')
      except TypeError as err:
        if 'transport' not in str(err) and 'keyword' not in str(err):
          raise
        raise CamoufoxSkippedError('Fetch callback does not support Camoufox.') from err
      if self.official_challenge_payload(payload):
        raise UrlFetcherError('Foundation browser response still requires bot verification.')
      return payload
    except (ImportCancelledError, CamoufoxRequiredError):
      raise
    except Exception as browser_error:
      raise UrlFetcherError(
        f'Foundation request failed at {url}. Legacy: {legacy_error}; '
        f'Camoufox: {browser_error}') from browser_error

  def official_challenge_payload(self, payload):
    """Reject the SiteGround refresh interstitial before year/category parsing."""
    if is_challenge_payload(payload):
      return True
    root = lxml_html.fromstring(payload or '<html></html>')
    return any('/.well-known/sgcaptcha/' in content.casefold() for content in root.xpath(
      '//meta[translate(@http-equiv, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
      '"abcdefghijklmnopqrstuvwxyz")="refresh"]/@content'))

  def fetch_official_legacy(self, fetch_url, url):
    # Long annual crawls encounter intermittent gateway/connection failures at
    # different years. Retry the same official GET twice before the unchanged
    # pending-year or replacement-source handling receives the failure.
    for attempt in range(3):
      try:
        return super().fetch_url(fetch_url, url)
      except (ImportCancelledError, CamoufoxRequiredError):
        raise
      except Exception as err:
        transient = (getattr(err, 'code', None) in (502, 503, 504) or
          'unexpected_eof_while_reading' in str(err).lower() or self.is_timeout_error(err))
        if attempt == 2 or not transient:
          raise

  def parse(self, html, **_kwargs):
    return self.parse_official_years(html, self.URL, None, self.parser())

  def parse_official_years(self, html, base_url, fetch_url, parser,
      cached_parsed=None, incremental_update=False, log=None, progress=None,
      supplement_wikipedia=True):
    urls = self.year_urls(html, base_url)
    if not urls:
      raise UrlFetcherError('Official National Book Foundation had no year URLs')
    if fetch_url is not None:
      result = read_annual_pages(json.dumps([
        base_url, self.source_id, self.CATEGORY, self.CATEGORY_SLUG, type(parser).__name__]),
        [(self.category_url(url), int(url.rstrip('/').rsplit('-',1)[-1])) for url in urls],
        fetch_url, lambda page, url: read_year(parser, page, url, self.NAME, self.CATEGORY, fetch_url),
        cached_parsed=cached_parsed, incremental_update=incremental_update,
        validate_empty=self.recognizable_empty_year, progress=progress, allow_partial=True,
        failure_note=lambda url, year, err: f'Foundation award year {year} unavailable: {err}.')
      if not result['entries']:
        raise UrlFetcherError('Official National Book Foundation produced no entries. ' + ' '.join(result['notes']))
      result.update(name=self.NAME, source=parsed_source(self.NAME, base_url, self.source_id), match_series=False)
      if supplement_wikipedia:
        result = supplement_failed_years(
          result, fetch_url, self.WIKIPEDIA_URL, self.NAME, self.CATEGORY, log=log)
      return result
    if fetch_url is None:
      urls = [base_url]
      fetch_url = lambda _url: html

    entries = []
    for year_url in urls:
      category_url = self.category_url(year_url)
      parsed = parser.parse(
        fetch_url(category_url),
        category_url,
        self.NAME,
        self.CATEGORY)
      entries.extend(parsed.get('entries', ()))
    if not entries:
      raise UrlFetcherError('Official National Book Foundation produced no entries')
    return {
      'name': self.NAME,
      'source': parsed_source(self.NAME, base_url, self.source_id),
      'entries': sorted(
        entries, key=lambda item: position_sort_key(item.get('position', ''))),
      'notes': [],
      'match_series': False,
    }

  def recognizable_empty_year(self, html, url, year):
    root = lxml_html.fromstring(html or '<html></html>')
    titles = root.xpath('//title')
    title = normalize_line(' '.join(titles[0].itertext())) if titles else ''
    return (f'National Book Awards {year}' in title and bool(root.xpath(
      '//div[contains(concat(" ", normalize-space(@class), " "), " finalists-wrapper ")]')))

  def year_urls(self, html, base_url):
    root = lxml_html.fromstring(html or '<html></html>')
    urls = []
    for href in root.xpath('//a[@href]/@href|//option[@value]/@value'):
      url = urljoin(base_url, href)
      if '/awards-prizes/national-book-awards-' not in url:
        continue
      if not normalize_line(url).rstrip('/').split('-')[-1].isdigit():
        continue
      if url not in urls:
        urls.append(url)
    return urls

  def category_url(self, year_url):
    return year_url.rstrip('/') + '/?cat=' + self.CATEGORY_SLUG


class UrlFetcherNationalBookAwardFiction(UrlFetcherNationalBookAward):
  SUPPORTS_INCREMENTAL_UPDATE = False
  source_id = 'national_book_award_fiction'
  NAME = 'National Book Award - Fiction'
  CATEGORY = 'Fiction'
  CATEGORY_SLUG = 'fiction'
  WIKIPEDIA_URL = NATIONAL_BOOK_AWARD_FICTION_WIKIPEDIA_URL
  FILTER_CATEGORIES = (
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )


class UrlFetcherNationalBookAwardNonfiction(UrlFetcherNationalBookAward):
  SUPPORTS_INCREMENTAL_UPDATE = False
  source_id = 'national_book_award_nonfiction'
  NAME = 'National Book Award - Nonfiction'
  CATEGORY = 'Nonfiction'
  CATEGORY_SLUG = 'nonfiction'
  WIKIPEDIA_URL = NATIONAL_BOOK_AWARD_NONFICTION_WIKIPEDIA_URL
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )


class UrlFetcherNationalBookAwardYoungPeoplesLiterature(UrlFetcherNationalBookAward):
  SUPPORTS_INCREMENTAL_UPDATE = False
  source_id = 'national_book_award_young_peoples_literature'
  NAME = "National Book Award - Young People's Literature"
  CATEGORY = "Young People's Literature"
  CATEGORY_SLUG = 'ypl'
  WIKIPEDIA_URL = NATIONAL_BOOK_AWARD_YPL_WIKIPEDIA_URL
  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
