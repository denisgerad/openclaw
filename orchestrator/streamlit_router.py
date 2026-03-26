"""
orchestrator/streamlit_router.py
──────────────────────────────────
Streamlit-compatible Router variant.

The original Router.run() is a blocking loop that halts for terminal HIL input.
Streamlit can't block — it re-runs the entire script on every interaction.

Solution: StreamlitRouter.run_until_hil()
  - Executes the agent loop until EITHER task completion OR a HIL action is staged
  - Returns a RouterState enum so the Streamlit app knows what to render next
  - The Streamlit app stores the ContextBundle in session_state between runs
  - When the human approves/rejects via UI, the app calls resume_after_hil()

State machine:
  IDLE → PLANNING → RUNNING → HIL_PENDING → RUNNING → ... → COMPLETE | ERROR
"""

import os
import json
from enum import Enum
from typing import Optional, Callable
from mistralai import Mistral

from context.context_bundle import ContextBundle
from orchestrator.planner import Planner
from orchestrator.verifier import Verifier
from orchestrator.debugger import Debugger, FailureType, RecoveryAction
from orchestrator.connectors.gmail import GmailConnector
from orchestrator.connectors.web_search import WebSearchConnector
from agent.tools.mail_tools import MailToolExecutor, MAIL_TOOL_SCHEMAS
from hil.cli_approver import requires_hil, execute_approved_action

ORCHESTRATOR_MODEL = os.getenv("MISTRAL_ORCHESTRATOR_MODEL", "mistral-large-latest")
MAX_PLAN_RETRIES   = 2
MAX_VERIFY_RETRIES = 2
MAX_TOTAL_LOOPS    = int(os.getenv("MAX_LOOP_RETRIES", "3")) * 5


class RouterState(str, Enum):
    IDLE        = "idle"
    PLANNING    = "planning"
    RUNNING     = "running"
    HIL_PENDING = "hil_pending"
    COMPLETE    = "complete"
    ERROR       = "error"


def _build_agent_system(bundle: ContextBundle) -> str:
    return f"""You are OpenClaw's execution agent — an intelligent email automation assistant.

Your goal: {bundle.task_goal}

Orchestrator plan:
{bundle.orchestrator_notes}

Available tools:
  READ (auto-execute, no approval):
    list_inbox, search_mail, read_message, read_thread, web_search
  WRITE (human approval required — stage only):
    stage_reply, stage_delete

Rules:
1. Read before write. Always fetch thread context before staging a reply.
2. Use web_search if you need external facts to compose an accurate reply.
3. stage_reply / stage_delete only STAGES the action — it does NOT execute.
4. One tool per turn. Check results before proceeding.
5. When done, respond with TASK_COMPLETE followed by a brief summary.

Execution history:
{bundle.history_summary()}
"""


class StreamlitRouter:
    """
    Router designed for Streamlit's stateless re-run model.

    Usage in app.py:
        router = StreamlitRouter(gmail, web_search)
        state  = router.run_until_hil(bundle, log_fn=st.write)
        # → HIL_PENDING: render approve/reject UI, store bundle in session_state
        # → COMPLETE: render summary
        # On approve/reject button click:
        state = router.resume_after_hil(bundle, decision, edited_content, log_fn)
    """

    def __init__(
        self,
        gmail: GmailConnector,
        web_search: WebSearchConnector,
        mistral: Optional[Mistral] = None,
    ):
        self.mistral    = mistral or Mistral(api_key=os.getenv("MISTRAL_API_KEY"))
        self.gmail      = gmail
        self.web_search = web_search
        self.planner    = Planner(self.mistral)
        self.verifier   = Verifier(self.mistral)
        self.debugger   = Debugger(self.mistral)

    # ── Public API ────────────────────────────────────────────────────────────

    def run_until_hil(
        self,
        bundle: ContextBundle,
        log_fn: Optional[Callable] = None,
    ) -> RouterState:
        """
        Run planner + agent loop until HIL pause or completion.
        Logs progress via log_fn (called with plain strings).
        Returns RouterState.
        """
        log = log_fn or (lambda msg: None)

        # Plan (only on first run — no execution history yet)
        if not bundle.execution_history:
            log("🗺️  **Planning task...**")
            plan = self.planner.plan(bundle)
            log(f"📋 **Plan:** {plan.get('plan_summary', '')}")
            steps = plan.get("steps", [])
            if steps:
                for s in steps:
                    hil = " `[HIL]`" if s.get("hil") else ""
                    log(f"  {s['step']}. `{s['tool']}`{hil} — {s['purpose']}")

        return self._agent_loop(bundle, log)

    def resume_after_hil(
        self,
        bundle: ContextBundle,
        decision: str,               # "approved" | "rejected" | "edited"
        edited_content: Optional[str] = None,
        log_fn: Optional[Callable] = None,
    ) -> RouterState:
        """
        Resume execution after a human HIL decision.

        Args:
            bundle:          The bundle paused at HIL_PENDING.
            decision:        Human's choice.
            edited_content:  Replacement draft text if decision == "edited".
            log_fn:          Progress logger.
        """
        log = log_fn or (lambda msg: None)

        if decision in ("approved", "edited"):
            if decision == "edited" and edited_content:
                bundle.draft_content = edited_content
            log(f"✅ **HIL approved** — executing `{bundle.draft_action}`")
            execute_approved_action(bundle, gmail=self.gmail)

        elif decision == "rejected":
            log("❌ **HIL rejected** — analysing failure...")
            last = bundle.execution_history[-1] if bundle.execution_history else None
            reason = last.output_summary if last else "no reason"
            report = self.debugger.handle_hil_rejection(bundle, reason)
            log(f"🔍 **Debugger:** {report.diagnosis}")
            if report.should_replan:
                bundle.orchestrator_notes = (
                    f"REPLAN after rejection: {report.recovery_prompt}\n"
                    + bundle.orchestrator_notes
                )
                log("🗺️  **Replanning...**")
                plan = self.planner.plan(bundle)
                log(f"📋 **New plan:** {plan.get('plan_summary', '')}")

        if bundle.final_answer:
            return RouterState.COMPLETE

        return self._agent_loop(bundle, log)

    # ── Internal loop ─────────────────────────────────────────────────────────

    def _agent_loop(
        self,
        bundle: ContextBundle,
        log: Callable,
    ) -> RouterState:
        """Run agent loop; return state when HIL pause or completion."""
        executor = MailToolExecutor(
            gmail=self.gmail,
            web_search=self.web_search,
            bundle=bundle,
        )

        messages = [
            {"role": "system", "content": _build_agent_system(bundle)},
            {"role": "user",   "content": bundle.task_goal},
        ]
        if bundle.execution_history:
            messages.append({
                "role": "user",
                "content": (
                    f"Continuing. History:\n{bundle.history_summary()}\n"
                    "Continue with the next required action."
                ),
            })

        verify_retries = getattr(bundle, "_verify_retries", 0)

        for _ in range(MAX_TOTAL_LOOPS * 8):
            try:
                response = self.mistral.chat.complete(
                    model=ORCHESTRATOR_MODEL,
                    messages=messages,
                    tools=MAIL_TOOL_SCHEMAS,
                    tool_choice="auto",
                )
            except Exception as e:
                log(f"❌ **Mistral error:** {e}")
                bundle.final_answer = f"API error: {e}"
                return RouterState.ERROR

            msg           = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            if finish_reason != "tool_calls" or not msg.tool_calls:
                content = msg.content or ""
                if "TASK_COMPLETE" in content:
                    bundle.final_answer = content
                    log("✅ **Task complete.**")
                    return RouterState.COMPLETE
                if content:
                    bundle.final_answer = content
                return RouterState.COMPLETE

            # Tool calls
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id, "type": "function",
                        "function": {"name": tc.function.name,
                                     "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                log(f"🔧 **Tool:** `{name}` — `{str(args)[:80]}`")
                result = executor.execute(name, args)
                log(f"↩️  `{result[:150]}{'...' if len(result) > 150 else ''}`")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

                # HIL staged — verify then pause
                if bundle.draft_action and requires_hil(bundle.draft_action):
                    verification = self.verifier.verify(bundle)
                    log(f"🔍 **Verifier:** {verification.summary}")

                    if not verification.passed and verify_retries < MAX_VERIFY_RETRIES:
                        verify_retries += 1
                        bundle._verify_retries = verify_retries
                        log(f"⚠️  **Verification failed** (attempt {verify_retries}/{MAX_VERIFY_RETRIES}) — asking agent to revise")
                        bundle.orchestrator_notes += (
                            "\n[Verification failed]\n"
                            + self.verifier.build_retry_prompt(verification)
                        )
                        bundle.clear_hil_stage()
                        # Inject correction into messages and continue loop
                        messages.append({
                            "role": "user",
                            "content": self.verifier.build_retry_prompt(verification),
                        })
                        break  # restart inner tool loop with new message

                    # Verification passed → pause for human
                    bundle._verify_retries = 0
                    return RouterState.HIL_PENDING

                if result.startswith("[ERROR]"):
                    bundle.record_step(
                        action=name, status="failed",
                        input_summary=str(args)[:100],
                        output_summary=result[:200],
                        error=result,
                    )
                    log(f"❌ **Tool error:** {result[:200]}")
                    report = self.debugger.diagnose(bundle, FailureType.TOOL_ERROR, result)
                    log(f"🔍 **Debugger:** {report.diagnosis}")
                    if report.recovery_action == RecoveryAction.ABORT:
                        bundle.final_answer = f"Aborted: {report.diagnosis}"
                        return RouterState.ERROR
                    if report.should_replan:
                        bundle.orchestrator_notes += f"\n[Recovery] {report.recovery_prompt}"
                        messages.append({"role": "user", "content": report.recovery_prompt})

        bundle.final_answer = "Max loops reached."
        return RouterState.ERROR
