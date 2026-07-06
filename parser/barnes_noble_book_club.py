#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Parser for explicit Barnes & Noble Book Club picks."""

from .book_club_base import BookClubParserBase


class BarnesNobleBookClubParser(BookClubParserBase):

  CLUB_NAME = 'Barnes & Noble Book Club'
  DEFAULT_SCOPE = 'main_club_only'
  DEFAULT_SELECTION_TYPE = 'monthly_pick'

  def accept_entry(self, _entry, text):
    normalized = text.casefold()
    if 'discover prize' in normalized or 'monthly picks' in normalized:
      return False
    return 'book club pick' in normalized or 'book club selection' in normalized

  def notes_for_entries(self, _entries):
    return ['Barnes & Noble historical discovery is fragile; only explicit Book Club picks are imported.']
