#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Agatha Award parser for Stop, You're Killing Me archive pages.
"""

try:
  from calibre_plugins.list_switchboard.parser.stopyourekillingme_base import (
    StopYoureKillingMeAwardParserBase,
  )
except ImportError:
  from .stopyourekillingme_base import StopYoureKillingMeAwardParserBase


class AgathaAwardsParser(StopYoureKillingMeAwardParserBase):

  AWARD_NAME = 'Agatha Award'


def parse_agatha_awards(
    html, base_url, name, category, category_aliases=(), award_name=None):
  return AgathaAwardsParser().parse(
    html,
    base_url,
    name,
    category,
    category_aliases,
    award_name=award_name or AgathaAwardsParser.AWARD_NAME)
