"""
pm_agent/scanner.py

Scans the repository for TODO comments, stub patterns, and missing test files.
Produces a list of raw findings that the WBS builder can structure into tasks.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

_logger = logging.getLogger(__name__)


@dataclass
class ScanFinding:
    """A single TODO, stub, or missing-test finding from the codebase."""

    kind: str  # "todo", "stub", "missing_test"
    file: str  # relative path from repo root
    line: int | None  # line number (1-based), None for missing_test
    text: str  # the matched line or description
    module: str  # top-level directory, e.g. "news_articles"


@dataclass
class ScanResult:
    """Aggregated scan results across all scanned directories."""

    findings: list[ScanFinding] = field(default_factory=list)

    @property
    def todos(self) -> list[ScanFinding]:
        return [f for f in self.findings if f.kind == "todo"]

    @property
    def stubs(self) -> list[ScanFinding]:
        return [f for f in self.findings if f.kind == "stub"]

    @property
    def missing_tests(self) -> list[ScanFinding]:
        return [f for f in self.findings if f.kind == "missing_test"]

    def summary(self) -> dict[str, int]:
        return {
            "todos": len(self.todos),
            "stubs": len(self.stubs),
            "missing_tests": len(self.missing_tests),
            "total": len(self.findings),
        }


class CodebaseScanner:
    """
    Scans repository directories for TODOs, stubs, and missing tests.

    Args:
        repo_root:        Absolute path to the repository root.
        scan_dirs:        List of directory names to scan (relative to repo_root).
        scan_extensions:  File extensions to include (e.g., [".py"]).
        stub_patterns:    List of string patterns that indicate unfinished work.
    """

    def __init__(
        self,
        repo_root: str,
        scan_dirs: list[str],
        scan_extensions: list[str] | None = None,
        stub_patterns: list[str] | None = None,
    ):
        self.repo_root = Path(repo_root)
        self.scan_dirs = scan_dirs
        self.scan_extensions = scan_extensions or [".py"]
        self.stub_patterns = stub_patterns or [
            "# TODO",
            "TODO:",
            "is not yet implemented",
            "not yet implemented",
        ]

    def scan(self) -> ScanResult:
        """Run a full scan and return aggregated results."""
        result = ScanResult()

        for dir_name in self.scan_dirs:
            dir_path = self.repo_root / dir_name
            if not dir_path.is_dir():
                _logger.warning("Scan directory not found: %s", dir_path)
                continue

            _logger.info("Scanning %s", dir_name)
            self._scan_directory(dir_path, dir_name, result)

        # Check for missing test files
        self._check_missing_tests(result)

        _logger.info("Scan complete: %s", result.summary())
        return result

    def _scan_directory(
        self, dir_path: Path, module_name: str, result: ScanResult
    ) -> None:
        """Recursively scan a directory for TODO/stub patterns."""
        for root, _dirs, files in os.walk(dir_path):
            for filename in files:
                if not any(filename.endswith(ext) for ext in self.scan_extensions):
                    continue

                filepath = Path(root) / filename
                rel_path = str(filepath.relative_to(self.repo_root))
                self._scan_file(filepath, rel_path, module_name, result)

    def _scan_file(
        self, filepath: Path, rel_path: str, module_name: str, result: ScanResult
    ) -> None:
        """Scan a single file for TODO/stub patterns."""
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            _logger.warning("Could not read %s: %s", filepath, exc)
            return

        for line_num, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            for pattern in self.stub_patterns:
                if pattern.lower() in stripped.lower():
                    # Classify as "todo" if it's a comment, "stub" if it's in code
                    kind = "todo" if stripped.startswith("#") else "stub"
                    result.findings.append(
                        ScanFinding(
                            kind=kind,
                            file=rel_path,
                            line=line_num,
                            text=stripped,
                            module=module_name,
                        )
                    )
                    break  # one match per line is enough

    def _check_missing_tests(self, result: ScanResult) -> None:
        """Check whether scanned Python modules have corresponding test files."""
        tests_dir = self.repo_root / "tests"

        for dir_name in self.scan_dirs:
            dir_path = self.repo_root / dir_name
            if not dir_path.is_dir():
                continue

            for root, _dirs, files in os.walk(dir_path):
                for filename in files:
                    if not filename.endswith(".py"):
                        continue
                    if filename.startswith("_"):
                        continue

                    src_path = Path(root) / filename
                    rel_path = src_path.relative_to(self.repo_root)

                    # Expected test path: tests/<module>/test_<filename>
                    test_filename = f"test_{filename}"
                    test_path = tests_dir / rel_path.parent / test_filename

                    if not test_path.exists():
                        result.findings.append(
                            ScanFinding(
                                kind="missing_test",
                                file=str(rel_path),
                                line=None,
                                text=f"No test file found (expected {test_path.relative_to(self.repo_root)})",
                                module=dir_name,
                            )
                        )



