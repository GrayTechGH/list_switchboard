#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

try:
  from calibre_plugins.list_switchboard.http_policy import random_user_agent
except ImportError:
  from http_policy import random_user_agent

from .generic import (
  CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS, UrlFetcherError, UrlFetcherGeneric,
)


class UrlFetcherBarnesNobleBookClub(UrlFetcherGeneric):

  source_id = 'barnes_noble_book_club'
  NAME = 'Barnes & Noble Book Club'
  URL = 'https://www.booknotification.com/book-clubs/barnes-noble-book-club/'
  USER_AGENT_RETRIES = 2
  order = 51
  FILTER_CATEGORIES = (CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,)
  options = {'match_series': False}

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.barnes_noble_book_club import (
        BarnesNobleBookClubParser,
      )
    except ImportError:
      from parser.barnes_noble_book_club import BarnesNobleBookClubParser
    return BarnesNobleBookClubParser()

  def fetch_url(self, fetch_url, url):
    tried = set()
    user_agent = self.random_user_agent()
    html = self.fetch_with_user_agent(fetch_url, url, user_agent)
    tried.add(user_agent)
    if not self.browser_update_required(html):
      return html

    for _attempt in range(self.USER_AGENT_RETRIES):
      user_agent = self.random_user_agent()
      if not user_agent or user_agent in tried:
        continue
      tried.add(user_agent)
      html = self.fetch_with_user_agent(fetch_url, url, user_agent)
      if not self.browser_update_required(html):
        return html
    return html

  def fetch_with_user_agent(self, fetch_url, url, user_agent):
    try:
      return fetch_url(url, user_agent=user_agent)
    except TypeError as err:
      if 'user_agent' not in str(err) and 'keyword' not in str(err):
        raise
      return fetch_url(url)

  def random_user_agent(self):
    return random_user_agent()

  def browser_update_required(self, html):
    response_text = (
      html.decode('utf-8', errors='ignore')
      if isinstance(html, bytes) else str(html or '')
    )
    return 'Browser Update Required' in response_text

  def parse(self, html, **_kwargs):
    if self.browser_update_required(html):
      raise UrlFetcherError(
        'BookNotification rejected this import\'s browser identity as outdated. '
        'Calibre-generated browser identities were also rejected. '
        'Please report this error if it persists.')
    return self.parser().parse(html, self.URL, self.NAME)
