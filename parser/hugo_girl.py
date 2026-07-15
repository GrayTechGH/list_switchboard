#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Parser for the Hugo, Girl! numbered book-discussion archive.

Maintenance notes:
- The Libsyn RSS feed is the freshest complete source. The Squarespace All
  Episodes page is a replacement fallback and can lag the feed.
- Numbered episodes are the source-record boundary, but not every numbered
  episode is a book selection. Screen-only episodes, short stories, and
  novelettes are excluded; novels, nonfiction books, and novellas are kept.
- Exact source corrections apply only while the fetched episode heading still
  matches. Changed live rows are parsed normally so repaired source data wins.
"""

from email.utils import parsedate_to_datetime
import re

import feedparser
from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.base import (  # type: ignore
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


CLUB_NAME = 'Hugo, Girl!'
LIST_NAME = 'Hugo Girl!'
NAME = CLUB_NAME
SOURCE_ID = 'hugo_girl'
RSS_URL = 'https://hugogirl.libsyn.com/rss'
ARCHIVE_URL = 'https://www.hugogirlpodcast.com/all-episodes'
BASELINE_EPISODES = frozenset(range(1, 94))
EPISODE_RE = re.compile(r'^Episode\s+(\d+)\s*[-:]\s*(.+)$', re.I)
AUTHOR_TOKEN = r"(?:[A-Z][\w'’.-]*|(?:[A-Z]\.){1,4}|de|del|van|von)"
AUTHOR_RE = rf'{AUTHOR_TOKEN}(?:\s+{AUTHOR_TOKEN}){{0,7}}'


# These are content-scope decisions, not title/author corrections. Requiring
# the exact live heading prevents a repurposed episode number from remaining
# excluded after the publisher changes it.
SOURCE_EXCLUSIONS = {
  13: "Episode 13: Bloodchild - Mademoiselle T'Gatoi (and a special announcement!)",
  44: 'Episode 44 - Jupiter Ascending: I Love Dogs!',
  46: 'Episode 46 - Event Horizon: No Actual Boding',
  67: 'Episode 67: Hugo Girls Gone Wild: Twilight: OnlyFangs',
  70: 'Episode 70 - The Ones Who Walk Away from Omelas: The Pilot',
  74: 'Episode 74 - Better Living Through Algorithms',
  79: 'Episode 79 - Moby-Dick at the Opera',
  85: "Episode 85 - Francis Ford Coppola's Bram Stoker's Dracula - Is This Mamma Mia?",
  91: 'Episode 91 - Battleship: Boobish Behavior',
  94: 'Episode 94 - Attack the Block: Hairy Aliens for Once',
}


# Rows whose prose does not expose a dependable title/author pair. Corrections
# require both the episode heading and a stable description fragment.
SOURCE_CORRECTIONS = {
  5: {
    'episode_title': 'Episode 5: The Left Hand of Darkness - TOO MALTY',
    'description_fragment': 'we dove into the sci-fi classic',
    'title': 'The Left Hand of Darkness',
    'authors': ('Ursula K. Le Guin',),
  },
  8: {
    'episode_title': 'Episode 8: Rendezvous With Rama - Big Dumb Object',
    'description_fragment': "December's selection was",
    'title': 'Rendezvous with Rama',
    'authors': ('Arthur C. Clarke',),
  },
  10: {
    'episode_title': 'Episode 10: The Man in the High Castle - This Could Have Just Been Bullet Points',
    'description_fragment': "February's selection is",
    'title': 'The Man in the High Castle',
    'authors': ('Philip K. Dick',),
  },
  11: {
    'episode_title': 'Episode 11: Speaker for the Dead - Bugger Duggars',
    'description_fragment': 'we revisit Ender Wiggin',
    'title': 'Speaker for the Dead',
    'authors': ('Orson Scott Card',),
  },
  16: {
    'episode_title': 'Episode 16: Ancillary Justice - Ship Protecc, Ship Attacc',
    'description_fragment': 'the first book in Ann Leckie',
    'title': 'Ancillary Justice',
    'authors': ('Ann Leckie',),
  },
  17: {
    'episode_title': 'Episode 17: Jonathan Strange & Mr Norrell - Rad Bromance',
    'description_fragment': 'a supersized episode for a supersized book',
    'title': 'Jonathan Strange & Mr Norrell',
    'authors': ('Susanna Clarke',),
  },
  18: {
    'episode_title': 'Episode 18: The Courtship of Princess Leia - Toyota Corellia',
    'description_fragment': 'a comfort read chosen by Haley',
    'title': 'The Courtship of Princess Leia',
    'authors': ('Dave Wolverton',),
  },
  21: {
    'episode_title': 'Episode 21 - To Your Scattered Bodies Go: The Crossover',
    'description_fragment': 'releasing the crossover episode',
    'title': 'To Your Scattered Bodies Go',
    'authors': ('Philip José Farmer',),
  },
  23: {
    'episode_title': 'Episode 23 - The Obelisk Gate: Butter Marble',
    'description_fragment': 'GEORGIA IS BLUE',
    'title': 'The Obelisk Gate',
    'authors': ('N. K. Jemisin',),
  },
  24: {
    'episode_title': 'Episode 24 - The Stone Sky: Hippopotabus',
    'description_fragment': 'conclusion of NK Jemisin',
    'title': 'The Stone Sky',
    'authors': ('N. K. Jemisin',),
  },
  26: {
    'episode_title': 'Episode 26 - The Fellowship of the Ring: My Favorite Mordor',
    'description_fragment': 'sensational jewelry heist',
    'title': 'The Fellowship of the Ring',
    'authors': ('J. R. R. Tolkien',),
  },
  30: {
    'episode_title': 'Episode 30 - The City & the City: Earl Kerma',
    'description_fragment': 'The City and the City by China',
    'title': 'The City & the City',
    'authors': ('China Miéville',),
  },
  31: {
    'episode_title': 'Episode 31 - Murderbot Diaries - All Systems Red: Jahoob Talk',
    'description_fragment': 'Murderbot is all of us',
    'title': 'All Systems Red',
    'authors': ('Martha Wells',),
  },
  34: {
    'episode_title': 'Episode 34 - Foundation: Tokyo Drift',
    'description_fragment': "Isaac Asimov's groundbreaking novel",
    'title': 'Foundation',
    'authors': ('Isaac Asimov',),
  },
  37: {
    'episode_title': 'Episode 37 - Barrayar: Vorld of Vorkraft',
    'description_fragment': 'an oppressive fantasy feeling',
    'title': 'Barrayar',
    'authors': ('Lois McMaster Bujold',),
  },
  42: {
    'episode_title': 'Episode 42 - 2001: A Space Odyssey: Friends of Hal',
    'description_fragment': 'we read and watched 2001',
    'title': '2001: A Space Odyssey',
    'authors': ('Arthur C. Clarke',),
  },
  47: {
    'episode_title': 'Episode 47 - The Word for World is Forest: Little Green Men',
    'description_fragment': "It's Novella-vember",
    'title': 'The Word for World Is Forest',
    'authors': ('Ursula K. Le Guin',),
  },
  48: {
    'episode_title': 'Episode 48 - Houston, Houston, Do You Read?: Clone Wars',
    'description_fragment': 'week 2 of Novella-vember',
    'title': 'Houston, Houston, Do You Read?',
    'authors': ('James Tiptree Jr.',),
  },
  51: {
    'episode_title': 'Episode 51 - Neuromancer: Peppered with Breasts',
    'description_fragment': 'noted orange cat owner',
    'title': 'Neuromancer',
    'authors': ('William Gibson',),
  },
  62: {
    'episode_title': 'Episode 62 - Blood of the Dragon: Dugs Talk',
    'description_fragment': 'consists of the Daenerys chapters',
    'title': 'Blood of the Dragon',
    'authors': ('George R. R. Martin',),
  },
  69: {
    'episode_title': 'Episode 69 - Mirror Dance: Res-erection',
    'description_fragment': 'Another attack of the clones',
    'title': 'Mirror Dance',
    'authors': ('Lois McMaster Bujold',),
  },
  71: {
    'episode_title': "Episode 71 - This is How You Lose the Time War: Blue & Red's Excellent Adventure",
    'description_fragment': 'Being gay and doing crime',
    'title': 'This Is How You Lose the Time War',
    'authors': ('Amal El-Mohtar', 'Max Gladstone'),
  },
  75: {
    'episode_title': 'Episode 75 - Red Mars: Other Effluvia',
    'description_fragment': "This wasn't so bad",
    'title': 'Red Mars',
    'authors': ('Kim Stanley Robinson',),
  },
  76: {
    'episode_title': "Episode 76 - A Deepness in the Sky: That's Just Like, Your Opinion, Cobber",
    'description_fragment': 'Y2K Hugo winner',
    'title': 'A Deepness in the Sky',
    'authors': ('Vernor Vinge',),
  },
  77: {
    'episode_title': 'Episode 77 - The Wanderer: Horniest Hugo Winner',
    'description_fragment': "you'll wander why",
    'title': 'The Wanderer',
    'authors': ('Fritz Leiber',),
  },
  78: {
    'episode_title': "Episode 78 - The Vor Game: Jackson's Whole Grimussy",
    'description_fragment': 'Miles is back at it',
    'title': 'The Vor Game',
    'authors': ('Lois McMaster Bujold',),
  },
  84: {
    'episode_title': 'Episode 84 - Redshirts: All I Got Was This Stupid T-shirt',
    'description_fragment': 'reading Redshirts',
    'title': 'Redshirts',
    'authors': ('John Scalzi',),
  },
  89: {
    'episode_title': 'Episode 89 - Endurance: Rotten Ice',
    'description_fragment': 'Endurance: Shackleton',
    'title': "Endurance: Shackleton's Incredible Voyage",
    'authors': ('Alfred Lansing',),
  },
}


def normalize_line(value):
  return re.sub(r'\s+', ' ', str(value or '').replace('\xa0', ' ')).strip()


def clean_title(value):
  value = normalize_line(value)
  value = re.sub(r'^Book\s*:\s*', '', value, flags=re.I)
  return value.strip(' "\'“”‘’,.;:-')


def clean_author(value):
  value = normalize_line(value)
  # The last period in compact initials such as "N.K. Jemisin" is not a
  # sentence boundary. A standalone capital immediately before it identifies
  # an initial while ordinary prose endings still trim trailing text.
  value = re.split(
    r'(?<!\b[A-Z])\.\s+(?=[A-Z][a-z])', value, maxsplit=1)[0]
  value = re.split(
    r'\s+(?:which|who|and\s+(?:it|we|the)|with\s+guest|for\s+the)\b',
    value, maxsplit=1, flags=re.I)[0]
  return value.strip(' "\'“”‘’,.;:-')


def source_identity(value):
  value = normalize_line(value).replace('�', '-').replace('—', '-').replace('–', '-')
  value = re.sub(r'\s*-\s*', ' - ', value)
  return value.casefold()


def source_fragment(value):
  value = normalize_line(value).replace('’', "'")
  return re.sub(r'\W+', ' ', value, flags=re.U).strip().casefold()


def episode_description(entry):
  content = entry.get('content') or ()
  if content and isinstance(content[0], dict) and content[0].get('value'):
    return content[0]['value']
  return entry.get('description') or entry.get('summary') or ''


class HugoGirlParser(ListParserBase):
  """Parse official numbered prose-book discussions into import entries."""

  FILTER_CATEGORIES = (
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    CATEGORY_SCIENCE_FICTION,
    CATEGORY_FANTASY,
  )

  def parse(self, payload, name=LIST_NAME):
    if self.looks_like_html(payload):
      records = self.html_records(payload)
      source_url = ARCHIVE_URL
      source_kind = 'html'
    else:
      records = self.rss_records(payload)
      source_url = RSS_URL
      source_kind = 'rss'

    self.validate_records(records)
    list_source = parsed_source(CLUB_NAME, source_url, SOURCE_ID)
    notes = []
    entries = []
    for episode_number in sorted(records):
      record = records[episode_number]
      if (
          self.excluded_record(episode_number, record)
          or self.explicitly_out_of_scope(record)):
        continue
      selection = self.selection_for_record(episode_number, record)
      if selection is None:
        message = (
          f'{NAME} Episode {episode_number} did not expose a dependable '
          'book-form title and author and was skipped.')
        if episode_number in BASELINE_EPISODES:
          raise ValueError(message)
        notes.append(message)
        continue
      title, authors = selection
      metadata = {
        'club_name': NAME,
        'priority_group': 'A',
        'recipe_scope': 'numbered book and novella discussions',
        'program_era': 'numbered podcast episodes',
        'theme_or_track': 'main numbered episode',
        'selection_type': 'episode_selection',
        'region': 'Global',
        'is_reread': False,
        'official_sequence': episode_number,
        'source_record_id': f'hugogirl:{episode_number}',
        'selection_url': record.get('url') or None,
        'raw_episode_title': record['episode_title'],
      }
      event_date = record.get('event_date') or ''
      if event_date:
        metadata.update({
          'event_date': event_date,
          'selection_year': event_date[:4],
          'selection_month': str(int(event_date[5:7])),
        })
      entries.append(imported_entry(
        '',
        title,
        authors,
        source=entry_source_object(
          record.get('url'), NAME, SOURCE_ID, list_source=list_source),
        **metadata))

    if not entries:
      raise ValueError(f'{NAME} exposed no usable numbered book discussions.')
    for position, entry in enumerate(entries, 1):
      entry['position'] = str(position)
    if source_kind == 'html':
      notes.append(
        'Hugo, Girl! used the All Episodes page because the fresher Libsyn RSS '
        'source was unavailable. The page can lag the feed and does not expose '
        'episode publication dates.')
    parsed = {
      'name': name,
      'source': list_source,
      'entries': entries,
      'match_series': False,
    }
    if notes:
      parsed['notes'] = notes
    return parsed

  def looks_like_html(self, payload):
    if isinstance(payload, bytes):
      text = payload[:5000].decode('utf-8', 'replace')
    else:
      text = str(payload or '')[:5000]
    lowered = text.lstrip().casefold()
    return lowered.startswith('<!doctype html') or lowered.startswith('<html')

  def rss_records(self, payload):
    if not payload:
      raise ValueError(f'{NAME} returned an empty response instead of RSS.')
    feed = feedparser.parse(payload)
    if feed.bozo:
      raise ValueError(f'{NAME} returned malformed RSS: {feed.bozo_exception}')
    channel_title = normalize_line(feed.feed.get('title'))
    if channel_title.casefold() != NAME.casefold():
      raise ValueError(f'{NAME} RSS channel identity was not present in the response.')
    if not feed.entries:
      raise ValueError(f'{NAME} RSS contained no episode entries.')
    records = {}
    for item in feed.entries:
      episode_title = normalize_line(item.get('title'))
      match = EPISODE_RE.match(episode_title)
      if match is None:
        continue
      episode_number = int(match.group(1))
      if episode_number in records:
        raise ValueError(f'{NAME} contained duplicate Episode {episode_number} records.')
      description_html = episode_description(item)
      records[episode_number] = {
        'episode_title': episode_title,
        'description_html': str(description_html or ''),
        'description_text': self.description_text(description_html),
        'url': normalize_line(item.get('link')),
        'event_date': self.episode_date(item),
      }
    return records

  def html_records(self, payload):
    soup = BeautifulSoup(payload or '', 'html.parser')
    title = normalize_line(soup.title.get_text(' ', strip=True) if soup.title else '')
    if 'hugo, girl' not in title.casefold() or 'all episodes' not in title.casefold():
      raise ValueError(
        f'{NAME} returned a challenge, empty, or unrecognized All Episodes page.')
    records = {}
    for item in soup.select('li.list-item'):
      heading = item.select_one('.list-item-content__title')
      description = item.select_one('.list-item-content__description')
      episode_title = normalize_line(
        heading.get_text(' ', strip=True) if heading is not None else '')
      match = EPISODE_RE.match(episode_title)
      if match is None:
        continue
      episode_number = int(match.group(1))
      if episode_number in records:
        raise ValueError(f'{NAME} contained duplicate Episode {episode_number} records.')
      link = None if description is None else description.find(
        'a', href=re.compile(r'^https?://hugogirl\.libsyn\.com/', re.I))
      description_html = str(description or '')
      records[episode_number] = {
        'episode_title': episode_title,
        'description_html': description_html,
        'description_text': self.description_text(description_html),
        'url': normalize_line(link.get('href')) if link is not None else '',
        'event_date': '',
      }
    return records

  def description_text(self, description):
    soup = BeautifulSoup(str(description or ''), 'html.parser')
    blocks = []
    for node in soup.find_all(['p', 'div', 'li'], recursive=True):
      if node.find_parent(['p', 'div', 'li']) is not None:
        continue
      text = normalize_line(node.get_text(' ', strip=True))
      if text:
        blocks.append(text)
    if not blocks:
      blocks = [normalize_line(soup.get_text(' ', strip=True))]
    return normalize_line(' '.join(blocks[:4]))

  def validate_records(self, records):
    if not records:
      raise ValueError(f'{NAME} contained no numbered episode records.')
    missing_baseline = sorted(BASELINE_EPISODES.difference(records))
    if missing_baseline:
      raise ValueError(
        f'{NAME} source was incomplete; missing baseline Episode(s): '
        + ', '.join(str(number) for number in missing_baseline))
    highest = max(records)
    missing_sequence = sorted(set(range(1, highest + 1)).difference(records))
    if missing_sequence:
      raise ValueError(
        f'{NAME} numbered episode sequence was incomplete; missing Episode(s): '
        + ', '.join(str(number) for number in missing_sequence))

  def excluded_record(self, episode_number, record):
    excluded_title = SOURCE_EXCLUSIONS.get(episode_number)
    return bool(
      excluded_title
      and source_identity(record['episode_title']) == source_identity(excluded_title))

  def explicitly_out_of_scope(self, record):
    text = record['description_text'][:500]
    if re.search(r'\b(?:short story|novelette)\b', text, re.I):
      return True
    if not re.search(r'\b(?:movie|film|TV show|opera)\b', text, re.I):
      return False
    return not (
      re.search(r'\bread\s+and\s+watched\b', text, re.I)
      or re.search(r'\b(?:book|novel|novella)\b', text, re.I))

  def selection_for_record(self, episode_number, record):
    correction = SOURCE_CORRECTIONS.get(episode_number)
    if (
        correction
        and source_identity(record['episode_title']) == source_identity(
          correction['episode_title'])
        and source_fragment(correction['description_fragment']) in source_fragment(
          record['description_text'])):
      return correction['title'], list(correction['authors'])
    title = self.title_from_heading(record['episode_title'])
    explicit_title = self.title_from_description(record)
    if explicit_title and (
        re.search(r'\bBook\s*:', record['description_text'], re.I)
        or self.same_title_or_more_specific(title, explicit_title)):
      title = explicit_title
    author = self.author_from_description(title, record['description_text'])
    if not title or not author:
      return None
    return title, [author]

  def same_title_or_more_specific(self, heading_title, explicit_title):
    heading_key = normalize_line(heading_title).casefold().replace('&', 'and')
    explicit_key = normalize_line(explicit_title).casefold().replace('&', 'and')
    return bool(
      heading_key == explicit_key
      or explicit_key.startswith(heading_key + ':'))

  def title_from_description(self, record):
    text = record['description_text']
    book_match = re.search(
      rf'\bBook\s*:\s*(?P<title>.+?)\s+by\s+'
      rf'(?P<author>{AUTHOR_RE})(?=\s*[,.;!(]|$)',
      text, re.I | re.U)
    if book_match:
      return clean_title(book_match.group('title'))
    read_match = re.search(
      rf'\b(?:read|discussed|read\s+and\s+discussed)\s+'
      rf'(?P<title>[^.!?]{{2,140}}?)\s*,?\s+by\s+'
      rf'(?P<author>{AUTHOR_RE})(?=\s*[,.;!(]|$)',
      text, re.I | re.U)
    if read_match:
      title = clean_title(read_match.group('title'))
      title = re.sub(
        r'^(?:and\s+discussed\s+|the\s+[^.!?]{0,35}?\b(?:book|novel)\s+)',
        '', title, flags=re.I)
      return clean_title(title)
    return ''

  def title_from_heading(self, episode_title):
    match = EPISODE_RE.match(episode_title)
    body = match.group(2) if match else ''
    body = re.split(r'\s+[—–-]\s+', body, maxsplit=1)[0]
    body = body.split(':', 1)[0]
    return clean_title(body)

  def author_from_description(self, title, text):
    if not title:
      return ''
    title_pattern = re.escape(title).replace(r'\ ', r'\s+')
    title_pattern = title_pattern.replace(r'\&', r'(?:&|and)')
    title_pattern = title_pattern.replace('&', r'(?:&|and)')
    after = re.search(
      rf'\b(?i:{title_pattern})\s*,?\s+(?i:by)\s+'
      rf'(?P<author>{AUTHOR_RE})(?=\s*[,.;!(]|$)',
      text, re.U)
    if after:
      return clean_author(after.group('author'))
    before = re.search(
      rf'(?:\b(?i:read|discuss(?:ed|ing)?|tackled|on)\s+|'
      rf'\b(?i:selection)\s+(?i:was|is)\s+|,\s*)'
      rf'(?P<author>{AUTHOR_RE})[\'’]s?\s+'
      rf'(?:[^.!?]{{0,80}}?\s+)?["“]?(?i:{title_pattern})'
      rf'(?=\s*[,.;!"”]|$)',
      text, re.U)
    if before:
      return clean_author(before.group('author'))
    after_possessive = re.search(
      rf'\b(?i:{title_pattern})\s*,\s*'
      rf'(?P<author>{AUTHOR_RE})[\'’]s?\b',
      text, re.U)
    if after_possessive:
      return clean_author(after_possessive.group('author'))
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


def parse_hugo_girl(payload, name=LIST_NAME):
  return HugoGirlParser().parse(payload, name=name)
