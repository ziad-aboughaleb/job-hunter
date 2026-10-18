"""Each source turns a site's response into Job objects. The responses here are small copies of the real formats."""
import json
import unittest
from unittest import mock

from jobhunter.fetch.sources import arbeitnow, ashby, greenhouse, lever, personio, recruitee, remoteok, remotive, workable
from tests.support import fake_get_text


def json_routes(routes):
    return fake_get_text({k: (None if v is None else json.dumps(v)) for k, v in routes.items()})


class CompanySourceTests(unittest.TestCase):
    def fetch(self, module, slug, routes, **kw):
        with mock.patch("jobhunter.helpers.http.get_text", json_routes(routes)):
            return module.fetch(slug, **kw)

    def test_greenhouse(self):
        jobs = self.fetch(greenhouse, "acme", {"boards-api.greenhouse.io/v1/boards/acme": {"jobs": [{
            "id": 1, "title": "Frontend Engineer", "absolute_url": "https://g/1", "location": {"name": "Remote - EMEA"},
            "first_published": "2026-10-10T10:00:00-04:00", "content": "&lt;p&gt;React &amp;amp; Node&lt;/p&gt;"}]}})
        self.assertEqual((jobs[0].title, jobs[0].location, jobs[0].description, jobs[0].uid),
                         ("Frontend Engineer", "Remote - EMEA", "React & Node", "greenhouse:acme:1"))

    def test_unknown_company_returns_none(self):
        self.assertIsNone(self.fetch(greenhouse, "nobody", {}))

    def test_lever_including_eu(self):
        data = [{"id": "l1", "text": "React Dev", "hostedUrl": "https://l/1", "categories": {"location": "Remote"},
                 "workplaceType": "remote", "createdAt": 1790000000000, "descriptionPlain": "React",
                 "lists": [{"text": "Req", "content": "<li>Node</li>"}], "additionalPlain": ""}]
        jobs = self.fetch(lever, "x", {"api.lever.co/v0/postings/x": data})
        self.assertTrue(jobs[0].remote)
        self.assertIn("- Node", jobs[0].description)
        self.assertEqual(self.fetch(lever, "x", {"api.eu.lever.co/v0/postings/x": data}, eu=True)[0].source, "lever_eu")

    def test_ashby_skips_unlisted_jobs(self):
        data = {"jobs": [
            {"id": "a1", "title": "Web Engineer", "jobUrl": "https://a/1", "location": "Cairo", "isRemote": True,
             "publishedAt": "2026-10-10T00:00:00+00:00", "descriptionPlain": "React"},
            {"id": "a2", "title": "Hidden", "jobUrl": "https://a/2", "isListed": False}]}
        jobs = self.fetch(ashby, "co", {"posting-api/job-board/co": data})
        self.assertEqual([j.title for j in jobs], ["Web Engineer"])
        self.assertTrue(jobs[0].remote)

    def test_recruitee_with_its_date_format(self):
        data = {"offers": [{"id": 11, "title": "Frontend Developer", "company_name": "Vandebron", "careers_url": "https://r/1",
                            "remote": True, "city": "Utrecht", "country": "Netherlands",
                            "published_at": "2026-10-10 08:23:10 UTC", "description": "<p>React</p>", "requirements": "<ul><li>Node</li></ul>"}]}
        job = self.fetch(recruitee, "van", {"van.recruitee.com/api/offers": data})[0]
        self.assertEqual((job.company, job.location, job.remote), ("Vandebron", "Utrecht, Netherlands", True))
        self.assertIsNotNone(job.posted)
        self.assertIn("React", job.description)
        self.assertIn("Node", job.description)

    def test_workable(self):
        data = {"name": "Blue Co", "jobs": [{"title": "Full Stack Developer", "shortcode": "ABC", "telecommuting": True,
                                             "country": "Egypt", "published_on": "2026-10-10", "url": "https://w/ABC",
                                             "description": "<p>React</p>"}]}
        job = self.fetch(workable, "blue", {"widget/accounts/blue": data})[0]
        self.assertEqual((job.company, job.location, job.remote, job.job_id), ("Blue Co", "Egypt", True, "ABC"))

    def test_personio_xml_and_domain_fallback(self):
        xml = """<?xml version="1.0"?><workzag-jobs><position><id>7</id><subcompany>Acme GmbH</subcompany>
            <office>Berlin</office><additionalOffices><office>Remote</office></additionalOffices>
            <name>Junior Frontend Developer</name><jobDescriptions><jobDescription><name>Tasks</name>
            <value><![CDATA[<p>React &amp; TypeScript</p>]]></value></jobDescription></jobDescriptions>
            <seniority>entry-level</seniority><createdAt>2026-10-10T10:00:00+0000</createdAt></position></workzag-jobs>"""
        # the feed only exists on the .com domain: the .de request returns 404 (None)
        with mock.patch("jobhunter.helpers.http.get_text", fake_get_text({"acme.jobs.personio.com": xml})):
            job = personio.fetch("acme")[0]
        self.assertEqual((job.company, job.location, job.remote), ("Acme GmbH", "Berlin, Remote", True))
        self.assertIn("React & TypeScript", job.description)
        self.assertIn("Seniority: entry-level", job.description)
        self.assertTrue(job.url.startswith("https://acme.jobs.personio.com/job/7"))

    def test_personio_without_remote_signal(self):
        self.assertFalse(personio.looks_remote("Munich", "React Developer", "On site, five days a week."))
        self.assertTrue(personio.looks_remote("Munich", "React Developer", "We are fully remote."))


class BoardSourceTests(unittest.TestCase):
    def test_remotive_uses_the_category_option(self):
        seen_urls = []

        def fake(url, *a, **k):
            seen_urls.append(url)
            return json.dumps({"jobs": [{"id": 1, "title": "DevOps Engineer", "company_name": "Beta", "url": "https://r/1",
                                         "candidate_required_location": "Worldwide", "publication_date": "2026-10-10T00:00:00",
                                         "description": "<p>k8s</p>"}]})
        with mock.patch("jobhunter.helpers.http.get_text", fake):
            jobs = remotive.fetch({"category": "devops"})
        self.assertIn("category=devops", seen_urls[0])
        self.assertEqual((jobs[0].company, jobs[0].location, jobs[0].remote), ("Beta", "Worldwide", True))

    def test_remoteok_skips_the_legal_notice(self):
        data = [{"legal": "notice"}, {"id": "9", "position": "React Dev", "company": "Acme", "url": "https://ro/9",
                                       "tags": ["react", "node"], "date": "2026-10-10T00:00:00+00:00", "description": "<p>TS</p>"}]
        with mock.patch("jobhunter.helpers.http.get_text", fake_get_text({"remoteok.com/api": json.dumps(data)})):
            jobs = remoteok.fetch({})
        self.assertEqual(len(jobs), 1)
        self.assertIn("Tags: react, node", jobs[0].description)

    def test_arbeitnow_reads_two_pages(self):
        page1 = {"data": [{"slug": "a", "title": "Dev", "company_name": "X", "url": "https://an/a", "created_at": 1790000000,
                           "remote": True, "description": "x"}], "links": {"next": "https://www.arbeitnow.com/api/job-board-api?page=2"}}
        page2 = {"data": [{"slug": "b", "title": "Dev 2", "company_name": "Y", "url": "https://an/b", "description": "y"}], "links": {}}

        def fake(url, *a, **k):
            return json.dumps(page2 if "page=2" in url else page1)
        with mock.patch("jobhunter.helpers.http.get_text", fake):
            self.assertEqual([j.job_id for j in arbeitnow.fetch({"pages": 2})], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
