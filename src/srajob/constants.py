from __future__ import annotations

from pathlib import Path

# Root directory for test artifacts used by integration tests
TEST_ARTIFACTS_DIR: Path = Path("tests/test-artifacts").resolve()

# Centralized screenshots directory at the top level of test artifacts
TEST_ARTIFACTS_SCREENSHOTS_DIR: Path = (TEST_ARTIFACTS_DIR / "screenshots").resolve()

