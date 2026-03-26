"""
orchestrator/debugger.py
─────────────────────────
Debugger: diagnoses agent failures and produces recovery strategies.

Triggered when:
  - An agent tool call returns an [ERROR] result
  - The agent loop exceeds MAX_LOOPS without completing
  - Verification fails more than MAX_VERIFY_RETRIES times
  - A HIL action is rejected by the human (to understand why and adapt)

The debugger analyses the execution_history and error context, then:
  1. Classifies the failure type
  2. Suggests a recovery action (retry, replan, escalate to human)
  3. Optionally patches the ContextBundle to guide the next loop iteration

Failure types:
  TOOL_ERROR      — connector/API failure (auth, network, rate limit)
  AGENT_LOOP      — agent spinning without progress
  VERIFY_FAIL     — draft quality below threshold after retries
  HIL_REJECTION   — human rejected the staged action
  CONTEXT_MISSING — agent tried to act without reading first
"""

import os
import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from mistralai import Mistral

from context.context_bundle import ContextBundle

ORCHESTRATOR_MODEL = os.getenv("MISTRAL_ORCHESTRATOR_MODEL", "mistral-large-latest")


class FailureType(str, Enum):
    TOOL_ERROR       = "tool_error"
    AGENT_LOOP       = "agent_loop"
    VERIFY_FAIL      = "verify_fail"
    HIL_REJECTION    = "hil_rejection"
    CONTEXT_MISSING  = "context_missing"
    UNKNOWN          = "unknown"


class RecoveryAction(str, Enum):
    RETRY            = "retry"         # retry the same step
    REPLAN           = "replan"        # generate a new plan
    ESCALATE         = "escalate"      # surface to human with explanation
    ABORT            = "abort"         # task cannot be completed


@dataclass
class DebugReport:
    failure_type: FailureType
    recovery_action: RecoveryAction
    diagnosis: str
    recovery_prompt: str          # injected into agent loop on retry/replan
    should_replan: bool
    should_escalate: bool

    def __str__(self) -> str:
        return (
            f"[Debugger] {self.failure_type.value} → {self.recovery_action.value}\n"
            f"  Diagnosis: {self.diagnosis}"
        )


DEBUGGER_SYSTEM = """You are the debugging component of OpenClaw, an agentic email automation system.

Given a failure report and execution history, diagnose what went wrong and recommend recovery.

Respond ONLY with a JSON object:
{
  "failure_type": "tool_error|agent_loop|verify_fail|hil_rejection|context_missing|unknown",
  "recovery_action": "retry|replan|escalate|abort",
  "diagnosis": "one sentence explaining root cause",
  "recovery_prompt": "instruction to inject into agent context to guide recovery",
  "should_replan": true/false,
  "should_escalate": true/false
}

Guidelines:
- tool_error + network/auth issue → escalate (human needs to fix credentials)
- tool_error + temporary → retry
- agent_loop → replan (agent is confused, needs fresh instructions)
- verify_fail after 2+ retries → escalate (human should write the reply)
- hil_rejection → replan (understand why human rejected and adjust approach)
- context_missing → retry with specific instruction to read first
"""


class Debugger:
    def __init__(self, mistral: Optional[Mistral] = None):
        self.mistral = mistral or Mistral(api_key=os.getenv("MISTRAL_API_KEY"))

    def diagnose(
        self,
        bundle: ContextBundle,
        failure_type: FailureType,
        error_detail: str = "",
    ) -> DebugReport:
        """
        Diagnose a failure and return a recovery plan.

        Args:
            bundle:        Current ContextBundle with execution_history.
            failure_type:  Classified failure type.
            error_detail:  The raw error string or description.
        """
        user_content = (
            f"Task goal: {bundle.task_goal}\n"
            f"Failure type: {failure_type.value}\n"
            f"Error detail: {error_detail or 'none'}\n"
            f"Loop count: {bundle.loop_count}\n"
            f"Connector: {bundle.connector}\n\n"
            f"Execution history:\n{bundle.history_summary()}"
        )

        response = self.mistral.chat.complete(
            model=ORCHESTRATOR_MODEL,
            messages=[
                {"role": "system", "content": DEBUGGER_SYSTEM},
                {"role": "user",   "content": user_content},
            ],
        )

        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        try:
            data = json.loads(raw)
            return DebugReport(
                failure_type     = FailureType(data.get("failure_type", "unknown")),
                recovery_action  = RecoveryAction(data.get("recovery_action", "escalate")),
                diagnosis        = data.get("diagnosis", "Unknown failure."),
                recovery_prompt  = data.get("recovery_prompt", "Please retry the task."),
                should_replan    = bool(data.get("should_replan", False)),
                should_escalate  = bool(data.get("should_escalate", True)),
            )
        except (json.JSONDecodeError, ValueError):
            return DebugReport(
                failure_type     = failure_type,
                recovery_action  = RecoveryAction.ESCALATE,
                diagnosis        = f"Debugger parse error. Raw error: {error_detail[:100]}",
                recovery_prompt  = "An error occurred. Please review and retry.",
                should_replan    = False,
                should_escalate  = True,
            )

    def handle_hil_rejection(self, bundle: ContextBundle, rejection_reason: str) -> DebugReport:
        """
        Specialised diagnosis for HIL rejection — the human said no.
        Helps the agent understand what to change on the next attempt.
        """
        detail = (
            f"Human rejected the staged action.\n"
            f"Action: {bundle.draft_action}\n"
            f"Rejection reason: {rejection_reason or 'no reason given'}\n"
            f"Draft content was:\n{(bundle.draft_content or '')[:300]}"
        )
        return self.diagnose(bundle, FailureType.HIL_REJECTION, detail)

    def detect_loop(self, bundle: ContextBundle) -> bool:
        """
        Detect if the agent is spinning — same action repeated without progress.
        Returns True if a loop is detected.
        """
        if len(bundle.execution_history) < 3:
            return False
        last_three = [s.action for s in bundle.execution_history[-3:]]
        # If last 3 actions are identical, we're looping
        return len(set(last_three)) == 1
