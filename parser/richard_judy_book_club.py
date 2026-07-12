#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Parser for Richard & Judy Book Club campaign picks."""

import re
from urllib.parse import urljoin

from .book_club_base import BookClubParserBase, clean_author, clean_title, normalize_line, text_blocks
from .generic import position_sort_key


class RichardJudyBookClubParser(BookClubParserBase):

  CLUB_NAME = 'Richard & Judy Book Club'
  DEFAULT_SCOPE = 'campaign_picks'
  DEFAULT_SELECTION_TYPE = 'seasonal_pick'

  def entry_sort_key(self, entry):
    try:
      year = int(entry.get('selection_year') or 9999)
    except (TypeError, ValueError):
      year = 9999
    # BookNotification's table is already chronological inside each year.
    # Preserve that order so annual picks remain before later Summer picks.
    return year, position_sort_key(entry.get('position', ''))

  def entries_from_soup(self, soup, base_url, scope):
    if 'booknotification.com' in (base_url or '').casefold():
      # The complete-history page has one stable five-column table, while its
      # surrounding search/navigation cards resemble generic book cards and
      # can otherwise become false selections.
      return self.finalize_entries(self.table_entries(soup, base_url, scope))
    entries = self.entries_from_latest_bundle_text(soup, base_url, scope)
    return entries or self.entries_from_latest_section(soup, base_url, scope) or super().entries_from_soup(soup, base_url, scope)

  def entries_from_latest_bundle_text(self, soup, base_url, scope):
    text = normalize_line(soup.get_text(' ', strip=True))
    match = re.search(r'latest picks include;?\s*(.+?)(?:\.|RRP|Add to basket)', text, re.I)
    if match is None:
      return []
    entries = []
    quoted_title = r'[\'\u2018\u2019]([^\'\u2018\u2019]+)[\'\u2018\u2019]'
    author_until_next_title = (
      r'(.+?)(?=(?:,\s*(?:and\s*)?[\'\u2018\u2019])|'
      r'(?:\s+and\s+[\'\u2018\u2019])|$)')
    for title, author in re.findall(
        rf'{quoted_title}\s+by\s+{author_until_next_title}',
        match.group(1)):
      entry = self.build_entry({
        'title': clean_title(title),
        'author': clean_author(author),
        'selection_label': 'latest pick set',
      }, f'latest pick set {title} by {author}', base_url, scope, len(entries) + 1, base_url=base_url)
      if entry is not None:
        entries.append(entry)
    return entries

  def entries_from_latest_section(self, soup, base_url, scope):
    blocks = text_blocks(soup)
    in_latest = False
    entries = []
    for index, (node, text) in enumerate(blocks):
      lowered = text.casefold()
      if 'latest richard' in lowered and 'judy book club picks' in lowered:
        in_latest = True
        continue
      if in_latest and ('you may also like' in lowered or 'archive' in lowered):
        break
      if not in_latest or text.startswith('By '):
        continue
      author = ''
      for _next_node, next_text in blocks[index + 1:index + 4]:
        if next_text.startswith('By '):
          author = clean_author(next_text)
          break
      if not author:
        continue
      entry_url = (
        urljoin(base_url, node.get('href'))
        if getattr(node, 'name', '') == 'a' and node.get('href') else base_url)
      entry = self.build_entry({
        'title': clean_title(text),
        'author': author,
        'selection_label': 'latest pick set',
      }, f'latest pick set {text} by {author}', entry_url, scope, len(entries) + 1, base_url=base_url)
      if entry is not None:
        entries.append(entry)
    return entries

  def accept_entry(self, entry, text):
    normalized = text.casefold()
    if 'archive' in normalized and not entry.get('selection_year'):
      return False
    return bool(
      entry.get('selection_year') or entry.get('season') or
      'latest pick' in normalized or 'current campaign' in normalized)

  def complete_entry(self, entry, _text):
    entry['selection_type'] = 'seasonal_pick'
    if entry.get('selection_label') == 'latest pick set':
      entry.pop('season', None)
    entry['advocate_defender_host_selector'] = (
      entry.get('advocate_defender_host_selector') or 'Richard Madeley; Judy Finnigan')
    return entry
