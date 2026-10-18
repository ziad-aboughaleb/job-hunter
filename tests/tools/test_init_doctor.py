import json
import os
import unittest

from jobhunter import cli
from jobhunter.fetch import stage as fetch_stage
from jobhunter.helpers import config
from jobhunter.tools import init_project
from tests.support import ProjectCase


class InitTests(ProjectCase):
    def test_init_creates_files_from_preset_and_level(self):
        self.assertEqual(cli.main(["init", "--preset", "backend", "--level", "junior"]), 0)
        for name in ("config.json", "cv.md", "preferences.md", ".env"):
            self.assertTrue((self.root / name).exists(), name)
        cfg = json.loads((self.root / "config.json").read_text())
        self.assertIn("backend", cfg["filters"]["title_include"])
        self.assertIn("intern", cfg["filters"]["title_include"])
        self.assertIn("senior", cfg["filters"]["title_exclude"])
        self.assertIn("recruiter", cfg["filters"]["title_exclude"])  # from the base template
        self.assertIn("postgresql", cfg["filters"]["stack_keywords"])
        self.assertIn("backend", cfg["profile"]["target_roles"])

    def test_init_never_overwrites_without_force(self):
        self.write_file("cv.md", "my real cv")
        cli.main(["init"])
        self.assertEqual((self.root / "cv.md").read_text(), "my real cv")
        cli.main(["init", "--force"])
        self.assertNotEqual((self.root / "cv.md").read_text(), "my real cv")

    def test_unknown_preset_is_rejected(self):
        self.assertEqual(cli.main(["init", "--preset", "nope"]), 1)

    def test_every_preset_produces_a_valid_config(self):
        for preset in init_project.available_presets():
            cfg = init_project.build_initial_config(preset, "mid")
            merged = config.deep_merge(config.DEFAULTS, cfg)
            self.assertEqual(config.validate(merged), [], preset)
            targets, problems = fetch_stage.build_targets(merged)
            self.assertEqual(problems, [], preset)

    def test_doctor_flags_placeholders_then_passes(self):
        cli.main(["init", "--preset", "frontend"])
        self.assertEqual(cli.main(["doctor"]), 1)
        self.write_file("cv.md", "React developer. " * 40)
        self.write_file("preferences.md", "Remote, junior roles.")
        self.write_file(".env", "TELEGRAM_BOT_TOKEN=1:a\nTELEGRAM_CHAT_ID=2\nLLM_API_KEY=k\n")
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "LLM_API_KEY")])
        self.assertEqual(cli.main(["doctor"]), 0)


if __name__ == "__main__":
    unittest.main()
