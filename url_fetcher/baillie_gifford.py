#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

import re
from urllib.parse import urljoin

from lxml import html as lxml_html

from .generic import (
  CATEGORY_NONFICTION,
  CATEGORY_REGIONAL_NATIONAL_AWARDS,
  UrlFetcherError,
  UrlFetcherGeneric,
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


BAILLIE_GIFFORD_YEARS_URL = (
  'https://www.thebailliegiffordprize.co.uk/year-by-year'
)
BAILLIE_GIFFORD_WIKIPEDIA_URL = (
  'https://en.wikipedia.org/wiki/Baillie_Gifford_Prize'
)


class UrlFetcherBaillieGiffordPrize(UrlFetcherGeneric):

  source_id = 'baillie_gifford_prize'
  NAME = 'Baillie Gifford Prize'
  URL = BAILLIE_GIFFORD_YEARS_URL
  FETCH_URLS = (BAILLIE_GIFFORD_YEARS_URL,)
  order = 172
  options = {'match_series': False}
  AWARD_NAME = 'Baillie Gifford Prize'
  CATEGORY = 'Non-Fiction'
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.baillie_gifford import (
        BaillieGiffordPrizeParser,
      )
    except ImportError:
      from parser.baillie_gifford import BaillieGiffordPrizeParser
    return BaillieGiffordPrizeParser()

  def source_attempts(self):
    try:
      from calibre_plugins.list_switchboard.parser.baillie_gifford import (
        BaillieGiffordPrizeParser,
        BaillieGiffordWikipediaParser,
      )
    except ImportError:
      from parser.baillie_gifford import (
        BaillieGiffordPrizeParser,
        BaillieGiffordWikipediaParser,
      )
    return (
      SourceAttempt(
        'Official Baillie Gifford',
        self.URL,
        lambda html, url, fetch_url=None, **_kwargs: self.parse_official_years(
          html,
          url,
          fetch_url,
          BaillieGiffordPrizeParser()),
        source_rank=0),
      SourceAttempt(
        'Wikipedia',
        BAILLIE_GIFFORD_WIKIPEDIA_URL,
        lambda html, url, **_kwargs: BaillieGiffordWikipediaParser().parse(
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
      raise UrlFetcherError('Official Baillie Gifford had no year URLs')
    if fetch_url is None:
      urls = [base_url]
      fetch_url = lambda _url: html

    entries = []
    notes = []
    for year_url in urls:
      parsed = parser.parse(
        fetch_url(year_url),
        year_url,
        self.NAME,
        self.CATEGORY,
        fetch_url=fetch_url)
      entries.extend(parsed.get('entries', ()))
      notes.extend(parsed.get('notes', ()))
    if not entries:
      raise UrlFetcherError('Official Baillie Gifford produced no entries')
    return {
      'name': self.NAME,
      'url': base_url,
      'source_url': base_url,
      'entries': sorted(
        entries, key=lambda item: position_sort_key(item.get('position', ''))),
      'notes': notes,
      'match_series': False,
    }

  def year_urls(self, html, base_url):
    root = lxml_html.fromstring(html or '<html></html>')
    urls = []
    for href in root.xpath('//a[@href]/@href|//option[@value]/@value'):
      url = urljoin(base_url, href)
      if not re.search(r'/year-by-year/(19|20)\d{2}/?$', normalize_line(url)):
        continue
      if url not in urls:
        urls.append(url)
    return urls
