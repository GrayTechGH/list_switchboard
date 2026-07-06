#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Parser for Oprah's Book Club primary selections."""

from urllib.parse import urljoin

from .book_club_base import (
  BookClubParserBase, clean_author, clean_title, parse_year, split_title_author,
  text_blocks,
)


class OprahBookClubParser(BookClubParserBase):

  CLUB_NAME = "Oprah's Book Club"
  DEFAULT_SCOPE = 'primary_selections'
  DEFAULT_SELECTION_TYPE = 'primary_pick'

  def entries_from_soup(self, soup, base_url, scope):
    entries = self.entries_from_numbered_lines(soup, base_url, scope)
    return entries or super().entries_from_soup(soup, base_url, scope)

  def entries_from_numbered_lines(self, soup, base_url, scope):
    blocks = text_blocks(soup)
    entries = []
    seen_numbers = set()
    for index, (node, text) in enumerate(blocks):
      if not text.isdigit():
        continue
      number = int(text)
      if number < 1 or number > 250 or number in seen_numbers:
        continue
      title = author = ''
      source_url = base_url
      for lookahead_node, lookahead_text in blocks[index + 1:index + 6]:
        title, author = split_title_author(lookahead_text)
        if title and author:
          link = lookahead_node if getattr(lookahead_node, 'name', '') == 'a' else None
          if link is not None and link.get('href'):
            source_url = urljoin(base_url, link.get('href'))
          break
      if not title or not author:
        continue
      entry = {
        'position': str(number),
        'title': clean_title(title),
        'author': clean_author(author),
        'source_url': source_url,
        'club': self.CLUB_NAME,
        'club_scope': self.era_for_entry(number, ''),
        'selection_type': self.DEFAULT_SELECTION_TYPE,
        'selection_label': str(number),
      }
      entries.append(self.complete_entry(entry, ' '.join(
        item[1] for item in blocks[index:index + 8])))
      seen_numbers.add(number)
    return entries

  def complete_entry(self, entry, text):
    rank = entry.get('position', '')
    try:
      rank_int = int(float(rank))
    except Exception:
      rank_int = 0
    if rank_int:
      entry['selection_label'] = entry.get('selection_label') or str(rank_int)
      entry['club_scope'] = self.era_for_entry(rank_int, entry.get('selection_year') or parse_year(text))
    lowered = text.casefold()
    flags = []
    if 'nonfiction' in lowered or 'memoir' in lowered:
      flags.append('nonfiction' if 'nonfiction' in lowered else 'memoir')
    if 'classic' in lowered or 'backlist' in lowered:
      flags.append('classic')
      entry['selection_type'] = 'classic_pick'
    if 'reread' in lowered or 'same book twice' in lowered:
      flags.append('reread')
      entry['selection_type'] = 'reread_pick'
    if flags:
      entry['scope_flags'] = ', '.join(dict.fromkeys(flags))
    return entry

  def era_for_entry(self, rank, year):
    try:
      year = int(year or 0)
    except Exception:
      year = 0
    if rank >= 109 or year >= 2024:
      return 'starbucks_primary'
    if rank >= 81 or year >= 2019:
      return 'apple_primary'
    if rank >= 18 or year >= 2012:
      return 'book_club_2_primary'
    return 'original_primary'
