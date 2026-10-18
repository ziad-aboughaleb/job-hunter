"""One test that runs the whole thing the way the daily schedule does: `python -m jobhunter run`.

Only the network is faked: job sites, the AI API and Telegram. Everything else is the real code.
"""
import json
import os
import unittest
from unittest import mock

from jobhunter import cli
from jobhunter.helpers import store
from tests.support import LONG_CV, ProjectCase, fake_get_text

REMOTIVE = {"jobs": [
    {"id": 1, "title": "Junior Frontend Developer", "company_name": "Acme", "url": "https://r/1",
     "candidate_required_location": "Worldwide", "publication_date": "2026-10-15T00:00:00",
     "description": "<p>We use React, TypeScript and Node.</p>"},
    {"id": 2, "title": "Senior Backend Developer", "company_name": "Beta", "url": "https://r/2",
     "candidate_required_location": "Worldwide", "publication_date": "2026-10-15T00:00:00",
     "description": "React TypeScript Node"},
    {"id": 3, "title": "Full Stack Developer", "company_name": "Gamma", "url": "https://r/3",
     "candidate_required_location": "Worldwide", "publication_date": "2026-10-15T00:00:00",
     "description": "React TypeScript Node, US residents only."},
]}


class PipelineTest(ProjectCase):
    def test_fetch_evaluate_send_end_to_end(self):
        cli.main(["init", "--preset", "fullstack", "--level", "junior"])
        self.write_file("cv.md", LONG_CV)
        self.write_file("preferences.md", "Remote only, junior roles, based outside the US.")
        self.write_file(".env", "TELEGRAM_BOT_TOKEN=1:abc\nTELEGRAM_CHAT_ID=42\nLLM_API_KEY=key\n")
        cfg = json.loads((self.root / "config.json").read_text())
        cfg["boards"] = {"remotive": True, "remoteok": False, "arbeitnow": False}
        cfg["filters"]["max_age_days"] = 100000
        cfg["llm"]["request_delay"] = 0
        (self.root / "config.json").write_text(json.dumps(cfg))

        telegram_messages = []

        def fake_post(url, payload, **kwargs):
            if "api.telegram.org" in url:
                telegram_messages.append(payload["text"])
                return {"ok": True}
            title = payload["messages"][1]["content"]  # the AI API
            if "Junior Frontend" in title:
                answer = {"hard_fail": "", "strengths": ["React and TypeScript match"], "gaps": [], "score": 88, "pitch": "I build React apps."}
            else:
                answer = {"hard_fail": "US residents only", "strengths": [], "gaps": [], "score": 0, "pitch": ""}
            return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(answer)}}]}

        with mock.patch("jobhunter.helpers.http.get_text", fake_get_text({"remotive.com/api": json.dumps(REMOTIVE)})), \
                mock.patch("jobhunter.helpers.http.post_json", fake_post), mock.patch("time.sleep"):
            self.assertEqual(cli.main(["run"]), 0)

        # Job 2 was removed by the title filter (senior), so the AI only saw jobs 1 and 3.
        self.assertEqual([c["company"] for c in self.read_data("candidates.json")], ["Acme", "Gamma"])
        cards = [m for m in telegram_messages if "🟢" in m]
        self.assertEqual(len(cards), 1)
        self.assertIn("Junior Frontend Developer — Acme", cards[0])
        self.assertIn("88%", telegram_messages[-1] + cards[0])
        self.assertEqual(len(store.load_seen()), 2)  # both evaluated jobs are finished

        # A second run finds nothing new: no cards, just the quiet summary.
        telegram_messages.clear()
        with mock.patch("jobhunter.helpers.http.get_text", fake_get_text({"remotive.com/api": json.dumps(REMOTIVE)})), \
                mock.patch("jobhunter.helpers.http.post_json", fake_post), mock.patch("time.sleep"):
            self.assertEqual(cli.main(["run"]), 0)
        self.assertEqual([m for m in telegram_messages if "🟢" in m], [])
        self.assertIn("no new jobs passed the filters", telegram_messages[0])


if __name__ == "__main__":
    unittest.main()
