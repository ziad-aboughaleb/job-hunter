from pathlib import Path


def get_project_root() -> Path:
  """Returns the root directory of the project by searching for 'pyproject.toml'."""
  current_dir = Path(__file__).resolve().parent

  for directory in [current_dir, *current_dir.parents]:
    if (directory / "pyproject.toml").exists():
      return directory

  return Path.cwd()
