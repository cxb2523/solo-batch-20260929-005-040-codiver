"""
Tests for the Java analysis pipeline: detector registry, exception
isolation, deduplication, scoring and degradation paths.
"""

import copy

import pytest

import analyzer_engine
from analyzer_engine import (
    DETECTOR_REGISTRY,
    ISSUE_PENALTY,
    REGISTRY_WARNINGS,
    StaticAnalyzerEngine,
    deduplicate_issues,
    normalize_score,
    register_detector,
)
from detectors.base import CodeSmell, SEVERITY_WEIGHTS


SAMPLE_JAVA = """
public class Foo {
    public void Bar() {
        try {
            int x = 5;
        } catch (Exception e) {
        }
    }
}
"""


@pytest.fixture
def preserve_registry():
    """Snapshot and restore the global registry around a test."""
    registry_backup = copy.copy(DETECTOR_REGISTRY)
    warnings_backup = list(REGISTRY_WARNINGS)
    yield
    DETECTOR_REGISTRY.clear()
    DETECTOR_REGISTRY.update(registry_backup)
    REGISTRY_WARNINGS.clear()
    REGISTRY_WARNINGS.extend(warnings_backup)


# --- Registration order and rule-id collisions -----------------------------

def test_builtin_registration_order():
    assert list(DETECTOR_REGISTRY.keys()) == [
        "design", "implementation", "naming", "documentation",
    ]


def test_duplicate_detector_id_is_first_wins(preserve_registry):
    original = DETECTOR_REGISTRY["design"]

    class OverrideDesign(CodeSmell):
        detector_id = "design"

        def detect(self, tree, lines):
            return []

    register_detector(OverrideDesign)

    assert DETECTOR_REGISTRY["design"] is original
    assert any("design" in warning for warning in REGISTRY_WARNINGS)


def test_new_detector_appends_after_builtins(preserve_registry):
    class ExtraSmells(CodeSmell):
        detector_id = "extra"

        def detect(self, tree, lines):
            return []

    register_detector(ExtraSmells)
    assert list(DETECTOR_REGISTRY.keys())[-1] == "extra"


# --- Exception isolation ----------------------------------------------------

def test_crashing_detector_is_isolated(preserve_registry):
    class BrokenSmells(CodeSmell):
        detector_id = "broken"

        def detect(self, tree, lines):
            raise RuntimeError("boom")

    register_detector(BrokenSmells)
    engine = StaticAnalyzerEngine(SAMPLE_JAVA, config=None)
    issues, _ = engine.run()
    report = engine.pipeline_report

    broken = next(r for r in report["detectors"] if r["id"] == "broken")
    assert broken["status"] == "error"
    assert "boom" in broken["error"]
    assert broken["hits"] == 0

    # Other detectors still ran and produced issues.
    ok_rows = [r for r in report["detectors"] if r["status"] == "ok"]
    assert len(ok_rows) == 4
    assert len(issues) > 0

    # The broken detector is excluded from the overall score.
    expected = round(sum(r["score"] for r in ok_rows) / len(ok_rows))
    assert report["overall_score"] == expected


# --- Deduplication -----------------------------------------------------------

def test_dedup_keeps_higher_severity():
    issues = [
        {"Type": "God Class", "Target": "Foo", "Severity": "Low"},
        {"Type": "God Class", "Target": "Foo", "Severity": "Critical"},
        {"Type": "Long Method", "Target": "bar", "Severity": "Medium"},
    ]
    deduped = deduplicate_issues(issues)
    assert len(deduped) == 2
    god = next(i for i in deduped if i["Type"] == "God Class")
    assert god["Severity"] == "Critical"


def test_dedup_tie_keeps_earlier_registration():
    issues = [
        {"Type": "God Class", "Target": "Foo", "Severity": "Low",
         "Reason": "from design"},
        {"Type": "God Class", "Target": "Foo", "Severity": "Low",
         "Reason": "from implementation"},
    ]
    deduped = deduplicate_issues(issues)
    assert len(deduped) == 1
    assert deduped[0]["Reason"] == "from design"


# --- Scoring -----------------------------------------------------------------

def test_normalize_score_clamps_to_0_100():
    assert normalize_score(0) == 100
    assert normalize_score(1) == 100 - ISSUE_PENALTY
    assert normalize_score(10_000) == 0
    assert 0 <= normalize_score(7) <= 100


def test_pipeline_report_is_recomputable():
    engine = StaticAnalyzerEngine(SAMPLE_JAVA, config=None)
    issues, _ = engine.run()
    report = engine.pipeline_report

    # Every page number can be recomputed from the issue list.
    assert report["total_issues"] == len(issues)
    assert sum(r["hits"] for r in report["detectors"]) == report["total_issues"]
    assert report["raw_issues"] - report["duplicates_removed"] == report["total_issues"]

    for row in report["detectors"]:
        if row["status"] != "ok":
            continue
        assert row["score"] == max(0, min(100, 100 - ISSUE_PENALTY * row["weighted_hits"]))

    ok_scores = [r["score"] for r in report["detectors"] if r["status"] == "ok"]
    assert report["overall_score"] == round(sum(ok_scores) / len(ok_scores))
    assert 0 <= report["overall_score"] <= 100


def test_severity_weights_match_documented_values():
    assert SEVERITY_WEIGHTS == {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}


# --- Degradation paths ---------------------------------------------------------

def test_all_detectors_disabled_yields_na_score():
    config = {"design": False, "implementation": False,
              "naming": False, "documentation": False}
    engine = StaticAnalyzerEngine(SAMPLE_JAVA, config=config)
    issues, _ = engine.run()
    report = engine.pipeline_report

    assert issues == []
    assert report["overall_score"] is None
    assert all(r["status"] == "disabled" for r in report["detectors"])


def test_syntax_error_marks_detectors_skipped():
    engine = StaticAnalyzerEngine("public class { broken", config=None)
    with pytest.raises(ValueError):
        engine.run()
    report = engine.pipeline_report

    assert report["overall_score"] is None
    assert all(r["status"] == "skipped" for r in report["detectors"])
