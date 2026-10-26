from jobhunter.sources import SOURCES


def run_discovery():
  for name, source in SOURCES.items():
    print(f"Searching for companies using {name} on domains: {source.domains}")
