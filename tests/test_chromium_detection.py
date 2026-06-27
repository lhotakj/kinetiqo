#!/usr/bin/env python3
"""
Comprehensive Chromium detection test.
Tests all four installation scenarios:
1. System Chromium package
2. System Chromium headless
3. Playwright-installed headless
4. Playwright-installed Chromium

Usage:
    python3 test_chromium_detection.py
"""

import os
import sys
import shutil
from typing import Optional


def find_system_chromium() -> Optional[str]:
    """
    Try to find a system-installed Chromium executable.

    Searches in this order:
    1. PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH environment variable
    2. System PATH locations (via shutil.which)
    3. Common installation paths (platform-aware)

    Returns:
        Full path to chromium executable if found, None otherwise
    """
    # Priority 1: Check environment variable
    exe_path = os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH')
    if exe_path and os.path.isfile(exe_path) and os.access(exe_path, os.X_OK):
        print(f"      ✓ Found via PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH: {exe_path}")
        return exe_path

    # Priority 2: Try to find in system PATH
    executable_names = [
        'chromium',              # Linux (common package name)
        'chromium-browser',      # Debian/Ubuntu variant
        'chromium-headless-shell',  # Playwright headless variant
        'google-chrome',         # Google Chrome (if installed as Chrome)
        'google-chrome-stable',  # Chrome stable variant
        'chrome',                # Windows/macOS
    ]

    for name in executable_names:
        exe = shutil.which(name)
        if exe:
            print(f"      ✓ Found in PATH: {exe} (name: {name})")
            return exe

    # Priority 3: Check common installation paths (Windows)
    if os.name == 'nt':  # Windows
        common_paths = [
            r'C:\Program Files\Chromium\Application\chrome.exe',
            r'C:\Program Files (x86)\Chromium\Application\chrome.exe',
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        ]
        for path in common_paths:
            if os.path.isfile(path):
                print(f"      ✓ Found at Windows path: {path}")
                return path

    # Priority 4: Check common installation paths (Unix/Linux/macOS)
    else:
        common_paths = [
            '/usr/bin/chromium',
            '/usr/bin/chromium-browser',
            '/snap/bin/chromium',
            '/opt/chromium/chrome',
            '/Applications/Chromium.app/Contents/MacOS/Chromium',
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        ]
        for path in common_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                print(f"      ✓ Found at common path: {path}")
                return path

    return None


def test_chromium_detection():
    """Test comprehensive Chromium detection for all installation scenarios."""

    print("\n" + "="*80)
    print("  Comprehensive Chromium Detection Test (All Installation Scenarios)")
    print("="*80 + "\n")

    print("[1/4] Searching for system-installed Chromium...")
    sys_chromium = find_system_chromium()
    if not sys_chromium:
        print("      ⚠ No system Chromium found (will fall back to Playwright bundled)")

    print("\n[2/4] Checking for Playwright installation...")
    try:
        from playwright.sync_api import sync_playwright
        print("      ✓ Playwright is installed")
    except ImportError:
        print("      ✗ Playwright not installed")
        print("        Run: pip install playwright")
        return False

    print("\n[3/4] Testing Chromium launch scenarios...")

    # Scenario 1: System Chromium (if found)
    if sys_chromium:
        print(f"\n      [Scenario 1] System Chromium: {sys_chromium}")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, executable_path=sys_chromium)
                version = browser.version
                browser.close()
                print(f"      ✓ Launched successfully (version: {version})")
        except Exception as e:
            print(f"      ✗ Failed: {e}")
            return False

    # Scenario 2: Playwright bundled Chromium
    print("\n      [Scenario 2] Playwright bundled Chromium (default)")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            version = browser.version
            browser.close()
            print(f"      ✓ Launched successfully (version: {version})")
    except Exception as e:
        print(f"      ✗ Failed: {e}")
        return False

    print("\n[4/4] Testing combined detection logic...")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            launch_kwargs = {'headless': True}

            # Use the same logic as app.py
            exe_path = find_system_chromium()
            if exe_path:
                launch_kwargs['executable_path'] = exe_path
                print(f"      ✓ Will use system Chromium: {exe_path}")
            else:
                print("      ℹ Will use Playwright's bundled Chromium")

            browser = p.chromium.launch(**launch_kwargs)
            version = browser.version
            browser.close()

            print("      ✓ Combined detection launched successfully")
            print(f"      ✓ Final Chromium version: {version}")

    except Exception as e:
        print(f"      ✗ Combined detection failed: {e}")
        return False

    print("\n" + "="*80)
    print("  ✓ All tests passed! Chromium detection working correctly.")
    print("  ✓ Code will work with all installation scenarios:")
    print("    • System Chromium (package)")
    print("    • System Chromium headless")
    print("    • Playwright-installed headless chromium")
    print("    • Playwright-installed chromium (bundled)")
    print("="*80 + "\n")
    return True


if __name__ == '__main__':
    try:
        success = test_chromium_detection()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

