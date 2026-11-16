#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Shared SFADB/ISFDB award-year source helpers.

Maintenance notes:
- This mixin is for SFADB overview/year-page fetchers whose verified fallback is
  the ISFDB award-type overview plus linked `ay.cgi` year pages.
- It intentionally keeps ISFDB fallback opt-in per fetcher class so categories
  that broaden scope, lose nominee semantics, or need extra filtering can stay
  SFADB-only.
- Recipes absent from SFADB can disable that source and use ISFDB as rank zero.
- A verified complete category page can replace the award-type/year traversal.
"""

import re
from urllib.parse import urljoin

from .isfdb_transport import ISFDBSourceAttempt

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
  from calibre_plugins.list_switchboard.parser.isfdb_base import (
    ISFDBAwardParserBase,
  )
  from calibre_plugins.list_switchboard.parser.source_fallback import (
    SourceAttempt, SourceFallbackRunner,
  )
  from calibre_plugins.list_switchboard.url_fetcher.generic import UrlFetcherError
except ImportError:
  from errors import ImportCancelledError
  from parser.generic import position_sort_key
  from parser.isfdb_base import ISFDBAwardParserBase
  from parser.source_fallback import SourceAttempt, SourceFallbackRunner
  from url_fetcher.generic import UrlFetcherError


ISFDB_AWARD_TYPE_URL = 'https://www.isfdb.org/cgi-bin/awardtype.cgi?{}'
ISFDB_CATEGORY_URL = 'https://www.isfdb.org/cgi-bin/award_category.cgi?{}+1'


class SFADBISFDYAwardFallbackMixin:

  AWARD_NAME = ''
  ISFDB_AWARD_ID = ''
  ISFDB_CATEGORY_ID = ''
  ISFDB_CATEGORY_ALIASES = ()
  ISFDB_SOURCE_LABEL = 'ISFDB'
  ISFDB_SOURCE_NOTES = ()
  USE_ISFDB_FALLBACK = False
  USE_SFADB_SOURCE = True
  RESOLVE_ISFDB_ORIGINAL_WORKS = False

  def create_isfdb_parser(self):
    parser = ISFDBAwardParserBase()
    parser.AWARD_NAME = self.AWARD_NAME
    parser.CAPTURE_ORIGINAL_WORK = self.RESOLVE_ISFDB_ORIGINAL_WORKS
    return parser

  def isfdb_url(self):
    if not self.ISFDB_AWARD_ID or not self.USE_ISFDB_FALLBACK:
      return ''
    if self.ISFDB_CATEGORY_ID:
      return ISFDB_CATEGORY_URL.format(self.ISFDB_CATEGORY_ID)
    return ISFDB_AWARD_TYPE_URL.format(self.ISFDB_AWARD_ID)

  def isfdb_category_aliases(self):
    return tuple(self.CATEGORY_ALIASES) + tuple(self.ISFDB_CATEGORY_ALIASES)

  def source_attempts(self, original_work_cache=None):
    attempts = []
    if self.USE_SFADB_SOURCE:
      attempts.append(SourceAttempt(
        'SFADB',
        self.URL,
        lambda html, _url, **kwargs: self.parse(html, **kwargs),
        source_rank=0))
    isfdb_url = self.isfdb_url()
    if isfdb_url:
      attempts.append(ISFDBSourceAttempt(
        self.ISFDB_SOURCE_LABEL,
        isfdb_url,
        lambda html, url, **kwargs: self.parse_isfdb_source(
          html, url, original_work_cache=original_work_cache, **kwargs),
        source_rank=len(attempts),
        page_validator=self.isfdb_page_usable))
    return tuple(attempts)

  def source_choices(self):
    return SourceFallbackRunner(self.source_attempts()).source_choices()

  def fetch_and_parse(
      self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
      before_fetch=None, after_fetch=None, before_parse=None,
      force_fallback_level=0, disable_fallbacks=False, source_choice=None,
      original_work_cache=None):
    attempts = (self.source_attempts(original_work_cache=original_work_cache)
      if self.RESOLVE_ISFDB_ORIGINAL_WORKS else self.source_attempts())
    parsed = SourceFallbackRunner(
      attempts,
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

  def isfdb_page_usable(self, html, url):
    if self.RESOLVE_ISFDB_ORIGINAL_WORKS:
      try:
        from calibre_plugins.list_switchboard.parser.isfdb_title import parse_title_record, title_id
      except ImportError:
        from parser.isfdb_title import parse_title_record, title_id
      if title_id(url):
        parse_title_record(html, url, require_complete=False)
        return True
    if self.isfdb_year_urls(html, url):
      return True
    return bool(self.create_isfdb_parser().parse(
      html, url, self.NAME, self.CATEGORY, self.isfdb_category_aliases()).get('entries'))

  def isfdb_year_urls(self, html, base_url):
    urls = []
    for match in re.finditer(r'href=[\"\']([^\"\']*?/ay\.cgi\?\d+\+\d{4})', html or '', re.I):
      url = urljoin(base_url, match.group(1))
      if url not in urls:
        urls.append(url)
    return tuple(urls)

  def parse_isfdb_source(
      self, html, base_url, fetch_url=None, log=None, progress=None,
      original_work_cache=None):
    award_progress = progress
    if self.RESOLVE_ISFDB_ORIGINAL_WORKS and progress is not None:
      award_progress = lambda _done, _total, message: progress(0, 1, message)
    parsed = self.parse_isfdb_award_type(
      html, base_url, fetch_url=fetch_url, log=log, progress=award_progress)
    if self.RESOLVE_ISFDB_ORIGINAL_WORKS:
      from .isfdb_originals import resolve_original_works
      parsed = resolve_original_works(parsed, fetch_url,
        cached=original_work_cache, progress=progress)
    return parsed

  def parse_isfdb_award_type(
      self, html, base_url, fetch_url=None, log=None, progress=None):
    parser = self.create_isfdb_parser()
    if self.ISFDB_CATEGORY_ID:
      parsed = parser.parse(
        html, base_url, self.NAME, self.CATEGORY, self.isfdb_category_aliases())
      parsed['notes'] = list(self.ISFDB_SOURCE_NOTES) + list(parsed.get('notes', ()))
      if progress is not None:
        progress(1, 1, f'Finished reading ISFDB {self.CATEGORY}.')
      return parsed
    entries = []
    notes = list(self.ISFDB_SOURCE_NOTES)
    urls = self.isfdb_year_urls(html, base_url)
    for number, url in enumerate(urls, 1):
      year = url.rsplit('+', 1)[-1]
      if progress is not None:
        progress(number - 1, len(urls),
          f'Fetching ISFDB {self.CATEGORY}: {year} ({number} of {len(urls)} years)...')
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
      except ImportCancelledError:
        raise
      except Exception as err:
        notes.append(f'{self.AWARD_NAME} ISFDB year {url} could not be fetched: {err}')
        if log is not None:
          log(f'{self.AWARD_NAME} ISFDB year failed: {url}: {err}')
      if progress is not None:
        progress(number, len(urls), f'Processed ISFDB year {year} ({number} of {len(urls)}).')
    return {
      'name': self.NAME,
      'entries': sorted(
        entries,
        key=lambda entry: position_sort_key(entry.get('position', ''))),
      'notes': notes,
    }
