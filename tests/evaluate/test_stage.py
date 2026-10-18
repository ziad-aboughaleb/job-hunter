"""The scoring stage, with a fake model: no network, no API key needed."""
import json
import os
import unittest
from unittest import mock

from jobhunter.evaluate import stage as evaluate
from jobhunter.helpers import http
from tests.support import LONG_CV, ProjectCase

GOOD = {"hard_fail": "", "strengths": ["React + TS"], "gaps": ["GraphQL"], "score": 84, "pitch": "I build React apps."}


def reply(content, finish="stop"):
    """What an OpenAI-compatible server returns."""
    return {"choices": [{"finish_reason": finish, "message": {"content": content}}]}


class EvaluateRunTests(ProjectCase):
    def setUp(self):
        super().setUp()
        os.environ["LLM_API_KEY"] = "test-key"
        self.write_config(llm={"request_delay": 0})
        self.write_file("cv.md", LONG_CV)
        self.write_file("preferences.md", "Remote only.")
        self.jobs = [{"ref": f"J{i}", "uid": f"u{i}", "title": f"Dev {i}", "company": "Co", "location": "Remote",
                      "posted": "2026-10-01", "description": f"React role {i}"} for i in range(1, 4)]
        self.write_data("candidates.json", self.jobs)
        self.requests = []

    def run_with(self, handler, **kw):
        def fake_post(url, payload, **kwargs):
            self.requests.append(payload)
            return handler(url, payload)
        with mock.patch("jobhunter.helpers.http.post_json", fake_post), mock.patch("time.sleep"):
            return evaluate.run(**kw)

    def test_each_job_is_its_own_independent_request(self):
        code = self.run_with(lambda url, p: reply(json.dumps(GOOD)))
        self.assertEqual(code, 0)
        self.assertEqual(len(self.requests), 3)
        self.assertTrue(all(len(p["messages"]) == 2 for p in self.requests))  # system + one job, no history
        self.assertEqual([r["ref"] for r in self.read_data("results.json")], ["J1", "J2", "J3"])

    def test_retry_tells_the_model_what_was_wrong(self):
        replies = iter(["I cannot do that", json.dumps(GOOD)] * 3)
        self.run_with(lambda url, p: reply(next(replies)), limit=1)
        self.assertEqual(len(self.requests), 2)
        self.assertIn("previous reply was unusable", self.requests[1]["messages"][1]["content"])

    def test_truncated_output_doubles_the_token_budget(self):
        replies = iter([reply('{"hard_fail": "", "stre', "length"), reply(json.dumps(GOOD))])
        self.run_with(lambda url, p: next(replies), limit=1)
        self.assertGreater(self.requests[1]["max_tokens"], self.requests[0]["max_tokens"])
        self.assertEqual(len(self.read_data("results.json")), 1)

    def test_failed_jobs_are_skipped_and_reported(self):
        def handler(url, payload):
            return reply("garbage" if "Dev 2" in payload["messages"][1]["content"] else json.dumps(GOOD))
        self.assertEqual(self.run_with(handler), 1)
        self.assertEqual([r["ref"] for r in self.read_data("results.json")], ["J1", "J3"])

    def test_five_failures_in_a_row_stop_the_run(self):
        self.write_data("candidates.json", [dict(self.jobs[0], ref=f"J{i}") for i in range(1, 9)])
        self.run_with(lambda url, p: reply("garbage"))
        self.assertEqual(len(self.requests), 10)  # 5 jobs x (request + one retry), then it stops

    def test_json_schema_rejected_falls_back_to_json_mode(self):
        def handler(url, payload):
            if payload["response_format"]["type"] == "json_schema":
                raise http.HttpStatusError(400, "json_schema unsupported")
            return reply(json.dumps(GOOD))
        self.assertEqual(self.run_with(handler, limit=2), 0)
        self.assertEqual([p["response_format"]["type"] for p in self.requests], ["json_schema", "json_object", "json_object"])

    def test_wrong_key_stops_immediately(self):
        def handler(url, payload):
            raise http.HttpStatusError(401, "bad key")
        self.assertEqual(self.run_with(handler), 1)
        self.assertEqual(len(self.requests), 1)

    def test_missing_key_and_unreachable_server_stop_immediately(self):
        os.environ.pop("LLM_API_KEY")
        self.assertEqual(self.run_with(lambda u, p: reply("{}")), 1)
        self.assertEqual(len(self.requests), 0)
        os.environ["LLM_API_KEY"] = "k"

        def down(url, payload):
            raise http.NetworkError("connection refused")
        self.assertEqual(self.run_with(down), 1)

    def test_placeholder_cv_is_refused(self):
        self.write_file("cv.md", "<!-- paste your CV -->")
        self.assertEqual(self.run_with(lambda u, p: reply("{}")), 1)
        self.assertEqual(len(self.requests), 0)

    def test_previous_results_are_cleared_even_if_everything_fails(self):
        self.write_data("results.json", [{"ref": "J1", "score": 99}])
        self.run_with(lambda url, p: reply("garbage"))
        self.assertEqual(self.read_data("results.json"), [])

    def test_extra_body_is_passed_through(self):
        self.write_config(llm={"request_delay": 0, "extra_body": {"reasoning_effort": "low"}})
        self.run_with(lambda url, p: reply(json.dumps(GOOD)), limit=1)
        self.assertEqual(self.requests[0]["reasoning_effort"], "low")


if __name__ == "__main__":
    unittest.main()
