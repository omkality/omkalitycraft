"""Download and packaging boundaries for the public source build."""

import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, call, patch
from urllib.error import HTTPError

from archive_format import entry, ordered
from fetch_inputs import ensure_input
from verify_build import inspect_jar


class Response(io.BytesIO):
    def geturl(self):
        return "https://example.invalid/input.jar"


class BuildSafetyTests(unittest.TestCase):
    def test_dj2_profile_binds_the_declared_fix_version(self):
        source = Path(__file__).resolve().parents[1]
        version = json.loads((source / "versions.json").read_bytes())["artifacts"][
            "dj2fix"
        ]["version"]
        profile = dict(
            line.split("=", 1)
            for line in (source / "packs/dj2/profile.properties")
            .read_text()
            .splitlines()
            if line and not line.startswith("#")
        )
        self.assertIn(
            "omkalitydj2fix@" + version, profile["required.extensions"].split(",")
        )

    def test_archive_metadata_does_not_depend_on_host_os(self):
        self.assertEqual(entry("example.class").create_system, 0)
        self.assertEqual(entry("example.class").date_time, (2026, 1, 1, 0, 0, 0))

    def test_archive_order_matches_the_accepted_windows_build(self):
        paths = [
            Path("ExampleZ.class"),
            Path("Example_a.class"),
            Path("ExampleB.class"),
        ]
        self.assertEqual(
            [p.name for p in ordered(paths)],
            ["Example_a.class", "ExampleB.class", "ExampleZ.class"],
        )

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = b"pinned fixture bytes"
        self.pins = {
            "compiler": {
                "filename": "input.jar",
                "download": "https://example.invalid/input.jar",
                "sha256": hashlib.sha256(self.data).hexdigest(),
            }
        }

    def test_verified_cache_works_without_network(self):
        (self.root / "input.jar").write_bytes(self.data)
        opener = Mock(side_effect=AssertionError("Network must not run"))
        result = ensure_input("compiler", self.root, self.pins, opener=opener)
        self.assertEqual(result.read_bytes(), self.data)
        opener.assert_not_called()

    def test_bad_cache_is_not_overwritten(self):
        target = self.root / "input.jar"
        target.write_bytes(b"bad cached artifact")
        opener = Mock()
        with self.assertRaisesRegex(ValueError, "Cached dependency hash mismatch"):
            ensure_input("compiler", self.root, self.pins, opener=opener)
        self.assertEqual(target.read_bytes(), b"bad cached artifact")
        opener.assert_not_called()

    def test_verified_download_is_promoted(self):
        result = ensure_input(
            "compiler",
            self.root,
            self.pins,
            opener=Mock(return_value=Response(self.data)),
        )
        self.assertEqual(result.read_bytes(), self.data)
        self.assertEqual([p.name for p in self.root.iterdir()], ["input.jar"])

    def _download_error(self, status, retry_after):
        headers = {} if retry_after is None else {"Retry-After": retry_after}
        url = self.pins["compiler"]["download"]
        return HTTPError(url, status, "test response", headers, io.BytesIO())

    def test_download_recovers_after_rate_limit(self):
        cases = (
            (None, 2),
            ("soon", 2),
            ("6", 6),
            ("Fri, 01 Jan 2021 00:00:06 GMT", 6),
        )
        for header, delay in cases:
            with (
                self.subTest(header=header),
                tempfile.TemporaryDirectory(dir=self.root) as cache,
                patch("fetch_inputs.time.time", return_value=1609459200),
                patch("fetch_inputs.time.sleep") as sleep,
                patch("sys.stderr", new_callable=io.StringIO) as log,
            ):
                limited = self._download_error(429, header)
                opener = Mock(side_effect=[limited, Response(self.data)])
                result = ensure_input("compiler", cache, self.pins, opener=opener)
                self.assertEqual(result.read_bytes(), self.data)
                self.assertEqual(list(Path(cache).iterdir()), [result])
                self.assertTrue(limited.closed)
                sleep.assert_called_once_with(delay)
                self.assertIn("input.jar: HTTP 429", log.getvalue())
                self.assertEqual(opener.call_count, 2)

    def test_rate_limit_retries_are_bounded(self):
        cases = (
            (429, None, 4, [2, 5, 10]),
            (429, "25", 2, [25]),
            (429, "31", 1, []),
            (404, None, 1, []),
        )
        for status, header, attempts, delays in cases:
            with (
                self.subTest(status=status, header=header),
                patch("fetch_inputs.time.sleep") as sleep,
                patch("sys.stderr", new_callable=io.StringIO),
            ):
                opener = Mock(
                    side_effect=[self._download_error(status, header) for _ in range(5)]
                )
                with self.assertRaises(HTTPError) as failure:
                    ensure_input("compiler", self.root, self.pins, opener=opener)
                self.assertEqual(failure.exception.code, status)
                self.assertIn("Dependency: input.jar", failure.exception.__notes__)
                self.assertEqual(opener.call_count, attempts)
                self.assertEqual(
                    sleep.call_args_list, [call(delay) for delay in delays]
                )
                self.assertEqual(list(self.root.iterdir()), [])

    def test_download_checks_sha256_after_retry(self):
        opener = Mock(
            side_effect=[self._download_error(429, None), Response(b"corrupt")]
        )
        with (
            patch("fetch_inputs.time.sleep") as sleep,
            patch("sys.stderr", new_callable=io.StringIO),
            self.assertRaisesRegex(ValueError, "Downloaded dependency hash mismatch"),
        ):
            ensure_input("compiler", self.root, self.pins, opener=opener)
        sleep.assert_called_once_with(2)
        self.assertEqual(opener.call_count, 2)
        self.assertEqual(list(self.root.iterdir()), [])

    @unittest.skipUnless(os.name == "posix", "POSIX bind-mount permission contract")
    def test_public_compile_input_is_readable_across_container_users(self):
        result = ensure_input(
            "compiler",
            self.root,
            self.pins,
            opener=Mock(return_value=Response(self.data)),
        )
        self.assertEqual(stat.S_IMODE(result.stat().st_mode), 0o644)

    def test_corrupt_download_leaves_no_usable_artifact(self):
        with self.assertRaisesRegex(ValueError, "Downloaded dependency hash mismatch"):
            ensure_input(
                "compiler",
                self.root,
                self.pins,
                opener=Mock(return_value=Response(b"corrupt")),
            )
        self.assertEqual(list(self.root.iterdir()), [])

    def test_oversized_download_is_removed(self):
        with self.assertRaisesRegex(ValueError, "download budget"):
            ensure_input(
                "compiler",
                self.root,
                self.pins,
                opener=Mock(return_value=Response(self.data)),
                max_bytes=4,
            )
        self.assertEqual(list(self.root.iterdir()), [])

    def test_dependency_filename_cannot_escape_cache(self):
        self.pins["compiler"]["filename"] = "../input.jar"
        with self.assertRaisesRegex(ValueError, "Noncanonical"):
            ensure_input("compiler", self.root, self.pins)

    def artifact(self, entries):
        path = self.root / "fixture.jar"
        with zipfile.ZipFile(path, "w") as jar:
            for name in entries:
                jar.writestr(name, b"\xca\xfe\xba\xbe\x00\x00\x00\x34fixture")
        return path

    def test_minecraft_compile_only_classes_are_rejected(self):
        path = self.artifact(
            ["net/omkality/client/Example.class", "net/minecraft/network/Packet.class"]
        )
        with self.assertRaisesRegex(ValueError, "Foreign class"):
            inspect_jar(path, "client")

    def test_dependencies_cannot_be_bundled(self):
        path = self.artifact(["net/omkality/Example.class", "lib/forge.jar"])
        with self.assertRaisesRegex(ValueError, "Dependency, lab or test"):
            inspect_jar(path, "core")

    def test_pack_specific_classes_cannot_enter_core(self):
        path = self.artifact(["net/omkality/dj2/Example.class"])
        with self.assertRaisesRegex(ValueError, "Pack/client implementation"):
            inspect_jar(path, "core")

    def test_duplicate_archive_names_are_rejected(self):
        with self.assertWarns(UserWarning):
            path = self.artifact(["net/omkality/Example.class"] * 2)
        with self.assertRaisesRegex(ValueError, "Duplicate archive entry"):
            inspect_jar(path, "core")


if __name__ == "__main__":
    unittest.main()
