# OpenClaw 🦀

Agentic automation platform for email, calendar, web research, and project knowledge management — built on a planner–executor–verifier–debugger orchestrator architecture.

---

## What it does

- **Email automation** — reads, searches, drafts replies, and deletes Gmail messages
- **Calendar management** — lists, creates, edits, and RSVPs to Google Calendar events
- **Web research** — searches the web via Tavily and saves summaries to a knowledge base
- **Project knowledge base** — per-project ChromaDB store for research, threat intel, and notes
- **File versioning** — ingests `.tar.gz` / `.zip` archives into versioned project snapshots
- **Agentic task loop** — Mistral LLM plans, executes, verifies, and self-corrects autonomously
- **Human-in-the-Loop (HIL)** — every write operation requires explicit human approval before execution

Both a **Streamlit web UI** (`app.py`) and a **CLI interface** (`main.py`) are provided.

---

## Quickstart

### 1. Install dependencies

```bash
cd openclaw
pip install -r requirements.txt
```

### 2. Set up Google OAuth2

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → **APIs & Services** → **Enable APIs**
   - Enable **Gmail API**
   - Enable **Google Calendar API**
3. **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
   - Application type: **Desktop app**
4. Download the JSON → save as `config/credentials.json`

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | Required | Description |
|---|---|---|
| `MISTRAL_API_KEY` | Yes | [console.mistral.ai](https://console.mistral.ai) |
| `TAVILY_API_KEY` | Yes | [tavily.com](https://tavily.com) — free tier available |
| `OPENCLAW_PROJECT_<NAME>` | Per project | Absolute path to project folder, e.g. `OPENCLAW_PROJECT_CYBERSHIELD=/home/user/cybershield` |
| `MISTRAL_ORCHESTRATOR_MODEL` | Optional | Defaults to `mistral-large-latest` |
| `MAX_LOOP_RETRIES` | Optional | Agent loop budget multiplier (default `3`) |
| `OPENCLAW_KB_OFFLINE` | Optional | Set to `1` to use local TF-IDF embeddings instead of Mistral API |

### 4. Run — Streamlit UI

```bash
streamlit run app.py
```

### 4. Run — CLI

```bash
python main.py
```

On first run, a browser window opens for Google OAuth consent. A `config/token.json`
is saved — subsequent runs skip the browser step.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Interfaces                        │
│  app.py (Streamlit UI)    main.py (CLI)             │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│              Orchestrator Layer                     │
│                                                     │
│  StreamlitRouter / Router                           │
│    │                                                │
│    ├── Planner      — generates step-by-step plan   │
│    ├── Agent loop   — Mistral tool-calling loop      │
│    ├── Verifier     — quality-gates drafts pre-HIL  │
│    └── Debugger     — classifies failures, recovers │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│                Agent Tools                          │
│  MailToolExecutor       CalendarToolExecutor        │
│  (mail_tools.py)        (calendar_tools.py)         │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│               Connectors                            │
│  GmailConnector   CalendarConnector   WebSearch     │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│             HIL Gate (Human-in-the-Loop)            │
│  CLIApprover / ProjectApprover / Streamlit UI       │
│    approve → execute_approved_action()              │
│    reject  → logged, agent notified                 │
│    edit    → human edits draft, then executes       │
└─────────────────────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│             Core / Knowledge Layer                  │
│  ProjectManager   KnowledgeBase   NotesEngine       │
│  (versioning)     (ChromaDB)      (JSONL notes)     │
└─────────────────────────────────────────────────────┘
```

---

## Implemented components

### Orchestrator

| Component | File | Description |
|---|---|---|
| `Router` | `orchestrator/router.py` | Blocking CLI orchestrator — plan → execute → verify → HIL → complete |
| `StreamlitRouter` | `orchestrator/streamlit_router.py` | Non-blocking Streamlit-compatible router with `run_until_hil()` / `resume_after_hil()` state machine: `IDLE → PLANNING → RUNNING → HIL_PENDING → COMPLETE \| ERROR` |
| `Planner` | `orchestrator/planner.py` | Calls Mistral LLM to turn a free-form task goal into a numbered execution plan; writes into `ContextBundle.orchestrator_notes` |
| `Verifier` | `orchestrator/verifier.py` | Quality-gates staged drafts before HIL: checks factual grounding, tone, length; returns `VerificationResult` (pass/fail + issues + suggestions) |
| `Debugger` | `orchestrator/debugger.py` | Diagnoses agent failures, classifies as `TOOL_ERROR`, `AGENT_LOOP`, `VERIFY_FAIL`, `HIL_REJECTION`, or `CONTEXT_MISSING`; returns `RecoveryAction`: retry / replan / escalate / abort |

### Connectors

| Connector | File | Description |
|---|---|---|
| `GmailConnector` | `orchestrator/connectors/gmail.py` | OAuth2 Gmail — list inbox, search, read message, read thread, send reply, send new email, trash |
| `CalendarConnector` | `orchestrator/connectors/calendar.py` | Google Calendar — list calendars, list/get/search events, check free-busy, find free slots, create/update/delete events, RSVP |
| `WebSearchConnector` | `orchestrator/connectors/web_search.py` | Tavily web search — returns ranked results with URL, title, and content summary |

### Agent tools

#### Email tools (`agent/tools/mail_tools.py`)

| Tool | HIL required | Description |
|---|---|---|
| `list_inbox` | No | List recent inbox messages (subject, sender, date, snippet) |
| `search_mail` | No | Search Gmail with full Gmail query syntax (`from:`, `subject:`, `is:unread`, etc.) |
| `read_message` | No | Fetch full body of a single message by ID |
| `read_thread` | No | Fetch full thread history for contextual replies |
| `web_search` | No | Search the web via Tavily |
| `stage_reply` | Yes | Stage a reply draft for HIL approval |
| `stage_delete` | Yes | Stage a message trash action for HIL approval |
| `stage_new_email` | Yes | Stage a new outbound email for HIL approval |

#### Calendar tools (`agent/tools/calendar_tools.py`)

| Tool | HIL required | Description |
|---|---|---|
| `list_calendars` | No | Discover all calendars and their IDs |
| `list_events` | No | List events in a date range |
| `get_event` | No | Fetch a single event by ID |
| `search_events` | No | Full-text search across events |
| `check_free_busy` | No | Check availability for a list of attendees |
| `find_free_slots` | No | Find open meeting slots across attendees |
| `stage_create_event` | Yes | Stage a new event (supports recurrence, Meet link, attendees) |
| `stage_update_event` | Yes | Stage field-level edits to an existing event |
| `stage_delete_event` | Yes | Stage event deletion |
| `stage_rsvp` | Yes | Stage accept / decline / tentative RSVP |

### HIL (Human-in-the-Loop)

| Component | File | Description |
|---|---|---|
| `CLIApprover` | `hil/cli_approver.py` | Terminal HIL — shows draft preview + execution history; `[y]` approve, `[n]` reject, `[e]` edit |
| `ProjectApprover` | `hil/project_approver.py` | HIL for the three project flows: file ingest, KB save, and note save — both CLI and Streamlit variants |

### Core / Knowledge management

| Component | File | Description |
|---|---|---|
| `ProjectContext` | `core/project_context.py` | Single entry point that combines `ProjectManager`, `KnowledgeBase`, and `NotesEngine` for one project |
| `ProjectManager` | `core/project_manager.py` | File versioning — `propose_ingest()` → HIL → `execute_ingest()` extracts tar/zip into `versions/v1/`, `v2/`, … with SHA-256 dedup and manifest tracking |
| `KnowledgeBase` | `core/knowledge_base.py` | Per-project ChromaDB store — `propose_save()` → HIL → `execute_save()` chunks text and upserts embeddings; `search()` with optional tag filter; `get_by_source()` reconstructs full multi-chunk documents; dedup threshold at 92 % cosine similarity |
| `NotesEngine` | `core/notes_engine.py` | JSONL notes — `propose_note()` → HIL → `execute_save_note()`; auto-tags anomaly gaps; `search_notes()`, `filter_by_tag()`, `filter_by_attack()` |
| `DownloadsWatcher` | `core/downloads_watcher.py` | `watchdog`-based filesystem monitor — detects new `.tar.gz` / `.zip` files in a watch directory and queues them for ingest |

### Embedding backends (`core/knowledge_base.py`)

| Backend | Activated when | Description |
|---|---|---|
| `MistralEmbedding` | `MISTRAL_API_KEY` set and `OPENCLAW_KB_OFFLINE` unset | Calls `mistral-embed` model via API; batched requests |
| `LocalTFIDFEmbedding` | `OPENCLAW_KB_OFFLINE=1` or no API key | Pure Python 256-dim TF-IDF vectors — zero network, zero downloads |

### State carrier

| Class | File | Key fields |
|---|---|---|
| `ContextBundle` | `context/context_bundle.py` | `task_goal`, `execution_history`, `search_results`, `active_mail`, `thread_history`, `calendar_context`, `draft_content`, `draft_action`, `final_answer` |
| `ExecutionStep` | `context/context_bundle.py` | Records each agent step with action, status, HIL decision, and output summary |

---

## HIL flow

```
Agent calls stage_reply / stage_delete / stage_create_event / …
              ↓
         Verifier checks quality
              ↓ (pass)
    HIL panel shown to human
    ┌─────────────────────┐
    │  Approve            │ → connector executes the action
    │  Reject             │ → logged, agent notified, can replan
    │  Approve edited     │ → human edits draft, then executes
    └─────────────────────┘
```

---

## Project folder layout

Each project lives at the path set in `.env`:

```
<PROJECT_ROOT>/
├── project.json          ← manifest (name, versions[], active_version)
├── versions/
│   ├── v1/               ← extracted archive
│   ├── v2/
│   └── v3/               ← active version
├── kb/
│   └── chroma.sqlite3    ← ChromaDB knowledge base
└── notes/
    └── notes.jsonl       ← structured notes
```

---

## Streamlit UI tabs

| Tab | Features |
|---|---|
| **Tasks** | Free-form task input → agentic execution → live agent log → execution step table → **Save output to Knowledge Base** (HIL-gated) |
| **Inbox** | Browse Gmail inbox; read threads; stage replies and deletions |
| **Projects** | Manage projects; ingest archives (HIL); search KB with tag filter; full-text source viewer; add manual KB entries and notes (HIL) |
| **Calendar** | View upcoming events; create / edit / delete events; RSVP — all HIL-gated |

---

## Adding new connectors

1. Create `orchestrator/connectors/your_service.py`
2. Add tool schemas and an executor class to `agent/tools/your_service_tools.py`
3. Register the schemas and executor in `orchestrator/streamlit_router.py` alongside the existing tools
4. Tag write operations with `bundle.stage_for_hil()` — the HIL gate works automatically

## Roadmap

- [ ] Google Calendar connector
- [ ] Web UI HIL (Flask) replacing terminal
- [ ] Slack / Telegram HIL notifications
- [ ] Attachment handling (read + summarise PDFs)
- [ ] Multi-account Gmail support
- [ ] Scheduled runs (cron mode)
