import subprocess
import unittest
from unittest.mock import patch

import pass_core


def _cp(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class GetTotpTests(unittest.TestCase):
    def test_returns_primary_totp_field(self):
        with patch.object(pass_core, "_cli_run", return_value=_cp(stdout='{"totp": "606440", "totp_uri": "otpauth://..."}')):
            self.assertEqual(pass_core.get_totp("share:item"), "606440")

    def test_falls_back_to_first_value_when_no_totp_key(self):
        with patch.object(pass_core, "_cli_run", return_value=_cp(stdout='{"TOTP 1": "119533", "TOTP 2": "622653"}')):
            self.assertIn(pass_core.get_totp("share:item"), {"119533", "622653"})

    def test_passes_share_and_item_id_with_json_output(self):
        with patch.object(pass_core, "_cli_run", return_value=_cp(stdout='{"totp": "1"}')) as m:
            pass_core.get_totp("SHARE_ABC:ITEM_XYZ")
        m.assert_called_once_with(
            "item", "totp",
            "--share-id", "SHARE_ABC",
            "--item-id", "ITEM_XYZ",
            "--output", "json",
        )

    def test_returns_none_on_nonzero_returncode(self):
        with patch.object(pass_core, "_cli_run", return_value=_cp(returncode=1, stderr="boom")):
            self.assertIsNone(pass_core.get_totp("share:item"))

    def test_returns_none_on_malformed_json(self):
        with patch.object(pass_core, "_cli_run", return_value=_cp(stdout="not json")):
            self.assertIsNone(pass_core.get_totp("share:item"))

    def test_returns_none_on_empty_payload(self):
        with patch.object(pass_core, "_cli_run", return_value=_cp(stdout="{}")):
            self.assertIsNone(pass_core.get_totp("share:item"))

    def test_rejects_invalid_composite_id(self):
        for bad in ("", "no-colon", ":only-item", "only-share:"):
            with patch.object(pass_core, "_cli_run") as m:
                self.assertIsNone(pass_core.get_totp(bad))
                m.assert_not_called()


if __name__ == "__main__":
    unittest.main()
