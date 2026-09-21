from pathlib import Path


ROOT = Path(__file__).parents[1]
APP = (ROOT / "finsight_app" / "app.py").read_text(encoding="utf-8")
BUSINESS_UI = (ROOT / "finsight_app" / "business_ui.py").read_text(encoding="utf-8")
WORKSPACE_UI = (ROOT / "finsight_app" / "workspace_ui.py").read_text(encoding="utf-8")
INGESTION_UI = (ROOT / "finsight_app" / "ingestion_ui.py").read_text(encoding="utf-8")


def test_programmatic_navigation_uses_pending_page_after_sidebar_widget_creation():
    # These page modules render after the sidebar radio has already been
    # instantiated. They must never mutate the widget-backed nav_choice key.
    assert 'session_state["nav_choice"]' not in BUSINESS_UI
    assert 'session_state["nav_choice"]' not in WORKSPACE_UI
    assert 'session_state["nav_choice"]' not in INGESTION_UI
    assert 'session_state["pending_page"]' in BUSINESS_UI
    assert 'session_state["pending_page"]' in WORKSPACE_UI
    assert 'session_state["pending_page"]' in INGESTION_UI


def test_pending_navigation_is_applied_before_nav_widget_is_instantiated():
    pending = APP.index('pending_page = st.session_state.pop("pending_page", None)')
    sidebar = APP.index("with st.sidebar:")
    radio = APP.index('key="nav_choice"')
    assert pending < sidebar < radio


def test_transient_workspace_pages_cannot_leave_reports_falsely_selected():
    assert 'st.session_state["nav_choice"] = "Overview"' in APP
    assert "Create/Manage are workspace actions rather than sidebar destinations." in APP


def test_form_readability_css_from_runtime_fix_is_preserved():
    assert 'div[data-baseweb="input"]' in APP
    assert 'background: #FFFFFF !important;' in APP
    assert '-webkit-text-fill-color: #173B57 !important;' in APP
    assert 'div[data-baseweb="select"] > div' in APP
