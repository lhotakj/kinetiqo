"""Unit tests for check-pypi-updates.py development script."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Dynamic import of development/check-pypi-updates.py
spec = importlib.util.spec_from_file_location(
    "check_pypi_updates",
    str(_REPO_ROOT / "development" / "check-pypi-updates.py"),
)
assert spec and spec.loader
cpu = importlib.util.module_from_spec(spec)
sys.modules["check_pypi_updates"] = cpu
spec.loader.exec_module(cpu)


class TestCheckPyPIUpdates(unittest.TestCase):
    """Test suite for check-pypi-updates validation, parsing, and execution."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(dir=str(_REPO_ROOT))
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # Path Traversal & Validation
    # -------------------------------------------------------------------------

    def test_validate_safe_path_inside_repo(self):
        """Paths strictly inside repository root pass validation."""
        test_file = self.test_dir / "requirements.txt"
        test_file.write_text("requests==2.32.0\n", encoding="utf-8")

        safe = cpu.validate_safe_path(test_file)
        self.assertEqual(safe, test_file.resolve())

    def test_validate_safe_path_repo_root(self):
        """Repository root itself is allowed as a boundary."""
        self.assertEqual(cpu.validate_safe_path(_REPO_ROOT), _REPO_ROOT.resolve())

    def test_validate_safe_path_traversal_relative_rejected(self):
        """Relative path traversal outside repository root is rejected with ValueError."""
        unsafe = _REPO_ROOT / ".." / "outside.txt"
        with self.assertRaises(ValueError) as ctx:
            cpu.validate_safe_path(unsafe)
        self.assertIn("Path traversal detected", str(ctx.exception))

    def test_validate_safe_path_traversal_absolute_rejected(self):
        """Absolute system paths outside repository root are rejected."""
        unsafe = Path("/etc/passwd")
        with self.assertRaises(ValueError) as ctx:
            cpu.validate_safe_path(unsafe)
        self.assertIn("Path traversal detected", str(ctx.exception))

    # -------------------------------------------------------------------------
    # File Parsing & Atomic Writes
    # -------------------------------------------------------------------------

    def test_parse_requirements_valid(self):
        """Existing requirements file is parsed into list of stripped lines."""
        req_file = self.test_dir / "reqs.txt"
        req_file.write_text("flask==3.0.0\nrequests>=2.0.0\n# comment\n", encoding="utf-8")

        lines = cpu.parse_requirements(req_file)
        self.assertEqual(lines, ["flask==3.0.0", "requests>=2.0.0", "# comment"])

    def test_parse_requirements_missing_file(self):
        """Non-existent file inside repo returns empty list without error."""
        missing = self.test_dir / "non_existent.txt"
        self.assertEqual(cpu.parse_requirements(missing), [])

    def test_parse_requirements_traversal_rejected(self):
        """Traversal path is skipped and returns empty list."""
        unsafe = Path("/etc/shadow")
        self.assertEqual(cpu.parse_requirements(unsafe), [])

    def test_write_atomic_success(self):
        """write_atomic writes all lines atomically and replaces target file."""
        target = self.test_dir / "output.txt"
        target.write_text("old content\n", encoding="utf-8")

        cpu.write_atomic(target, ["line1", "line2"])
        self.assertEqual(target.read_text(encoding="utf-8"), "line1\nline2\n")

    def test_write_atomic_traversal_raises(self):
        """write_atomic raises ValueError on traversal paths."""
        unsafe = Path("/tmp/unsafe_file.txt")
        with self.assertRaises(ValueError):
            cpu.write_atomic(unsafe, ["line1"])

    def test_make_backup_success(self):
        """make_backup creates a timestamped .bak file with exact content."""
        target = self.test_dir / "reqs.txt"
        target.write_text("flask==3.0.0\n", encoding="utf-8")

        bak = cpu.make_backup(target)
        self.assertTrue(bak.exists())
        self.assertIn(".bak-", bak.name)
        self.assertEqual(bak.read_text(encoding="utf-8"), "flask==3.0.0\n")

    def test_update_file_with_backup(self):
        """update_file creates backup and writes new lines when backup=True."""
        target = self.test_dir / "reqs.txt"
        target.write_text("old==1.0\n", encoding="utf-8")

        cpu.update_file(target, ["new==2.0"], backup=True)
        self.assertEqual(target.read_text(encoding="utf-8"), "new==2.0\n")

        backups = list(self.test_dir.glob("reqs.txt.bak-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "old==1.0\n")

    # -------------------------------------------------------------------------
    # Target Collection & Path Filtering
    # -------------------------------------------------------------------------

    def test_collect_targets_explicit_paths(self):
        """collect_targets validates and returns explicit paths provided."""
        t1 = self.test_dir / "req1.txt"
        t2 = self.test_dir / "req2.txt"
        t1.write_text("click==8.0\n", encoding="utf-8")
        t2.write_text("pandas==2.0\n", encoding="utf-8")

        targets = cpu.collect_targets([str(t1), str(t2)])
        self.assertEqual(len(targets), 2)
        self.assertIn(t1.resolve(), targets)
        self.assertIn(t2.resolve(), targets)

    def test_collect_targets_filters_unsafe_paths(self):
        """collect_targets drops paths attempting directory traversal."""
        t1 = self.test_dir / "req1.txt"
        t1.write_text("click==8.0\n", encoding="utf-8")

        targets = cpu.collect_targets([str(t1), "../../etc/passwd", "/bin/sh"])
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0], t1.resolve())

    def test_collect_targets_default_discovery(self):
        """collect_targets without arguments discovers requirements.txt in repo."""
        targets = cpu.collect_targets([])
        self.assertGreater(len(targets), 0)
        self.assertTrue(any(t.name == "requirements.txt" for t in targets))

    # -------------------------------------------------------------------------
    # PyPI Version Lookup & Requirement Analysis
    # -------------------------------------------------------------------------

    @patch("requests.get")
    def test_get_latest_version_success(self, mock_get):
        """get_latest_version retrieves release version from PyPI response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"info": {"version": "3.1.4"}}
        mock_get.return_value = mock_resp

        version = cpu.get_latest_version("flask")
        self.assertEqual(version, "3.1.4")
        mock_get.assert_called_once_with("https://pypi.org/pypi/flask/json", timeout=15)

    @patch("requests.get")
    def test_get_latest_version_not_found(self, mock_get):
        """Non-200 PyPI response returns None."""
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        self.assertIsNone(cpu.get_latest_version("non_existent_pkg_xyz"))

    @patch("requests.get")
    def test_get_latest_version_network_error(self, mock_get):
        """Network exception returns None gracefully."""
        import requests
        mock_get.side_effect = requests.RequestException("DNS lookup failed")

        self.assertIsNone(cpu.get_latest_version("flask"))

    @patch.object(cpu, "get_latest_version", return_value="3.1.4")
    def test_analyze_line_pinned_outdated(self, mock_version):
        """analyze_line parses pinned requirement and notes latest version."""
        res = cpu.analyze_line("Flask==3.0.0")
        self.assertIsNotNone(res)
        self.assertEqual(res["name"], "Flask")
        self.assertEqual(res["latest"], "3.1.4")

    def test_analyze_line_comment_or_empty(self):
        """Comments and blank lines return None."""
        self.assertIsNone(cpu.analyze_line("# This is a comment"))
        self.assertIsNone(cpu.analyze_line("   "))
        self.assertIsNone(cpu.analyze_line(""))

    def test_build_new_requirement_with_and_without_extras(self):
        """build_new_requirement formats package==latest and preserves extras."""
        from packaging.requirements import Requirement

        req_simple = Requirement("flask>=2.0.0")
        self.assertEqual(cpu.build_new_requirement(req_simple, "3.1.4"), "flask==3.1.4")

        req_extras = Requirement("flask[async]>=2.0.0")
        self.assertEqual(cpu.build_new_requirement(req_extras, "3.1.4"), "flask[async]==3.1.4")

    # -------------------------------------------------------------------------
    # End-to-End Processing & CLI Args
    # -------------------------------------------------------------------------

    @patch.object(cpu, "get_latest_version", return_value="3.1.4")
    def test_process_file_dry_run(self, mock_version):
        """Dry-run identifies available update but does not write changes."""
        req_file = self.test_dir / "requirements.txt"
        req_file.write_text("Flask==3.0.0\n", encoding="utf-8")

        args = MagicMock(apply=False, force=False, backup=False)
        any_updates, written = cpu.process_file(req_file, args)

        self.assertTrue(any_updates)
        self.assertFalse(written)
        self.assertEqual(req_file.read_text(encoding="utf-8"), "Flask==3.0.0\n")

    @patch.object(cpu, "get_latest_version", return_value="3.1.4")
    def test_process_file_apply_with_force(self, mock_version):
        """apply with force=True updates the file with latest pinned version."""
        req_file = self.test_dir / "requirements.txt"
        req_file.write_text("Flask==3.0.0\n", encoding="utf-8")

        args = MagicMock(apply=True, force=True, backup=False)
        any_updates, written = cpu.process_file(req_file, args)

        self.assertTrue(any_updates)
        self.assertTrue(written)
        self.assertEqual(req_file.read_text(encoding="utf-8"), "Flask==3.1.4\n")

    def test_parse_args(self):
        """parse_args extracts all CLI flags accurately."""
        with patch("sys.argv", ["check-pypi-updates.py", "--apply", "--force", "--backup", "-v", "reqs.txt"]):
            args = cpu.parse_args()
            self.assertTrue(args.apply)
            self.assertTrue(args.force)
            self.assertTrue(args.backup)
            self.assertTrue(args.verbose)
            self.assertEqual(args.paths, ["reqs.txt"])

    def test_print_table_header(self):
        """print_table_header prints formatted column names."""
        with patch("builtins.print") as mock_print:
            cpu.print_table_header()
            mock_print.assert_called()

    @patch.object(cpu, "get_latest_version", return_value="1.2.3")
    def test_analyze_line_invalid_fallback(self, mock_version):
        """analyze_line falls back to raw token extraction when Requirement parsing fails."""
        res = cpu.analyze_line("custom-pkg===invalid==version")
        self.assertIsNotNone(res)
        self.assertEqual(res["name"], "custom-pkg")
        self.assertEqual(res["latest"], "1.2.3")

    def test_process_file_empty(self):
        """process_file on empty file skips and returns (False, False)."""
        req_file = self.test_dir / "empty.txt"
        req_file.write_text("", encoding="utf-8")
        args = MagicMock(apply=False, force=False, backup=False)
        any_updates, written = cpu.process_file(req_file, args)
        self.assertFalse(any_updates)
        self.assertFalse(written)

    @patch.object(cpu, "get_latest_version", return_value="3.1.4")
    def test_process_file_already_up_to_date(self, mock_version):
        """process_file on up-to-date pinned package returns (False, False)."""
        req_file = self.test_dir / "requirements.txt"
        req_file.write_text("Flask==3.1.4\n", encoding="utf-8")
        args = MagicMock(apply=True, force=False, backup=False)
        any_updates, written = cpu.process_file(req_file, args)
        self.assertFalse(any_updates)
        self.assertFalse(written)

    @patch.object(cpu, "get_latest_version", return_value="3.1.4")
    @patch.object(cpu, "confirm", return_value=False)
    def test_process_file_apply_declined(self, mock_confirm, mock_version):
        """process_file aborts write when user declines confirmation."""
        req_file = self.test_dir / "requirements.txt"
        req_file.write_text("Flask==3.0.0\n", encoding="utf-8")
        args = MagicMock(apply=True, force=False, backup=False)
        any_updates, written = cpu.process_file(req_file, args)
        self.assertTrue(any_updates)
        self.assertFalse(written)
        self.assertEqual(req_file.read_text(encoding="utf-8"), "Flask==3.0.0\n")

    @patch.object(cpu, "collect_targets", return_value=[])
    def test_main_no_targets(self, mock_targets):
        """main returns 1 if no target files found."""
        with patch("sys.argv", ["check-pypi-updates.py"]):
            self.assertEqual(cpu.main(), 1)

    @patch.object(cpu, "collect_targets")
    @patch.object(cpu, "process_file", return_value=(True, True))
    def test_main_with_updates(self, mock_process, mock_targets):
        """main returns 0 when updates are processed."""
        mock_targets.return_value = [self.test_dir / "reqs.txt"]
        with patch("sys.argv", ["check-pypi-updates.py", "--apply", "--force"]):
            self.assertEqual(cpu.main(), 0)

    @patch.object(cpu, "collect_targets")
    @patch.object(cpu, "process_file", return_value=(False, False))
    def test_main_no_updates(self, mock_process, mock_targets):
        """main returns 0 when no packages need updates."""
        mock_targets.return_value = [self.test_dir / "reqs.txt"]
        with patch("sys.argv", ["check-pypi-updates.py"]):
            self.assertEqual(cpu.main(), 0)


if __name__ == "__main__":
    unittest.main()
