"""
context/context_bundle.py
─────────────────────────
ContextBundle extended for OpenClaw mail + task automation.
Carries all state the orchestrator and agent need across loop iterations,
eliminating the manual human-shuttling problem from prior work.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime, timezone
import json


@dataclass
class MailMeta:
    """Lightweight metadata for a Gmail message or thread."""
    message_id: str
    thread_id: str
    subject: str
    sender: str
    recipients: list[str]
    date: str
    snippet: str
    labels: list[str] = field(default_factory=list)
    has_attachments: bool = False


@dataclass
class ExecutionStep:
    """Single step recorded in execution_history — unchanged from prior arch."""
    step_number: int
    action: str          # e.g. "read_mail", "web_search", "reply_mail"
    status: str          # "success" | "failed" | "hil_pending" | "hil_rejected"
    input_summary: str
    output_summary: str
    hil_approved: Optional[bool] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: Optional[str] = None


@dataclass
class ContextBundle:
    """
    Central state object passed between orchestrator and agent.

    Reuses the proven pattern from the multi-service orchestrator project:
    - execution_history   → reduces loops by giving agent full context
    - task_goal           → single source of truth for what we're trying to do
    - project_context     → OpenClaw-specific: which connector, which account

    New fields for mail automation:
    - active_mail         → the mail being acted on right now
    - thread_history      → prior messages in the same thread (for reply context)
    - search_results      → accumulated web search snippets
    - draft_content       → staged reply/compose text awaiting HIL approval
    """

    # ── Core task fields (reused from prior arch) ────────────────────────────
    task_goal: str
    project_context: str = "openclaw"
    connector: str = "gmail"             # active connector: gmail | calendar | ...
    execution_history: list[ExecutionStep] = field(default_factory=list)
    loop_count: int = 0
    max_loops: int = 3

    # ── Mail-specific fields ─────────────────────────────────────────────────
    active_mail: Optional[MailMeta] = None
    thread_history: list[dict] = field(default_factory=list)   # [{role, content}]
    search_results: list[dict] = field(default_factory=list)   # [{query, summary, url}]

    # ── Calendar-specific fields ─────────────────────────────────────────────
    active_event_id: Optional[str] = None     # event currently being acted on
    calendar_context: list[dict] = field(default_factory=list)  # fetched events cache

    # ── HIL staging area ─────────────────────────────────────────────────────
    draft_content: Optional[str] = None          # text staged for human review
    draft_action: Optional[str] = None           # "reply" | "send" | "delete"
    draft_target_id: Optional[str] = None        # message_id to act on (reply/delete)
    draft_to: Optional[str] = None               # recipient address for new emails
    draft_subject: Optional[str] = None          # subject for new emails
    hil_decision: Optional[str] = None           # "approved" | "rejected" | "edited"

    # ── Orchestrator scratchpad ──────────────────────────────────────────────
    orchestrator_notes: str = ""
    final_answer: Optional[str] = None

    def record_step(
        self,
        action: str,
        status: str,
        input_summary: str,
        output_summary: str,
        hil_approved: Optional[bool] = None,
        error: Optional[str] = None,
    ) -> None:
        """Append a completed step to execution_history."""
        step = ExecutionStep(
            step_number=len(self.execution_history) + 1,
            action=action,
            status=status,
            input_summary=input_summary,
            output_summary=output_summary,
            hil_approved=hil_approved,
            error=error,
        )
        self.execution_history.append(step)
        self.loop_count += 1

    def stage_for_hil(self, action: str, content: str, target_id: str) -> None:
        """Stage a destructive or outbound action for human approval."""
        self.draft_action = action
        self.draft_content = content
        self.draft_target_id = target_id
        self.hil_decision = None

    def stage_new_email(self, to: str, subject: str, body: str) -> None:
        """Stage a new (non-reply) outbound email for human approval."""
        self.draft_action = "send"
        self.draft_content = body
        self.draft_to = to
        self.draft_subject = subject
        self.draft_target_id = None
        self.hil_decision = None

    def clear_hil_stage(self) -> None:
        """Clear staging area after HIL decision is resolved."""
        self.draft_content = None
        self.draft_action = None
        self.draft_target_id = None
        self.draft_to = None
        self.draft_subject = None

    def history_summary(self) -> str:
        """Compact execution history string for orchestrator prompt injection."""
        if not self.execution_history:
            return "No steps executed yet."
        lines = []
        for s in self.execution_history:
            hil_tag = ""
            if s.hil_approved is True:
                hil_tag = " [HIL:approved]"
            elif s.hil_approved is False:
                hil_tag = " [HIL:rejected]"
            lines.append(
                f"  Step {s.step_number} | {s.action} | {s.status}{hil_tag}\n"
                f"    in:  {s.input_summary}\n"
                f"    out: {s.output_summary}"
            )
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize for logging or passing over REST."""
        return {
            "task_goal": self.task_goal,
            "connector": self.connector,
            "loop_count": self.loop_count,
            "execution_history": [
                {
                    "step": s.step_number,
                    "action": s.action,
                    "status": s.status,
                    "hil_approved": s.hil_approved,
                    "timestamp": s.timestamp,
                }
                for s in self.execution_history
            ],
            "active_mail": (
                {
                    "message_id": self.active_mail.message_id,
                    "subject": self.active_mail.subject,
                    "sender": self.active_mail.sender,
                }
                if self.active_mail
                else None
            ),
            "hil_pending": self.draft_action is not None,
        }
