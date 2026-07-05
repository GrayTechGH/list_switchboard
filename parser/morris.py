#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
William C. Morris YA Debut Award parser for official ALA/YALSA pages.

Maintenance notes:
- Morris publishes an official public finalist shortlist. These finalists are
  imported as `shortlisted` entries; unlike Printz/Newbery, this is not a
  schema-only mapping from honor books.
- Shared official-YALSA mechanics live in `parser.yalsa_base`; this module owns
  only Morris-specific page headings, section boundaries, and notes.
"""

import re

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    RESULT_SHORTLISTED, RESULT_WINNER, normalize_heading, normalize_line,
  )
  from calibre_plugins.list_switchboard.parser.yalsa_base import ( # type: ignore
    YALSAOfficialAwardParserBase, yma_awards_url,
  )
except ImportError:
  from .award_base import (
    RESULT_SHORTLISTED, RESULT_WINNER, normalize_heading, normalize_line,
  )
  from .yalsa_base import YALSAOfficialAwardParserBase, yma_awards_url


AWARD_NAME = 'William C. Morris YA Debut Award'
CATEGORY = 'Young Adult Literature'
HISTORY_URL = 'https://www.ala.org/yalsa/booklistsawards/bookawards/morris/previous'
CURRENT_URL = 'https://www.ala.org/yalsa/morris-award'


class MorrisAwardParser(YALSAOfficialAwardParserBase):

  AWARD_NAME = AWARD_NAME
  CATEGORY = CATEGORY
  HISTORY_URL = HISTORY_URL
  CURRENT_URL = CURRENT_URL
  CURRENT_FETCH_MESSAGE = 'Fetching current Morris Award page'
  CURRENT_FAILED_LABEL = 'Current Morris Award page'
  SUPPLEMENT_FETCH_LABEL = 'Morris Award supplement'
  SUPPLEMENT_FAILED_LABEL = 'Morris Award supplement'
  NO_ENTRIES_MESSAGE = 'No William C. Morris YA Debut Award entries found on official ALA/YALSA pages.'
  FINAL_NOTE = (
    'Morris Award finalists are official public shortlists and are imported '
    'as shortlisted entries.')

  def history_rows(self, html, base_url=HISTORY_URL):
    rows = []
    current_year = None
    current_result = None

    for line in self.text_lines(html):
      year_match = re.match(r'^\s*((?:19|20)\d{2})\s*:?\s*$', line)
      if year_match is not None:
        year = int(year_match.group(1))
        if year >= 2009:
          current_year = year
          current_result = None
        continue

      if current_year is None:
        continue
      lower = normalize_heading(line)
      if lower in {'winner', 'winners'}:
        current_result = RESULT_WINNER
        continue
      if lower in {'finalist', 'finalists'}:
        current_result = RESULT_SHORTLISTED
        continue
      if lower.startswith('winner '):
        line = re.sub(r'^\s*winners?\s*:?\s*', '', line, flags=re.I).strip()
        rows.extend(self.rows_from_text(current_year, line, RESULT_WINNER, base_url))
        current_result = RESULT_WINNER
        continue
      if lower.startswith(('finalist ', 'finalists ')):
        line = re.sub(r'^\s*finalists?\s*:?\s*', '', line, flags=re.I).strip()
        rows.extend(self.rows_from_text(current_year, line, RESULT_SHORTLISTED, base_url))
        current_result = RESULT_SHORTLISTED
        continue
      if current_result not in {RESULT_WINNER, RESULT_SHORTLISTED}:
        continue
      if self.skip_history_line(line):
        continue
      rows.extend(self.rows_from_text(current_year, line, current_result, base_url))
    return rows

  def current_page_rows(self, html, base_url=CURRENT_URL):
    rows = []
    current_year = None
    winner_pending = False
    for line in self.text_lines(html):
      match = re.match(
        r'^\s*((?:19|20)\d{2})\s+Morris Award Winner\s*:?\s*(.*)$',
        line,
        re.I)
      if match is not None:
        current_year = int(match.group(1))
        winner_pending = True
        if match.group(2):
          rows.extend(self.rows_from_text(current_year, match.group(2), RESULT_WINNER, base_url))
          winner_pending = False
        continue
      if winner_pending and current_year is not None:
        parsed = self.rows_from_text(current_year, line, RESULT_WINNER, base_url)
        if parsed:
          rows.extend(parsed)
          winner_pending = False
        continue
      if 'was named the' in line and 'winner of the william c morris' in normalize_heading(line):
        year = current_year or self.year_from_url_or_lines(base_url, (line,))
        if year is not None:
          rows.extend(self.rows_from_text(year, line, RESULT_WINNER, base_url))
    return rows

  def annual_page_rows(self, html, base_url):
    lines = self.text_lines(html)
    year = self.year_from_url_or_lines(base_url, lines)
    if year is None:
      return []
    rows = []
    current_result = None
    for line in lines:
      key = normalize_heading(line)
      if re.match(r'^20\d{2}\s+winner$', key) or key.endswith(' morris award winner'):
        current_result = RESULT_WINNER
        continue
      if re.match(r'^20\d{2}\s+finalists?$', key) or key.endswith(' morris award finalists'):
        current_result = RESULT_SHORTLISTED
        continue
      if 'has been named the' in line and 'winner of the william c morris' in key:
        rows.extend(self.rows_from_text(year, line, RESULT_WINNER, base_url))
        current_result = None
        continue
      if 'morris award finalists' in key and 'include' in key:
        current_result = RESULT_SHORTLISTED
        remainder = re.sub(r'^.*?\binclude:?\s*', '', line, flags=re.I).strip()
        rows.extend(self.rows_from_text(year, remainder, RESULT_SHORTLISTED, base_url))
        continue
      if current_result not in {RESULT_WINNER, RESULT_SHORTLISTED}:
        continue
      parsed = self.rows_from_text(year, line, current_result, base_url)
      if parsed:
        rows.extend(parsed)
        if current_result == RESULT_WINNER:
          current_result = None
    return rows

  def yma_page_rows(self, html, base_url):
    lines = self.morris_section_lines(html)
    year = self.year_from_url_or_lines(base_url, lines)
    if year is None:
      return []
    rows = []
    current_result = None
    for line in lines:
      key = normalize_heading(line)
      if key == 'william c morris award':
        current_result = RESULT_WINNER
        continue
      if key == 'william c morris award finalists':
        current_result = RESULT_SHORTLISTED
        continue
      if current_result not in {RESULT_WINNER, RESULT_SHORTLISTED}:
        continue
      parsed = self.rows_from_text(year, line, current_result, base_url)
      if parsed:
        rows.extend(parsed)
        if current_result == RESULT_WINNER:
          current_result = None
    return rows

  def morris_section_lines(self, html):
    return self.section_lines(
      html,
      lambda key: key == 'william c morris award',
      self.is_next_yma_award_heading)

  def is_next_yma_award_heading(self, key):
    if key in {'william c morris award', 'william c morris award finalists'}:
      return False
    next_awards = (
      'award for excellence in nonfiction',
      'michael l printz award',
      'schneider family book award',
      'alex awards',
      'newbery',
      'caldecott',
    )
    return any(key.startswith(item) for item in next_awards)

  def annual_award_links(self, html, base_url=CURRENT_URL):
    return self.annual_award_links_matching(
      html,
      base_url,
      r'\b(20\d{2})\s+Morris Award\b')

  def clean_stage_prefix(self, text):
    text = super().clean_stage_prefix(text)
    text = re.sub(
      r'^\s*The\s+20\d{2}\s+Morris Award finalists?,\s+announced\s+in\s+December,\s+include:?\s*',
      '',
      text,
      flags=re.I)
    return text.strip()

  def clean_title_text(self, text):
    return normalize_line(text).strip(' "\'\u2018\u2019\u201c\u201d,.;:')

  def skip_history_line(self, line):
    key = normalize_heading(line)
    return (
      key in {'email', 'print', 'cite', 'share this page'}
      or key.startswith('learn more')
      or key.startswith('back to ')
      or key.startswith('previous morris'))


def parse_morris_award(html, base_url=HISTORY_URL, name=AWARD_NAME, **kwargs):
  return MorrisAwardParser().parse(html, base_url, name, **kwargs)
