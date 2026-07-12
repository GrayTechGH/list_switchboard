#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""Parser for the r/bookclub Previous Selections wiki.

Maintenance notes:
- Reddit may return wiki JSON, a Markdown source view, rendered HTML, or a
  verification page for the same URL. The parser accepts the useful forms and
  rejects interstitials before looking for selection rows.
- The wiki is newest-first. Positions are assigned oldest-first by reversing
  sections while preserving the source order of rows inside each section.
- A plus sign splits selections only when it separates distinct linked titles.
  Plus signs inside one linked title or a parenthetical remain part of that
  title.
"""

import json
import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag

try:
  from calibre_plugins.list_switchboard.parser.base import (
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    entry_source_object,
    imported_entry,
    ListParserBase,
    parsed_source,
  )
except ImportError:
  from .base import (
    CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,
    entry_source_object,
    imported_entry,
    ListParserBase,
    parsed_source,
  )


BLOCKED_MARKERS = (
  'Please wait for verification',
  'blocked by network security',
  'You have been blocked',
  'whoa there, pardner',
)
MONTHS = {
  'january': '1',
  'february': '2',
  'march': '3',
  'april': '4',
  'may': '5',
  'june': '6',
  'july': '7',
  'august': '8',
  'september': '9',
  'october': '10',
  'november': '11',
  'december': '12',
  'jan': '1',
  'feb': '2',
  'mar': '3',
  'apr': '4',
  'jun': '6',
  'jul': '7',
  'aug': '8',
  'sep': '9',
  'sept': '9',
  'oct': '10',
  'nov': '11',
  'dec': '12',
}
MONTH_PATTERN = '|'.join(MONTHS)
MARKDOWN_LINK_RE = re.compile(
  r'\[([^\]]+)\]\(([^()]*(?:\([^()]*\)[^()]*)*)\)')
REDDIT_POST_RE = re.compile(r'/comments/([^/]+)/', re.I)
HISTORICAL_CORRECTIONS_FILE = 'r_bookclub_corrections.json'


def normalize_text(value):
  value = str(value or '').replace('\xa0', ' ')
  value = re.sub(r'[\t\r\f\v ]+', ' ', value)
  return value.strip()


def markdown_text(value):
  value = MARKDOWN_LINK_RE.sub(lambda match: match.group(1), value or '')
  value = re.sub(r'[*_~`]+', '', value)
  return normalize_text(value)


def heading_context(value):
  text = markdown_text(value).strip('# ').strip()
  year_match = re.fullmatch(r'((?:19|20)\d{2})', text)
  if year_match:
    return {'kind': 'year', 'year': year_match.group(1), 'label': text}
  month_match = re.search(
    rf'\b({MONTH_PATTERN})\b(?:\s*[-/]\s*({MONTH_PATTERN})\b)?'
    r'(?:\s+((?:19|20)\d{2}))?', text, re.I)
  explicit_years = re.findall(r'\b((?:19|20)\d{2})\b', text)
  year = explicit_years[0] if explicit_years else ''
  return {
    'kind': 'section',
    'year': year,
    'year_end': explicit_years[1] if len(explicit_years) > 1 else '',
    'month': MONTHS.get(month_match.group(1).casefold(), '') if month_match else '',
    'month_end': (
      MONTHS.get(month_match.group(2).casefold(), '')
      if month_match and month_match.group(2) else ''),
    'label': text,
  }


def slug(value):
  return re.sub(r'[^a-z0-9]+', '-', (value or '').casefold()).strip('-')


def reddit_post_id(url):
  match = REDDIT_POST_RE.search(url or '')
  return match.group(1) if match else ''


def clean_title(value):
  value = markdown_text(value).strip(' \"\'\u2018\u2019\u201c\u201d,.;')
  while value.endswith(')') and value.count(')') > value.count('('):
    value = value[:-1].rstrip()
  return value


def clean_credit(value):
  value = markdown_text(value)
  value = value.replace('\\', '')
  # These are navigation/resource labels attached to the selection, not credits.
  value = re.split(
    r'\s+(?:\+\s*)?(?:posts?|marginalia|gutenberg(?:\s+link)?|'
    r'parallel\s*text|librivox|audiobook)(?:\b|\s*\[)',
    value, maxsplit=1, flags=re.I)[0]
  value = re.sub(r'\s+-\s+(?:two\s+)?posts?\b.*$', '', value, flags=re.I)
  value = re.sub(
    r'\s*\((?:continued|undiscussed|gutenberg(?:\s+link)?|'
    r'converted\s+to\s+a\s+big\s+read|big\s+read\s+through\b[^)]*)\)\s*$',
    '', value, flags=re.I)
  preserve_suffix_period = bool(re.search(r'\b(?:Jr|Sr)\.\s*$', value, re.I))
  value = value.strip(' \"\'\u2018\u2019\u201c\u201d,.;')
  return value + '.' if preserve_suffix_period else value


def split_authors(value):
  credit = clean_credit(value)
  incomplete = bool(re.search(r'\bet\s+al\.?\b', credit, re.I))
  credit = re.sub(r'(?:,?\s*)\bet\s+al\.?,?', '', credit, flags=re.I).strip(' ,;')
  parts = re.split(
    r'(?:,\s*)?\s+(?:and|with|&)\s+|\s*;\s*', credit, flags=re.I)
  if incomplete and len(parts) == 1 and ',' in credit:
    parts = re.split(r'\s*,\s*', credit)
  authors = []
  for part in parts:
    part = normalize_text(part).strip(' ,;')
    if part and part not in authors:
      authors.append(part)
  return authors, incomplete


def paragraph_blocks(markdown):
  blocks = []
  paragraph = []
  for raw_line in str(markdown or '').splitlines():
    line = raw_line.strip()
    if line.startswith('#'):
      if paragraph:
        blocks.append(('row', ' '.join(paragraph)))
        paragraph = []
      blocks.append(('heading', line))
    elif not line:
      if paragraph:
        blocks.append(('row', ' '.join(paragraph)))
        paragraph = []
    else:
      paragraph.append(line)
  if paragraph:
    blocks.append(('row', ' '.join(paragraph)))
  return blocks


def html_row_markdown(node, base_url):
  """Serialize emphasized HTML titles as Markdown while retaining nearby text."""
  chunks = []

  def append(item):
    if isinstance(item, NavigableString):
      chunks.append(str(item))
      return
    if not isinstance(item, Tag):
      return
    if item.name in ('em', 'i'):
      parent = item.parent if getattr(item.parent, 'name', '') == 'a' else None
      href = urljoin(base_url, parent.get('href', '')) if parent else ''
      title = normalize_text(item.get_text(' ', strip=True))
      chunks.append(f'[*{title}*]({href})' if href else f'*{title}*')
      return
    for child in item.children:
      append(child)

  append(node)
  return normalize_text(''.join(chunks))


class RBookclubParser(ListParserBase):
  """Parse the full r/bookclub Previous Selections chronology."""

  FILTER_CATEGORIES = (CATEGORY_ONLINE_COMMUNITY_BOOK_CLUBS,)
  CLUB_NAME = 'r/bookclub'
  SOURCE_ID = 'r_bookclub_previous_selections'

  def parse(self, payload, base_url, name=None):
    payload = payload or ''
    self.reject_interstitial(payload)
    markdown = self.markdown_from_payload(payload)
    if markdown:
      blocks = paragraph_blocks(markdown)
    else:
      blocks = self.blocks_from_html(self.html_from_payload(payload), base_url)
    entries, notes = self.entries_from_blocks(blocks, base_url)
    if not entries:
      raise ValueError('Could not find r/bookclub selection rows in the fetched wiki page.')
    list_name = name or 'r/bookclub Previous Selections'
    return {
      'name': list_name,
      'source': parsed_source(list_name, base_url, self.SOURCE_ID),
      'entries': entries,
      'notes': notes,
      'match_series': False,
    }

  def reject_interstitial(self, payload):
    text = BeautifulSoup(str(payload), 'html.parser').get_text(' ', strip=True)
    for marker in BLOCKED_MARKERS:
      if marker.casefold() in text.casefold():
        raise ValueError(
          'Reddit returned a verification or blocking page instead of the '
          'r/bookclub Previous Selections wiki.')

  def markdown_from_payload(self, payload):
    stripped = str(payload).lstrip()
    if stripped.startswith('{'):
      try:
        data = json.loads(stripped)
      except (TypeError, ValueError):
        data = None
      if isinstance(data, dict):
        wiki_data = data.get('data') or {}
        if isinstance(wiki_data, dict):
          content = wiki_data.get('content_md')
          if content:
            return content
          if wiki_data.get('content_html'):
            return ''
    soup = BeautifulSoup(str(payload), 'html.parser')
    for node in soup.find_all(['textarea', 'pre', 'code']):
      text = node.get_text('\n', strip=False)
      if '# Previous Selections' in text:
        return text
    if stripped.startswith('# Previous Selections'):
      return str(payload)
    return ''

  def html_from_payload(self, payload):
    stripped = str(payload).lstrip()
    if not stripped.startswith('{'):
      return payload
    try:
      data = json.loads(stripped)
    except (TypeError, ValueError):
      return payload
    wiki_data = data.get('data') if isinstance(data, dict) else None
    if isinstance(wiki_data, dict) and wiki_data.get('content_html'):
      return wiki_data['content_html']
    return payload

  def blocks_from_html(self, payload, base_url):
    soup = BeautifulSoup(str(payload), 'html.parser')
    blocks = []
    started = False
    for node in soup.find_all(['h1', 'h2', 'h3', 'p', 'li']):
      text = normalize_text(node.get_text(' ', strip=True))
      if not text:
        continue
      boundary = node.find(['h1', 'h2', 'h3']) if node.name == 'li' else None
      if started and boundary and normalize_text(
          boundary.get_text(' ', strip=True)).casefold() in ('page title', 'page sections'):
        break
      if node.name in ('h1', 'h2', 'h3'):
        if text.casefold() == 'previous selections':
          started = True
          blocks.append(('heading', '# Previous Selections'))
          continue
        if not started:
          continue
        if text.casefold() in ('page title', 'page sections'):
          break
        blocks.append(('heading', '# ' + text))
      elif started:
        blocks.append(('row', html_row_markdown(node, base_url)))
    return blocks

  def entries_from_blocks(self, blocks, base_url):
    sections = []
    notes = []
    current_year = ''
    current_section = None
    for kind, value in blocks:
      if kind == 'heading':
        context = heading_context(value)
        if context['kind'] == 'year':
          current_year = context['year']
          continue
        if context['label'].casefold() == 'previous selections':
          continue
        context['year'] = context.get('year') or current_year
        current_year = context['year'] or current_year
        context['rows'] = []
        sections.append(context)
        current_section = context
        continue
      text = markdown_text(value)
      if not current_section or not text:
        continue
      if self.is_intentional_empty_row(text):
        continue
      current_section['rows'].append(value)

    entries = []
    for section in reversed(sections):
      for row_index, row in enumerate(section['rows'], 1):
        parsed_rows = self.parse_row(row, section, row_index, base_url)
        if not parsed_rows:
          notes.append(self.section_note(section, f'Unparsed selection row: {markdown_text(row)}'))
          continue
        entries.extend(parsed_rows)
    for index, entry in enumerate(entries, 1):
      entry['position'] = str(index)
    return entries, notes

  def is_intentional_empty_row(self, row):
    text = normalize_text(row).casefold().strip(' .')
    return text == 'inactive' or bool(re.fullmatch(r'short\s+story\s*:\s*none', text))

  def section_note(self, section, message):
    context = ' '.join(filter(None, (section.get('label'), section.get('year'))))
    return f'{context}: {message}' if context else message

  def parse_row(self, row, section, row_index, base_url):
    raw = normalize_text(row)
    label, body = self.split_label(raw, section)
    components = self.linked_components(body, base_url)
    if not components:
      component = self.plain_component(body)
      components = [component] if component else []
    if not components:
      correction = self.historical_correction(raw, section)
      if correction:
        label = correction.get('label') or label
        components = [correction['component']]
    if not components:
      return []

    group_id = ''
    if len(components) > 1:
      post_id = next((reddit_post_id(item.get('url')) for item in components if item.get('url')), '')
      group_id = (
        f'rbc:{post_id}' if post_id else
        'rbc:%s:%s:%s:%s' % (
          section.get('year') or 'unknown',
          section.get('month') or slug(section.get('label')) or 'unknown',
          slug(label) or 'selection', row_index))

    entries = []
    for component_index, component in enumerate(components, 1):
      authors, incomplete = split_authors(component.get('credit'))
      title = clean_title(component.get('title'))
      if not title or not authors:
        return []
      post_id = reddit_post_id(component.get('url'))
      source_url = component.get('url') if post_id else ''
      list_source = parsed_source(
        'r/bookclub Previous Selections', base_url, self.SOURCE_ID)
      metadata = {
        'club_name': self.CLUB_NAME,
        'selection_year': section.get('year') or None,
        'selection_year_end': section.get('year_end') or None,
        'selection_month': section.get('month') or None,
        'selection_month_end': section.get('month_end') or None,
        'selection_type': (
          'global_read' if label.casefold().startswith('read the world')
          else 'discussion_selection'),
        'theme_or_track': label,
        'raw_selection_label': label,
        'raw_author_credit': clean_credit(component.get('credit')),
        'credit_role': component.get('role') or 'author',
        'authors_incomplete': True if incomplete else None,
        'event_group_id': group_id or None,
        'source_record_id': (
          f'reddit:{post_id}:{component_index}'
          if post_id and len(components) > 1 else
          f'reddit:{post_id}' if post_id else None),
        'selection_url': source_url or None,
        'linked_book_url': component.get('url') if component.get('url') and not post_id else None,
        'component_label': component.get('component_label') or None,
        'undiscussed': True if re.search(r'\bundiscussed\b', raw, re.I) else None,
        'continued': True if re.search(r'\bcontinued\b', raw, re.I) else None,
      }
      entries.append(imported_entry(
        '', title, authors,
        source=entry_source_object(
          source_url, self.CLUB_NAME, self.SOURCE_ID, list_source=list_source),
        **metadata))
    return entries

  def historical_correction(self, row, section):
    """Recover three source rows whose historical wiki records omit credits."""
    text = markdown_text(row).replace('\\', '').casefold()
    for correction in load_historical_corrections():
      if any(str(correction.get(field) or '') != str(section.get(field) or '')
             for field in ('year', 'month', 'month_end')):
        continue
      if normalize_text(correction.get('raw_text')).casefold() != text:
        continue
      return {
        'label': correction.get('label') or '',
        'component': {
          'title': correction.get('title') or '',
          'credit': correction.get('author') or '',
          'role': correction.get('role') or 'author',
          'url': '',
        },
      }
    return None

  def split_label(self, row, section):
    first_link = row.find('[')
    colon = row.find(':')
    if colon >= 0 and (first_link < 0 or colon < first_link):
      return markdown_text(row[:colon]), row[colon + 1:].strip()
    return section.get('label') or 'Selection', row

  def linked_components(self, body, base_url):
    links = list(MARKDOWN_LINK_RE.finditer(body))
    title_links = []
    for match in links:
      tail = body[match.end():]
      role_match = re.match(r'\s+(translated\s+by|by)\s+', tail, re.I)
      if role_match:
        title_links.append((match, role_match))
    if not title_links:
      emphasized = [
        match for match in links
        if re.search(r'[*_]', match.group(1))
      ]
      if len(emphasized) == 1:
        match = emphasized[0]
        tail = markdown_text(body[match.end():]).strip(' ,.;')
        if tail and not tail.casefold().startswith(('post', 'schedule')):
          return [{
            'title': match.group(1),
            'credit': tail,
            'role': 'author',
            'url': urljoin(base_url, match.group(2)),
          }]
      return []

    components = []
    previous_end = 0
    for index, (match, role_match) in enumerate(title_links):
      credit_start = match.end() + role_match.end()
      next_start = title_links[index + 1][0].start() if index + 1 < len(title_links) else len(body)
      credit = body[credit_start:next_start]
      connector = ''
      if index + 1 < len(title_links):
        connector_match = re.search(
          r'\s+\+\s+(?:(Bonus\s+Pre-Read)\s*)?$', credit, re.I)
        if connector_match:
          connector = connector_match.group(1) or ''
          credit = credit[:connector_match.start()]
      prefix = markdown_text(body[previous_end:match.start()])
      component_label = connector or prefix.strip(' +:') if index else ''
      components.append({
        'title': match.group(1),
        'credit': credit,
        'role': 'translator' if role_match.group(1).casefold().startswith('translated') else 'author',
        'url': urljoin(base_url, match.group(2)),
        'component_label': component_label,
      })
      previous_end = credit_start + len(credit)
    return components

  def plain_component(self, body):
    text = markdown_text(body)
    match = re.match(r'^(.+?)\s+(translated\s+by|by)\s+(.+)$', text, re.I)
    if match:
      return {
        'title': match.group(1),
        'credit': match.group(3),
        'role': 'translator' if match.group(2).casefold().startswith('translated') else 'author',
        'url': '',
      }
    match = re.match(r'^(.+?),\s*([^,]+?)(?:\s+posts?)?$', text, re.I)
    if match:
      return {
        'title': match.group(1),
        'credit': match.group(2),
        'role': 'author',
        'url': '',
      }
    return None


def parse_r_bookclub(payload, base_url, name=None):
  return RBookclubParser().parse(payload, base_url, name=name)


def load_historical_corrections():
  try:
    from importlib import resources
    package = 'calibre_plugins.list_switchboard.parser.data'
    text = resources.files(package).joinpath(
      HISTORICAL_CORRECTIONS_FILE).read_text(encoding='utf-8')
  except Exception:
    path = Path(__file__).with_name('data') / HISTORICAL_CORRECTIONS_FILE
    text = path.read_text(encoding='utf-8')
  return tuple(json.loads(text).get('rows') or ())
