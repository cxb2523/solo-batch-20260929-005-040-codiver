"""
Enterprise Java Static Analyzer Pro
Main Entry Point - Streamlit UI Application

This is the main entry point that coordinates the UI and analysis engine.
Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
from datetime import datetime

from analyzer_engine import (
    StaticAnalyzerEngine,
    ISSUE_PENALTY,
    REGISTRY_WARNINGS,
)
from detectors.base import SEVERITY_WEIGHTS
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
    if 'source_code' not in st.session_state:
        st.session_state.source_code = None
    if 'file_name' not in st.session_state:
        st.session_state.file_name = None
    if 'pipeline_report' not in st.session_state:
        st.session_state.pipeline_report = None


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
            
    except ValueError as ve:
        st.session_state.pipeline_report = engine.pipeline_report
        st.error(f"❌ **Validation Error:** {ve}")
        st.info(" [TIP]  Please ensure your Java file has valid syntax and try again.")
    except Exception as e:
        st.session_state.pipeline_report = engine.pipeline_report
        st.error(f"❌ **System Error:** {e}")
        st.exception(e)


def render_pipeline_page():
    """
    Render the detector pipeline page.

    Shows every registered detector in registration order with its run
    status, deduplicated hit count, severity-weighted hits and normalized
    score. Every number on the page is recomputable from the formulas shown
    at the bottom (and documented in docs/architecture.md).
    """
    st.markdown("###  Detector Pipeline")

    report = st.session_state.get("pipeline_report")
    if not report:
        st.info("Run the analysis first to populate the detector pipeline.")
        return

    rows = []
    for row in report["detectors"]:
        rows.append({
            "#": row["order"],
            "Detector ID": row["id"],
            "Class": row["class"],
            "Status": row["status"],
            "Raw Hits": row["raw_hits"],
            "Hits (deduped)": row["hits"],
            "Weighted Hits": row["weighted_hits"],
            "Score": row["score"] if row["score"] is not None else "N/A",
            "Error": row["error"] or "",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Issues (deduped)", report["total_issues"])
    with col2:
        st.metric("Duplicates Removed", report["duplicates_removed"])
    with col3:
        overall = report["overall_score"]
        st.metric("Overall Score", f"{overall}/100" if overall is not None else "N/A")

    if report["overall_score"] is None:
        st.warning(
            "Degraded path: no detector produced a usable score "
            "(all detectors disabled, failed, or the source could not be "
            "parsed), so the overall score is reported as N/A instead of "
            "defaulting to 100."
        )

    if any(r["status"] == "error" for r in report["detectors"]):
        st.warning(
            "One or more detectors crashed and were isolated in place: they "
            "contributed zero issues and were excluded from the overall "
            "score. Remaining detectors were unaffected."
        )

    warnings = report.get("registry_warnings") or list(REGISTRY_WARNINGS)
    if warnings:
        with st.expander(" Registry warnings (rule-id collisions)"):
            for warning in warnings:
                st.warning(warning)

    with st.expander(" How to recompute these numbers"):
        weights = ", ".join(f"{k}={v}" for k, v in SEVERITY_WEIGHTS.items())
        st.markdown(f"""
- **Severity weights:** {weights}
- **Deduplication:** issues colliding on `(Type, Target)` keep the higher
  severity weight; ties keep the earlier-registered detector's issue.
- **Per-detector score:** `clamp(100 - {ISSUE_PENALTY} x weighted_hits, 0, 100)`
- **Overall score:** `round(mean of per-detector scores over detectors with
  status ok)`, clamped to 0-100; `N/A` when no detector scored.
        """)


def display_analysis_results():
    """Display all analysis results from session state."""
    if st.session_state.analysis_results is not None:
        results = st.session_state.analysis_results
        metrics = st.session_state.analysis_metrics
        df = pd.DataFrame(results) if results else pd.DataFrame()
        
        # Render all dashboard sections
        render_executive_summary(df, metrics)
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
