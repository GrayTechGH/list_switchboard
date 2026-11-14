#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Anthony Award parser for Stop, You're Killing Me archive pages.
"""

try:
  from calibre_plugins.list_switchboard.parser.stopyourekillingme_base import (
    StopYoureKillingMeAwardParserBase,
  )
except ImportError:
  from .stopyourekillingme_base import StopYoureKillingMeAwardParserBase


class AnthonyAwardsParser(StopYoureKillingMeAwardParserBase):

  AWARD_NAME = 'Anthony Award'
  AUTHOR_CREDIT_CORRECTIONS = {
    # The SYKM 2020 winner row omits the delimiter between its first two
    # editors; Bouchercon's award history identifies all three explicitly.
    'verena rose rita owen and shawn reilly simmons': (
      'Verena Rose', 'Rita Owen', 'Shawn Reilly Simmons'),
  }


def parse_anthony_awards(
    html, base_url, name, category, category_aliases=(), award_name=None):
  return AnthonyAwardsParser().parse(
    html,
    base_url,
    name,
    category,
    category_aliases,
    award_name=award_name or AnthonyAwardsParser.AWARD_NAME)
