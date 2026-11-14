#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Parser for the finite Spectology numbered book-club archive.

Maintenance notes:
- The official RSS feed is the complete runtime source. The HTML ``pre-read``
  category is not complete: its current first page omits cycle 24 and its
  pagination does not expose a dependable replacement archive.
- Numbered ``.1`` episodes identify selections. Post-reads, interviews,
  announcements, and digital-book-tour episodes are intentionally excluded.
- A few episode headings describe a theme rather than every selected work.
  Exact-title overrides below are bounded to the fetched episode heading so a
  changed live record is parsed normally instead of being silently overwritten.
"""

import re
from email.utils import parsedate_to_datetime

import feedparser
from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.base import (
    CATEGORY_FANTASY,
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    CATEGORY_SCIENCE_FICTION,
    entry_source_object,
    imported_entry,
    ListParserBase,
    parsed_source,
  )
except ImportError:
  from .base import (
    CATEGORY_FANTASY,
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    CATEGORY_SCIENCE_FICTION,
    entry_source_object,
    imported_entry,
    ListParserBase,
    parsed_source,
  )


FEED_URL = 'https://www.spectology.com/feed.xml'
SOURCE_ID = 'spectology'
CLUB_NAME = 'Spectology'
BASELINE_CYCLES = frozenset(range(1, 29))
NUMBERED_EPISODE_RE = re.compile(r'^(\d+)\.1\s*:\s*(.+)$', re.I)
PRE_READ_RE = re.compile(r'\bpre[\s-]*read\b', re.I)
NAME_TOKEN = r"(?:[A-Z](?:[\w'’.-]*|\.)|(?:[A-Z]\.){2,}|de|del|van|von)"
AUTHOR_AFTER_TITLE_RE = re.compile(
  rf'\bby\s+(?:new\s+British\s+author\s+)?'
  rf'(?P<author>{NAME_TOKEN}(?:\s+{NAME_TOKEN}){{0,5}})', re.U)


SOURCE_OVERRIDES = {
  1: {
    'episode_title': '1.1: Use of Weapons Pre-Read',
    'selections': (('Use of Weapons', ('Iain M. Banks',), None),),
  },
  3: {
    'episode_title': '3.1: The Binti Trilogy pre-read',
    'selections': (
      ('Binti', ('Nnedi Okorafor',), None),
      ('Binti: Home', ('Nnedi Okorafor',), None),
      ('Binti: The Night Masquerade', ('Nnedi Okorafor',), None),
    ),
  },
  4: {
    'episode_title': '4.1: The New & Improved Romie Futch pre-read',
    'selections': (
      ('The New and Improved Romie Futch', ('Julia Elliott',), None),
    ),
  },
  5: {
    'episode_title': (
      '5.1: Pre-read for Gnomon, by Nick Harkaway, with guest Max Gladstone'),
    'selections': (('Gnomon', ('Nick Harkaway',), None),),
  },
  7: {
    'episode_title': (
      '7.1: The Ballad of Black Tom pre-read: Race & the History of Horror Fiction'),
    'selections': (('The Ballad of Black Tom', ('Victor LaValle',), None),),
  },
  8: {
    'episode_title': '8.1: The Children of Time pre-read: What is "Hard" Science Fiction?',
    'selections': (('Children of Time', ('Adrian Tchaikovsky',), None),),
  },
  14: {
    'episode_title': (
      '14.1: The Raven Tower pre-read w/ Reading the End: Fantasy, Genre, & Gender!'),
    'selections': (('The Raven Tower', ('Ann Leckie',), None),),
  },
  16: {
    'episode_title': '16.1: Empress of Forever pre-read: Space Opera, Epics, & Journey to the West',
    'selections': (('Empress of Forever', ('Max Gladstone',), None),),
  },
  18: {
    'episode_title': (
      '18.1: Waste Tide pre-read: Chinese Language, Literary History, and Science Fiction'),
    'selections': (('Waste Tide', ('Chen Qiufan',), {'translator_credit': 'Ken Liu'}),),
  },
  19: {
    'episode_title': '19.1: Zone One pre-read: Zombies, Horror, and LitFic',
    'selections': (('Zone One', ('Colson Whitehead',), None),),
  },
  21: {
    'episode_title': (
      '21.1: Classic SF pre-read: On creating cannons, and how to read problematic fiction & authors.'),
    'selections': (
      ("Childhood's End", ('Arthur C. Clarke',), None),
      ('Ice', ('Anna Kavan',), None),
      ('Stars in My Pocket Like Grains of Sand', ('Samuel R. Delany',), None),
    ),
  },
  22: {
    'episode_title': (
      "22.1: A Memory Called Empire pre-read: Martine's academic work, historical ambassadors, "
      'and what it means to be a member of an empire'),
    'selections': (('A Memory Called Empire', ('Arkady Martine',), None),),
  },
  24: {
    'episode_title': (
      "24.1: Wittgenstein's Mistress pre-read: Philosophical Science Fiction & being lonely at "
      'the end of the world'),
    'selections': (("Wittgenstein's Mistress", ('David Markson',), None),),
  },
  25: {
    'episode_title': (
      '25.1: The Tea Master & the Detective pre-read w/ Julia Rios: Domestic Cozy Detective '
      'Fiction, in Space!'),
    'selections': (
      ('The Tea Master and the Detective', ('Aliette de Bodard',), None),
    ),
  },
  26: {
    'episode_title': (
      '26.1: The True Queen pre-read w/ Reading the End: Historical Fantasy, Trash Birds, and '
      'Chaotic Quarantine Brain'),
    'selections': (('The True Queen', ('Zen Cho',), None),),
  },
}


def normalize_line(value):
  return re.sub(r'\s+', ' ', str(value or '').replace('\xa0', ' ')).strip()


def episode_description(entry):
  content = entry.get('content') or ()
  if content and isinstance(content[0], dict) and content[0].get('value'):
    return content[0]['value']
  return entry.get('description') or entry.get('summary') or ''


class SpectologyParser(ListParserBase):
  """Parse official Spectology ``.1`` pre-read episodes into book entries."""

  FILTER_CATEGORIES = (
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    CATEGORY_SCIENCE_FICTION,
    CATEGORY_FANTASY,
  )

  def parse(self, payload, base_url=FEED_URL, name=None):
    self.reject_non_feed(payload)
    feed = feedparser.parse(payload or '')
    if feed.bozo:
      raise ValueError(f'Spectology returned malformed RSS: {feed.bozo_exception}')
    channel_title = normalize_line(feed.feed.get('title'))
    if 'spectology' not in channel_title.casefold():
      raise ValueError('Spectology RSS channel identity was not present in the response.')
    if not feed.entries:
      raise ValueError('Spectology RSS contained no episode entries.')

    selected = {}
    notes = []
    for episode in feed.entries:
      episode_title = normalize_line(episode.get('title'))
      match = NUMBERED_EPISODE_RE.match(episode_title)
      if match is None:
        continue
      cycle = int(match.group(1))
      if not PRE_READ_RE.search(match.group(2)):
        notes.append(
          f'Spectology cycle {cycle}.1 did not contain the required pre-read marker and was skipped.')
        continue
      if cycle in selected:
        raise ValueError(f'Spectology RSS contained duplicate cycle {cycle}.1 episodes.')
      selected[cycle] = episode

    missing = sorted(BASELINE_CYCLES.difference(selected))
    if missing:
      raise ValueError(
        'Spectology RSS was incomplete; missing baseline pre-read cycle(s): '
        + ', '.join(str(cycle) for cycle in missing))

    list_name = name or 'Spectology (discontinued)'
    list_source = parsed_source(list_name, base_url, SOURCE_ID)
    entries = []
    failed_baseline = []
    for cycle in sorted(selected):
      episode = selected[cycle]
      episode_title = normalize_line(episode.get('title'))
      selections = self.selections_for_episode(cycle, episode_title, episode)
      if not selections:
        notes.append(f'Spectology cycle {cycle}.1 did not expose a usable title and author credit.')
        if cycle in BASELINE_CYCLES:
          failed_baseline.append(cycle)
        continue
      event_date = self.episode_date(episode)
      if not event_date:
        notes.append(f'Spectology cycle {cycle}.1 did not expose a valid publication date.')
      episode_url = normalize_line(episode.get('link'))
      event_group_id = f'spectology:{cycle}.1' if len(selections) > 1 else None
      for component_index, (title, authors, extra) in enumerate(selections, 1):
        metadata = dict(extra or {})
        source_record_id = f'spectology:{cycle}.1'
        if len(selections) > 1:
          source_record_id += f':{component_index}'
          metadata['component_index'] = component_index
        metadata.update({
          'club_name': CLUB_NAME,
          'priority_group': 'A',
          'recipe_scope': 'finite numbered pre-read cycles',
          'program_era': 'numbered book-club cycles',
          'theme_or_track': 'pre-read cycle',
          'selection_type': 'episode_selection',
          'region': 'Global',
          'is_reread': False,
          'official_sequence': cycle,
          'source_record_id': source_record_id,
          'event_group_id': event_group_id,
          'selection_url': episode_url or None,
          'raw_episode_title': episode_title,
        })
        if event_date:
          metadata.update({
            'event_date': event_date,
            'selection_year': event_date[:4],
            'selection_month': str(int(event_date[5:7])),
          })
        entries.append(imported_entry(
          '', title, authors,
          source=entry_source_object(
            episode_url, CLUB_NAME, SOURCE_ID, list_source=list_source),
          **metadata))

    if failed_baseline:
      raise ValueError(
        'Spectology RSS baseline cycle(s) could not be parsed: '
        + ', '.join(str(cycle) for cycle in failed_baseline))
    if not entries:
      raise ValueError('Spectology RSS exposed no usable numbered pre-read selections.')
    for position, entry in enumerate(entries, 1):
      entry['position'] = str(position)
    notes.append(
      'Spectology is a finite archive: the official site announced its series finale in '
      'October 2020, so append updates are not expected.')
    return {
      'name': list_name,
      'source': list_source,
      'entries': entries,
      'notes': notes,
      'match_series': False,
    }

  def reject_non_feed(self, payload):
    if isinstance(payload, bytes):
      text = payload.decode('utf-8', 'replace').lstrip()
    else:
      text = str(payload or '').lstrip()
    if not text:
      raise ValueError('Spectology returned an empty response instead of RSS.')
    lowered = text[:5000].casefold()
    if text.startswith('<!DOCTYPE html') or text.startswith('<html'):
      raise ValueError('Spectology returned HTML instead of its RSS feed.')
    if any(marker in lowered for marker in (
        'please wait for verification', 'just a moment', 'access denied', 'captcha')):
      raise ValueError('Spectology returned a verification or blocking response instead of RSS.')

  def selections_for_episode(self, cycle, episode_title, episode):
    override = SOURCE_OVERRIDES.get(cycle)
    if override and episode_title == override['episode_title']:
      return list(override['selections'])
    title = self.title_from_episode_heading(episode_title)
    if not title:
      return []
    author = self.author_from_description(title, episode_description(episode))
    return [(title, (author,), None)] if author else []

  def title_from_episode_heading(self, episode_title):
    match = NUMBERED_EPISODE_RE.match(episode_title)
    body = match.group(2) if match else ''
    leading = re.match(r'^pre[\s-]*read\s+for\s+(.+?)(?:,\s*by\s+|$)', body, re.I)
    if leading:
      return leading.group(1).strip(' ,:;.-')
    title = PRE_READ_RE.split(body, maxsplit=1)[0]
    title = re.split(r'\s+by\s+', title, maxsplit=1, flags=re.I)[0]
    return title.strip(' ,:;.-')

  def author_from_description(self, title, description):
    soup = BeautifulSoup(str(description or ''), 'html.parser')
    blocks = soup.find_all(['p', 'li'])
    if not blocks:
      blocks = [soup]
    title_key = normalize_line(title).casefold()
    for block in blocks[:12]:
      text = normalize_line(block.get_text(' ', strip=True))
      index = text.casefold().find(title_key)
      if index < 0:
        continue
      tail = text[index + len(title):index + len(title) + 180]
      match = AUTHOR_AFTER_TITLE_RE.search(tail)
      if match:
        return normalize_line(match.group('author')).strip(' ,.;')
    return ''

  def episode_date(self, episode):
    published = normalize_line(episode.get('published'))
    if published:
      try:
        return parsedate_to_datetime(published).date().isoformat()
      except (TypeError, ValueError, OverflowError):
        pass
    parts = episode.get('published_parsed')
    if parts:
      try:
        return f'{parts.tm_year:04d}-{parts.tm_mon:02d}-{parts.tm_mday:02d}'
      except (AttributeError, TypeError, ValueError):
        pass
    return ''


def parse_spectology(payload, base_url=FEED_URL, name=None):
  return SpectologyParser().parse(payload, base_url, name=name)
