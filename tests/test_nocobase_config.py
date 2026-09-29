"""Behavioral tests for NocoBase API-key configuration."""

from __future__ import annotations

import ctypes
import json
import unittest
from contextlib import redirect_stdout
from dataclasses import FrozenInstanceError
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from features.nocobase_sync import config


class NocoBaseConfigTests(unittest.TestCase):
    def test_save_encrypts_api_key_and_load_round_trips_without_plaintext(self):
        with TemporaryDirectory() as directory:
            seen = []
            config.save(Path(directory), "http://cloud.njncc.com:443/", "secret-api-key",
                        protect=lambda value: seen.append(value) or b"ciphertext")
            raw = (Path(directory) / "nocobase-config.json").read_text(encoding="utf-8")
            self.assertEqual(seen, [b"secret-api-key"])
            self.assertNotIn("secret-api-key", raw)
            loaded = config.load(Path(directory), unprotect=lambda value: b"secret-api-key")
            self.assertEqual((loaded.url, loaded.api_key, loaded.enabled),
                             ("http://cloud.njncc.com:443", "secret-api-key", True))

    def test_configuration_value_is_immutable(self):
        value = config.NocoBaseConfig("https://example.test", "token", True)
        with self.assertRaises(FrozenInstanceError):
            value.url = "https://other.test"

    def test_blank_api_key_is_rejected_before_writing(self):
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "new"
            with self.assertRaises(ValueError):
                config.save(destination, "https://example.test", "   ", protect=lambda _: b"x")
            self.assertFalse((destination / "nocobase-config.json").exists())

    def test_old_username_password_configuration_is_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "nocobase-config.json"
            path.write_text(json.dumps({"version": 1, "url": "https://example.test",
                                        "username": "u", "password": "eA=="}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "API Key"):
                config.load(Path(directory), unprotect=lambda _: b"secret")

    def test_load_rejects_missing_corrupt_and_invalid_base64(self):
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            with self.assertRaises(ValueError):
                config.load(data_dir, unprotect=lambda _: b"token")
            path = data_dir / "nocobase-config.json"
            path.write_text("{bad", encoding="utf-8")
            with self.assertRaises(ValueError):
                config.load(data_dir, unprotect=lambda _: b"token")
            path.write_text(json.dumps({"version": 2, "url": "https://example.test",
                                        "api_key": "%%%", "enabled": True}), encoding="utf-8")
            with self.assertRaises(ValueError):
                config.load(data_dir, unprotect=lambda _: b"token")

    def test_decryption_error_is_secret_safe(self):
        with TemporaryDirectory() as directory:
            secret = "never-print-this-token"
            config.save(Path(directory), "https://example.test", secret, protect=lambda _: b"cipher")
            with self.assertRaises(ValueError) as raised:
                config.load(Path(directory), unprotect=lambda _: (_ for _ in ()).throw(RuntimeError("failed")))
            self.assertNotIn(secret, str(raised.exception))
            self.assertIn("重新配置", str(raised.exception))

    def test_configured_requires_enabled_valid_configuration(self):
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            self.assertFalse(config.configured(data_dir))
            config.save(data_dir, "https://example.test", "token", enabled=False, protect=lambda _: b"cipher")
            self.assertFalse(config.configured(data_dir, unprotect=lambda _: b"token"))
            config.save(data_dir, "https://example.test", "token", enabled=True, protect=lambda _: b"cipher")
            self.assertTrue(config.configured(data_dir, unprotect=lambda _: b"token"))

    def test_url_normalization_rejects_credentials_and_invalid_ports(self):
        self.assertEqual(config.normalize_url(" http://cloud.njncc.com:443/ "), "http://cloud.njncc.com:443")
        self.assertEqual(config.normalize_url("https://example.test/api/"), "https://example.test/api")
        for value in ("", "ftp://example.test", "http:///bad", "https://u:p@example.test", "https://example.test:99999"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                config.normalize_url(value)

    def test_protector_and_unprotector_must_return_bytes(self):
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            with self.assertRaises(TypeError):
                config.save(data_dir, "https://example.test", "token", protect=lambda _: "bad")
            config.save(data_dir, "https://example.test", "token", protect=lambda _: b"cipher")
            with self.assertRaises(TypeError):
                config.load(data_dir, unprotect=lambda _: "bad")

    def test_dpapi_failure_mentions_windows_without_secret(self):
        crypt32 = unittest.mock.Mock()
        crypt32.CryptProtectData.return_value = 0
        kernel32 = unittest.mock.Mock()
        with patch.object(config, "_windows_crypto", return_value=(crypt32, kernel32)):
            with self.assertRaises(config._DPAPIUnavailable) as raised:
                config._protect_password(b"fixture-token")
        self.assertIn("Windows DPAPI", str(raised.exception))
        self.assertNotIn("fixture-token", str(raised.exception))

    def test_unprotect_frees_dpapi_output(self):
        plaintext = ctypes.create_string_buffer(b"plain")
        crypt32 = unittest.mock.Mock()
        kernel32 = unittest.mock.Mock()

        def unprotect(_input, _description, _entropy, _reserved, _prompt, _flags, output):
            output._obj.cbData = 5
            output._obj.pbData = ctypes.cast(plaintext, ctypes.POINTER(ctypes.c_byte))
            return 1

        crypt32.CryptUnprotectData.side_effect = unprotect
        with patch.object(config, "_windows_crypto", return_value=(crypt32, kernel32)):
            self.assertEqual(config._unprotect_password(b"cipher"), b"plain")
        kernel32.LocalFree.assert_called_once()


class ConfigureCommandTests(unittest.TestCase):
    def test_cli_reads_hidden_api_key_and_never_prints_it(self):
        from features.nocobase_sync import configure

        output = StringIO()
        with (patch.object(configure, "save") as save_configuration,
              patch.object(configure.getpass, "getpass", return_value="secret-api-key") as read_key,
              patch("builtins.input", side_effect=[" http://cloud.njncc.com:443/ "]),
              redirect_stdout(output)):
            self.assertEqual(configure.main(), 0)
        read_key.assert_called_once()
        save_configuration.assert_called_once_with(
            configure.default_data_dir(), " http://cloud.njncc.com:443/ ", "secret-api-key")
        self.assertNotIn("secret-api-key", output.getvalue())
        self.assertIn("配置已保存", output.getvalue())


if __name__ == "__main__":
    unittest.main()
