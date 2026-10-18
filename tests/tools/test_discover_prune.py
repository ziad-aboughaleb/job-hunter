import json
import unittest

from tests.support import ProjectCase


class PruneAndDiscoverTests(ProjectCase):
    def test_prune_removes_only_404_boards(self):
        from jobhunter.tools import prune
        self.write_config(companies={"greenhouse": ["gitlab", "Gone"], "lever": ["flaky"]})
        self.write_data("run_status.json", {"errors": ["greenhouse/Gone: board not found (404) - check the slug",
                                                       "lever/flaky: HTTP 500"]})
        prune.run(dry_run=True)
        self.assertEqual(json.loads((self.root / "config.json").read_text())["companies"]["greenhouse"], ["gitlab", "Gone"])
        prune.run()
        companies = json.loads((self.root / "config.json").read_text())["companies"]
        self.assertEqual((companies["greenhouse"], companies["lever"]), (["gitlab"], ["flaky"]))

    def test_discover_topics_come_from_your_titles(self):
        from jobhunter.tools import discover
        cfg = self.write_config(filters={"title_include": ["frontend", "front-end", "front end", "react", "engineer", "junior", "node.js"]})
        self.assertEqual(discover.topics_from_config(cfg), ["frontend", "react", "node.js"])
        self.assertEqual(discover.topics_from_config(cfg, max_topics=2), ["frontend", "react"])
        self.assertEqual(discover.company_from_url("workable", "https://apply.workable.com/acme-co/j/ABC"), "acme-co")
        self.assertIsNone(discover.company_from_url("workable", "https://apply.workable.com/j/ABC"))
        self.assertEqual(discover.company_from_url("recruitee", "https://good.recruitee.com/o/fe"), "good")


if __name__ == "__main__":
    unittest.main()
