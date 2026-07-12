#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_FANTASY,
  CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
  UrlFetcherGeneric,
)


class UrlFetcherReddit(UrlFetcherGeneric):

  FILTER_CATEGORIES = (
    CATEGORY_FANTASY,
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
  )
  WAYBACK_URL = ''
  WAYBACK_CAPTURE_DATE = ''
  WAYBACK_MARKER = '<!-- list-switchboard-r-fantasy-wayback -->'

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.reddit import RedditResultsParser
    except ImportError:
      from parser.reddit import RedditResultsParser

    return RedditResultsParser()

  def fetch_url(self, fetch_url, url):
    payload = super().fetch_url(fetch_url, url)
    if url == self.WAYBACK_URL and str(payload or '').lstrip().startswith('<'):
      return self.WAYBACK_MARKER + str(payload)
    return payload

  def parse(self, html, **_kwargs):
    archived = self.WAYBACK_MARKER in str(html or '')
    parsed = self.parser().parse(
      html, self.NAME, self.WAYBACK_URL if archived else self.URL, self.schemas)
    if archived:
      captured = self.WAYBACK_CAPTURE_DATE or 'an unknown date'
      parsed.setdefault('notes', []).append(
        f'Internet Archive snapshot captured {captured}; imported results use '
        'archived Reddit content.')
    return parsed
