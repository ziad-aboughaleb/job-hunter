"""Shared test setup. Tests never touch the network: they replace jobhunter.http functions with fakes."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jobhunter.helpers import config


class ProjectCase(unittest.TestCase):
    """Gives each test its own empty project folder (JOBHUNTER_HOME) and cleans up afterwards."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        env = mock.patch.dict(os.environ, {"JOBHUNTER_HOME": str(self.root)})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self._tmp.cleanup)
        for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "LLM_API_KEY"):
            os.environ.pop(name, None)
        # Keep the test output clean. Tests that care can read self.out / self.err.
        self.out, self.err = io.StringIO(), io.StringIO()
        for stream, fake in (("sys.stdout", self.out), ("sys.stderr", self.err)):
            patcher = mock.patch(stream, fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    # -- helpers --
    def write_config(self, **overrides):
        """Write config.json containing only the given top-level settings (the rest use defaults)."""
        (self.root / "config.json").write_text(json.dumps(overrides), encoding="utf-8")
        return config.load_config(quiet=True)

    def write_file(self, name, text):
        (self.root / name).write_text(text, encoding="utf-8")

    def read_data(self, name):
        return json.loads((self.root / "data" / name).read_text(encoding="utf-8"))

    def write_data(self, name, obj):
        (self.root / "data").mkdir(exist_ok=True)
        (self.root / "data" / name).write_text(json.dumps(obj), encoding="utf-8")


def fake_get_text(routes):
    """A stand-in for http.get_text. `routes` maps a substring of the URL to the response text (or None for 404)."""
    def fake(url, *args, **kwargs):
        for fragment, response in routes.items():
            if fragment in url:
                return response
        return None
    return fake


LONG_CV = "Full-stack engineer with React, TypeScript and Node experience. " * 12  # > 400 characters
