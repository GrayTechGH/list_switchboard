#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Parser for Reese's Book Club main monthly picks.

Maintenance notes:
- The live WordPress archive separates pick cards (date/category metadata)
  from popup blocks (title/author metadata); their shared ``post-####`` class
  and id are the stable join key.
- The current featured card can omit its taxonomy label, so its official book
  detail page supplies that one label. Historical cards remain archive-driven.
"""

import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from .book_club_base import (
  BookClubParserBase, clean_author, clean_title, parse_month, parse_season,
  parse_year, text_blocks,
)
from .base import parsed_source
from .incremental import ParsedUnitCache, position_independent_fingerprint

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError


# The redesigned archive collapses these early YA taxonomies into the same
# month labels as the adult picks. Official Reese pages identify each as a YA
# selection; later YA rows retain seasonal labels in the archive itself.
EARLY_YA_TITLES = {
  'i m still here black dignity in a world made for whiteness',
  'you should see me in a crown',
  'furia',
  'fable',
  'a cuban girl s guide to tea and tomorrow',
  'the light in hidden places',
  'you have a match',
}


class ReeseBookClubParser(BookClubParserBase):

  CLUB_NAME = "Reese's Book Club"
  DEFAULT_SCOPE = 'main_monthly'
  DEFAULT_SELECTION_TYPE = 'monthly_pick'

  def parse(
      self, html, base_url, name=None, scope=None, fetch_url=None,
      cached_parsed=None, incremental_update=False, **_kwargs):
    scope = scope or self.DEFAULT_SCOPE
    notes = []
    soup = BeautifulSoup(html or '<html></html>', 'html.parser')
    units = ParsedUnitCache('reese-posts-v1', [base_url, scope],
      cached_parsed, incremental_update)
    pages = [(base_url, soup)]
    discovery = {}
    if self.looks_like_wordpress_archive(soup):
      details = self.popup_details(pages)
      root_ids = {self.post_id(card) for card in soup.select('li.wp-block-post.book')}
      old_discovery = units.old_discovery
      # Live root popups advertise the entire post catalog, including books on
      # later pages. Missing/changed IDs invalidate the pagination shortcut.
      can_reuse = (bool(units.old_units) and old_discovery.get('popup_catalog_complete') is True
        and set(units.old_units).issubset(details))
      old_rows = []
      if can_reuse:
        for key, detail in details.items():
          if key in root_ids:
            continue
          reused = units.reuse(key, self.detail_revision(detail))
          if reused is None:
            can_reuse = False
            break
          old_rows.extend(reused)
      if not can_reuse:
        units.units.clear()
        pages.extend(self.fetch_archive_pages(soup, base_url, fetch_url, notes))
        old_rows = []
      entries = self.entries_from_wordpress_archive(
        pages, base_url, scope, fetch_url, notes, units)
      entries.extend(old_rows)
      for key, detail in details.items():
        if key not in units.units and key in units.old_units:
          entries.extend(units.failed(key, self.detail_revision(detail)))
      discovery = {'popup_catalog_complete': set(units.units) == set(details),
        'refresh_units': sorted(root_ids)}
    else:
      entries = self.entries_from_soup(soup, base_url, scope)
    if incremental_update and (cached_parsed or {}).get('entries') and not entries:
      raise ValueError('Reese did not expose usable selections; saved history was not replaced.')
    entries = sorted(entries, key=self.entry_sort_key)
    for position, entry in enumerate(entries, 1):
      entry['position'] = str(position)
    notes.extend(self.notes_for_entries(entries))
    parsed = {
      'name': name or self.CLUB_NAME,
      'source': parsed_source(name or self.CLUB_NAME, base_url),
      'entries': entries,
      'notes': notes,
      'match_series': False,
    }
    if units.units:
      parsed['incremental_state'] = units.state(entries,
        identity=position_independent_fingerprint)
      parsed['incremental_state']['discovery'] = discovery
    if incremental_update:
      parsed['incremental_update'] = True
    return parsed

  def detail_revision(self, detail):
    return [detail.get('title') or '', detail.get('authors') or []]

  def looks_like_wordpress_archive(self, soup):
    return bool(
      soup.select_one('li.wp-block-post.book')
      and soup.select_one('div.popup-details[id]'))

  def fetch_archive_pages(self, soup, base_url, fetch_url, notes):
    if fetch_url is None:
      return []
    pages = []
    seen = {base_url}
    for link in soup.find_all('a', href=True):
      url = urljoin(base_url, link.get('href'))
      parsed = urlparse(url)
      if (
          parsed.netloc.casefold() != urlparse(base_url).netloc.casefold()
          or 'query-2-page' not in parse_qs(parsed.query)
          or url in seen):
        continue
      seen.add(url)
      try:
        page_html = fetch_url(url)
      except (ImportCancelledError, CamoufoxRequiredError):
        raise
      except Exception as err:
        notes.append(f"Reese's Book Club archive page could not be fetched: {err}")
        continue
      pages.append((url, BeautifulSoup(page_html or '<html></html>', 'html.parser')))
    return pages

  def entries_from_wordpress_archive(
      self, pages, base_url, scope, fetch_url, notes, units=None):
    details = self.popup_details(pages)
    entries = []
    seen_posts = set()
    seen_entries = set()
    for _page_url, soup in pages:
      for card in soup.select('li.wp-block-post.book'):
        post_id = self.post_id(card)
        if not post_id or post_id in seen_posts:
          continue
        seen_posts.add(post_id)
        detail = details.get(post_id, {})
        revision = self.detail_revision(detail)
        title = detail.get('title') or self.card_title(card)
        authors = detail.get('authors') or []
        entry_url = self.card_url(card, base_url)
        label = self.card_label(card)
        if not label and entry_url and fetch_url is not None:
          label, detail_title, detail_authors = self.featured_pick_details(
            entry_url, fetch_url, notes)
          title = title or detail_title
          authors = authors or detail_authors
        if not title or not authors or not label:
          if units is not None:
            entries.extend(units.failed(post_id, revision))
          continue
        entry = self.build_entry({
          'title': title,
          'authors': authors,
          'selection_label': label,
          'selection_year': parse_year(label),
          'selection_month': parse_month(label),
          'season': parse_season(label),
        }, f'{label} {title} by {" and ".join(authors)}', entry_url, scope,
          len(entries) + 1, base_url=base_url)
        if entry is None:
          if units is not None:
            units.put(post_id, [], revision)
          continue
        key = self.entry_key(entry)
        if key in seen_entries:
          continue
        seen_entries.add(key)
        entries.append(entry)
        if units is not None:
          units.put(post_id, [entry], revision)
    return entries

  def popup_details(self, pages):
    details = {}
    for _page_url, soup in pages:
      for popup in soup.select('div.popup-details[id]'):
        post_id = popup.get('id')
        title_node = popup.select_one('.popup-content h3')
        author_node = popup.select_one('.popup-content h4')
        title = clean_title(title_node.get_text(' ', strip=True)) if title_node else ''
        authors = self.split_authors(author_node.get_text(' ', strip=True) if author_node else '')
        if post_id and title and authors:
          details.setdefault(post_id, {'title': title, 'authors': authors})
    return details

  def post_id(self, card):
    for class_name in card.get('class', ()):
      if re.fullmatch(r'post-\d+', class_name):
        return class_name
    return ''

  def card_title(self, card):
    image = card.find('img', alt=True)
    return clean_title(image.get('alt')) if image else ''

  def card_url(self, card, base_url):
    link = card.select_one('figure a[href]') or card.find('a', href=True)
    return urljoin(base_url, link.get('href')) if link else base_url

  def card_label(self, card):
    label = card.select_one('.taxonomy-book_category')
    return self.normalize_pick_label(label.get_text(' ', strip=True)) if label else ''

  def normalize_pick_label(self, label):
    return ' '.join(
      (label or '').replace('\ufffd', '\u2019').replace('\u2018', '\u2019').split())

  def featured_pick_details(self, url, fetch_url, notes):
    try:
      html = fetch_url(url)
    except (ImportCancelledError, CamoufoxRequiredError):
      raise
    except Exception as err:
      notes.append(f"Reese's current pick detail page could not be fetched: {err}")
      return '', '', []
    soup = BeautifulSoup(html or '<html></html>', 'html.parser')
    label = ''
    for heading in soup.find_all(['h2', 'h3', 'h4']):
      text = self.normalize_pick_label(heading.get_text(' ', strip=True))
      if 'pick' in text.casefold() and parse_year(text):
        label = text
        break
    title_node = soup.find('h1')
    author_node = soup.select_one('h3.mt-0')
    return (
      label,
      clean_title(title_node.get_text(' ', strip=True)) if title_node else '',
      self.split_authors(author_node.get_text(' ', strip=True) if author_node else ''),
    )

  def split_authors(self, value):
    value = clean_author(value)
    return [
      author.strip()
      for author in re.split(r'\s+(?:and|&)\s+', value, flags=re.I)
      if author.strip()
    ]

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
    if self.normalized_title(entry.get('title')) in EARLY_YA_TITLES:
      return False
    if 'gone before goodbye' in entry.get('title', '').casefold():
      return False
    return bool(entry.get('selection_month') or entry.get('selection_year'))

  def complete_entry(self, entry, text):
    lowered = text.casefold()
    if 'short story' in lowered:
      entry['scope_flags'] = 'short_story_collection'
    return entry

  def normalized_title(self, title):
    return re.sub(r'[^a-z0-9]+', ' ', (title or '').casefold()).strip()


class ReeseBookClubYAParser(ReeseBookClubParser):
  """Parse the seasonal and early corrected Reese's YA selections."""

  CLUB_NAME = "Reese's Book Club - YA Picks"
  DEFAULT_SCOPE = 'young_adult_picks'
  DEFAULT_SELECTION_TYPE = 'ya_pick'

  def accept_entry(self, entry, _text):
    label = entry.get('selection_label', '').casefold()
    return (
      any(season in label for season in ('spring', 'summer', 'fall', 'winter'))
      or self.normalized_title(entry.get('title')) in EARLY_YA_TITLES)

  def complete_entry(self, entry, _text):
    entry['selection_type'] = self.DEFAULT_SELECTION_TYPE
    entry['scope_flags'] = 'young_adult'
    return entry
