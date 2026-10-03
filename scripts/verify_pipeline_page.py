"""
Manual verification: render the pipeline page via Streamlit AppTest with a
real engine report and check every number against the documented formulas.
Run: python scripts/verify_pipeline_page.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "java_analyzer"))

from streamlit.testing.v1 import AppTest

from analyzer_engine import ISSUE_PENALTY, StaticAnalyzerEngine
from detectors.base import SEVERITY_WEIGHTS

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


def build_report():
    engine = StaticAnalyzerEngine(SAMPLE_JAVA, config=None)
    engine.run()
    return engine.pipeline_report


def main():
    report = build_report()

    def render():
        from dashboard import render_pipeline_page
        render_pipeline_page()

    at = AppTest.from_function(render)
    at.session_state["pipeline_report"] = report
    at.run()
    assert not at.exception, f"page raised: {at.exception}"

    # Recompute every number from the report per docs/architecture.md.
    ok = [r for r in report["detectors"] if r["status"] == "ok"]
    expected_overall = round(sum(r["score"] for r in ok) / len(ok))
    assert report["overall_score"] == expected_overall
    for row in ok:
        assert row["score"] == max(0, min(100, 100 - ISSUE_PENALTY * row["weighted_hits"]))
        assert row["weighted_hits"] >= 0
    assert sum(r["hits"] for r in ok) == report["total_issues"]
    assert report["raw_issues"] - report["duplicates_removed"] == report["total_issues"]

    # Numbers must actually appear on the rendered page.
    metric_labels = {m.label: m.value for m in at.metric}
    assert metric_labels["Total Issues (deduped)"] == str(report["total_issues"])
    assert metric_labels["Duplicates Removed"] == str(report["duplicates_removed"])
    assert metric_labels["Overall Score"] == f"{expected_overall}/100"

    df = at.dataframe[0].value
    assert list(df["Detector ID"]) == ["design", "implementation", "naming", "documentation"]
    assert list(df["#"]) == [1, 2, 3, 4]

    print("registration order:", list(df["Detector ID"]))
    print("hits:", list(df["Hits (deduped)"]))
    print("scores:", list(df["Score"]))
    print("overall:", metric_labels["Overall Score"])
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
