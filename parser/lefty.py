#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Lefty Award parser for Stop, You're Killing Me archive pages.

Maintenance notes:
- Historical Mystery headings include a memorial/period qualifier in the same
  table cell as the category name. Remove that qualifier before the shared
  exact-category boundary check.
- Pre-2017 Humorous and Historical categories use earlier award names. Fetcher
  aliases preserve those rows as part of the same category lineages.
"""

import re

try:
  from calibre_plugins.list_switchboard.parser.stopyourekillingme_base import (
    StopYoureKillingMeAwardParserBase,
  )
except ImportError:
  from .stopyourekillingme_base import StopYoureKillingMeAwardParserBase


class LeftyAwardsParser(StopYoureKillingMeAwardParserBase):

  AWARD_NAME = 'Lefty Award'

  def clean_category_heading(self, text):
    text = super().clean_category_heading(text)
    if re.match(r'^Bruce Alexander Memorial Mystery Award\b', text, flags=re.I):
      return 'Bruce Alexander Memorial Mystery Award'
    return re.sub(
      r'\s*\([^)]*\bMemorial,\s*covering events before\s+(?:19|20)\d{2}\)\s*$',
      '',
      text,
      flags=re.I).strip()

  def looks_like_category_heading(self, text):
    if re.match(r'^\s*[*\u2217\u00b0]', text or ''):
      return False
    cleaned = self.clean_category_heading(text).casefold()
    older_named_category = (
      ' award ' in f' {cleaned} ' or
      cleaned.startswith('lefty award for ') or
      cleaned.startswith((
        'the rose ', 'the rosebud ', 'the squid ', 'the calamari ',
        'the panik ', 'hawaii five-o ',
      ))
    )
    return older_named_category or super().looks_like_category_heading(text)


def parse_lefty_awards(
    html, base_url, name, category, category_aliases=(), award_name=None):
  return LeftyAwardsParser().parse(
    html,
    base_url,
    name,
    category,
    category_aliases,
    award_name=award_name or LeftyAwardsParser.AWARD_NAME)
