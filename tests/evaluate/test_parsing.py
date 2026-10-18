import unittest

from jobhunter.evaluate import parsing


class ParsingTests(unittest.TestCase):
    def test_tolerates_fences_and_chatty_text(self):
        self.assertEqual(parsing.parse_json_text('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(parsing.parse_json_text('Sure! {"a": 1} hope that helps'), {"a": 1})

    def test_normalize_fixes_small_mistakes(self):
        result = parsing.normalize({"score": "77%", "strengths": "React match", "gaps": None}, "J1")
        self.assertEqual((result["score"], result["strengths"], result["gaps"]), (77, ["React match"], []))

    def test_missing_score_is_an_error_not_a_zero(self):
        with self.assertRaises(ValueError):
            parsing.normalize({"strengths": ["x"]}, "J1")

    def test_hard_fail_forces_score_zero(self):
        result = parsing.normalize({"hard_fail": "US only", "score": 90, "strengths": ["x"], "pitch": "p"}, "J1")
        self.assertEqual((result["score"], result["hard_fail"], result["strengths"], result["pitch"]), (0, "US only", [], ""))


if __name__ == "__main__":
    unittest.main()
