#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Parser for Canada Reads contenders and winners."""

from .book_club_base import BookClubParserBase


class CanadaReadsParser(BookClubParserBase):

  CLUB_NAME = 'Canada Reads'
  DEFAULT_SCOPE = 'yearly_contenders_and_winner'
  DEFAULT_SELECTION_TYPE = 'contender'

  def complete_entry(self, entry, text):
    if 'winner' in text.casefold():
      entry['selection_type'] = 'winner'
    elif entry.get('selection_type') != 'winner':
      entry['selection_type'] = 'contender'
    return entry

  def finalize_entries(self, entries):
    winners = {
      (entry.get('title', '').casefold(), entry.get('author', '').casefold(), entry.get('selection_year', ''))
      for entry in entries
      if entry.get('selection_type') == 'winner'
    }
    grouped = {}
    order = []
    for entry in entries:
      year = entry.get('selection_year', '')
      grouped.setdefault(year, [])
      if year not in order:
        order.append(year)
    result = []
    skipped = set()
    for entry in entries:
      key = (entry.get('title', '').casefold(), entry.get('author', '').casefold(), entry.get('selection_year', ''))
      if key in skipped:
        continue
      if key in winners:
        entry = dict(entry)
        entry['selection_type'] = 'winner'
        skipped.add(key)
      grouped.setdefault(entry.get('selection_year', ''), []).append(entry)
    for year in order:
      year_rows = grouped.get(year, ())
      suffix = 0
      winner_seen = False
      for entry in year_rows:
        entry = dict(entry)
        if entry.get('selection_type') == 'winner' and not winner_seen and year:
          entry['position'] = year
          winner_seen = True
        elif year:
          suffix += 1
          entry['position'] = f'{year}.{suffix:02d}'
        result.append(entry)
    return result
