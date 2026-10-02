"""
Tests for the Java analysis pipeline: detector registration, exception
isolation, issue deduplication, score clamping and degradation paths.
"""

from pathlib import Path

import pytest

from analyzer_engine import StaticAnalyzerEngine
from detectors.base import CodeSmell, registered_detectors, registry_conflicts
from detectors.naming_docs import NamingSmells
from utils.helpers import (
    PENALTY_PER_WEIGHT,
    calculate_normalized_score,
    calculate_weighted_penalty,
    deduplicate_issues,
)

SAMPLE_CODE = (Path(__file__).parent / "sample_data" / "SampleSmells.java").read_text()


def test_registration_order_is_priority_driven():
    ids = [c.detector_id for c in registered_detectors() if c.config_key]
    assert ids == ["design", "implementation", "naming", "documentation"]


def test_rule_id_collision_first_registered_wins():
    class DupFirst(CodeSmell):
        detector_id = "dup-test"
        priority = 999
        config_key = ""

        def detect(self, tree, lines):
            return []

    before = len(registry_conflicts())

    class DupSecond(CodeSmell):
        detector_id = "dup-test"
        priority = 1
        config_key = ""

        def detect(self, tree, lines):
            return []

    conflicts = registry_conflicts()
    assert len(conflicts) == before + 1
    assert conflicts[-1] == {
        "detector_id": "dup-test",
        "kept": "DupFirst",
        "skipped": "DupSecond",
    }
    active = next(c for c in registered_detectors() if c.detector_id == "dup-test")
    assert active.__name__ == "DupFirst"


def test_registry_only_detectors_are_not_auto_enabled():
    engine = StaticAnalyzerEngine(SAMPLE_CODE)
    assert [d.detector_id for d in engine.detectors] == [
        "design", "implementation", "naming", "documentation",
    ]


def test_detector_exception_is_isolated_and_excluded_from_score():
    class Boom(CodeSmell):
        detector_id = "boom-test"
        priority = 5
        config_key = ""

        def detect(self, tree, lines):
            raise RuntimeError("boom")

    engine = StaticAnalyzerEngine(SAMPLE_CODE)
    engine.detectors = [Boom(), NamingSmells()]
    issues, _ = engine.run()

    first, second = engine.pipeline_report
    assert first["status"] == "degraded"
    assert "boom" in first["error"]
    assert first["hits"] == 0
    assert first["normalized_score"] is None
    assert second["status"] == "ok"

    assert all(i["Category"] == "Naming" for i in issues)
    assert engine.quality_score == calculate_normalized_score(issues)


def test_dedup_keeps_earliest_entry_and_max_severity():
    issues = [
        {"Type": "X", "Target": "A.m", "Severity": "Low",
         "Reason": "r1", "Category": "Naming"},
        {"Type": "X", "Target": "A.m", "Severity": "Critical",
         "Reason": "r2", "Category": "Implementation"},
        {"Type": "Y", "Target": "B", "Severity": "Low",
         "Reason": "r3", "Category": "Naming"},
    ]
    merged = deduplicate_issues(issues)

    assert len(merged) == 2
    assert merged[0]["Category"] == "Naming"
    assert merged[0]["Severity"] == "Critical"
    assert merged[0]["Reason"] == "r2"
    assert calculate_weighted_penalty(merged) == (4 + 1) * PENALTY_PER_WEIGHT


def test_score_is_clamped_between_0_and_100():
    many_critical = [{"Severity": "Critical"} for _ in range(10)]
    assert calculate_normalized_score(many_critical) == 0
    assert calculate_normalized_score([]) == 100


def test_missing_data_degrades_to_none():
    assert calculate_normalized_score(None) is None


def test_parse_failure_raises_value_error():
    engine = StaticAnalyzerEngine("public class { broken")
    with pytest.raises(ValueError):
        engine.run()


def test_full_pipeline_on_sample_file():
    engine = StaticAnalyzerEngine(SAMPLE_CODE)
    issues, _ = engine.run()

    assert len(issues) == 7
    hits = {e["detector_id"]: e["hits"] for e in engine.pipeline_report}
    assert hits == {"design": 1, "implementation": 2, "naming": 2, "documentation": 2}

    scores = {e["detector_id"]: e["normalized_score"] for e in engine.pipeline_report}
    assert scores == {"design": 95, "implementation": 75, "naming": 90, "documentation": 90}

    total_penalty = sum(e["weighted_penalty"] for e in engine.pipeline_report)
    assert total_penalty == calculate_weighted_penalty(issues) == 50
    assert engine.quality_score == 50
