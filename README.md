# OpenClaw 🦀

Agentic email automation platform built on the orchestrator-agent architecture.

## What it does

OpenClaw connects to Gmail, reads and searches your mail, can draft replies using
web-searched context, and surfaces all write operations (reply, delete) to you
for approval via a terminal HIL (Human-in-the-Loop) interface.

---

## Quickstart

### 1. Install dependencies

```bash
cd openclaw
pip install -r requirements.txt
```

### 2. Set up Gmail OAuth2

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → **APIs & Services** → **Enable APIs** → enable **Gmail API**
3. **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
   - Application type: **Desktop app**
4. Download the JSON file → save as `config/credentials.json`

### 3. Set up environment

```bash
cp .env.example .env
```

Edit `.env` and fill in:
- `MISTRAL_API_KEY` — from [console.mistral.ai](https://console.mistral.ai)
- `TAVILY_API_KEY` — from [tavily.com](https://tavily.com) (free tier available)
- Gmail paths are pre-filled and work out of the box

### 4. Run

```bash
python main.py
```

On first run, a browser window opens for Gmail consent. After approval, a
`config/token.json` is saved — subsequent runs are instant.

---

## Architecture

```
main.py
  │
  ├── ContextBundle          — task state + execution_history (loop reduction)
  │
  ├── GmailConnector         — OAuth2, read/search/reply/delete
  │
  ├── WebSearchConnector     — Tavily search
  │
  ├── MailToolExecutor       — dispatches agent tool calls
  │     ├── list_inbox       ─┐
  │     ├── search_mail       │  READ-ONLY (no HIL required)
  │     ├── read_message      │
  │     ├── read_thread      ─┘
  │     ├── web_search        (no HIL)
  │     ├── stage_reply      ─┐  WRITE ops — staged only,
  │     └── stage_delete     ─┘  executed after HIL approval
  │
  ├── Mistral LLM            — orchestrator (mistral-large-latest)
  │
  └── CLI HIL Approver       — human gate for reply/delete
        ├── y → approve & execute
        ├── n → reject, log reason
        └── e → edit draft, then execute
```

## HIL flow

```
Agent stages reply/delete
        ↓
Terminal shows preview + execution history
        ↓
Human: [y]approve / [n]reject / [e]edit
        ↓
Approved → GmailConnector.reply() or .trash()
```

---

## Adding new connectors

1. Create `orchestrator/connectors/your_app.py`
2. Add tool schemas to `agent/tools/your_app_tools.py`
3. Register tools in `main.py` alongside the Gmail tools
4. Tag write ops with `bundle.stage_for_hil()` — HIL works automatically

## Roadmap

- [ ] Google Calendar connector
- [ ] Web UI HIL (Flask) replacing terminal
- [ ] Slack / Telegram HIL notifications
- [ ] Attachment handling (read + summarise PDFs)
- [ ] Multi-account Gmail support
- [ ] Scheduled runs (cron mode)
