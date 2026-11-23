import unittest

from parser.incremental import ParsedUnitCache


class ParsedUnitTests(unittest.TestCase):

  def cache(self):
    entries = [{'title': 'A'}, {'title': 'B'}]
    units = ParsedUnitCache('annual', 'source/category')
    units.put('2020', [entries[0]], 'r1')
    units.put('2021', [entries[1]], 'r2')
    return {'entries': entries, 'incremental_state': units.state(entries)}

  def test_reuse_after_sorted_storage_roundtrip_is_independent_copy(self):
    cache = self.cache()
    units = ParsedUnitCache('annual', 'source/category', cache, True)
    rows = units.reuse('2020', 'r1')
    self.assertEqual([{'title': 'A'}], rows)
    rows[0]['title'] = 'edited'
    self.assertEqual('A', cache['entries'][0]['title'])
    self.assertEqual([{'title': 'A'}], units.previous('2020'))

  def test_revision_source_strategy_and_legacy_cache_mismatch_force_fetch(self):
    for strategy, source, cache in [('different','source/category',self.cache()),
        ('annual','different',self.cache()),('annual','source/category',{'entries':[]})]:
      units = ParsedUnitCache(strategy, source, cache, True)
      self.assertIsNone(units.reuse('2020','r1'))
    units = ParsedUnitCache('annual','source/category',self.cache(),True)
    self.assertIsNone(units.reuse('2020','changed'))

  def test_invalid_unit_indexes_cannot_reuse_corrupt_cache(self):
    for indexes in ([12], [-1], [True], ['0']):
      cache = self.cache()
      cache['incremental_state']['units']['2020']['entry_indexes'] = indexes
      units = ParsedUnitCache('annual','source/category',cache,True)
      self.assertIsNone(units.reuse('2021','r2'))

  def test_failure_retains_rows_but_remains_pending(self):
    units = ParsedUnitCache('annual','source/category',self.cache(),True)
    rows = units.failed('2020','r1')
    cache = {'entries': rows, 'incremental_state': units.state(rows)}
    next_run = ParsedUnitCache('annual','source/category',cache,True)
    self.assertIsNone(next_run.reuse('2020','r1'))
    self.assertEqual(rows,next_run.previous('2020'))

  def test_unrepresented_entries_invalidate_whole_cache(self):
    cache = self.cache()
    cache['entries'].append({'title':'untracked'})
    self.assertIsNone(ParsedUnitCache('annual','source/category',cache,True).reuse('2020','r1'))

  def test_complete_empty_units_are_distinct_from_missing_units(self):
    units = ParsedUnitCache('annual','source/category')
    units.put('2020', [])
    cache={'entries': [], 'incremental_state': units.state([])}
    reused=ParsedUnitCache('annual','source/category',cache,True)
    self.assertEqual([],reused.reuse('2020'))
    self.assertIsNone(reused.reuse('missing'))

  def test_repositioned_rows_can_use_stable_identity_without_raw_duplicates(self):
    units=ParsedUnitCache('annual','source')
    units.put('year',[{'title':'A','position':'1'}])
    entries=[{'title':'A','position':'2'}]
    state=units.state(entries,identity=lambda e:e['title'])
    cache={'entries':entries,'incremental_state':state}
    self.assertEqual(entries,ParsedUnitCache('annual','source',cache,True).reuse('year'))
    ambiguous=units.state(entries+[{'title':'A','position':'3'}],identity=lambda e:e['title'])
    self.assertFalse(ambiguous['units']['year']['complete'])


if __name__ == '__main__':
  unittest.main()
