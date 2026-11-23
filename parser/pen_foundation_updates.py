"""Official Foundation history, book cards and bounded announcement readers.

Maintenance notes:
- Cover alt text is reused across books; only the linked detail supplies title
  and creator. The history column supplies winner status, since detail pages
  can retain an earlier Finalist label after the winner is announced.
- History can be reused within a verified current award cycle. At rollover or
  after missed cycles it refreshes. Current book details/announcements stay live;
  closed detail rows and dated posts remain source-scoped parsed projections.
"""

import datetime
import json
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, NavigableString

try:
  from calibre_plugins.list_switchboard.errors import ImportCancelledError, CamoufoxRequiredError
  from calibre_plugins.list_switchboard.parser.award_base import normalize_heading, normalize_line, strip_publication_notes, is_author_suffix
  from calibre_plugins.list_switchboard.parser.incremental import ParsedUnitCache, project_source_rows, restore_source_rows
  from calibre_plugins.list_switchboard.parser.generic import position_sort_key
except ImportError:
  from errors import ImportCancelledError, CamoufoxRequiredError
  from .award_base import normalize_heading, normalize_line, strip_publication_notes, is_author_suffix
  from .incremental import ParsedUnitCache, project_source_rows, restore_source_rows
  from .generic import position_sort_key


def content(html):
  soup = BeautifulSoup(html, 'html.parser')
  return soup.select_one('.entry-content') or soup.find('main') or soup


def row(year, title, author, result, url, category):
  return {'award_year': str(year), 'title': normalize_line(title),
    'author': strip_publication_notes(normalize_line(author)),
    'result': result, 'source_url': url, 'category': category}


def paragraph_rows(p, year, result, url, category):
  """Read marked titles and their own line's byline, preserving title commas."""
  lines, text, titles = [], '', []
  for node in p.descendants:
    if isinstance(node, NavigableString):
      text += str(node)
    elif node.name == 'br':
      lines.append((normalize_line(text), titles))
      text, titles = '', []
    elif node.name in ('i', 'em'):
      titles.append(node.get_text(' ', strip=True))
  lines.append((normalize_line(text), titles))
  rows = []
  for text, titles in lines:
    if not titles:
      work = re.sub(r'^\s*(?:winner|finalists?)\s*:\s*', '', text, flags=re.I)
      work = re.sub(r'^\s*(?:19|20)\d{2}\s*', '', work)
      if re.search(r'\s+by\s+', work, re.I):
        title, author = re.split(r'\s+by\s+', work, maxsplit=1, flags=re.I)
      elif ',' in work:
        author, title = work.split(',',1)
        if ',' in title:
          suffix, rest = title.split(',',1)
          if is_author_suffix(suffix.strip()):
            author, title = author + ',' + suffix, rest
      else:
        continue
      if title.strip() and author.strip():
        rows.append(row(year,title.strip(),author.strip(),result,url,category))
      continue
    start = text.find(titles[0])
    if start<0:
      continue
    end = start + len(titles[0])
    contiguous = True
    for fragment in titles[1:]:
      following = text.find(fragment,end)
      if following<0 or text[end:following].strip():
        contiguous = False
        break
      end = following + len(fragment)
    if not contiguous:
      continue
    title = text[start:end]
    before, _title, after = text.partition(title)
    if re.match(r'^\s*by\s+', after, re.I):
      author = re.sub(r'^\s*by\s+', '', after, flags=re.I)
    else:
      author = re.sub(r'^\s*(?:winner|finalists?)\s*:\s*', '', before, flags=re.I)
      author = re.sub(r'^\s*(?:19|20)\d{2}\s*', '', author).strip(' ,:')
    if author:
      rows.append(row(year, title, author, result, url, category))
  return rows


def history_sources(html, url, parser):
  body = content(html)
  links, seen, rows = [], set(), []
  for heading in body.find_all(['h2', 'h3']):
    text = heading.get_text(' ', strip=True)
    match = re.fullmatch(r'((?:19|20)\d{2})\s+Winner', text, re.I)
    if match:
      year = int(match.group(1))
      column = heading.find_parent('div', class_='et_pb_column')
      group = heading.find_parent('div', class_='et_pb_row')
      if column is None or group is None:
        continue
      winner_link = next((a.get('href') for a in column.find_all('a', href=True) if a.find('img')), None)
      for anchor in group.find_all('a', href=True):
        target = urljoin(url, anchor['href'])
        if (not anchor.find('img') or urlsplit(target).hostname != urlsplit(url).hostname or
            not re.search(r'/\d{4}/\d{2}/\d{2}/[^/]+/?$', urlsplit(target).path)):
          continue
        result = 'winner' if anchor['href'] == winner_link else 'nominee'
        key = (target, year, result)
        if key not in seen:
          seen.add(key)
          links.append({'url': target, 'year': year, 'result': result})
    if re.fullmatch(r'(?:19|20)\d{2}', text):
      year, result = int(text), None
      for sibling in heading.next_siblings:
        if getattr(sibling, 'name', None) in ('h2', 'h3'):
          break
        if getattr(sibling, 'name', None) != 'p':
          continue
        label = sibling.get_text(' ', strip=True)
        if re.match(r'^WINNER\s*:', label, re.I):
          result = 'winner'
        elif re.match(r'^FINALISTS?\s*:', label, re.I):
          result = 'nominee'
        if result:
          rows.extend(paragraph_rows(sibling, year, result, url, parser.CATEGORY))
    if text == 'Past Winners' and 'Hemingway' in parser.AWARD_NAME:
      section = heading.find_parent('div', class_='et_pb_section') or heading.parent
      for p in section.find_all('p'):
        match = re.match(r'^((?:19|20)\d{2})\b', p.get_text(' ', strip=True))
        if match:
          rows.extend(paragraph_rows(p, int(match.group(1)), 'winner', url, parser.CATEGORY))
  if not links and not rows:
    # Small legacy fixtures use explicit year/result headings and bylines.
    if body.select_one('.et_pb_row'):
      raise ValueError('Official Foundation history did not expose award sections.')
    rows = parser.parse_history(parser.html_root(str(body)), url)
  if not rows and not links:
    raise ValueError('Official Foundation history had no usable award rows.')
  return rows, links


def detail_row(html, spec, parser):
  body = content(html)
  heading = body.find(['h1', 'h2'])
  if heading is None:
    raise ValueError('Foundation book detail had no title heading.')
  title = heading.get_text(' ', strip=True)
  author = ''
  biography = heading.parent
  byline = biography.select_one('.et_pb_member_position') if biography else None
  if byline:
    author = re.sub(r'^by\s+', '', byline.get_text(' ', strip=True), flags=re.I)
  bold = biography.find(['strong', 'b']) if biography else None
  if not author and bold and biography.get_text(' ',strip=True).partition(title)[2].strip().startswith(bold.get_text(' ',strip=True)):
    author = bold.get_text(' ',strip=True)
  for p in heading.find_all_next('p'):
    if author:
      break
    if body not in p.parents:
      break
    text = p.get_text(' ', strip=True)
    if text.startswith('Purchase'):
      break
    bold = p.find(['strong', 'b'])
    if bold and text.startswith(bold.get_text(' ', strip=True)):
      author = bold.get_text(' ', strip=True)
      break
    match = re.match(r'^(.+?)\s+(?:is|was|has|attended|received|grew|lives|holds|studied|writes|worked|earned|graduated|teaches)\b', text)
    if match:
      author = match.group(1)
      break
  if not title or not author:
    raise ValueError('Foundation book detail did not identify its creator.')
  author = re.sub(r"[\u2019']s$", '', author)
  return row(spec['year'], title, author, spec['result'], spec['url'], parser.CATEGORY)


def announcement_rows(html, url, kind, parser):
  body = content(html)
  year_match = re.search(r'/((?:19|20)\d{2})/', url)
  year = int(year_match.group(1)) if year_match else parser.year_from_text(body.get_text(' ', strip=True))
  if kind in ('winner_post', 'current'):
    for p in body.find_all('p'):
      text = p.get_text(' ', strip=True)
      if 'has been selected as the winner' not in text:
        continue
      title_node = p.find(['i', 'em'])
      if title_node is None:
        continue
      title = title_node.get_text(' ', strip=True)
      author = text.partition(title)[0].strip()
      author = re.sub(r"[\u2019']s?\s*$", '', author).strip()
      if author and year:
        return [row(year, title, author, 'winner', url, parser.CATEGORY)]
  if kind == 'finalist_post':
    for p in body.find_all('p'):
      if not re.search(r'\bfinalists\b', p.get_text(' ', strip=True), re.I):
        continue
      titles = p.find_all(['i', 'em'])
      if not titles:
        listing = p.find_next_sibling(['ul', 'ol'])
        if listing:
          return [r for li in listing.find_all('li', recursive=False)
            for r in paragraph_rows(li, year, 'nominee', url, parser.CATEGORY)]
        continue
      text = p.get_text(' ', strip=True)
      titles = [n.get_text(' ', strip=True) for n in titles]
      rows, cursor = [], 0
      for index, title in enumerate(titles):
        start = text.find(title, cursor)
        end = text.find(titles[index+1], start+len(title)) if index+1 < len(titles) else len(text)
        byline = text[start+len(title):end]
        match = re.match(r'\s*by\s+(.+)', byline, re.I)
        if match:
          author = re.sub(r',\s*(?:and\s*)?$', '', match.group(1).strip().rstrip('.')).strip()
          rows.append(row(year, title, author, 'nominee', url, parser.CATEGORY))
        cursor = end
      if rows:
        return rows
  root = parser.html_root(str(body))
  if kind == 'finalist_post':
    return parser.parse_current_finalist_post(root, url)
  return parser.parse_current(root, url) if kind == 'current' else parser.parse_current_winner_post(root, url)


def fetch_foundation(recipe, fetch_url, cached_parsed=None, incremental_update=False,
    before_fetch=None, after_fetch=None, progress=None):
  parser, year = recipe.parser(), datetime.datetime.now().year
  cache = ParsedUnitCache('pen-foundation-projections-v1', json.dumps([
    recipe.source_id, recipe.URL, recipe.POST_URLS, type(parser).__name__]), cached_parsed, incremental_update)
  snapshots = {}
  def previous(key):
    unit = cache.old_units.get(key) or {}
    try:
      return restore_source_rows(cache.previous(key), unit.get('metadata') or {})
    except (ValueError, TypeError):
      return None
  def fetch(url):
    if before_fetch:
      before_fetch(url)
    html = recipe.fetch_url(fetch_url, url)
    if after_fetch:
      after_fetch(url, html)
    return html
  notes, fresh_cycle, current_changed = [], False, False
  for url, kind in recipe.POST_URLS:
    matched = re.search(r'/((?:19|20)\d{2})/', url)
    cycle = int(matched.group(1)) if matched else None
    old = cache.old_units.get(url) or {}
    old_rows = previous(url)
    if cycle and cycle < year and old.get('complete') is True and old_rows:
      snapshots[url] = (old_rows, True, cycle, {})
      continue
    try:
      rows = announcement_rows(fetch(url), url, kind, parser)
      if not rows:
        raise ValueError('Foundation announcement did not expose award rows.')
      fresh_cycle = fresh_cycle or (cycle == year and any(r['result']=='winner' for r in rows))
      if cycle == year and rows != old_rows:
        current_changed = True
      snapshots[url] = (rows, True, cycle, {})
    except (ImportCancelledError, CamoufoxRequiredError):
      raise
    except Exception as err:
      if not cache.old_units:
        raise
      snapshots[url] = (old_rows or [], False, cycle, {})
      notes.append(f'Foundation announcement could not be refreshed: {url}: {err}')
  old_history = cache.old_units.get(recipe.URL) or {}
  history_rows = previous(recipe.URL)
  history_meta = old_history.get('metadata') or {}
  links = history_meta.get('links')
  valid_links = (isinstance(links,list) and
    all(isinstance(s,dict) and isinstance(s.get('url'),str) and type(s.get('year')) is int and
      s.get('result') in ('winner','nominee') for s in links))
  if (fresh_cycle and not current_changed and old_history.get('complete') is True and old_history.get('revision') == year and
      history_rows is not None and isinstance(links, list) and
      all(isinstance(s,dict) and isinstance(s.get('url'),str) and type(s.get('year')) is int and
        s.get('result') in ('winner','nominee') and s['year'] <= year for s in links)):
    snapshots[recipe.URL] = (history_rows, True, year, {'links':links})
  else:
    try:
      history_rows, links = history_sources(fetch(recipe.URL), recipe.URL, parser)
      snapshots[recipe.URL] = (history_rows, True, year, {'links':links})
    except (ImportCancelledError, CamoufoxRequiredError):
      raise
    except Exception as err:
      if not cache.old_units or not valid_links or history_rows is None:
        raise
      snapshots[recipe.URL] = (history_rows or [], False, year, {'links':links})
      notes.append(f'Foundation history could not be refreshed: {err}')
  for index, spec in enumerate(links,1):
    url, revision = spec['url'], [spec['year'],spec['result']]
    old, old_rows = cache.old_units.get(url) or {}, previous(url)
    if (spec['year'] < year and old.get('complete') is True and
        old.get('revision') == revision and old_rows):
      snapshots[url] = (old_rows, True, revision, {})
    else:
      try:
        snapshots[url] = ([detail_row(fetch(url),spec,parser)], True, revision, {})
      except (ImportCancelledError, CamoufoxRequiredError):
        raise
      except Exception as err:
        if not cache.old_units:
          raise
        snapshots[url] = (old_rows or [], False, revision, {})
        notes.append(f'Foundation book detail could not be refreshed: {url}: {err}')
    if progress:
      progress(index,len(links),f'Processed Foundation book {index} of {len(links)}...')
  ordered = [recipe.URL] + [s['url'] for s in links] + [url for url,_kind in recipe.POST_URLS]
  raw, owners = [], {}
  for key in ordered:
    for item in snapshots[key][0]:
      identity = (item['award_year'], normalize_heading(item['title']), normalize_heading(item['author']))
      if identity not in owners:
        owners[identity] = len(raw)
        raw.append(item)
      elif item['result']=='winner' and raw[owners[identity]]['result']!='winner':
        raw[owners[identity]] = item
  entries = sorted(parser.entries_from_rows(raw,parser.CATEGORY),
    key=lambda e: position_sort_key(e.get('position','')))
  for key,(rows,complete,revision,extra) in snapshots.items():
    projected,metadata = project_source_rows(rows,entries,
      lambda r: (str(r['award_year']),normalize_heading(r['title'])))
    metadata.update(extra)
    cache.put(key,projected,revision=revision,complete=complete,metadata=metadata)
  result = parser.parsed_result(recipe.NAME,recipe.URL,entries,notes)
  if not entries:
    raise ValueError('Foundation sources did not expose usable award entries.')
  result['incremental_state'] = cache.state(entries)
  result['incremental_state']['discovery'] = {'refresh_units': [s['url'] for s in links if s['year'] >= year]}
  return result
