"""Run named regression modules and write recipe-specific verification receipts."""

import argparse
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
  p=argparse.ArgumentParser(description=__doc__)
  p.add_argument('--recipe',action='append',required=True)
  p.add_argument('--module',action='append',required=True)
  p.add_argument('--output',type=Path,required=True)
  args=p.parse_args()
  stream=io.StringIO()
  started=time.monotonic()
  with redirect_stdout(stream),redirect_stderr(stream):
    suite=unittest.defaultTestLoader.loadTestsFromNames(args.module)
    result=unittest.TextTestRunner(stream=stream,verbosity=1).run(suite)
  args.output.mkdir(parents=True,exist_ok=True)
  (args.output/'tests.log').write_text(stream.getvalue(),encoding='utf-8')
  for source_id in args.recipe:
    report={'kind':'automated','source_id':source_id,
      'passed':result.wasSuccessful() and result.testsRun>0,'tests':result.testsRun,
      'failures':len(result.failures),'errors':len(result.errors),'modules':args.module,
      'command':sys.argv,'elapsed_seconds':round(time.monotonic()-started,3),
      'log':str(args.output/'tests.log')}
    (args.output/f'{source_id}.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
  print(f'{result.testsRun} tests; failures={len(result.failures)}, errors={len(result.errors)}; receipts={args.output}')
  if not result.wasSuccessful():
    print(stream.getvalue())
  return 0 if result.wasSuccessful() else 1


if __name__=='__main__':
  raise SystemExit(main())
