import unittest

from errors import ImportCancelledError
from parser.source_fallback import SourceAttempt, SourceFallbackRunner


class IncrementalFallbackTests(unittest.TestCase):

  def test_existing_parser_receives_no_new_keywords(self):
    def parse(html,url,fetch_url=None,log=None,progress=None):
      return {'entries':[{'title':html}]}
    result=SourceFallbackRunner([SourceAttempt('old','url',parse)]).run(
      lambda u:'Old',cached_parsed={'entries':[]},incremental_update=True)
    self.assertEqual('Old',result['entries'][0]['title'])

  def test_opted_in_parser_receives_cache_without_mutating_shared_attempt(self):
    seen=[]
    def parse(html,url,**kwargs):
      seen.append(kwargs)
      return {'entries':[{'title':'A'}]}
    attempt=SourceAttempt('new','url',parse,supports_incremental=True)
    runner=SourceFallbackRunner([attempt])
    cache={'entries':[{'title':'old'}]}
    runner.run(lambda u:'payload',cached_parsed=cache,incremental_update=True)
    runner.run(lambda u:'payload')
    self.assertIs(cache,seen[0]['cached_parsed'])
    self.assertTrue(seen[0]['incremental_update'])
    self.assertIsNone(seen[1]['cached_parsed'])
    self.assertFalse(seen[1]['incremental_update'])
    self.assertEqual({},attempt.incremental_context)

  def test_fallback_transport_execute_signature_remains_compatible(self):
    class TransportAttempt(SourceAttempt):
      def execute(self,fetch_url,log=None,progress=None,before_fetch=None,
                  after_fetch=None,before_parse=None):
        return super().execute(fetch_url,log,progress,before_fetch,after_fetch,before_parse)
    seen=[]
    def failed(*args,**kwargs):
      raise ValueError('primary failed')
    def parse(html,url,**kwargs):
      seen.append(kwargs)
      return {'entries':[{'title':'fallback'}]}
    runner=SourceFallbackRunner([SourceAttempt('primary','first',failed),
      TransportAttempt('secondary','second',parse,source_rank=1,supports_incremental=True)])
    result=runner.run(lambda u:'payload',cached_parsed={'entries':[]},incremental_update=True)
    self.assertTrue(seen[0]['incremental_update'])
    self.assertTrue(result['notes'])

  def test_cancellation_is_not_an_incremental_fallback(self):
    seen=[]
    def fetch(url):
      seen.append(url)
      raise ImportCancelledError('stop')
    runner=SourceFallbackRunner([SourceAttempt('first','first',lambda *a,**k:{}),
      SourceAttempt('second','second',lambda *a,**k:{},source_rank=1,supports_incremental=True)])
    with self.assertRaises(ImportCancelledError):
      runner.run(fetch,incremental_update=True)
    self.assertEqual(['first'],seen)


if __name__ == '__main__':
  unittest.main()
