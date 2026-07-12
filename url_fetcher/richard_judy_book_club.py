#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

from .generic import (
  CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS, UrlFetcherError, UrlFetcherGeneric,
)


class UrlFetcherRichardJudyBookClub(UrlFetcherGeneric):

  source_id = 'richard_judy_book_club'
  NAME = 'Richard & Judy Book Club'
  URL = 'https://www.tgjonesonline.co.uk/books/book-club'
  BOOK_NOTIFICATION_URL = (
    'https://www.booknotification.com/book-clubs/richard-judy-book-club/')
  # BookNotification rejects the plugin's older default Chrome identity with a
  # successful "Browser Update Required" page instead of the history table.
  BOOK_NOTIFICATION_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/150.0.0.0 Safari/537.36'
  )
  USER_AGENT_RETRIES = 2
  _session_book_notification_user_agent = ''
  order = 53
  FILTER_CATEGORIES = (CATEGORY_GENERAL_AUDIENCE_BOOK_CLUBS,)
  options = {'match_series': False}

  def fallback_urls(self, url):
    return (self.BOOK_NOTIFICATION_URL,) if url == self.URL else ()

  def create_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.richard_judy_book_club import (
        RichardJudyBookClubParser,
      )
    except ImportError:
      from parser.richard_judy_book_club import RichardJudyBookClubParser
    return RichardJudyBookClubParser()

  def fetch_url(self, fetch_url, url):
    if url != self.BOOK_NOTIFICATION_URL:
      return super().fetch_url(fetch_url, url)
    tried = set()
    user_agent = (
      type(self)._session_book_notification_user_agent or
      self.BOOK_NOTIFICATION_USER_AGENT)
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
        type(self)._session_book_notification_user_agent = user_agent
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
    try:
      from calibre.utils.random_ua import random_common_chrome_user_agent
      return random_common_chrome_user_agent()
    except Exception:
      return ''

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
        'Calibre-generated browser identities were also rejected.')
    base_url = (
      self.BOOK_NOTIFICATION_URL
      if 'Richard &amp; Judy Book Club Picks' in (html or '') or
      'Richard & Judy Book Club Picks' in (html or '')
      else self.URL)
    parsed = self.parser().parse(html, base_url, self.NAME)
    if not parsed.get('entries'):
      raise UrlFetcherError(
        'The fetched Richard & Judy page did not contain recognizable book-club picks.')
    return parsed
