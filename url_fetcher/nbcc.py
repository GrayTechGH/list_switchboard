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


NBCC_PAST_AWARDS_URL = 'https://www.bookcritics.org/awards/past/'
NBCC_NONFICTION_WIKIPEDIA_URL = (
  'https://en.wikipedia.org/wiki/National_Book_Critics_Circle_Award_for_Nonfiction'
)
NBCC_CRITICISM_WIKIPEDIA_URL = (
  'https://en.wikipedia.org/wiki/National_Book_Critics_Circle_Award_for_Criticism'
)


class UrlFetcherNBCCAward(UrlFetcherGeneric):

  URL = NBCC_PAST_AWARDS_URL
  FETCH_URLS = (NBCC_PAST_AWARDS_URL,)
  order = 173
  options = {'match_series': False}
  AWARD_NAME = 'National Book Critics Circle Award'
  CATEGORY = ''
  CATEGORY_ALIASES = ()
  WIKIPEDIA_URL = ''
  FILTER_CATEGORIES = (
    CATEGORY_NONFICTION,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
  )

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.nbcc import NBCCAwardParser
    except ImportError:
      from parser.nbcc import NBCCAwardParser
    return NBCCAwardParser()

  def source_attempts(self):
    try:
      from calibre_plugins.list_switchboard.parser.nbcc import (
        NBCCAwardParser,
        NBCCWikipediaParser,
      )
    except ImportError:
      from parser.nbcc import NBCCAwardParser, NBCCWikipediaParser
    return (
      SourceAttempt(
        'Official NBCC',
        self.URL,
        lambda html, url, fetch_url=None, **_kwargs: self.parse_official_years(
          html,
          url,
          fetch_url,
          NBCCAwardParser()),
        source_rank=0),
      SourceAttempt(
        'Wikipedia',
        self.WIKIPEDIA_URL,
        lambda html, url, **_kwargs: NBCCWikipediaParser().parse(
          html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES),
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
    initial_urls = self.year_urls(html, base_url)
    if not initial_urls:
      raise UrlFetcherError('Official NBCC had no year URLs')
    if fetch_url is None:
      initial_urls = [base_url]
      fetch_url = lambda _url: html

    entries = []
    notes = []
    queue = list(initial_urls)
    seen_urls = set()
    while queue:
      year_url = queue.pop(0)
      if year_url in seen_urls:
        continue
      seen_urls.add(year_url)
      year_html = fetch_url(year_url)
      parsed = parser.parse(
        year_html,
        year_url,
        self.NAME,
        self.CATEGORY,
        self.CATEGORY_ALIASES)
      entries.extend(parsed.get('entries', ()))
      notes.extend(parsed.get('notes', ()))
      for next_url in self.next_year_urls(year_html, year_url):
        if next_url not in seen_urls and next_url not in queue:
          queue.append(next_url)
    if not entries:
      raise UrlFetcherError('Official NBCC produced no entries')
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
      if not self.is_year_url(url):
        continue
      if url not in urls:
        urls.append(url)
    return urls

  def next_year_urls(self, html, base_url):
    root = lxml_html.fromstring(html or '<html></html>')
    urls = []
    for href in root.xpath('//a[@href and contains(concat(" ", normalize-space(@rel), " "), " next ")]/@href'):
      url = urljoin(base_url, href)
      if self.is_year_url(url) and url not in urls:
        urls.append(url)
    return urls

  def is_year_url(self, url):
    return bool(re.search(r'/past-awards/(19|20)\d{2}/?$', normalize_line(url)))


class UrlFetcherNBCCNonfiction(UrlFetcherNBCCAward):
  source_id = 'nbcc_award_nonfiction'
  NAME = 'National Book Critics Circle Award - Nonfiction'
  CATEGORY = 'Nonfiction'
  CATEGORY_ALIASES = ('General Nonfiction',)
  WIKIPEDIA_URL = NBCC_NONFICTION_WIKIPEDIA_URL


class UrlFetcherNBCCCriticism(UrlFetcherNBCCAward):
  source_id = 'nbcc_award_criticism'
  NAME = 'National Book Critics Circle Award - Criticism'
  CATEGORY = 'Criticism'
  WIKIPEDIA_URL = NBCC_CRITICISM_WIKIPEDIA_URL
