"""`prompt` prints what the AI receives. These tests also pin down WHICH settings shape the rubric."""
import json
import unittest

from jobhunter import cli
from tests.support import LONG_CV, ProjectCase


class ShowPromptTests(ProjectCase):
    def setUp(self):
        super().setUp()
        self.write_config(
            profile={"target_roles": "embedded firmware engineering"},
            score_threshold=65,
            scoring_weights=[{"name": "Firmware skills", "weight": 70, "what": "C and RTOS experience"},
                             {"name": "Seniority fit", "weight": 30, "what": "years of experience"}],
            filters={"title_include": ["a-word-only-in-the-filters"]},
        )
        self.write_file("cv.md", LONG_CV)
        self.write_file("preferences.md", "I can only work from Portugal.")

    def output(self, *args):
        self.assertEqual(cli.main(["prompt", *args]), 0)
        return self.out.getvalue()

    def test_rubric_is_built_from_the_config(self):
        text = self.output()
        self.assertIn("The role is not mainly embedded firmware engineering.", text)   # profile.target_roles
        self.assertIn("Firmware skills (70): C and RTOS experience", text)             # scoring_weights
        self.assertIn("Seniority fit (30): years of experience", text)
        self.assertIn("below 65", text)                                                # score_threshold
        self.assertIn("65-89", text)
        self.assertNotIn("Core skills overlap", text)                                  # the default weights are gone

    def test_cv_and_preferences_are_included_and_come_last(self):
        text = self.output()
        self.assertIn("Full-stack engineer with React", text)
        self.assertIn("I can only work from Portugal.", text)
        self.assertLess(text.index("# Step 1 - hard gates"), text.index("I can only work from Portugal."))

    def test_filters_are_not_part_of_the_prompt(self):
        self.assertNotIn("a-word-only-in-the-filters", self.output())

    def test_hide_cv_shows_placeholders(self):
        text = self.output("--hide-cv")
        self.assertNotIn("Full-stack engineer with React", text)
        self.assertIn("the text of cv.md goes here", text)

    def test_first_candidate_is_shown_as_the_per_job_message(self):
        self.write_data("candidates.json", [{"ref": "J1", "uid": "u", "title": "Firmware Dev", "company": "Acme",
                                             "location": "Remote", "posted": "", "description": "RTOS and C"}])
        text = self.output()
        self.assertIn("USER MESSAGE", text)
        self.assertIn("Title: Firmware Dev", text)


if __name__ == "__main__":
    unittest.main()
