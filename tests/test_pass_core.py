import json
import os
import subprocess
import tempfile
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
            self.assertEqual(pass_core.get_totp("share:item"), "119533")

    def test_passes_share_and_item_id_with_json_output(self):
        with patch.object(pass_core, "_cli_run", return_value=_cp(stdout='{"totp": "1"}')) as m:
            pass_core.get_totp("SHARE_ABC:ITEM_XYZ")
        m.assert_called_once_with(
            "item", "totp",
            "--share-id=SHARE_ABC",
            "--item-id=ITEM_XYZ",
            "--output", "json",
        )

    def test_uses_equals_form_for_ids_with_leading_dash(self):
        with patch.object(pass_core, "_cli_run", return_value=_cp(stdout='{"totp": "1"}')) as m:
            pass_core.get_totp("-DASH_SHARE:-DASH_ITEM")
        args = m.call_args.args
        self.assertIn("--share-id=-DASH_SHARE", args)
        self.assertIn("--item-id=-DASH_ITEM", args)
        self.assertNotIn("-DASH_SHARE", args)
        self.assertNotIn("-DASH_ITEM", args)

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


class GetPasswordTests(unittest.TestCase):
    def test_returns_stripped_stdout(self):
        with patch.object(pass_core, "_cli_run", return_value=_cp(stdout="hunter2\n")) as m:
            self.assertEqual(pass_core.get_password("SHARE:ITEM"), "hunter2")
        m.assert_called_once_with(
            "item", "view", "--field", "password",
            "--share-id=SHARE", "--item-id=ITEM",
        )

    def test_uses_equals_form_for_ids_with_leading_dash(self):
        with patch.object(pass_core, "_cli_run", return_value=_cp(stdout="pw")) as m:
            pass_core.get_password("-DASH_SHARE:-DASH_ITEM")
        args = m.call_args.args
        self.assertIn("--share-id=-DASH_SHARE", args)
        self.assertIn("--item-id=-DASH_ITEM", args)
        self.assertNotIn("-DASH_SHARE", args)
        self.assertNotIn("-DASH_ITEM", args)

    def test_returns_none_on_nonzero_returncode(self):
        with patch.object(pass_core, "_cli_run", return_value=_cp(returncode=1, stderr="boom")):
            self.assertIsNone(pass_core.get_password("share:item"))

    def test_rejects_invalid_composite_id(self):
        for bad in ("", "no-colon", ":only-item", "only-share:"):
            with patch.object(pass_core, "_cli_run") as m:
                self.assertIsNone(pass_core.get_password(bad))
                m.assert_not_called()


class OpenUrlTests(unittest.TestCase):
    def test_opens_http_and_https(self):
        for url in ("http://example.com", "https://example.com/path?q=1"):
            with patch.object(pass_core.subprocess, "run") as m:
                self.assertTrue(pass_core.open_url(url))
                m.assert_called_once_with(["open", url], check=False)

    def test_rejects_unsafe_schemes(self):
        unsafe = (
            "file:///etc/passwd",
            "javascript:alert(1)",
            "ftp://example.com",
            "data:text/html,<script>alert(1)</script>",
            "ssh://user@host",
            "vbscript:msgbox(1)",
        )
        for url in unsafe:
            with patch.object(pass_core.subprocess, "run") as m:
                self.assertFalse(pass_core.open_url(url))
                m.assert_not_called()

    def test_rejects_empty_and_none(self):
        for url in ("", None):
            with patch.object(pass_core.subprocess, "run") as m:
                self.assertFalse(pass_core.open_url(url))
                m.assert_not_called()


class ExtractDomainTests(unittest.TestCase):
    def test_returns_first_valid_hostname(self):
        self.assertEqual(
            pass_core._extract_domain(["https://example.com/login", "https://other.com"]),
            "example.com",
        )

    def test_skips_invalid_and_returns_next_valid(self):
        self.assertEqual(
            pass_core._extract_domain(["not a url", "https://valid.example.com"]),
            "valid.example.com",
        )

    def test_returns_none_for_empty_or_none(self):
        self.assertIsNone(pass_core._extract_domain([]))
        self.assertIsNone(pass_core._extract_domain(None))

    def test_rejects_unsafe_hostnames(self):
        for uri in (
            "https://under_score.example.com",
            "https://-leading-dash.com",
            "https://exa mple.com",
            "javascript:alert(1)",
        ):
            self.assertIsNone(pass_core._extract_domain([uri]))


class ParseEntryTests(unittest.TestCase):
    def _entry(self, **overrides):
        base = {
            "id": "ITEM_ID",
            "share_id": "SHARE_ID",
            "content": {
                "title": "GitHub",
                "content": {
                    "Login": {
                        "username": "alice",
                        "email": "alice@example.com",
                        "urls": ["https://github.com/login", "https://github.com"],
                    },
                },
            },
        }
        base.update(overrides)
        return base

    def test_parses_full_entry(self):
        result = pass_core._parse_entry(self._entry(), "Personal")
        self.assertEqual(result, {
            "id": "SHARE_ID:ITEM_ID",
            "name": "GitHub",
            "username": "alice",
            "url": "https://github.com/login",
            "domain": "github.com",
            "vault": "Personal",
        })

    def test_returns_none_when_ids_missing(self):
        self.assertIsNone(pass_core._parse_entry(self._entry(id=None), "v"))
        self.assertIsNone(pass_core._parse_entry(self._entry(share_id=None), "v"))
        self.assertIsNone(pass_core._parse_entry({}, "v"))

    def test_falls_back_from_username_to_email(self):
        entry = self._entry()
        entry["content"]["content"]["Login"]["username"] = ""
        result = pass_core._parse_entry(entry, "v")
        self.assertEqual(result["username"], "alice@example.com")

    def test_handles_missing_urls(self):
        entry = self._entry()
        entry["content"]["content"]["Login"]["urls"] = []
        result = pass_core._parse_entry(entry, "v")
        self.assertEqual(result["url"], "")
        self.assertIsNone(result["domain"])

    def test_handles_missing_login_block(self):
        entry = {"id": "I", "share_id": "S", "content": {"title": "T", "content": {}}}
        result = pass_core._parse_entry(entry, "v")
        self.assertEqual(result, {
            "id": "S:I",
            "name": "T",
            "username": "",
            "url": "",
            "domain": None,
            "vault": "v",
        })


class ListVaultsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._cache_dir = patch.object(pass_core, "_CACHE_DIR", self._tmp.name)
        self._vault_cache = patch.object(pass_core, "_VAULT_CACHE", os.path.join(self._tmp.name, "vaults.json"))
        self._cache_dir.start()
        self._vault_cache.start()
        self.addCleanup(self._cache_dir.stop)
        self.addCleanup(self._vault_cache.stop)

    def test_unwraps_vaults_key_from_json(self):
        vaults = [{"id": "v1", "name": "Personal"}, {"id": "v2", "name": "Work"}]
        with patch.object(pass_core, "_cli_run", return_value=_cp(stdout=json.dumps({"vaults": vaults}))):
            self.assertEqual(pass_core._list_vaults(), vaults)

    def test_returns_empty_list_when_vaults_key_missing(self):
        with patch.object(pass_core, "_cli_run", return_value=_cp(stdout='{"other": []}')):
            self.assertEqual(pass_core._list_vaults(), [])

    def test_returns_none_on_cli_failure(self):
        with patch.object(pass_core, "_cli_run", return_value=_cp(returncode=1, stderr="not logged in")):
            self.assertIsNone(pass_core._list_vaults())

    def test_returns_none_on_malformed_json(self):
        with patch.object(pass_core, "_cli_run", return_value=_cp(stdout="not json")):
            self.assertIsNone(pass_core._list_vaults())

    def test_passes_output_json_flag(self):
        with patch.object(pass_core, "_cli_run", return_value=_cp(stdout='{"vaults": []}')) as m:
            pass_core._list_vaults()
        m.assert_called_once_with("vault", "list", "--output", "json")

    def test_writes_cache_after_successful_call(self):
        vaults = [{"id": "v1", "name": "Personal"}]
        with patch.object(pass_core, "_cli_run", return_value=_cp(stdout=json.dumps({"vaults": vaults}))):
            pass_core._list_vaults()
        with open(pass_core._VAULT_CACHE) as f:
            self.assertEqual(json.load(f), vaults)


class FetchVaultItemsTests(unittest.TestCase):
    def test_unwraps_items_key_from_json(self):
        items = [{"id": "i1"}, {"id": "i2"}]
        with patch.object(pass_core, "_cli_run", return_value=_cp(stdout='{"items": [{"id": "i1"}, {"id": "i2"}]}')):
            self.assertEqual(pass_core._fetch_vault_items("Personal"), items)

    def test_returns_empty_list_when_items_key_missing(self):
        with patch.object(pass_core, "_cli_run", return_value=_cp(stdout='{"other": []}')):
            self.assertEqual(pass_core._fetch_vault_items("Personal"), [])

    def test_returns_empty_list_on_cli_failure(self):
        with patch.object(pass_core, "_cli_run", return_value=_cp(returncode=1, stderr="boom")):
            self.assertEqual(pass_core._fetch_vault_items("Personal"), [])

    def test_returns_empty_list_on_malformed_json(self):
        with patch.object(pass_core, "_cli_run", return_value=_cp(stdout="not json")):
            self.assertEqual(pass_core._fetch_vault_items("Personal"), [])

    def test_filters_to_login_type(self):
        with patch.object(pass_core, "_cli_run", return_value=_cp(stdout='{"items": []}')) as m:
            pass_core._fetch_vault_items("Personal")
        m.assert_called_once_with("item", "list", "Personal", "--filter-type", "login", "--output", "json")


if __name__ == "__main__":
    unittest.main()
