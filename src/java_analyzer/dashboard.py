"""
Enterprise Java Static Analyzer Pro
Main Entry Point - Streamlit UI Application

This is the main entry point that coordinates the UI and analysis engine.
Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
from datetime import datetime

from analyzer_engine import StaticAnalyzerEngine
from detectors.base import registry_conflicts
from utils.ui_components import (
    render_executive_summary,
    render_code_metrics,
    render_visualizations,
    render_detailed_findings,
    render_source_code_viewer,
    render_summary_report,
    render_landing_page
)
from utils.helpers import format_file_size


def initialize_session_state():
    """Initialize session state variables for persistent data storage."""
    if 'analysis_results' not in st.session_state:
        st.session_state.analysis_results = None
    if 'analysis_metrics' not in st.session_state:
        st.session_state.analysis_metrics = None
    if 'pipeline_report' not in st.session_state:
        st.session_state.pipeline_report = None
    if 'pipeline_score' not in st.session_state:
        st.session_state.pipeline_score = None
    if 'pipeline_status' not in st.session_state:
        st.session_state.pipeline_status = None
    if 'source_code' not in st.session_state:
        st.session_state.source_code = None
    if 'file_name' not in st.session_state:
        st.session_state.file_name = None


def configure_page():
    """Configure Streamlit page settings and custom CSS."""

    
    # Custom CSS styling
    st.markdown("""
        <style>
        .main-header {
            font-size: 2.5rem;
            font-weight: 700;
            background: linear-gradient(120deg, #1e3a8a 0%, #3b82f6 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }
        .subtitle {
            color: #64748b;
            font-size: 1.1rem;
            margin-bottom: 2rem;
        }
        </style>
    """, unsafe_allow_html=True)


def render_header():
    """Render the main application header."""
    st.markdown('<h1 class="main-header">  Java Static Analyzer</h1>', 
                unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Advanced Technical Debt Detection & Code Quality Intelligence Platform</p>', 
                unsafe_allow_html=True)


def render_sidebar():
    """
    Render the sidebar with file upload and configuration options.
    
    Returns:
        Tuple of (uploaded_file, analyze_button_clicked, config_dict)
    """
    with st.sidebar:
        st.markdown("###  Control Center")
        
        # File uploader
        uploaded_file = st.file_uploader(
            "Upload Java Source File",
            type=["java"],
            help="Select a .java file for comprehensive analysis"
        )
        
        st.markdown("---")
        
        # Analysis configuration
        with st.expander(" Analysis Configuration"):
            enable_design = st.checkbox("Design Smells", value=True)
            enable_implementation = st.checkbox("Implementation Smells", value=True)
            enable_naming = st.checkbox("Naming Conventions", value=True)
            enable_documentation = st.checkbox("Documentation", value=True)
        
        config = {
            'design': enable_design,
            'implementation': enable_implementation,
            'naming': enable_naming,
            'documentation': enable_documentation
        }
        
        # Analyze button
        analyze_btn = st.button(
            " [START]  Run Deep Analysis",
            type="primary",
            use_container_width=True
        )
        
        st.markdown("---")
        
        # Analysis scope information
        st.markdown("###  Analysis Scope")
        st.markdown("""
        - ✅ Design Pattern Violations
        - ✅ Cyclomatic Complexity
        - ✅ Code Smell Detection
        - ✅ Naming Conventions
        - ✅ Documentation Coverage
        - ✅ Maintainability Index
        """)
        
        st.markdown("---")
        
        # Version and timestamp
        st.caption(" Ahmad Hassan")
        st.caption(" Muhammad Abdullah")
        st.caption(" Nayyar Abbas")
        st.caption(" Faraz Ashraf")
        st.caption(" Ahsan Ali Khan")
        st.caption(f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return uploaded_file, analyze_btn, config


def render_file_info(file_name: str, file_size: int, line_count: int):
    """
    Render file information metrics.
    
    Args:
        file_name: Name of the uploaded file
        file_size: Size of the file in bytes
        line_count: Number of lines in the file
    """
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.info(f" **File:** {file_name}")
    with col2:
        st.info(f" **Size:** {file_size} bytes")
    with col3:
        st.info(f" **Lines:** {line_count}")


def handle_analysis(source_code: str, config: dict = None):
    """
    Handle the analysis execution and error handling.
    
    Args:
        source_code: Java source code to analyze
        config: Analysis configuration dictionary
    """
    engine = StaticAnalyzerEngine(source_code, config)
    
    try:
        with st.spinner(" Parsing AST nodes and executing analyzers..."):
            results, tree = engine.run()
            metrics = engine.calculate_metrics(tree)
            
            # Store results in session state
            st.session_state.analysis_results = results
            st.session_state.analysis_metrics = metrics
            st.session_state.pipeline_report = engine.pipeline_report
            st.session_state.pipeline_score = engine.quality_score
            st.session_state.pipeline_status = "ok"
            
    except ValueError as ve:
        # Parse-level degradation: no detector ran, score is unavailable.
        st.session_state.analysis_results = None
        st.session_state.analysis_metrics = None
        st.session_state.pipeline_report = []
        st.session_state.pipeline_score = None
        st.session_state.pipeline_status = "parse_failed"
        st.error(f"❌ **Validation Error:** {ve}")
        st.info(" [TIP]  Please ensure your Java file has valid syntax and try again.")
    except Exception as e:
        st.error(f"❌ **System Error:** {e}")
        st.exception(e)


def display_analysis_results():
    """Display all analysis results from session state."""
    if st.session_state.get('pipeline_status') == 'parse_failed':
        render_pipeline_page()
        return
    if st.session_state.analysis_results is not None:
        results = st.session_state.analysis_results
        metrics = st.session_state.analysis_metrics
        df = pd.DataFrame(results) if results else pd.DataFrame()
        
        # Render all dashboard sections
        render_executive_summary(df, metrics)
        st.markdown("---")

        render_pipeline_page()
        st.markdown("---")
        
        render_code_metrics(metrics)
        st.markdown("---")
        
        render_visualizations(df)
        st.markdown("---")
        
        render_detailed_findings(df)
        
        # Source code viewer
        render_source_code_viewer(st.session_state.source_code)
        
        # Summary report
        render_summary_report(df, metrics, st.session_state.file_name)


def render_pipeline_page():
    """
    Render the detection pipeline page: detector registration order,
    per-detector hit counts and normalized scores, plus the overall
    quality score. Every number shown is reproducible from the formula
    documented in docs/architecture.md:

        score = clamp(100 - sum(weight(severity) * 5), 0, 100)
        weights: Critical=4, High=3, Medium=2, Low=1
    """
    report = st.session_state.get('pipeline_report')

    st.markdown("###  Detection Pipeline")

    if report is None:
        st.info("Run an analysis to inspect the detection pipeline.")
        return

    if st.session_state.get('pipeline_status') == 'parse_failed':
        st.warning("AST parsing failed: no detector ran and the overall "
                   "score is unavailable (N/A) instead of a misleading 0 or 100.")
        return

    if not report:
        st.info("No detectors were enabled for this run.")
        return

    st.caption(
        "Scoring formula: `score = clamp(100 - sum(weight(severity) x 5), 0, 100)` "
        "with weights Critical=4 / High=3 / Medium=2 / Low=1. "
        "Duplicate issues from multiple detectors are merged on (Type, Target): "
        "the earliest detector in registration order keeps the issue, the "
        "highest severity wins. Degraded detectors are excluded from scoring."
    )

    display_rows = []
    for entry in report:
        display_rows.append({
            "Order": entry["order"],
            "Detector ID": entry["detector_id"],
            "Detector": entry["detector"],
            "Status": entry["status"],
            "Raw Hits": entry["raw_hits"],
            "Hits (deduped)": entry["hits"],
            "Weighted Penalty": entry["weighted_penalty"],
            "Normalized Score": (
                "N/A (degraded)" if entry["normalized_score"] is None
                else entry["normalized_score"]
            ),
            "Error": entry["error"] or "",
        })
    st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)

    total_penalty = sum(entry["weighted_penalty"] for entry in report)
    score = st.session_state.get('pipeline_score')

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Detectors Run", len(report))
    with col2:
        st.metric("Total Weighted Penalty", total_penalty)
    with col3:
        st.metric("Pipeline Quality Score",
                  "N/A" if score is None else f"{score}/100")

    degraded = [entry for entry in report if entry["status"] == "degraded"]
    if degraded:
        names = ", ".join(entry["detector"] for entry in degraded)
        st.warning(f"Degraded detectors excluded from scoring: {names}. "
                   "The score above is an optimistic upper bound computed "
                   "from the remaining detectors only.")

    conflicts = registry_conflicts()
    if conflicts:
        lines = "; ".join(
            f"'{c['detector_id']}': kept {c['kept']}, skipped {c['skipped']}"
            for c in conflicts
        )
        st.info(f"Registry id collisions resolved first-registered-wins: {lines}")


def main():
    """Main application entry point."""
    # Initialize
    initialize_session_state()
    configure_page()
    
    # Render header
    render_header()
    
    # Render sidebar and get inputs
    uploaded_file, analyze_btn, config = render_sidebar()
    
    # Main application logic
    if uploaded_file:
        source_code = uploaded_file.getvalue().decode("utf-8")
        
        # Check if this is a new file
        if st.session_state.file_name != uploaded_file.name:
            st.session_state.file_name = uploaded_file.name
            st.session_state.source_code = source_code
            # Reset analysis when new file is uploaded
            st.session_state.analysis_results = None
            st.session_state.analysis_metrics = None
        
        # Display file information
        render_file_info(
            uploaded_file.name,
            len(source_code),
            len(source_code.split('\n'))
        )
        
        # Handle analysis button click
        if analyze_btn:
            handle_analysis(source_code)
        
        # Display results if they exist
        display_analysis_results()
    
    else:
        # Show landing page when no file is uploaded
        render_landing_page()


if __name__ == "__main__":
    main()
