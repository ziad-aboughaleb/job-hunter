import json
import unittest
from unittest import mock

from jobhunter.evaluate.llm import LLMClient, LLMUnavailable
from jobhunter.helpers import http
from jobhunter.helpers.config import DEFAULTS

GOOD = {"hard_fail": "", "strengths": ["React + TS"], "gaps": ["GraphQL"], "score": 84, "pitch": "I build React apps."}


class OllamaTests(unittest.TestCase):
    def test_think_option_is_dropped_if_the_model_rejects_it(self):
        cfg = dict(DEFAULTS["llm"], provider="ollama", base_url="http://localhost:11434", model="m", think=False)
        calls = []

        def fake_post(url, payload, **kwargs):
            calls.append(dict(payload))
            if "think" in payload:
                raise http.HttpStatusError(400, '"m" does not support thinking')
            return {"message": {"content": json.dumps(GOOD)}}
        client = LLMClient(cfg)
        with mock.patch("jobhunter.helpers.http.post_json", fake_post):
            client.complete("system", "user")
            client.complete("system", "user")
        self.assertEqual(["think" in c for c in calls], [True, False, False])

    def test_unreachable_ollama(self):
        client = LLMClient(dict(DEFAULTS["llm"], provider="ollama", base_url="http://localhost:1"))
        with mock.patch("jobhunter.helpers.http.post_json", side_effect=http.NetworkError("refused")):
            with self.assertRaises(LLMUnavailable):
                client.complete("s", "u")


if __name__ == "__main__":
    unittest.main()
