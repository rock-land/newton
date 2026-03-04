"""UAT test runner API endpoints (T-402).

GET  /api/v1/uat/suites — list registered test suites with counts
POST /api/v1/uat/run    — execute suite, individual test, or all tests
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.api.schemas import (
    UATRunRequest,
    UATRunResponse,
    UATRunSummary,
    UATSuiteResponse,
    UATSuitesResponse,
    UATTestResult,
)
from src.uat.suites import build_runner

router = APIRouter(tags=["uat"])

_runner = build_runner()


@router.get("/uat/suites")
def list_suites() -> UATSuitesResponse:
    """List all UAT test suites with test counts."""
    suites = _runner.list_suites()
    return UATSuitesResponse(
        suites=[
            UATSuiteResponse(id=s.id, name=s.name, test_count=s.test_count)
            for s in suites
        ],
    )


@router.post("/uat/run")
def run_tests(body: UATRunRequest) -> UATRunResponse:
    """Execute UAT tests by suite, individual test ID, or all.

    - ``suite`` set: run all tests in that suite
    - ``test_id`` set: run a single test
    - both null: run all tests
    """
    if body.suite and not _runner.has_suite(body.suite):
        raise HTTPException(status_code=404, detail=f"Suite not found: {body.suite}")
    if body.test_id and not _runner.has_test(body.test_id):
        raise HTTPException(status_code=404, detail=f"Test not found: {body.test_id}")

    if body.test_id:
        results = _runner.run_test(body.test_id)
    elif body.suite:
        results = _runner.run_suite(body.suite)
    else:
        results = _runner.run_all()

    passed = sum(1 for r in results if r.status == "pass")
    total_ms = sum(r.duration_ms for r in results)

    return UATRunResponse(
        results=[
            UATTestResult(
                id=r.id,
                name=r.name,
                suite=r.suite,
                status=r.status,
                duration_ms=r.duration_ms,
                details=r.details,
                error=r.error,
            )
            for r in results
        ],
        summary=UATRunSummary(
            total=len(results),
            passed=passed,
            failed=len(results) - passed,
            duration_ms=total_ms,
        ),
    )
