#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Parser for Reese's Book Club main monthly picks."""

from urllib.parse import urljoin

from .book_club_base import (
  BookClubParserBase, clean_author, clean_title, parse_month, parse_season,
  parse_year, text_blocks,
)


class ReeseBookClubParser(BookClubParserBase):

  CLUB_NAME = "Reese's Book Club"
  DEFAULT_SCOPE = 'main_monthly'
  DEFAULT_SELECTION_TYPE = 'monthly_pick'

  def entries_from_soup(self, soup, base_url, scope):
    entries = self.entries_from_pick_archive(soup, base_url, scope)
    return entries or super().entries_from_soup(soup, base_url, scope)

  def entries_from_pick_archive(self, soup, base_url, scope):
    blocks = text_blocks(soup)
    labels_by_title = {}
    for index, (_node, text) in enumerate(blocks):
      if not text.startswith('Image: '):
        continue
      title = clean_title(text[7:])
      for _next_node, next_text in blocks[index + 1:index + 4]:
        if 'pick' in next_text.casefold():
          labels_by_title.setdefault(title.casefold(), next_text)
          break
    entries = []
    seen = set()
    for index, (node, text) in enumerate(blocks):
      if not text or text.startswith('Image: '):
        continue
      title = clean_title(text)
      label = labels_by_title.get(title.casefold(), '')
      if not label:
        continue
      author = ''
      for _next_node, next_text in blocks[index + 1:index + 4]:
        if next_text.casefold().startswith('by '):
          author = clean_author(next_text)
          break
      if not author:
        continue
      link = node if getattr(node, 'name', '') == 'a' and node.get('href') else None
      entry_url = urljoin(base_url, link.get('href')) if link else base_url
      entry = self.build_entry({
        'title': title,
        'author': author,
        'selection_label': label,
        'selection_year': parse_year(label),
        'selection_month': parse_month(label),
        'season': parse_season(label),
      }, f'{label} {title} by {author}', entry_url, scope, len(entries) + 1, base_url=base_url)
      if entry is not None:
        key = self.entry_key(entry)
        if key in seen:
          if entry.get('source'):
            for existing in entries:
              if self.entry_key(existing) == key:
                existing['source'] = entry['source']
                break
          continue
        seen.add(key)
        entries.append(entry)
    return entries

  def accept_entry(self, entry, text):
    normalized = text.casefold()
    label = entry.get('selection_label', '').casefold()
    if 'ya pick' in normalized or 'young adult' in normalized or '_ya' in entry.get('club_scope', ''):
      return False
    if any(season in label for season in ('spring', 'summer', 'fall', 'winter')):
      return False
    if 'gone before goodbye' in entry.get('title', '').casefold():
      return False
    return bool(entry.get('selection_month') or entry.get('selection_year'))

  def complete_entry(self, entry, text):
    lowered = text.casefold()
    if 'short story' in lowered:
      entry['scope_flags'] = 'short_story_collection'
    return entry
