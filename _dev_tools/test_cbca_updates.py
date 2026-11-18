"""CBCA source contracts required before enabling per-category updates."""

import unittest
from html import escape

from errors import CamoufoxRequiredError, ImportCancelledError
from parser.cbca_book_of_the_year import (
  ARCHIVE_URL, AWARDS_URL, PDF_URL, ALL_CATEGORY_ALIASES,
  CBCABookOfTheYearParser, CATEGORY_OLDER_READERS, CATEGORY_YOUNGER_READERS,
  CATEGORY_EARLY_CHILDHOOD, CATEGORY_EVE_POWNALL, CATEGORY_NEW_ILLUSTRATOR,
  CATEGORY_PICTURE_BOOK,
)
from parser.cbca_sources import annual_xml_rows, creator_name, history_xml_rows, table_column_rows


def xml_page(records, number=2):
  nodes = []
  for top, left, text, style in records:
    text = escape(text)
    if style:
      text = f'<{style}>{text}</{style}>'
    nodes.append(f'<text top="{top}" left="{left}">{text}</text>')
  return f'<pdf2xml><page number="{number}" height="1188" width="892">'+''.join(nodes)+'</page></pdf2xml>'


class CBCASourceTests(unittest.TestCase):

  def parser(self, category=CATEGORY_OLDER_READERS):
    return CBCABookOfTheYearParser(category)

  def panel(self, content, year=2026):
    return f'<main><h1>CBCA Book of the Year Award through history</h1><details><summary><div>{year}</div></summary>{content}</details></main>'

  def test_archive_year_comes_from_summary_and_br_delimits_books(self):
    html = self.panel('<h3>Older Readers</h3><p><b>Winner |</b><i>Darkest Night, Brightest Star</i>, Barry Jonsberg (Allen &amp; Unwin)</p><p><b>Honour |</b><i>Golden</i>, Jade Timms (Text)<br><b>Shortlist |</b><i>Unhallowed Halls</i>, Lili Wilkinson (Publisher)</p>')
    rows = self.parser().html_rows(html, ARCHIVE_URL)
    self.assertEqual(['2026'] * 3, [r['award_year'] for r in rows])
    self.assertEqual(['Darkest Night, Brightest Star', 'Golden', 'Unhallowed Halls'], [r['title'] for r in rows])
    self.assertEqual(['winner', 'shortlisted', 'shortlisted'], [r['result'] for r in rows])
    self.assertEqual('Barry Jonsberg', rows[0]['author'])

  def test_archive_category_boundary_excludes_neighbouring_books(self):
    html = self.panel('<h3>Older Readers</h3><p>Winner | <i>Older Book</i>, Older Writer</p><h3>Younger Readers</h3><p>Winner | <i>Younger Book</i>, Younger Writer</p>')
    self.assertEqual(['Older Book'], [r['title'] for r in self.parser().html_rows(html, ARCHIVE_URL)])

  def test_plain_title_parenthetical_creator_and_publisher(self):
    html = self.panel('<h3>Picture Book of the Year</h3><p>Winner | Timeless (Kelly Canby, Fremantle Press)</p>')
    row = self.parser(CATEGORY_PICTURE_BOOK).html_rows(html, ARCHIVE_URL)[0]
    self.assertEqual(('Timeless', 'Kelly Canby'), (row['title'], row['author']))

  def test_split_italic_title_keeps_its_unitalic_first_letter(self):
    html = self.panel('<h3>Picture Book of the Year</h3><p>Shortlist | B<i>owerbird Blues</i>, Aura Parker (Scholastic)</p>')
    self.assertEqual('Bowerbird Blues', self.parser(CATEGORY_PICTURE_BOOK).html_rows(html, ARCHIVE_URL)[0]['title'])

  def test_by_inside_title_is_not_a_byline_separator(self):
    row = self.parser().row_from_entry_text(2024, CATEGORY_NEW_ILLUSTRATOR,
      'Raised by Moths, Michelle Conn, written by Charlie Archbold (MidnightSun)', 'shortlisted', ARCHIVE_URL)
    self.assertEqual('Raised by Moths', row['title'])
    self.assertEqual('Michelle Conn, written by Charlie Archbold', row['author'])

  def test_author_publisher_surname_and_suffix_survive(self):
    self.assertEqual('Eva Collins', self.parser().clean_author('Eva Collins'))
    self.assertEqual('Writer, Jr.', self.parser().clean_author('Writer, Jr.'))

  def test_entire_italic_entry_and_years_do_not_leak_between_panels(self):
    html = self.panel('<h3>Eve Pownall Award</h3><p>Winner | <i>Peculiar Parents, Stephanie Owen Reeder, illustrated by Ingrid Bartkowiak (NLA Publishing)</i></p>')
    row = self.parser(CATEGORY_EVE_POWNALL).html_rows(html, ARCHIVE_URL)[0]
    self.assertEqual('Peculiar Parents', row['title'])
    self.assertEqual('Stephanie Owen Reeder, illustrated by Ingrid Bartkowiak', row['author'])

  def test_annual_shortlist_uses_own_heading_year(self):
    html = '<title>2024 stale SEO</title><main><h1>2026 Book of the Year Awards - Shortlist</h1><h2>Older Readers</h2><p><i>One</i>, One Writer<br><i>Two</i>, Two Writer</p></main><footer>2029 winners</footer>'
    self.assertEqual(['2026', '2026'], [r['award_year'] for r in self.parser().html_rows(html, 'https://cbca.org.au/2025-shortlist/')])

  def test_winner_card_uses_bounded_image_result_and_excludes_synopsis(self):
    html = '<main><h1>2026 Book of the Year Awards - Winners</h1><h2>Book of the Year Award: Older Readers</h2><section><img src="/2026_OR_winner.png"><div data-widget_type="text-editor.default"><p><b>Book, With Comma<br></b>Writer Person<br><em>Publisher</em></p><p>What the judges thought:</p><p><i>Unrelated Work</i>, Different Author</p></div></section></main>'
    rows = self.parser().html_rows(html, 'https://cbca.org.au/2026-winners/')
    self.assertEqual([('Book, With Comma', 'Writer Person', 'winner')], [(r['title'], r['author'], r['result']) for r in rows])
    self.assertEqual([], self.parser().html_rows(html.replace('2026_OR_', '2025_OR_'), 'https://cbca.org.au/2026-winners/'))

  def test_pdf_fonts_separate_author_title_and_publisher(self):
    xml = xml_page([(100, 85, 'BOOK OF THE YEAR: OLDER READERS', 'b'),
      (140, 85, '1996 – WINNER', 'b'), (140, 247, 'JINKS, Catherine', ''),
      (136, 358, 'Pagan’s Vows', 'i'), (140, 679, 'Omnibus', '')])
    rows = history_xml_rows(self.parser(), xml, PDF_URL)
    self.assertEqual([('Pagan’s Vows', 'Catherine Jinks')], [(r['title'], r['author']) for r in rows])

  def test_pdf_wrapped_title_and_creator_survive(self):
    xml = xml_page([(100, 85, 'BOOK OF THE YEAR: OLDER READERS', 'b'),
      (140, 85, '1986 – WINNER', 'b'), (140, 247, 'SCOTT-MITCHELL, Clare (comp)', ''),
      (140, 466, 'Apples from', 'i'), (157, 247, 'Hurricane Street', 'i'),
      (157, 355, 'Illus. Louise Hogan', ''), (157, 679, 'Methuen', '')])
    row = history_xml_rows(self.parser(), xml, PDF_URL)[0]
    self.assertEqual('Apples from Hurricane Street', row['title'])
    self.assertEqual('Clare Scott-Mitchell', row['author'])

  def test_pdf_medal_is_a_winner_and_missing_comma_creator_is_readable(self):
    xml = xml_page([(100, 85, 'BOOK OF THE YEAR: YOUNGER READERS', 'b'),
      (140, 85, '1987 – MEDAL', 'b'), (140, 247, 'RODDA Emily', ''),
      (140, 345, 'Pigs Might Fly', 'i'), (140, 679, 'Angus & Robertson', '')])
    row = history_xml_rows(self.parser(CATEGORY_YOUNGER_READERS), xml, PDF_URL)[0]
    self.assertEqual(('Emily Rodda', 'winner'), (row['author'], row['result']))

  def test_pdf_other_award_sections_end_the_category(self):
    xml = xml_page([(100, 85, 'BOOK OF THE YEAR: YOUNGER READERS', 'b'),
      (140, 85, '2021 — WINNER', 'b'), (140, 247, 'GORDON, Kate', ''),
      (140, 351, 'Aster’s Good, Right Things', 'i'),
      (200, 85, 'VISUAL ARTS BOARD AWARDS 1974 - 1976', 'b'),
      (240, 85, '1974 – WINNER', 'b'), (240, 247, 'NILAND, Kilmeny', ''),
      (240, 598, 'Different Award', 'i')])
    self.assertEqual(['Aster’s Good, Right Things'], [r['title'] for r in history_xml_rows(self.parser(CATEGORY_YOUNGER_READERS), xml, PDF_URL)])

  def test_pdf_crichton_joint_winners_keep_both_works(self):
    xml = xml_page([(100, 85, 'THE CRICHTON AWARD FOR NEW ILLUSTRATOR 1988 — 2018', 'b'),
      (140, 85, '1995', ''), (140, 193, 'Joint Winners:', ''),
      (157, 193, 'Astri Baker', ''), (154, 267, 'I Wish I’d Gone to the Moon with Neil Armstrong', 'i'),
      (174, 193, 'Geoff Kelly', ''), (174, 269, 'Power and Glory', 'i')])
    rows = history_xml_rows(self.parser(CATEGORY_NEW_ILLUSTRATOR), xml, PDF_URL)
    self.assertEqual(['Astri Baker', 'Geoff Kelly'], [r['author'] for r in rows])
    self.assertEqual(['winner', 'winner'], [r['result'] for r in rows])

  def test_pdf_contents_page_and_nonentry_years_do_not_create_books(self):
    xml = xml_page([(100, 85, 'BOOK OF THE YEAR: OLDER READERS', 'b'),
      (140, 85, '2021 — WINNER', 'b'), (140, 247, 'WRITER, Person', ''),
      (140, 351, 'Contents entry', 'i')], number=1)
    self.assertEqual([], history_xml_rows(self.parser(), xml, PDF_URL))

  def test_middle_readers_does_not_inherit_pre_2027_category_rows(self):
    html = self.panel('<h3>Older Readers</h3><p>Winner | <i>Book</i>, Writer Person</p>')
    self.assertEqual([], self.parser('Middle Readers').html_rows(html, ARCHIVE_URL))

  def test_critical_fetch_errors_propagate_at_pdf_and_awards_boundaries(self):
    archive = '<main><a href="'+PDF_URL+'">PDF of all prior winners</a></main>'
    for error in (ImportCancelledError, CamoufoxRequiredError):
      for boundary in (PDF_URL, AWARDS_URL):
        def fetch(url):
          if url == boundary:
            raise error('stop')
          return ''
        with self.subTest(error=error, boundary=boundary), self.assertRaises(error):
          self.parser().parse(archive, fetch_url=fetch)

  def annual_table(self, winner=False, missing_publisher=False, year=2023):
    heading = f'{year} CBCA Book of the Year '+('Award Winners' if winner else 'Shortlist')
    words = [(20, 30, heading), (100, 40, 'Book of the Year: Older Readers')]
    if winner:
      words += [(150, 280, 'WINNER'), (180, 69, 'Tom'), (180, 90, 'Taylor'),
        (180, 120, '(illus.'), (180, 150, 'by'), (180, 170, 'Jon'),
        (194, 69, 'Sommariva'), (180, 205, 'Neverlanders'), (180, 460, '9781761049071')]
      if not missing_publisher:
        words += [(180, 347, 'Publisher')]
      layout = xml_page([(270, 103, 'Tom Taylor (illus. by Jon', ''),
        (270, 308, 'Neverlanders', ''), (270, 520, 'Publisher', ''),
        (270, 690, '9781761049071', '')])
    else:
      words += [(150, 59, 'Author'), (150, 151, 'Illustrator'), (150, 223, 'Title'),
        (150, 348, 'ISBN'), (150, 440, 'Publisher'),
        (180, 59, 'Eva'), (180, 80, 'Collins'), (180, 223, 'Ask'),
        (180, 240, 'No'), (180, 255, 'Questions'), (180, 348, '9781922571342')]
      if not missing_publisher:
        words += [(180, 440, 'Publisher')]
      layout = None
    nodes = ''.join(f'<word xMin="{x}" yMin="{y}">{escape(text)}</word>' for y, x, text in words)
    bbox = f'<html><body><doc><page width="595" height="792">{nodes}</page></doc></body></html>'
    if layout:
      layout = layout.replace('number="2"', 'number="1"')
    return bbox, layout

  def test_annual_pdf_header_columns_keep_collins_and_title_separate(self):
    bbox, layout = self.annual_table()
    rows = annual_xml_rows(self.parser(), bbox,
      'https://cbca.blob.core.windows.net/documents/BookOfTheYear/2023/2023_CBCA_Shortlist_List.pdf', layout)
    self.assertEqual([('Ask No Questions', 'Eva Collins', 'shortlisted')],
      [(r['title'], r['author'], r['result']) for r in rows])

  def test_annual_winner_geometry_and_unclosed_illustrator_credit(self):
    bbox, layout = self.annual_table(winner=True)
    rows = annual_xml_rows(self.parser(), bbox,
      'https://cbca.blob.core.windows.net/documents/BookOfTheYear/2023/2023_CBCA-WinnersList.pdf', layout)
    self.assertEqual([('Neverlanders', 'Tom Taylor, illustrated by Jon Sommariva', 'winner')],
      [(r['title'], r['author'], r['result']) for r in rows])

  def test_annual_pdf_rejects_partial_metadata_and_wrong_year(self):
    url = 'https://cbca.blob.core.windows.net/documents/BookOfTheYear/2023/2023_CBCA_Shortlist_List.pdf'
    for options in ({'missing_publisher': True}, {'year': 2022}):
      with self.subTest(options=options), self.assertRaises(ValueError):
        bbox, layout = self.annual_table(**options)
        annual_xml_rows(self.parser(), bbox, url, layout)

  def test_image_only_annual_pdf_has_no_certifiable_rows(self):
    self.assertEqual([], annual_xml_rows(self.parser(), '<pdf2xml><page number="1"/></pdf2xml>',
      'https://cbca.blob.core.windows.net/documents/BookOfTheYear/2022/2022%20CBCA%20Shortlist_full.pdf'))

  def test_byline_suffix_and_pdf_shared_surnames(self):
    self.assertEqual(('A Book', 'Alice Writer, Jr.'), self.parser().title_author_from_html_text('A Book by Alice Writer, Jr.'))
    self.assertEqual('J.H. Martin & W.D. Martin', creator_name('MARTIN, J.H. & W.D.'))
    self.assertEqual('Anna McKinnon', creator_name('McKINNON, Anna'))

  def test_annual_discovery_accepts_current_winner_slug_and_plural_awards(self):
    html = '<main><a href="/2026-winners/">2026 Book of the Year Award – Winners</a><a href="/2025-book-of-the-year-award-winners/">2025 Book of the Year Awards – Winners</a><a href="/2026-shortlist/">2026 Shortlist</a></main>'
    self.assertEqual(('https://cbca.org.au/2026-winners/',
      'https://cbca.org.au/2025-book-of-the-year-award-winners/',
      'https://cbca.org.au/2026-shortlist/'), self.parser().annual_links(html, AWARDS_URL))

  def test_annual_discovery_excludes_other_hosts_pdfs_and_notables(self):
    html = '<a href="https://example.org/2026-winners/">2026 Winners</a><a href="https://awards.cbca.org.au/2026-shortlist/">2026 Shortlist</a><a href="/2026-notables/">2026 Notables</a><a href="/2026-winners.pdf">2026 Winners PDF</a>'
    self.assertEqual((), self.parser().annual_links(html, AWARDS_URL))

  def test_archive_panels_do_not_take_years_from_navigation_or_footer(self):
    html = '<nav>2029</nav>'+self.panel('<h3>Older Readers</h3><p>Winner | <i>Current Book</i>, Current Writer</p>')
    html = html.replace('</main>', '<details><summary>2025</summary><h3>Older Readers</h3><p>Winner | <i>Older Book</i>, Older Writer</p></details></main>')+'<footer>2030</footer>'
    rows = self.parser().html_rows(html, ARCHIVE_URL)
    self.assertEqual([('2026', 'Current Book'), ('2025', 'Older Book')],
      [(r['award_year'], r['title']) for r in rows])

  def test_2025_shortlist_introduction_paragraphs_bound_category_lists(self):
    html = '<main><h1>2025 Book of the Year Awards – Shortlist</h1><p>Presenting the 2025 CBCA Book of the Year Awards Older Readers Shortlist …</p><ul><li><b><i>A Wreck of Seabirds </i></b>by Karleah Olson (Fremantle Press)</li></ul><p>Presenting the 2025 CBCA Book of the Year Awards Younger Readers Shortlist …</p><ul><li><i>Other Book </i>by Another Author</li></ul></main>'
    rows = self.parser().html_rows(html, 'https://cbca.org.au/2025-shortlist/')
    self.assertEqual([('A Wreck of Seabirds', 'Karleah Olson')], [(r['title'], r['author']) for r in rows])

  def test_centred_pdf_cells_keep_four_line_title_inside_one_book(self):
    lines = [(261, 'A Is for Australian Reefs'), (289, 'Amazing Animal Journeys'),
      (309, 'Come Together: Things'), (322, 'Every Aussie Kid Should'),
      (335, 'Know about the First'), (349, 'Peoples'), (362, 'DEEP: Delve into Hidden'),
      (376, 'Worlds'), (396, 'Opal and Dart'), (417, 'Wild Australian Life')]
    rows = table_column_rows(lines, [261, 289, 329, 369, 396, 417])
    self.assertEqual(('Amazing Animal Journeys',), rows[1])
    self.assertEqual(('Come Together: Things', 'Every Aussie Kid Should', 'Know about the First', 'Peoples'), rows[2])
    self.assertEqual(('DEEP: Delve into Hidden', 'Worlds'), rows[3])

  def test_top_aligned_pdf_cells_keep_final_title_line_out_of_next_book(self):
    rows = table_column_rows([(325, 'DEEP'), (362, 'Come Together'),
      (376, 'Aussie Kid Should Know about'), (390, 'the First Peoples'),
      (405, 'Wild Australian Life')], [325, 362, 405], top_aligned=True)
    self.assertEqual(('Come Together', 'Aussie Kid Should Know about', 'the First Peoples'), rows[1])
    self.assertEqual(('Wild Australian Life',), rows[2])


if __name__ == '__main__':
  unittest.main()
