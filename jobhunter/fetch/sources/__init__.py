"""Where jobs come from. One small module per website.

There are two kinds of source:

  COMPANY sources list one company's own job board. The function takes the company's name as it
  appears in its job-board URL and returns a list of Job objects, or None if no such board exists:

        def fetch(slug: str) -> Optional[List[Job]]

  BOARD sources are aggregators that list many companies at once. The function takes the options
  from config.json ("boards" section) and returns a list of Job objects:

        def fetch(options: dict) -> List[Job]

To add a website: write a module with a fetch() function like the ones here, then register it in
COMPANY_SOURCES or BOARD_SOURCES below. See docs/ARCHITECTURE.md for a step-by-step example.
"""
from jobhunter.fetch.sources import (arbeitnow, ashby, greenhouse, lever, personio, recruitee,
                               remoteok, remotive, workable)

COMPANY_SOURCES = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "lever_eu": lever.fetch_eu,
    "ashby": ashby.fetch,
    "recruitee": recruitee.fetch,
    "workable": workable.fetch,
    "personio": personio.fetch,
}

BOARD_SOURCES = {
    "remotive": remotive.fetch,
    "remoteok": remoteok.fetch,
    "arbeitnow": arbeitnow.fetch,
}
