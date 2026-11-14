#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
British Fantasy Awards parser for BFS official pages plus SFADB supplements.

Maintenance notes:
- The British Fantasy Society winners archive is authoritative but winner-only.
- The BFS shortlist page/blog link is current-cycle coverage, not a historical
  shortlist archive.
- SFADB year pages provide the historical non-winner rows used here as
  shortlist coverage. Keep that distinction visible in notes and docs.
"""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, parse_winner_prefix, split_title_author,
    strip_editor_marker, strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
  from calibre_plugins.list_switchboard.parser.sfadb_base import (
    SFADBParser, StandardItemMixin,
  )
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_SHORTLISTED, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, parse_winner_prefix, split_title_author,
    strip_editor_marker, strip_publication_notes,
  )
  from .generic import position_sort_key
  from .sfadb_base import SFADBParser, StandardItemMixin


AWARD_NAME = 'British Fantasy Award'
BFS_WINNERS_URL = (
  'https://britishfantasysociety.org/about-the-bfs/'
  'the-british-fantasy-awards/bfa-winners/')
BFS_AWARDS_URL = (
  'https://britishfantasysociety.org/about-the-bfs/'
  'the-british-fantasy-awards/')
BFS_LEGACY_SHORTLIST_URL = (
  'https://britishfantasysociety.org/british-fantasy-awards-shortlists/')
SFADB_URL = 'https://www.sfadb.com/British_Fantasy_Awards'
SFADB_YEAR_PAGE_URL = re.compile(r'/British_Fantasy_Awards_(\d{4})$')
SEMANTIC_TAGS = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li')
YEAR_RE = re.compile(r'^(?:19|20)\d{2}$')

CATEGORY_BOUNDARIES = frozenset({
  'anthology', 'anthology collection', 'anthology/collection', 'artist',
  'audio', 'best anthology', 'best artist',
  'best audio', 'best audio fiction', 'best audio non fiction',
  'best audio non-fiction', 'best collection', 'best comic',
  'best comic graphic novel', 'best fantasy novel', 'best horror novel',
  'best independent press', 'best magazine', 'best magazine periodical',
  'best new horror', 'best newcomer', 'best non fiction', 'best non-fiction',
  'best nonfiction', 'best novel', 'best novella', 'best screenplay',
  'best short fiction', 'best short story', 'collection', 'comic',
  'fantasy novel', 'graphic novel', 'horror novel', 'independent press',
  'magazine', 'magazine periodical', 'newcomer', 'non fiction',
  'non-fiction', 'nonfiction', 'novel', 'novella', 'robert holdstock award',
  'robert holdstock award fantasy novel', 'screenplay', 'short fiction',
  'short story', 'small press', 'sydney j bounds award for best newcomer',
})

TITLE_FIXES = {
  ('1983', 'best novel', 'sword of the lictor'): (
    'The Sword of the Lictor',
    'Corrected the 1983 British Fantasy Best Novel title from '
    '"Sword of the Lictor" to "The Sword of the Lictor".'),
  ('2025', 'horror novel', 'my darling beautiful thing'): (
    'My Darling Dreadful Thing',
    'Corrected 2025 British Fantasy Horror Novel title from '
    '"My Darling Beautiful Thing" to "My Darling Dreadful Thing".'),
}


def category_key(value):
  return normalize_heading(value).replace('non fiction', 'nonfiction')


def clean_source_text(value):
  value = normalize_line(value).replace('\xa0', ' ')
  replacements = {
    'Ã¨': 'è',
    'Ã­': 'í',
    'â€“': '-',
    'â€”': '-',
    'â€œ': '"',
    'â€\x9d': '"',
    'â€™': "'",
    'â€˜': "'",
  }
  for old, new in replacements.items():
    value = value.replace(old, new)
  return normalize_line(value)


BFS_AUTHOR_FIRST_WINNER_CATEGORIES = {
  1975: frozenset({'best novel'}),
  1976: frozenset({'best novel'}),
  1998: frozenset({'anthology/collection'}),
  2008: frozenset({
    'anthology', 'best novel', 'collection', 'nonfiction', 'novella',
  }),
}

BFS_WINNER_WORK_FIXES = {
  (
    '2004',
    'collection',
    'told by the dead ramsey campbell',
  ): (
    'Told By the Dead',
    'Ramsey Campbell',
    'Protected the 2004 British Fantasy Collection title containing "By".',
  ),
  (
    '2009',
    'best novel',
    'memoirs of a master forger william heaney aka graham joyce',
  ): (
    'Memoirs of a Master Forger',
    'Graham Joyce',
    'Normalized the 2009 British Fantasy Best Novel pseudonym credit to '
    'Graham Joyce.',
  ),
  (
    '2009',
    'nonfiction',
    'basil copper a life in books by basil copper ed stephen jones',
  ): (
    'Basil Copper: A Life in Books',
    'Stephen Jones',
    'Normalized the official 2009 British Fantasy Non-Fiction editor credit '
    'to Stephen Jones.',
  ),
  (
    '2017',
    'nonfiction',
    'the geek feminist revolution tor books kameron huxley',
  ): (
    'The Geek Feminist Revolution',
    'Kameron Hurley',
    'Corrected the official 2017 British Fantasy Non-Fiction author typo from '
    'Kameron Huxley to Kameron Hurley.',
  ),
}

BFS_SHORTLIST_WORK_FIXES = {
  (
    '2026',
    'anthology',
    'blood in the bricks',
  ): (
    'Blood in the Bricks',
    'Neil Williamson',
    'Removed the publisher mistakenly appended to the official 2026 British '
    'Fantasy Anthology editor credit.',
  ),
  (
    '2026',
    'anthology',
    'this way lies madness',
  ): (
    'This Way Lies Madness',
    'Dave Jeffery & Lee Murray',
    'Recovered the editors from the malformed official 2026 British Fantasy '
    'Anthology credit.',
  ),
}

BFS_AUTHOR_NAME_FIXES = {
  'Mauguerite Kenner': 'Marguerite Kenner',
}


class BritishFantasySFADBParser(StandardItemMixin, SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = SFADB_YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = CATEGORY_BOUNDARIES

  def parse_year(self, html, source_url, year, category, category_aliases):
    """
    Parse live SFADB category blocks with their bold-title and author-link
    boundaries. Text-only fixtures retain the shared SFADB fallback.
    """
    soup = BeautifulSoup(html or '', 'html.parser')
    blocks = soup.select('div.categoryblock')
    if not blocks:
      return super().parse_year(
        html, source_url, year, category, category_aliases)
    aliases = {
      normalize_heading(alias) for alias in category_aliases if alias
    }
    rows = []
    for block in blocks:
      heading_node = block.select_one('div.category')
      heading = normalize_heading(
        heading_node.get_text(' ', strip=True) if heading_node else '')
      if heading not in aliases:
        continue
      for item in block.find_all('li'):
        parsed = self.parse_item_node(item)
        if parsed is not None:
          rows.append(self.build_award_entry(
            parsed, source_url, year, category))
    return assign_positions(rows, year, tied_winners_share_position=True)

  def parse_item_node(self, item):
    text = clean_source_text(item.get_text(' ', strip=True))
    cleaned, result = parse_winner_prefix(text)
    if normalize_heading(cleaned) == 'no award':
      return None
    title_node = item.find(['b', 'strong'], recursive=False)
    first_link = item.find('a', href=True)
    if title_node is not None and first_link is not None:
      descendants = list(item.descendants)
      if descendants.index(title_node) > descendants.index(first_link):
        # A later bold node is a containing publication, not the work title.
        title_node = None
    marker = re.search(r'\b(?:edited|eds?\.?)\s+by\b', cleaned, re.I)
    links = [
      clean_source_text(link.get_text(' ', strip=True))
      for link in item.find_all('a', href=True)
    ]
    if title_node is None:
      if marker is None or ',' not in cleaned or not links:
        return self.parse_item(text)
      title = cleaned.split(',', 1)[0]
      authors = links
    else:
      title = clean_source_text(title_node.get_text(' ', strip=True))
      authors = links
      if marker is not None:
        editor_text = cleaned[marker.end():].casefold()
        editors = [
          author for author in authors
          if author.casefold() in editor_text
        ]
        if editors:
          authors = editors
    authors = [BFS_AUTHOR_NAME_FIXES.get(author, author) for author in authors]
    authors = list(dict.fromkeys(author for author in authors if author))
    title = strip_publication_notes(title).strip(' "\u201c\u201d,')
    if not title or not authors:
      return self.parse_item(text)
    return {
      'title': title,
      'author': ' & '.join(authors),
      'result': result if result == RESULT_WINNER else RESULT_SHORTLISTED,
    }

  def parse_item(self, text):
    parsed = super().parse_item(text)
    if parsed is not None and parsed.get('result') != RESULT_WINNER:
      parsed['result'] = RESULT_SHORTLISTED
    return parsed


class BritishFantasyParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def parse_bfs_winners(
      self, html, base_url, name, category, category_aliases=(),
      min_year=None, max_year=None):
    rows = []
    notes = []
    current_year = None
    for node in self.semantic_nodes(html):
      text = self.node_text(node)
      if not text:
        continue
      if YEAR_RE.match(text):
        current_year = int(text)
        continue
      if node.name != 'li' or current_year is None:
        continue
      parsed = self.parse_bfs_winner_row(
        node, text, base_url, current_year, category, category_aliases,
        min_year, max_year, notes)
      if parsed is not None:
        rows.append(parsed)
    return self.parsed_from_rows(name, base_url, rows, notes)

  def parse_bfs_shortlist(
      self, html, base_url, name, category, category_aliases=(),
      min_year=None, max_year=None):
    award_year = self.shortlist_award_year(html)
    rows = []
    notes = []
    current_category = None
    for node in self.semantic_nodes(html):
      text = self.node_text(node)
      if not text:
        continue
      if node.name in ('h2', 'h3', 'h4', 'h5', 'h6'):
        current_category = text if self.category_matches(
          text, category, category_aliases) else None
        continue
      if node.name != 'li' or current_category is None or award_year is None:
        continue
      if not self.year_allowed(award_year, min_year, max_year):
        continue
      parsed = self.parse_bfs_shortlist_work_text(
        node, text, notes, award_year, category)
      if parsed is None:
        continue
      rows.append(self.build_award_entry(
        parsed,
        self.first_link_url(node, base_url) or base_url,
        award_year,
        category))
    if award_year is None:
      notes.append(f'{name} official shortlist award year could not be determined.')
    return self.parsed_from_rows(name, base_url, rows, notes)

  def parse_bfs_shortlist_work_text(
      self, node, text, notes, year, category):
    title_node = node.find(['strong', 'b'])
    if title_node is None:
      return self.parse_work_text(text, notes, year, category)
    title = self.clean_title(self.node_text(title_node))
    fix_key = (str(year), category_key(category), category_key(title))
    fixed = BFS_SHORTLIST_WORK_FIXES.get(fix_key)
    if fixed is not None:
      title, author, note = fixed
      if note not in notes:
        notes.append(note)
      return {
        'title': title,
        'author': author,
        'result': RESULT_SHORTLISTED,
      }
    credit = text
    if credit.casefold().startswith(title.casefold()):
      credit = credit[len(title):].lstrip(' ,-\u2013\u2014')
    credit = self.clean_structured_author_credit(credit)
    if not title or not credit:
      return self.parse_work_text(text, notes, year, category)
    return {
      'title': title,
      'author': credit,
      'result': RESULT_SHORTLISTED,
    }

  def parse_sfadb(
      self, html, base_url, name, category, category_aliases=(),
      fetch_url=None, log=None, progress=None, min_year=None, max_year=None):
    parsed = BritishFantasySFADBParser().parse(
      html,
      base_url,
      name,
      category,
      self.sfadb_category_aliases(category, category_aliases),
      fetch_url=fetch_url,
      log=log,
      progress=progress)
    rows = [
      self.apply_title_fixes(dict(entry), parsed.setdefault('notes', []))
      for entry in parsed.get('entries', ())
      if self.year_allowed(int(entry.get('award_year', '0')), min_year, max_year)
    ]
    parsed['entries'] = rows
    return parsed

  def combine_results(self, name, base_url, *parsed_results):
    rows = []
    notes = [
      'Official BFS winners archive is winner-only.',
      'Official BFS shortlist coverage is current-cycle only; historical '
      'shortlist rows come from SFADB year pages.',
    ]
    official_winner_keys = set()
    if parsed_results and parsed_results[0]:
      official_winner_keys = {
        self.year_category_key(entry)
        for entry in parsed_results[0].get('entries', ())
        if entry.get('result') == RESULT_WINNER
      }
    omitted_supplement_winner = False
    for source_index, parsed in enumerate(parsed_results):
      if not parsed:
        continue
      notes.extend(parsed.get('notes', ()))
      for entry in parsed.get('entries', ()):
        if (
            source_index > 0
            and entry.get('result') == RESULT_WINNER
            and self.year_category_key(entry) in official_winner_keys
        ):
          omitted_supplement_winner = True
          continue
        rows.append(dict(entry))
    if omitted_supplement_winner:
      notes.append(
        'SFADB winner rows were omitted where the authoritative official BFS '
        'archive already supplied that year and category winner.')
    rows = self.dedupe_rows(rows)
    return self.parsed_from_rows(name, base_url, rows, self.unique_notes(notes))

  def parse_bfs_winner_row(
      self, node, text, base_url, year, category, category_aliases,
      min_year, max_year, notes):
    if not self.year_allowed(year, min_year, max_year):
      return None
    if ':' not in text:
      return None
    row_category, work_text = text.split(':', 1)
    if not self.category_matches(row_category, category, category_aliases):
      return None
    parsed = self.parse_bfs_winner_work_text(
      work_text, notes, year, category)
    if parsed is None:
      notes.append(f'{AWARD_NAME} {year} {category} has no award row.')
      return None
    parsed['result'] = RESULT_WINNER
    return self.build_award_entry(
      parsed,
      self.first_link_url(node, base_url) or base_url,
      year,
      category)

  def parse_bfs_winner_work_text(self, text, notes, year, category):
    cleaned = clean_source_text(text).strip(' -*')
    fix_key = (
      str(year),
      category_key(category),
      normalize_heading(strip_publication_notes(cleaned)),
    )
    fixed = BFS_WINNER_WORK_FIXES.get(fix_key)
    if fixed is not None:
      title, author, note = fixed
      if note not in notes:
        notes.append(note)
      return {
        'title': title,
        'author': author,
        'result': RESULT_SHORTLISTED,
      }
    author_first = category_key(category) in (
      BFS_AUTHOR_FIRST_WINNER_CATEGORIES.get(year, ()))
    return self.parse_work_text(
      cleaned, notes, year, category, author_first=author_first)

  def parse_work_text(
      self, text, notes, year, category, author_first=False):
    text = clean_source_text(text).strip(' -*')
    if normalize_heading(text) == 'no award':
      return None
    parsed = self.parse_edited_by(text)
    if parsed is None:
      parsed = self.parse_editor_credit(text)
    if parsed is None:
      parsed = self.parse_by(text)
    if parsed is None:
      parsed = self.parse_dash(text)
    if parsed is None:
      parsed = (
        self.parse_author_first_comma(text)
        if author_first else self.parse_comma(text))
    if parsed is None:
      return None
    title, author = parsed
    title = self.clean_title(title)
    author = self.clean_author(author)
    if not title or not author:
      return None
    row = {
      'title': title,
      'author': author,
      'result': RESULT_SHORTLISTED,
    }
    return self.apply_title_fixes(
      row, notes, award_year=str(year), category=category)

  def parse_edited_by(self, text):
    match = re.match(r'^(.*?)\s*,?\s+edited\s+by\s+(.+)$', text, re.I)
    if match is None:
      return None
    return match.group(1), match.group(2)

  def parse_editor_credit(self, text):
    match = re.match(
      r'^(.*),\s*eds?\.?\s+(?!\()(.+?)'
      r'(?:\s+\([^)]*\))?'
      r'(?:\s+with\s+stories\s+by\s+.+)?$',
      text,
      re.I)
    if match is None:
      return None
    return match.group(1), match.group(2)

  def parse_by(self, text):
    match = re.match(r'^(.*?)\s*,?\s+by\s+(.+)$', text, re.I)
    if match is None:
      return None
    return match.group(1), match.group(2)

  def parse_dash(self, text):
    match = re.match(r'^(.*?)\s+[-\u2013\u2014]\s*(.+)$', text)
    if match is None:
      return None
    return match.group(1), match.group(2)

  def parse_comma(self, text):
    title, author = split_title_author(text)
    if title and author:
      return title, author
    return None

  def parse_author_first_comma(self, text):
    if ',' not in text:
      return None
    author, title = text.split(',', 1)
    if title.strip() and author.strip():
      # The text before the first comma is a structurally isolated credit, so
      # its explicit conjunction can safely become Calibre's author separator.
      author = re.sub(r'\s+and\s+', ' & ', author, flags=re.I)
      return title, author
    return None

  def clean_title(self, value):
    value = clean_source_text(value)
    value = strip_publication_notes(value).strip(' "\'.,')
    return re.sub(r'\s+eds?\.?$', '', value, flags=re.I).strip()

  def clean_author(self, value):
    value = clean_source_text(value)
    value = re.sub(
      r'^\s*(?:by|edited\s+by|eds?\.?)\s+', '', value, flags=re.I)
    value = strip_editor_marker(strip_publication_notes(value))
    value = re.sub(r',\s*eds?\.?\s+.+$', '', value, flags=re.I)
    value = re.sub(r'\s*,?\s*published\s+by\s+.+$', '', value, flags=re.I)
    # This value is already isolated from the title, so explicit source
    # conjunctions and semicolons are safe Calibre author boundaries.
    value = re.sub(r'\s+(?:and|with)\s+|\s*;\s*', ' & ', value, flags=re.I)
    return value.strip(' "\'.,')

  def clean_structured_author_credit(self, value):
    value = strip_publication_notes(clean_source_text(value))
    value = re.sub(
      r'^\s*(?:by|edited(?:\s+by)?|eds?\.?)\s+', '', value, flags=re.I)
    value = re.sub(
      r'\s*,\s*(?:edited(?:\s+by)?|eds?\.?)\s+', ' & ', value,
      flags=re.I)
    suffix_marker = '\x00'
    value = re.sub(
      r',\s*(jr\.?|sr\.?|ii|iii|iv|v)\b',
      lambda match: f'{suffix_marker}{match.group(1)}',
      value,
      flags=re.I)
    value = re.sub(r'\s*,\s*', ' & ', value)
    value = value.replace(suffix_marker, ', ')
    return self.clean_author(value)

  def apply_title_fixes(
      self, row, notes, award_year=None, category=None):
    award_year = award_year or row.get('award_year')
    category = category or row.get('category')
    key = (
      str(award_year),
      category_key(category),
      category_key(row.get('title', '')))
    fixed = TITLE_FIXES.get(key)
    if fixed is None:
      return row
    title, note = fixed
    row['title'] = title
    if note not in notes:
      notes.append(note)
    return row

  def shortlist_award_year(self, html):
    soup = BeautifulSoup(html or '', 'html.parser')
    for text in (
        self.node_text(node)
        for node in soup.find_all(['title', 'h1', 'h2', 'p'])
    ):
      match = re.search(r'British Fantasy Awards?\s+((?:19|20)\d{2})', text, re.I)
      if match is not None:
        return int(match.group(1))
    return None

  def discover_shortlist_urls(self, html, base_url):
    soup = BeautifulSoup(html or '', 'html.parser')
    urls = []
    for link in soup.find_all('a', href=True):
      text = self.node_text(link)
      href = link.get('href') or ''
      if 'shortlist' not in f'{text} {href}'.casefold():
        continue
      url = urljoin(base_url, href)
      if url not in urls:
        urls.append(url)
    return tuple(urls)

  def parsed_from_rows(self, name, base_url, rows, notes):
    entries = self.entries_from_rows(rows)
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      year = str(row.get('award_year', ''))
      if not year:
        continue
      clean_row = dict(row)
      clean_row.pop('position', None)
      by_year.setdefault(year, []).append(clean_row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      year_rows = sorted(
        by_year[year],
        key=lambda row: 0 if row.get('result') == RESULT_WINNER else 1)
      entries.extend(assign_positions(year_rows, int(year)))
    return entries

  def dedupe_rows(self, rows):
    ordered = []
    by_key = {}
    for row in rows:
      key = self.row_key(row)
      existing = by_key.get(key)
      if existing is None:
        by_key[key] = row
        ordered.append(row)
        continue
      if existing.get('result') != RESULT_WINNER and row.get('result') == RESULT_WINNER:
        existing.update(row)
    return ordered

  def row_key(self, row):
    return (
      str(row.get('award_year', '')),
      category_key(row.get('category', '')),
      category_key(row.get('title', '')),
    )

  def year_category_key(self, row):
    return (
      str(row.get('award_year', '')),
      category_key(row.get('category', '')),
    )

  def category_matches(self, label, category, category_aliases):
    label_key = category_key(label)
    aliases = {category, *(category_aliases or ())}
    alias_keys = {category_key(alias) for alias in aliases if alias}
    if label_key in alias_keys:
      return True
    return any(
      len(alias) > 5 and alias in label_key
      for alias in alias_keys)

  def sfadb_category_aliases(self, category, category_aliases):
    aliases = [category, *(category_aliases or ())]
    key = category_key(category)
    if key == 'horror novel':
      aliases.extend((
        'horror novel august derleth award',
        'august derleth award horror novel',
      ))
    elif key == 'fantasy novel':
      aliases.extend((
        'fantasy novel robert holdstock award',
        'robert holdstock award fantasy novel',
      ))
    elif key == 'best novel':
      aliases.extend((
        'novel',
        'best novel',
        'novel the august derleth fantasy award',
        'novel the august derleth award',
        'august derleth fantasy award novel',
        'august derleth award novel',
        'august derleth fantasy award best novel',
      ))
    return tuple(dict.fromkeys(alias for alias in aliases if alias))

  def year_allowed(self, year, min_year=None, max_year=None):
    if min_year is not None and year < min_year:
      return False
    if max_year is not None and year > max_year:
      return False
    return True

  def semantic_nodes(self, html):
    soup = BeautifulSoup(html or '', 'html.parser')
    for removable in soup.find_all(['script', 'style', 'sup']):
      removable.decompose()
    return soup.find_all(SEMANTIC_TAGS)

  def node_text(self, node):
    return clean_source_text(node.get_text(' ', strip=True))

  def first_link_url(self, node, base_url):
    link = node.find('a', href=True)
    return urljoin(base_url, link['href']) if link is not None else ''

  def unique_notes(self, notes):
    unique = []
    for note in notes:
      if note and note not in unique:
        unique.append(note)
    return unique
