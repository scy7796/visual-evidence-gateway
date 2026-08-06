"""Trigger policy tests (T1 and spec sections 4-7)."""
from __future__ import annotations

import unittest

from visual_evidence_gateway.router.policy import visual_required


class TriggerPolicyTest(unittest.TestCase):
    def test_t1_code_task_image_merely_exists(self):
        # Image exists in the repo, but the task is code-only.
        self.assertFalse(visual_required(True, False, True))
        self.assertFalse(visual_required(True, False, False))

    def test_user_explicitly_asks_about_screenshot(self):
        self.assertTrue(visual_required(True, True, True))

    def test_logs_are_better_text_source_than_screenshot(self):
        self.assertFalse(visual_required(True, False, False))
        self.assertFalse(visual_required(True, True, False))

    def test_no_accessible_image(self):
        self.assertFalse(visual_required(False, True, True))

    def test_chart_with_source_csv_available(self):
        self.assertFalse(visual_required(True, True, False))

    def test_chart_itself_is_evidence(self):
        self.assertTrue(visual_required(True, True, True))

    def test_user_already_transcribed_image(self):
        self.assertFalse(visual_required(True, True, False))

    def test_ui_state_not_derivable_from_code(self):
        self.assertTrue(visual_required(True, True, True))

    def test_all_three_conditions_must_hold(self):
        cases = [
            (True, True, True, True),
            (True, True, False, False),
            (True, False, True, False),
            (False, True, True, False),
            (True, False, False, False),
            (False, False, False, False),
        ]
        for a, b, c, expected in cases:
            self.assertEqual(visual_required(a, b, c), expected, f"({a},{b},{c})")


if __name__ == "__main__":
    unittest.main()
