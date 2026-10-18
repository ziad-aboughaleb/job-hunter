import unittest
from datetime import timezone

from jobhunter.helpers.textutil import clean_html, parse_date, pretty_company, term_in


class CleanHtmlTests(unittest.TestCase):
    def test_strips_tags_and_keeps_lists(self):
        self.assertEqual(clean_html("<p>Hello <b>world</b></p><ul><li>One</li><li>Two</li></ul>"),
                         "Hello world\n- One\n- Two")

    def test_handles_html_that_was_html_escaped(self):  # Greenhouse does this
        self.assertEqual(clean_html("&lt;p&gt;React &amp;amp; Node&lt;/p&gt;"), "React & Node")

    def test_none_and_empty(self):
        self.assertEqual(clean_html(None), "")


class ParseDateTests(unittest.TestCase):
    def test_formats_seen_in_the_wild(self):
        for value in ["2026-07-27 14:23:51 UTC", "2026-07-23T16:58:07+00:00", "2026-07-23T16:58:07+0000",
                      "2019-04-07", "2026-07-21T07:48:42.5Z", 1790000000000]:
            parsed = parse_date(value)
            self.assertIsNotNone(parsed, value)
            self.assertEqual(parsed.tzinfo, timezone.utc if value != "2026-07-23T16:58:07+0000" else parsed.tzinfo)

    def test_garbage_and_empty(self):
        self.assertIsNone(parse_date("not a date"))
        self.assertIsNone(parse_date(""))
        self.assertIsNone(parse_date(None))


class TermInTests(unittest.TestCase):
    def test_whole_words_only(self):
        self.assertFalse(term_in("frontend engineer (javascript)", "java"))
        self.assertTrue(term_in("java developer", "java"))
        self.assertFalse(term_in("lusaka, zambia", "usa"))
        self.assertTrue(term_in("remote - usa", "usa"))
        self.assertFalse(term_in("studios platform engineer", "ios"))
        self.assertFalse(term_in("ukraine", "uk"))

    def test_terms_with_punctuation(self):
        self.assertTrue(term_in("c#/.net developer", ".net"))
        self.assertTrue(term_in("sr. engineer", "sr."))
        self.assertTrue(term_in("c++ engineer", "c++"))

    def test_case_insensitive_and_blank(self):
        self.assertTrue(term_in("Senior Engineer", "SENIOR"))
        self.assertFalse(term_in("anything", "  "))


class PrettyCompanyTests(unittest.TestCase):
    def test_slug_to_name(self):
        self.assertEqual(pretty_company("acme-corp"), "Acme Corp")


if __name__ == "__main__":
    unittest.main()
