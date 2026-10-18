import json
import os
import unittest

from jobhunter.helpers import config
from tests.support import ProjectCase


class ConfigTests(ProjectCase):
    def test_missing_settings_use_defaults(self):
        cfg = self.write_config(score_threshold=60)
        self.assertEqual(cfg["score_threshold"], 60)
        self.assertEqual(cfg["limits"]["max_messages"], 15)

    def test_typos_are_reported(self):
        self.write_file("config.json", json.dumps({"filters": {"titel_include": ["x"]}, "scor_threshold": 5}))
        config.load_config()
        self.assertIn("filters.titel_include", self.err.getvalue())
        self.assertIn("scor_threshold", self.err.getvalue())

    def test_notes_and_free_form_sections_are_not_flagged(self):
        self.write_file("config.json", json.dumps({"_help": "note", "llm": {"extra_body": {"anything": 1}},
                                                   "boards": {"newboard": True}}))
        config.load_config()
        self.assertEqual(self.err.getvalue(), "")

    def test_mistakes_are_warned_about(self):
        cfg = self.write_config(scoring_weights=[{"name": "a", "weight": 60, "what": "x"}],
                                filters={"min_stack_hits": 2, "stack_keywords": []})
        problems = " | ".join(config.validate(cfg))
        self.assertIn("add up to 60", problems)
        self.assertIn("no job can pass", problems)

    def test_boards_can_be_true_false_or_objects(self):
        self.assertEqual(config.board_options(True), {"enabled": True})
        self.assertEqual(config.board_options(False), {"enabled": False})
        self.assertEqual(config.board_options({"category": "devops"}), {"category": "devops", "enabled": True})

    def test_invalid_json_is_a_clear_error(self):
        self.write_file("config.json", "{ not json")
        with self.assertRaises(SystemExit):
            config.load_config()

    def test_env_file_is_loaded_but_real_environment_wins(self):
        self.write_file(".env", "TEST_A=from_file\nTEST_B=from_file\n# comment\n")
        os.environ["TEST_B"] = "from_env"
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in ("TEST_A", "TEST_B")])
        config.load_env()
        self.assertEqual((os.environ["TEST_A"], os.environ["TEST_B"]), ("from_file", "from_env"))


if __name__ == "__main__":
    unittest.main()
