#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Macavity Award parser for the Mystery Readers International awards page.

Maintenance notes:
- The official page groups one long archive by award year, then category. The
  winner is the first work line after each category heading; nominee rows are
  list items. In the raw HTML, that winner line is often an h4 continuation
  after a br inside the category heading.
- Historical tie headings can put multiple winners on one semicolon-separated
  line. Those winners share the base award-year position.
- A few publisher parentheticals contain an inline br. Keep those fragments
  together so the publication note cannot bleed into the author field.
- Official winner rows use "Author: Title (publisher)" order. Older nominee
  rows can instead use "Title by Author (publisher)"; accept that alternate
  shape only after a category boundary has been established. LibraryThing
  fallback keeps using the shared LibraryThing award parser.
"""

import re

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, assign_positions, is_author_suffix, normalize_heading,
    normalize_line, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
  from calibre_plugins.list_switchboard.parser.librarything_base import (
    LibraryThingAwardParserBase,
  )
  from calibre_plugins.list_switchboard.parser.stopyourekillingme_base import (
    StopYoureKillingMeAwardParserBase,
  )
except ImportError:
  from .award_base import (
    AwardParserBase, assign_positions, is_author_suffix, normalize_heading,
    normalize_line, strip_publication_notes,
  )
  from .generic import position_sort_key
  from .librarything_base import LibraryThingAwardParserBase
  from .stopyourekillingme_base import StopYoureKillingMeAwardParserBase


AWARD_NAME = 'Macavity Award'
YEAR_HEADING = re.compile(r'^((?:19|20)\d{2})$')
BLOCK_TAGS = {
  'address', 'article', 'aside', 'blockquote', 'body', 'dd', 'div', 'dl', 'dt',
  'fieldset', 'figcaption', 'figure', 'footer', 'form', 'h1', 'h2', 'h3', 'h4',
  'h5', 'h6', 'header', 'hr', 'li', 'main', 'nav', 'ol', 'p', 'pre', 'section',
  'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr', 'ul',
}


class MacavityAwardsParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def parse(self, html, base_url, name, category, category_aliases=()):
    rows = self.parse_rows(html, base_url, category, category_aliases)
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))))

  def parse_rows(self, html, source_url, category, category_aliases=()):
    soup = BeautifulSoup(html, 'html.parser')
    accepted_categories = self.accepted_category_headings(category, category_aliases)
    current_year = None
    current_category = None
    category_has_tied_winners = False
    category_index = 0
    rows = []

    for fragment in self.line_fragments(soup):
      text = normalize_line(fragment['text'])
      if not text:
        continue
      if fragment['tag'] == 'h3':
        current_year = self.year_from_heading(text)
        current_category = None
        category_has_tied_winners = False
        category_index = 0
        continue
      if fragment['tag'] == 'h4':
        heading_category = self.category_from_heading(text, category, accepted_categories)
        if heading_category is not None:
          current_category = heading_category
          category_has_tied_winners = self.heading_marks_tie(text)
          category_index = 0
          continue
        if self.looks_like_category_heading(text):
          current_category = None
          category_has_tied_winners = False
          category_index = 0
          continue
      if current_year is None or current_category is None:
        continue
      if self.looks_like_category_heading(text):
        current_category = None
        category_has_tied_winners = False
        category_index = 0
        continue
      line_starts_category = category_index == 0
      title_first = self.title_first_from_fragment(fragment)
      for line_index, entry_text in enumerate(self.split_entry_lines(text)):
        result = 'nominee'
        if line_starts_category and fragment['tag'] != 'li' and (
            line_index == 0 or category_has_tied_winners):
          result = 'winner'
        row = self.parse_entry_line(
          entry_text,
          source_url,
          current_year,
          current_category,
          result,
          title_first=title_first,
          title_hint=fragment.get('lead_bold_text', ''))
        if row is not None:
          rows.append(row)
          category_index += 1

    return self.dedupe_rows(rows)

  def line_fragments(self, soup):
    root = soup.body or soup
    fragments = []
    current = []
    current_tag = ''
    lead_bold_text = ''

    def flush():
      nonlocal current_tag, lead_bold_text
      text = normalize_line(''.join(current))
      if text:
        fragments.append({
          'text': text,
          'tag': current_tag,
          'lead_bold_text': lead_bold_text,
        })
      current.clear()
      current_tag = ''
      lead_bold_text = ''

    def append_text(value, tag_name=''):
      nonlocal current_tag
      if tag_name and not current_tag:
        current_tag = tag_name
      current.append(re.sub(r'\s*\r?\n\s*', ' ', str(value)))

    def walk(node, block_name=''):
      nonlocal lead_bold_text
      if isinstance(node, NavigableString):
        append_text(node, block_name)
        return
      if not isinstance(node, Tag):
        return
      if node.name in {'script', 'style'}:
        return
      if node.name == 'br':
        current_text = ''.join(current)
        if block_name == 'li' or current_text.count('(') > current_text.count(')'):
          current.append(' ')
          return
        flush()
        return
      if (
          node.name in {'b', 'strong'} and not lead_bold_text
          and not normalize_line(''.join(current))):
        lead_bold_text = normalize_line(node.get_text(' ', strip=True))
      tag_name = node.name if node.name in BLOCK_TAGS else block_name
      if node.name in BLOCK_TAGS and current:
        flush()
      for child in node.children:
        walk(child, tag_name)
      if node.name in BLOCK_TAGS:
        flush()

    for child in root.children:
      walk(child)
    flush()
    return fragments

  def accepted_category_headings(self, category, category_aliases):
    return {
      normalize_heading(value)
      for value in (category, *category_aliases)
      if value
    }

  def year_from_heading(self, text):
    match = YEAR_HEADING.match(text or '')
    return int(match.group(1)) if match is not None else None

  def category_from_heading(self, text, category, accepted_categories):
    cleaned = normalize_line((text or '').rstrip(':'))
    cleaned = re.sub(r'\s*\(\s*tie\s*\)\s*$', '', cleaned, flags=re.I)
    if normalize_heading(cleaned) in accepted_categories:
      return category
    return None

  def heading_marks_tie(self, text):
    return re.search(r'\(\s*tie\s*\)\s*:?\s*$', text or '', re.I) is not None

  def looks_like_category_heading(self, text):
    normalized = normalize_heading((text or '').rstrip(':'))
    return normalized.startswith('best ') or normalized.startswith('sue feder ')

  def parse_entry_line(
      self, text, source_url, year, category, result, title_first=None,
      title_hint=''):
    title, author = self.title_author_from_text(
      text,
      result=result,
      title_first=title_first,
      title_hint=title_hint)
    if not title or not author:
      return None
    return {
      'award_year': str(year),
      'title': title,
      'author': author,
      'result': result,
      'source_url': source_url,
      'category': category,
    }

  def split_entry_lines(self, text):
    """Split legacy tied winners only where another Author: Title row starts."""
    return [
      value.strip()
      for value in re.split(r';\s*(?=[^:;]+:\s*\S)', text or '')
      if value.strip()
    ]

  def title_first_from_fragment(self, fragment):
    title_hint = normalize_line(fragment.get('lead_bold_text', ''))
    text = normalize_line(fragment.get('text', ''))
    if not title_hint or not text.startswith(title_hint):
      return None
    remainder = text[len(title_hint):].lstrip()
    if re.match(r'^(?:,\s*)?(?:edited\s+)?by\b', remainder, re.I):
      return True
    return False

  def title_author_from_text(
      self, text, result=None, title_first=None, title_hint=''):
    text = normalize_line(text).lstrip('*').strip()
    by_match = re.match(r'^(.+)\s+by\s+(.+)$', text, re.I)
    if title_first is True and title_hint:
      remainder = text[len(title_hint):].lstrip()
      credit_match = re.match(
        r'^(?:,\s*)?(?:edited\s+)?by\s+(.+)$', remainder, re.I)
      if credit_match is not None:
        return self.clean_title(title_hint), self.clean_author(credit_match.group(1))
    if (title_first is True or (title_first is None and result != 'winner')) and by_match:
      return self.clean_title(by_match.group(1)), self.clean_author(by_match.group(2))
    if ':' in text:
      author, title = text.split(':', 1)
      return self.clean_title(title), self.clean_author(author)
    if by_match is not None:
      return (
        self.clean_title(by_match.group(1)),
        self.clean_author(by_match.group(2)))
    return '', ''

  def clean_title(self, value):
    return strip_publication_notes(normalize_line(value)).strip(' "\u201c\u201d,')

  def clean_author(self, value):
    value = normalize_line(value)
    value = re.sub(r'\s*;\s*photograph(?:ed|y)\s+by\s+.+$', '', value, flags=re.I)
    value = re.sub(
      r",\s*St\.?\s*Martin(?:['\u2019]s)?\s+Minotaur$", '', value, flags=re.I)
    value = re.sub(r'\s+with\s+additional\s+essays\s+by\s+', ' & ', value, flags=re.I)
    value = re.sub(r'\s*,?\s*editors?$', '', value, flags=re.I)
    value = re.sub(r'\s*,?\s*eds?\.?$', '', value, flags=re.I)
    value = strip_publication_notes(value).strip(' "\u201c\u201d,')
    authors = []
    for part in re.split(
        r'\s*(?:,\s*(?:and\s+)?|;\s*|&|\band\b|\bwith\b)\s*',
        value,
        flags=re.I):
      part = normalize_line(part).strip(' ,;')
      if not part:
        continue
      if is_author_suffix(part) and authors:
        authors[-1] = f'{authors[-1]}, {part}'
      elif part not in authors:
        authors.append(part)
    return ' & '.join(authors)

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
      award_rows = [
        self.build_award_entry(row, row['source_url'], year, row['category'])
        for row in by_year[year]
      ]
      entries.extend(assign_positions(
        award_rows, int(year), tied_winners_share_position=True))
    return entries


class MacavitySYKMAwardsParser(StopYoureKillingMeAwardParserBase):

  AUTHOR_CREDIT_CORRECTIONS = {
    'suzanne marrs and tom nolan editors': ('Suzanne Marrs', 'Tom Nolan'),
    'mwa with editors lee child and laurie r king': (
      'Lee Child', 'Laurie R. King'),
  }


class MacavityLibraryThingAwardsParser(LibraryThingAwardParserBase):

  AUTHOR_CORRECTIONS = {
    normalize_heading(title): authors
    for title, authors in (
      ("1001 Midnights: The Aficionado's Guide to Mystery and Detective Fiction",
       ('Marcia Muller', 'Bill Pronzini')),
      ('Talking Mysteries', ('Tony Hillerman', 'Ernie Bulow')),
      ("Deadly Women: The Woman Mystery Reader's Indispensable Companion",
       ('Jan Grape', 'Dean James', 'Ellen Nehr')),
      ('G Is for Grafton: The World of Kinsey Millhone',
       ('Natalie Kaufman', 'Carol Kay')),
      ('Killer Books', ('Jean Swanson', 'Dean James')),
      ('Speaking of Murder', ('Ed Gorman', 'Martin Greenberg')),
      ('Silk Stalkings: When Women Write of Murder',
       ('Victoria Nichols', 'Susan Thompson')),
      ('A Taste of Murder: Diabolically Delicious Recipes from Contemporary Mystery Writers',
       ('Jo Grossman', 'Robert Weibezahl')),
      ('Women of Mystery: The Lives and Works of Notable Women Crime Novelists',
       ('Martha Hailey Dubose', 'Margaret Caldwell Thomas')),
      ("Mystery Muses: 100 Classics That Inspire Today's Mystery Writers",
       ('Jim Huang', 'Austin Lugar')),
      ('Thrillers: 100 Must-Reads', ('David Morrell', 'Hank W. Wagner')),
      ('Meanwhile There Are Letters: The Correspondence of Eudora Welty and Ross Macdonald',
       ('Suzanne Marrs', 'Tom Nolan')),
      ('The Man from the Train: The Solving of a Century-Old Serial Killer Mystery',
       ('Bill James', 'Rachel McCarthy James')),
      ('How to Write a Mystery: A Handbook from Mystery Writers of America',
       ('Lee Child', 'Laurie R. King')),
      ('The Bloomsbury Handbook to Agatha Christie',
       ('Mary Anna Evans', 'J.C. Bernthal')),
      ('Spillane: King of Pulp Fiction',
       ('Max Allan Collins', 'James L. Traylor')),
      ('Tower', ('Ken Bruen', 'Reed Farrel Coleman')),
      ('The Murder of Mr. Ma', ('John Shen Yen Nee', 'S.J. Rozan')),
    )
  }

  def title_author_from_work_cell(self, cell):
    title, author = super().title_author_from_work_cell(cell)
    corrected = self.AUTHOR_CORRECTIONS.get(normalize_heading(title))
    if corrected is not None:
      author = ' & '.join(corrected)
    return title, author


def parse_macavity_awards(html, base_url, name, category, category_aliases=()):
  return MacavityAwardsParser().parse(
    html,
    base_url,
    name,
    category,
    category_aliases=category_aliases)
