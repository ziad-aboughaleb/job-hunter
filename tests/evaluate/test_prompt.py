import json
import unittest

from jobhunter.evaluate.prompt import build_system_prompt, build_user_message
from jobhunter.helpers.config import DEFAULTS


class PromptTests(unittest.TestCase):
    def test_prompt_follows_the_config(self):
        cfg = json.loads(json.dumps(DEFAULTS))
        cfg["score_threshold"] = 70
        cfg["profile"]["target_roles"] = "DevOps and SRE work"
        cfg["scoring_weights"] = [{"name": "Cloud skills", "weight": 100, "what": "AWS and Kubernetes"}]
        prompt = build_system_prompt(cfg, "MY CV TEXT", "MY PREFS TEXT")
        for expected in ("DevOps and SRE work", "Cloud skills (100): AWS and Kubernetes", "below 70", "70-89", "50-69",
                         "MY CV TEXT", "MY PREFS TEXT"):
            self.assertIn(expected, prompt)
        self.assertLess(prompt.index("# Step 1"), prompt.index("MY CV TEXT"))  # rubric first, CV last (cache-friendly)

    def test_user_message_truncates_long_descriptions(self):
        message = build_user_message({"title": "T", "company": "C", "location": "L", "description": "x" * 5000}, 100)
        self.assertLess(len(message), 400)


if __name__ == "__main__":
    unittest.main()
