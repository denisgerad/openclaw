"""
app.py  —  OpenClaw Streamlit UI
──────────────────────────────────
Run:  streamlit run app.py
"""

import os
import sys
import time
import html
import threading
from dotenv import load_dotenv

load_dotenv()

import streamlit as st

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="OpenClaw",
    page_icon="🦀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=Syne:wght@400;600;700;800&display=swap');

  html, body, [class*="css"] {
    font-family: 'DM Mono', monospace;
  }

  h1, h2, h3, .brand {
    font-family: 'Syne', sans-serif !important;
  }

  /* Dark slate base */
  .stApp {
    background: #0d1117;
    color: #c9d1d9;
  }

  /* Sidebar */
  [data-testid="stSidebar"] {
    background: #161b22;
    border-right: 1px solid #21262d;
  }
  [data-testid="stSidebar"] .stMarkdown { color: #8b949e; }

  /* Cards */
  .oc-card {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 8px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 0.8rem;
  }

  .oc-card-accent {
    border-left: 3px solid #58a6ff;
  }

  .oc-card-warn {
    border-left: 3px solid #d29922;
    background: #1a1608;
  }

  .oc-card-success {
    border-left: 3px solid #3fb950;
    background: #0d1a0f;
  }

  .oc-card-error {
    border-left: 3px solid #f85149;
    background: #1a0a0a;
  }

  /* Mail item */
  .mail-item {
    background: #0d1117;
    border: 1px solid #21262d;
    border-radius: 6px;
    padding: 0.8rem 1rem;
    margin-bottom: 0.5rem;
    cursor: pointer;
    transition: border-color 0.15s;
  }
  .mail-item:hover { border-color: #58a6ff; }
  .mail-sender  { font-size: 0.78rem; color: #8b949e; }
  .mail-subject { font-family: 'Syne', sans-serif; font-size: 0.92rem; color: #e6edf3; font-weight: 600; }
  .mail-snippet { font-size: 0.78rem; color: #6e7681; margin-top: 2px; }
  .mail-unread  { border-left: 3px solid #58a6ff; }

  /* Step log */
  .step-log {
    background: #0d1117;
    border: 1px solid #21262d;
    border-radius: 6px;
    padding: 0.6rem 0.9rem;
    font-size: 0.82rem;
    color: #8b949e;
    margin-bottom: 0.3rem;
    font-family: 'DM Mono', monospace;
  }

  /* HIL panel */
  .hil-panel {
    background: #1a1304;
    border: 2px solid #d29922;
    border-radius: 10px;
    padding: 1.4rem 1.6rem;
  }

  .hil-title {
    font-family: 'Syne', sans-serif;
    font-size: 1.1rem;
    font-weight: 700;
    color: #d29922;
    margin-bottom: 0.6rem;
  }

  /* Brand header */
  .oc-brand {
    font-family: 'Syne', sans-serif;
    font-size: 1.6rem;
    font-weight: 800;
    color: #58a6ff;
    letter-spacing: -0.5px;
  }
  .oc-brand span { color: #3fb950; }

  /* Status badge */
  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.72rem;
    font-weight: 500;
    font-family: 'DM Mono', monospace;
  }
  .badge-blue   { background: #1d3a5e; color: #58a6ff; }
  .badge-green  { background: #0d2e12; color: #3fb950; }
  .badge-yellow { background: #2e1f08; color: #d29922; }
  .badge-red    { background: #2e0c0a; color: #f85149; }

  /* Override Streamlit button styles */
  .stButton > button {
    font-family: 'DM Mono', monospace;
    border-radius: 6px;
    font-size: 0.85rem;
    padding: 0.4rem 1.2rem;
  }

  /* Dividers */
  hr { border-color: #21262d !important; }

  /* Input */
  .stTextInput input, .stTextArea textarea {
    background: #0d1117 !important;
    border: 1px solid #30363d !important;
    color: #c9d1d9 !important;
    font-family: 'DM Mono', monospace !important;
    border-radius: 6px !important;
  }

  /* Tab styling */
  .stTabs [data-baseweb="tab-list"] {
    background: transparent;
    gap: 4px;
  }
  .stTabs [data-baseweb="tab"] {
    font-family: 'DM Mono', monospace;
    font-size: 0.82rem;
    color: #8b949e;
    background: #161b22;
    border-radius: 6px 6px 0 0;
    padding: 6px 16px;
  }
  .stTabs [aria-selected="true"] {
    color: #58a6ff !important;
    background: #1d3a5e !important;
  }

  /* Hide Streamlit default menu */
  #MainMenu, footer { visibility: hidden; }
  header[data-testid="stHeader"] { background: transparent; }
</style>
""", unsafe_allow_html=True)


# ── Session state bootstrap ───────────────────────────────────────────────────

def init_session():
    defaults = {
        "router_state":      "idle",     # idle | planning | running | hil_pending | complete | error
        "bundle":            None,
        "gmail":             None,
        "web_search":        None,
        "calendar":          None,
        "router":            None,
        "agent_log":         [],          # list of log strings
        "task_input":        "",
        "hil_edit_text":     "",
        "inbox_cache":       [],
        "inbox_loaded":      False,
        "selected_mail":     None,
        "active_tab":        "task",
        "cal_events_cache":  [],
        "cal_loaded":        False,
        "cal_selected_id":   None,
        # ── Project automation ───────────────────────────────────────────────
        "project_ctx":       None,    # active ProjectContext
        "project_name":      "",
        "ingest_proposal":   None,
        "kb_proposal":       None,
        "note_proposal":     None,
        "proj_hil_state":    None,    # "ingest"|"kb_save"|"note_save"
        "notes_search_q":    "",
        "kb_search_q":       "",
        "kb_results":        [],
        "downloads_watcher": None,    # DownloadsWatcher background thread
        # ── Task → KB bridge ──────────────────────────────────────────────────
        "task_kb_proposal":  None,    # KB proposal staged from Task tab output
        "task_kb_project":   "",      # which project to save into
        "task_kb_hil_open":  False,   # HIL panel open on Task tab
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()


# ── Connector init (cached so OAuth only runs once) ───────────────────────────

@st.cache_resource(show_spinner=False)
def get_gmail():
    from orchestrator.connectors.gmail import GmailConnector
    return GmailConnector()


@st.cache_resource(show_spinner=False)
def get_web_search():
    from orchestrator.connectors.web_search import WebSearchConnector
    return WebSearchConnector()


@st.cache_resource(show_spinner=False)
def get_calendar():
    from orchestrator.connectors.calendar import CalendarConnector
    return CalendarConnector()


@st.cache_resource(show_spinner=False)
def get_router(_gmail, _web_search, _calendar):
    from orchestrator.streamlit_router import StreamlitRouter
    return StreamlitRouter(gmail=_gmail, web_search=_web_search, calendar=_calendar)


def ensure_connectors():
    """Initialise connectors once; store errors in session state."""
    if st.session_state.gmail is None:
        try:
            st.session_state.gmail = get_gmail()
        except Exception as e:
            return False, str(e)
    if st.session_state.web_search is None:
        try:
            st.session_state.web_search = get_web_search()
        except Exception as e:
            return False, str(e)
    if st.session_state.get("calendar") is None:
        try:
            st.session_state.calendar = get_calendar()
        except Exception as e:
            st.session_state.calendar = None  # Calendar is optional
    if st.session_state.router is None:
        try:
            st.session_state.router = get_router(
                st.session_state.gmail,
                st.session_state.web_search,
                st.session_state.get("calendar"),
            )
        except Exception as e:
            return False, str(e)
    return True, None


# ── Log helper ────────────────────────────────────────────────────────────────

def log(msg: str):
    st.session_state.agent_log.append(msg)


# ── Downloads watcher ─────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def get_downloads_watcher():
    from core.downloads_watcher import DownloadsWatcher
    w = DownloadsWatcher()
    w.start()
    return w


def poll_downloads():
    """
    Check for new archive files in the downloads folder.
    If found and a project is active, auto-set the ingest proposal.
    Returns the path string if a new file was found, else None.
    """
    if st.session_state.proj_hil_state is not None:
        return None   # already reviewing something
    if st.session_state.project_ctx is None:
        return None   # no project active

    watcher = get_downloads_watcher()
    new_file = watcher.poll()
    if new_file:
        try:
            ctx = st.session_state.project_ctx
            proposal = ctx.pm.propose_ingest(new_file)
            st.session_state.ingest_proposal = proposal
            st.session_state.proj_hil_state  = "ingest"
            return new_file
        except Exception as e:
            st.warning(f"Downloads watcher: could not propose {new_file}: {e}")
    return None


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.markdown('<div class="oc-brand">Open<span>Claw</span> 🦀</div>', unsafe_allow_html=True)
        st.markdown('<div style="color:#6e7681;font-size:0.78rem;margin-bottom:1rem;">Agentic Email Automation</div>', unsafe_allow_html=True)

        st.divider()

        # Connection status
        st.markdown("**Connections**")
        gmail_ok = st.session_state.gmail is not None
        search_ok = st.session_state.web_search is not None

        cal_ok = st.session_state.get("calendar") is not None
        col1, col2, col3 = st.columns(3)
        with col1:
            if gmail_ok:
                st.markdown('<span class="badge badge-green">✓ Gmail</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="badge badge-red">✗ Gmail</span>', unsafe_allow_html=True)
        with col2:
            if search_ok:
                st.markdown('<span class="badge badge-green">✓ Tavily</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="badge badge-red">✗ Tavily</span>', unsafe_allow_html=True)
        with col3:
            if cal_ok:
                st.markdown('<span class="badge badge-green">✓ Calendar</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="badge badge-yellow">○ Calendar</span>', unsafe_allow_html=True)

        st.divider()

        # Agent state
        state = st.session_state.router_state
        state_labels = {
            "idle":        ("⬜", "badge-blue",   "Idle"),
            "planning":    ("🗺️",  "badge-blue",   "Planning"),
            "running":     ("⚙️",  "badge-blue",   "Running"),
            "hil_pending": ("⏸️",  "badge-yellow", "Awaiting approval"),
            "complete":    ("✅",  "badge-green",  "Complete"),
            "error":       ("❌",  "badge-red",    "Error"),
        }
        icon, badge, label = state_labels.get(state, ("?", "badge-blue", state))
        st.markdown(f"**Agent state**")
        st.markdown(f'{icon} <span class="badge {badge}">{label}</span>', unsafe_allow_html=True)

        if st.session_state.bundle:
            b = st.session_state.bundle
            st.markdown(f"**Steps:** {len(b.execution_history)}")
            st.markdown(f"**Loops:** {b.loop_count}")

        st.divider()

        # Quick actions
        st.markdown("**Quick tasks**")
        quick_tasks = [
            "Summarise my 5 latest unread emails",
            "Find emails from last week and list them",
            "Show my calendar for this week",
            "Find a free 1-hour slot this week for a team meeting",
            "Search for any invoice emails",
            "Find unread emails and draft replies",
        ]
        for qt in quick_tasks:
            if st.button(qt, key=f"qt_{qt[:20]}", use_container_width=True):
                st.session_state.task_input = qt
                st.session_state.active_tab = "task"
                st.rerun()

        st.divider()

        # Downloads watcher status
        try:
            w = get_downloads_watcher()
            st.markdown("**Downloads watcher**")
            if w.is_running:
                st.markdown('<span class="badge badge-green">● Watching</span>', unsafe_allow_html=True)
                st.markdown(f'<div style="font-size:0.72rem;color:#6e7681;margin-top:2px">{w.watch_path}</div>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="badge badge-red">○ Stopped</span>', unsafe_allow_html=True)
        except Exception:
            pass

        st.divider()
        if st.button("🔄 New session", use_container_width=True):
            for key in ["bundle", "agent_log", "router_state", "task_input",
                        "inbox_cache", "inbox_loaded", "selected_mail"]:
                st.session_state[key] = [] if key in ("agent_log", "inbox_cache") else (
                    False if key in ("inbox_loaded",) else None if key != "router_state" else "idle"
                )
            st.rerun()


# ── Task tab ──────────────────────────────────────────────────────────────────

def render_task_tab():
    state = st.session_state.router_state

    # ── Task input (shown when idle or complete) ──────────────────────────────
    if state in ("idle", "complete", "error"):
        st.markdown("### What would you like OpenClaw to do?")

        task = st.text_area(
            "Task",
            value=st.session_state.task_input,
            placeholder="e.g. Find emails from Alice and draft a polite follow-up reply",
            height=90,
            label_visibility="collapsed",
            key="task_textarea",
        )

        col1, col2 = st.columns([1, 5])
        with col1:
            run_clicked = st.button("▶  Run", type="primary", use_container_width=True)

        if run_clicked and task.strip():
            st.session_state.task_input = task.strip()
            _start_task(task.strip())
            st.rerun()

    # ── Running / planning state ──────────────────────────────────────────────
    if state in ("running", "planning"):
        b = st.session_state.bundle
        st.markdown(f'### <span class="badge badge-blue">⚙️ Running</span> &nbsp; {b.task_goal if b else ""}', unsafe_allow_html=True)
        _render_agent_log()
        st.info("Agent is working…", icon="⚙️")

    # ── HIL panel ─────────────────────────────────────────────────────────────
    if state == "hil_pending":
        _render_hil_panel()

    # ── Complete ──────────────────────────────────────────────────────────────
    if state == "complete":
        b = st.session_state.bundle
        st.markdown(f'### <span class="badge badge-green">✅ Complete</span>', unsafe_allow_html=True)

        if b and b.final_answer:
            answer = b.final_answer.replace("TASK_COMPLETE", "").strip()
            st.markdown(f'<div class="oc-card oc-card-success">{answer}</div>', unsafe_allow_html=True)

        _render_agent_log()
        _render_step_table()
        _render_save_to_kb_panel()

    # ── Error ─────────────────────────────────────────────────────────────────
    if state == "error":
        b = st.session_state.bundle
        st.markdown(f'### <span class="badge badge-red">❌ Error</span>', unsafe_allow_html=True)
        if b and b.final_answer:
            st.markdown(f'<div class="oc-card oc-card-error">{b.final_answer}</div>', unsafe_allow_html=True)
        _render_agent_log()


def _start_task(task: str):
    from context.context_bundle import ContextBundle
    from orchestrator.streamlit_router import RouterState

    ok, err = ensure_connectors()
    if not ok:
        st.session_state.router_state = "error"
        log(f"❌ Connector error: {err}")
        return

    bundle = ContextBundle(task_goal=task)
    st.session_state.bundle     = bundle
    st.session_state.agent_log  = []
    st.session_state.router_state = "running"

    router = st.session_state.router
    result_state = router.run_until_hil(bundle, log_fn=log)
    st.session_state.router_state = result_state.value


def _render_hil_panel():
    b = st.session_state.bundle
    if not b:
        return

    action    = b.draft_action or ""
    is_delete = action in ("delete", "trash", "delete_event")
    is_cal    = action in ("create_event", "update_event", "delete_event", "rsvp")

    action_color = {"delete": "#f85149", "trash": "#f85149", "delete_event": "#f85149"}.get(action, "#d29922")
    action_icon  = {"create_event": "📅", "update_event": "✏️", "delete_event": "🗑️", "rsvp": "✋"}.get(action, "⚠️")

    st.markdown(f"""
    <div class="hil-panel">
      <div class="hil-title">{action_icon} Human Approval Required — {action.upper()}</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Mail context ────────────────────────────────────────────
    if b.active_mail and not is_cal:
        m = b.active_mail
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**From:** {m.sender}")
            st.markdown(f"**Subject:** {m.subject}")
        with col2:
            st.markdown(f"**Date:** {m.date}")
            st.markdown(f"**Message ID:** `{m.message_id}`")

    st.divider()

    # ── Calendar action preview ───────────────────────────────────────────
    if is_cal:
        import json as _json
        try:
            payload = _json.loads(b.draft_content or "{}")
        except Exception:
            payload = {}

        if action == "create_event":
            st.markdown("📅 **New event to be created:**")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Title:** {payload.get('title', '')}")
                st.markdown(f"**Start:** {payload.get('start', '')}")
                st.markdown(f"**End:**   {payload.get('end', '')}")
                st.markdown(f"**Calendar:** {payload.get('calendar_id', 'primary')}")
            with c2:
                if payload.get("location"):
                    st.markdown(f"**Location:** {payload['location']}")
                if payload.get("attendees"):
                    st.markdown(f"**Attendees:** {', '.join(payload['attendees'])}")
                if payload.get("add_google_meet"):
                    st.markdown("**Google Meet:** will be created")
                if payload.get("recurrence"):
                    st.markdown(f"**Recurrence:** {payload['recurrence'][0]}")
            if payload.get("description"):
                st.markdown(f"**Description:** {payload['description']}")

        elif action == "update_event":
            st.markdown(f"✏️ **Event update — ID:** `{payload.get('event_id', '')}`")
            updates = payload.get("updates", {})
            if updates:
                st.json(updates)

        elif action == "delete_event":
            st.error(f"⚠️ **Delete event ID:** `{payload.get('event_id', '')}`  — This cannot be undone.", icon="🗑️")

        elif action == "rsvp":
            resp = payload.get("response", "")
            resp_color = {"accepted": "🟢", "declined": "🔴", "tentative": "🟡"}.get(resp, "⬜")
            st.markdown(f"**RSVP** {resp_color} **{resp.upper()}** for event `{payload.get('event_id', '')}`")

        # Editable JSON for create/update
        if action in ("create_event", "update_event"):
            with st.expander("✎ Edit event details (advanced)"):
                edited_json = st.text_area(
                    "Edit JSON payload",
                    value=b.draft_content or "",
                    height=250,
                    key="hil_draft_edit",
                )
                st.session_state.hil_edit_text = edited_json
        else:
            st.session_state.hil_edit_text = b.draft_content or ""

    # ── Mail draft preview ────────────────────────────────────────────
    elif is_delete:
        st.warning(f"⚠️ This will move **{b.draft_target_id}** to Trash. Recoverable within 30 days.", icon="🗑️")
        st.session_state.hil_edit_text = b.draft_content or ""
    else:
        st.markdown("**Draft to be sent:**")
        hil_edit = st.text_area(
            "Edit draft (optional)",
            value=b.draft_content or "",
            height=200,
            key="hil_draft_edit",
        )
        st.session_state.hil_edit_text = hil_edit

    if b.orchestrator_notes:
        with st.expander("🤖 Agent reasoning"):
            st.markdown(b.orchestrator_notes)

    _render_agent_log()

    st.divider()
    st.markdown("**Your decision:**")
    col_a, col_r, col_e = st.columns(3)

    with col_a:
        if st.button("✅ Approve", type="primary", use_container_width=True):
            _hil_decision("approved")
            st.rerun()

    with col_r:
        if st.button("❌ Reject", use_container_width=True):
            _hil_decision("rejected")
            st.rerun()

    allow_edit = not is_delete or action in ("create_event", "update_event")
    if allow_edit:
        with col_e:
            if st.button("✎ Approve edited", use_container_width=True):
                _hil_decision("edited")
                st.rerun()


def _hil_decision(decision: str):
    from orchestrator.streamlit_router import RouterState

    b      = st.session_state.bundle
    router = st.session_state.router
    edited = st.session_state.hil_edit_text if decision == "edited" else None

    log(f"👤 **Human decision:** {decision}")
    result_state = router.resume_after_hil(b, decision, edited_content=edited, log_fn=log)
    st.session_state.router_state = result_state.value


# ── Task → KB bridge ──────────────────────────────────────────────────────────────

def _build_kb_content_from_bundle() -> tuple[str, str, list[str]]:
    """
    Extract KB-saveable content from the completed task bundle.
    Returns (content, title, tags).
    """
    b = st.session_state.bundle
    if not b:
        return "", "", []

    parts: list[str] = []
    title = b.task_goal[:80] if b.task_goal else "Agent task output"
    tags: list[str] = []

    parts.append(f"Task: {b.task_goal}")
    parts.append("")

    if b.final_answer:
        answer = b.final_answer.replace("TASK_COMPLETE", "").strip()
        parts.append("## Summary")
        parts.append(answer)
        parts.append("")

    if b.search_results:
        parts.append("## Web Sources")
        for r in b.search_results:
            if r.get("type") == "direct_answer":
                parts.append(f"[Direct Answer] {r.get('summary', '')}")
            else:
                parts.append(f"### {r.get('title', 'Source')}")
                parts.append(r.get("summary", ""))
                if r.get("url"):
                    parts.append(f"Source: {r['url']}")
            parts.append("")

    # Auto-tag from task goal keywords
    goal_lower = b.task_goal.lower()
    attack_kws = ["xss", "csrf", "sql", "injection", "traversal", "smuggling",
                  "tampering", "overflow", "ssrf", "xxe", "rce", "lfi", "rfi",
                  "ddos", "phishing", "malware", "ransomware", "arp", "mitm"]
    for kw in attack_kws:
        if kw in goal_lower:
            tags.append(kw)
    if not tags:
        tags = ["research"]
    tags.append("web_search")

    return "\n".join(parts), title, tags


def _render_save_to_kb_panel():
    """
    Shown below completed task output.
    Project picker + content editor + HIL-gated KB save.
    """
    b = st.session_state.bundle
    if not b or not b.final_answer:
        return
    has_content = bool(
        (b.final_answer and len(b.final_answer.strip()) > 20) or b.search_results
    )
    if not has_content:
        return

    st.divider()
    with st.expander("📚 Save this output to Knowledge Base", expanded=False):

        # If HIL is staged, show it and return
        if st.session_state.task_kb_hil_open and st.session_state.task_kb_proposal:
            _render_task_kb_hil()
            return

        # Project picker
        from core.project_manager import ProjectManager
        all_projects = ProjectManager.list_all_projects()
        if not all_projects:
            st.warning("No projects found. Create one in the **🗂️ Projects** tab first.")
            return

        col_p, col_s = st.columns([3, 1])
        with col_p:
            chosen_project = st.selectbox(
                "Save to project",
                all_projects,
                key="task_kb_project_select",
                label_visibility="collapsed",
            )
        with col_s:
            src_count = len(b.search_results) if b.search_results else 0
            st.markdown(
                f'<div style="padding-top:8px;font-size:0.8rem;color:#6e7681">'
                f'{src_count} web source(s) · {len(b.execution_history)} steps</div>',
                unsafe_allow_html=True,
            )

        content, title, tags = _build_kb_content_from_bundle()

        edit_title = st.text_input("KB entry title", value=title, key="task_kb_title")
        edit_tags  = st.text_input("Tags (comma-separated)", value=", ".join(tags), key="task_kb_tags")
        edit_content = st.text_area(
            "Content to save",
            value=content,
            height=220,
            key="task_kb_content",
            help="This is the full text that will be chunked and saved to ChromaDB. Edit freely.",
        )

        # Source attribution
        source_label = f"agent_task:{b.task_goal[:60]}"
        if b.search_results:
            urls = [r.get("url", "") for r in b.search_results if r.get("url")]
            if urls:
                source_label = urls[0]
        st.markdown(
            f'<div style="font-size:0.76rem;color:#6e7681;margin-bottom:6px">'
            f'Source: <code>{html.escape(source_label)}</code></div>',
            unsafe_allow_html=True,
        )

        if st.button("📥 Propose save to KB", type="primary", key="task_kb_propose"):
            if not edit_content.strip():
                st.warning("Nothing to save.")
                return
            from core.project_context import ProjectContext
            ctx = ProjectContext(chosen_project)
            parsed_tags = [t.strip() for t in edit_tags.split(",") if t.strip()]
            proposal = ctx.kb.propose_save(
                content=edit_content,
                title=edit_title,
                source=source_label,
                tags=parsed_tags,
            )
            st.session_state.task_kb_proposal = proposal
            st.session_state.task_kb_project  = chosen_project
            st.session_state.task_kb_hil_open = True
            st.rerun()


def _render_task_kb_hil():
    """HIL panel for the Task→KB save flow."""
    from core.knowledge_base import KBSaveProposal
    from core.project_context import ProjectContext

    p: KBSaveProposal = st.session_state.task_kb_proposal
    project_name: str = st.session_state.task_kb_project

    dup_color = "#f85149" if p.is_duplicate else "#d29922"
    st.markdown(f"""
    <div class="hil-panel">
      <div class="hil-title" style="color:{dup_color}">
        📚 Save to KB — project: <strong>{project_name}</strong>{'  ⚠ Near-duplicate detected!' if p.is_duplicate else ''}
      </div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Title:** {p.title}")
        st.markdown(f"**Chunks:** {len(p.chunks)}")
    with c2:
        st.markdown(f"**Tags:** {', '.join(p.tags) or '(none)'}")
        st.markdown(f"**Source:** {p.source[:60]}")

    if p.near_duplicates:
        st.markdown("**⚠ Similar entries already in this KB:**")
        for r in p.near_duplicates[:3]:
            st.markdown(f"- {r.similarity_pct}% match — **{r.title}** [{r.source[:50]}]")

    edit_tags    = st.text_input("Edit tags",    value=", ".join(p.tags), key="tkb_hil_tags")
    edit_content = st.text_area("Edit content", value=p.content, height=180, key="tkb_hil_content")

    col_a, col_r = st.columns(2)
    with col_a:
        if st.button("✅ Approve & Save to KB", type="primary", key="tkb_hil_approve"):
            p.edited_tags    = [t.strip() for t in edit_tags.split(",") if t.strip()]
            p.edited_content = edit_content if edit_content != p.content else ""
            p.decision       = "edited" if (p.edited_tags or p.edited_content) else "approved"
            ctx    = ProjectContext(project_name)
            chunks = ctx.kb.execute_save(p)
            st.success(f"✓ Saved {chunks} chunk(s) to **{project_name}** knowledge base.")
            st.session_state.task_kb_proposal = None
            st.session_state.task_kb_hil_open = False
            st.rerun()
    with col_r:
        if st.button("❌ Reject", key="tkb_hil_reject"):
            st.session_state.task_kb_proposal = None
            st.session_state.task_kb_hil_open = False
            st.info("KB save rejected.")
            st.rerun()


def _render_agent_log():
    if not st.session_state.agent_log:
        return
    st.markdown("**Agent log:**")
    log_container = st.container()
    with log_container:
        for entry in st.session_state.agent_log:
            # Escape angle brackets so email addresses like <info@example.com>
            # are not misinterpreted as HTML tags by the browser.
            safe_entry = entry.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            st.markdown(f'<div class="step-log">{safe_entry}</div>', unsafe_allow_html=True)


def _render_step_table():
    b = st.session_state.bundle
    if not b or not b.execution_history:
        return
    st.divider()
    st.markdown("**Execution steps:**")

    rows = []
    for s in b.execution_history:
        hil_badge = ""
        if s.hil_approved is True:
            hil_badge = '<span class="badge badge-green">approved</span>'
        elif s.hil_approved is False:
            hil_badge = '<span class="badge badge-red">rejected</span>'

        status_color = (
            "badge-green"  if s.status == "success"      else
            "badge-yellow" if "pending" in s.status      else
            "badge-red"
        )
        rows.append(
            f"<tr>"
            f"<td style='padding:4px 10px;color:#6e7681'>{s.step_number}</td>"
            f"<td style='padding:4px 10px'><code>{s.action}</code></td>"
            f"<td style='padding:4px 10px'><span class='badge {status_color}'>{s.status}</span></td>"
            f"<td style='padding:4px 10px'>{hil_badge}</td>"
            f"<td style='padding:4px 10px;color:#8b949e;font-size:0.78rem'>{s.output_summary[:60]}</td>"
            f"</tr>"
        )

    html = (
        "<table style='width:100%;border-collapse:collapse;font-family:DM Mono,monospace;font-size:0.82rem'>"
        "<thead><tr style='color:#6e7681;border-bottom:1px solid #21262d'>"
        "<th style='padding:4px 10px;text-align:left'>#</th>"
        "<th style='padding:4px 10px;text-align:left'>Action</th>"
        "<th style='padding:4px 10px;text-align:left'>Status</th>"
        "<th style='padding:4px 10px;text-align:left'>HIL</th>"
        "<th style='padding:4px 10px;text-align:left'>Output</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )
    st.markdown(html, unsafe_allow_html=True)


# ── Inbox tab ─────────────────────────────────────────────────────────────────

def render_inbox_tab():
    st.markdown("### Inbox")

    col1, col2 = st.columns([1, 4])
    with col1:
        max_r = st.selectbox("Show", [5, 10, 20, 50], index=1, label_visibility="collapsed")
    with col2:
        search_q = st.text_input("Search", placeholder="from: subject: is:unread ...",
                                  label_visibility="collapsed")

    load_btn = st.button("📥 Load inbox", type="primary")

    ok, err = ensure_connectors()
    if not ok:
        st.error(f"Gmail not connected: {err}")
        return

    if load_btn or (not st.session_state.inbox_loaded):
        with st.spinner("Loading inbox..."):
            try:
                gmail = st.session_state.gmail
                if search_q.strip():
                    mails = gmail.search_messages(query=search_q, max_results=max_r)
                else:
                    mails = gmail.list_messages(max_results=max_r, label_ids=["INBOX"])
                st.session_state.inbox_cache  = mails
                st.session_state.inbox_loaded = True
            except Exception as e:
                st.error(f"Error loading inbox: {e}")
                return

    mails = st.session_state.inbox_cache
    if not mails:
        st.info("No messages found.")
        return

    st.markdown(f"<div style='color:#6e7681;font-size:0.8rem;margin-bottom:0.5rem'>{len(mails)} message(s)</div>", unsafe_allow_html=True)

    for m in mails:
        is_unread = "UNREAD" in m.labels
        unread_class = "mail-unread" if is_unread else ""
        unread_dot = "●&nbsp;" if is_unread else "&nbsp;&nbsp;"

        mail_html = f"""
        <div class="mail-item {unread_class}">
          <div class="mail-subject">{unread_dot}{html.escape(m.subject or '(no subject)')}</div>
          <div class="mail-sender">{html.escape(m.sender)} · {html.escape(m.date)}</div>
          <div class="mail-snippet">{html.escape(m.snippet[:120])}</div>
        </div>
        """
        st.markdown(mail_html, unsafe_allow_html=True)

        col1, col2, col3 = st.columns([2, 2, 6])
        with col1:
            if st.button("Read", key=f"read_{m.message_id}"):
                st.session_state.selected_mail = m.message_id
        with col2:
            task_str = f"Read email with subject '{m.subject}' from {m.sender} and summarise it"
            if st.button("→ Task", key=f"task_{m.message_id}"):
                st.session_state.task_input = task_str
                st.session_state.active_tab = "task"
                st.rerun()

    # Render selected mail
    if st.session_state.selected_mail:
        st.divider()
        with st.spinner("Fetching message..."):
            try:
                data = st.session_state.gmail.get_message(st.session_state.selected_mail)
                meta = data["meta"]
                body = data["body_text"] or data["body_html"] or "(empty)"
                st.markdown(f"""
                <div class="oc-card oc-card-accent">
                  <div style="font-family:'Syne',sans-serif;font-size:1rem;font-weight:700;color:#e6edf3">{html.escape(meta.subject or '')}</div>
                  <div style="color:#8b949e;font-size:0.8rem;margin:4px 0">From: {html.escape(meta.sender or '')} · {html.escape(meta.date or '')}</div>
                  <hr style="border-color:#21262d">
                  <pre style="white-space:pre-wrap;font-size:0.82rem;color:#c9d1d9;font-family:'DM Mono',monospace">{html.escape(body[:3000])}</pre>
                </div>
                """, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Could not fetch message: {e}")


# ── Calendar tab ──────────────────────────────────────────────────────────────

def render_calendar_tab():
    st.markdown("### Calendar")

    calendar = st.session_state.get("calendar")
    if not calendar:
        st.warning(
            "⚠️ Google Calendar not connected. "
            "Ensure your `config/token.json` includes Calendar scopes — "
            "delete the existing token and restart to re-consent.",
            icon="📅",
        )
        return

    # ── Controls row ──────────────────────────────────────────────────────────
    col_view, col_cal, col_load = st.columns([2, 3, 1])
    with col_view:
        view = st.selectbox(
            "View",
            ["Today", "This week", "Next 7 days", "Next 30 days", "Custom"],
            label_visibility="collapsed",
        )
    with col_cal:
        cal_id = st.text_input(
            "Calendar ID", value="primary",
            placeholder="primary or calendar ID",
            label_visibility="collapsed",
        )
    with col_load:
        load_btn = st.button("📅 Load", type="primary", use_container_width=True)

    # Date range picker for custom view
    custom_range = None
    if view == "Custom":
        cc1, cc2 = st.columns(2)
        with cc1:
            d_from = st.date_input("From")
        with cc2:
            d_to = st.date_input("To")
        custom_range = (d_from, d_to)

    # Search bar
    search_q = st.text_input(
        "Search events",
        placeholder="Search by title, attendee, location...",
        label_visibility="collapsed",
    )

    if load_btn or not st.session_state.cal_loaded:
        with st.spinner("Loading calendar..."):
            try:
                from datetime import datetime, timedelta, timezone as tz_mod
                now = datetime.now(tz=tz_mod.utc)

                time_min, time_max = None, None
                if view == "Today":
                    time_min = now.replace(hour=0,  minute=0,  second=0).isoformat()
                    time_max = now.replace(hour=23, minute=59, second=59).isoformat()
                elif view == "This week":
                    monday   = now - timedelta(days=now.weekday())
                    time_min = monday.replace(hour=0, minute=0, second=0).isoformat()
                    time_max = (monday + timedelta(days=6, hours=23, minutes=59)).isoformat()
                elif view == "Next 7 days":
                    time_max = (now + timedelta(days=7)).isoformat()
                elif view == "Next 30 days":
                    time_max = (now + timedelta(days=30)).isoformat()
                elif custom_range:
                    from datetime import date
                    time_min = datetime.combine(custom_range[0], datetime.min.time()).isoformat() + "Z"
                    time_max = datetime.combine(custom_range[1], datetime.max.time()).isoformat() + "Z"

                if search_q.strip():
                    events = calendar.search_events(query=search_q, calendar_id=cal_id, max_results=50)
                else:
                    events = calendar.list_events(
                        calendar_id=cal_id, time_min=time_min,
                        time_max=time_max, max_results=50,
                    )
                st.session_state.cal_events_cache = events
                st.session_state.cal_loaded = True
            except Exception as e:
                st.error(f"Error loading calendar: {e}")
                return

    events = st.session_state.cal_events_cache

    # ── Mini stats row ────────────────────────────────────────────────────────
    total     = len(events)
    with_meet = sum(1 for e in events if e.meet_link)
    all_day   = sum(1 for e in events if e.all_day)

    m1, m2, m3 = st.columns(3)
    m1.metric("Events", total)
    m2.metric("With Meet link", with_meet)
    m3.metric("All day", all_day)

    st.divider()

    if not events:
        st.info("No events found for this period.")
        return

    # ── Event list ────────────────────────────────────────────────────────────
    for ev in events:
        tz_str = calendar.default_tz
        time_str = ev.friendly_time(tz_str)
        recur_badge = " 🔁" if ev.recurrence else ""
        meet_badge  = " 🎥" if ev.meet_link else ""
        attendee_ct = f" 👥{len(ev.attendees)}" if ev.attendees else ""

        strip_color = {
            "confirmed":  "#3fb950",
            "tentative":  "#d29922",
            "cancelled":  "#f85149",
        }.get(ev.status, "#58a6ff")

        ev_html = f"""
        <div class="oc-card" style="border-left:3px solid {strip_color};margin-bottom:0.5rem">
          <div style="font-family:'Syne',sans-serif;font-size:0.95rem;font-weight:700;color:#e6edf3">
            {ev.title}{recur_badge}{meet_badge}{attendee_ct}
          </div>
          <div style="color:#8b949e;font-size:0.8rem;margin:3px 0">{time_str}</div>
          {"<div style='color:#6e7681;font-size:0.78rem'>📍 " + ev.location + "</div>" if ev.location else ""}
          {"<div style='color:#6e7681;font-size:0.78rem'>👥 " + ", ".join(ev.attendees[:4]) + ("..." if len(ev.attendees) > 4 else "") + "</div>" if ev.attendees else ""}
        </div>
        """
        st.markdown(ev_html, unsafe_allow_html=True)

        col1, col2, col3, col4 = st.columns([1, 1, 1, 5])
        with col1:
            if st.button("Detail", key=f"det_{ev.event_id}"):
                st.session_state.cal_selected_id = ev.event_id
        with col2:
            if st.button("→ Task", key=f"caltask_{ev.event_id}"):
                st.session_state.task_input = f"Review the event '{ev.title}' and help me prepare"
                st.rerun()
        with col3:
            if ev.meet_link:
                st.link_button("Join 🎥", ev.meet_link)

    # ── Event detail panel ────────────────────────────────────────────────────
    if st.session_state.cal_selected_id:
        selected = next(
            (e for e in events if e.event_id == st.session_state.cal_selected_id), None
        )
        if selected:
            st.divider()
            st.markdown(f"""
            <div class="oc-card oc-card-accent">
              <div style="font-family:'Syne',sans-serif;font-size:1.1rem;font-weight:700;color:#e6edf3">{selected.title}</div>
              <div style="color:#8b949e;font-size:0.82rem;margin:6px 0">{selected.friendly_time(calendar.default_tz)}</div>
              {"<div style='margin-top:6px;color:#c9d1d9;font-size:0.85rem'>" + selected.description[:400] + "</div>" if selected.description else ""}
              {"<div style='margin-top:6px;font-size:0.82rem'>📍 " + selected.location + "</div>" if selected.location else ""}
              {"<div style='margin-top:6px;font-size:0.82rem'>👥 " + ", ".join(selected.attendees) + "</div>" if selected.attendees else ""}
              {"<div style='margin-top:6px;font-size:0.82rem'>🎥 <a href=\"" + selected.meet_link + "\" target=\"_blank\">Join Google Meet</a></div>" if selected.meet_link else ""}
              <div style="margin-top:8px;font-size:0.75rem;color:#6e7681">Event ID: {selected.event_id}</div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("**Quick actions for this event:**")
            qa_cols = st.columns(4)
            quick = [
                ("Draft agenda",   f"Draft a meeting agenda for the event '{selected.title}' scheduled for {selected.friendly_time(calendar.default_tz)}"),
                ("Reschedule",     f"Help me reschedule the event '{selected.title}' (ID: {selected.event_id}) to a better time"),
                ("Add attendee",   f"Add an attendee to event '{selected.title}' (ID: {selected.event_id})"),
                ("Cancel event",   f"Cancel and delete the event '{selected.title}' (ID: {selected.event_id})"),
            ]
            for col, (label, task) in zip(qa_cols, quick):
                with col:
                    if st.button(label, key=f"qa_{label}_{selected.event_id}", use_container_width=True):
                        st.session_state.task_input = task
                        st.rerun()

    # ── Free/Busy checker ─────────────────────────────────────────────────────
    st.divider()
    with st.expander("🔍 Find a free meeting slot"):
        fb_emails = st.text_input(
            "Attendee emails (comma-separated)",
            placeholder="alice@example.com, bob@example.com",
            key="fb_emails",
        )
        fb_duration = st.slider("Meeting duration (minutes)", 15, 180, 60, 15)
        fb_days     = st.slider("Look ahead (days)", 1, 14, 7)
        fb_tz       = st.text_input("Timezone", value=calendar.default_tz, key="fb_tz")

        if st.button("Find free slots", type="primary"):
            emails = [e.strip() for e in fb_emails.split(",") if e.strip()]
            if not emails:
                st.warning("Enter at least one email address.")
            else:
                with st.spinner("Checking availability..."):
                    try:
                        slots = calendar.find_free_slots(
                            emails=emails,
                            duration_minutes=fb_duration,
                            days_ahead=fb_days,
                            timezone=fb_tz,
                        )
                        if not slots:
                            st.info("No free slots found in this window.")
                        else:
                            st.success(f"Found {len(slots)} available slot(s):")
                            for i, s in enumerate(slots, 1):
                                col_a, col_b = st.columns([3, 1])
                                with col_a:
                                    st.markdown(f"**{i}.** {s['day']}  —  {s['time']}")
                                with col_b:
                                    task_str = (
                                        f"Schedule a {fb_duration}-minute meeting with "
                                        f"{', '.join(emails)} on {s['day']} at {s['time']}. "
                                        f"Start: {s['start']}  End: {s['end']}"
                                    )
                                    if st.button("Schedule →", key=f"sched_{i}", use_container_width=True):
                                        st.session_state.task_input = task_str
                                        st.rerun()
                    except Exception as e:
                        st.error(f"Free/busy check failed: {e}")


# ── History tab ───────────────────────────────────────────────────────────────

def render_history_tab():
    st.markdown("### Session History")
    b = st.session_state.bundle
    if not b or not b.execution_history:
        st.info("No steps executed yet in this session.")
        return

    st.markdown(f"**Task:** {b.task_goal}")
    st.markdown(f"**Loops:** {b.loop_count} · **Steps:** {len(b.execution_history)}")
    st.divider()

    for s in b.execution_history:
        color = "#3fb950" if s.status == "success" else (
                "#d29922" if "pending" in s.status else "#f85149")
        hil_str = ""
        if s.hil_approved is True:   hil_str = " · HIL ✅"
        if s.hil_approved is False:  hil_str = " · HIL ❌"
        if s.error:                  hil_str += f" · error: {s.error[:60]}"

        st.markdown(f"""
        <div class="oc-card" style="border-left:3px solid {color}">
          <div style="font-size:0.78rem;color:#6e7681">Step {s.step_number} · {s.timestamp[:19]}</div>
          <div><code>{s.action}</code> &nbsp; <span style="color:{color}">{s.status}</span>{hil_str}</div>
          <div style="font-size:0.8rem;color:#8b949e;margin-top:4px">↩ {s.output_summary}</div>
        </div>
        """, unsafe_allow_html=True)

    if b.search_results:
        st.divider()
        st.markdown(f"**Web searches:** {len(b.search_results)}")
        for r in b.search_results[:5]:
            if r.get("url"):
                st.markdown(f"- [{r['title']}]({r['url']})")


# ── Main layout ───────────────────────────────────────────────────────────────

def main():
    render_sidebar()

    # Main content
    st.markdown('<div class="oc-brand" style="font-size:2rem;margin-bottom:0.2rem">Open<span>Claw</span> 🦀</div>', unsafe_allow_html=True)
    st.markdown('<div style="color:#6e7681;font-size:0.85rem;margin-bottom:1.5rem">Agentic email automation · Mistral · Gmail · Tavily</div>', unsafe_allow_html=True)

    # Connection banner if not ready
    ok, err = ensure_connectors()
    if not ok:
        st.markdown(f"""
        <div class="oc-card oc-card-error">
          <strong>Connection error:</strong> {err}<br>
          <span style="font-size:0.82rem;color:#8b949e">
            Check your <code>.env</code> file and ensure <code>config/credentials.json</code> exists.
          </span>
        </div>
        """, unsafe_allow_html=True)

    # Poll downloads watcher — auto-propose any new archive files
    new_dl = poll_downloads()
    if new_dl:
        st.toast(f"📦 New download detected: {new_dl.split('/')[-1]} — review in Projects tab", icon="📦")
        st.rerun()

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["⚡ Task", "📬 Inbox", "📅 Calendar", "🗂️ Projects", "📋 History"])

    with tab1:
        render_task_tab()
    with tab2:
        render_inbox_tab()
    with tab3:
        render_calendar_tab()
    with tab4:
        render_projects_tab()
    with tab5:
        render_history_tab()


# ── Projects tab ──────────────────────────────────────────────────────────────

def _get_or_create_project_ctx(name: str):
    """Return cached ProjectContext or create a new one."""
    if st.session_state.project_ctx is None or st.session_state.project_name != name:
        from core.project_context import ProjectContext
        st.session_state.project_ctx  = ProjectContext(name)
        st.session_state.project_name = name
    return st.session_state.project_ctx


def render_projects_tab():
    st.markdown("### 🗂️ Projects")

    from core.project_manager import ProjectManager
    all_projects = ProjectManager.list_all_projects()

    # ── How to register projects (always visible) ─────────────────────────────
    with st.expander("ℹ️ How to add / register projects", expanded=not all_projects):
        st.markdown("""
**Two ways to register a project:**

**1 — Create a new project here** (data saved to `~/openclaw/projects/<name>/`)

**2 — Register an existing folder** by adding a line to your `.env` file:
```
OPENCLAW_PROJECT_CYBERSHIELD=/home/dennis/projects/cybershield
OPENCLAW_PROJECT_MYAPP=/data/myapp
```
The key format is `OPENCLAW_PROJECT_<NAME_UPPERCASE>`. Restart the app after editing `.env`.
""")

    # ── Create new project ────────────────────────────────────────────────────
    st.markdown("**Create a new project:**")
    col_name, col_btn = st.columns([4, 1])
    with col_name:
        new_name = st.text_input("Project name", placeholder="e.g. cybershield",
                                  label_visibility="collapsed", key="new_proj_name")
    with col_btn:
        if st.button("➕ Create", type="primary", use_container_width=True,
                     disabled=not new_name.strip()):
            _get_or_create_project_ctx(new_name.strip())
            st.success(f"Project '{new_name.strip()}' created.")
            st.rerun()

    if not all_projects:
        st.info("No projects found. Create one above, or register an existing folder in `.env` (see ℹ️ above).")
        return

    st.divider()

    # ── Project selector ──────────────────────────────────────────────────────
    st.markdown("**Active project:**")
    selected = st.selectbox("Active project", all_projects, label_visibility="collapsed")

    if not selected:
        return

    ctx = _get_or_create_project_ctx(selected)

    summary = ctx.summary()

    # ── Project overview ──────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Versions",  summary["version_count"])
    m2.metric("KB docs",   summary["kb_docs"])
    m3.metric("Notes",     summary["notes"]["total"])
    m4.metric("Anom. gaps", summary["notes"]["anomaly_gap"])

    st.markdown(f'<div style="font-family:DM Mono,monospace;font-size:0.78rem;color:#6e7681;margin:4px 0">Root: {summary["root"]}</div>', unsafe_allow_html=True)

    desc_val = summary.get("description", "")
    new_desc = st.text_input("Project description", value=desc_val, placeholder="What is this project about?")
    if new_desc != desc_val:
        ctx.pm.set_description(new_desc)

    st.divider()

    # ── Sub-sections as expanders ─────────────────────────────────────────────
    _render_versions_section(ctx)
    _render_kb_section(ctx)
    _render_notes_section(ctx)


# ── Versions section ──────────────────────────────────────────────────────────

def _render_versions_section(ctx):
    with st.expander("📦 File Versions", expanded=True):
        versions = ctx.pm.list_versions()
        active   = ctx.pm.get_active_version()

        # Upload widget
        st.markdown("**Ingest a downloaded file:**")
        uploaded = st.file_uploader(
            "Drop .tar.gz, .tar, .tar.bz2, or .zip here",
            type=["gz", "zip", "tar", "bz2"],
            label_visibility="collapsed",
            key="proj_upload",
        )

        if uploaded:
            import tempfile, os as _os
            tmp_dir  = tempfile.mkdtemp()
            tmp_path = _os.path.join(tmp_dir, uploaded.name)
            with open(tmp_path, "wb") as f:
                f.write(uploaded.getbuffer())

            if st.button("🔍 Analyse file", type="primary"):
                proposal = ctx.pm.propose_ingest(tmp_path)
                st.session_state.ingest_proposal = proposal
                st.session_state.proj_hil_state  = "ingest"
                st.rerun()

        # HIL panel for ingest
        if st.session_state.proj_hil_state == "ingest" and st.session_state.ingest_proposal:
            _render_ingest_hil(ctx)

        # Version list
        if versions:
            st.markdown(f"**{len(versions)} version(s):**")
            for v in reversed(versions):
                is_active = active and active.name == v.name
                border    = "#3fb950" if is_active else "#21262d"
                active_badge = " 🟢 **active**" if is_active else ""
                st.markdown(f"""
                <div class="oc-card" style="border-left:3px solid {border}">
                  <span style="font-family:Syne,sans-serif;font-weight:700;color:#e6edf3">{v.name}</span>{active_badge}
                  <span style="font-size:0.78rem;color:#6e7681;margin-left:10px">{v.timestamp[:19] if v.timestamp else ""}</span><br>
                  <span style="font-size:0.82rem;color:#8b949e">📄 {v.source}  ·  {v.file_count} files  ·  {v.size_kb} KB  ·  sha256: {v.sha256}</span>
                  {"<br><span style='font-size:0.8rem;color:#6e7681'>📝 " + v.notes + "</span>" if v.notes else ""}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No versions yet. Upload a file above.")


def _render_ingest_hil(ctx):
    from core.project_manager import IngestProposal
    p: IngestProposal = st.session_state.ingest_proposal

    st.markdown(f"""
    <div class="hil-panel">
      <div class="hil-title">📦 File Ingest — {p.version_name.upper()}</div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**File:** {p.source_path.name}")
        st.markdown(f"**Type:** `{p.archive_type}`")
        st.markdown(f"**Size:** {p.size_kb} KB")
    with c2:
        st.markdown(f"**Destination:** `{p.dest_path}`")
        st.markdown(f"**SHA-256:** `{p.sha256}`")

    st.markdown("**Contents:**")
    for f in p.file_list[:12]:
        st.markdown(f"`{f}`")
    if len(p.file_list) > 12:
        st.markdown(f"*... and {len(p.file_list) - 12} more*")

    notes_input = st.text_input("Version notes (optional)", value=p.notes, key="ingest_notes")
    p.notes = notes_input

    col_a, col_r = st.columns(2)
    with col_a:
        if st.button("✅ Approve & Extract", type="primary", key="ingest_approve"):
            p.decision = "approved"
            version    = ctx.pm.execute_ingest(p)
            st.success(f"✓ Extracted {version.file_count} files → `{version.path}`")
            st.session_state.ingest_proposal = None
            st.session_state.proj_hil_state  = None
            st.rerun()
    with col_r:
        if st.button("❌ Reject", key="ingest_reject"):
            st.session_state.ingest_proposal = None
            st.session_state.proj_hil_state  = None
            st.info("Ingest rejected.")
            st.rerun()


# ── KB section ────────────────────────────────────────────────────────────────

def _render_kb_section(ctx):
    with st.expander("📚 Knowledge Base", expanded=False):
        kb = ctx.kb
        st.markdown(f"**{kb.count()} document chunk(s)** in ChromaDB")

        # Search
        st.markdown("**Search:**")
        q = st.text_input("Search knowledge base", placeholder="e.g. SQL injection bypass techniques",
                           key="kb_search_input", label_visibility="collapsed")
        col_s, col_t = st.columns([3, 1])
        with col_t:
            tag_filter = st.text_input("Tag filter", placeholder="e.g. anomaly_gap", label_visibility="collapsed", key="kb_tag")
        if st.button("🔍 Search", key="kb_search_btn"):
            results = kb.search(q, tag_filter=tag_filter or None)
            st.session_state.kb_results = results

        if st.session_state.kb_results:
            st.markdown(f"**{len(st.session_state.kb_results)} result(s):**")
            for i, r in enumerate(st.session_state.kb_results):
                st.markdown(f"""
                <div class="oc-card oc-card-accent">
                  <div style="font-size:0.78rem;color:#3fb950">{r.similarity_pct}% match</div>
                  <div style="font-size:0.75rem;color:#6e7681">📰 {r.title}  ·  🔗 {r.source[:80]}  ·  🏷 {", ".join(r.tags)}</div>
                </div>
                """, unsafe_allow_html=True)
                with st.expander("Show full text", expanded=False):
                    st.markdown(r.content)

        st.divider()

        # Add to KB
        st.markdown("**Add to Knowledge Base:**")
        kb_title   = st.text_input("Title",   placeholder="e.g. SQL Injection — OWASP", key="kb_title")
        kb_source  = st.text_input("Source",  placeholder="URL or description", key="kb_source")
        kb_tags    = st.text_input("Tags",    placeholder="comma-separated: sql, owasp, injection", key="kb_tags")
        kb_content = st.text_area("Content", placeholder="Paste article text, notes, or threat intel here...",
                                  height=150, key="kb_content")

        if st.button("📥 Propose save to KB", type="primary", key="kb_propose"):
            if kb_content.strip():
                tags = [t.strip() for t in kb_tags.split(",") if t.strip()]
                proposal = kb.propose_save(kb_content, kb_title, kb_source, tags)
                st.session_state.kb_proposal    = proposal
                st.session_state.proj_hil_state = "kb_save"
                st.rerun()
            else:
                st.warning("Enter some content first.")

        if st.session_state.proj_hil_state == "kb_save" and st.session_state.kb_proposal:
            _render_kb_hil(ctx)

        # Sources list
        sources = kb.list_sources()
        if sources:
            st.divider()
            st.markdown(f"**Stored sources ({len(sources)}):**")
            for s in sources:
                col_s, col_d = st.columns([5, 1])
                with col_s:
                    st.markdown(f"""
                    <div class="step-log">
                      <strong>{s["title"]}</strong>  ·  <span style="color:#6e7681">{s["source"][:70]}</span><br>
                      🏷 {", ".join(s["tags"])}  ·  {s["timestamp"][:10] if s["timestamp"] else ""}
                    </div>
                    """, unsafe_allow_html=True)
                    with st.expander("Show full text", expanded=False):
                        full_text = kb.get_by_source(s["source"])
                        st.markdown(full_text if full_text else "_No content found._")
                with col_d:
                    if st.button("🗑", key=f"del_src_{s['source'][:20]}"):
                        n = kb.delete_by_source(s["source"])
                        st.success(f"Deleted {n} chunk(s).")
                        st.rerun()


def _render_kb_hil(ctx):
    from core.knowledge_base import KBSaveProposal
    p: KBSaveProposal = st.session_state.kb_proposal

    dup_color = "#f85149" if p.is_duplicate else "#d29922"
    st.markdown(f"""
    <div class="hil-panel">
      <div class="hil-title" style="color:{dup_color}">
        📚 KB Save{'  ⚠ Near-duplicate!' if p.is_duplicate else ''}
      </div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Title:** {p.title}")
        st.markdown(f"**Source:** {p.source}")
    with c2:
        st.markdown(f"**Tags:** {', '.join(p.tags) or '(none)'}")
        st.markdown(f"**Chunks:** {len(p.chunks)}")

    st.markdown("**Content preview:**")
    st.markdown(f'<div class="step-log">{p.content[:400]}{"..." if len(p.content)>400 else ""}</div>', unsafe_allow_html=True)

    if p.near_duplicates:
        st.markdown("**⚠ Similar existing documents:**")
        for r in p.near_duplicates[:3]:
            st.markdown(f"- {r.similarity_pct}% match — **{r.title}** [{r.source[:60]}]")

    edit_tags    = st.text_input("Edit tags (comma-separated)", value=", ".join(p.tags), key="kb_hil_tags")
    edit_content = st.text_area("Edit content", value=p.content, height=120, key="kb_hil_content")

    col_a, col_r = st.columns(2)
    with col_a:
        if st.button("✅ Approve & Save to KB", type="primary", key="kb_approve"):
            p.edited_tags    = [t.strip() for t in edit_tags.split(",") if t.strip()]
            p.edited_content = edit_content if edit_content != p.content else ""
            p.decision       = "edited" if (p.edited_tags or p.edited_content) else "approved"
            chunks = ctx.kb.execute_save(p)
            st.success(f"✓ Saved {chunks} chunk(s) to ChromaDB")
            st.session_state.kb_proposal    = None
            st.session_state.proj_hil_state = None
            st.rerun()
    with col_r:
        if st.button("❌ Reject", key="kb_reject"):
            st.session_state.kb_proposal    = None
            st.session_state.proj_hil_state = None
            st.info("KB save rejected.")
            st.rerun()


# ── Notes section ─────────────────────────────────────────────────────────────

def _render_notes_section(ctx):
    with st.expander("📝 Agent Notes", expanded=False):
        notes_eng = ctx.notes
        stats     = notes_eng.stats()

        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("Total notes",   stats["total"])
        sc2.metric("Anomaly gaps",  stats["anomaly_gap"])
        sc3.metric("By agent",      stats["by_source"].get("agent_reasoning", 0))

        # Add note manually
        st.markdown("**Add a note:**")
        note_content = st.text_area("Snippet / observation", placeholder="e.g. The model did not flag the SYN flood because...",
                                    height=100, key="note_content")
        col_at, col_src = st.columns(2)
        with col_at:
            note_attack = st.text_input("Attack type", placeholder="e.g. syn_flood", key="note_attack")
        with col_src:
            note_source = st.selectbox("Source", ["agent_reasoning", "manual", "web"], key="note_src")
        note_tags = st.text_input("Extra tags", placeholder="comma-separated", key="note_tags")
        note_ctx  = st.text_input("Context", placeholder="What task was running?", key="note_ctx")

        if st.button("📥 Propose note save", type="primary", key="note_propose"):
            if note_content.strip():
                extra_tags = [t.strip() for t in note_tags.split(",") if t.strip()]
                proposal   = notes_eng.propose_note(
                    content=note_content, source=note_source,
                    attack_type=note_attack, context=note_ctx,
                    extra_tags=extra_tags,
                )
                st.session_state.note_proposal   = proposal
                st.session_state.proj_hil_state  = "note_save"
                st.rerun()
            else:
                st.warning("Enter a note first.")

        if st.session_state.proj_hil_state == "note_save" and st.session_state.note_proposal:
            _render_note_hil(ctx)

        st.divider()

        # Search and filter
        col_sq, col_ft = st.columns([3, 1])
        with col_sq:
            search_q = st.text_input("Search notes", placeholder="e.g. SQL injection",
                                     key="notes_search", label_visibility="collapsed")
        with col_ft:
            filt = st.selectbox("Filter", ["all", "anomaly_gap", "agent_reasoning", "manual"],
                                key="notes_filter", label_visibility="collapsed")

        all_notes = notes_eng.all_notes()
        if search_q:
            all_notes = notes_eng.search_notes(search_q)
        elif filt == "anomaly_gap":
            all_notes = notes_eng.anomaly_gap_notes()
        elif filt in ("agent_reasoning", "manual"):
            all_notes = [n for n in all_notes if n.source == filt]

        st.markdown(f"**{len(all_notes)} note(s):**")
        for note in all_notes[:30]:
            gap_color  = "#d29922" if note.is_anomaly_gap else "#21262d"
            gap_icon   = "🔴 " if note.is_anomaly_gap else ""
            is_long    = len(note.content) > 300
            preview    = note.content[:300] + ("…" if is_long else "")

            col_n, col_d = st.columns([10, 1])
            with col_n:
                st.markdown(f"""
                <div class="oc-card" style="border-left:3px solid {gap_color}">
                  <div style="font-size:0.75rem;color:#6e7681">{gap_icon}{note.timestamp[:19]}  ·  {note.source}  ·  {note.attack_type or "—"}</div>
                  <div style="font-size:0.85rem;color:#c9d1d9;margin:4px 0">{preview}</div>
                  <div style="font-size:0.75rem;color:#6e7681">🏷 {", ".join(note.tags)}  ·  id: {note.note_id}</div>
                </div>
                """, unsafe_allow_html=True)
                if is_long:
                    with st.expander("📖 View full note"):
                        st.markdown(
                            f'<pre style="white-space:pre-wrap;font-size:0.83rem;'
                            f'color:#c9d1d9;font-family:DM Mono,monospace;'
                            f'background:#0d1117;border:1px solid #21262d;'
                            f'border-radius:6px;padding:0.8rem">'
                            f'{html.escape(note.content)}</pre>',
                            unsafe_allow_html=True,
                        )
                        if note.context:
                            st.markdown(f"**Context:** {note.context}")
            with col_d:
                if st.button("🗑", key=f"del_note_{note.note_id}"):
                    notes_eng.delete_note(note.note_id)
                    st.rerun()


def _render_note_hil(ctx):
    from core.notes_engine import NoteSaveProposal
    p: NoteSaveProposal = st.session_state.note_proposal

    anomaly_color = "#d29922" if p.is_anomaly_gap else "#4a9eff"
    anom_label    = "🔴 ANOMALY GAP — " if p.is_anomaly_gap else ""
    st.markdown(f"""
    <div class="hil-panel">
      <div class="hil-title" style="color:{anomaly_color}">{anom_label}Note Save</div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Source:** {p.source}")
        st.markdown(f"**Attack type:** {p.attack_type or '(none)'}")
    with c2:
        st.markdown(f"**Tags:** {', '.join(p.tags) or '(none)'}")
        if p.detected_keywords:
            st.markdown(f"**Triggered by:** {', '.join(p.detected_keywords)}")

    edit_content = st.text_area("Edit snippet", value=p.content, height=120, key="note_hil_content")
    edit_attack  = st.text_input("Edit attack type", value=p.attack_type, key="note_hil_attack")
    edit_tags    = st.text_input("Edit tags", value=", ".join(p.tags), key="note_hil_tags")

    col_a, col_r = st.columns(2)
    with col_a:
        if st.button("✅ Approve & Save Note", type="primary", key="note_approve"):
            p.edited_content = edit_content if edit_content != p.content else ""
            p.edited_attack  = edit_attack  if edit_attack  != p.attack_type else ""
            p.edited_tags    = [t.strip() for t in edit_tags.split(",") if t.strip()]
            p.decision       = "edited" if any([p.edited_content, p.edited_attack]) else "approved"
            note = ctx.notes.execute_save_note(p)
            gap_msg = "  🔴 Tagged as anomaly_gap" if note.is_anomaly_gap else ""
            st.success(f"✓ Note saved [{note.note_id}]{gap_msg}")
            st.session_state.note_proposal   = None
            st.session_state.proj_hil_state  = None
            st.rerun()
    with col_r:
        if st.button("❌ Reject", key="note_reject"):
            st.session_state.note_proposal   = None
            st.session_state.proj_hil_state  = None
            st.info("Note rejected.")
            st.rerun()


if __name__ == "__main__":
    main()
