"""The send stage, with a fake Telegram. The important thing to protect is what gets marked as 'seen'."""
import json
import os
import unittest
from unittest import mock

from jobhunter.helpers import store
from jobhunter.send import matches, stage as deliver, telegram
from tests.support import ProjectCase


def candidate(i, **kw):
    return dict({"ref": f"J{i}", "uid": f"uid{i}", "title": f"Job {i}", "company": "Co", "url": f"https://x/{i}",
                 "location": "Remote", "posted": "2026-10-10", "priority": False}, **kw)


def result(i, score, hard_fail=None):
    return {"ref": f"J{i}", "score": score, "hard_fail": hard_fail, "strengths": ["s"], "gaps": [], "pitch": "p"}


class DeliverTests(ProjectCase):
    def setUp(self):
        super().setUp()
        os.environ.update(TELEGRAM_BOT_TOKEN="123:token", TELEGRAM_CHAT_ID="42")
        self.write_config(score_threshold=75, limits={"max_messages": 2})
        self.sent = []
        self.fail_for = set()

        def fake_send(token, chat_id, text, preview=False):
            self.sent.append(text)
            return (False, "HTTP 500") if any(marker in text for marker in self.fail_for) else (True, "")
        for target, replacement in (("jobhunter.send.telegram.send_message", fake_send), ("time.sleep", None)):
            patcher = mock.patch(target, replacement) if replacement else mock.patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.write_data("run_status.json", {"fetched": 100, "sources_ok": 5, "sources_total": 6, "errors": []})

    def seen(self):
        return store.load_seen()

    def test_matches_are_sent_and_everything_evaluated_is_marked_seen(self):
        self.write_data("candidates.json", [candidate(1), candidate(2), candidate(3)])
        self.write_data("results.json", [result(1, 90), result(2, 50), result(3, 0, "US only")])
        self.assertEqual(deliver.run(), 0)
        cards = [t for t in self.sent if "🟢" in t]
        self.assertEqual(len(cards), 1)
        self.assertIn("Match Score:</b> 90%", cards[0])
        self.assertEqual(set(self.seen()), {"uid1", "uid2", "uid3"})
        self.assertIn("matches ≥75%: 1", self.sent[-1])

    def test_unevaluated_jobs_are_not_marked_seen_and_are_reported(self):
        self.write_data("candidates.json", [candidate(1), candidate(2)])
        self.write_data("results.json", [result(1, 40)])
        self.assertEqual(deliver.run(), 1)
        self.assertEqual(set(self.seen()), {"uid1"})
        self.assertIn("not evaluated: J2", self.sent[-1])

    def test_a_failed_send_keeps_the_match_unseen_for_next_time(self):
        self.write_data("candidates.json", [candidate(1), candidate(2)])
        self.write_data("results.json", [result(1, 90), result(2, 85)])
        self.fail_for = {"Job 2"}
        self.assertEqual(deliver.run(), 1)
        self.assertEqual(set(self.seen()), {"uid1"})

    def test_message_cap_holds_extra_matches_back(self):
        self.write_data("candidates.json", [candidate(i) for i in range(1, 5)])
        self.write_data("results.json", [result(1, 80), result(2, 95), result(3, 85), result(4, 76)])
        deliver.run()
        cards = [t for t in self.sent if "🟢" in t]
        self.assertEqual(len(cards), 2)  # cap is 2: the two best (95 and 85)
        self.assertIn("95%", cards[0])
        self.assertEqual(set(self.seen()), {"uid2", "uid3"})  # the held-back matches stay unseen
        self.assertIn("2 more match", self.sent[-1])

    def test_dry_run_sends_nothing_and_saves_nothing(self):
        self.write_data("candidates.json", [candidate(1)])
        self.write_data("results.json", [result(1, 90)])
        self.assertEqual(deliver.run(dry_run=True), 0)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.seen(), {})
        self.assertIn("Job 1", self.out.getvalue())

    def test_invalid_results_are_reported_and_never_trusted(self):
        self.write_data("candidates.json", [candidate(1)])
        self.write_data("results.json", [{"ref": "J99", "score": 99}, {"ref": "J1", "score": "high"}])
        results, problems = matches.load_results([candidate(1)])
        self.assertEqual(results, {})
        self.assertEqual(len(problems), 3)  # unknown ref, bad score, J1 not evaluated

    def test_check_mode_validates_without_sending(self):
        self.write_data("candidates.json", [candidate(1)])
        self.write_data("results.json", [result(1, 90)])
        self.assertEqual(deliver.run(check_only=True), 0)
        self.assertEqual(self.sent, [])

    def test_missing_results_file_is_an_alert(self):
        self.write_data("candidates.json", [candidate(1)])
        self.assertEqual(deliver.run(), 1)
        self.assertIn("results.json does not exist", self.sent[-1])

    def test_no_candidates_sends_a_quiet_message(self):
        self.write_data("candidates.json", [])
        self.write_data("run_status.json", {"fetched": 10, "sources_ok": 1, "sources_total": 2, "errors": ["a/b: boom"]})
        self.assertEqual(deliver.run(), 0)
        self.assertIn("no new jobs passed the filters", self.sent[0])
        self.assertIn("1 source(s) failed", self.sent[0])

    def test_missing_candidates_means_the_fetch_stage_failed(self):
        self.assertEqual(deliver.run(), 1)
        self.assertIn("did not run or crashed", self.sent[0])

    def test_missing_credentials(self):
        os.environ.pop("TELEGRAM_BOT_TOKEN")
        self.assertEqual(deliver.run(), 1)
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
