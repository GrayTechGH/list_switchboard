#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Ripped Bodice Awards parser for Wikipedia's wikitext source.

Maintenance notes:
- The current official storefront is not a stable machine-readable award
  archive. This parser uses the Wikipedia article's Romance Awards section,
  fetched through MediaWiki wikitext JSON, and imports only the public
  2019/2020 honoree prose currently present there.
- The source is prose rather than an award table, so this intentionally does
  not inherit from WikipediaAwardTableParserBase.
"""

import html as html_lib
import json
import re
from urllib.parse import quote, urljoin

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, RESULT_WINNER, assign_positions, normalize_heading,
    normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_WINNER, assign_positions, normalize_heading,
    normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key


RIPPED_BODICE_AWARD_NAME = 'Ripped Bodice Awards for Excellence in Romance Fiction'
RIPPED_BODICE_ARTICLE_URL = 'https://en.wikipedia.org/wiki/The_Ripped_Bodice'
RIPPED_BODICE_WIKITEXT_URL = (
  'https://en.wikipedia.org/w/api.php?action=parse&page=The_Ripped_Bodice'
  '&prop=wikitext&format=json&formatversion=2')
RIPPED_BODICE_CATEGORY = 'Romance Fiction'


class RippedBodiceAwardsParser(AwardParserBase):

  AWARD_NAME = RIPPED_BODICE_AWARD_NAME

  def parse(self, source, base_url=RIPPED_BODICE_ARTICLE_URL,
            name=RIPPED_BODICE_AWARD_NAME):
    rows = self.dedupe_rows(self.parse_rows(source, base_url))
    if not rows:
      raise ValueError('Could not parse Ripped Bodice awards from source.')
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, source, base_url):
    wikitext = self.source_wikitext(source)
    section = self.romance_awards_section(wikitext)
    if not section:
      return []
    link_urls = self.link_urls_by_label(section, base_url)
    section = self.strip_unmatchable_wikitext(section)
    rows = []
    for year, phrase in (
        ('2019', r'\bThe winners included\b'),
        ('2020', r'\bThe 2020 winners were\b'),
    ):
      winner_text = self.winner_text_after_phrase(section, phrase)
      for title, author in self.title_author_pairs(winner_text):
        rows.append({
          'award_year': year,
          'title': title,
          'author': author,
          'result': RESULT_WINNER,
          'source_url': self.source_url_for_title(title, link_urls, base_url),
          'category': RIPPED_BODICE_CATEGORY,
          '_source_order': len(rows),
        })
    return rows

  def source_wikitext(self, source):
    if isinstance(source, bytes):
      source = source.decode('utf-8', 'replace')
    value = source or ''
    try:
      data = json.loads(value)
    except Exception:
      return value
    if not isinstance(data, dict):
      return value
    parsed = data.get('parse')
    if not isinstance(parsed, dict):
      return value
    wikitext = parsed.get('wikitext')
    if isinstance(wikitext, str):
      return wikitext
    if isinstance(wikitext, dict):
      return wikitext.get('*') or ''
    return value

  def romance_awards_section(self, wikitext):
    match = re.search(
      r'(?im)^==\s*Romance Awards\s*==\s*$',
      wikitext or '')
    if match is None:
      return ''
    remainder = wikitext[match.end():]
    next_heading = re.search(r'(?m)^==[^=].*?==\s*$', remainder)
    return remainder[:next_heading.start()] if next_heading is not None else remainder

  def strip_unmatchable_wikitext(self, value):
    value = re.sub(r'<ref\b[^>/]*>.*?</ref>', ' ', value, flags=re.I | re.S)
    value = re.sub(r'<ref\b[^>]*/\s*>', ' ', value, flags=re.I)
    while True:
      stripped = re.sub(r'\{\{[^{}]*\}\}', ' ', value)
      if stripped == value:
        break
      value = stripped
    return normalize_line(value)

  def winner_text_after_phrase(self, section, phrase):
    match = re.search(phrase + r'\s+(.+?)(?=\.\s+The\s+20\d{2}\s+winners\b|$)',
                      section, flags=re.I)
    if match is None:
      return ''
    return match.group(1).rstrip('. ')

  def title_author_pairs(self, winner_text):
    pairs = []
    if not winner_text:
      return pairs
    for match in re.finditer(
        r'(.+?)\s+by\s+(.+?)(?=,\s+(?:and\s+)?(?:\'\'|\[\[|[A-Z])|$)',
        winner_text):
      title_text = match.group(1)
      author = self.clean_author(match.group(2))
      if not author:
        continue
      for title in self.split_titles(title_text):
        if title:
          pairs.append((title, author))
    return pairs

  def split_titles(self, title_text):
    title_text = re.sub(r'^[,\s]*(?:and\s+)?', '', title_text)
    parts = title_text.split(';') if ';' in title_text else (title_text,)
    return [
      self.clean_title(re.sub(r'^[,\s]*(?:and\s+)?', '', part))
      for part in parts
      if self.clean_title(re.sub(r'^[,\s]*(?:and\s+)?', '', part))
    ]

  def clean_title(self, value):
    value = strip_publication_notes(self.clean_wikitext_text(value))
    return value.strip(' "\'\u2018\u2019\u201c\u201d,:')

  def clean_author(self, value):
    value = self.clean_wikitext_text(value)
    value = re.sub(r'\s+(?:and|,)\s*$', '', value, flags=re.I)
    return value.strip(' "\'\u2018\u2019\u201c\u201d,:')

  def clean_wikitext_text(self, value):
    value = re.sub(
      r'\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]',
      lambda match: match.group(2) or match.group(1),
      value or '')
    value = value.replace("''", '')
    value = re.sub(r'<[^>]+>', ' ', value)
    return normalize_line(html_lib.unescape(value))

  def link_urls_by_label(self, wikitext, base_url):
    urls = {}
    for match in re.finditer(
        r'\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]',
        wikitext or ''):
      page = match.group(1)
      label = self.clean_wikitext_text(match.group(2) or page)
      if not label:
        continue
      urls.setdefault(
        normalize_heading(label),
        urljoin(base_url, '/wiki/' + quote(page.replace(' ', '_'), safe="/:_(),'")))
    return urls

  def source_url_for_title(self, title, link_urls, base_url):
    return link_urls.get(normalize_heading(title), base_url)

  def dedupe_rows(self, rows):
    deduped = []
    seen = set()
    for row in rows:
      key = (
        row['award_year'],
        normalize_heading(row['category']),
        normalize_heading(row['title']),
        normalize_heading(row['author']),
      )
      if key in seen:
        continue
      seen.add(key)
      deduped.append(row)
    return deduped

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      award_rows = []
      for row in sorted(by_year[year], key=lambda item: item.get('_source_order', 0)):
        entry_row = {key: value for key, value in row.items() if not key.startswith('_')}
        award_rows.append(self.build_award_entry(
          entry_row, row['source_url'], year, row['category']))
      entries.extend(assign_positions(award_rows, int(year)))
    return entries


def parse_ripped_bodice_awards(
    source, base_url=RIPPED_BODICE_ARTICLE_URL, name=RIPPED_BODICE_AWARD_NAME):
  return RippedBodiceAwardsParser().parse(source, base_url, name)
