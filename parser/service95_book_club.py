#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Parser for Service95 Book Club monthly reads."""

import re

from .book_club_base import (
  BookClubParserBase, image_alt_blocks, normalize_line, parse_month, parse_year,
  split_title_author,
)


class Service95BookClubParser(BookClubParserBase):

  CLUB_NAME = 'Service95 Book Club'
  DEFAULT_SCOPE = 'full_monthly_list'
  DEFAULT_SELECTION_TYPE = 'monthly_pick'

  def entries_from_soup(self, soup, base_url, scope):
    entries = []
    for _node, text in image_alt_blocks(soup):
      normalized = normalize_line(text)
      if 'monthly read' not in normalized.casefold() and "dua's" not in normalized.casefold():
        continue
      title_author_text = re.sub(r"^.*?(?:Monthly Read|Read)\s*(?:for\s+\w+)?\s*[-:]\s*", '', normalized, flags=re.I)
      match = re.search(r'\bRead\s+(.+?)\s+by\s+(.+?)(?:\s+-\s+.*)?$', normalized, re.I)
      if match:
        title, author = match.group(1), match.group(2)
      else:
        title, author = split_title_author(title_author_text)
      if not title or not author:
        title, author = split_title_author(normalized)
      if not title or not author:
        continue
      entry = self.build_entry({
        'title': title,
        'author': author,
        'selection_label': normalized,
        'selection_year': parse_year(normalized),
        'selection_month': parse_month(normalized),
      }, normalized, base_url, scope, len(entries) + 1)
      if entry is not None:
        entries.append(entry)
    return entries or super().entries_from_soup(soup, base_url, scope)

  def complete_entry(self, entry, text):
    lowered = text.casefold()
    flags = []
    for marker, flag in (
        ('memoir', 'memoir'),
        ('essay', 'essay_collection'),
        ('nonfiction', 'nonfiction'),
        ('play', 'play'),
        ('classic', 'classic')):
      if marker in lowered:
        flags.append(flag)
    if flags:
      entry['scope_flags'] = ', '.join(dict.fromkeys(flags))
    entry['advocate_defender_host_selector'] = (
      entry.get('advocate_defender_host_selector') or 'Dua Lipa')
    return entry
