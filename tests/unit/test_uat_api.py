"""Tests for UAT test runner framework and API endpoints (T-402)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.app import app
from src.uat.runner import UATResult, UATRunner, UATSuiteInfo, UATTest


# ---------------------------------------------------------------------------
# Runner framework tests
# ---------------------------------------------------------------------------


class TestUATRunner:
    """Tests for the UATRunner class."""

    def _make_runner(self) -> UATRunner:
        runner = UATRunner()
        runner.register_suite(
            "suite_a",
            "Suite A",
            [
                UATTest(id="A-01", name="Test one", suite="suite_a", fn=lambda: "ok"),
                UATTest(id="A-02", name="Test two", suite="suite_a", fn=lambda: "ok"),
            ],
        )
        runner.register_suite(
            "suite_b",
            "Suite B",
            [
                UATTest(
                    id="B-01",
                    name="Failing test",
                    suite="suite_b",
                    fn=self._failing_test,
                ),
            ],
        )
        return runner

    @staticmethod
    def _failing_test() -> str:
        msg = "expected failure"
        raise AssertionError(msg)

    def test_list_suites(self) -> None:
        runner = self._make_runner()
        suites = runner.list_suites()
        assert len(suites) == 2
        assert all(isinstance(s, UATSuiteInfo) for s in suites)
        ids = {s.id for s in suites}
        assert ids == {"suite_a", "suite_b"}

    def test_run_suite(self) -> None:
        runner = self._make_runner()
        results = runner.run_suite("suite_a")
        assert len(results) == 2
        assert all(r.status == "pass" for r in results)

    def test_run_single_test(self) -> None:
        runner = self._make_runner()
        results = runner.run_test("A-01")
        assert len(results) == 1
        assert results[0].id == "A-01"
        assert results[0].status == "pass"

    def test_run_failing_test(self) -> None:
        runner = self._make_runner()
        results = runner.run_test("B-01")
        assert len(results) == 1
        assert results[0].status == "fail"
        assert results[0].error is not None

    def test_run_all(self) -> None:
        runner = self._make_runner()
        results = runner.run_all()
        assert len(results) == 3
        passed = [r for r in results if r.status == "pass"]
        failed = [r for r in results if r.status == "fail"]
        assert len(passed) == 2
        assert len(failed) == 1

    def test_run_unknown_suite_returns_empty(self) -> None:
        runner = self._make_runner()
        results = runner.run_suite("nonexistent")
        assert results == []

    def test_run_unknown_test_returns_empty(self) -> None:
        runner = self._make_runner()
        results = runner.run_test("Z-99")
        assert results == []

    def test_has_suite(self) -> None:
        runner = self._make_runner()
        assert runner.has_suite("suite_a")
        assert not runner.has_suite("nonexistent")

    def test_has_test(self) -> None:
        runner = self._make_runner()
        assert runner.has_test("A-01")
        assert not runner.has_test("Z-99")

    def test_result_fields(self) -> None:
        runner = self._make_runner()
        results = runner.run_test("A-01")
        r = results[0]
        assert isinstance(r, UATResult)
        assert r.id == "A-01"
        assert r.name == "Test one"
        assert r.suite == "suite_a"
        assert r.status == "pass"
        assert r.duration_ms >= 0
        assert r.details == "ok"
        assert r.error is None

    def test_error_test_status(self) -> None:
        runner = UATRunner()
        runner.register_suite(
            "err",
            "Error Suite",
            [
                UATTest(
                    id="ERR-01",
                    name="Error test",
                    suite="err",
                    fn=lambda: 1 / 0,  # type: ignore[return-value]
                ),
            ],
        )
        results = runner.run_test("ERR-01")
        assert results[0].status == "error"
        assert "ZeroDivisionError" in (results[0].error or "")


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


client = TestClient(app)


class TestUATSuitesEndpoint:
    """Tests for GET /api/v1/uat/suites."""

    def test_list_suites_returns_200(self) -> None:
        resp = client.get("/api/v1/uat/suites")
        assert resp.status_code == 200

    def test_list_suites_has_7_suites(self) -> None:
        resp = client.get("/api/v1/uat/suites")
        data = resp.json()
        assert "suites" in data
        assert len(data["suites"]) == 7

    def test_suite_fields_present(self) -> None:
        resp = client.get("/api/v1/uat/suites")
        suite = resp.json()["suites"][0]
        assert "id" in suite
        assert "name" in suite
        assert "test_count" in suite
        assert isinstance(suite["test_count"], int)
        assert suite["test_count"] > 0

    def test_expected_suite_ids(self) -> None:
        resp = client.get("/api/v1/uat/suites")
        ids = {s["id"] for s in resp.json()["suites"]}
        expected = {
            "data_pipeline", "event_detection", "bayesian",
            "ml_training", "regime", "ensemble", "end_to_end",
        }
        assert ids == expected

    def test_total_test_count(self) -> None:
        resp = client.get("/api/v1/uat/suites")
        total = sum(s["test_count"] for s in resp.json()["suites"])
        assert total == 28


class TestUATRunEndpoint:
    """Tests for POST /api/v1/uat/run."""

    def test_run_single_test(self) -> None:
        resp = client.post("/api/v1/uat/run", json={"test_id": "DP-01"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["id"] == "DP-01"
        assert data["results"][0]["status"] == "pass"
        assert data["summary"]["total"] == 1
        assert data["summary"]["passed"] == 1

    def test_run_suite(self) -> None:
        resp = client.post("/api/v1/uat/run", json={"suite": "regime"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 4
        assert all(r["suite"] == "regime" for r in data["results"])
        assert data["summary"]["total"] == 4

    def test_run_all(self) -> None:
        resp = client.post("/api/v1/uat/run", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["total"] == 28
        assert data["summary"]["passed"] == 28
        assert data["summary"]["failed"] == 0

    def test_result_fields(self) -> None:
        resp = client.post("/api/v1/uat/run", json={"test_id": "E2E-01"})
        result = resp.json()["results"][0]
        assert "id" in result
        assert "name" in result
        assert "suite" in result
        assert "status" in result
        assert "duration_ms" in result
        assert "details" in result
        assert "error" in result

    def test_summary_fields(self) -> None:
        resp = client.post("/api/v1/uat/run", json={"test_id": "DP-01"})
        summary = resp.json()["summary"]
        assert "total" in summary
        assert "passed" in summary
        assert "failed" in summary
        assert "duration_ms" in summary

    def test_unknown_suite_returns_404(self) -> None:
        resp = client.post("/api/v1/uat/run", json={"suite": "nonexistent"})
        assert resp.status_code == 404

    def test_unknown_test_returns_404(self) -> None:
        resp = client.post("/api/v1/uat/run", json={"test_id": "ZZ-99"})
        assert resp.status_code == 404
