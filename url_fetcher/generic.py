#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

try:
  from urllib.parse import urlparse
except ImportError:
  urlparse = None

try:
  from calibre_plugins.list_switchboard.parser.base import (
    CATEGORY_FANTASY,
    CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,
    CATEGORY_HORROR_DARK_FICTION,
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_NONFICTION,
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
    CATEGORY_ROMANCE,
    CATEGORY_SCIENCE_FICTION,
    CATEGORY_UNKNOWN,
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_CRIME_MYSTERY_THRILLER,
    DEFAULT_FILTER_CATEGORIES,
    ListParserBase,
  )
except ImportError:
  from parser.base import (
    CATEGORY_FANTASY,
    CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,
    CATEGORY_HORROR_DARK_FICTION,
    CATEGORY_LITERARY_GENERAL_FICTION,
    CATEGORY_NONFICTION,
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    CATEGORY_REGIONAL_NATIONAL_AWARDS,
    CATEGORY_ROMANCE,
    CATEGORY_SCIENCE_FICTION,
    CATEGORY_UNKNOWN,
    CATEGORY_YOUNG_ADULT_CHILDRENS_LITERATURE,
    CATEGORY_CRIME_MYSTERY_THRILLER,
    DEFAULT_FILTER_CATEGORIES,
    ListParserBase,
  )


class UrlFetcherGeneric:

  source_id = ''
  NAME = ''
  URL = ''
  FETCH_URLS = ()
  order = 0
  options = {}
  schemas = ()
  FILTER_CATEGORIES = DEFAULT_FILTER_CATEGORIES
  PARSER_CLASS = ListParserBase
  REQUIRES_SERIES_MATCHING = False

  @property
  def name(self):
    return self.NAME

  @property
  def display_url(self):
    return self.URL

  def primary_urls(self):
    return tuple(self.FETCH_URLS or ((self.URL,) if self.URL else ()))

  def fallback_urls(self, _url):
    return ()

  def source_label_for_url(self, url, index):
    if urlparse is None:
      return 'Main source' if index == 0 else f'Fallback source {index}'
    parsed = urlparse(url)
    host = (parsed.netloc or '').lower()
    if 'swordandlaser.fandom.com' in host:
      if parsed.path.endswith('/api.php'):
        return 'Fandom API'
      if parsed.query == 'action=raw':
        return 'Fandom raw page'
      if '/wiki/Special:Export/' in parsed.path:
        return 'Fandom export'
      return 'Fandom wiki page'
    if host.startswith('www.'):
      host = host[4:]
    if host:
      return host
    return 'Main source' if index == 0 else f'Fallback source {index}'

  def source_choices(self):
    urls = self.fetch_urls(disable_fallbacks=False)
    choices = [{'label': 'Automatic', 'value': 'automatic'}]
    if len(urls) <= 1:
      return tuple(choices)
    for index, url in enumerate(urls):
      label = self.source_label_for_url(url, index)
      choices.append({'label': label, 'value': index})
    return tuple(choices)

  def fetch_urls(self, disable_fallbacks=False):
    urls = []
    for url in self.primary_urls():
      self.add_unique_url(urls, url)
      if disable_fallbacks:
        continue
      for fallback_url in self.fallback_urls(url):
        self.add_unique_url(urls, fallback_url)
    return tuple(urls)

  def add_unique_url(self, urls, url):
    if url and url not in urls:
      urls.append(url)

  def create_parser(self):
    return self.PARSER_CLASS()

  def parser(self):
    parser = self.create_parser()
    if hasattr(parser, 'configure_filter_categories'):
      parser.configure_filter_categories(self.FILTER_CATEGORIES)
    return parser

  def get_filter_list(self):
    return self.parser().get_filter_list()

  def fetch_and_parse(
      self, fetch_url, sleep=None, fetch_error=None, log=None, progress=None,
      before_fetch=None, after_fetch=None, before_parse=None,
      force_fallback_level=0, disable_fallbacks=False, source_choice=None):
    last_error = None
    errors = []
    urls = self.fetch_urls(disable_fallbacks=disable_fallbacks)
    force_fallback_level = int(force_fallback_level or 0)
    if source_choice is not None and source_choice != 'automatic':
      try:
        source_index = int(source_choice)
      except Exception:
        source_index = -1
      all_urls = self.fetch_urls(disable_fallbacks=False)
      if source_index < 0 or source_index >= len(all_urls):
        raise UrlFetcherError(
          f'No URL fallback exists for selected source {source_choice}.')
      urls = (all_urls[source_index],)
      if log is not None:
        log(f'URL fallback limited to level {source_choice}')
    elif force_fallback_level > 0 and not disable_fallbacks:
      urls = urls[force_fallback_level:]
      if log is not None:
        log(f'URL fallback forced to level {force_fallback_level}')
      if not urls:
        raise UrlFetcherError(
          f'No URL fallback exists for forced level {force_fallback_level}.')
    for url in urls:
      try:
        if before_fetch is not None:
          before_fetch(url)
        html = fetch_url(url)
        if after_fetch is not None:
          after_fetch(url, html)
        if before_parse is not None:
          before_parse(url)
        parsed = self.parse(
          html,
          fetch_url=fetch_url,
          sleep=sleep,
          fetch_error=fetch_error,
          log=log,
          progress=progress)
        parsed.setdefault('source_url', url)
        parsed.setdefault('match_series', self.options.get('match_series', True))
        return parsed
      except Exception as err:
        last_error = err
        errors.append(f'{url}: {err}')
    if last_error is not None:
      raise UrlFetcherError(
        'Could not fetch or parse the imported list.\n\nTried:\n- ' + '\n- '.join(errors))
    raise UrlFetcherError('The URL fetcher did not define a URL to import.')

  def parse(self, _html, **_kwargs):
    raise NotImplementedError


class UrlFetcherError(Exception):
  pass
