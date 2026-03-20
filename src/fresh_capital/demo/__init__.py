"""Fixture-driven demo runner for the Fresh Capital Flow Strategy MVP."""

from fresh_capital.demo.runner import (
    DemoFixtureSummary,
    DemoEndToEndResult,
    DemoRunRequest,
    DemoRunResult,
    DemoWrittenArtifacts,
    load_demo_fixture,
    main,
    run_demo_end_to_end,
    run_demo_fixture,
)

__all__ = [
    "DemoFixtureSummary",
    "DemoEndToEndResult",
    "DemoRunRequest",
    "DemoRunResult",
    "DemoWrittenArtifacts",
    "load_demo_fixture",
    "main",
    "run_demo_end_to_end",
    "run_demo_fixture",
]
