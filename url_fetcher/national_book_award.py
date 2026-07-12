#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from urllib.parse import urljoin

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
except ImportError:
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner
  from parser.award_base import normalize_line
  from parser.generic import position_sort_key


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

  def source_attempts(self):
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
        lambda html, url, fetch_url=None, **_kwargs: self.parse_official_years(
          html,
          url,
          fetch_url,
          NationalBookAwardParser()),
        source_rank=0),
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

  def parse(self, html, **_kwargs):
    return self.parse_official_years(html, self.URL, None, self.parser())

  def parse_official_years(self, html, base_url, fetch_url, parser):
    urls = self.year_urls(html, base_url)
    if not urls:
      raise UrlFetcherError('Official National Book Foundation had no year URLs')
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
  source_id = 'national_book_award_young_peoples_literature'
  NAME = "National Book Award - Young People's Literature"
  CATEGORY = "Young People's Literature"
  CATEGORY_SLUG = 'ypl'
  WIKIPEDIA_URL = NATIONAL_BOOK_AWARD_YPL_WIKIPEDIA_URL
  FILTER_CATEGORIES = (
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )
