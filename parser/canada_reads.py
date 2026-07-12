#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Parser for CBC's past Canada Reads contenders and winners article."""

import re
from urllib.parse import urljoin

from .base import author_list
from .book_club_base import BookClubParserBase, clean_author, clean_title, normalize_line


class CanadaReadsParser(BookClubParserBase):

  CLUB_NAME = 'Canada Reads'
  DEFAULT_SCOPE = 'yearly_contenders_and_winner'
  DEFAULT_SELECTION_TYPE = 'contender'

  def entries_from_soup(self, soup, base_url, scope):
    story = soup.select_one('div.story')
    entries = self.archive_entries(story, base_url, scope) if story is not None else []
    return entries or super().entries_from_soup(soup, base_url, scope)

  def archive_entries(self, story, base_url, scope):
    """Read each winner paragraph and its following contender list."""
    entries = []
    current_year = ''
    for node in story.find_all(['p', 'ul'], recursive=False):
      text = normalize_line(node.get_text(' ', strip=True))
      winner_match = re.search(r'\bwon Canada Reads ((?:19|20)\d{2})\b', text, re.I)
      if node.name == 'p' and winner_match:
        entry = self.archive_winner_entry(
          node, text, winner_match.group(1), base_url, scope, len(entries) + 1)
        if entry is not None:
          current_year = winner_match.group(1)
          entries.append(entry)
        continue
      if node.name != 'ul' or not current_year:
        continue
      for item in node.find_all('li', recursive=False):
        entry = self.archive_contender_entry(
          item, current_year, base_url, scope, len(entries) + 1)
        if entry is not None:
          entries.append(entry)
      current_year = ''
    return self.finalize_entries(entries)

  def archive_winner_entry(self, node, text, year, base_url, scope, index):
    title_node = node.find(['em', 'i'])
    title = clean_title(title_node.get_text(' ', strip=True)) if title_node else ''
    if not title:
      match = re.match(r'(.+?)\s+by\s+.+?\s*,?\s*won Canada Reads\s+', text, re.I)
      title = clean_title(match.group(1)) if match else ''
    tail = text[text.find(title) + len(title):] if title and title in text else text
    match = re.match(
      r'\s+by\s+(.+?)\s*,?\s*won Canada Reads\s+(?:19|20)\d{2}\b', tail, re.I)
    authors = self.archive_authors(match.group(1)) if match else []
    if not title or not authors:
      return None
    defender = self.archive_defender(text)
    link = title_node.find_parent('a', href=True) if title_node else None
    return self.build_entry({
      'title': title,
      'authors': authors,
      'selection_year': year,
      'selection_label': f'{year} winner',
      'selection_type': 'winner',
      'advocate_defender_host_selector': defender,
    }, text, urljoin(base_url, link['href']) if link else base_url,
      scope, index, base_url=base_url)

  def archive_contender_entry(self, item, year, base_url, scope, index):
    text = normalize_line(item.get_text(' ', strip=True)).replace('\u200b', '')
    match = re.match(
      r'^(.+?)\s+by\s+(.+?)\s*,\s*(?:championed|defended)\s+by\s+(.+?)\s*$',
      text, re.I)
    if match:
      title = clean_title(match.group(1))
      authors = self.archive_authors(match.group(2))
      defender = clean_author(match.group(3))
    else:
      match = re.match(r'^(.+?)\s+champions\s+(.+?)\s+by\s+(.+?)\s*$', text, re.I)
      if not match:
        return None
      defender = clean_author(match.group(1))
      title = clean_title(match.group(2))
      authors = self.archive_authors(match.group(3))
    if not title or not authors:
      return None
    link = next((
      anchor for anchor in item.find_all('a', href=True)
      if title in normalize_line(anchor.get_text(' ', strip=True)).replace('\u200b', '')
    ), None)
    return self.build_entry({
      'title': title,
      'authors': authors,
      'selection_year': year,
      'selection_label': f'{year} contender',
      'selection_type': 'contender',
      'advocate_defender_host_selector': defender,
    }, text, urljoin(base_url, link['href']) if link else base_url,
      scope, index, base_url=base_url)

  def archive_authors(self, value):
    value = re.split(r'\s+(?:and\s+)?translated\s+by\s+', value or '', maxsplit=1, flags=re.I)[0]
    value = re.sub(r',\s*with\s+', ' with ', value, flags=re.I)
    return [
      clean_author(author).replace('\u200b', '')
      for author in re.split(r'\s+(?:with|&)\s+', value)
      if clean_author(author)
    ]

  def archive_defender(self, text):
    match = re.search(r'\b(?:championed|defended)\s+by\s+(.+?)\s*\.?$', text, re.I)
    return clean_author(match.group(1)) if match else ''

  def complete_entry(self, entry, text):
    if 'winner' in text.casefold():
      entry['selection_type'] = 'winner'
    elif entry.get('selection_type') != 'winner':
      entry['selection_type'] = 'contender'
    return entry

  def finalize_entries(self, entries):
    winners = {
      (entry.get('title', '').casefold(), tuple(
        author.casefold() for author in author_list(entry.get('authors'))),
       entry.get('selection_year', ''))
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
      key = (entry.get('title', '').casefold(), tuple(
        author.casefold() for author in author_list(entry.get('authors'))),
       entry.get('selection_year', ''))
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
