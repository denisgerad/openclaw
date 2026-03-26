"""
tests/test_calendar_tools.py
──────────────────────────────
Unit tests for CalendarToolExecutor and calendar ContextBundle fields.
No API calls — uses a mock CalendarConnector.
Run: python -m pytest tests/ -v
"""

import sys, os, json
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from context.context_bundle import ContextBundle
from orchestrator.connectors.calendar import CalendarEvent, FreeBusySlot
from agent.tools.calendar_tools import CalendarToolExecutor, CALENDAR_TOOL_SCHEMAS


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_event(
    event_id="evt001", title="Team Standup",
    start="2025-02-10T09:00:00Z", end="2025-02-10T09:30:00Z",
    attendees=None, location="", meet_link="", description="",
    status="confirmed", all_day=False,
):
    return CalendarEvent(
        event_id=event_id, calendar_id="primary",
        title=title, start=start, end=end,
        attendees=attendees or ["alice@x.com", "bob@x.com"],
        location=location, meet_link=meet_link,
        description=description, organizer="alice@x.com",
        status=status, all_day=all_day,
    )


_SENTINEL = object()

def make_executor(events=_SENTINEL, calendars=None, free_slots=_SENTINEL, free_busy=None):
    """Build a CalendarToolExecutor with a mocked CalendarConnector."""
    mock_cal = MagicMock()
    mock_cal.default_tz = "UTC"
    mock_cal.list_events.return_value     = [make_event()] if events is _SENTINEL else events
    mock_cal.list_calendars.return_value  = calendars or [{"id": "primary", "summary": "My Calendar", "primary": True, "accessRole": "owner", "description": ""}]
    mock_cal.get_event.return_value       = make_event()
    mock_cal.search_events.return_value   = [make_event()] if events is _SENTINEL else events
    mock_cal.find_free_slots.return_value = [{"start": "2025-02-10T10:00:00Z", "end": "2025-02-10T11:00:00Z", "duration_minutes": 60, "day": "Mon Feb 10", "time": "10:00 AM – 11:00 AM UTC"}] if free_slots is _SENTINEL else free_slots
    mock_cal.get_free_busy.return_value   = free_busy or {"alice@x.com": []}

    bundle = ContextBundle(task_goal="Test calendar task")
    return CalendarToolExecutor(calendar=mock_cal, bundle=bundle), bundle, mock_cal


# ── Tool schema validation ────────────────────────────────────────────────────

def test_all_schemas_have_required_fields():
    for schema in CALENDAR_TOOL_SCHEMAS:
        assert "type" in schema
        assert schema["type"] == "function"
        fn = schema["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn


def test_schema_names_are_unique():
    names = [s["function"]["name"] for s in CALENDAR_TOOL_SCHEMAS]
    assert len(names) == len(set(names)), "Duplicate schema names"


def test_write_tools_have_reasoning_param():
    write_tools = ["stage_create_event", "stage_update_event", "stage_delete_event", "stage_rsvp"]
    for schema in CALENDAR_TOOL_SCHEMAS:
        name = schema["function"]["name"]
        if name in write_tools:
            params = schema["function"]["parameters"]["properties"]
            assert "reasoning" in params, f"{name} missing 'reasoning' param"


# ── Read tool tests ───────────────────────────────────────────────────────────

def test_list_calendars():
    executor, bundle, mock_cal = make_executor()
    result = executor.execute("list_calendars", {})
    assert "My Calendar" in result
    assert "primary" in result.lower()
    mock_cal.list_calendars.assert_called_once()


def test_list_events_returns_formatted_output():
    executor, bundle, mock_cal = make_executor()
    result = executor.execute("list_events", {"calendar_id": "primary", "max_results": 10})
    assert "Team Standup" in result
    assert "evt001" in result
    assert bundle.loop_count == 1


def test_list_events_empty():
    executor, bundle, mock_cal = make_executor(events=[])
    result = executor.execute("list_events", {})
    assert "No events" in result


def test_get_event():
    executor, bundle, mock_cal = make_executor()
    result = executor.execute("get_event", {"event_id": "evt001"})
    assert "Team Standup" in result
    assert "evt001" in result
    mock_cal.get_event.assert_called_once_with("evt001", "primary")


def test_search_events():
    executor, bundle, mock_cal = make_executor()
    result = executor.execute("search_events", {"query": "standup"})
    assert "standup" in result.lower() or "Team Standup" in result
    mock_cal.search_events.assert_called_once()


def test_check_free_busy():
    executor, bundle, mock_cal = make_executor(
        free_busy={"alice@x.com": [FreeBusySlot("2025-02-10T09:00:00Z", "2025-02-10T10:00:00Z", True)]}
    )
    result = executor.execute("check_free_busy", {"emails": ["alice@x.com"]})
    assert "alice@x.com" in result
    assert "BUSY" in result


def test_check_free_busy_no_conflicts():
    executor, bundle, mock_cal = make_executor(free_busy={"alice@x.com": []})
    result = executor.execute("check_free_busy", {"emails": ["alice@x.com"]})
    assert "alice@x.com" in result
    assert "No busy" in result or "FREE" in result or "✓" in result


def test_find_free_slots():
    executor, bundle, mock_cal = make_executor()
    result = executor.execute("find_free_slots", {"emails": ["alice@x.com", "bob@x.com"], "duration_minutes": 60})
    assert "10:00" in result or "Mon" in result or "slot" in result.lower()
    mock_cal.find_free_slots.assert_called_once()


def test_find_free_slots_none_available():
    executor, bundle, mock_cal = make_executor(free_slots=[])
    result = executor.execute("find_free_slots", {"emails": ["alice@x.com"]})
    assert "No free slots" in result


# ── Staging (write) tests ─────────────────────────────────────────────────────

def test_stage_create_event_sets_hil():
    executor, bundle, _ = make_executor()
    result = executor.execute("stage_create_event", {
        "title": "Sprint Planning",
        "start": "2025-02-10T14:00:00Z",
        "end":   "2025-02-10T15:00:00Z",
        "reasoning": "Requested by team lead",
    })
    assert bundle.draft_action == "create_event"
    assert bundle.draft_content is not None
    payload = json.loads(bundle.draft_content)
    assert payload["title"] == "Sprint Planning"
    assert "approved" not in result  # not executed yet


def test_stage_create_event_with_attendees():
    executor, bundle, _ = make_executor()
    executor.execute("stage_create_event", {
        "title":     "Design Review",
        "start":     "2025-02-11T10:00:00Z",
        "end":       "2025-02-11T11:00:00Z",
        "attendees": ["alice@x.com", "bob@x.com"],
        "add_google_meet": True,
        "reasoning": "Weekly design sync",
    })
    payload = json.loads(bundle.draft_content)
    assert payload["attendees"] == ["alice@x.com", "bob@x.com"]
    assert payload["add_google_meet"] is True


def test_stage_update_event_sets_hil():
    executor, bundle, _ = make_executor()
    executor.execute("stage_update_event", {
        "event_id": "evt001",
        "updates":  {"title": "Updated Standup", "location": "Zoom"},
        "reasoning": "Moving to Zoom",
    })
    assert bundle.draft_action == "update_event"
    payload = json.loads(bundle.draft_content)
    assert payload["event_id"] == "evt001"
    assert payload["updates"]["title"] == "Updated Standup"


def test_stage_delete_event_sets_hil():
    executor, bundle, _ = make_executor()
    executor.execute("stage_delete_event", {
        "event_id":  "evt001",
        "reasoning": "Event was cancelled",
    })
    assert bundle.draft_action == "delete_event"
    assert bundle.draft_target_id == "evt001"


def test_stage_rsvp_accepted():
    executor, bundle, _ = make_executor()
    executor.execute("stage_rsvp", {
        "event_id":  "evt001",
        "response":  "accepted",
        "reasoning": "I can attend",
    })
    assert bundle.draft_action == "rsvp"
    payload = json.loads(bundle.draft_content)
    assert payload["response"] == "accepted"


def test_stage_rsvp_declined():
    executor, bundle, _ = make_executor()
    executor.execute("stage_rsvp", {
        "event_id":  "evt001",
        "response":  "declined",
        "reasoning": "Conflict with another meeting",
    })
    payload = json.loads(bundle.draft_content)
    assert payload["response"] == "declined"


def test_stage_records_hil_pending_step():
    executor, bundle, _ = make_executor()
    executor.execute("stage_create_event", {
        "title": "Test", "start": "2025-02-10T09:00:00Z", "end": "2025-02-10T10:00:00Z",
        "reasoning": "test",
    })
    last_step = bundle.execution_history[-1]
    assert last_step.status == "hil_pending"
    assert last_step.action == "stage_create_event"


# ── ContextBundle calendar fields ─────────────────────────────────────────────

def test_context_bundle_calendar_fields_default():
    b = ContextBundle(task_goal="calendar test")
    assert b.active_event_id is None
    assert b.calendar_context == []


def test_context_bundle_active_event_id():
    b = ContextBundle(task_goal="test")
    b.active_event_id = "evt001"
    assert b.active_event_id == "evt001"


def test_context_bundle_calendar_context_stores_events():
    b = ContextBundle(task_goal="test")
    b.calendar_context = [{"event_id": "evt001", "title": "Standup"}]
    assert len(b.calendar_context) == 1
    assert b.calendar_context[0]["title"] == "Standup"


# ── Error handling ────────────────────────────────────────────────────────────

def test_unknown_tool_returns_error():
    executor, _, _ = make_executor()
    result = executor.execute("nonexistent_tool", {})
    assert "[ERROR]" in result


def test_connector_exception_returns_error():
    executor, _, mock_cal = make_executor()
    mock_cal.list_events.side_effect = RuntimeError("API quota exceeded")
    result = executor.execute("list_events", {})
    assert "[ERROR]" in result


# ── CalendarEvent helpers ─────────────────────────────────────────────────────

def test_calendar_event_friendly_time_same_day():
    e = make_event(start="2025-02-10T09:00:00Z", end="2025-02-10T09:30:00Z")
    time_str = e.friendly_time("UTC")
    assert "Feb 10" in time_str
    assert "09:00" in time_str or "9:00" in time_str


def test_calendar_event_all_day():
    e = make_event(start="2025-02-10", end="2025-02-11", all_day=True)
    time_str = e.friendly_time("UTC")
    assert "All day" in time_str


def test_calendar_event_to_summary():
    e = make_event(description="Daily sync", location="Zoom")
    summary = e.to_summary("UTC")
    assert "Team Standup" in summary
    assert "Daily sync" in summary
    assert "Zoom" in summary
    assert "alice@x.com" in summary


def test_free_busy_slot_friendly():
    slot = FreeBusySlot("2025-02-10T09:00:00Z", "2025-02-10T10:00:00Z", True)
    result = slot.friendly("UTC")
    assert "BUSY" in result
    assert "Feb 10" in result


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
