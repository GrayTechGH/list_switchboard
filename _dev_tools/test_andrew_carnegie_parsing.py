import copy
import unittest

from parser.andrew_carnegie import AndrewCarnegieOfficialParser


class AndrewCarnegieParsingTests(unittest.TestCase):

  def parse(self,html,year=2026):
    parser=AndrewCarnegieOfficialParser()
    return parser.parse(html,f'https://www.ala.org/carnegie-medals/{year}-winners',parser.AWARD_NAME)

  def test_old_author_first_nested_marks_and_winner_promotion(self):
    html='''<h2><strong>NONFICTION WINNER</strong></h2>
      <p><strong>Robert K. Massie</strong><br/><br/><strong><em>Catherine the Great: Portrait of a Woman</em></strong><br/>(Random House)</p>
      <h3><strong>NONFICTION FINALISTS</strong></h3><div class="columns-3"><div class="column">
      <p><strong>James Gleick<br/><br/><em><a href="https://www.booklistonline.com/information">The Information: A History, A Theory, A Flood</a></em></strong><br/>(Pantheon Books)</p>
      </div><div><p><strong>Robert K. Massie</strong><br/><em><a href="https://www.booklistonline.com/catherine">Catherine the Great: Portrait of a Woman</a></em><br/>(Random House)</p></div></div>'''
    entries=self.parse(html,2012)['entries']
    self.assertEqual([
      ('2012','Catherine the Great: Portrait of a Woman',['Robert K. Massie'],'winner'),
      ('2012.01','The Information: A History, A Theory, A Flood',['James Gleick'],'finalist'),
    ],[(e['position'],e['title'],e['authors'],e['result']) for e in entries])

  def test_italic_author_winner_and_title_first_finalist_ignore_reviews(self):
    html='''<h2>Nonfiction Winner</h2><p><em><strong>Rebecca Giggs</strong></em><br/>
      <em><strong>Fathoms: The World in the Whale</strong></em><br/><em>(Simon &amp; Schuster)</em></p>
      <p>Focusing on whales, Giggs examines history, science, and what we can save.</p>
      <h3>Nonfiction Finalists</h3><p><a href="https://www.booklistonline.com/fathoms"><em>Fathoms: The World in the Whale</em></a><br/>Rebecca Giggs<br/>(Simon &amp; Schuster)</p>
      <p><a href="https://www.booklistonline.com/just-us"><em>Just Us: An American Conversation</em></a> .<br/>Claudia Rankine<br/>(Graywolf Press)</p>
      <p><em>From the review:</em> Blending essays, memoir, and poetry, this is an essential, illuminating collection.</p>'''
    entries=self.parse(html,2021)['entries']
    self.assertEqual(['Fathoms: The World in the Whale','Just Us: An American Conversation'],[e['title'] for e in entries])
    self.assertEqual([['Rebecca Giggs'],['Claudia Rankine']],[e['authors'] for e in entries])
    self.assertEqual(['winner','finalist'],[e['result'] for e in entries])

  def test_modern_wrapped_fragments_unclosed_images_and_section_boundaries(self):
    html='''<div><h2>Fiction Winner</h2><p>Wrong Writer<br/><i>Wrong Fiction</i><br/>(Publisher)</p></div>
      <div><h2>Nonfiction Winner</h2><div><img src="cover.png"><div><html><body>
      <p><strong>Roxanna Asgarian</strong><br/><em>We Were Once a Family</em><br/>(Publisher)</p>
      <p>Investigating what happened in 2018 uncovered this devastating history.</p></body></html></div></div></div>
      <div><h2>Nonfiction Finalists</h2><div><img src="other.png"><div><html><body>
      <p><a href="https://www.booklistonline.com/displacement"><i>The Great Displacement</i></a><br/>Jake Bittle<br/>(Publisher)</p>
      <p>Weather patterns shape a future filled with displacements, hardships, and action.</p></body></html></div></div></div>
      <h2>Social Media Graphics</h2><p><em>Not a Book</em> by Graphic Writer (Publisher)</p>
      <h2>Nonfiction Longlist</h2><p><em>Excluded Longlist</em> by Other Writer (Publisher)</p>'''
    entries=self.parse(html,2024)['entries']
    self.assertEqual(['We Were Once a Family','The Great Displacement'],[e['title'] for e in entries])
    self.assertEqual([['Roxanna Asgarian'],['Jake Bittle']],[e['authors'] for e in entries])

  def test_split_title_links_keep_full_title_and_source_author(self):
    html='''<h3>Nonfiction Finalists</h3><p><strong>David Treuer</strong><br/>
      <em><a href="https://www.booklistonline.com/heartbeat">The</a> <a href="https://www.booklistonline.com/heartbeat">Heartbeat of Wounded Knee: Native America from 1890 to the Present</a></em><br/>(Riverhead Books)</p>'''
    entry=self.parse(html,2020)['entries'][0]
    self.assertEqual('The Heartbeat of Wounded Knee: Native America from 1890 to the Present',entry['title'])
    self.assertEqual(['David Treuer'],entry['authors'])

  def test_author_roles_coauthors_suffixes_and_unicode(self):
    html='''<meta charset="utf-8"><h2>Nonfiction Winner</h2>
      <p>Ed Yong<br/><em>An Immense World</em><br/>(Publisher)</p>
      <h2>Nonfiction Finalists</h2>
      <p><a href="https://www.booklistonline.com/baldwin"><em>Baldwin, Styron, and Me</em></a><br/>M\u00e9likah Abdelmoumen. Translated by Catherine Khordoc.<br/>(Biblioasis)</p>
      <p><a href="https://www.booklistonline.com/souls"><em>Four Hundred Souls</em></a><br/>Ibram X. Kendi and Keisha N. Blain<br/>(Publisher)</p>
      <p><a href="https://www.booklistonline.com/another"><em>Another Book (Volume Two)</em></a><br/>Writer,Jr.<br/>(Publisher)</p>'''
    entries=self.parse(html.encode('utf-8'))['entries']
    self.assertEqual([['Ed Yong'],['M\u00e9likah Abdelmoumen'],['Ibram X. Kendi','Keisha N. Blain'],['Writer,Jr.']],
      [e['authors'] for e in entries])
    self.assertEqual('Another Book (Volume Two)',entries[-1]['title'])

  def test_short_finalist_title_alias_retains_winner_and_distinct_books(self):
    p=AndrewCarnegieOfficialParser()
    rows=[{'award_year':'2015','category':'Nonfiction','source_url':'year','author':'Bryan Stevenson',
           'title':'Just Mercy: A Story of Justice and Redemption','result':'winner'},
          {'award_year':'2015','category':'Nonfiction','source_url':'book','author':'Bryan Stevenson',
           'title':'Just Mercy','result':'finalist'}]
    original=copy.deepcopy(rows);merged=p.dedupe_rows(rows)
    self.assertEqual(1,len(merged));self.assertEqual(['Just Mercy'],merged[0]['aliases'])
    self.assertEqual('year',merged[0]['source_url']);self.assertEqual(original,rows)
    rows.append(dict(rows[0],title='Just Mercy: Another Volume'))
    self.assertEqual(3,len(p.dedupe_rows(rows)))

  def test_no_medal_year_keeps_only_official_finalists(self):
    html='<h2>Nonfiction Winner</h2><p>No medal was awarded.</p><h3>Nonfiction Finalists</h3>'+''.join(
      f'<p><em>Finalist {n}</em> by Writer {n} (Publisher)</p>' for n in range(3))
    entries=self.parse(html,2018)['entries']
    self.assertEqual(['2018.01','2018.02','2018.03'],[e['position'] for e in entries])
    self.assertTrue(all(e['result']=='finalist' for e in entries))

  def test_inline_legacy_byline_and_navigation_exclusion(self):
    html='''<nav><h2>Nonfiction Winner</h2><p><em>Wrong Menu Book</em> by Wrong Writer (Publisher)</p></nav>
      <h2>Nonfiction Winner</h2><p><em>Winner Takes All: A Book</em> by Fred Anderson (Publisher)</p>
      <h2>Nonfiction Finalists</h2><p><em>Quoted Book</em> is an exploration of society, science, and humanity.</p>
      <p>A long review, with several commas, and no actual book byline.</p>'''
    entry=self.parse(html)['entries'][0]
    self.assertEqual('Winner Takes All: A Book',entry['title']);self.assertEqual(['Fred Anderson'],entry['authors'])
    self.assertEqual(1,len(self.parse(html)['entries']))
    linked=html.replace('<em>Winner Takes All: A Book</em>',
      '<a href="https://www.booklistonline.com/winner">Winner Takes All: A Book</a>')
    self.assertEqual(entry['title'],self.parse(linked)['entries'][0]['title'])


if __name__=='__main__':
  unittest.main()
