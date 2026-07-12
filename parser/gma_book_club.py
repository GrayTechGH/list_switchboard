#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Parser for GMA Book Club main and YA monthly picks.

The GMA article renders commerce cards alongside everscroll news and sponsored
cards.  Its server-state JSON retains the important relationship between each
month heading and its product, so that is the primary source.  The HTML walk is
kept as a narrow fallback for fixtures and older page shapes.
"""

import json
import re
from urllib.parse import urljoin

from .book_club_base import (
  BookClubParserBase,
  clean_author,
  clean_title,
  parse_month,
  parse_year,
  text_blocks,
)


# Some GMA commerce headlines omit the author entirely.  These corrections are
# deliberately title-specific rather than inferred from retailer URLs, many of
# which are opaque Amazon short links.
MISSING_OR_CORRECTED_AUTHORS = {
  'age of vice': 'Deepti Kapoor',
  'atmosphere: a love story': 'Taylor Jenkins Reid',
  'colored television: a novel': 'Danzy Senna',
  'come and get it': 'Kiley Reid',
  'homeseeking': 'Karissa Chen',
  'ink blood sister scribe': 'Emma Törzs',
  'junie: a novel': 'Erin Crosby Eckstine',
  'just for the summer': 'Abby Jimenez',
  'listen for the lie: a novel': 'Amy Tintera',
  'heir': 'Sabaa Tahir',
  'skyshade (the lightlark saga book 3) (volume 3)': 'Alex Aster',
  'the otherwhere post': 'Emily J. Taylor',
  'the blue hour: a novel': 'Paula Hawkins',
  'the frozen river: a novel': 'Ariel Lawhon',
  'the last one': 'Rachel Howzell Hall',
  'the love of my afterlife': 'Kirsty Greenwood',
  'the ministry of time: a novel': 'Kaliane Bradley',
  'the sirens: a novel': 'Emilia Hart',
  'the storm we made: a novel': 'Vanessa Chan',
  'under the same stars': 'Libba Bray',
}


def split_gma_title_author(text):
  """Split the final ``by`` credit without treating title commas as delimiters."""
  text = re.sub(r'\s+', ' ', str(text or '')).strip()
  match = re.match(r'^(.+)\s+by\s+(.+)$', text, re.I)
  if match:
    title = re.sub(
      r'\s*:?[ ]*(?:(?:A\s+)?(?:GMA|Good\s+Morning\s+America)\s+'
      r'(?:YA\s+)?Book\s+Club\s+Pick|A\s+Novel)\s*$',
      '', match.group(1), flags=re.I)
    title = clean_title(title)
    author = clean_author(match.group(2))
  else:
    title = clean_title(text)
    author = ''
  corrected_author = MISSING_OR_CORRECTED_AUTHORS.get(title.casefold())
  title = re.sub(r'\s*:\s*A\s+Novel\s*$', '', title, flags=re.I)
  return title, corrected_author or author


def split_gma_authors(author):
  return [part.strip() for part in re.split(r'\s+(?:and|&)\s+', author) if part.strip()]


class GMABookClubParser(BookClubParserBase):

  CLUB_NAME = 'GMA Book Club'
  DEFAULT_SCOPE = 'main_monthly'
  DEFAULT_SELECTION_TYPE = 'monthly_pick'

  def entries_from_soup(self, soup, base_url, scope):
    structured_entries = self.entries_from_server_state(soup, base_url, scope)
    if structured_entries:
      return self.with_chronological_positions(structured_entries)

    entries = []
    seen = set()
    current_label = ''
    for node, text in text_blocks(soup):
      normalized = text.casefold()
      if normalized.startswith(("editor's note:", 'editor’s note:')):
        break
      if parse_month(text) and parse_year(text) and len(text) < 30:
        current_label = text
        continue
      title, author = split_gma_title_author(text)
      if not title or not author or not current_label:
        continue
      entry_url = (
        urljoin(base_url, node.get('href'))
        if getattr(node, 'name', '') == 'a' and node.get('href') else base_url)
      entry = self.build_entry({
        'title': title,
        'authors': split_gma_authors(author),
        'selection_label': current_label,
        'selection_year': parse_year(current_label),
        'selection_month': parse_month(current_label),
      }, f'{current_label} {text}', entry_url, scope, len(entries) + 1, base_url=base_url)
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
    if not entries:
      entries = super().entries_from_soup(soup, base_url, scope)
    return self.with_chronological_positions(entries)

  def with_chronological_positions(self, entries):
    """GMA publishes newest-first; list positions must increase oldest-first."""
    for position, entry in enumerate(sorted(entries, key=self.entry_sort_key), 1):
      entry['position'] = str(position)
    return entries

  def entries_from_server_state(self, soup, base_url, scope):
    body_items = self.server_state_body_items(soup)
    if not body_items:
      return []
    entries = []
    current_label = ''
    for item in body_items:
      item_type = item.get('type')
      content = item.get('content')
      if item_type in ('h2', 'h3'):
        current_label = self.rich_text(content)
        continue
      if item_type != 'inline' or not isinstance(content, dict):
        continue
      if content.get('name') != 'CommercePromo' or not current_label:
        continue
      props = content.get('props') or {}
      headline = props.get('headline') or props.get('imageAlt')
      title, author = split_gma_title_author(headline)
      if not title or not author:
        continue
      entry = self.build_entry({
        'title': title,
        'authors': split_gma_authors(author),
        'selection_label': current_label,
        'selection_year': parse_year(current_label),
        'selection_month': parse_month(current_label),
      }, f'{current_label} {headline}', base_url, scope, len(entries) + 1,
        base_url=base_url)
      if entry is not None:
        entries.append(entry)
    return entries

  def server_state_body_items(self, soup):
    marker = "window['__gma__']="
    for script in soup.find_all('script'):
      text = script.string or ''
      marker_at = text.find(marker)
      if marker_at < 0:
        continue
      try:
        state, _end = json.JSONDecoder().raw_decode(text[marker_at + len(marker):])
        components = state['page']['content']['article']['mainComponents']
      except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        continue
      for component in components:
        if component.get('name') != 'Body':
          continue
        groups = (component.get('props') or {}).get('body') or []
        return [
          item for group in groups if isinstance(group, list)
          for item in group if isinstance(item, dict)]
    return []

  def rich_text(self, content):
    if isinstance(content, str):
      return content
    if isinstance(content, list):
      return ''.join(self.rich_text(part) for part in content)
    if isinstance(content, dict):
      return self.rich_text(content.get('content'))
    return ''

  def accept_entry(self, _entry, text):
    normalized = text.casefold()
    return 'ya pick' not in normalized and 'young adult' not in normalized


class GMAYABookClubParser(GMABookClubParser):

  CLUB_NAME = 'GMA Book Club YA'
  DEFAULT_SCOPE = 'young_adult_monthly'

  def accept_entry(self, _entry, _text):
    return True
