"""Render test for the pipeline page via streamlit AppTest."""

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_pipeline_page_renders_reproducible_numbers():
    at = AppTest.from_file(str(Path(__file__).parent / "pipeline_page_app.py"))
    at.run()

    assert not at.exception

    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Detectors Run"] == "4"
    assert metrics["Total Weighted Penalty"] == "50"
    assert metrics["Pipeline Quality Score"] == "50/100"

    assert len(at.dataframe) == 1
    table = at.dataframe[0].value
    assert list(table["Detector ID"]) == [
        "design", "implementation", "naming", "documentation",
    ]
    assert list(table["Hits (deduped)"]) == [1, 2, 2, 2]
    assert list(table["Weighted Penalty"]) == [5, 25, 10, 10]
    assert list(table["Normalized Score"]) == [95, 75, 90, 90]
