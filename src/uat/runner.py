"""UAT test runner framework.

Provides the UATTest, UATSuiteInfo, UATResult, and UATRunner classes
for registering and executing behavioral tests via /api/v1/uat endpoints.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class UATResult:
    """Result of a single UAT test execution."""

    id: str
    name: str
    suite: str
    status: str  # "pass" | "fail" | "error"
    duration_ms: int
    details: str
    error: str | None = None


@dataclass(frozen=True)
class UATSuiteInfo:
    """Summary info for a test suite."""

    id: str
    name: str
    test_count: int


@dataclass(frozen=True)
class UATTest:
    """Definition of a single UAT test."""

    id: str
    name: str
    suite: str
    fn: Callable[[], str]  # Returns details string on success, raises on failure


class UATRunner:
    """Registry and executor for UAT behavioral tests."""

    def __init__(self) -> None:
        self._suites: dict[str, list[UATTest]] = {}
        self._suite_names: dict[str, str] = {}
        self._tests: dict[str, UATTest] = {}

    def register_suite(self, suite_id: str, name: str, tests: list[UATTest]) -> None:
        """Register a test suite with its tests."""
        self._suites[suite_id] = tests
        self._suite_names[suite_id] = name
        for test in tests:
            self._tests[test.id] = test

    def list_suites(self) -> list[UATSuiteInfo]:
        """Return summary info for all registered suites."""
        return [
            UATSuiteInfo(id=sid, name=self._suite_names[sid], test_count=len(tests))
            for sid, tests in self._suites.items()
        ]

    def run_suite(self, suite_id: str) -> list[UATResult]:
        """Run all tests in a specific suite."""
        tests = self._suites.get(suite_id)
        if tests is None:
            return []
        return [self._run_test(t) for t in tests]

    def run_test(self, test_id: str) -> list[UATResult]:
        """Run a single test by ID."""
        test = self._tests.get(test_id)
        if test is None:
            return []
        return [self._run_test(test)]

    def run_all(self) -> list[UATResult]:
        """Run all tests across all suites."""
        results: list[UATResult] = []
        for tests in self._suites.values():
            for test in tests:
                results.append(self._run_test(test))
        return results

    def has_suite(self, suite_id: str) -> bool:
        """Check if a suite exists."""
        return suite_id in self._suites

    def has_test(self, test_id: str) -> bool:
        """Check if a test exists."""
        return test_id in self._tests

    def _run_test(self, test: UATTest) -> UATResult:
        """Execute a single test and return its result."""
        start = time.monotonic()
        try:
            details = test.fn()
            elapsed = int((time.monotonic() - start) * 1000)
            return UATResult(
                id=test.id,
                name=test.name,
                suite=test.suite,
                status="pass",
                duration_ms=elapsed,
                details=details,
            )
        except AssertionError as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            return UATResult(
                id=test.id,
                name=test.name,
                suite=test.suite,
                status="fail",
                duration_ms=elapsed,
                details=str(exc) or "Assertion failed",
                error=traceback.format_exc(),
            )
        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            return UATResult(
                id=test.id,
                name=test.name,
                suite=test.suite,
                status="error",
                duration_ms=elapsed,
                details=f"Unexpected error: {exc}",
                error=traceback.format_exc(),
            )
