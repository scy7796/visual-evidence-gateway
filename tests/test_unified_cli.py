"""Tests for the single-binary user interface."""
from __future__ import annotations

import unittest
from unittest import mock


class UnifiedCliTest(unittest.TestCase):
    def test_version_is_available_without_loading_a_backend(self):
        from visual_evidence_gateway import cli

        with self.assertRaises(SystemExit) as raised:
            cli.main(["--version"])
        self.assertEqual(raised.exception.code, 0)

    def test_setup_dispatches_arguments(self):
        from visual_evidence_gateway import cli

        from visual_evidence_gateway import setup_cli

        with mock.patch.object(setup_cli, "main", return_value=7) as setup:
            self.assertEqual(cli.main(["setup", "--skip-probe"]), 7)
        setup.assert_called_once_with(["--skip-probe"])

    def test_healthcheck_dispatches_arguments(self):
        from visual_evidence_gateway import cli

        from visual_evidence_gateway import healthcheck

        with mock.patch.object(healthcheck, "main", return_value=0) as health:
            self.assertEqual(cli.main(["healthcheck", "--json"]), 0)
        health.assert_called_once_with(["--json"])

    def test_serve_rejects_extra_arguments(self):
        from visual_evidence_gateway import cli

        with self.assertRaisesRegex(SystemExit, "does not accept"):
            cli.main(["serve", "--unexpected"])


if __name__ == "__main__":
    unittest.main()
