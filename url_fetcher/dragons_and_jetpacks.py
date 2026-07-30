#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""URL fetcher for the Dragons & Jetpacks Goodreads group-read shelf."""

from urllib.parse import parse_qs, urlparse

from .generic import (
  CATEGORY_FANTASY,
  CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
  CATEGORY_SCIENCE_FICTION,
  GoodreadsFetchPolicyMixin,
  UrlFetcherGeneric,
)


class UrlFetcherDragonsJetpacks(GoodreadsFetchPolicyMixin, UrlFetcherGeneric):

  source_id = 'dragons_and_jetpacks'
  NAME = 'Dragons & Jetpacks'
  URL = (
    'https://www.goodreads.com/group/bookshelf/106876-dragons-jetpacks'
    '?per_page=100&shelf=group-read')
  order = 58
  FILTER_CATEGORIES = (
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    CATEGORY_SCIENCE_FICTION,
    CATEGORY_FANTASY,
  )
  options = {'match_series': False}

  def source_choices(self):
    return ({'label': 'Automatic', 'value': 'automatic'},)

  def fetch_and_parse(self, fetch_url, *args, **kwargs):
    progress = kwargs.get('progress')
    if progress is None and len(args) > 3:
      progress = args[3]
    self._dragons_fetch_progress = progress
    try:
      return super().fetch_and_parse(fetch_url, *args, **kwargs)
    finally:
      self._dragons_fetch_progress = None

  def fetch_url(self, fetch_url, url):
    retries = self.timeout_retries(url)
    for retry in range(retries + 1):
      try:
        return self.fetch_url_once(fetch_url, url)
      except Exception as err:
        if retry >= retries or not self.is_timeout_error(err):
          raise
        self.timeout_retry_progress(
          getattr(self, '_dragons_fetch_progress', None),
          url,
          retry + 1,
          retries)

  def initial_fetch_progress(self, progress, _url):
    if progress is not None:
      progress(
        0, 1,
        f'Fetching {self.NAME} shelf page 1 (discovering page count)')

  def timeout_retry_progress(self, progress, url, retry, retries):
    if progress is None:
      return
    page_values = parse_qs(urlparse(url).query).get('page') or ['1']
    page_number = page_values[0] if page_values[0].isdigit() else '?'
    progress(
      0, 1,
      f'Goodreads timed out; retrying {self.NAME} shelf page {page_number} '
      f'(retry {retry} of {retries})')

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.dragons_and_jetpacks import ( # type: ignore
        DragonsJetpacksParser,
      )
    except ImportError:
      from parser.dragons_and_jetpacks import DragonsJetpacksParser
    return DragonsJetpacksParser()

  def parse(
      self, html, fetch_url=None, fetch_error=None, log=None, progress=None,
      **_kwargs):
    return self.parser().parse(
      html,
      self.URL,
      self.NAME,
      fetch_url=fetch_url,
      fetch_error=fetch_error,
      log=log,
      progress=progress)
