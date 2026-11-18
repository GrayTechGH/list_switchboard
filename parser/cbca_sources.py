"""Bounded CBCA Elementor rosters and font-aware official history PDFs.

The archive's accordion summary owns its year. Paragraph line breaks delimit
books; italic title runs preserve commas inside titles. PDF authors and titles
share a line, so Poppler's font/position XML separates them before normalization.
Unrelated visual-arts awards and the contents page are category boundaries.
"""

from collections import defaultdict
from functools import lru_cache
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup, NavigableString, UnicodeDammit


def soup_for(source):
  if isinstance(source, bytes):
    source = UnicodeDammit(source, is_html=True).unicode_markup
  return BeautifulSoup(source or '', 'html.parser')


def paragraph_lines(node):
  pieces = []
  for child in node.descendants:
    if getattr(child, 'name', None) == 'br':
      if pieces:
        yield pieces
      pieces = []
    elif isinstance(child, NavigableString):
      pieces.append((str(child), any(p.name in ('i', 'em') for p in child.parents if p is not node)))
  if pieces:
    yield pieces


def modern_html_rows(parser, source, url):
  soup = soup_for(source)
  main = soup.find('main') or soup
  details = main.find_all('details')
  blocks = []
  for panel in details:
    summary = panel.find('summary', recursive=False)
    year = parser.standalone_year(summary.get_text(' ', strip=True)) if summary else None
    if year:
      blocks.append((panel, year, None))
  if not blocks:
    heading = main.find(['h1', 'h2', 'h3'])
    text = heading.get_text(' ', strip=True) if heading else ''
    year = parser.year_from_text(text)
    key = text.casefold()
    if year and ('shortlist' in key or 'winner' in key):
      blocks.append((main, year, 'shortlisted' if 'shortlist' in key else None))
  if not blocks:
    return None
  rows = []
  for block, year, default_stage in blocks:
    category, stage = None, default_stage
    for node in block.find_all(['h2', 'h3', 'h4', 'h5', 'p', 'li']):
      text = node.get_text(' ', strip=True)
      if node.name == 'p':
        introduction = re.fullmatch(r'(?:Presenting|Introducing) the (\d{4}) CBCA Book of the Year Awards (.+?) Shortlist\s*[.\u2026]*', text, re.I)
        if introduction:
          if int(introduction[1]) != year:
            raise ValueError('CBCA shortlist introduction has a conflicting award year.')
          category = parser.category_from_text(introduction[2])
          stage = default_stage
          continue
      if node.name.startswith('h'):
        found = parser.category_from_text(text)
        if found:
          category, stage = found, default_stage
        elif re.fullmatch(r'(?:Winner|Winners|Honou?r(?: Books?)?|Shortlist)', text.strip(), re.I):
          stage = parser.result_from_stage(text)
        elif node.name in ('h2', 'h3') and not parser.year_from_text(text):
          category = None
        continue
      if not category or not parser.category_matches(category):
        continue
      for pieces in paragraph_lines(node):
        line = ''.join(t for t, _ in pieces).strip()
        result, remainder = parser.stage_from_line(line)
        if result:
          stage = result
          line = remainder
        if stage not in ('winner', 'shortlisted') or not line or parser.is_non_entry_line(line):
          continue
        italic = ''.join(t for t, marked in pieces if marked).strip()
        # Some official paragraphs italicize the entire entry, including byline.
        title = parser.clean_title(italic)
        offset = line.find(italic) if italic else -1
        tail = line[offset + len(italic):].lstrip(' ,') if offset >= 0 else ''
        if title and tail and not re.search(r'\b(?:illustrated|text) by\b', title, re.I):
          title = line[:offset] + italic
          row = parser.build_row(year, category, title, tail, stage, url)
        else:
          row = parser.row_from_entry_text(year, category, line, stage, url)
        if row:
          rows.append(row)
  if not rows and blocks and blocks[0][2] is None and not details:
    return winner_card_rows(parser, main, blocks[0][1], url)
  return rows


def winner_card_rows(parser, main, year, url):
  rows, category = [], None
  codes = {'Older Readers': 'OR', 'Younger Readers': 'YR', 'Early Childhood': 'EC',
    'Picture Book': 'PB', 'Eve Pownall': 'EP', 'New Illustrator': 'NI'}
  for node in main.find_all(['h2', 'h3', 'p']):
    if node.name.startswith('h'):
      category = parser.category_from_text(node.get_text(' ', strip=True))
      continue
    if not category or not parser.category_matches(category) or not node.find(['b', 'strong']):
      continue
    widget = node.find_parent(attrs={'data-widget_type': 'text-editor.default'})
    if widget is None or widget.find('p') is not node:
      continue
    card = next((p for p in widget.parents if p.find('img') is not None), None)
    if card is None:
      continue
    marker = re.compile(rf'{year}_{codes[category]}_(winner|honour)', re.I)
    stages = [marker.search(img.get('src', '')) for img in card.find_all('img')]
    stages = [m[1].casefold() for m in stages if m]
    if len(stages) != 1:
      continue
    lines = [parser.clean_entry_text(''.join(t for t, _ in pieces)) for pieces in paragraph_lines(node)]
    lines = [line for line in lines if line]
    if len(lines) < 3:
      continue
    row = parser.build_row(year, category, lines[0], ' & '.join(lines[1:-1]),
      'winner' if stages[0] == 'winner' else 'shortlisted', url)
    if row:
      rows.append(row)
  return rows


def history_pdf_rows(parser, value, source_url):
  is_pdf = (isinstance(value, bytes) and value.startswith(b'%PDF-')) or (
    isinstance(value, str) and value.startswith('%PDF-'))
  if not is_pdf:
    return None
  try:
    from calibre.ebooks.pdf.pdftohtml import PDFTOHTML, PDFTOTEXT, creationflags
  except ImportError:
    return None
  data = value if isinstance(value, bytes) else value.encode('latin-1')
  with tempfile.TemporaryDirectory(prefix='list-switchboard-cbca-pdf-') as folder:
    pdf, out = Path(folder) / 'history.pdf', Path(folder) / 'history'
    pdf.write_bytes(data)
    if '/BookOfTheYear/' in source_url:
      result = subprocess.run([PDFTOTEXT, '-bbox', '-enc', 'UTF-8', str(pdf), '-'],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45, creationflags=creationflags)
      subprocess.run([PDFTOHTML, '-xml', '-i', str(pdf), str(out)], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45, creationflags=creationflags)
      return annual_xml_rows(parser, result.stdout.decode('utf-8'), source_url,
        out.with_suffix('.xml').read_text(encoding='utf-8'))
    subprocess.run([PDFTOHTML, '-xml', '-i', str(pdf), str(out)], check=True,
      stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45, creationflags=creationflags)
    xml = out.with_suffix('.xml').read_text(encoding='utf-8')
    return history_xml_rows(parser, xml, source_url)


def table_column_rows(lines, anchors, top_aligned=False, required=True):
  """Partition a PDF column into ISBN-owned cells without cutting wrapped text.

  Shortlist cells are vertically centred, winners top-aligned. Assigning each
  line to the nearest ISBN splits long titles at neighbouring row midpoints.
  A sequence partition instead compares each whole cell's alignment to its ISBN.
  """
  lines = sorted(lines)

  @lru_cache(None)
  def best(row, offset):
    if row == len(anchors):
      return (0, ()) if offset == len(lines) else None
    remaining = len(anchors) - row - 1 if required else 0
    first_end = offset + 1 if required else offset
    choices = []
    for end in range(first_end, len(lines) - remaining + 1):
      rest = best(row + 1, end)
      if rest is None:
        continue
      group = lines[offset:end]
      if group:
        first, last = group[0][0], group[-1][0]
        aligned = first if top_aligned else (first + last) / 2
        cost = (aligned - anchors[row]) ** 2 + .001 * (last - first) ** 2
        cost += sum(max(0, b[0] - a[0] - 15) ** 2 for a, b in zip(group, group[1:]))
      else:
        cost = 0
      choices.append((cost + rest[0], (tuple(t for _, t in group),) + rest[1]))
    return min(choices, key=lambda item: item[0]) if choices else None

  result = best(0, 0)
  if result is None:
    raise ValueError('Incomplete CBCA PDF table column.')
  return result[1]


def annual_xml_rows(parser, xml, source_url, layout_xml=None):
  """Read official 2022/2023 PDF tables by header columns and ISBN row anchors."""
  year = parser.year_from_text(source_url)
  if year not in (2022, 2023):
    raise ValueError('Unconfigured CBCA annual PDF table year.')
  winners = 'winner' in source_url.casefold()
  rows = []
  layouts = {p.get('number'): p for p in ET.fromstring(layout_xml).findall('page')} if layout_xml else {}
  root = ET.fromstring(xml)
  for page_index, page in enumerate((n for n in root.iter() if n.tag.rsplit('}', 1)[-1] == 'page'), 1):
    width = float(page.get('width', '892'))
    words = [n for n in page.iter() if n.tag.rsplit('}', 1)[-1] == 'word']
    cells = [(float(n.get('yMin', 0)), float(n.get('xMin', 0)), ''.join(n.itertext()).strip())
      for n in words] if words else [(float(n.get('top', 0)), float(n.get('left', 0)), ''.join(n.itertext()).strip())
      for n in page.findall('text') if ''.join(n.itertext()).strip()]
    line_cells = cells
    if words:
      lines = defaultdict(list)
      for y, x, t in cells:
        anchor = next((a for a in lines if abs(a - y) < 2), y)
        lines[anchor].append((x, t))
      line_cells = [(y, min(x for x, _ in line), ' '.join(t for _, t in sorted(line)))
        for y, line in lines.items()]
    for _, _, text in line_cells:
      declared = parser.year_from_text(text)
      if declared and 'book of the year' in text.casefold() and declared != year:
        raise ValueError('CBCA annual PDF heading disagrees with its configured year.')
    headings = sorted((y, parser.category_from_text(t)) for y, x, t in line_cells
      if parser.category_from_text(t) and ('Year' in t or 'Award' in t))
    for index, (start, category) in enumerate(headings):
      if not parser.category_matches(category):
        continue
      end = headings[index + 1][0] if index + 1 < len(headings) else float(page.get('height', '1188'))
      section = [(y, x, t) for y, x, t in cells if start < y < end]
      anchors = sorted({y for y, x, t in section if re.fullmatch(r'97[89][\d -]{10,16}', t)})
      headers = {t.casefold(): x for y, x, t in section
        if t.casefold() in ('author', 'illustrator', 'title', 'isbn', 'publisher') and anchors and y < anchors[0]}
      if winners:
        title_start = .30 if category == 'New Illustrator' else .34
        columns = [('creator', width * .11), ('title', width * title_start),
          ('publisher', width * .58), ('isbn', width * .77)]
      elif {'title', 'isbn', 'publisher'} <= set(headers) and ('author' in headers or 'illustrator' in headers):
        columns = sorted((label, x) for label, x in headers.items())
        columns.sort(key=lambda pair: pair[1])
      else:
        continue
      if winners and words:
        layout = layouts.get(str(page_index))
        if layout is None:
          raise ValueError('CBCA winner PDF needs table-column geometry.')
        scale = width / float(layout.get('width'))
        starts = []
        for n in layout.findall('text'):
          y, x = float(n.get('top')) * scale, float(n.get('left')) * scale
          if start < y < end and ''.join(n.itertext()).strip() and any(abs(y - a) < width * .035 for a in anchors):
            starts.append(x)
        inferred = []
        for label, lo, hi in (('creator', .07, .20), ('title', .25, .43), ('publisher', .50, .70), ('isbn', .72, .85)):
          candidates = [x for x in starts if lo * width < x < hi * width]
          if not candidates:
            raise ValueError('Missing CBCA winner PDF column.')
          inferred.append((label, min(candidates)))
        columns = inferred
      stages = [(y, parser.result_from_stage(t)) for y, _, t in line_cells if start < y < end
        if re.fullmatch(r'WINNER|HONOUR BOOKS?', t, re.I)]
      if not anchors:
        continue
      data_start = min((y for y, _ in stages), default=start) if winners else max(
        [start] + [y for y, _, t in section if t.casefold() in headers and y < anchors[0]])
      column_lines = {label: {} for label, _ in columns if label != 'isbn'}
      excluded = [y for y, _, t in line_cells if re.fullmatch(r'WINNER|HONOUR BOOKS?', t, re.I) or
        re.search(r'will be announced|Support us by purchasing|store\.cbca|Noon AEST', t, re.I)]
      for y, x, text in sorted(section):
        if y <= data_start or y < anchors[0] - width * .05 or y > anchors[-1] + width * .06:
          continue
        if any(abs(y - label_y) < 2 for label_y in excluded):
          continue
        candidates = [(label, cx) for label, cx in columns if cx <= x + width * .006]
        label = max(candidates, key=lambda pair: pair[1])[0] if candidates else None
        if label in column_lines:
          lines = column_lines[label]
          line_y = next((a for a in lines if abs(a - y) < 2), y)
          lines.setdefault(line_y, []).append((x, text))
      primary_creator = next(label for label, _ in columns if label in ('creator', 'author', 'illustrator'))
      values_by_column = {}
      for label, lines in column_lines.items():
        values_by_column[label] = table_column_rows(
          [(y, ' '.join(t for _, t in sorted(words))) for y, words in lines.items()], anchors,
          top_aligned=winners, required=label in ('title', 'publisher', primary_creator))
      for i, anchor in enumerate(anchors):
        result = 'shortlisted'
        if winners:
          prior = [(y, stage) for y, stage in stages if y < anchor]
          if not prior:
            continue
          result = max(prior)[1]
        values = {label: groups[i] for label, groups in values_by_column.items()}
        title = ' '.join(values['title'])
        if winners:
          author = ' '.join(values['creator'])
          # The official 2023 Taylor byline itself lacks its closing bracket.
          author = re.sub(r'\s*\((illus\.?\s*by|text by)\s+',
            lambda m: ', illustrated by ' if m[1].casefold().startswith('illus') else ', text by ',
            author, flags=re.I).rstrip(')')
        else:
          creators = [(label, ' '.join(values[label])) for label, _ in columns if label in ('author', 'illustrator')]
          author = ', '.join(text for _, text in creators if text)
        if not title or not author or not values['publisher']:
          raise ValueError(f'Incomplete CBCA {year} annual PDF book row: {category}.')
        row = parser.build_row(year, category, title, author, result, source_url)
        if row:
          rows.append(row)
  return rows


def creator_name(text):
  def surname(value):
    value = value.title()
    return re.sub(r'\bMc([a-z])', lambda m: 'Mc' + m[1].upper(), value)
  text = re.sub(r'\s*\((?:ed|comp)\.?\)\s*', ' ', text, flags=re.I).strip()
  text = re.sub(r'^([A-Z][A-Z\'-]+)\.\s+', r'\1, ', text)
  if ',' not in text:
    match = re.fullmatch(r'([A-Z][A-Z\'-]+)\s+([A-Z][a-z].+)', text)
    if match:
      return match[2] + ' ' + surname(match[1])
    return text
  names = []
  for part in re.split(r'\s*&\s*', text):
    if ',' in part:
      last, given = part.split(',', 1)
      names.append((given.strip() + ' ' + surname(last.strip())).strip())
    elif names and re.fullmatch(r'(?:[A-Z]\.?\s*){1,4}', part):
      names.append(part + ' ' + names[0].rsplit(' ', 1)[-1])
    else:
      names.append(part)
  return ' & '.join(names)


def history_xml_rows(parser, xml, source_url):
  root = ET.fromstring(xml)
  rows, category, year, stage, pending = [], None, None, None, None

  def flush():
    nonlocal pending
    if pending and not pending['title']:
      pair = parser.title_author_from_pdf_text(pending['author'])
      if pair:
        title, author = pair
        pending['title'], pending['author'] = [title], author
    if pending and pending['title'] and parser.category_matches(pending['category']):
      row = parser.build_row(pending['year'], pending['category'],
        ' '.join(pending['title']), creator_name(pending['author']), pending['stage'], source_url)
      if row:
        rows.append(row)
    pending = None

  for page in root.findall('page'):
    if int(page.get('number', '0')) == 1:
      continue
    lines = defaultdict(list)
    anchors = []
    for node in page.findall('text'):
      text = ''.join(node.itertext()).strip()
      top, left = int(node.get('top', '0')), int(node.get('left', '0'))
      if not text or top > int(page.get('height', '1188')) - 85:
        continue
      anchor = next((a for a in anchors if abs(a - top) <= 5), None)
      if anchor is None:
        anchor = top
        anchors.append(anchor)
      lines[anchor].append((left, text, node.find('i') is not None, node.find('b') is not None))
    for top in sorted(lines):
      cells = sorted(lines[top])
      heading = ' '.join(t for left, t, _, bold in cells if left < 160 and bold)
      found = parser.category_from_text(heading)
      if found or ('AWARD' in heading and not re.match(r'^\d{4}', heading)) or 'BOOK WEEK SLOGANS' in heading:
        flush()
        category, year, stage = found, None, None
        continue
      if not category:
        continue
      label = ' '.join(t for left, t, _, _ in cells if left < 160)
      match = re.match(r'^((?:19|20)\d{2})(?!\d)\s*[-\u2013\u2014]?\s*(.*)', label)
      if match:
        flush()
        year = int(match[1])
        stage = 'winner' if category == 'New Illustrator' else None
        label = match[2]
      result, _ = parser.pdf_stage_from_line(label)
      if re.match(r'^MEDALS?\b', label):
        result = 'winner'
      if result:
        flush()
        stage = result
      if not year or not stage:
        continue
      body = [(left, t, italic) for left, t, italic, _ in cells if 160 <= left < 650]
      if not body:
        continue
      first = body[0][1]
      creator = not body[0][2] and (',' in first or category == 'New Illustrator' or
        any(italic for _, _, italic in body[1:]) or first == 'VARIOUS AUTHORS' or
        re.match(r'^[A-Z][A-Z\'-]+\.\s', first))
      if creator and not re.match(r'^(?:Illus|Text|Note|by|No Award|No winner|Joint Winners)', first, re.I):
        flush()
        title_at = next((i for i, (_, _, italic) in enumerate(body) if italic), len(body))
        author = ' '.join(t for _, t, _ in body[:title_at])
        titles = [t for _, t, italic in body[title_at:] if italic]
        if author.endswith(',') and titles:
          # The source styles a given name as part of the title (2021 Wilkinson).
          given, _, rest = titles[0].partition(' ')
          author += ' ' + given
          titles[0] = rest
        pending = {'year': year, 'category': category, 'stage': stage,
          'author': author, 'title': titles}
      elif pending:
        pending['title'].extend(t for _, t, italic in body if italic and not re.match(r'^Illus', t, re.I))
  flush()
  return rows
