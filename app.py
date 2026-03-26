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


def _render_agent_log():
    if not st.session_state.agent_log:
        return
    st.markdown("**Agent log:**")
    log_container = st.container()
    with log_container:
        for entry in st.session_state.agent_log:
            st.markdown(f'<div class="step-log">{entry}</div>', unsafe_allow_html=True)


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

    tab1, tab2, tab3, tab4 = st.tabs(["⚡ Task", "📬 Inbox", "📅 Calendar", "📋 History"])

    with tab1:
        render_task_tab()
    with tab2:
        render_inbox_tab()
    with tab3:
        render_calendar_tab()
    with tab4:
        render_history_tab()


if __name__ == "__main__":
    main()
