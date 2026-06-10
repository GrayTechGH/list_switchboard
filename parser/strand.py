#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
The Strand Critics Award parsers.

Maintenance notes:
- V1 keeps Strand on the shared LibraryThing award parser because the verified
  import shape is already the standard Winner/Nominee award table/list format.
- Official Strand Magazine pages remain reference-only for now because nominee
  and winner history is scattered across year-specific posts.
"""

try:
  from calibre_plugins.list_switchboard.parser.librarything_base import (
    LibraryThingAwardParserBase,
  )
except ImportError:
  from .librarything_base import LibraryThingAwardParserBase


AWARD_NAME = 'The Strand Critics Award'


class StrandLibraryThingParser(LibraryThingAwardParserBase):
  AWARD_NAME = AWARD_NAME


def parse_strand_librarything(html, base_url, name, category, category_aliases=()):
  return StrandLibraryThingParser().parse(
    html, base_url, name, category, category_aliases)
