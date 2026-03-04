"""UAT test suite registry.

Imports all suite modules and registers them with a UATRunner instance.
"""

from __future__ import annotations

from src.uat.runner import UATRunner
from src.uat.suites import (
    bayesian,
    data_pipeline,
    end_to_end,
    ensemble,
    event_detection,
    ml_training,
    regime,
)


def build_runner() -> UATRunner:
    """Create a UATRunner with all suites registered."""
    runner = UATRunner()
    runner.register_suite(
        data_pipeline.SUITE_ID, data_pipeline.SUITE_NAME, data_pipeline.TESTS,
    )
    runner.register_suite(
        event_detection.SUITE_ID, event_detection.SUITE_NAME, event_detection.TESTS,
    )
    runner.register_suite(
        bayesian.SUITE_ID, bayesian.SUITE_NAME, bayesian.TESTS,
    )
    runner.register_suite(
        ml_training.SUITE_ID, ml_training.SUITE_NAME, ml_training.TESTS,
    )
    runner.register_suite(
        regime.SUITE_ID, regime.SUITE_NAME, regime.TESTS,
    )
    runner.register_suite(
        ensemble.SUITE_ID, ensemble.SUITE_NAME, ensemble.TESTS,
    )
    runner.register_suite(
        end_to_end.SUITE_ID, end_to_end.SUITE_NAME, end_to_end.TESTS,
    )
    return runner
