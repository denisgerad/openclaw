"""
tests/test_context_bundle.py
─────────────────────────────
Unit tests for ContextBundle — no API calls needed.
Run: python -m pytest tests/ -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from context.context_bundle import ContextBundle, MailMeta


def make_bundle(goal="Test task"):
    return ContextBundle(task_goal=goal)


def make_mail():
    return MailMeta(
        message_id="msg001",
        thread_id="thr001",
        subject="Test Subject",
        sender="alice@example.com",
        recipients=["me@example.com"],
        date="Mon, 1 Jan 2024",
        snippet="Hello there...",
    )


# ── ContextBundle basics ──────────────────────────────────────────────────────

def test_initial_state():
    b = make_bundle()
    assert b.loop_count == 0
    assert b.execution_history == []
    assert b.draft_action is None
    assert b.final_answer is None


def test_record_step_increments_loop_count():
    b = make_bundle()
    b.record_step("list_inbox", "success", "query", "10 results")
    assert b.loop_count == 1
    assert len(b.execution_history) == 1


def test_record_step_fields():
    b = make_bundle()
    b.record_step("search_mail", "success", "from:alice", "3 results", hil_approved=None)
    s = b.execution_history[0]
    assert s.step_number == 1
    assert s.action == "search_mail"
    assert s.status == "success"
    assert s.hil_approved is None


def test_multiple_steps_numbered_correctly():
    b = make_bundle()
    for i in range(3):
        b.record_step(f"action_{i}", "success", "in", "out")
    numbers = [s.step_number for s in b.execution_history]
    assert numbers == [1, 2, 3]


def test_history_summary_empty():
    b = make_bundle()
    summary = b.history_summary()
    assert "No steps executed" in summary


def test_history_summary_with_steps():
    b = make_bundle()
    b.record_step("list_inbox", "success", "inbox query", "5 messages")
    summary = b.history_summary()
    assert "list_inbox" in summary
    assert "success" in summary


# ── HIL staging ──────────────────────────────────────────────────────────────

def test_stage_for_hil():
    b = make_bundle()
    b.stage_for_hil("reply", "Dear Alice, thanks for reaching out.", "msg001")
    assert b.draft_action == "reply"
    assert b.draft_content == "Dear Alice, thanks for reaching out."
    assert b.draft_target_id == "msg001"
    assert b.hil_decision is None


def test_clear_hil_stage():
    b = make_bundle()
    b.stage_for_hil("delete", "Move to trash", "msg002")
    b.clear_hil_stage()
    assert b.draft_action is None
    assert b.draft_content is None
    assert b.draft_target_id is None


def test_stage_overwrites_previous():
    b = make_bundle()
    b.stage_for_hil("reply", "First draft", "msg001")
    b.stage_for_hil("delete", "Actually delete it", "msg002")
    assert b.draft_action == "delete"
    assert b.draft_target_id == "msg002"


# ── active_mail ───────────────────────────────────────────────────────────────

def test_active_mail_set():
    b = make_bundle()
    m = make_mail()
    b.active_mail = m
    assert b.active_mail.message_id == "msg001"
    assert b.active_mail.sender == "alice@example.com"


# ── Serialisation ─────────────────────────────────────────────────────────────

def test_to_dict_no_mail():
    b = make_bundle("Summarise inbox")
    d = b.to_dict()
    assert d["task_goal"] == "Summarise inbox"
    assert d["active_mail"] is None
    assert d["hil_pending"] is False


def test_to_dict_with_mail_and_hil():
    b = make_bundle()
    b.active_mail = make_mail()
    b.stage_for_hil("reply", "Hi!", "msg001")
    d = b.to_dict()
    assert d["hil_pending"] is True
    assert d["active_mail"]["subject"] == "Test Subject"


# ── HIL record in history ─────────────────────────────────────────────────────

def test_hil_rejected_step_recorded():
    b = make_bundle()
    b.record_step(
        action="reply",
        status="hil_rejected",
        input_summary="Reply to msg001",
        output_summary="Rejected: tone too casual",
        hil_approved=False,
    )
    s = b.execution_history[0]
    assert s.hil_approved is False
    assert s.status == "hil_rejected"
    assert "HIL:rejected" in b.history_summary()


def test_hil_approved_step_recorded():
    b = make_bundle()
    b.record_step("reply", "success", "Reply to msg001", "Sent ID: abc", hil_approved=True)
    assert "HIL:approved" in b.history_summary()


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
