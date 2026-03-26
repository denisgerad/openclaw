"""
agent/tools/calendar_tools.py
───────────────────────────────
Calendar tool definitions for the OpenClaw agent.

READ tools (agent executes directly, no HIL):
  list_calendars, list_events, get_event, search_events,
  check_free_busy, find_free_slots

WRITE tools (agent stages only — HIL required):
  stage_create_event, stage_update_event, stage_delete_event,
  stage_rsvp

All write intents are stored in ContextBundle.draft_* and
executed only after human approval via hil/cli_approver.py.
"""

import json
from typing import Optional
from datetime import datetime, timedelta, timezone

from context.context_bundle import ContextBundle
from orchestrator.connectors.calendar import CalendarConnector


# ── Tool Schemas ──────────────────────────────────────────────────────────────

CALENDAR_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_calendars",
            "description": (
                "List all Google Calendars the user has access to. "
                "Call this first to discover available calendar IDs before listing events."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_events",
            "description": (
                "List upcoming events from a calendar. "
                "Use time_min/time_max to scope a date range. "
                "Returns title, time, location, attendees, Meet link for each event."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "calendar_id": {
                        "type": "string",
                        "description": "Calendar ID (default: 'primary'). Get IDs from list_calendars.",
                        "default": "primary",
                    },
                    "time_min": {
                        "type": "string",
                        "description": "ISO 8601 start bound. e.g. '2025-01-20T00:00:00Z'. Defaults to now.",
                    },
                    "time_max": {
                        "type": "string",
                        "description": "ISO 8601 end bound. e.g. '2025-01-27T23:59:59Z'.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of events to return (1–50). Default 20.",
                        "default": 20,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_event",
            "description": "Fetch full details of a single calendar event by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "The Google Calendar event ID.",
                    },
                    "calendar_id": {
                        "type": "string",
                        "description": "Calendar containing the event (default: 'primary').",
                        "default": "primary",
                    },
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_events",
            "description": (
                "Search calendar events by keyword. "
                "Searches across title, description, location, and attendees. "
                "Useful for finding a specific meeting or all events related to a project."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query string.",
                    },
                    "calendar_id": {
                        "type": "string",
                        "description": "Calendar to search (default: 'primary').",
                        "default": "primary",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max events to return (default: 10).",
                        "default": 10,
                    },
                    "days_ahead": {
                        "type": "integer",
                        "description": "How many days ahead to search (default: 90).",
                        "default": 90,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_free_busy",
            "description": (
                "Check free/busy status for one or more people over a time window. "
                "Use this before scheduling to avoid conflicts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "emails": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of email addresses to check.",
                    },
                    "time_min": {
                        "type": "string",
                        "description": "ISO 8601 start. Defaults to now.",
                    },
                    "time_max": {
                        "type": "string",
                        "description": "ISO 8601 end. Defaults to 7 days from now.",
                    },
                    "timezone": {
                        "type": "string",
                        "description": "IANA timezone (e.g. 'Asia/Kolkata', 'America/New_York'). Default: UTC.",
                        "default": "UTC",
                    },
                },
                "required": ["emails"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_free_slots",
            "description": (
                "Find available meeting slots where ALL listed attendees are free. "
                "Checks free/busy and returns suggested time slots within working hours."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "emails": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of attendee emails to check availability for.",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Meeting duration in minutes (default: 60).",
                        "default": 60,
                    },
                    "days_ahead": {
                        "type": "integer",
                        "description": "How many days ahead to search (default: 7).",
                        "default": 7,
                    },
                    "timezone": {
                        "type": "string",
                        "description": "IANA timezone string (e.g. 'Asia/Kolkata'). Default: UTC.",
                        "default": "UTC",
                    },
                },
                "required": ["emails"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stage_create_event",
            "description": (
                "Stage a new calendar event for human approval (HIL). "
                "The event will NOT be created until the human approves. "
                "Use find_free_slots first to suggest a good time."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title."},
                    "start": {"type": "string", "description": "ISO 8601 start datetime."},
                    "end":   {"type": "string", "description": "ISO 8601 end datetime."},
                    "calendar_id": {
                        "type": "string",
                        "description": "Target calendar (default: 'primary').",
                        "default": "primary",
                    },
                    "description":    {"type": "string", "description": "Event description."},
                    "location":       {"type": "string", "description": "Location or video link."},
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of attendee email addresses.",
                    },
                    "timezone":       {"type": "string", "description": "IANA timezone.", "default": "UTC"},
                    "add_google_meet":{"type": "boolean", "description": "Add a Google Meet link.", "default": False},
                    "recurrence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "RRULE strings for recurring events, e.g. ['RRULE:FREQ=WEEKLY;COUNT=4'].",
                    },
                    "reasoning": {"type": "string", "description": "Why this event is being created — shown to human."},
                },
                "required": ["title", "start", "end", "reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stage_update_event",
            "description": (
                "Stage changes to an existing calendar event for human approval (HIL). "
                "Use get_event first to confirm the current event details."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "ID of the event to update."},
                    "calendar_id": {"type": "string", "description": "Calendar ID.", "default": "primary"},
                    "updates": {
                        "type": "object",
                        "description": (
                            "Fields to change. Any of: title, description, location, "
                            "start (ISO 8601), end (ISO 8601), attendees (list of emails), "
                            "status ('confirmed'|'cancelled'), timezone."
                        ),
                    },
                    "reasoning": {"type": "string", "description": "Why this update is needed."},
                },
                "required": ["event_id", "updates", "reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stage_delete_event",
            "description": (
                "Stage deletion of a calendar event for human approval (HIL). "
                "Use get_event first to confirm you have the right event."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id":    {"type": "string", "description": "ID of the event to delete."},
                    "calendar_id": {"type": "string", "description": "Calendar ID.", "default": "primary"},
                    "reasoning":   {"type": "string", "description": "Why this event should be deleted."},
                },
                "required": ["event_id", "reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stage_rsvp",
            "description": (
                "Stage an RSVP response to a calendar invite for human approval (HIL). "
                "Use get_event first to verify the invite details."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id":    {"type": "string", "description": "ID of the event to RSVP to."},
                    "calendar_id": {"type": "string", "description": "Calendar ID.", "default": "primary"},
                    "response": {
                        "type": "string",
                        "enum": ["accepted", "declined", "tentative"],
                        "description": "RSVP response.",
                    },
                    "reasoning": {"type": "string", "description": "Reason for this response."},
                },
                "required": ["event_id", "response", "reasoning"],
            },
        },
    },
]


# ── Tool Executor ─────────────────────────────────────────────────────────────

class CalendarToolExecutor:
    """
    Executes calendar tool calls from the agent.
    Read ops run immediately; write ops are staged in the bundle for HIL.
    """

    def __init__(self, calendar: CalendarConnector, bundle: ContextBundle):
        self.calendar = calendar
        self.bundle   = bundle
        self.tz       = calendar.default_tz

    def execute(self, tool_name: str, tool_args: dict) -> str:
        try:
            dispatch = {
                "list_calendars":     self._list_calendars,
                "list_events":        self._list_events,
                "get_event":          self._get_event,
                "search_events":      self._search_events,
                "check_free_busy":    self._check_free_busy,
                "find_free_slots":    self._find_free_slots,
                "stage_create_event": self._stage_create_event,
                "stage_update_event": self._stage_update_event,
                "stage_delete_event": self._stage_delete_event,
                "stage_rsvp":         self._stage_rsvp,
            }
            fn = dispatch.get(tool_name)
            if not fn:
                return f"[ERROR] Unknown calendar tool: {tool_name}"
            return fn(**tool_args)
        except Exception as e:
            return f"[ERROR] Calendar tool {tool_name} failed: {e}"

    # ── Read ops ──────────────────────────────────────────────────────────────

    def _list_calendars(self) -> str:
        cals = self.calendar.list_calendars()
        if not cals:
            return "No calendars found."
        lines = [f"Found {len(cals)} calendar(s):\n"]
        for c in cals:
            primary = " [PRIMARY]" if c["primary"] else ""
            lines.append(f"  {c['summary']}{primary}\n    ID: {c['id']}\n    Access: {c['accessRole']}")
        self.bundle.record_step("list_calendars", "success", "", f"{len(cals)} calendars")
        return "\n".join(lines)

    def _list_events(
        self,
        calendar_id: str = "primary",
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        max_results: int = 20,
    ) -> str:
        events = self.calendar.list_events(
            calendar_id=calendar_id,
            time_min=time_min,
            time_max=time_max,
            max_results=max_results,
        )
        if not events:
            return "No events found in this period."
        lines = [f"Found {len(events)} event(s):\n"]
        for i, e in enumerate(events, 1):
            lines.append(
                f"{i}. [{e.event_id}] {e.title}\n"
                f"   {e.friendly_time(self.tz)}\n"
                + (f"   📍 {e.location}\n" if e.location else "")
                + (f"   👥 {', '.join(e.attendees[:4])}{'...' if len(e.attendees) > 4 else ''}\n" if e.attendees else "")
                + (f"   🎥 Meet: {e.meet_link}\n" if e.meet_link else "")
            )
        self.bundle.record_step("list_events", "success", f"cal={calendar_id}", f"{len(events)} events")
        return "\n".join(lines)

    def _get_event(self, event_id: str, calendar_id: str = "primary") -> str:
        event = self.calendar.get_event(event_id, calendar_id)
        self.bundle.record_step("get_event", "success", event_id, event.title)
        return event.to_summary(self.tz)

    def _search_events(
        self,
        query: str,
        calendar_id: str = "primary",
        max_results: int = 10,
        days_ahead: int = 90,
    ) -> str:
        events = self.calendar.search_events(
            query=query, calendar_id=calendar_id,
            max_results=max_results, days_ahead=days_ahead,
        )
        if not events:
            return f"No events found matching: '{query}'"
        lines = [f"Search '{query}' — {len(events)} result(s):\n"]
        for i, e in enumerate(events, 1):
            lines.append(f"{i}. [{e.event_id}] {e.title}  |  {e.friendly_time(self.tz)}")
        self.bundle.record_step("search_events", "success", query, f"{len(events)} results")
        return "\n".join(lines)

    def _check_free_busy(
        self,
        emails: list[str],
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        timezone: str = "UTC",
    ) -> str:
        result = self.calendar.get_free_busy(
            emails=emails, time_min=time_min, time_max=time_max, timezone=timezone
        )
        lines = ["Free/busy status:\n"]
        for email, slots in result.items():
            lines.append(f"  {email}:")
            if not slots:
                lines.append("    ✓ No busy periods in this window")
            else:
                for s in slots[:8]:
                    lines.append(f"    {s.friendly(timezone)}")
        self.bundle.record_step("check_free_busy", "success", str(emails), f"{sum(len(v) for v in result.values())} busy periods")
        return "\n".join(lines)

    def _find_free_slots(
        self,
        emails: list[str],
        duration_minutes: int = 60,
        days_ahead: int = 7,
        timezone: str = "UTC",
    ) -> str:
        slots = self.calendar.find_free_slots(
            emails=emails,
            duration_minutes=duration_minutes,
            days_ahead=days_ahead,
            timezone=timezone,
        )
        if not slots:
            return "No free slots found for all attendees in the given window."
        lines = [f"Found {len(slots)} available slot(s) for {duration_minutes}-min meeting:\n"]
        for i, s in enumerate(slots, 1):
            lines.append(f"  {i}. {s['day']}  {s['time']}")
            lines.append(f"     start={s['start']}  end={s['end']}")
        self.bundle.record_step("find_free_slots", "success", str(emails), f"{len(slots)} free slots")
        return "\n".join(lines)

    # ── Staging (write ops) ───────────────────────────────────────────────────

    def _stage_create_event(
        self,
        title: str,
        start: str,
        end: str,
        calendar_id: str = "primary",
        description: str = "",
        location: str = "",
        attendees: Optional[list] = None,
        timezone: str = "UTC",
        add_google_meet: bool = False,
        recurrence: Optional[list] = None,
        reasoning: str = "",
    ) -> str:
        payload = json.dumps({
            "action":          "create_event",
            "title":           title,
            "start":           start,
            "end":             end,
            "calendar_id":     calendar_id,
            "description":     description,
            "location":        location,
            "attendees":       attendees or [],
            "timezone":        timezone,
            "add_google_meet": add_google_meet,
            "recurrence":      recurrence or [],
        }, indent=2)
        self.bundle.stage_for_hil("create_event", payload, f"new:{title}")
        self.bundle.orchestrator_notes = reasoning
        self.bundle.record_step("stage_create_event", "hil_pending", title, "Staged for HIL review")
        return f"Event '{title}' staged for human approval.\nReasoning: {reasoning}\nTime: {start} → {end}"

    def _stage_update_event(
        self,
        event_id: str,
        updates: dict,
        calendar_id: str = "primary",
        reasoning: str = "",
    ) -> str:
        payload = json.dumps({
            "action":      "update_event",
            "event_id":    event_id,
            "calendar_id": calendar_id,
            "updates":     updates,
        }, indent=2)
        self.bundle.stage_for_hil("update_event", payload, event_id)
        self.bundle.orchestrator_notes = reasoning
        self.bundle.record_step("stage_update_event", "hil_pending", event_id, "Staged for HIL review")
        return f"Event update staged for human approval.\nEvent: {event_id}\nChanges: {updates}\nReasoning: {reasoning}"

    def _stage_delete_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        reasoning: str = "",
    ) -> str:
        payload = json.dumps({
            "action":      "delete_event",
            "event_id":    event_id,
            "calendar_id": calendar_id,
        }, indent=2)
        self.bundle.stage_for_hil("delete_event", payload, event_id)
        self.bundle.orchestrator_notes = reasoning
        self.bundle.record_step("stage_delete_event", "hil_pending", event_id, "Staged for HIL review")
        return f"Event deletion staged for human approval.\nEvent ID: {event_id}\nReasoning: {reasoning}"

    def _stage_rsvp(
        self,
        event_id: str,
        response: str,
        calendar_id: str = "primary",
        reasoning: str = "",
    ) -> str:
        payload = json.dumps({
            "action":      "rsvp",
            "event_id":    event_id,
            "calendar_id": calendar_id,
            "response":    response,
        }, indent=2)
        self.bundle.stage_for_hil("rsvp", payload, event_id)
        self.bundle.orchestrator_notes = reasoning
        self.bundle.record_step("stage_rsvp", "hil_pending", f"{event_id} → {response}", "Staged for HIL review")
        return f"RSVP '{response}' staged for human approval.\nEvent: {event_id}\nReasoning: {reasoning}"
