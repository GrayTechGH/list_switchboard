"""Official correction for the copied 2018 Fiction block on the 2017 page.

Only that known Creative Australia contradiction uses the original government
shortlist/winner announcements. Their bounded Fiction sections must agree on
five nominees and exactly one winning work. Other year/category checks remain
strict; this never relabels 2018 books as 2017.
"""

from copy import deepcopy
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, UnicodeDammit

from .award_base import normalize_heading, split_title_author
from .prime_ministers_literary_awards import PrimeMinistersLiteraryAwardsOfficialParser


SHORTLIST_URL = 'https://pmtranscripts.pmc.gov.au/release/transcript-41331'
WINNER_URL = 'https://pmtranscripts.pmc.gov.au/release/transcript-41357'


def work_key(row):
  return normalize_heading(row['title']), normalize_heading(row['author'])


def transcript_rows(parser, source, url, shortlist):
  if isinstance(source, bytes):
    source = UnicodeDammit(source, is_html=True).unicode_markup
  soup = BeautifulSoup(source or '', 'html.parser')
  canonical = soup.find('link', rel='canonical')
  if canonical and canonical.get('href', '').rstrip('/') != url.rstrip('/'):
    raise ValueError('Official 2017 transcript canonical identity did not match.')
  article = soup.select_one('article.node--type-transcript')
  body = article.find(class_='field--name-body') if article else None
  intro = body.find('p', recursive=False) if body else None
  text = normalize_heading(intro.get_text(' ', strip=True)) if intro else ''
  if '2017 prime minister s literary awards' not in text or ('shortlist' if shortlist else 'winners') not in text:
    raise ValueError('Official 2017 transcript had the wrong award year or announcement kind.')
  fiction = next((p for p in body.find_all('p', recursive=False)
    if normalize_heading(p.get_text(' ', strip=True)) == 'fiction'), None)
  section = fiction.find_next_sibling() if fiction else None
  if section is None or section.name != ('ul' if shortlist else 'p'):
    raise ValueError('Official 2017 transcript was missing its bounded Fiction section.')
  nodes = section.find_all('li', recursive=False) if shortlist else [section]
  rows = []
  for node in nodes:
    title, author = split_title_author(node.get_text(' ', strip=True))
    if not title or not author:
      raise ValueError('Official 2017 Fiction announcement had an incomplete book byline.')
    rows.append({'award_year': '2017', 'category': 'Fiction',
      'title': parser.clean_title(title), 'author': parser.clean_author(author),
      'result': 'shortlisted' if shortlist else 'winner', 'source_url': url})
  expected = 5 if shortlist else 1
  if len(rows) != expected or len({work_key(r) for r in rows}) != expected:
    raise ValueError('Official 2017 Fiction announcement had an incomplete roster.')
  return rows


class PrimeMinistersFictionOfficialParser(PrimeMinistersLiteraryAwardsOfficialParser):

  UPDATE_STRATEGY = 'pmla-fiction-official-2017-v1'
  EXTRA_SOURCE_SCOPE = (SHORTLIST_URL, WINNER_URL)

  def annual_rows(self, page, url, year, fetch_url):
    rows = self.page_rows(page, url)
    wrong = [r for r in rows if str(r['award_year']) != str(year)]
    if not wrong:
      return rows
    soup = BeautifulSoup(page, 'html.parser')
    heading = soup.find('h1')
    known_copy = (self.category == 'Fiction' and year == 2017 and
      urlsplit(url).hostname in ('creative.gov.au', 'www.creative.gov.au') and
      urlsplit(url).path.rstrip('/') == '/2017-pmla-winners-shortlist-and-judges' and
      heading is not None and self.year_from_text(self.clean_text(heading)) == 2017 and
      {r['award_year'] for r in wrong} == {'2018'} and len({work_key(r) for r in wrong}) == 5 and
      len({work_key(r) for r in wrong if r['result'] == 'winner'}) == 1)
    if not known_copy:
      raise ValueError('Official annual archive returned another award year.')
    shortlist = transcript_rows(self, fetch_url(SHORTLIST_URL), SHORTLIST_URL, True)
    winners = transcript_rows(self, fetch_url(WINNER_URL), WINNER_URL, False)
    winner = winners[0]
    if work_key(winner) not in {work_key(r) for r in shortlist}:
      raise ValueError('Official 2017 Fiction winner was not in the official shortlist.')
    corrected = deepcopy(shortlist)
    for row in corrected:
      if work_key(row) == work_key(winner):
        row['result'] = 'winner'
        row['shortlist_source_url'] = SHORTLIST_URL
        row['source_url'] = WINNER_URL
    return corrected

  def parse(self, *args, **kwargs):
    parsed = super().parse(*args, **kwargs)
    if any(e.get('source', {}).get('url') in (SHORTLIST_URL, WINNER_URL) for e in parsed['entries']):
      parsed['notes'].append('The official 2017 Fiction shortlist and winner announcements correct a copied 2018 Fiction block on the Creative Australia 2017 archive page.')
    return parsed
