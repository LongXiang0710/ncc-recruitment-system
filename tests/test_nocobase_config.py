"""Behavioral tests for the NocoBase sync configuration boundary."""

from __future__ import annotations

import subprocess
import sys
import unittest
import ctypes
from dataclasses import FrozenInstanceError
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from features.nocobase_sync import config


class NocoBaseConfigAvailabilityTests(unittest.TestCase):
    def test_configuration_module_can_be_imported_by_the_application(self):
        """Removing the configuration module would prevent its public API loading."""
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from features.nocobase_sync import config; "
                "print(config.__name__)",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "features.nocobase_sync.config")


class NocoBaseConfigTests(unittest.TestCase):
    def test_save_uses_protector_and_never_writes_plain_password(self):
        """A failed encryption boundary must never leave a readable password on disk."""
        with TemporaryDirectory() as directory:
            protected_values = []

            def protect(value):
                protected_values.append(value)
                return b"ciphertext"

            config.save(
                Path(directory),
                "http://cloud.njncc.com:443/",
                "sync-user",
                "secret-value",
                protect=protect,
            )

            raw = (Path(directory) / "nocobase-config.json").read_text(encoding="utf-8")
            self.assertEqual(protected_values, [b"secret-value"])
            self.assertNotIn("secret-value", raw)
            self.assertNotIn("sync-user:secret-value", raw)
            loaded = config.load(Path(directory), unprotect=lambda value: b"secret-value")
            self.assertEqual(
                (loaded.url, loaded.username, loaded.password),
                ("http://cloud.njncc.com:443", "sync-user", "secret-value"),
            )

    def test_url_normalization_and_rejection_of_invalid_urls(self):
        """A malformed URL or unsupported scheme must not become a sync target."""
        self.assertEqual(
            config.normalize_url("  http://cloud.njncc.com:443/  "),
            "http://cloud.njncc.com:443",
        )
        self.assertEqual(config.normalize_url("https://example.test/a/"), "https://example.test/a")
        for value in ("", "   ", "ftp://example.test", "http:///missing-host", "https://"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    config.normalize_url(value)

    def test_config_value_is_immutable(self):
        """Changing a returned password in-place would desynchronize its validated fields."""
        value = config.NocoBaseConfig("https://example.test", "user", "password")
        with self.assertRaises(FrozenInstanceError):
            value.url = "https://other.test"

    def test_blank_username_or_password_is_rejected_before_writing(self):
        """Blank credentials must not replace a previously absent config file."""
        for username, password in (("", "password"), ("user", ""), ("   ", "password")):
            with self.subTest(username=username, password=password):
                with TemporaryDirectory() as directory:
                    data_dir = Path(directory) / "created-by-save"
                    with self.assertRaises(ValueError):
                        config.save(data_dir, "https://example.test", username, password, protect=lambda _: b"x")
                    self.assertFalse((data_dir / "nocobase-config.json").exists())

    def test_save_atomically_replaces_config_and_removes_temporary_file(self):
        """A successful save should expose only the completed replacement file."""
        with TemporaryDirectory() as directory:
            data_dir = Path(directory) / "nested"
            config.save(data_dir, "https://example.test/", "user", "password", protect=lambda _: b"x")
            self.assertEqual(sorted(path.name for path in data_dir.iterdir()), ["nocobase-config.json"])

    def test_load_rejects_missing_corrupt_json_and_invalid_base64(self):
        """Unreadable stored state must be rejected before an unprotector sees data."""
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            with self.assertRaises(ValueError):
                config.load(data_dir, unprotect=lambda _: b"password")

            path = data_dir / "nocobase-config.json"
            path.write_text("{not-json", encoding="utf-8")
            with self.assertRaises(ValueError):
                config.load(data_dir, unprotect=lambda _: b"password")

            path.write_text(
                '{"version": 1, "url": "https://example.test", "username": "user", "password": "%%%"}',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                config.load(data_dir, unprotect=lambda _: (_ for _ in ()).throw(AssertionError("must not decrypt")))

            path.write_text(
                '{"version": true, "url": "https://example.test", "username": "user", "password": ""}',
                encoding="utf-8",
            )
            unprotect_calls = []
            with self.assertRaises(ValueError):
                config.load(data_dir, unprotect=lambda value: unprotect_calls.append(value) or b"password")
            self.assertEqual(unprotect_calls, [])

    def test_decryption_failure_requests_current_windows_account_reconfiguration(self):
        """Wrong-account ciphertext must never be surfaced as a possible password."""
        with TemporaryDirectory() as directory:
            secret = "never-print-this-secret"
            ciphertext = b"not-the-secret"
            config.save(Path(directory), "https://example.test", "user", secret, protect=lambda _: ciphertext)
            with self.assertRaises(ValueError) as raised:
                config.load(Path(directory), unprotect=lambda _: (_ for _ in ()).throw(RuntimeError("wrong account")))

            message = str(raised.exception)
            self.assertIn("当前 Windows 帐户", message)
            self.assertIn("重新配置", message)
            self.assertNotIn(secret, message)
            self.assertNotIn("bm90LXRoZS1zZWNyZXQ=", message)

    def test_configured_requires_a_successful_load_with_all_values(self):
        """A corrupt or incomplete configuration must not enable synchronization."""
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            self.assertFalse(config.configured(data_dir))
            config.save(data_dir, "https://example.test", "user", "password", protect=lambda _: b"cipher")
            self.assertTrue(config.configured(data_dir, unprotect=lambda _: b"password"))
            (data_dir / "nocobase-config.json").write_text("{}", encoding="utf-8")
            self.assertFalse(config.configured(data_dir, unprotect=lambda _: b"password"))

    def test_injected_protector_and_unprotector_enforce_bytes_contract(self):
        """Injection must preserve the same bytes-only cryptographic boundary as DPAPI."""
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            with self.assertRaises(TypeError):
                config.save(data_dir, "https://example.test", "user", "password", protect=lambda _: "not-bytes")

            config.save(data_dir, "https://example.test", "user", "password", protect=lambda value: b"cipher")
            with self.assertRaises(TypeError):
                config.load(data_dir, unprotect=lambda _: "not-bytes")

    def test_unavailable_windows_dpapi_reports_an_explicit_configuration_error(self):
        """A DPAPI call failure must identify the Windows configuration boundary."""
        crypt32 = unittest.mock.Mock()
        crypt32.CryptProtectData.return_value = 0
        kernel32 = unittest.mock.Mock()
        with patch.object(config, "_windows_crypto", return_value=(crypt32, kernel32)):
            with self.assertRaises(config._DPAPIUnavailable) as raised:
                config._protect_password(b"fixture-password")
        self.assertIn("Windows DPAPI", str(raised.exception))

    def test_save_rejects_url_userinfo_without_creating_a_config_file(self):
        """A password embedded in a URL must never bypass the DPAPI password field."""
        with TemporaryDirectory() as directory:
            data_dir = Path(directory) / "new-config"
            embedded_secret = "url-password-token"
            with self.assertRaises(ValueError) as raised:
                config.save(
                    data_dir,
                    f"https://alice:{embedded_secret}@example.test/",
                    "alice",
                    "fixture-password",
                    protect=lambda _: b"cipher",
                )
            self.assertNotIn(embedded_secret, str(raised.exception))
            self.assertFalse((data_dir / "nocobase-config.json").exists())

    def test_normalize_url_rejects_invalid_host_and_port_and_preserves_query_fragment_values(self):
        """Host validation must not silently alter query or fragment data while normalizing a path."""
        self.assertEqual(
            config.normalize_url("https://example.test/a///?next=/&from=#ending/"),
            "https://example.test/a?next=/&from=#ending/",
        )
        self.assertEqual(
            config.normalize_url("https://example.test/?next=/"),
            "https://example.test?next=/",
        )
        for value in (
            "http://exa mple.test/",
            "http://exam\nple.test/",
            "https://example.test:bad/",
            "https://example.test:99999/",
            "http://:80/",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    config.normalize_url(value)

    def test_empty_protector_result_neither_creates_nor_replaces_configuration(self):
        """Saving an unreadable empty ciphertext must leave the previous configuration untouched."""
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            with self.assertRaises(ValueError):
                config.save(data_dir / "new", "https://example.test", "user", "password", protect=lambda _: b"")
            self.assertFalse((data_dir / "new" / "nocobase-config.json").exists())

            config.save(data_dir, "https://example.test", "user", "password", protect=lambda _: b"existing")
            previous_content = (data_dir / "nocobase-config.json").read_text(encoding="utf-8")
            with self.assertRaises(ValueError):
                config.save(data_dir, "https://other.test", "user", "password", protect=lambda _: b"")
            self.assertEqual((data_dir / "nocobase-config.json").read_text(encoding="utf-8"), previous_content)

    def test_unprotect_prototype_uses_description_output_pointer_and_frees_output_once(self):
        """CryptUnprotectData needs LPWSTR output typing and exactly one LocalFree call."""
        plaintext = ctypes.create_string_buffer(b"plain")
        crypt32 = unittest.mock.Mock()
        kernel32 = unittest.mock.Mock()

        def unprotect(_input_blob, _description, _entropy, _reserved, _prompt, _flags, output_blob):
            output_blob._obj.cbData = 5
            output_blob._obj.pbData = ctypes.cast(plaintext, ctypes.POINTER(ctypes.c_byte))
            return 1

        crypt32.CryptUnprotectData.side_effect = unprotect
        with patch.object(config, "_windows_crypto", return_value=(crypt32, kernel32)):
            self.assertEqual(config._unprotect_password(b"cipher"), b"plain")

        self.assertIs(crypt32.CryptUnprotectData.argtypes[1], ctypes.POINTER(ctypes.c_wchar_p))
        kernel32.LocalFree.assert_called_once()


class ConfigureCommandTests(unittest.TestCase):
    def test_cli_uses_getpass_saves_then_reports_unavailable_browser_module(self):
        """A missing future browser feature must not undo an already saved configuration."""
        from features.nocobase_sync import configure

        output = StringIO()
        with (
            patch.object(configure, "save") as save_configuration,
            patch.object(configure.getpass, "getpass", return_value="test-password") as read_password,
            patch("builtins.input", side_effect=[" https://example.test/ ", "cli-user", "y"]),
            patch.object(configure, "import_module", side_effect=ModuleNotFoundError("browser unavailable")),
            redirect_stdout(output),
        ):
            configure.main()

        read_password.assert_called_once()
        save_configuration.assert_called_once_with(
            configure.default_data_dir(), " https://example.test/ ", "cli-user", "test-password"
        )
        self.assertIn("配置已保存，连接测试将在浏览器模块完成后可用", output.getvalue())
        self.assertNotIn("test-password", output.getvalue())

    def test_batch_file_has_the_exact_safe_launcher_content(self):
        """The launcher must start the module from its own directory and keep its console open."""
        batch_file = Path("配置NocoBase.bat")
        self.assertTrue(batch_file.exists())
        self.assertEqual(
            batch_file.read_text(encoding="utf-8"),
            "@echo off\ncd /d \"%~dp0\"\npython -m features.nocobase_sync.configure\npause\n",
        )


if __name__ == "__main__":
    unittest.main()
