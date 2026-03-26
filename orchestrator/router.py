"""
orchestrator/router.py
───────────────────────
Router: the central nervous system of OpenClaw's orchestrator.

Coordinates the full lifecycle of a task:
  1. Plan       → Planner generates step-by-step strategy
  2. Execute    → Agent loop runs tool calls
  3. Verify     → Verifier checks staged HIL actions before human sees them
  4. HIL        → CLI approver gates write operations
  5. Debug      → Debugger handles failures and decides retry/replan/escalate
  6. Complete   → ContextBundle.final_answer is set

This is the layer main.py talks to — it no longer needs to manage
the orchestrator internals directly.

Loop budget:
  MAX_PLAN_RETRIES   = 2   (how many times to replan if stuck)
  MAX_VERIFY_RETRIES = 2   (how many times agent can revise a bad draft)
  MAX_TOTAL_LOOPS    = 15  (absolute ceiling before escalation)
"""

import os
import json
from typing import Optional
from mistralai import Mistral
from colorama import Fore, Style
from rich.console import Console
from rich.panel import Panel

from context.context_bundle import ContextBundle
from orchestrator.planner import Planner
from orchestrator.verifier import Verifier
from orchestrator.debugger import Debugger, FailureType, RecoveryAction
from orchestrator.connectors.gmail import GmailConnector
from orchestrator.connectors.web_search import WebSearchConnector
from agent.tools.mail_tools import MailToolExecutor, MAIL_TOOL_SCHEMAS
from hil.cli_approver import review_and_decide, execute_approved_action, requires_hil

console = Console()

ORCHESTRATOR_MODEL  = os.getenv("MISTRAL_ORCHESTRATOR_MODEL", "mistral-large-latest")
MAX_PLAN_RETRIES    = 2
MAX_VERIFY_RETRIES  = 2
MAX_TOTAL_LOOPS     = int(os.getenv("MAX_LOOP_RETRIES", "3")) * 5


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
5. When all tasks are done or all actions are staged, respond with TASK_COMPLETE
   followed by a brief summary of what was accomplished.

Execution history:
{bundle.history_summary()}
"""


class Router:
    """
    Orchestrator router — drives the full task lifecycle.
    Instantiate once per session; call run(bundle) to execute a task.
    """

    def __init__(
        self,
        gmail: GmailConnector,
        web_search: WebSearchConnector,
        mistral: Optional[Mistral] = None,
    ):
        api_key     = os.getenv("MISTRAL_API_KEY")
        self.mistral    = mistral or Mistral(api_key=api_key)
        self.gmail      = gmail
        self.web_search = web_search
        self.planner    = Planner(self.mistral)
        self.verifier   = Verifier(self.mistral)
        self.debugger   = Debugger(self.mistral)

    # ── Public entry point ────────────────────────────────────────────────────

    def run(self, bundle: ContextBundle) -> ContextBundle:
        """
        Execute a task end-to-end.
        Returns the bundle with final_answer set (or escalation note).
        """
        console.print(f"\n[bold cyan]  OpenClaw Router[/bold cyan] — starting task")
        console.print(f"  [dim]Goal:[/dim] {bundle.task_goal}\n")

        # ── Step 1: Plan ──────────────────────────────────────────────────────
        plan = self._run_planner(bundle)

        plan_retries    = 0
        verify_retries  = 0
        total_loops     = 0

        # ── Main execution loop ───────────────────────────────────────────────
        while total_loops < MAX_TOTAL_LOOPS:
            total_loops += 1

            # ── Step 2: Agent loop ────────────────────────────────────────────
            loop_result = self._run_agent_loop(bundle)

            # Agent finished cleanly with no HIL action pending
            if loop_result == "complete":
                console.print(f"\n[green]  ✓ Task complete.[/green]")
                break

            # Agent loop hit an error
            if loop_result == "error":
                report = self.debugger.diagnose(
                    bundle, FailureType.TOOL_ERROR,
                    "Agent loop returned error state."
                )
                console.print(f"\n[red]  {report}[/red]")
                if report.recovery_action == RecoveryAction.ABORT:
                    bundle.final_answer = f"Task aborted: {report.diagnosis}"
                    break
                if report.should_replan and plan_retries < MAX_PLAN_RETRIES:
                    plan_retries += 1
                    bundle.orchestrator_notes += f"\n[Recovery] {report.recovery_prompt}"
                    plan = self._run_planner(bundle)
                    continue
                # Escalate
                bundle.final_answer = f"Escalated to human: {report.diagnosis}"
                break

            # Agent loop detected a spin/loop
            if self.debugger.detect_loop(bundle):
                report = self.debugger.diagnose(bundle, FailureType.AGENT_LOOP)
                console.print(f"\n[yellow]  ⚠ Loop detected. {report.diagnosis}[/yellow]")
                if plan_retries < MAX_PLAN_RETRIES:
                    plan_retries += 1
                    bundle.orchestrator_notes = (
                        f"REPLAN (loop detected): {report.recovery_prompt}\n"
                        + bundle.orchestrator_notes
                    )
                    plan = self._run_planner(bundle)
                    continue
                bundle.final_answer = "Max replans reached. Escalating to human."
                break

            # ── Step 3: HIL action staged ─────────────────────────────────────
            if loop_result == "hil_pending":
                # Verify before showing to human
                verification = self.verifier.verify(bundle)
                console.print(f"\n[dim]{verification}[/dim]")

                if not verification.passed and verify_retries < MAX_VERIFY_RETRIES:
                    verify_retries += 1
                    console.print(
                        f"[yellow]  ⚠ Draft failed verification "
                        f"(attempt {verify_retries}/{MAX_VERIFY_RETRIES}). "
                        f"Asking agent to revise...[/yellow]"
                    )
                    # Inject feedback back into agent via orchestrator_notes
                    bundle.orchestrator_notes += (
                        f"\n[Verification failed]\n"
                        + self.verifier.build_retry_prompt(verification)
                    )
                    # Clear the failed draft so agent re-stages
                    bundle.clear_hil_stage()
                    continue  # re-run agent loop

                # Verification passed (or retries exhausted) → show to human
                decision = review_and_decide(bundle)

                if decision in ("approved", "edited"):
                    execute_approved_action(bundle, gmail=self.gmail)
                    verify_retries = 0

                elif decision == "rejected":
                    # Diagnose the rejection and adapt
                    last_step = bundle.execution_history[-1] if bundle.execution_history else None
                    rejection_reason = (
                        last_step.output_summary if last_step else "no reason"
                    )
                    report = self.debugger.handle_hil_rejection(bundle, rejection_reason)
                    console.print(f"\n[yellow]  {report}[/yellow]")

                    if report.should_replan and plan_retries < MAX_PLAN_RETRIES:
                        plan_retries += 1
                        bundle.orchestrator_notes = (
                            f"REPLAN after rejection: {report.recovery_prompt}\n"
                            + bundle.orchestrator_notes
                        )
                        plan = self._run_planner(bundle)

                # Continue loop — there may be more work after this HIL action
                if bundle.final_answer:
                    break
                continue

        # ── Final answer fallback ─────────────────────────────────────────────
        if not bundle.final_answer:
            bundle.final_answer = (
                f"Task ended after {bundle.loop_count} steps. "
                f"Check execution history for details."
            )

        return bundle

    # ── Private helpers ───────────────────────────────────────────────────────

    def _run_planner(self, bundle: ContextBundle) -> dict:
        """Run the planner and display the plan."""
        console.print("\n[bold cyan]  Planning...[/bold cyan]")
        plan = self.planner.plan(bundle)
        console.print(
            Panel(
                self.planner.format_plan_for_display(plan),
                title="[bold]Execution Plan[/bold]",
                border_style="cyan",
            )
        )
        return plan

    def _run_agent_loop(self, bundle: ContextBundle) -> str:
        """
        Run one pass of the agent tool-call loop.

        Returns:
          "complete"    — agent finished (TASK_COMPLETE or no more tool calls)
          "hil_pending" — agent staged a HIL action
          "error"       — unrecoverable error in tool execution
        """
        executor = MailToolExecutor(
            gmail=self.gmail,
            web_search=self.web_search,
            bundle=bundle,
        )

        messages = [
            {"role": "system", "content": _build_agent_system(bundle)},
            {"role": "user",   "content": bundle.task_goal},
        ]

        # Inject execution history as assistant context for continuity
        if bundle.execution_history:
            messages.append({
                "role": "user",
                "content": (
                    f"Continuing from prior steps. History:\n{bundle.history_summary()}\n"
                    "Continue with the next required action."
                ),
            })

        inner_loops = 0
        max_inner   = 8  # per-pass cap

        while inner_loops < max_inner:
            inner_loops += 1

            try:
                response = self.mistral.chat.complete(
                    model=ORCHESTRATOR_MODEL,
                    messages=messages,
                    tools=MAIL_TOOL_SCHEMAS,
                    tool_choice="auto",
                )
            except Exception as e:
                console.print(f"[red]  ✗ Mistral API error: {e}[/red]")
                return "error"

            msg           = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            # ── Text response (no tool call) ──────────────────────────────
            if finish_reason != "tool_calls" or not msg.tool_calls:
                content = msg.content or ""
                if content:
                    console.print(
                        Panel(content, title="[bold green]Agent[/bold green]",
                              border_style="green")
                    )
                if "TASK_COMPLETE" in content:
                    bundle.final_answer = content
                return "complete"

            # ── Tool calls ────────────────────────────────────────────────
            tool_calls_payload = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": tool_calls_payload,
            })

            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                console.print(
                    f"  [cyan]→[/cyan] [bold]{name}[/bold]  "
                    f"[dim]{str(args)[:80]}[/dim]"
                )
                result = executor.execute(name, args)
                short  = result[:200] + ("..." if len(result) > 200 else "")
                console.print(f"  [green]←[/green] {short}")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

                # HIL action staged — hand off to router's HIL flow
                if bundle.draft_action and requires_hil(bundle.draft_action):
                    return "hil_pending"

                # Error result from tool — let debugger handle
                if result.startswith("[ERROR]"):
                    bundle.record_step(
                        action=name, status="failed",
                        input_summary=str(args)[:100],
                        output_summary=result[:200],
                        error=result,
                    )
                    return "error"

        # Inner loop exhausted
        return "complete"
