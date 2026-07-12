#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Parser for Oprah's Book Club primary selections."""

import base64
import json
import math
import re
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from .book_club_base import (
  BookClubParserBase, clean_author, clean_title, parse_year, split_title_author,
  text_blocks, parsed_source,
)


class OprahBookClubParser(BookClubParserBase):

  CLUB_NAME = "Oprah's Book Club"
  DEFAULT_SCOPE = 'primary_selections'
  DEFAULT_SELECTION_TYPE = 'primary_pick'
  LISTICLE_PAGE_SIZE = 20

  def parse(self, html, base_url, name=None, scope=None, fetch_url=None):
    soup = BeautifulSoup(html or '<html></html>', 'html.parser')
    scope = scope or self.DEFAULT_SCOPE
    entries = self.entries_from_next_data(soup, base_url, scope, fetch_url)
    if not entries:
      entries = self.entries_from_soup(soup, base_url, scope)
    return {
      'name': name or self.CLUB_NAME,
      'source': parsed_source(name or self.CLUB_NAME, base_url),
      'entries': sorted(entries, key=self.entry_sort_key),
      'notes': self.notes_for_entries(entries),
      'match_series': False,
    }

  def entries_from_soup(self, soup, base_url, scope):
    entries = self.entries_from_numbered_lines(soup, base_url, scope)
    return entries or super().entries_from_soup(soup, base_url, scope)

  def entries_from_next_data(self, soup, base_url, scope, fetch_url=None):
    page_props = self.next_page_props(soup)
    if not page_props:
      return []
    slides = list(page_props.get('slides') or [])
    total_count = self.slide_count(page_props, len(slides))
    listicle_id = self.listicle_id(page_props)
    media_pages = self.media_pages(page_props)
    if fetch_url is not None and listicle_id and total_count > len(slides):
      page_count = max(len(media_pages), int(math.ceil(
        float(total_count) / self.LISTICLE_PAGE_SIZE)))
      for page_number in range(2, page_count + 1):
        slides.extend(self.fetch_slide_page(
          fetch_url, base_url, listicle_id, page_number, page_props))
    entries = []
    seen = set()
    for index, slide in enumerate(slides):
      entry = self.entry_from_slide(slide, base_url, scope, total_count, index)
      if entry is None:
        continue
      key = self.entry_key(entry)
      if key in seen:
        continue
      seen.add(key)
      entries.append(entry)
    return entries

  def next_page_props(self, soup):
    script = soup.find('script', id='__NEXT_DATA__')
    if script is None:
      return {}
    try:
      data = json.loads(script.string or script.get_text() or '{}')
    except Exception:
      return {}
    return (((data.get('props') or {}).get('pageProps')) or {})

  def slide_count(self, page_props, fallback):
    count = (
      page_props.get('embeddedListicleSlideCount') or
      (((page_props.get('data') or {}).get('content') or [{}])[0].get('metadata') or {}).get('slide_count'))
    try:
      return int(count or fallback or 0)
    except Exception:
      return int(fallback or 0)

  def listicle_id(self, page_props):
    content = ((page_props.get('data') or {}).get('content') or [{}])[0]
    return page_props.get('embeddedListicleId') or content.get('id') or ''

  def media_pages(self, page_props):
    content = ((page_props.get('data') or {}).get('content') or [{}])[0]
    pages = content.get('media_pages') or page_props.get('mediaIdPages') or []
    return pages if isinstance(pages, list) else []

  def fetch_slide_page(self, fetch_url, base_url, listicle_id, page_number, page_props):
    params = {
      'id': listicle_id,
      'page': page_number,
      'mediaPagesCount': 1,
    }
    media_pages = self.media_pages(page_props)
    content = ((page_props.get('data') or {}).get('content') or [{}])[0]
    if content.get('media_pages_is_reordered') and page_number >= 2:
      page_ids = media_pages[page_number - 2] if page_number - 2 < len(media_pages) else []
      if page_ids:
        params['ids'] = base64.b64encode(
          ','.join(page_ids).encode('ascii')).decode('ascii')
    url = urljoin(base_url, '/api/listicle-slides?' + urlencode(params))
    try:
      data = json.loads(fetch_url(url) or '[]')
    except Exception:
      return []
    return data if isinstance(data, list) else []

  def entry_from_slide(self, slide, base_url, scope, total_count, index):
    name_text = self.html_text(slide.get('name') or slide.get('title') or '')
    title, author = split_title_author(name_text)
    if not title or not author:
      return None
    text = ' '.join(filter(None, (
      name_text,
      self.html_text(slide.get('custom_description') or slide.get('description') or ''),
    )))
    rank = self.slide_rank(slide, total_count, index, text)
    source_url = base_url
    product_id = slide.get('product_id') or slide.get('content_product_id') or ''
    if product_id:
      source_url = urljoin(base_url, '#product-' + product_id)
    return self.build_entry({
      'rank_or_position': str(rank or index + 1),
      'title': clean_title(title),
      'authors': [clean_author(author)],
      'selection_label': str(rank or index + 1),
      'selection_type': self.DEFAULT_SELECTION_TYPE,
    }, text, source_url, scope, rank or index + 1, base_url=base_url)

  def html_text(self, html):
    return BeautifulSoup(html or '', 'html.parser').get_text(' ', strip=True)

  def slide_rank(self, slide, total_count, index, text):
    try:
      return total_count - int(slide.get('order'))
    except Exception:
      pass
    for value in (slide.get('position'), slide.get('rank')):
      try:
        rank = int(value)
      except Exception:
        continue
      if rank > 0:
        return rank
    match = re.search(r'\bOprah.?s\s+(\d+)(?:st|nd|rd|th)?\s+Book Club pick\b', text, re.I)
    if match:
      return int(match.group(1))
    return total_count - index if total_count else index + 1

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
      entry = self.build_entry({
        'rank_or_position': str(number),
        'title': clean_title(title),
        'authors': [clean_author(author)],
        'selection_label': str(number),
        'selection_type': self.DEFAULT_SELECTION_TYPE,
      }, ' '.join(item[1] for item in blocks[index:index + 8]),
        source_url, scope, number, base_url=base_url)
      if entry is not None:
        entries.append(entry)
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
