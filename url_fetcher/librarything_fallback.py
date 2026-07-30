#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Fetcher-side helper for LibraryThing award fallback sources.

Maintenance notes:
- LibraryThing stays a replacement fallback behind the recipe's preferred
  source. Fetchers still own category names, aliases, and award labels.
- LibraryThing may reject an otherwise valid browser identity with HTTP 403.
  Use the tested identity first, then a bounded set of Calibre-generated Chrome
  identities before allowing the source attempt to fail.
"""

try:
  from calibre.utils.random_ua import random_common_chrome_user_agent
except ImportError:
  random_common_chrome_user_agent = None

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError
except ImportError:
  from errors import ImportCancelledError

try:
  from calibre_plugins.list_switchboard.parser.source_fallback import SourceAttempt
except ImportError:
  from parser.source_fallback import SourceAttempt


LIBRARYTHING_USER_AGENT = (
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
  'AppleWebKit/537.36 (KHTML, like Gecko) '
  'Chrome/150.0.0.0 Safari/537.36'
)


class LibraryThingFetchPolicyMixin:
  """Retry LibraryThing with a small set of current Chrome identities."""

  LIBRARYTHING_RANDOM_USER_AGENT_ATTEMPTS = 2
  _session_librarything_user_agent = ''

  def fetch_librarything_url(self, fetch_url, url):
    last_error = None
    for user_agent in self.librarything_user_agents():
      try:
        payload = self.fetch_with_librarything_user_agent(
          fetch_url, url, user_agent)
        LibraryThingFetchPolicyMixin._session_librarything_user_agent = user_agent
        return payload
      except ImportCancelledError:
        raise
      except Exception as err:
        last_error = err
    if last_error is not None:
      raise last_error
    return fetch_url(url)

  def librarything_user_agents(self):
    user_agents = set()
    cached = LibraryThingFetchPolicyMixin._session_librarything_user_agent
    if cached:
      user_agents.add(cached)
      yield cached
    if LIBRARYTHING_USER_AGENT not in user_agents:
      user_agents.add(LIBRARYTHING_USER_AGENT)
      yield LIBRARYTHING_USER_AGENT
    for _attempt in range(self.LIBRARYTHING_RANDOM_USER_AGENT_ATTEMPTS):
      try:
        generated = self.random_librarything_user_agent()
      except Exception:
        continue
      if generated and generated not in user_agents:
        user_agents.add(generated)
        yield generated

  def fetch_with_librarything_user_agent(self, fetch_url, url, user_agent):
    try:
      return fetch_url(url, user_agent=user_agent)
    except TypeError as err:
      if 'user_agent' not in str(err) and 'keyword' not in str(err):
        raise
      return fetch_url(url)

  def random_librarything_user_agent(self):
    if random_common_chrome_user_agent is None:
      return ''
    return random_common_chrome_user_agent()


class LibraryThingSourceAttempt(SourceAttempt):

  def __init__(self, owner, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.owner = owner

  def fetch_url(self, fetch_url):
    if fetch_url is None:
      return None
    return lambda url: self.owner.fetch_librarything_url(fetch_url, url)


class LibraryThingAwardFallbackMixin(LibraryThingFetchPolicyMixin):

  LIBRARYTHING_URL = ''
  LIBRARYTHING_AWARD_NAME = ''

  def create_librarything_parser(self):
    try:
      from calibre_plugins.list_switchboard.parser.librarything_base import (
        LibraryThingAwardParserBase,
      )
    except ImportError:
      from parser.librarything_base import LibraryThingAwardParserBase

    parser = LibraryThingAwardParserBase()
    parser.AWARD_NAME = self.LIBRARYTHING_AWARD_NAME or self.AWARD_NAME
    return parser

  def librarything_attempt(self, source_rank=1):
    parser = self.create_librarything_parser()
    return LibraryThingSourceAttempt(
      self,
      'LibraryThing',
      self.LIBRARYTHING_URL,
      lambda html, url, **_kwargs: parser.parse(
        html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES),
      source_rank=source_rank)
