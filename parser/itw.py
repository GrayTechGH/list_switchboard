#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
ITW Thriller Awards parser for the official past nominees and winners archive.

Maintenance notes:
- The official ITW archive is one long page. Each award year contains category
  headings followed by author/title/publisher blocks.
- Current nominee blocks identify winners with the ``winner`` class. The
  legacy page shape did not, so only legacy rows retain first-entry winner
  inference.
"""

import re

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, assign_positions, is_author_suffix, normalize_heading,
    normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    AwardParserBase, assign_positions, is_author_suffix, normalize_heading,
    normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key


AWARD_NAME = 'ITW Thriller Award'


class ITWThrillerAwardsParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def parse(self, html, base_url, name, category, category_aliases=()):
    rows = self.parse_rows(html, base_url, category, category_aliases)
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, source_url, category, category_aliases):
    soup = BeautifulSoup(html, 'html.parser')
    accepted_categories = self.accepted_category_headings(category, category_aliases)
    current_year = None
    current_category = None
    pending_author = ''
    category_index = 0
    rows = []

    for node in soup.find_all(['h1', 'h2', 'h3', 'li']):
      text = normalize_line(node.get_text(' ', strip=True))
      if not text:
        continue
      if node.name == 'h3' and 'media_title' in node.get('class', ()):
        # Current titles are descendants of rows already handled at the li
        # boundary. A title beginning with "Best" must not look like the next
        # category heading and discard the remaining nominees.
        continue
      year = self.year_from_heading(text)
      if year is not None and node.name in {'h1', 'h2'}:
        current_year = year
        current_category = None
        pending_author = ''
        category_index = 0
        continue
      if node.name in {'h2', 'h3'}:
        heading_category = self.category_from_heading(
          text, category, accepted_categories)
        if heading_category is not None:
          current_category = heading_category
          pending_author = ''
          category_index = 0
          continue
        if self.looks_like_category_heading(text):
          current_category = None
          pending_author = ''
          category_index = 0
          continue
        if current_year is not None and current_category and pending_author:
          title = self.clean_title(text, pending_author)
          if title:
            rows.append({
              'award_year': str(current_year),
              'title': title,
              'authors': self.clean_authors(pending_author),
              'result': 'winner' if category_index == 0 else 'nominee',
              'source_url': source_url,
              'category': current_category,
            })
            category_index += 1
            pending_author = ''
        continue
      if node.name == 'li' and current_year is not None and current_category:
        author_node = node.find('p', class_='author')
        title_node = node.find('h3', class_='media_title')
        if author_node is not None and title_node is not None:
          author = self.clean_author(author_node.get_text(' ', strip=True))
          authors = self.clean_authors(author)
          title = self.clean_title(
            title_node.get_text(' ', strip=True), author)
          if authors and title and not self.line_is_metadata(author):
            classes = {
              normalize_heading(value)
              for value in node.get('class', ())
            }
            rows.append({
              'award_year': str(current_year),
              'title': title,
              'authors': authors,
              'result': 'winner' if 'winner' in classes else 'nominee',
              'source_url': source_url,
              'category': current_category,
            })
            category_index += 1
          pending_author = ''
          continue
        author = self.clean_author(text)
        if author and not self.line_is_metadata(author):
          pending_author = author

    return self.dedupe_rows(rows)

  def accepted_category_headings(self, category, category_aliases):
    return {
      normalize_heading(value)
      for value in (category, *category_aliases)
      if value
    }

  def year_from_heading(self, text):
    match = re.search(r'\b((?:19|20)\d{2})\s+(?:ITW\s+)?Thriller Awards?\b',
                      text or '', re.I)
    if match is None:
      return None
    return int(match.group(1))

  def category_from_heading(self, text, category, accepted_categories):
    cleaned = re.sub(r'\b(?:19|20)\d{2}\b', '', text or '').strip()
    normalized = normalize_heading(cleaned)
    if normalized in accepted_categories:
      return category
    if normalized.startswith('best ') and normalized[5:] in accepted_categories:
      return category
    return None

  def looks_like_category_heading(self, text):
    return normalize_heading(text).startswith('best ')

  def line_is_metadata(self, value):
    text = normalize_heading(value)
    return (
      text in {'itw community', 'actives', 'associates'} or
      'narrated by' in text or
      text.startswith('audio narrated by'))

  def clean_title(self, value, author=''):
    title = strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')
    title = re.split(
      r'\s+(?:audio\s+)?narrated\s+by\b',
      title,
      maxsplit=1,
      flags=re.I)[0].strip()
    if author:
      title = re.sub(
        r'\s+by\s+' + re.escape(author) + r'\s*$',
        '',
        title,
        flags=re.I).strip()
    return title

  def clean_author(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_authors(self, value):
    """Split the bounded ITW author credit while preserving name suffixes."""
    parts = re.split(
      r'\s*(?:,\s*(?:and\s+)?|;\s*|&|\band\b)\s*',
      self.clean_author(value),
      flags=re.I)
    authors = []
    for part in parts:
      part = normalize_line(part).strip(' ,;')
      if not part:
        continue
      if is_author_suffix(part) and authors:
        authors[-1] = f'{authors[-1]}, {part}'
      elif part not in authors:
        authors.append(part)
    return authors

  def dedupe_rows(self, rows):
    deduped = []
    seen = set()
    for row in rows:
      authors = row.get('authors', row.get('author', ''))
      if not isinstance(authors, str):
        authors = ' '.join(authors or ())
      key = (
        row['award_year'],
        normalize_heading(row['category']),
        normalize_heading(row['title']),
        normalize_heading(authors),
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
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in by_year[year]
      ]
      entries.extend(assign_positions(award_rows, int(year)))
    return entries


def parse_itw_thriller_awards(html, base_url, name, category, category_aliases=()):
  return ITWThrillerAwardsParser().parse(
    html,
    base_url,
    name,
    category,
    category_aliases=category_aliases)
