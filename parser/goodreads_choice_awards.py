#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=2:sw=2:sta:et:sts=2:ai

"""
Goodreads Choice Awards parser.

Maintenance notes:
- Goodreads is the runtime source for this recipe family. The yearly overview
  pages discover category result pages, and category pages expose winners plus
  an "All Nominees" card stream.
- The modern `best-books-YYYY` overview URL pattern starts with 2011; the 2009
  and 2010 overview pages are not available at that path and are not fetched.
  Categories found only in those unavailable legacy years must not be
  registered as live imports without a nominee-complete Goodreads source.
- Wikipedia is useful as category-history reference only; it is winner-focused
  and should not be wired as a replacement fallback for nominee-complete imports.
- Visible import labels may mark discontinued categories, but parsed award
  metadata stores the source category name without that label suffix.
- Goodreads book links are identity metadata for deduplication and narrow title
  corrections, not award provenance. Emitted entries cite the category-year
  Choice Awards page that establishes their result and position.
- Historical contributor repairs are book-ID/title guarded. Runtime detail
  enrichment is limited to the newest advertised award year and stops after
  the first access challenge without discarding ballot rows.
"""

from datetime import date
import json
from pathlib import Path
import re
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup

try:
  from calibre_plugins.list_switchboard.parser.award_base import ( # type: ignore
    AwardParserBase, RESULT_NOMINEE, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, split_title_author_byline,
    strip_publication_notes,
  )
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key # pyright: ignore[reportMissingImports]
except ImportError:
  from .award_base import (
    AwardParserBase, RESULT_NOMINEE, RESULT_WINNER, assign_positions,
    normalize_heading, normalize_line, split_title_author_byline,
    strip_publication_notes,
  )
  from .generic import position_sort_key


AWARD_NAME = 'Goodreads Choice Awards'
FIRST_OVERVIEW_YEAR = 2011
CHOICE_AWARDS_URL = 'https://www.goodreads.com/choiceawards'
OVERVIEW_URL_TEMPLATE = 'https://www.goodreads.com/choiceawards/best-books-{year}'
CONTRIBUTOR_CORRECTIONS_FILE = 'goodreads_choice_contributors.json'
DETAIL_REQUEST_DELAY_SECONDS = 1.5
DETAIL_REQUEST_LIMIT = 25
DETAIL_ENRICH_LATEST_YEARS = 1
MIN_CATEGORY_ROWS = 10
MAX_CATEGORY_ROWS = 25

# Add only source-verified exceptions. Most final Goodreads ballots expose 20
# unique books, including the winner repeated in the nominee card stream.
GOODREADS_ROW_COUNT_EXCEPTIONS = {}

# These Choice cards expose shortened titles, while their stable Goodreads book
# records retain the distinguishing subtitle. Apply only while the short source
# title and book ID both still match so a repaired source takes precedence.
GOODREADS_TITLE_CORRECTIONS = {
  '25111004': ('Star Wars', 'Star Wars: Aftermath'),
  '36385830': ('Thrawn', 'Thrawn: Alliances'),
  '43160651': ('Thrawn', 'Thrawn: Treason'),
}


def load_goodreads_contributor_corrections():
  """Load narrow, reviewed contributor repairs packaged with the parser."""
  try:
    from importlib import resources
    package = 'calibre_plugins.list_switchboard.parser.data'
    text = resources.files(package).joinpath(
      CONTRIBUTOR_CORRECTIONS_FILE).read_text(encoding='utf-8')
  except Exception:
    path = Path(__file__).with_name('data') / CONTRIBUTOR_CORRECTIONS_FILE
    text = path.read_text(encoding='utf-8')
  rows = json.loads(text).get('corrections') or ()
  return {
    str(row.get('book_id') or ''): row
    for row in rows
    if str(row.get('book_id') or '')
  }


def goodreads_choice_overview_url(year):
  return OVERVIEW_URL_TEMPLATE.format(year=int(year))


def goodreads_choice_candidate_years(today=None):
  today = today or date.today()
  return range(FIRST_OVERVIEW_YEAR, today.year + 1)


def category_key(value):
  key = normalize_heading(value)
  key = key.replace('sci fi', 'science fiction')
  key = key.replace('scifi', 'science fiction')
  key = key.replace('non fiction', 'nonfiction')
  key = key.replace('childrens', 'children s')
  key = key.replace('graphic novel and comics', 'graphic novels and comics')
  key = key.replace('memoir and autobiography', 'memoir')
  key = key.replace('memoir autobiography', 'memoir')
  return re.sub(r'\s+', ' ', key).strip()


def clean_category_text(value):
  value = normalize_line(value)
  value = re.sub(r'\s*[✓✔]\s*', ' ', value)
  value = re.sub(r'\s*(?:view results?|results?)\s*[→>-]*\s*$', '', value, flags=re.I)
  value = re.sub(r'^\s*readers[’\']?\s+favorite\s+', '', value, flags=re.I)
  # "Best" is normally presentation text (for example, "Best Fiction"), but
  # it is part of the literal one-off category name "Best of the Best".
  if not re.match(r'^\s*best\s+of\s+the\s+best\b', value, flags=re.I):
    value = re.sub(r'^\s*best\s+', '', value, flags=re.I)
  value = re.sub(r'\s+books?\s*$', '', value, flags=re.I)
  return normalize_line(value).strip(' "\'\u2018\u2019\u201c\u201d,:')


def year_from_text(value):
  match = re.search(r'(?:19|20)\d{2}', value or '')
  return int(match.group(0)) if match is not None else None


class GoodreadsChoiceAwardsParser(AwardParserBase):

  AWARD_NAME = AWARD_NAME

  def __init__(self, category, category_aliases=()):
    self.category = category
    self.category_aliases = tuple(category_aliases or (category,))
    self.category_keys = {
      category_key(alias)
      for alias in self.category_aliases
    }
    self.contributor_corrections = load_goodreads_contributor_corrections()

  def parse(
      self, html, base_url=CHOICE_AWARDS_URL, name=AWARD_NAME,
      fetch_url=None, log=None, progress=None, overview_pages=None,
      category_pages=None, sleep=None, validate_pages=None,
      enrich_contributors=None):
    notes = []
    rows = []
    if validate_pages is None:
      validate_pages = category_pages is None
    if enrich_contributors is None:
      enrich_contributors = overview_pages is None and category_pages is None
    latest_published_year = None
    if category_pages is not None:
      rows.extend(self.parse_category_pages(
        category_pages, notes=notes, validate=validate_pages))
    else:
      pages = (
        tuple(overview_pages)
        if overview_pages is not None
        else self.overview_pages(html, base_url, fetch_url, notes, progress))
      published_years = [
        year_from_text(page_url)
        for page_url, _page_html in pages
        if year_from_text(page_url) is not None
      ]
      published_years.extend(self.advertised_overview_years(html, base_url))
      if published_years:
        latest_published_year = max(published_years)
      rows.extend(self.fetch_category_rows(pages, fetch_url, notes, log, progress))
    rows = self.dedupe_rows(rows)
    corrected_book_ids = self.apply_contributor_corrections(rows)
    if fetch_url is not None and enrich_contributors:
      self.enrich_latest_contributors(
        rows,
        fetch_url,
        notes,
        sleep=sleep,
        progress=progress,
        corrected_book_ids=corrected_book_ids,
        latest_published_year=latest_published_year)
    entries = self.entries_from_rows(rows)
    if not entries:
      notes.append(f'No Goodreads Choice Awards rows were parsed for {self.category}.')
    return self.parsed_result(
      name,
      base_url,
      sorted(entries, key=lambda item: position_sort_key(item.get('position', ''))),
      notes=notes)

  def overview_pages(self, html, base_url, fetch_url, notes, progress):
    if fetch_url is None:
      return ((base_url, html),)
    pages = [(base_url, html)] if html else []
    advertised_years = self.advertised_overview_years(html, base_url)
    current_year = date.today().year
    years = tuple(
      year for year in goodreads_choice_candidate_years()
      if year != current_year or year in advertised_years
    )
    total = len(years)
    for index, year in enumerate(years, 1):
      url = goodreads_choice_overview_url(year)
      try:
        if progress is not None:
          progress(index, total, f'Fetching Goodreads Choice Awards {year}')
        page_html = html if self.same_url(url, base_url) else fetch_url(url)
        pages.append((url, page_html))
      except Exception as err:
        notes.append(f'Goodreads Choice Awards overview could not be fetched: {url}: {err}')
    return tuple(pages)

  def advertised_overview_years(self, html, base_url=CHOICE_AWARDS_URL):
    soup = BeautifulSoup(html or '', 'html.parser')
    years = set()
    for link in soup.find_all('a', href=True):
      href = urljoin(base_url, link.get('href') or '')
      if '/choiceawards/best-books-' not in href:
        continue
      year = year_from_text(href)
      if year is not None:
        years.add(year)
    return years

  def same_url(self, left, right):
    return (left or '').rstrip('/') == (right or '').rstrip('/')

  def fetch_category_rows(self, overview_pages, fetch_url, notes, log, progress):
    rows = []
    links = []
    for page_url, page_html in overview_pages:
      links.extend(self.discover_category_links(page_html, page_url))
    total = len(links)
    for index, link in enumerate(links, 1):
      try:
        if fetch_url is None:
          continue
        if progress is not None:
          progress(index, total, f'Fetching {self.category} result page {index} of {total}')
        page_html = fetch_url(link['url'])
        rows.extend(self.parse_category_page(
          page_html,
          link['url'],
          fallback_year=link['year'],
          fallback_category=link['category'],
          notes=notes,
          validate=True))
      except Exception as err:
        notes.append(
          f'Goodreads Choice Awards category page could not be fetched: '
          f'{link["url"]}: {err}')
        if log is not None:
          log(f'Goodreads Choice Awards category page failed: {link["url"]}: {err}')
    return rows

  def discover_category_links(self, html, base_url):
    soup = BeautifulSoup(html or '', 'html.parser')
    fallback_year = year_from_text(base_url) or year_from_text(soup.get_text(' ', strip=True))
    links = []
    seen = set()
    for link in soup.find_all('a', href=True):
      href = urljoin(base_url, link['href'])
      if '/choiceawards/' not in href:
        continue
      link_year = year_from_text(href) or fallback_year
      if link_year is None:
        continue
      text = clean_category_text(link.get_text(' ', strip=True))
      if not text or self.skip_overview_link(text, href):
        continue
      if not self.category_matches(text):
        continue
      key = (link_year, href)
      if key in seen:
        continue
      seen.add(key)
      links.append({
        'year': link_year,
        'category': text,
        'url': href,
      })
    return tuple(sorted(links, key=lambda item: (item['year'], item['url'])))

  def skip_overview_link(self, text, href):
    key = normalize_heading(text)
    href_key = normalize_heading(href)
    if re.fullmatch(r'(?:19|20)\d{2} awards?', key):
      return True
    if key in {'view results', 'rules and eligibility', 'learn more'}:
      return True
    return 'best books' in href_key and not self.category_matches(text)

  def category_matches(self, value):
    return category_key(value) in self.category_keys

  def parse_category_pages(self, pages, notes=None, validate=False):
    rows = []
    notes = notes if notes is not None else []
    if isinstance(pages, dict):
      pages = pages.items()
    for page_url, page_html in pages:
      rows.extend(self.parse_category_page(
        page_html, page_url, notes=notes, validate=validate))
    return rows

  def parse_category_page(
      self, html, page_url, fallback_year=None, fallback_category=None,
      notes=None, validate=True):
    notes = notes if notes is not None else []
    soup = BeautifulSoup(html or '', 'html.parser')
    year = fallback_year or year_from_text(page_url) or year_from_text(self.clean_text(soup.find('title')))
    if year is None:
      if validate:
        self.reject_page(notes, page_url, 'the award year could not be identified')
      return []
    detected_category = self.detect_page_category(soup)
    if validate and not detected_category:
      self.reject_page(
        notes,
        page_url,
        f'the page heading did not match {self.category}')
      return []
    page_category = detected_category or fallback_category or self.category
    nodes = list(soup.descendants)
    winner_marker = self.first_marker_index(nodes, r'\bwinner\b')
    nominee_marker = self.first_marker_index(nodes, r'\ball nominees\b')
    if validate and (winner_marker is None or nominee_marker is None):
      self.reject_page(
        notes,
        page_url,
        'required WINNER and All Nominees markers were not both present')
      return []
    rows = self.book_rows_from_cards(soup, page_url, year, page_category)
    rows = self.dedupe_rows(rows)
    if not validate:
      return rows
    winners = [
      row for row in rows
      if row.get('result') == RESULT_WINNER
    ]
    if len(winners) != 1:
      self.reject_page(
        notes,
        page_url,
        f'expected exactly one explicit winner but parsed {len(winners)}')
      return []
    minimum, maximum = self.expected_row_count_bounds(year)
    has_rules_boundary = self.first_marker_index(
      nodes, r'\brules?\s*(?:&|and)?\s*eligibility\b') is not None
    if (
        has_rules_boundary
        and (len(rows) < minimum or len(rows) > maximum)):
      self.reject_page(
        notes,
        page_url,
        f'parsed {len(rows)} unique books; expected {minimum}-{maximum}')
      return []
    return rows

  def reject_page(self, notes, page_url, reason):
    notes.append(
      f'Goodreads Choice Awards category page was rejected: '
      f'{page_url}: {reason}.')

  def expected_row_count_bounds(self, year):
    key = (category_key(self.category), int(year))
    return GOODREADS_ROW_COUNT_EXCEPTIONS.get(
      key, (MIN_CATEGORY_ROWS, MAX_CATEGORY_ROWS))

  def detect_page_category(self, soup):
    candidates = list(soup.select('.gcaMastheader'))
    candidates.extend(soup.find_all(['h1', 'h2', 'h3']))
    for node in candidates:
      text = clean_category_text(self.clean_text(node))
      if text and self.category_matches(text):
        return text
    raw_title = self.clean_text(soup.find('title'))
    raw_title = re.sub(
      r'\s+(?:19|20)\d{2}\s+[—-]\s+Goodreads Choice Awards.*$',
      '',
      raw_title,
      flags=re.I)
    title_text = clean_category_text(raw_title)
    return title_text if title_text and self.category_matches(title_text) else ''

  def book_rows_from_cards(self, soup, page_url, year, category):
    nodes = list(soup.descendants)
    nominee_marker = self.first_marker_index(nodes, r'\ball nominees\b')
    winner_marker = self.first_marker_index(nodes, r'\bwinner\b')
    end_marker = self.first_marker_index(
      nodes, r'\brules?\s*(?:&|and)?\s*eligibility\b')
    if end_marker is None:
      end_marker = len(nodes)
    start_markers = [
      marker for marker in (winner_marker, nominee_marker)
      if marker is not None
    ]
    start_marker = min(start_markers) if start_markers else None
    rows = []
    for image in soup.find_all(['img']):
      node_index = self.node_index(nodes, image)
      card = self.card_for_image(image)
      explicit_winner = self.card_has_winner_label(card)
      if (
          (start_marker is not None
           and node_index <= start_marker
           and not explicit_winner)
          or node_index >= end_marker):
        continue
      parsed = self.book_from_image(image, page_url)
      if parsed is None:
        continue
      votes = self.votes_near_node(image)
      if not votes:
        continue
      result = self.result_for_card(card, node_index, winner_marker, nominee_marker, rows)
      rows.append(self.row(
        year,
        parsed['title'],
        parsed['authors'],
        category,
        result,
        page_url,
        len(rows),
        votes=votes,
        book_url=parsed['book_url']))
    return rows

  def first_marker_index(self, nodes, pattern):
    for index, node in enumerate(nodes):
      if not isinstance(node, str):
        continue
      if re.search(pattern, normalize_line(node), re.I):
        return index
    return None

  def node_index(self, nodes, target):
    for index, node in enumerate(nodes):
      if node is target:
        return index
    return len(nodes)

  def result_for_card(self, card, node_index, winner_marker, nominee_marker, rows):
    if self.card_has_winner_label(card):
      return RESULT_WINNER
    return self.result_for_node_index(node_index, winner_marker, nominee_marker, rows)

  def card_has_winner_label(self, card):
    if card is None:
      return False
    for text_node in card.find_all(string=True):
      text = normalize_line(str(text_node))
      if re.match(r'^WINNER\b', text) or re.search(
          r'\bWINNER\s+\d[\d,]*(?:\s*&\s*\d{3})?\s+votes?\b',
          text):
        return True
    return False

  def result_for_node_index(self, node_index, winner_marker, nominee_marker, rows):
    # A bounded WINNER section is explicit source evidence. Missing markers
    # never promote the first parsed card.
    if (
        winner_marker is not None
        and nominee_marker is not None
        and winner_marker < node_index < nominee_marker):
      return RESULT_WINNER
    return RESULT_NOMINEE

  def book_from_image(self, image, page_url):
    alt_title, alt_author = self.title_author_from_alt(image.get('alt') or '')
    if not alt_title or not alt_author:
      return None
    card = self.card_for_image(image)
    title = self.clean_title(alt_title)
    authors = self.clean_authors(alt_author)
    book_url = self.link_for_node(image, page_url)
    explicit = self.explicit_title_author(card, page_url)
    if explicit is not None:
      explicit_title, explicit_authors, book_url = explicit
      title = self.preferred_title(title, explicit_title)
      if explicit_authors:
        authors = explicit_authors
    title = self.completed_title_from_book_url(title, book_url)
    title = self.corrected_title(title, book_url)
    if not title or not authors:
      return None
    return {
      'title': title,
      'authors': authors,
      'book_url': book_url,
    }

  def card_for_image(self, image):
    current = image
    for _level in range(5):
      if current is None:
        break
      text = self.clean_text(current)
      if re.search(r'\b\d[\d,]*\s+votes?\b', text, re.I):
        return current
      current = current.parent
    return image.parent or image

  def explicit_title_author(self, card, page_url):
    if card is None:
      return None
    title_link = None
    for link in card.find_all('a', href=True):
      href = link.get('href') or ''
      text = self.clean_text(link)
      if '/book/show/' in href and text and not self.link_text_noise(text):
        title_link = link
        break
    author_links = [
      link for link in card.find_all('a', href=True)
      if '/author/show/' in (link.get('href') or '') and self.clean_text(link)
    ]
    if title_link is None or not author_links:
      return None
    title = self.clean_text(title_link)
    authors = self.matchable_authors_from_links(author_links)
    if not authors:
      authors = self.clean_authors(
        self.clean_author_text_from_card(card, author_links))
    return (
      title,
      authors,
      urljoin(page_url, title_link.get('href') or ''))

  def matchable_authors_from_links(self, author_links):
    credits = [
      {
        'name': self.clean_text(link),
        'role': self.author_role_from_link(link),
      }
      for link in author_links
      if self.clean_text(link)
    ]
    return self.matchable_contributor_names(credits)

  def author_role_from_link(self, link):
    role_node = link.find(attrs={'data-testid': 'role'})
    if role_node is not None:
      return self.clean_role(self.clean_text(role_node))
    roles = []
    for index, sibling in enumerate(link.next_siblings):
      if index >= 6:
        break
      if getattr(sibling, 'name', None) == 'a':
        break
      text = (
        self.clean_text(sibling)
        if getattr(sibling, 'get_text', None) is not None
        else normalize_line(str(sibling)))
      classes = {
        str(value).casefold()
        for value in (getattr(sibling, 'get', lambda *_args: [])('class') or [])
      }
      if 'role' in classes:
        role = self.clean_role(text)
        if role:
          roles.append(role)
      for match in re.findall(r'\(([^)]+)\)', text):
        role = self.clean_role(match)
        if role and category_key(role) != category_key('Goodreads Author'):
          roles.append(role)
      if ',' in text:
        break
    return ', '.join(roles)

  def clean_role(self, value):
    value = normalize_line(value).strip()
    value = re.sub(r'^\s*\(|\)\s*$', '', value)
    return normalize_line(value)

  def matchable_contributor_names(self, credits):
    normalized = []
    first_editor_index = None
    for index, credit in enumerate(credits):
      name = normalize_line(credit.get('name') or '')
      role = self.clean_role(credit.get('role') or '')
      role_key = category_key(role)
      role_tokens = {
        token.strip()
        for token in re.split(r'\s*(?:,|&|/)\s*', role_key)
        if token.strip()
      }
      if 'editor' in role_tokens and first_editor_index is None:
        first_editor_index = index
      normalized.append((name, role_tokens))

    is_graphic = category_key(self.category) == category_key(
      'Graphic Novels & Comics')
    allowed = {'author', 'co author', 'editor'}
    if is_graphic:
      allowed.update({'writer', 'artist', 'illustrator', 'penciller'})
    excluded = {
      'adapter', 'adaptor', 'colorist', 'letterer', 'narrator',
      'translator',
    }
    names = []
    seen = set()
    for index, (name, role_tokens) in enumerate(normalized):
      if not name:
        continue
      if role_tokens:
        include = bool(role_tokens & allowed) and not bool(
          role_tokens & excluded)
      else:
        include = first_editor_index is None or index < first_editor_index
      key = normalize_heading(name)
      if include and key not in seen:
        seen.add(key)
        names.append(name)
    return names

  def clean_author_text_from_card(self, card, author_links):
    for container in self.author_text_containers(author_links):
      text = self.clean_text(container)
      if not self.safe_author_line(text):
        continue
      by_match = re.search(r'\bby\s+(.+)$', text, re.I)
      if by_match is not None:
        author = self.clean_author(by_match.group(1))
        if author:
          return author
    fallback_authors = []
    seen = set()
    for link in author_links:
      text = self.clean_text(link)
      key = normalize_heading(text)
      if text and key not in seen:
        seen.add(key)
        fallback_authors.append(text)
    return self.clean_author(', '.join(fallback_authors))

  def author_text_containers(self, author_links):
    seen = set()
    for link in author_links:
      current = link
      for _level in range(4):
        if current is None:
          break
        marker = id(current)
        if marker not in seen:
          seen.add(marker)
          yield current
        current = current.parent

  def safe_author_line(self, text):
    if not text or len(text) > 300:
      return False
    if not re.search(r'\bby\s+', text, re.I):
      return False
    key = normalize_heading(text)
    return not any(phrase in key for phrase in (
      'problem',
      'return to book page',
      'not the book you re looking for',
      'preview',
      'winner',
      'votes',
      'want to read',
      'more',
    ))

  def link_text_noise(self, value):
    key = normalize_heading(value)
    return key in {'open preview', 'preview', 'want to read', 'start now'}

  def title_author_from_alt(self, value):
    return split_title_author_byline(value)

  def preferred_title(self, alt_title, explicit_title):
    alt_title = self.clean_title(alt_title)
    explicit_title = self.clean_title(explicit_title)
    alt_key = normalize_heading(alt_title)
    explicit_key = normalize_heading(explicit_title)
    if alt_title and explicit_title and alt_key.startswith(explicit_key):
      return alt_title
    return explicit_title or alt_title

  def corrected_title(self, title, entry_url):
    book_id = self.goodreads_book_id(entry_url)
    correction = GOODREADS_TITLE_CORRECTIONS.get(book_id)
    if correction is None:
      return title
    source_title, corrected_title = correction
    if normalize_heading(title) == normalize_heading(source_title):
      return corrected_title
    return title

  def completed_title_from_book_url(self, title, entry_url):
    """Complete a visibly ellipsized ballot title from its own book-link slug."""
    ellipsis = re.search(r'\s*(?:\.\.\.|…)\s*$', title or '')
    if ellipsis is None:
      return title
    visible = normalize_line(title[:ellipsis.start()])
    path = unquote(urlparse(entry_url or '').path)
    slug_match = re.search(r'/book/show/\d+(?:[.-])([^/]+)', path, re.I)
    if not visible or slug_match is None:
      return title
    slug_words = [
      word
      for word in re.split(r'[-_]+', slug_match.group(1))
      if word
    ]
    visible_words = visible.split()
    if not slug_words or len(visible_words) > len(slug_words):
      return title
    for source_word, slug_word in zip(visible_words[:-1], slug_words):
      if normalize_heading(source_word) != normalize_heading(slug_word):
        return title
    source_tail = normalize_heading(visible_words[-1])
    slug_tail = normalize_heading(slug_words[len(visible_words) - 1])
    if not source_tail or not slug_tail.startswith(source_tail):
      return title

    completed = list(visible_words[:-1])
    if source_tail == slug_tail:
      completed.append(visible_words[-1])
    else:
      completed.append(self.slug_title_word(
        slug_words[len(visible_words) - 1],
        len(completed)))
    completed.extend(
      self.slug_title_word(word, index)
      for index, word in enumerate(
        slug_words[len(visible_words):],
        len(visible_words))
    )
    return normalize_line(' '.join(completed)) or title

  def slug_title_word(self, word, index):
    minor_words = {
      'a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'from', 'in',
      'nor', 'of', 'on', 'or', 'the', 'to', 'via', 'vs',
    }
    if index and word.casefold() in minor_words:
      return word.casefold()
    return word[:1].upper() + word[1:]

  def link_for_node(self, node, page_url):
    current = node
    while current is not None:
      if getattr(current, 'name', None) == 'a' and current.get('href'):
        return urljoin(page_url, current['href'])
      current = current.parent
    return page_url

  def votes_near_node(self, node):
    current = node
    for _level in range(5):
      if current is None:
        break
      match = re.search(r'\b(\d[\d,]*)\s+votes?\b', self.clean_text(current), re.I)
      if match is not None:
        return match.group(1).replace(',', '')
      current = current.parent
    return ''

  def clean_text(self, node):
    if node is None:
      return ''
    return normalize_line(node.get_text(' ', strip=True).replace('\xa0', ' '))

  def clean_title(self, value):
    value = normalize_line(value)
    value = re.sub(r'\s+\((?:[^)]*#[^)]+)\)\s*$', '', value)
    return strip_publication_notes(value).strip(' "\'\u2018\u2019\u201c\u201d,:')

  def clean_author(self, value):
    value = normalize_line(value)
    value = re.sub(r'^\s*by\s+', '', value, flags=re.I)
    parts = [
      part.strip()
      for part in re.split(r'\s*,\s*', value)
      if part.strip()
    ]
    author_parts = [
      part for part in parts
      if re.search(r'\(\s*author\s*\)', part, re.I)
    ]
    if not author_parts:
      author_parts = [
        part for part in parts
        if not re.search(r'\(\s*(?:narrator|translator|illustrator|editor)\s*\)', part, re.I)
      ]
    cleaned = []
    for part in author_parts:
      part = re.sub(r'\s*\(\s*(?:goodreads\s+author|author)\s*\)\s*', '', part, flags=re.I)
      part = re.sub(r'\s*\([^)]*\)\s*$', '', part).strip()
      if part:
        cleaned.append(part)
    if cleaned:
      return ' & '.join(cleaned)
    value = re.sub(r'\s*\([^)]*\)\s*', ' ', value)
    return strip_publication_notes(normalize_line(value)).strip(' "\'\u2018\u2019\u201c\u201d,:')

  def clean_authors(self, value):
    """Preserve Goodreads multi-author credits as schema author lists."""
    value = self.clean_author(value)
    return [
      author.strip()
      for author in re.split(r'\s+&\s+', value)
      if author.strip()
    ]

  def row(
      self, year, title, authors, category, result, source_url, source_order,
      votes='', book_url=''):
    row = {
      'award_year': str(year),
      'title': title,
      'authors': list(authors or []),
      'result': result,
      'source_url': source_url,
      'category': clean_category_text(category) or self.category,
      '_source_order': source_order,
    }
    if book_url:
      row['_book_url'] = book_url
    if votes:
      row['votes'] = votes
    return row

  def dedupe_rows(self, rows):
    deduped = []
    index_by_key = {}
    for row in rows:
      authors = row.get('authors', row.get('author', ''))
      if isinstance(authors, (list, tuple)):
        authors = ' '.join(str(author) for author in authors)
      year = row.get('award_year')
      category = category_key(row.get('category', ''))
      title = normalize_heading(row.get('title', ''))
      authors = normalize_heading(authors)
      if not title or not authors:
        continue
      book_id = self.goodreads_book_id(
        row.get('_book_url') or row.get('source_url', ''))
      keys = [('title_authors', year, category, title, authors)]
      if book_id:
        keys.insert(0, ('goodreads_book', year, category, book_id))
      existing_index = next(
        (index_by_key[key] for key in keys if key in index_by_key),
        None)
      if existing_index is None:
        existing_index = len(deduped)
        deduped.append(row)
      for key in keys:
        index_by_key[key] = existing_index
      existing = deduped[existing_index]
      if existing.get('result') != RESULT_WINNER and row.get('result') == RESULT_WINNER:
        deduped[existing_index] = row
    return deduped

  def goodreads_book_id(self, source_url):
    """Identify repeated winner/nominee cards even when their credits differ."""
    match = re.search(r'/book/show/(\d+)', source_url or '', re.I)
    return match.group(1) if match is not None else ''

  def apply_contributor_corrections(self, rows):
    corrected_book_ids = set()
    for row in rows:
      book_id = self.goodreads_book_id(row.get('_book_url') or '')
      correction = self.contributor_corrections.get(book_id)
      if correction is None:
        continue
      if normalize_heading(row.get('title', '')) != normalize_heading(
          correction.get('title', '')):
        continue
      categories = {
        category_key(value)
        for value in (correction.get('categories') or ())
      }
      if categories and category_key(row.get('category', '')) not in categories:
        continue
      authors = [
        normalize_line(author)
        for author in (correction.get('authors') or ())
        if normalize_line(author)
      ]
      if not authors:
        continue
      row['authors'] = authors
      corrected_book_ids.add(book_id)
    return corrected_book_ids

  def enrich_latest_contributors(
      self, rows, fetch_url, notes, sleep=None, progress=None,
      corrected_book_ids=None, latest_published_year=None):
    corrected_book_ids = set(corrected_book_ids or ())
    row_years = [
      int(row['award_year'])
      for row in rows
      if str(row.get('award_year', '')).isdigit()
    ]
    if not row_years:
      return
    latest_published_year = int(
      latest_published_year or max(row_years))
    enrichment_years = set(
      range(
        latest_published_year - DETAIL_ENRICH_LATEST_YEARS + 1,
        latest_published_year + 1))
    candidates = []
    for row in rows:
      try:
        row_year = int(row.get('award_year'))
      except (TypeError, ValueError):
        continue
      book_id = self.goodreads_book_id(row.get('_book_url') or '')
      if (
          row_year in enrichment_years
          and book_id
          and book_id not in corrected_book_ids):
        candidates.append((row, book_id))
    candidates = candidates[:DETAIL_REQUEST_LIMIT]
    if not candidates:
      return

    detail_cache = {}
    successful = 0
    failures = 0
    request_count = 0
    challenge = False
    total = len(candidates)
    for index, (row, book_id) in enumerate(candidates, 1):
      if progress is not None:
        progress(
          index,
          total,
          f'Checking Goodreads contributors {index} of {total}')
      try:
        if book_id not in detail_cache:
          if request_count and sleep is not None:
            sleep(DETAIL_REQUEST_DELAY_SECONDS)
          request_count += 1
          page_html = fetch_url(row['_book_url'])
          if self.is_challenge_page(page_html):
            challenge = True
            break
          detail_cache[book_id] = self.detail_contributors(page_html)
        detail_authors = detail_cache[book_id]
        successful += 1
        row['authors'] = self.merge_authors(
          row.get('authors') or (), detail_authors)
      except Exception as err:
        if self.is_access_challenge_error(err):
          challenge = True
          break
        failures += 1

    if challenge:
      unchecked = total - successful
      notes.append(
        f'Goodreads contributor enrichment stopped after an access '
        f'challenge; {unchecked} newest-year row'
        f'{"s" if unchecked != 1 else ""} retained ballot credits.')
    elif failures:
      notes.append(
        f'Goodreads contributor enrichment could not check {failures} '
        f'newest-year row{"s" if failures != 1 else ""}; ballot credits '
        f'were retained.')

  def detail_contributors(self, html):
    soup = BeautifulSoup(html or '', 'html.parser')
    container = soup.select_one(
      '.BookPageMetadataSection__contributor, '
      '[aria-label="List of contributors"]')
    if container is None:
      return []
    credits = []
    for name_node in container.select('[data-testid="name"]'):
      name = self.clean_text(name_node)
      link = name_node.find_parent('a')
      role_node = (
        link.select_one('[data-testid="role"]')
        if link is not None
        else None)
      credits.append({
        'name': name,
        'role': self.clean_text(role_node) if role_node is not None else '',
      })
    return self.matchable_contributor_names(credits)

  def is_challenge_page(self, html):
    text = normalize_heading(
      BeautifulSoup(html or '', 'html.parser').get_text(' ', strip=True))
    return any(marker in text for marker in (
      'access denied',
      'verify you are human',
      'captcha',
      'robot check',
      'not a robot',
      'cloudflare',
    ))

  def is_access_challenge_error(self, error):
    code = getattr(error, 'code', None)
    if code in (403, 429):
      return True
    text = normalize_heading(str(error))
    return any(marker in text for marker in (
      '403',
      '429',
      'forbidden',
      'access denied',
      'captcha',
      'challenge',
      'too many requests',
    ))

  def merge_authors(self, existing, additions):
    merged = []
    seen = set()
    for author in tuple(existing or ()) + tuple(additions or ()):
      author = normalize_line(author)
      key = normalize_heading(author)
      if author and key not in seen:
        seen.add(key)
        merged.append(author)
    return merged

  def entries_from_rows(self, rows):
    by_year = {}
    for row in rows:
      by_year.setdefault(int(row['award_year']), []).append(row)
    entries = []
    for year in sorted(by_year):
      year_rows = sorted(
        by_year[year],
        key=lambda row: (
          0 if row.get('result') == RESULT_WINNER else 1,
          row.get('_source_order', 0)))
      award_rows = []
      for row in year_rows:
        entry_row = {
          key: value
          for key, value in row.items()
          if not key.startswith('_')
        }
        award_rows.append(self.build_award_entry(
          entry_row, row['source_url'], year, row['category']))
      entries.extend(assign_positions(award_rows, year))
    return entries


def parse_goodreads_choice_awards(
    html, category, category_aliases=(), url=CHOICE_AWARDS_URL,
    name=AWARD_NAME, fetch_url=None, overview_pages=None, category_pages=None,
    sleep=None, validate_pages=None, enrich_contributors=None):
  return GoodreadsChoiceAwardsParser(category, category_aliases).parse(
    html,
    url,
    name,
    fetch_url=fetch_url,
    overview_pages=overview_pages,
    category_pages=category_pages,
    sleep=sleep,
    validate_pages=validate_pages,
    enrich_contributors=enrich_contributors)
