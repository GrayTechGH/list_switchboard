#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Parser for Read With Jenna main monthly selections."""

from urllib.parse import urljoin

from .book_club_base import BookClubParserBase, parse_month, parse_year, split_title_author, text_blocks


class ReadWithJennaParser(BookClubParserBase):

  CLUB_NAME = 'Read With Jenna'
  DEFAULT_SCOPE = 'main_monthly'
  DEFAULT_SELECTION_TYPE = 'monthly_pick'

  def entries_from_soup(self, soup, base_url, scope):
    entries = []
    seen = set()
    current_label = ''
    for node, text in text_blocks(soup):
      if parse_month(text) and parse_year(text) and len(text) < 30:
        current_label = text
        continue
      title, author = split_title_author(text)
      if not title or not author or not current_label:
        continue
      source_url = (
        urljoin(base_url, node.get('href'))
        if getattr(node, 'name', '') == 'a' and node.get('href') else base_url)
      entry = self.build_entry({
        'title': title,
        'author': author,
        'selection_label': current_label,
        'selection_year': parse_year(current_label),
        'selection_month': parse_month(current_label),
      }, f'{current_label} {text}', source_url, scope, len(entries) + 1)
      if entry is not None:
        key = self.entry_key(entry)
        if key in seen:
          if entry.get('source_url') != base_url:
            for existing in entries:
              if self.entry_key(existing) == key:
                existing['source_url'] = entry.get('source_url', existing['source_url'])
                break
          continue
        seen.add(key)
        entries.append(entry)
    return entries or super().entries_from_soup(soup, base_url, scope)

  def accept_entry(self, entry, text):
    normalized = f"{text} {entry.get('selection_label', '')}".casefold().replace('.', '')
    return 'jenna jr' not in normalized and 'read with jenna jr' not in normalized

  def complete_entry(self, entry, text):
    lowered = text.casefold()
    if 'classic' in lowered or entry.get('title') == 'Pride and Prejudice':
      entry['selection_type'] = 'classic_pick'
      entry['scope_flags'] = 'classic'
    if 'essay' in lowered or entry.get('title') == 'Here for It':
      entry['selection_type'] = 'special_pick'
      entry['scope_flags'] = 'essay_collection'
    return entry
