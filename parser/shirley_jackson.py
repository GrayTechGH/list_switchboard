#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Shirley Jackson Awards parser for SFADB year pages.

Maintenance notes:
- SFADB exposes one overview page with linked yearly award pages.
- Live SFADB rows use a bold work title followed by linked contributors.
  Translators follow an explicit ``translated by`` boundary and are not
  matchable authors for these recipes.
- Live ISFDB rows are supplemented by complete packaged replacement years only
  when their normalized title/author/result signatures still differ.
- The packaged coverage map rejects partial or unexpected year sets.
"""

import json
import re
from pathlib import Path

try:
  from calibre_plugins.list_switchboard.parser.award_base import (
    RESULT_NOMINEE, RESULT_WINNER, assign_positions, normalize_heading,
    normalize_line, parse_winner_prefix,
  )
  from calibre_plugins.list_switchboard.parser.isfdb_base import (
    ISFDBAwardParserBase,
  )
  from calibre_plugins.list_switchboard.parser.sfadb_base import (
    SFADBParser, StandardItemMixin, node_text,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from .award_base import (
    RESULT_NOMINEE, RESULT_WINNER, assign_positions, normalize_heading,
    normalize_line, parse_winner_prefix,
  )
  from .isfdb_base import ISFDBAwardParserBase
  from .sfadb_base import SFADBParser, StandardItemMixin, node_text
  from .generic import position_sort_key


AWARD_NAME = 'Shirley Jackson Award'
YEAR_PAGE_URL = re.compile(r'/Shirley_Jackson_Awards_(\d{4})$')
SUPPLEMENT_FILE = 'shirley_jackson_isfdb_supplement.json'
SUPPLEMENT_SCHEMA_VERSION = 1
CATEGORY_BOUNDARIES = frozenset({
  'novel', 'novella', 'novelette', 'short fiction', 'short story',
  'single author collection', 'single-author collection', 'collection',
  'edited anthology', 'anthology', 'special award', 'judges',
})
CATEGORY_KEYS = {
  'novel': 'novel',
  'novella': 'novella',
  'single author collection': 'single_author_collection',
  'collection': 'single_author_collection',
  'edited anthology': 'edited_anthology',
  'anthology': 'edited_anthology',
}
VALID_RESULTS = frozenset({RESULT_WINNER, RESULT_NOMINEE})


class ShirleyJacksonParser(StandardItemMixin, SFADBParser):

  AWARD_NAME = AWARD_NAME
  YEAR_PAGE_URL = YEAR_PAGE_URL
  CATEGORY_BOUNDARIES = CATEGORY_BOUNDARIES

  def parse(self, overview_html, base_url, name, category, category_aliases,
            fetch_url=None, log=None, progress=None):
    parsed = super().parse(
      overview_html, base_url, name, category, category_aliases,
      fetch_url=fetch_url, log=log, progress=progress)
    return require_complete_shirley_jackson_result(parsed, category, 'SFADB')

  def parse_item_node(self, node):
    """
    Preserve SFADB title/person boundaries and stop before translator credits.

    Flattening a linked multi-editor row makes its first editor look like part
    of the title. The same text path makes a trailing translator look like the
    author. Bold titles and linked people are authoritative on live year pages.
    """
    text = node_text(node)
    cleaned, result = parse_winner_prefix(text)
    if normalize_heading(cleaned) == 'no award':
      return None
    title_nodes = node.xpath('(./b | ./strong)[1]')
    person_nodes = node.xpath('./a[@href]')
    if not title_nodes or not person_nodes:
      return self.parse_item(text)
    title = node_text(title_nodes[0]).strip(' "\u201c\u201d,')
    authors = []
    for person_node in person_nodes:
      preceding = _text_before_descendant(node, person_node)
      if re.search(r'\btranslated\s+by\s*$', preceding, re.I):
        break
      author = normalize_line(node_text(person_node)).strip(' ,')
      if author and author not in authors:
        authors.append(author)
    if not title or not authors:
      return self.parse_item(text)
    return {
      'title': title,
      'authors': authors,
      'result': result,
    }


class ShirleyJacksonISFDBParser(ISFDBAwardParserBase):
  """
  Preserve Shirley Jackson ISFDB contributor, tie, and provenance semantics.

  ISFDB contributor cells use bold ``and`` separators. The containing award
  year page establishes the result; linked title records do not.
  """

  AWARD_NAME = AWARD_NAME

  def author_from_cell(self, cell):
    authors = []
    fragments = []
    for fragment in cell.xpath('.//text()'):
      parent = fragment.getparent()
      value = normalize_line(str(fragment))
      if (
          value.casefold() == 'and'
          and parent is not None
          and str(parent.tag).casefold() in {'b', 'strong'}):
        _append_author_fragment(authors, fragments)
        fragments = []
      else:
        fragments.append(str(fragment))
    _append_author_fragment(authors, fragments)
    return authors

  def clean_author(self, value):
    if isinstance(value, (list, tuple)):
      return [
        cleaned
        for cleaned in (
          normalize_line(author).strip(' ,') for author in value
        )
        if cleaned
      ]
    return super().clean_author(value)

  def first_record_url(self, _cell, _base_url):
    return ''

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(row['award_year'], []).append(row)
    entries = []
    for year in sorted(by_year, key=lambda value: int(value)):
      award_rows = [
        self.build_award_entry(
          row, row['source_url'], year, row['category'], award=row.get('award'))
        for row in by_year[year]
      ]
      entries.extend(assign_positions(
        award_rows, int(year), tied_winners_share_position=True))
    return entries


def category_key(category):
  key = CATEGORY_KEYS.get(normalize_heading(category))
  if key is None:
    raise ValueError(f'Unsupported Shirley Jackson category: {category}')
  return key


def load_shirley_jackson_isfdb_supplement(data=None):
  if data is None:
    try:
      from importlib import resources
      package = 'calibre_plugins.list_switchboard.parser.data'
      text = resources.files(package).joinpath(
        SUPPLEMENT_FILE).read_text(encoding='utf-8')
    except Exception:
      path = Path(__file__).with_name('data') / SUPPLEMENT_FILE
      text = path.read_text(encoding='utf-8')
    data = json.loads(text)
  _validate_supplement(data)
  return data


def require_complete_shirley_jackson_result(
    parsed, category, source_label, supplement=None):
  supplement = supplement or load_shirley_jackson_isfdb_supplement()
  expected = supplement['coverage'][category_key(category)]
  actual = {}
  for entry in parsed.get('entries', ()):
    year = str(entry.get('award_year') or '')
    total, winners = actual.get(year, (0, 0))
    actual[year] = (
      total + 1,
      winners + int(entry.get('result') == RESULT_WINNER),
    )
  expected_counts = {
    str(year): (int(counts['rows']), int(counts['winners']))
    for year, counts in expected.items()
  }
  if actual != expected_counts:
    missing = sorted(set(expected_counts) - set(actual), key=int)
    unexpected = sorted(set(actual) - set(expected_counts), key=int)
    mismatched = {
      year: {'expected': expected_counts[year], 'actual': actual.get(year)}
      for year in sorted(set(expected_counts) & set(actual), key=int)
      if actual[year] != expected_counts[year]
    }
    raise ValueError(
      f'{source_label} returned incomplete {category} coverage '
      f'(missing years={missing}; unexpected years={unexpected}; '
      f'mismatched years={mismatched})')
  return parsed


def apply_shirley_jackson_isfdb_supplement(
    parsed, category, name, supplement=None):
  supplement = supplement or load_shirley_jackson_isfdb_supplement()
  key = category_key(category)
  replacements = supplement['replacement_years'].get(key, {})
  entries = list(parsed.get('entries', ()))
  notes = list(parsed.get('notes', ()))
  for year in sorted(replacements, key=int):
    live_rows = [
      entry for entry in entries
      if str(entry.get('award_year') or '') == str(year)
    ]
    replacement_rows = _replacement_entries(
      replacements[year], year, category)
    if _entry_signature(live_rows) == _entry_signature(replacement_rows):
      continue
    entries = [
      entry for entry in entries
      if str(entry.get('award_year') or '') != str(year)
    ]
    entries.extend(replacement_rows)
    notes.append(
      f'ISFDB {category} {year} was replaced by the packaged verified '
      f'Shirley Jackson supplement.')
  parsed['name'] = name
  parsed['entries'] = sorted(
    entries, key=lambda entry: position_sort_key(entry.get('position', '')))
  parsed['notes'] = notes
  return require_complete_shirley_jackson_result(
    parsed, category, 'ISFDB + packaged supplement', supplement=supplement)


def _replacement_entries(rows, year, category):
  parser = ShirleyJacksonISFDBParser()
  award_rows = [
    parser.build_award_entry(
      {
        'title': row['title'],
        'authors': row['authors'],
        'result': row['result'],
      },
      row['source_url'],
      int(year),
      category)
    for row in rows
  ]
  return assign_positions(
    award_rows, int(year), tied_winners_share_position=True)


def _entry_signature(entries):
  return tuple(
    (
      normalize_heading(entry.get('title', '')),
      tuple(normalize_heading(author) for author in entry.get('authors', ())),
      entry.get('result', ''),
    )
    for entry in entries
  )


def _validate_supplement(data):
  if not isinstance(data, dict):
    raise ValueError('Shirley Jackson supplement must be a JSON object.')
  if data.get('schema_version') != SUPPLEMENT_SCHEMA_VERSION:
    raise ValueError(
      f'Unsupported Shirley Jackson supplement schema: '
      f'{data.get("schema_version")}')
  verified_through = data.get('verified_through')
  if not isinstance(verified_through, int) or verified_through < 2008:
    raise ValueError('Shirley Jackson supplement verified_through is invalid.')
  coverage = data.get('coverage')
  replacement_years = data.get('replacement_years')
  if set(coverage or {}) != set(CATEGORY_KEYS.values()):
    raise ValueError('Shirley Jackson supplement coverage categories are invalid.')
  if (
      not isinstance(replacement_years, dict)
      or set(replacement_years) != set(CATEGORY_KEYS.values())):
    raise ValueError('Shirley Jackson supplement replacement_years is invalid.')
  for key in set(CATEGORY_KEYS.values()):
    expected_years = {str(year) for year in range(2008, verified_through + 1)}
    category_coverage = coverage.get(key)
    if not isinstance(category_coverage, dict) or set(category_coverage) != expected_years:
      raise ValueError(
        f'Shirley Jackson supplement {key} coverage years are invalid.')
    for year, counts in category_coverage.items():
      if (
          not isinstance(counts, dict)
          or not isinstance(counts.get('rows'), int)
          or not isinstance(counts.get('winners'), int)
          or counts['rows'] < 1
          or counts['winners'] < 1
          or counts['winners'] > counts['rows']):
        raise ValueError(
          f'Shirley Jackson supplement {key} {year} coverage is invalid.')
    category_replacements = replacement_years.get(key, {})
    if not isinstance(category_replacements, dict):
      raise ValueError(
        f'Shirley Jackson supplement {key} replacement years are invalid.')
    for year, rows in category_replacements.items():
      if year not in category_coverage or not isinstance(rows, list) or not rows:
        raise ValueError(
          f'Shirley Jackson supplement {key} {year} replacement is invalid.')
      seen = set()
      winner_count = 0
      saw_nominee = False
      for row in rows:
        if not isinstance(row, dict):
          raise ValueError(
            f'Shirley Jackson supplement {key} {year} row is invalid.')
        title = row.get('title')
        authors = row.get('authors')
        result = row.get('result')
        source_url = row.get('source_url')
        if (
            not isinstance(title, str) or not title.strip()
            or not isinstance(authors, list) or not authors
            or not all(isinstance(author, str) and author.strip() for author in authors)
            or result not in VALID_RESULTS
            or not isinstance(source_url, str)
            or not source_url.startswith('https://')):
          raise ValueError(
            f'Shirley Jackson supplement {key} {year} row fields are invalid.')
        signature = (
          normalize_heading(title),
          tuple(normalize_heading(author) for author in authors),
        )
        if signature in seen:
          raise ValueError(
            f'Shirley Jackson supplement {key} {year} has duplicate rows.')
        if result == RESULT_WINNER and saw_nominee:
          raise ValueError(
            f'Shirley Jackson supplement {key} {year} rows are out of order.')
        seen.add(signature)
        winner_count += int(result == RESULT_WINNER)
        saw_nominee = saw_nominee or result == RESULT_NOMINEE
      expected = category_coverage[year]
      if len(rows) != expected['rows'] or winner_count != expected['winners']:
        raise ValueError(
          f'Shirley Jackson supplement {key} {year} replacement coverage '
          f'is invalid.')


def _text_before_descendant(node, boundary):
  fragments = []
  for fragment in node.xpath('.//text()'):
    parent = fragment.getparent()
    if parent is boundary or boundary in parent.iterancestors():
      break
    fragments.append(str(fragment))
  return normalize_line(' '.join(fragments))


def _append_author_fragment(authors, fragments):
  author = normalize_line(' '.join(fragments)).strip(' ,')
  if author and author not in authors:
    authors.append(author)


def parse_shirley_jackson_awards(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=None, log=None, progress=None):
  return ShirleyJacksonParser().parse(
    overview_html, base_url, name, category, category_aliases,
    fetch_url=fetch_url, log=log, progress=progress)
