"""
agent/tools/mail_tools.py
──────────────────────────
Tool definitions the agent can invoke autonomously (no HIL required).
These are READ-ONLY operations — list, search, get, thread fetch.

Write operations (reply, delete) are intentionally absent here.
The agent signals intent via ContextBundle.stage_for_hil() and the
orchestrator routes to hil/cli_approver.py.

Tool schema follows Mistral's function calling format (same as prior arch):
  {
      "type": "function",
      "function": {
          "name": ...,
          "description": ...,
          "parameters": { ... JSON Schema ... }
      }
  }
"""

from context.context_bundle import ContextBundle
from orchestrator.connectors.gmail import GmailConnector
from orchestrator.connectors.web_search import WebSearchConnector


# ── Tool Schemas (passed to Mistral API) ─────────────────────────────────────

MAIL_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_inbox",
            "description": (
                "List recent messages from the Gmail inbox. "
                "Use this to get an overview of recent mail. "
                "Returns subject, sender, date, snippet for each message."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "Number of messages to return (1–20). Default 10.",
                        "default": 10,
                    },
                    "unread_only": {
                        "type": "boolean",
                        "description": "If true, return only unread messages.",
                        "default": False,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_mail",
            "description": (
                "Search Gmail using a query string. "
                "Supports Gmail search syntax: from:, to:, subject:, after:, before:, is:unread, etc. "
                "Examples: 'from:alice@example.com subject:invoice', 'is:unread after:2024/01/01'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Gmail search query string.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results to return (1–20). Default 10.",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_message",
            "description": (
                "Fetch the full body of a specific Gmail message by its ID. "
                "Use this after listing or searching to read the actual content."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "The Gmail message ID (from list_inbox or search_mail results).",
                    },
                },
                "required": ["message_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_thread",
            "description": (
                "Fetch all messages in a Gmail thread, ordered oldest to newest. "
                "Use this to understand the full conversation context before drafting a reply."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "thread_id": {
                        "type": "string",
                        "description": "The Gmail thread ID.",
                    },
                },
                "required": ["thread_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the internet for current information. "
                "Use this when you need facts, news, or data not available in the email itself."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results (1–5). Default 3.",
                        "default": 3,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stage_reply",
            "description": (
                "Stage a reply draft for human approval (HIL). "
                "IMPORTANT: Do NOT call this until you have read the full thread. "
                "The reply will NOT be sent until the human approves it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "The message ID to reply to.",
                    },
                    "draft_text": {
                        "type": "string",
                        "description": "The full text of the reply to stage for human review.",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Why you drafted this reply — shown to the human reviewer.",
                    },
                },
                "required": ["message_id", "draft_text", "reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stage_delete",
            "description": (
                "Stage a message for deletion (move to Trash) pending human approval. "
                "The message will NOT be deleted until the human approves."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "The message ID to delete.",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Why this message should be deleted — shown to the human reviewer.",
                    },
                },
                "required": ["message_id", "reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stage_new_email",
            "description": (
                "Stage a brand-new outbound email (not a reply) for human approval (HIL). "
                "Use this when composing a fresh email to any recipient. "
                "Do NOT use stage_reply for new emails — use this tool instead. "
                "The email will NOT be sent until the human approves it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address.",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Full email body text to stage for human review.",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Why you composed this email — shown to the human reviewer.",
                    },
                },
                "required": ["to", "subject", "body", "reasoning"],
            },
        },
    },
]


# ── Tool Executor ─────────────────────────────────────────────────────────────

class MailToolExecutor:
    """
    Executes tool calls returned by the agent LLM.
    Receives parsed tool call dicts and routes to the correct connector method.
    """

    def __init__(
        self,
        gmail: GmailConnector,
        web_search: WebSearchConnector,
        bundle: ContextBundle,
    ):
        self.gmail = gmail
        self.web_search = web_search
        self.bundle = bundle

    def execute(self, tool_name: str, tool_args: dict) -> str:
        """
        Dispatch a tool call and return a string result for the next LLM turn.

        Returns a human-readable string summary that gets injected back
        into the agent's message history as a tool_result.
        """
        try:
            if tool_name == "list_inbox":
                return self._list_inbox(**tool_args)

            elif tool_name == "search_mail":
                return self._search_mail(**tool_args)

            elif tool_name == "read_message":
                return self._read_message(**tool_args)

            elif tool_name == "read_thread":
                return self._read_thread(**tool_args)

            elif tool_name == "web_search":
                return self._web_search(**tool_args)

            elif tool_name == "stage_reply":
                return self._stage_reply(**tool_args)

            elif tool_name == "stage_delete":
                return self._stage_delete(**tool_args)

            elif tool_name == "stage_new_email":
                return self._stage_new_email(**tool_args)

            else:
                return f"[ERROR] Unknown tool: {tool_name}"

        except Exception as e:
            return f"[ERROR] Tool {tool_name} failed: {e}"

    # ── Tool implementations ──────────────────────────────────────────────────

    def _list_inbox(self, max_results: int = 10, unread_only: bool = False) -> str:
        labels = ["UNREAD"] if unread_only else ["INBOX"]
        mails = self.gmail.list_messages(max_results=max_results, label_ids=labels)
        if not mails:
            return "Inbox is empty."
        lines = [f"Found {len(mails)} message(s):\n"]
        for i, m in enumerate(mails, 1):
            unread = "● " if "UNREAD" in m.labels else "  "
            lines.append(
                f"{unread}{i}. [{m.message_id}]\n"
                f"   From: {m.sender}\n"
                f"   Subject: {m.subject}\n"
                f"   Date: {m.date}\n"
                f"   Snippet: {m.snippet[:100]}..."
            )
        self.bundle.record_step(
            action="list_inbox",
            status="success",
            input_summary=f"max={max_results} unread_only={unread_only}",
            output_summary=f"Returned {len(mails)} messages",
        )
        return "\n".join(lines)

    def _search_mail(self, query: str, max_results: int = 10) -> str:
        mails = self.gmail.search_messages(query=query, max_results=max_results)
        if not mails:
            return f"No messages found for query: {query}"
        lines = [f"Search '{query}' — {len(mails)} result(s):\n"]
        for i, m in enumerate(mails, 1):
            lines.append(
                f"{i}. [{m.message_id}] {m.subject}\n"
                f"   From: {m.sender} | {m.date}"
            )
        self.bundle.record_step(
            action="search_mail",
            status="success",
            input_summary=query,
            output_summary=f"{len(mails)} results",
        )
        return "\n".join(lines)

    def _read_message(self, message_id: str) -> str:
        data = self.gmail.get_message(message_id)
        meta = data["meta"]
        body = data["body_text"] or "(no plain text body)"
        # Update active_mail on the bundle
        self.bundle.active_mail = meta
        self.bundle.record_step(
            action="read_message",
            status="success",
            input_summary=message_id,
            output_summary=f"Read: {meta.subject} from {meta.sender}",
        )
        return (
            f"Message ID: {meta.message_id}\n"
            f"Thread ID: {meta.thread_id}\n"
            f"From: {meta.sender}\n"
            f"To: {', '.join(meta.recipients)}\n"
            f"Subject: {meta.subject}\n"
            f"Date: {meta.date}\n"
            f"Has attachments: {meta.has_attachments}\n\n"
            f"Body:\n{body[:3000]}"  # cap at 3k chars to stay in context
        )

    def _read_thread(self, thread_id: str) -> str:
        history = self.gmail.get_thread(thread_id)
        self.bundle.thread_history = history
        if not history:
            return f"No messages found in thread: {thread_id}"
        lines = [f"Thread {thread_id} — {len(history)} message(s):\n"]
        for i, msg in enumerate(history, 1):
            lines.append(
                f"── Message {i} ──\n"
                f"From: {msg['sender']} | {msg['date']}\n"
                f"{msg['content'][:500]}...\n"
            )
        self.bundle.record_step(
            action="read_thread",
            status="success",
            input_summary=thread_id,
            output_summary=f"{len(history)} messages in thread",
        )
        return "\n".join(lines)

    def _web_search(self, query: str, max_results: int = 3) -> str:
        results = self.web_search.search(query, max_results=max_results)
        self.bundle.search_results.extend(results)
        lines = [f"Web search: '{query}'\n"]
        for r in results:
            if r["type"] == "direct_answer":
                lines.append(f"[Direct Answer]\n{r['summary']}\n")
            else:
                lines.append(
                    f"[{r['title']}]\n{r['summary'][:300]}\nSource: {r['url']}\n"
                )
        self.bundle.record_step(
            action="web_search",
            status="success",
            input_summary=query,
            output_summary=f"{len(results)} results",
        )
        return "\n".join(lines)

    def _stage_reply(self, message_id: str, draft_text: str, reasoning: str) -> str:
        self.bundle.stage_for_hil(
            action="reply",
            content=draft_text,
            target_id=message_id,
        )
        self.bundle.orchestrator_notes = reasoning
        self.bundle.record_step(
            action="stage_reply",
            status="hil_pending",
            input_summary=f"Reply to {message_id}",
            output_summary="Staged for HIL review",
        )
        return (
            f"Reply staged for human review.\n"
            f"Reasoning: {reasoning}\n"
            f"The human will approve, edit, or reject before sending."
        )

    def _stage_new_email(self, to: str, subject: str, body: str, reasoning: str) -> str:
        self.bundle.stage_new_email(to=to, subject=subject, body=body)
        self.bundle.orchestrator_notes = reasoning
        self.bundle.record_step(
            action="stage_new_email",
            status="hil_pending",
            input_summary=f"New email to {to} — {subject}",
            output_summary="Staged for HIL review",
        )
        return (
            f"New email to '{to}' staged for human review.\n"
            f"Subject: {subject}\n"
            f"Reasoning: {reasoning}\n"
            f"The human will approve, edit, or reject before sending."
        )

    def _stage_delete(self, message_id: str, reasoning: str) -> str:
        self.bundle.stage_for_hil(
            action="delete",
            content=f"Move message {message_id} to Trash",
            target_id=message_id,
        )
        self.bundle.orchestrator_notes = reasoning
        self.bundle.record_step(
            action="stage_delete",
            status="hil_pending",
            input_summary=f"Delete {message_id}",
            output_summary="Staged for HIL review",
        )
        return (
            f"Delete staged for human review.\n"
            f"Reasoning: {reasoning}\n"
            f"The human will approve or reject before deletion."
        )
