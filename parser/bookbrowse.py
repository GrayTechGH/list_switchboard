#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Parse the legacy and current BookBrowse Online Book Club sources.

Maintenance notes:
- The legacy BookTalk page is cumulative. Its numbered pages repeat an
  increasingly small tail of the same archive and must not be crawled.
- Current official selections are Discourse child categories of parent ID 5.
  Merely living under that parent is insufficient: side reads and other
  community categories are rejected unless their description identifies a
  BookBrowse-hosted discussion of one named book.
- Missing current-category dates are enrichment failures, not missing books.
  The category identity is retained and the failure is reported in notes.
"""

import json
import re
from datetime import date, datetime
from urllib.parse import parse_qs, quote, urljoin, urlparse

from lxml import html as lxml_html

try:
  from calibre_plugins.list_switchboard.parser.base import (
    entry_source_object,
    imported_entry,
    parsed_source,
  )
  from calibre_plugins.list_switchboard.parser.award_base import normalize_line
  from calibre_plugins.list_switchboard.parser.bookbrowse_base import (
    BookBrowseBookClubParserBase,
  )
except ImportError:
  from .base import entry_source_object, imported_entry, parsed_source
  from .award_base import normalize_line
  from .bookbrowse_base import BookBrowseBookClubParserBase


LEGACY_URL = 'https://www.bookbrowse.com/booktalk/index.cfm'
COMMUNITY_URL = 'https://community.bookbrowse.com'
CATEGORIES_URL = COMMUNITY_URL + '/site.json'
PARENT_CATEGORY_ID = 5
CATEGORY = 'BookBrowse Online Book Club'
CHALLENGE_MARKERS = (
  'just a moment', 'checking your browser', 'enable javascript and cookies',
  'cf-challenge', 'challenge-platform')
DISCUSSION_DESCRIPTION = re.compile(
  r'\b(?:please\s+)?join\s+(?:bookbrowse|us)\b'
  r'.*?\b(?:a\s+)?(?:book\s+club\s+)?discussion\s+(?:of|about)\s+'
  r'(.+?)\s+by\s+(.+?)(?:[.!]|$)',
  re.I)
OPENS_DATE = re.compile(
  r'\bOpens\s+(\d{1,2})\s+'
  r'(January|February|March|April|May|June|July|August|September|October|November|December)\b',
  re.I)
MONTHS = {
  month.casefold(): index for index, month in enumerate((
    'January', 'February', 'March', 'April', 'May', 'June', 'July',
    'August', 'September', 'October', 'November', 'December'), 1)
}


class BookBrowseOnlineBookClubParser(BookBrowseBookClubParserBase):

  DATE_ENRICHMENT_LIMIT = 8

  def parse(
      self, landing_html, base_url, name='BookBrowse Online Book Club',
      fetch_url=None, current_date=None, progress=None):
    if fetch_url is None:
      raise ValueError('BookBrowse parsing requires linked-source fetching.')
    self.require_real_page(landing_html, 'BookBrowse Online Book Club landing page')
    today = current_date or date.today()
    if isinstance(today, str):
      today = date.fromisoformat(today)

    legacy_html = fetch_url(LEGACY_URL)
    legacy = self.parse_legacy(legacy_html, name)

    upcoming, upcoming_notes = self.parse_upcoming(
      landing_html, base_url, fetch_url, name, today, progress=progress)
    categories_payload = fetch_url(CATEGORIES_URL)
    current, notes = self.parse_current(
      categories_payload, fetch_url, name, progress=progress)
    notes[:0] = upcoming_notes

    entries = self.merge_entries(legacy + upcoming + current)
    for position, entry in enumerate(entries, 1):
      entry['position'] = str(position)
      entry.pop('_source_order', None)
      entry.pop('_era_rank', None)
    return {
      'name': name,
      'source': parsed_source(name, base_url),
      'entries': entries,
      'notes': notes,
      'match_series': False,
    }

  def parse_legacy(self, html, name):
    self.require_real_page(html, 'BookBrowse legacy BookTalk archive')
    root = lxml_html.fromstring(html or '<html></html>')
    entries = []
    current_year = None
    source_order = 0
    for heading in root.xpath('//h1|//h2|//h3'):
      text = self.node_text(heading)
      year = self.year_from_heading(text)
      if year is not None:
        current_year = year
        continue
      if current_year is None or heading.tag.lower() != 'h2':
        continue
      title, credit = self.title_author_from_text(text)
      if not title or not credit:
        title, credit = self.legacy_description_identity(heading)
      authors = self.authors_from_credit(credit)
      if not title or not authors:
        continue
      source_url = self.source_url_from_heading(heading, LEGACY_URL)
      record_id = self.legacy_record_id(source_url)
      if not record_id:
        continue
      source_order += 1
      entries.append(imported_entry(
        '', title, authors,
        source=entry_source_object(source_url, name, record_id),
        club_name=name,
        category=CATEGORY,
        selection_type='discussion_selection',
        discussion_year=str(current_year),
        program_era='legacy_booktalk',
        source_record_id=f'bookbrowse-booktalk:{record_id}',
        _source_order=source_order,
        _era_rank=1,
      ))
    if not entries or not any(entry.get('discussion_year') == '2011' for entry in entries):
      raise ValueError('BookBrowse legacy archive did not expose its complete 2011-present shape.')
    return entries

  def legacy_description_identity(self, heading):
    rows = heading.xpath('ancestor::div[contains(concat(" ", normalize-space(@class), " "), " clear_row ")][1]')
    if not rows:
      return '', ''
    descriptions = rows[0].xpath('.//*[contains(concat(" ", normalize-space(@class), " "), " forumDesc ")]')
    description = self.node_text(descriptions[0]) if descriptions else ''
    match = re.search(r'\bDiscuss\s+(.+?)\s+by\s+(.+?)(?:[.!]|$)', description, re.I)
    if match:
      return self.clean_title(match.group(1)), self.clean_author(match.group(2))
    title, credit = self.title_author_from_text(description)
    if title and credit:
      return title, credit
    # One legacy row describes the author before the title instead of using a
    # normal discussion label. The relationship is still explicit live data.
    match = re.search(r'^From\s+(.+?),\s+author\s+of\b', description, re.I)
    if match:
      title = re.sub(r'\s+Book\s+Club\s+Discussion$', '', self.node_text(heading), flags=re.I)
      return self.clean_title(title), self.clean_author(match.group(1))
    return '', ''

  def legacy_record_id(self, source_url):
    values = parse_qs(urlparse(source_url).query).get('forumid', ())
    return values[0] if values else ''

  def parse_current(self, payload, fetch_url, name, progress=None):
    data = self.json_object(payload, 'BookBrowse Discourse category index')
    categories = [
      item for item in data.get('categories', [])
      if item.get('parent_category_id') == PARENT_CATEGORY_ID]
    if not categories:
      raise ValueError('BookBrowse Discourse index did not expose book-club child categories.')
    entries = []
    enrichment = []
    notes = []
    total = len(categories)
    for index, category in enumerate(categories, 1):
      category_id = category.get('id')
      if progress is not None:
        progress(index - 1, total, f'Parsing BookBrowse discussion {index} of {total}')
      title, authors = self.current_identity(category)
      if not title or not authors:
        continue
      category_url = urljoin(COMMUNITY_URL, f"/c/{category.get('slug')}/{category_id}")
      topic_url = category.get('topic_url') or ''
      metadata = {
        'club_name': name,
        'category': CATEGORY,
        'selection_type': 'discussion_selection',
        'program_era': 'discourse_community',
        'source_record_id': f'bookbrowse-discourse-category:{category_id}',
        '_source_order': int(category_id),
        '_era_rank': 3,
      }
      entry = imported_entry(
        '', title, authors,
        source=entry_source_object(category_url, name, str(category_id)),
        **metadata)
      entries.append(entry)
      if topic_url:
        enrichment.append((entry, topic_url, category_id, title))
    # Fetch all required category identities before optional date enrichment.
    # BookBrowse can throttle long bursts; a late About-topic failure must not
    # discard a fully identified official selection.
    enrichment = sorted(
      enrichment, key=lambda item: int(item[2]), reverse=True
    )[:self.DATE_ENRICHMENT_LIMIT]
    for entry, topic_url, category_id, title in enrichment:
      try:
        topic_json_url = urljoin(COMMUNITY_URL, topic_url.rstrip('/') + '.json')
        topic = self.json_object(fetch_url(topic_json_url), f'BookBrowse About topic {category_id}')
        event_date = self.topic_date(topic)
        if event_date:
          entry.update({
            'event_date': event_date,
            'discussion_year': event_date[:4],
            'selection_year': event_date[:4],
            'selection_month': str(int(event_date[5:7])),
          })
      except Exception as err:
        notes.append(f'BookBrowse discussion date was unavailable for {title}: {err}')
    if progress is not None:
      progress(total, total, f'Fetched {total} BookBrowse discussions')
    if not entries:
      raise ValueError('BookBrowse Discourse source exposed no official discussions.')
    return entries, notes

  def current_identity(self, category):
    name = normalize_line(category.get('name') or '')
    description = normalize_line(category.get('description_text') or '')
    if name.casefold().startswith(('side read', 'community book club')):
      return '', []
    match = DISCUSSION_DESCRIPTION.search(description)
    if not match:
      return '', []
    return self.clean_title(match.group(1)), self.authors_from_credit(match.group(2))

  def topic_date(self, topic):
    posts = topic.get('post_stream', {}).get('posts', [])
    if not posts:
      return ''
    created = posts[0].get('created_at') or ''
    try:
      return datetime.fromisoformat(created.replace('Z', '+00:00')).date().isoformat()
    except Exception:
      return ''

  def parse_upcoming(self, html, base_url, fetch_url, name, today, progress=None):
    root = lxml_html.fromstring(html or '<html></html>')
    headings = root.xpath('//h3[normalize-space()="Discussions Coming Soon"]')
    if not headings:
      return [], ['BookBrowse did not list any upcoming discussions.']
    lists = headings[0].xpath('following-sibling::ul[1]')
    cards = lists[0].xpath('./li') if lists else []
    entries = []
    notes = []
    for index, card in enumerate(cards, 1):
      links = card.xpath('.//a[@href][1]')
      if not links:
        continue
      detail_url = quote(
        urljoin(base_url, links[0].get('href')),
        safe=':/?&=%#')
      label = self.node_text(card)
      date_match = OPENS_DATE.search(label)
      if not date_match:
        notes.append(f'BookBrowse upcoming discussion had no opening date: {detail_url}')
        continue
      day = int(date_match.group(1))
      month = MONTHS[date_match.group(2).casefold()]
      year = today.year
      candidate = date(year, month, day)
      if candidate < today:
        year += 1
        candidate = date(year, month, day)
      try:
        if progress is not None:
          progress(index - 1, len(cards), f'Fetching BookBrowse upcoming book {index} of {len(cards)}')
        detail = fetch_url(detail_url)
        self.require_real_page(detail, 'BookBrowse upcoming book detail')
        title, authors = self.detail_identity(detail)
        if not title or not authors:
          raise ValueError('book detail did not expose title and author')
      except Exception as err:
        notes.append(f'BookBrowse upcoming discussion was unavailable: {detail_url}: {err}')
        continue
      record_id = self.detail_record_id(detail_url)
      entries.append(imported_entry(
        '', title, authors,
        source=entry_source_object(detail_url, name, record_id),
        club_name=name,
        category=CATEGORY,
        selection_type='discussion_selection',
        program_era='upcoming_landing',
        event_date=candidate.isoformat(),
        discussion_year=str(year),
        selection_year=str(year),
        selection_month=str(month),
        source_record_id=f'bookbrowse-upcoming:{record_id}',
        _source_order=index,
        _era_rank=2,
      ))
    return entries, notes

  def detail_identity(self, html):
    root = lxml_html.fromstring(html or '<html></html>')
    title = ''
    for heading in root.xpath('//h1|//h2'):
      text = self.node_text(heading)
      if text and not re.search(r'book summary|reviews|discussion|online book club', text, re.I):
        title = self.clean_title(text)
        break
    credit = ''
    for node in root.xpath('//h1|//h2|//h3|//p|//div'):
      text = self.node_text(node)
      match = re.match(r'^by\s+(.+?)\s*$', text, re.I)
      if match:
        credit = match.group(1)
        break
    return title, self.authors_from_credit(credit)

  def detail_record_id(self, url):
    match = re.search(r'/ezine_preview_number/(\d+)', url, re.I)
    return match.group(1) if match else urlparse(url).path.rstrip('/').split('/')[-1]

  def authors_from_credit(self, credit):
    credit = self.clean_author(credit)
    if not credit:
      return []
    parts = re.split(r'\s+(?:and|&)\s+|\s*;\s*', credit, flags=re.I)
    return [part.strip(' ,') for part in parts if part.strip(' ,')]

  def merge_entries(self, entries):
    selected = []
    for entry in entries:
      duplicate_index = next((
        index for index, prior in enumerate(selected)
        if self.merge_match(prior, entry)), None)
      if duplicate_index is None:
        selected.append(entry)
      elif entry.get('_era_rank', 0) > selected[duplicate_index].get('_era_rank', 0):
        selected[duplicate_index] = entry
    return sorted(selected, key=self.entry_sort_key)

  def merge_match(self, left, right):
    left_identity = (self.identity_key(left.get('title')), tuple(
      self.identity_key(author) for author in left.get('authors', ())))
    right_identity = (self.identity_key(right.get('title')), tuple(
      self.identity_key(author) for author in right.get('authors', ())))
    if left_identity != right_identity:
      return False
    left_era = left.get('program_era') or ''
    right_era = right.get('program_era') or ''
    if left_era == right_era:
      return False
    if {left_era, right_era} == {'upcoming_landing', 'discourse_community'}:
      return True
    left_year = left.get('discussion_year') or ''
    right_year = right.get('discussion_year') or ''
    return bool(left_year and left_year == right_year)

  def entry_sort_key(self, entry):
    year = int(entry.get('discussion_year') or 9999)
    event_date = entry.get('event_date') or f'{year:04d}-00-00'
    return (year, event_date, entry.get('_source_order', 0), entry.get('title', '').casefold())

  def identity_key(self, value):
    return re.sub(r'[^a-z0-9]+', '', normalize_line(value).casefold())

  def json_object(self, payload, label):
    if isinstance(payload, dict):
      return payload
    self.require_real_page(payload, label)
    try:
      data = json.loads(payload or '')
    except Exception as err:
      raise ValueError(f'{label} did not return valid JSON: {err}')
    if not isinstance(data, dict):
      raise ValueError(f'{label} did not return a JSON object.')
    return data

  def require_real_page(self, payload, label):
    text = str(payload or '')
    key = text[:10000].casefold()
    if not text.strip() or any(marker in key for marker in CHALLENGE_MARKERS):
      raise ValueError(f'{label} returned a challenge or empty response.')
