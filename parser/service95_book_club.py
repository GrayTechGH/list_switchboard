#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Parser for Service95 Book Club monthly reads.

Maintenance notes:
- The landing page's monthly carousel links to one official `/books/` detail
  page per selection. Older carousel images expose only a year/month alt value,
  so title and author must come from the linked detail page rather than the
  surrounding image stream.
- Article/recommendation images below the carousel are intentionally excluded.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .book_club_base import (
  BookClubParserBase, image_alt_blocks, MONTHS, normalize_line, parse_month, parse_year,
  split_title_author,
)
from .base import parsed_source


class Service95BookClubParser(BookClubParserBase):

  CLUB_NAME = 'Service95 Book Club'
  DEFAULT_SCOPE = 'full_monthly_list'
  DEFAULT_SELECTION_TYPE = 'monthly_pick'
  # Several migrated detail pages omit a usable author credit, and two expose
  # a truncated/typoed credit. Keep these corrections title-bounded.
  AUTHOR_CORRECTIONS = {
    'bad habit': 'Alana S. Portero',
    'crying in h mart': 'Michelle Zauner',
    'half of a yellow sun': 'Chimamanda Ngozi Adichie',
    'lincoln in the bardo': 'George Saunders',
    'say nothing': 'Patrick Radden Keefe',
    'so late in the day': 'Claire Keegan',
    'the guest': 'Emma Cline',
    'there there': 'Tommy Orange',
    'trust': 'Hernan Diaz',
  }

  def parse(
      self, html, base_url, name=None, scope=None, fetch_url=None,
      progress=None, **_kwargs):
    scope = scope or self.DEFAULT_SCOPE
    soup = BeautifulSoup(html or '<html></html>', 'html.parser')
    links = self.monthly_read_links(soup, base_url)
    if not links or fetch_url is None:
      parsed = super().parse(html, base_url, name or self.CLUB_NAME, scope)
      parsed['entries'] = self.positioned_entries(parsed['entries'])
      return parsed

    entries = []
    notes = []
    total = len(links)
    for index, (detail_url, card_text) in enumerate(links, 1):
      if progress is not None:
        progress(index - 1, total, f'Fetching Service95 monthly read {index} of {total}')
      try:
        detail_html = fetch_url(detail_url)
        entry = self.entry_from_detail(
          detail_html, detail_url, card_text, base_url, scope, index)
      except Exception as err:
        notes.append(f'Service95 monthly-read page could not be fetched: {detail_url} ({err})')
        entry = self.entry_from_card_text(
          card_text, detail_url, base_url, scope, index)
      if entry is not None:
        entries.append(entry)
      else:
        notes.append(
          f'Service95 monthly-read page did not expose complete book metadata: {detail_url}')
    if progress is not None:
      progress(total, total, f'Fetched {total} Service95 monthly reads')
    entries = self.positioned_entries(entries)
    if not entries:
      notes.append('No Service95 monthly-read detail pages exposed title and author data.')
    return {
      'name': name or self.CLUB_NAME,
      'source': parsed_source(name or self.CLUB_NAME, base_url),
      'entries': entries,
      'notes': notes,
      'match_series': False,
    }

  def monthly_read_links(self, soup, base_url):
    links = []
    seen = set()
    for anchor in soup.find_all('a', href=True):
      href = normalize_line(anchor.get('href', ''))
      if not href.lstrip('/').startswith('books/'):
        continue
      url = urljoin(base_url, href)
      if url in seen:
        continue
      seen.add(url)
      container = anchor.find_parent(class_=re.compile(r'(?:swiper-slide|hero)', re.I))
      text_parts = [
        anchor.get('title', ''),
        anchor.get_text(' ', strip=True),
      ]
      image = anchor.find('img')
      if image is not None:
        text_parts.extend((image.get('alt', ''), image.get('title', '')))
      if container is not None:
        text_parts.append(container.get_text(' ', strip=True))
      links.append((url, normalize_line(' '.join(text_parts))))
    return links

  def entry_from_detail(
      self, html, detail_url, card_text, base_url, scope, index):
    soup = BeautifulSoup(html or '<html></html>', 'html.parser')
    heading = soup.find('h1')
    title = normalize_line(heading.get_text(' ', strip=True)) if heading else ''
    metadata = []
    for meta in soup.find_all('meta'):
      if meta.get('property') == 'og:title' or meta.get('name') in ('title', 'description'):
        metadata.append(normalize_line(meta.get('content', '')))
    if soup.title is not None:
      metadata.append(normalize_line(soup.title.get_text(' ', strip=True)))
    _card_title, card_author = self.card_identity(card_text)
    author = card_author or self.author_from_metadata(title, metadata)
    author = self.AUTHOR_CORRECTIONS.get(title.casefold(), author)
    detail_scope = heading.find_parent('section') if heading is not None else None
    detail_text = normalize_line(
      detail_scope.get_text(' ', strip=True) if detail_scope is not None
      else soup.get_text(' ', strip=True))
    year = parse_year(card_text) or parse_year(detail_text)
    month = parse_month(card_text) or parse_month(detail_text)
    if not title or not author or not year or not month:
      return self.entry_from_card_text(
        card_text, detail_url, base_url, scope, index)
    return self.build_entry({
      'title': title,
      'author': author,
      'selection_label': self.selection_label(year, month),
      'selection_year': year,
      'selection_month': month,
    }, detail_text, detail_url, scope, index, base_url=base_url)

  def author_from_metadata(self, title, metadata):
    if not title:
      return ''
    pattern = re.compile(
      re.escape(title) + r'\s+by\s+(.+?)(?:\s*[|\-\u2013\u2014]\s*Service95.*)?$',
      re.I)
    for value in metadata:
      match = pattern.search(value)
      if match:
        return self.clean_metadata_author(match.group(1))
    for value in metadata:
      parts = re.split(r'\s+by\s+', value, flags=re.I)
      if len(parts) > 1:
        author = self.clean_metadata_author(parts[-1])
        if author:
          return author
    return ''

  def clean_metadata_author(self, value):
    value = re.sub(r'\s+Explore\b.*$', '', normalize_line(value), flags=re.I)
    value = re.sub(
      r',?\s+for\s+(?:the\s+)?Service95.*$', '', value, flags=re.I)
    value = re.sub(r'\s*[|\u2013\u2014]\s*Service95.*$', '', value, flags=re.I)
    return normalize_line(value).strip(' .,:;')

  def card_identity(self, text):
    match = re.search(
      r'(?:Monthly Read.*?[-:,]\s*|,\s*)(.+?)\s+by\s+(.+?)'
      r'(?=\s+(?:19|20)\d{2}\b|\s+Dua(?:\u2019|\')s\b|$)',
      text, re.I)
    if not match:
      return '', ''
    return (
      normalize_line(match.group(1)).strip(' -,:'),
      self.clean_metadata_author(match.group(2)),
    )

  def entry_from_card_text(self, text, detail_url, base_url, scope, index):
    title, author = self.card_identity(text)
    if not title or not author:
      return None
    author = self.AUTHOR_CORRECTIONS.get(title.casefold(), author)
    year = parse_year(text)
    month = parse_month(text)
    return self.build_entry({
      'title': title,
      'author': author,
      'selection_label': self.selection_label(year, month),
      'selection_year': year,
      'selection_month': month,
    }, text, detail_url, scope, index, base_url=base_url)

  def selection_label(self, year, month):
    month_name = next(
      (name.title() for name, value in MONTHS.items() if value == month), '')
    return normalize_line(f'{month_name} {year}')

  def positioned_entries(self, entries):
    entries = sorted(entries, key=self.entry_sort_key)
    for position, entry in enumerate(entries, 1):
      entry['position'] = str(position)
    return entries

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
      }, normalized, base_url, scope, len(entries) + 1, base_url=base_url)
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
