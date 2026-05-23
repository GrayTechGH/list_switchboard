#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Shared SFADB-primary, ISFDB award-year replacement fallback helpers.

Maintenance notes:
- This mixin is for SFADB overview/year-page fetchers whose verified fallback is
  the ISFDB award-type overview plus linked `ay.cgi` year pages.
- It intentionally keeps ISFDB fallback opt-in per fetcher class so categories
  that broaden scope, lose nominee semantics, or need extra filtering can stay
  SFADB-only.
"""

import re
from urllib.parse import urljoin

try:
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
  from calibre_plugins.list_switchboard.parser.isfdb_base import (
    ISFDBAwardParserBase,
  )
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
  from calibre_plugins.list_switchboard.url_fetcher.generic import UrlFetcherError
except ImportError:
  from parser.generic import position_sort_key
  from parser.isfdb_base import ISFDBAwardParserBase
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner
  from url_fetcher.generic import UrlFetcherError


ISFDB_AWARD_TYPE_URL = 'https://www.isfdb.org/cgi-bin/awardtype.cgi?{}'


class SFADBISFDYAwardFallbackMixin:

  AWARD_NAME = ''
  ISFDB_AWARD_ID = ''
  ISFDB_CATEGORY_ALIASES = ()
  USE_ISFDB_FALLBACK = False

  def create_isfdb_parser(self):
    parser = ISFDBAwardParserBase()
    parser.AWARD_NAME = self.AWARD_NAME
    return parser

  def isfdb_url(self):
    if not self.ISFDB_AWARD_ID or not self.USE_ISFDB_FALLBACK:
      return ''
    return ISFDB_AWARD_TYPE_URL.format(self.ISFDB_AWARD_ID)

  def isfdb_category_aliases(self):
    return tuple(self.CATEGORY_ALIASES) + tuple(self.ISFDB_CATEGORY_ALIASES)

  def source_attempts(self):
    attempts = [
      SourceAttempt(
        'SFADB',
        self.URL,
        lambda html, _url, **kwargs: self.parse(html, **kwargs),
        source_rank=0),
    ]
    isfdb_url = self.isfdb_url()
    if isfdb_url:
      attempts.append(SourceAttempt(
        'ISFDB',
        isfdb_url,
        lambda html, url, **kwargs: self.parse_isfdb_award_type(
          html, url, **kwargs),
        source_rank=1))
    return tuple(attempts)

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
    parsed['match_series'] = self.options.get('match_series', True)
    return parsed

  def isfdb_year_urls(self, html, base_url):
    urls = []
    for match in re.finditer(r'href=[\"\']([^\"\']*?/ay\.cgi\?\d+\+\d{4})', html or '', re.I):
      url = urljoin(base_url, match.group(1))
      if url not in urls:
        urls.append(url)
    return tuple(urls)

  def parse_isfdb_award_type(
      self, html, base_url, fetch_url=None, log=None, progress=None):
    parser = self.create_isfdb_parser()
    entries = []
    notes = []
    for url in self.isfdb_year_urls(html, base_url):
      try:
        year_html = fetch_url(url) if fetch_url is not None else ''
        parsed = parser.parse(
          year_html,
          url,
          self.NAME,
          self.CATEGORY,
          self.isfdb_category_aliases())
        entries.extend(parsed.get('entries', ()))
        notes.extend(parsed.get('notes', ()))
      except Exception as err:
        notes.append(f'{self.AWARD_NAME} ISFDB year {url} could not be fetched: {err}')
        if log is not None:
          log(f'{self.AWARD_NAME} ISFDB year failed: {url}: {err}')
    return {
      'name': self.NAME,
      'entries': sorted(
        entries,
        key=lambda entry: position_sort_key(entry.get('position', ''))),
      'notes': notes,
    }
