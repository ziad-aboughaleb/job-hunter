import json
import unittest
from unittest import mock

from jobhunter.fetch import stage as fetch
from jobhunter.helpers import store
from tests.support import ProjectCase, fake_get_text

GOOD_DESC = "We use React, TypeScript and Node."
GREENHOUSE = {"jobs": [
    {"id": 1, "title": "Frontend Developer", "absolute_url": "https://g/1", "location": {"name": "Remote - EMEA"}, "content": GOOD_DESC},
    {"id": 2, "title": "Senior Frontend Developer", "absolute_url": "https://g/2", "location": {"name": "Remote"}, "content": GOOD_DESC},
    {"id": 3, "title": "Frontend Developer", "absolute_url": "https://g/3", "location": {"name": "Remote - USA"}, "content": GOOD_DESC},
    {"id": 4, "title": "Accountant Developer", "absolute_url": "https://g/4", "location": {"name": "Remote"}, "content": "Excel"},
]}
REMOTIVE = {"jobs": [
    {"id": 10, "title": "Frontend Developer", "company_name": "Acme", "url": "https://r/10",
     "candidate_required_location": "Worldwide", "description": GOOD_DESC},   # same company+title as greenhouse job 1: a duplicate
    {"id": 11, "title": "Full Stack Developer", "company_name": "Beta", "url": "https://r/11",
     "candidate_required_location": "Worldwide", "description": GOOD_DESC},
]}

FILTERS = dict(title_include=["developer"], title_exclude=["senior"], stack_keywords=["react", "typescript", "node"],
               min_stack_hits=2, location_exclude_terms=["usa"], location_allow_terms=[])


class FetchTests(ProjectCase):
    def setUp(self):
        super().setUp()
        self.routes = {"boards-api.greenhouse.io/v1/boards/acme": json.dumps(GREENHOUSE),
                       "boards-api.greenhouse.io/v1/boards/ghost": None,
                       "remotive.com/api": json.dumps(REMOTIVE)}
        patcher = mock.patch("jobhunter.helpers.http.get_text", fake_get_text(self.routes))
        patcher.start()
        self.addCleanup(patcher.stop)

    def config(self, **extra):
        return self.write_config(companies={"greenhouse": ["acme", "Acme", "ghost"]},
                                 boards={"remotive": True, "remoteok": False}, filters=FILTERS, **extra)

    def test_full_run(self):
        self.config()
        self.assertEqual(fetch.run(), 0)
        candidates = self.read_data("candidates.json")
        self.assertEqual(sorted((c["company"], c["title"]) for c in candidates),
                         [("Acme", "Frontend Developer"), ("Beta", "Full Stack Developer")])  # duplicate removed
        self.assertEqual([c["ref"] for c in candidates], ["J1", "J2"])
        status = self.read_data("run_status.json")
        for reason, count in {"title_excluded": 1, "location_excluded": 1, "stack_mismatch": 1, "duplicate": 1}.items():
            self.assertEqual(status["dropped"].get(reason), count, reason)
        self.assertTrue(any("ghost" in e and "board not found" in e for e in status["errors"]))
        self.assertEqual((status["sources_total"], status["sources_ok"]), (3, 2))  # "Acme" counted once: case-insensitive

    def test_seen_jobs_are_skipped_unless_ignored(self):
        self.config()
        fetch.run()
        uid = self.read_data("candidates.json")[0]["uid"]
        store.save_seen({uid: store.today()}, 90)
        fetch.run()
        self.assertNotIn(uid, [c["uid"] for c in self.read_data("candidates.json")])
        fetch.run(ignore_seen=True)
        self.assertIn(uid, [c["uid"] for c in self.read_data("candidates.json")])

    def test_priority_company_survives_the_cap(self):
        self.write_config(companies={"greenhouse": ["acme"]}, boards={"remotive": True, "remoteok": False},
                          filters=dict(FILTERS, company_priority=["Beta"]), limits={"max_candidates_per_run": 0})
        fetch.run()
        candidates = self.read_data("candidates.json")
        self.assertEqual([c["company"] for c in candidates], ["Beta"])  # cap is 0 but the priority job stays
        self.assertTrue(candidates[0]["priority"])
        self.assertEqual(self.read_data("run_status.json")["deferred_over_cap"], 1)

    def test_no_boards_flag_skips_aggregators(self):
        self.config()
        fetch.run(no_boards=True)
        self.assertEqual({c["company"] for c in self.read_data("candidates.json")}, {"Acme"})

    def test_stale_results_are_removed_at_the_start(self):
        self.config()
        self.write_data("results.json", [{"ref": "J1", "score": 99}])
        fetch.run()
        self.assertFalse((self.root / "data" / "results.json").exists())

    def test_exit_code_2_when_every_source_fails(self):
        self.routes.clear()
        self.write_config(companies={"greenhouse": ["ghost"]}, boards={"remotive": False, "remoteok": False})
        self.assertEqual(fetch.run(), 2)

    def test_exit_code_2_when_nothing_is_configured(self):
        self.write_config(boards={"remotive": False, "remoteok": False, "arbeitnow": False})
        self.assertEqual(fetch.run(), 2)

    def test_unknown_source_names_are_reported_not_fatal(self):
        self.write_config(companies={"greenhous": ["acme"], "greenhouse": ["acme"]}, boards={"remotive": False, "remoteok": False}, filters=FILTERS)
        self.assertEqual(fetch.run(), 0)
        self.assertTrue(any("unknown company source 'greenhous'" in e for e in self.read_data("run_status.json")["errors"]))


if __name__ == "__main__":
    unittest.main()
