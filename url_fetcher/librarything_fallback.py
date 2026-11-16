#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Fetcher-side helper for LibraryThing award fallback sources.

Maintenance notes:
- LibraryThing stays a replacement fallback behind the recipe's preferred
  source. Fetchers still own category names, aliases, and award labels.
- On Calibre 9.16+, the Calibre-facing fetch callback may provide the optional
  Camoufox transport. This policy tries it before the bounded legacy identities
  while keeping editorial source rank unchanged.
- LibraryThing may reject an otherwise valid browser identity with HTTP 403.
  Use only freshly generated Calibre agents, with bounded retries before
  allowing the source attempt to fail.
"""

from urllib.parse import urlparse

try:
  from calibre_plugins.list_switchboard.http_policy import random_user_agent
except ImportError:
  from http_policy import random_user_agent

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError
except ImportError:
  from errors import ImportCancelledError

try:
  from calibre_plugins.list_switchboard.camoufox_transport import (
    CamoufoxError, CamoufoxRequiredError, CamoufoxSkippedError, is_challenge_payload,
  )
except ImportError:
  from camoufox_transport import (
    CamoufoxError, CamoufoxRequiredError, CamoufoxSkippedError, is_challenge_payload,
  )

try:
  from calibre_plugins.list_switchboard.parser.source_fallback import SourceAttempt
except ImportError:
  from parser.source_fallback import SourceAttempt


class LibraryThingFetchPolicyMixin:
  """Try Camoufox, then retry with a small set of Chrome identities."""

  LIBRARYTHING_RANDOM_USER_AGENT_ATTEMPTS = 3

  def fetch_librarything_url(self, fetch_url, url):
    host = (urlparse(url).hostname or '').casefold()
    if host != 'librarything.com' and not host.endswith('.librarything.com'):
      return fetch_url(url)
    try:
      payload = fetch_url(url, transport='camoufox')
      if is_challenge_payload(payload):
        raise CamoufoxError(
          'LibraryThing returned a browser verification page through Camoufox.')
      return payload
    except ImportCancelledError:
      raise
    except CamoufoxRequiredError:
      raise
    except CamoufoxSkippedError as err:
      self.log_librarything_transport(fetch_url, f'using old transport: {err}')
    except TypeError as err:
      # Older/test fetch callbacks do not know the transport keyword. They are
      # the same compatibility path used by Calibre versions before 9.16.
      if 'transport' not in str(err) and 'keyword' not in str(err):
        raise
      self.log_librarything_transport(
        fetch_url, 'Camoufox callback unavailable; using old transport')
    except CamoufoxError as err:
      self.log_librarything_transport(
        fetch_url, f'Camoufox failed; using old transport: {err}')
    last_error = None
    for user_agent in self.librarything_user_agents():
      try:
        self.log_librarything_transport(
          fetch_url, f'old transport attempt url={url} user_agent={user_agent}')
        payload = self.fetch_with_librarything_user_agent(
          fetch_url, url, user_agent)
        if is_challenge_payload(payload):
          raise RuntimeError(
            'LibraryThing returned a browser verification page.')
        return payload
      except ImportCancelledError:
        raise
      except Exception as err:
        last_error = err
        self.log_librarything_transport(
          fetch_url, f'old transport failed url={url}: {err}')
    if last_error is not None:
      raise last_error
    return fetch_url(url)

  def log_librarything_transport(self, fetch_url, message):
    owner = getattr(fetch_url, '__self__', None)
    log = getattr(owner, 'debug_camoufox', None)
    if log is not None:
      log(message)

  def librarything_user_agents(self):
    user_agents = set()
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
    return random_user_agent()


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
