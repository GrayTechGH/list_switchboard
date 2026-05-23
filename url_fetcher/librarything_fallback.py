#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Fetcher-side helper for LibraryThing award fallback sources.

Maintenance notes:
- LibraryThing stays a replacement fallback behind the recipe's preferred
  source. Fetchers still own category names, aliases, and award labels.
"""

try:
  from calibre_plugins.list_switchboard.parser.source_fallback import SourceAttempt
except ImportError:
  from parser.source_fallback import SourceAttempt


class LibraryThingAwardFallbackMixin:

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
    return SourceAttempt(
      'LibraryThing',
      self.LIBRARYTHING_URL,
      lambda html, url, **_kwargs: parser.parse(
        html, url, self.NAME, self.CATEGORY, self.CATEGORY_ALIASES),
      source_rank=source_rank)
