"""
orchestrator/planner.py
────────────────────────
Planner: turns a free-form task goal into an ordered execution plan.

The planner runs ONCE at the start of a session (or after a major replanning
trigger) and writes a structured plan into ContextBundle.orchestrator_notes.

It does NOT execute steps — it only reasons about WHAT needs to happen and
in what order, given the available tools and connectors.

Design principle (from prior arch):
  The orchestrator should think in terms of ContextBundle state changes.
  Each plan step should move the bundle closer to final_answer with
  minimal back-and-forth.
"""

import os
import json
from typing import Optional
from mistralai import Mistral

from context.context_bundle import ContextBundle

ORCHESTRATOR_MODEL = os.getenv("MISTRAL_ORCHESTRATOR_MODEL", "mistral-large-latest")

PLANNER_SYSTEM = """You are the planning component of OpenClaw, an agentic email and calendar automation system.

Given a user task, produce a concise execution plan as a numbered list of steps.

Available tools the agent can call:
  EMAIL — READ (no approval needed):
    - list_inbox(max_results, unread_only)
    - search_mail(query, max_results)
    - read_message(message_id)
    - read_thread(thread_id)
    - web_search(query, max_results)

  EMAIL — WRITE (requires human approval via HIL):
    - stage_reply(message_id, draft_text, reasoning)
    - stage_delete(message_id, reasoning)
    - stage_new_email(to, subject, body, reasoning)

  CALENDAR — READ (no approval needed):
    - list_calendars()
    - list_events(calendar_id, time_min, time_max, max_results)
    - get_event(event_id, calendar_id)
    - search_events(query, calendar_id, max_results, days_ahead)
    - check_free_busy(emails, time_min, time_max, timezone)
    - find_free_slots(emails, duration_minutes, days_ahead, timezone)

  CALENDAR — WRITE (requires human approval via HIL):
    - stage_create_event(title, start, end, calendar_id, description, location, attendees, timezone, add_google_meet, recurrence, reasoning)
    - stage_update_event(event_id, updates, calendar_id, reasoning)
    - stage_delete_event(event_id, calendar_id, reasoning)
    - stage_rsvp(event_id, response, calendar_id, reasoning)

Rules for good plans:
1. Read before write — gather context before staging any action.
2. For scheduling with a specific time: go straight to stage_create_event [HIL].
3. For scheduling without a time: use find_free_slots first, then stage_create_event [HIL].
4. Parse natural-language times into ISO 8601 before passing to calendar tools.
5. Minimise loops — combine reads where possible.
6. Flag HIL steps explicitly with [HIL] tag.
7. Keep the plan to 3–7 steps maximum.

Respond ONLY with a JSON object in this exact format:
{
  "plan_summary": "one-sentence description of the approach",
  "steps": [
    {"step": 1, "tool": "tool_name", "purpose": "why this step", "hil": false},
    ...
  ],
  "requires_web_search": true/false,
  "estimated_hil_actions": 0
}
"""


class Planner:
    def __init__(self, mistral: Optional[Mistral] = None):
        self.mistral = mistral or Mistral(api_key=os.getenv("MISTRAL_API_KEY"))

    def plan(self, bundle: ContextBundle) -> dict:
        """
        Generate an execution plan for the task in the bundle.
        Writes plan summary to bundle.orchestrator_notes.
        Returns the raw plan dict.
        """
        response = self.mistral.chat.complete(
            model=ORCHESTRATOR_MODEL,
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"Task: {bundle.task_goal}\n\n"
                        f"Connector in use: {bundle.connector}\n"
                        f"Execution history so far:\n{bundle.history_summary()}"
                    ),
                },
            ],
        )

        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        try:
            plan = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: treat as unstructured and continue
            plan = {
                "plan_summary": raw[:200],
                "steps": [],
                "requires_web_search": False,
                "estimated_hil_actions": 0,
            }

        # Write summary into bundle so agent can reference it
        bundle.orchestrator_notes = (
            f"Plan: {plan.get('plan_summary', '')}\n"
            f"Steps: {len(plan.get('steps', []))}\n"
            f"HIL actions expected: {plan.get('estimated_hil_actions', '?')}"
        )

        return plan

    def format_plan_for_display(self, plan: dict) -> str:
        """Return a human-readable plan string for terminal display."""
        lines = [
            f"  Plan: {plan.get('plan_summary', 'N/A')}",
            f"  Web search needed: {plan.get('requires_web_search', False)}",
            f"  Expected HIL approvals: {plan.get('estimated_hil_actions', '?')}",
            "",
        ]
        for s in plan.get("steps", []):
            hil_tag = "  [HIL]" if s.get("hil") else ""
            lines.append(f"  {s['step']}. [{s['tool']}]{hil_tag} — {s['purpose']}")
        return "\n".join(lines)
