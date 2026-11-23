"""Read Columbia's paired prize table and bounded annual summary rosters.

The archive alternates author/title rows for winners and 2022-onward finalists.
Earlier finalists and shortlist rows contain names only, never inferred book
titles; juror rows are excluded.
Annual summaries end at About the Prizes, before repeated book biographies.
"""

import hashlib
import json
import re

from bs4 import BeautifulSoup,UnicodeDammit

try:
  from calibre_plugins.list_switchboard.parser.award_base import normalize_heading,normalize_line
except ImportError:
  from .award_base import normalize_heading,normalize_line


FINALIST_TITLES_FROM_YEAR = 2022


def soup_for(source):
  if isinstance(source,bytes):source=UnicodeDammit(source).unicode_markup or ''
  return BeautifulSoup(source or '','html.parser')


def read_modern_lukas(parser,html,url,category):
  soup=soup_for(html);root=soup.find('main') or soup.find('article') or soup
  for node in root.find_all(['nav','footer','script','style']):node.decompose()
  title=' '.join(n.get_text(' ',strip=True) for n in root.find_all('h1'))
  if 'lukas' not in normalize_heading(title) or 'prize' not in normalize_heading(title):return None
  for table in root.find_all('table'):
    header=table.find('tr')
    cells=header.find_all(['th','td'],recursive=False) if header else []
    columns=[index for index,cell in enumerate(cells) if
      normalize_heading(cell.get_text(' ',strip=True)) in parser.normalized_category_aliases()]
    if columns:
      return archive_rows(parser,root,table,columns[0],url,category)
  if '/news/' in url or 'shortlist' in normalize_heading(title) or 'winners' in normalize_heading(title):
    return news_rows(parser,root,title,url,category)
  if 'project' in normalize_heading(title):
    raise ValueError('The official Lukas project page did not expose its prize archive table.')
  return None


def archive_rows(parser,root,table,column,url,category):
  rows=[];rosters={};notes=[];year=None;stage=None;pending=None;complete=True;missing_titles=False
  def finish_pending():
    nonlocal pending,complete,missing_titles
    if pending is not None:
      missing_titles=True
      if pending['result']=='winner':complete=False
      pending=None
  for tr in table.find_all('tr')[1:]:
    cells=tr.find_all(['td','th'],recursive=False)
    if len(cells)<=max(column,1):continue
    texts=[normalize_line(cell.get_text(' ',strip=True)) for cell in cells]
    if re.fullmatch(r'(?:19|20)\d{2}',texts[0]):
      finish_pending();year=int(texts[0]);stage=None
    label=normalize_heading(texts[1])
    if label:
      finish_pending();stage=parser.result_from_heading(label)
      if label.startswith(('juror','judge','jury')):stage=None
    if year is None or stage is None:continue
    value=texts[column]
    if not value:continue
    roster=rosters.setdefault(year,[])
    # Earlier finalist blocks list consecutive people, not alternating book rows.
    if stage=='shortlisted' or (stage=='finalist' and year<FINALIST_TITLES_FROM_YEAR):
      roster.append({'author':parser.clean_official_author(value),'title':None,'result':stage})
      missing_titles=True
    elif pending is None:
      pending={'author':parser.clean_official_author(value),'title':None,'result':stage}
      roster.append(pending)
    else:
      pending['title']=parser.clean_title(value)
      rows.append({'award_year':str(year),'category':category,'source_url':url,**pending})
      pending=None
  finish_pending()
  years=sorted(rosters)
  declared=None
  for heading in root.find_all(['h2','h3','h4']):
    match=re.fullmatch(r'Winners since ((?:19|20)\d{2})',normalize_line(heading.get_text(' ',strip=True)),re.I)
    if match:declared=int(match.group(1));break
  if not years or years!=list(range(declared or years[0],years[-1]+1)):
    raise ValueError('Columbia prize archive did not expose continuous declared years.')
  if any(not any(row['result']=='winner' and row['title'] for row in rosters[y]) for y in years[:-1]):
    complete=False
  if not rows:raise ValueError('Columbia prize archive did not expose title-bearing results.')
  if missing_titles:notes.append('The official archive lists some finalist/shortlist names without book titles; only title-bearing archive rows and configured annual news rosters are imported.')
  if not complete:notes.append('The official prize archive has an incomplete winner/title pair; history remains pending.')
  revisions={str(y):hashlib.sha256(json.dumps(rosters[y],sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest() for y in years}
  return {'kind':'archive','rows':rows,'notes':notes,'rosters':rosters,'revisions':revisions,'complete':complete}


def prize_label(parser,node):
  text=normalize_line(node.get_text(' ',strip=True))
  text=re.sub(r'\s*\([^)]*\$[^)]*\)\s*',' ',text).strip(' :')
  key=normalize_heading(text)
  def matches(aliases):
    return any(re.fullmatch(re.escape(alias)+r'(?: (?:winners?|finalists?|shortlists?))?',key) for alias in aliases)
  if matches(parser.normalized_category_aliases()):return 'target'
  if matches(parser.normalized_peer_prize_aliases()):return 'peer'
  return None


def news_rows(parser,root,title,url,category):
  year=parser.year_from_text(title);expected=parser.year_from_text(url)
  if not year or (expected and year!=expected):raise ValueError('Official Lukas news returned another award year.')
  rows=[];active=False;complete=True;found=False
  default='shortlisted' if 'shortlist' in normalize_heading(title) else 'winner'
  stage=default
  for node in root.find_all(['h2','h3','h4','p','li']):
    if node.find_parent(['nav','footer']):continue
    text=normalize_line(node.get_text(' ',strip=True));key=normalize_heading(text)
    if node.name in ('h2','h3','h4') and key.startswith('about the prizes'):break
    label=prize_label(parser,node) if node.name in ('h2','h3','h4','p') else None
    if label:
      active=label=='target';found=found or active
      stage=parser.result_from_heading(text) or default
      continue
    if not active or node.name!='li':continue
    explicit=re.match(r'^\s*(winner|finalists?|shortlist(?:ed)?)\s*:\s*(.+)$',text,re.I)
    result=parser.result_from_heading(explicit.group(1)) if explicit else stage
    work=explicit.group(2) if explicit else text
    title_node=next((n for n in node.find_all(['em','i']) if normalize_line(n.get_text(' ',strip=True))),None)
    if title_node is not None:
      book_title=parser.clean_title(title_node.get_text(' ',strip=True))
      fragment=soup_for(str(node));mark=fragment.find(['em','i']);mark.replace_with('__LUKAS_TITLE__')
      prefix=fragment.get_text(' ',strip=True).split('__LUKAS_TITLE__',1)[0]
      prefix=re.sub(r'^\s*(?:winner|finalists?|shortlist(?:ed)?)\s*:\s*','',prefix,flags=re.I)
      author=parser.clean_official_author(prefix.strip(' ,:'))
    else:book_title,author=parser.title_author_from_text(work)
    author=parser.clean_official_author(author)
    if not book_title or not author:
      complete=False;continue
    rows.append({'award_year':str(year),'category':category,'source_url':url,
      'title':book_title,'author':author,'result':result})
  if not found or not rows:raise ValueError('Official Lukas news did not expose its configured prize summary.')
  notes=[] if complete else ['An official prize news summary contains an incomplete book byline.']
  return {'kind':'news','rows':rows,'notes':notes,'year':year,'complete':complete,'rosters':{},'revisions':{}}
