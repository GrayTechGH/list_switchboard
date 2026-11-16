"""User agents for legacy HTTP transports."""


def random_user_agent():
  """Generate an agent for this request; never retain a site or session identity."""
  from calibre.utils.random_ua import random_common_chrome_user_agent
  return random_common_chrome_user_agent()
