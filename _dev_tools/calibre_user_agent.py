"""Generate Calibre agents for dev tools running outside Calibre's Python."""

import subprocess


def random_user_agent():
  try:
    from calibre.utils.random_ua import random_common_chrome_user_agent
  except ImportError:
    return subprocess.check_output([
      'calibre-debug', '-c',
      'from calibre.utils.random_ua import random_common_chrome_user_agent; '
      'print(random_common_chrome_user_agent())',
    ], text=True).strip()
  return random_common_chrome_user_agent()
