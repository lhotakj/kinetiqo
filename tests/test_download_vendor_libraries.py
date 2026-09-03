"""Unit tests for the unified vendor libraries manager script."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "development"))

import importlib.util

spec = importlib.util.spec_from_file_location(
    "download_vendor_libraries",
    str(_REPO_ROOT / "development" / "download-vendor-libraries.py"),
)
dvl = importlib.util.module_from_spec(spec)
sys.modules["download_vendor_libraries"] = dvl
spec.loader.exec_module(dvl)


class TestDownloadVendorLibraries(unittest.TestCase):
    """Test suite for vendor-libraries.yaml parsing and downloader logic."""

    def test_load_yaml_config(self):
        """Verify that default vendor-libraries.yaml loads cleanly and has required keys."""
        config_path = _REPO_ROOT / "development" / "vendor-libraries.yaml"
        config = dvl.load_yaml_config(config_path)

        self.assertIn("settings", config)
        self.assertIn("prerequisites", config)
        self.assertIn("libraries", config)

        self.assertIn("tailwind_cli", config["prerequisites"])
        libraries = config["libraries"]
        self.assertGreater(len(libraries), 0)

        # Check expected library IDs
        lib_ids = {lib["id"] for lib in libraries}
        expected_ids = {
            "tailwind",
            "htmx",
            "jquery",
            "leaflet",
            "chart",
            "datatables",
            "select2",
            "daterangepicker",
            "moment",
            "jszip",
            "sortable",
            "html2canvas",
        }
        self.assertTrue(expected_ids.issubset(lib_ids))

    def test_format_template_str_single_version(self):
        """Test template substitution with single version string."""
        template = "htmx-{version}.min.js"
        result = dvl.format_template_str(template, version="2.0.10", versions=None)
        self.assertEqual(result, "htmx-2.0.10.min.js")

    def test_format_template_str_versions_dict(self):
        """Test template substitution with multiple versions dictionary."""
        template = "chartjs-adapter-moment-{versions.moment}.min.js"
        versions = {"chartjs": "4.5.1", "moment": "1.0.1"}
        result = dvl.format_template_str(template, version=None, versions=versions)
        self.assertEqual(result, "chartjs-adapter-moment-1.0.1.min.js")

    def test_detect_platform_os_arch(self):
        """Test detection of platform OS and architecture mappings."""
        os_map = {"linux": "linux", "darwin": "macos", "windows": "windows.exe"}
        arch_map = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64"}

        with patch("platform.system", return_value="Linux"), patch("platform.machine", return_value="x86_64"):
            sys_os, sys_arch = dvl.detect_platform_os_arch(os_map, arch_map)
            self.assertEqual(sys_os, "linux")
            self.assertEqual(sys_arch, "x64")

        with patch("platform.system", return_value="Darwin"), patch("platform.machine", return_value="arm64"):
            sys_os, sys_arch = dvl.detect_platform_os_arch(os_map, arch_map)
            self.assertEqual(sys_os, "macos")
            self.assertEqual(sys_arch, "arm64")

    @patch("pathlib.Path.is_file", return_value=False)
    @patch("pathlib.Path.mkdir")
    @patch("builtins.open", new_callable=unittest.mock.mock_open)
    def test_download_file_new_download(self, mock_open_file, mock_mkdir, mock_is_file):
        """Test downloading a file when it does not exist locally."""
        mock_response = MagicMock()
        mock_response.content = b"console.log('mock js content');"

        mock_httpx = MagicMock()
        mock_httpx.get.return_value = mock_response

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            dest_path = _REPO_ROOT / "src" / "kinetiqo" / "web" / "static" / "vendor" / "mock_test.js"
            downloaded, _ = dvl.download_file("https://example.com/test.js", dest_path, force=False)
            self.assertTrue(downloaded)
            mock_open_file.assert_called_once_with(dest_path.resolve(), "wb")

    @patch("pathlib.Path.is_file", return_value=True)
    def test_download_file_skip_existing(self, mock_is_file):
        """Test skipping download when file exists and force=False."""
        dest_path = _REPO_ROOT / "src" / "kinetiqo" / "web" / "static" / "vendor" / "mock_test.js"
        downloaded, status = dvl.download_file("https://example.com/test.js", dest_path, force=False)
        self.assertFalse(downloaded)


if __name__ == "__main__":
    unittest.main()
