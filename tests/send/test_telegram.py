import unittest
from unittest import mock

from jobhunter.send import telegram


def candidate(i, **kw):
    return dict({"ref": f"J{i}", "uid": f"uid{i}", "title": f"Job {i}", "company": "Co", "url": f"https://x/{i}",
                 "location": "Remote", "posted": "2026-10-10", "priority": False}, **kw)


class FormatTests(unittest.TestCase):
    def test_everything_from_the_posting_is_escaped(self):
        job = candidate(1, title="Dev <script> & more", company="A&B", location="X > Y")
        text = telegram.format_card(job, {"score": 80, "strengths": ["uses <b>bold</b>"], "gaps": [], "pitch": 'I said "hi"'})
        self.assertNotIn("<script>", text)
        self.assertIn("Dev &lt;script&gt; &amp; more", text)
        self.assertIn("uses &lt;b&gt;bold&lt;/b&gt;", text)
        self.assertIn('href="https://x/1"', text)

    def test_priority_jobs_get_a_star_and_long_text_stays_under_the_limit(self):
        job = candidate(1, priority=True, title="T" * 500)
        text = telegram.format_card(job, {"score": 80, "strengths": ["s" * 900] * 5, "gaps": ["g" * 900] * 5, "pitch": "p" * 2000})
        self.assertTrue(text.startswith("⭐"))
        self.assertLess(len(text), 4096)

    def test_token_never_appears_in_error_text(self):
        from jobhunter.helpers import http
        with mock.patch("jobhunter.helpers.http.post_json", side_effect=http.HttpStatusError(401, "bad token 123:secret")):
            ok, error = telegram.send_message("123:secret", "42", "hi")
        self.assertFalse(ok)
        self.assertNotIn("123:secret", error)


if __name__ == "__main__":
    unittest.main()
