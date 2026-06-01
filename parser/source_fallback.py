#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Shared source-attempt fallback for parsers that can use multiple archives.

Maintenance notes:
- Fetchers remain the recipe boundary; this module only coordinates source
  attempts that each fetch and parse one root page.
- Source-specific linked-page failures should usually stay inside the parser
  attempt as notes when partial results are still useful.
"""


class SourceAttempt:
  """
  One parseable source in a fallback chain.

  Type constraints:
  - parser may be a callable or an object with parse().
  - usability_check receives the parsed dict and should return True when the
    result is good enough to stop trying fallback sources.
  """

  def __init__(
      self, label, url, parser, source_rank=0, usability_check=None,
      user_agent=None):
    self.label = label
    self.url = url
    self.parser = parser
    self.source_rank = source_rank
    self.usability_check = usability_check
    self.user_agent = user_agent

  def parse(self, html, fetch_url=None, log=None, progress=None):
    parser = self.parser
    fetch_url = self.fetch_url(fetch_url)
    if hasattr(parser, 'parse'):
      return parser.parse(
        html, self.url, fetch_url=fetch_url, log=log, progress=progress)
    return parser(
      html, self.url, fetch_url=fetch_url, log=log, progress=progress)

  def fetch_url(self, fetch_url):
    if fetch_url is None or not self.user_agent:
      return fetch_url

    def wrapped(url):
      try:
        return fetch_url(url, user_agent=self.user_agent)
      except TypeError as err:
        if 'user_agent' not in str(err) and 'keyword' not in str(err):
          raise
        return fetch_url(url)

    return wrapped

  def is_usable(self, parsed):
    if self.usability_check is not None:
      return self.usability_check(parsed)
    return bool(parsed and parsed.get('entries'))


class SourceFallbackError(Exception):
  pass


class SourceFallbackRunner:
  """
  Run source attempts in priority order and return the first usable result.

  Invariants:
  - Fetch, parse, and unusable-output failures are logged and recorded as notes.
  - Earlier failed-attempt notes are merged into the successful parsed result.
  - Only an all-source failure raises, using error_class when supplied.
  """

  def __init__(self, attempts, error_class=SourceFallbackError):
    self.attempts = tuple(sorted(attempts, key=lambda attempt: attempt.source_rank))
    self.error_class = error_class

  def source_choices(self):
    choices = [{'label': 'Automatic', 'value': 'automatic'}]
    if len(self.attempts) <= 1:
      return tuple(choices)
    for attempt in self.attempts:
      choices.append({'label': attempt.label, 'value': attempt.source_rank})
    return tuple(choices)

  def run(
      self, fetch_url, log=None, progress=None, before_fetch=None,
      after_fetch=None, before_parse=None, force_fallback_level=0,
      disable_fallbacks=False, source_choice=None):
    failures = []
    force_fallback_level = int(force_fallback_level or 0)
    attempts = self.attempts
    if source_choice is not None and source_choice != 'automatic':
      try:
        source_rank = int(source_choice)
      except Exception:
        source_rank = None
      attempts = tuple(
        attempt for attempt in attempts
        if attempt.source_rank == source_rank)
      if log is not None:
        log(f'Source fallback limited to level {source_choice}')
      if not attempts:
        raise self.error_class(
          f'No source fallback attempt exists for selected source {source_choice}.')
    elif disable_fallbacks:
      attempts = tuple(
        attempt for attempt in attempts
        if attempt.source_rank == 0)
      if log is not None:
        log('Source fallbacks disabled')
      if not attempts:
        raise self.error_class('No primary source attempt exists.')
    elif force_fallback_level > 0:
      attempts = tuple(
        attempt for attempt in attempts
        if attempt.source_rank >= force_fallback_level)
      if log is not None:
        log(f'Source fallback forced to level {force_fallback_level}')
      if not attempts:
        raise self.error_class(
          f'No source fallback attempt exists for forced level {force_fallback_level}.')
    for attempt in attempts:
      try:
        if before_fetch is not None:
          before_fetch(attempt.url)
        html = attempt.fetch_url(fetch_url)(attempt.url)
        if after_fetch is not None:
          after_fetch(attempt.url, html)
        if before_parse is not None:
          before_parse(attempt.url)
        parsed = attempt.parse(
          html, fetch_url=fetch_url, log=log, progress=progress)
        if not attempt.is_usable(parsed):
          raise ValueError('parsed result did not contain usable entries')
        parsed.setdefault('url', attempt.url)
        parsed.setdefault('source_url', attempt.url)
        parsed['notes'] = failures + list(parsed.get('notes', ()))
        return parsed
      except Exception as err:
        reason = str(err) or err.__class__.__name__
        note = f'{attempt.label} failed: {reason}'
        failures.append(note)
        if log is not None:
          log(f'Source fallback {attempt.label} failed: {reason}')
    raise self.error_class(
      'Could not fetch or parse the imported list.\n\nTried:\n- ' +
      '\n- '.join(failures))
