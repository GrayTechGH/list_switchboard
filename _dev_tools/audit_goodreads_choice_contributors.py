#!/usr/bin/env python

"""Resume-safe Goodreads Choice contributor audit.

The audit stores normalized ballot/detail credits only. It deliberately stops
at the first access challenge and never attempts to solve or bypass one.
Corrections still require manual verification before they are copied into the
packaged contributor ledger.
"""

import argparse
from datetime import date
import json
from pathlib import Path
import socket
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))

from parser.award_base import normalize_heading  # noqa: E402
from parser.goodreads_choice_awards import (  # noqa: E402
  CHOICE_AWARDS_URL,
  DETAIL_REQUEST_DELAY_SECONDS,
  FIRST_OVERVIEW_YEAR,
  GoodreadsChoiceAwardsParser,
  clean_category_text,
  goodreads_choice_overview_url,
  year_from_text,
)


USER_AGENT = (
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
  'AppleWebKit/537.36 Chrome/125 Safari/537.36')
REQUEST_TIMEOUT_SECONDS = 60
TIMEOUT_RETRIES = 3
EXCLUDED_CATEGORY_KEYS = {
  normalize_heading('Goodreads Author'),
  normalize_heading('Cover Art'),
}


class AccessChallenge(RuntimeError):
  pass


class ThrottledFetcher:

  def __init__(self, delay):
    self.delay = max(0.0, float(delay))
    self.last_request_at = None
    self.challenge_parser = GoodreadsChoiceAwardsParser('Audit')

  def fetch(self, url):
    if self.last_request_at is not None:
      remaining = self.delay - (time.monotonic() - self.last_request_at)
      if remaining > 0:
        time.sleep(remaining)
    for attempt in range(TIMEOUT_RETRIES + 1):
      self.last_request_at = time.monotonic()
      try:
        request = Request(url, headers={'User-Agent': USER_AGENT})
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
          html = response.read().decode('utf-8', errors='replace')
        if self.challenge_parser.is_challenge_page(html):
          raise AccessChallenge(f'challenge page returned for {url}')
        return html
      except HTTPError as err:
        if err.code in (403, 429):
          raise AccessChallenge(f'HTTP {err.code} for {url}') from err
        raise
      except (TimeoutError, socket.timeout, URLError) as err:
        reason = getattr(err, 'reason', err)
        is_timeout = isinstance(reason, (TimeoutError, socket.timeout))
        if not is_timeout or attempt >= TIMEOUT_RETRIES:
          raise


def load_checkpoint(path):
  if not path.exists():
    return {
      'schema_version': 1,
      'checked': {},
      'completed_pages': [],
      'ballot_pages': {},
      'stopped_reason': '',
    }
  data = json.loads(path.read_text(encoding='utf-8'))
  if data.get('schema_version') != 1:
    raise ValueError(f'Unsupported checkpoint schema in {path}')
  data.setdefault('checked', {})
  data.setdefault('completed_pages', [])
  data.setdefault('ballot_pages', {})
  data.setdefault('stopped_reason', '')
  return data


def save_checkpoint(path, data):
  path.parent.mkdir(parents=True, exist_ok=True)
  temporary = path.with_suffix(path.suffix + '.tmp')
  temporary.write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + '\n',
    encoding='utf-8')
  temporary.replace(path)


def category_links(html, overview_url, category_filter=''):
  soup = BeautifulSoup(html or '', 'html.parser')
  fallback_year = year_from_text(overview_url)
  wanted = normalize_heading(category_filter)
  links = []
  seen = set()
  for link in soup.find_all('a', href=True):
    href = urljoin(overview_url, link.get('href') or '')
    if '/choiceawards/' not in href or '/best-books-' in href:
      continue
    year = year_from_text(href) or fallback_year
    category = clean_category_text(link.get_text(' ', strip=True))
    key = normalize_heading(category)
    if (
        year is None
        or not category
        or key in EXCLUDED_CATEGORY_KEYS
        or (wanted and key != wanted)
        or (year, href) in seen):
      continue
    seen.add((year, href))
    links.append({
      'year': year,
      'category': category,
      'url': href,
    })
  return sorted(links, key=lambda item: (item['year'], item['category']))


def newest_advertised_year(html):
  soup = BeautifulSoup(html or '', 'html.parser')
  years = [
    year_from_text(link.get('href') or '')
    for link in soup.find_all('a', href=True)
    if '/choiceawards/best-books-' in (link.get('href') or '')
  ]
  years = [year for year in years if year is not None]
  return max(years) if years else date.today().year - 1


def audit(args):
  checkpoint_path = Path(args.checkpoint).resolve()
  state = load_checkpoint(checkpoint_path)
  state['stopped_reason'] = ''
  fetcher = ThrottledFetcher(args.delay)
  details_checked_this_run = 0

  try:
    landing_html = fetcher.fetch(CHOICE_AWARDS_URL)
    final_year = args.end_year or newest_advertised_year(landing_html)
    first_year = max(FIRST_OVERVIEW_YEAR, args.start_year)
    for year in range(first_year, final_year + 1):
      overview_url = goodreads_choice_overview_url(year)
      overview_html = fetcher.fetch(overview_url)
      for link in category_links(
          overview_html, overview_url, args.category):
        page_url = link['url']
        if (
            (args.ballots_only and page_url in state['ballot_pages'])
            or (not args.ballots_only and page_url in state['completed_pages'])):
          continue
        page_html = fetcher.fetch(page_url)
        parser = GoodreadsChoiceAwardsParser(
          link['category'], (link['category'],))
        notes = []
        rows = parser.parse_category_page(
          page_html,
          page_url,
          fallback_year=link['year'],
          fallback_category=link['category'],
          notes=notes,
          validate=True)
        if not rows:
          raise RuntimeError('; '.join(notes) or f'No rows parsed from {page_url}')
        corrected_book_ids = (
          parser.apply_contributor_corrections(rows)
          if args.ballots_only
          else set())
        state['ballot_pages'][page_url] = {
          'year': link['year'],
          'category': link['category'],
          'row_count': len(rows),
          'corrected_book_ids': sorted(corrected_book_ids),
        }
        save_checkpoint(checkpoint_path, state)
        if args.ballots_only:
          continue
        for row in rows:
          book_id = parser.goodreads_book_id(row.get('_book_url') or '')
          if not book_id:
            continue
          existing = state['checked'].get(book_id)
          if existing is not None:
            categories = existing.setdefault('categories', [])
            if link['category'] not in categories:
              categories.append(link['category'])
              save_checkpoint(checkpoint_path, state)
            continue
          detail_html = fetcher.fetch(row['_book_url'])
          detail_authors = parser.detail_contributors(detail_html)
          ballot_authors = list(row.get('authors') or ())
          merged_authors = parser.merge_authors(
            ballot_authors, detail_authors)
          state['checked'][book_id] = {
            'title': row.get('title', ''),
            'ballot_authors': ballot_authors,
            'detail_authors': detail_authors,
            'merged_authors': merged_authors,
            'categories': [link['category']],
            'detail_url': row['_book_url'],
            'candidate': merged_authors != ballot_authors,
          }
          details_checked_this_run += 1
          save_checkpoint(checkpoint_path, state)
          if (
              args.max_details is not None
              and details_checked_this_run >= args.max_details):
            return checkpoint_path, state, details_checked_this_run
        state['completed_pages'].append(page_url)
        save_checkpoint(checkpoint_path, state)
  except AccessChallenge as err:
    state['stopped_reason'] = str(err)
    save_checkpoint(checkpoint_path, state)
  return checkpoint_path, state, details_checked_this_run


def parse_args():
  default_checkpoint = (
    Path(tempfile.gettempdir())
    / 'goodreads_choice_contributor_audit.json')
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
    '--checkpoint',
    default=str(default_checkpoint),
    help='Normalized resume checkpoint (default: system temporary folder).')
  parser.add_argument(
    '--start-year', type=int, default=FIRST_OVERVIEW_YEAR)
  parser.add_argument('--end-year', type=int)
  parser.add_argument(
    '--category',
    default='',
    help='Optional exact source category label.')
  parser.add_argument(
    '--delay',
    type=float,
    default=DETAIL_REQUEST_DELAY_SECONDS,
    help='Minimum delay between every Goodreads request.')
  parser.add_argument(
    '--max-details',
    type=int,
    help='Stop normally after this many new detail-page checks.')
  parser.add_argument(
    '--ballots-only',
    action='store_true',
    help='Validate/count category ballots without requesting book pages.')
  return parser.parse_args()


def main():
  path, state, checked = audit(parse_args())
  candidates = sum(
    bool(row.get('candidate'))
    for row in state.get('checked', {}).values())
  print(f'Checkpoint: {path}')
  print(f'New detail pages checked: {checked}')
  ballot_rows = sum(
    int(page.get('row_count') or 0)
    for page in state.get('ballot_pages', {}).values())
  print(f'Validated ballot rows in checkpoint: {ballot_rows}')
  ballot_corrections = {
    book_id
    for page in state.get('ballot_pages', {}).values()
    for book_id in (page.get('corrected_book_ids') or ())
  }
  print(f'Applied packaged ballot corrections: {len(ballot_corrections)}')
  print(f'Total correction candidates: {candidates}')
  if state.get('stopped_reason'):
    print(f'Stopped safely: {state["stopped_reason"]}')


if __name__ == '__main__':
  main()
