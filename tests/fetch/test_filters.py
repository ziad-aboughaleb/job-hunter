import unittest
from datetime import datetime, timedelta, timezone

from jobhunter.helpers.config import DEFAULTS, deep_merge
from jobhunter.fetch.filters import JobFilter
from jobhunter.helpers.models import Job

NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)


def make_filter(**overrides):
    return JobFilter(deep_merge(DEFAULTS["filters"], overrides), now=NOW)


def job(title="Frontend Developer", location="Remote", description="React TypeScript Node", company="Acme", **kw):
    return Job(source="test", board="t", company=company, title=title, url="https://x", location=location,
               description=description, **kw)


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.f = make_filter(
            title_include=["frontend", "full-stack", "developer", "engineer"],
            title_exclude=["senior", "java", "ios", "ii"],
            stack_keywords=["react", "typescript", "node"], min_stack_hits=2,
            location_exclude_terms=["us", "usa", "germany", "uk"], location_allow_terms=["worldwide", "egypt"],
        )

    def reason(self, **kw):
        return self.f.reject_reason(job(**kw))

    def test_a_good_job_passes(self):
        self.assertIsNone(self.reason())

    def test_title_include_and_exclude(self):
        self.assertEqual(self.reason(title="Office Manager"), "title_no_match")
        self.assertEqual(self.reason(title="Senior Frontend Developer"), "title_excluded")
        self.assertEqual(self.reason(title="Java Developer"), "title_excluded")
        self.assertIsNone(self.reason(title="Frontend Developer (JavaScript)"))  # "java" must not match "JavaScript"
        self.assertEqual(self.reason(title="Software Engineer II"), "title_excluded")

    def test_remote_rule(self):
        self.assertEqual(self.reason(location="Berlin"), "not_remote")
        self.assertIsNone(self.reason(location="Berlin", remote=True))
        self.assertIsNone(self.reason(location="", description="This role is remote. React TypeScript"))
        self.f.f["require_remote"] = False
        self.assertIsNone(self.reason(location="Berlin"))

    def test_location_exclude_and_allow(self):
        self.assertEqual(self.reason(location="Remote - USA"), "location_excluded")
        self.assertEqual(self.reason(location="Remote, US"), "location_excluded")
        self.assertIsNone(self.reason(location="Remote - US or Worldwide"))  # an allow word rescues it
        self.assertIsNone(self.reason(location="Remote - Lusaka"))  # whole words: "usa" is not in "Lusaka"
        self.assertIsNone(self.reason(location="Remote - Ukraine"))

    def test_location_require_terms(self):
        self.f.f["location_require_terms"] = ["cairo", "egypt"]
        self.assertEqual(self.reason(location="Remote - Berlin"), "location_missing")
        self.assertIsNone(self.reason(location="Remote - Cairo"))

    def test_age(self):
        old = NOW - timedelta(days=30)
        self.assertEqual(self.reason(posted=old), "too_old")
        self.assertIsNone(self.reason(posted=NOW - timedelta(days=2)))
        self.assertIsNone(self.reason(posted=None))  # no date: keep

    def test_stack_rule(self):
        self.assertEqual(self.reason(description="Only React here"), "stack_mismatch")
        self.assertIsNone(self.reason(description="React and Node"))

    def test_company_rules(self):
        self.f.f["company_exclude"] = ["RecruitCo"]
        self.assertEqual(self.reason(company="Recruit-Co Ltd"), "company_excluded")

    def test_priority_company_skips_only_the_stack_rule(self):
        self.f.f["company_priority"] = ["acme"]
        j = job(description="no keywords at all")
        self.assertIsNone(self.f.reject_reason(j))
        self.assertTrue(j.priority)
        self.assertEqual(self.reason(title="Office Manager"), "title_no_match")  # other rules still apply


if __name__ == "__main__":
    unittest.main()
