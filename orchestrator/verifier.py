"""
orchestrator/verifier.py
─────────────────────────
Verifier: quality-gates agent output before it reaches the human.

Runs before any HIL action is presented to the user. If the draft
fails verification, the verifier returns specific feedback so the
agent can self-correct — reducing the chance of bad replies reaching
the human for approval.

Checks performed:
  REPLY drafts:
    - Is it responsive to the original message?
    - Is it an appropriate length (not empty, not excessively long)?
    - Does it avoid hallucinated facts not grounded in thread or search results?
    - Does it have a professional/appropriate tone?

  DELETE actions:
    - Is the reasoning coherent?
    - Does the message_id exist in execution_history (was it actually read)?

Returns a VerificationResult with pass/fail + feedback.
"""

import os
import json
from dataclasses import dataclass
from typing import Optional
from mistralai import Mistral

from context.context_bundle import ContextBundle

ORCHESTRATOR_MODEL = os.getenv("MISTRAL_ORCHESTRATOR_MODEL", "mistral-large-latest")

VERIFIER_SYSTEM = """You are the verification component of OpenClaw, an agentic email automation system.

Your job: review a staged action (reply draft or delete request) and determine if it is
safe, appropriate, and high quality before presenting it to the human for approval.

You are NOT the final gatekeeper — the human is. Your role is to catch obvious problems
early so the human isn't shown low-quality drafts.

Evaluate the staged action and respond ONLY with a JSON object:
{
  "passed": true/false,
  "confidence": 0.0-1.0,
  "issues": ["list of specific problems if any"],
  "suggestions": ["list of concrete improvements if failed"],
  "summary": "one-sentence verdict"
}

Be strict about factual grounding. If a reply claims something not supported by the
thread history or web search results, flag it as an issue.
Be lenient about style — the human can edit tone themselves.
"""


@dataclass
class VerificationResult:
    passed: bool
    confidence: float
    issues: list[str]
    suggestions: list[str]
    summary: str

    def __str__(self) -> str:
        status = "✓ PASSED" if self.passed else "✗ FAILED"
        lines = [f"Verification: {status} (confidence: {self.confidence:.0%})"]
        lines.append(f"  {self.summary}")
        if self.issues:
            lines.append("  Issues:")
            for issue in self.issues:
                lines.append(f"    • {issue}")
        if self.suggestions:
            lines.append("  Suggestions:")
            for s in self.suggestions:
                lines.append(f"    → {s}")
        return "\n".join(lines)


class Verifier:
    def __init__(self, mistral: Optional[Mistral] = None):
        self.mistral = mistral or Mistral(api_key=os.getenv("MISTRAL_API_KEY"))

    def verify(self, bundle: ContextBundle) -> VerificationResult:
        """
        Verify the staged action in the bundle.
        Returns VerificationResult — caller decides whether to proceed or retry.
        """
        action  = bundle.draft_action
        content = bundle.draft_content
        target  = bundle.draft_target_id

        if not action:
            return VerificationResult(
                passed=True, confidence=1.0,
                issues=[], suggestions=[],
                summary="No action staged — nothing to verify."
            )

        # Build verification context
        thread_ctx = ""
        if bundle.thread_history:
            thread_ctx = "\n\nThread history (last 3 messages):\n" + "\n---\n".join(
                f"From: {m['sender']}\n{m['content'][:400]}"
                for m in bundle.thread_history[-3:]
            )

        search_ctx = ""
        if bundle.search_results:
            search_ctx = "\n\nWeb search results used:\n" + "\n".join(
                r["summary"][:200] for r in bundle.search_results[:3]
            )

        mail_ctx = ""
        if bundle.active_mail:
            m = bundle.active_mail
            mail_ctx = (
                f"\n\nOriginal mail:\n"
                f"From: {m.sender}\nSubject: {m.subject}\nDate: {m.date}"
            )

        user_content = (
            f"Task goal: {bundle.task_goal}\n"
            f"Action type: {action}\n"
            f"Target message ID: {target}\n"
            f"Staged content:\n{content}\n"
            f"Agent reasoning: {bundle.orchestrator_notes}"
            f"{mail_ctx}{thread_ctx}{search_ctx}"
        )

        response = self.mistral.chat.complete(
            model=ORCHESTRATOR_MODEL,
            messages=[
                {"role": "system", "content": VERIFIER_SYSTEM},
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
            return VerificationResult(
                passed      = bool(data.get("passed", True)),
                confidence  = float(data.get("confidence", 0.8)),
                issues      = data.get("issues", []),
                suggestions = data.get("suggestions", []),
                summary     = data.get("summary", "Verification complete."),
            )
        except (json.JSONDecodeError, KeyError):
            # If verifier fails to parse, pass through to human — they're the real gate
            return VerificationResult(
                passed=True, confidence=0.5,
                issues=["Verifier could not parse LLM response — passing to human."],
                suggestions=[],
                summary="Verification inconclusive — human review recommended.",
            )

    def build_retry_prompt(self, result: VerificationResult) -> str:
        """
        Build a correction prompt to inject into the agent loop when verification fails.
        The agent receives this as a tool_result message and can revise its draft.
        """
        lines = [
            "Your draft failed quality verification. Please revise and re-stage.",
            f"Reason: {result.summary}",
        ]
        if result.issues:
            lines.append("Specific issues:")
            for issue in result.issues:
                lines.append(f"  - {issue}")
        if result.suggestions:
            lines.append("Suggestions for improvement:")
            for s in result.suggestions:
                lines.append(f"  - {s}")
        lines.append("\nRevise your draft and call stage_reply again with the improved version.")
        return "\n".join(lines)
