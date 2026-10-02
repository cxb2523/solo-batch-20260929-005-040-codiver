"""Streamlit harness script used by test_pipeline_page.py (AppTest)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "java_analyzer"))

import streamlit as st

from analyzer_engine import StaticAnalyzerEngine
from dashboard import initialize_session_state, render_pipeline_page

code = (Path(__file__).parent / "sample_data" / "SampleSmells.java").read_text()
engine = StaticAnalyzerEngine(code)
engine.run()

initialize_session_state()
st.session_state.pipeline_report = engine.pipeline_report
st.session_state.pipeline_score = engine.quality_score
st.session_state.pipeline_status = "ok"

render_pipeline_page()
