#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Parser for Barnes & Noble's current Book Club and monthly-picks pages."""

import re
from urllib.parse import urljoin

from .book_club_base import (
  BookClubParserBase, clean_author, clean_title, normalize_line, parse_month,
  parse_year,
)
from .generic import position_sort_key


class BarnesNobleBookClubParser(BookClubParserBase):

  CLUB_NAME = 'Barnes & Noble Book Club'
  DEFAULT_SCOPE = 'main_club_only'
  DEFAULT_SELECTION_TYPE = 'monthly_pick'
  CURRENT_SCOPE = 'current_book_club_pick'
  MONTHLY_SCOPE = 'monthly_picks_current'

  def entry_sort_key(self, entry):
    if entry.get('club_scope') in (self.CURRENT_SCOPE, self.MONTHLY_SCOPE):
      return (position_sort_key(entry.get('position', '')),)
    return super().entry_sort_key(entry)

  def entries_from_soup(self, soup, base_url, scope):
    entries = self.booknotification_entries(soup, base_url)
    if not entries:
      entries = self.recommended_more_entries(soup, base_url)
    if not entries:
      entries = self.product_highlight_entries(soup, base_url)
    return entries or super().entries_from_soup(soup, base_url, scope)

  def booknotification_entries(self, soup, base_url):
    entries = []
    seen = set()
    for table in soup.find_all('table'):
      for row in table.find_all('tr'):
        cells = [normalize_line(cell.get_text(' ', strip=True)) for cell in row.find_all(['td', 'th'])]
        if len(cells) < 5:
          continue
        label, author, title = cells[1], cells[2], cells[3]
        if 'pick' not in label.casefold() or not title or not author:
          continue
        year = parse_year(label)
        month = parse_month(label)
        if not year:
          continue
        try:
          position = '%s.%02d' % (year, int(month or 0))
        except Exception:
          position = str(len(entries) + 1)
        entry = self.build_entry({
          'rank_or_position': position,
          'title': title,
          'author': author,
          'selection_label': label,
          'selection_year': year,
          'selection_month': month,
          'selection_type': self.DEFAULT_SELECTION_TYPE,
        }, ' '.join(cells), base_url, self.DEFAULT_SCOPE, len(entries) + 1, base_url=base_url)
        if entry is None:
          continue
        key = self.entry_key(entry)
        if key in seen:
          continue
        seen.add(key)
        entries.append(entry)
    return entries

  def recommended_more_entries(self, soup, base_url):
    entries = []
    seen = set()
    for section in soup.select('section.recommended-more'):
      if self.node_text(section, '.recommended-more__title') != self.CLUB_NAME:
        continue
      for product in section.select('.recommended-more__product'):
        title_node = product.select_one('.recommended-more__product-title')
        title = self.clean_bn_title(self.node_text(product, '.recommended-more__product-title'))
        author = clean_author(self.node_text(product, '.recommended-more__product-author'))
        if not title or not author:
          continue
        href = title_node.get('href') if title_node is not None else ''
        entry = self.build_entry({
          'title': title,
          'author': author,
          'selection_label': self.CLUB_NAME,
          'selection_type': self.DEFAULT_SELECTION_TYPE,
        }, product.get_text(' ', strip=True), urljoin(base_url, href) if href else base_url,
          self.CURRENT_SCOPE, len(entries) + 1, base_url=base_url)
        if entry is None:
          continue
        entry.pop('season', None)
        key = self.entry_key(entry)
        if key in seen:
          continue
        seen.add(key)
        entries.append(entry)
    return entries

  def product_highlight_entries(self, soup, base_url):
    entries = []
    seen = set()
    for section in soup.select('section.product-highlight'):
      label = self.node_text(section, '.product-highlight__title')
      title = self.clean_bn_title(self.node_text(section, '.product-highlight__content-title'))
      author = self.clean_bn_author(self.node_text(section, '.product-highlight__content-contributors'))
      if not title or not author:
        continue
      link = section.select_one('.product-highlight__details-column a[href]')
      if link is None:
        link = section.find('a', href=True)
      entry = self.build_entry({
        'title': title,
        'author': author,
        'selection_label': label,
        'selection_type': self.DEFAULT_SELECTION_TYPE,
      }, section.get_text(' ', strip=True), urljoin(base_url, link['href']) if link else base_url,
        self.MONTHLY_SCOPE, len(entries) + 1, base_url=base_url)
      if entry is None:
        continue
      entry.pop('season', None)
      key = self.entry_key(entry)
      if key in seen:
        continue
      seen.add(key)
      entries.append(entry)
    return entries

  def node_text(self, node, selector):
    child = node.select_one(selector)
    return normalize_line(child.get_text(' ', strip=True)) if child is not None else ''

  def clean_bn_title(self, value):
    value = clean_title(value)
    value = re.sub(r'\s*\((?:B&N|Barnes\s*&\s*Noble)[^)]*\)\s*$', '', value, flags=re.I)
    value = re.sub(r'\s*\((?:Read\s+with\s+Jenna|Reese.?s|Oprah.?s|GMA)[^)]*Pick\)\s*$', '', value, flags=re.I)
    value = re.sub(r'\s*:\s*A\s+Good\s+Morning\s+America\s+YA\s+Book\s+Club\s+Pick\s*$', '', value, flags=re.I)
    return clean_title(value)

  def clean_bn_author(self, value):
    return clean_author(re.sub(r'^\s*By\s+', '', value or '', flags=re.I))

  def accept_entry(self, entry, text):
    if entry.get('club_scope') == self.CURRENT_SCOPE:
      return True
    if entry.get('club_scope') == self.MONTHLY_SCOPE:
      return 'monthly' in normalize_line(text).casefold()
    if entry.get('selection_year') and entry.get('selection_month'):
      normalized = normalize_line(text).casefold()
      label = normalize_line(entry.get('selection_label', '')).casefold()
      return 'pick' in label or 'book club pick' in normalized or 'book club selection' in normalized
    normalized = text.casefold()
    if 'discover prize' in normalized or 'monthly picks' in normalized:
      return False
    return 'book club pick' in normalized or 'book club selection' in normalized

  def notes_for_entries(self, _entries):
    return ['Barnes & Noble imports the current official Book Club page; older article discovery is best-effort only.']
