"""
core/notes_engine.py
─────────────────────
NotesEngine: saves agent reasoning snippets as structured notes.

HIL contract:
  propose_note() NEVER writes to disk.
  It returns a NoteSaveProposal shown to the human.
  execute_save_note() writes only after approval.

All snippets are saved. Anomaly-related ones get tag "anomaly_gap"
so they can be filtered/searched separately.

Notes are stored as JSONL (one JSON object per line) in:
  <PROJECT_ROOT>/notes/notes.jsonl

Each note:
  {
    "id":          "note_abc123",
    "timestamp":   "2026-03-27T10:00:00+00:00",
    "project":     "cybershield",
    "content":     "The model did not flag this SQL injection...",
    "attack_type": "sql_injection",       # if known
    "source":      "agent_reasoning",     # or "manual", "web"
    "tags":        ["anomaly_gap", "sql"],
    "is_anomaly_gap": true,
    "context":     "Task: analyse PCAP file...",  # surrounding task context
    "edited":      false
  }

Search:
  search_notes(query)         → full-text scan across content
  filter_by_tag("anomaly_gap")→ all anomaly gap notes
  filter_by_attack("xss")     → all notes for a specific attack type
"""

import json
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


NOTES_FILE      = "notes.jsonl"
ANOMALY_KEYWORDS = [
    "anomaly", "not flagged", "ignored", "missed", "no alert",
    "false negative", "baseline", "normal traffic", "not detected",
    "below threshold", "no anomaly", "model ignored", "silent",
    "undetected", "zero score", "low confidence",
]


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class Note:
    note_id:        str
    timestamp:      str
    project:        str
    content:        str
    attack_type:    str           # "sql_injection", "xss", "ddos" etc. or ""
    source:         str           # "agent_reasoning" | "manual" | "web"
    tags:           list[str]
    is_anomaly_gap: bool
    context:        str = ""      # surrounding task / session context
    edited:         bool = False

    def to_dict(self) -> dict:
        return {
            "id":             self.note_id,
            "timestamp":      self.timestamp,
            "project":        self.project,
            "content":        self.content,
            "attack_type":    self.attack_type,
            "source":         self.source,
            "tags":           self.tags,
            "is_anomaly_gap": self.is_anomaly_gap,
            "context":        self.context,
            "edited":         self.edited,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Note":
        return cls(
            note_id        = d.get("id", ""),
            timestamp      = d.get("timestamp", ""),
            project        = d.get("project", ""),
            content        = d.get("content", ""),
            attack_type    = d.get("attack_type", ""),
            source         = d.get("source", "agent_reasoning"),
            tags           = d.get("tags", []),
            is_anomaly_gap = d.get("is_anomaly_gap", False),
            context        = d.get("context", ""),
            edited         = d.get("edited", False),
        )

    def preview(self, max_chars: int = 120) -> str:
        return self.content[:max_chars] + ("…" if len(self.content) > max_chars else "")


@dataclass
class NoteSaveProposal:
    """
    Staged note save — shown to human before writing to notes.jsonl.
    """
    project_name:   str
    content:        str
    attack_type:    str
    source:         str
    tags:           list[str]
    is_anomaly_gap: bool
    context:        str
    detected_keywords: list[str]   # which anomaly keywords triggered the tag
    # HIL decision
    decision:       str = ""       # "approved" | "rejected" | "edited"
    edited_content: str = ""
    edited_tags:    list[str] = field(default_factory=list)
    edited_attack:  str = ""


# ── NotesEngine ───────────────────────────────────────────────────────────────

class NotesEngine:
    """
    Saves all agent reasoning snippets as structured notes.
    Anomaly-related notes are auto-tagged; human reviews all via HIL.
    """

    def __init__(self, project_name: str, notes_path: Path):
        self.project    = project_name
        self.notes_path = notes_path
        self.notes_path.mkdir(parents=True, exist_ok=True)
        self._notes_file = self.notes_path / NOTES_FILE

    # ── HIL Step 1: Propose ───────────────────────────────────────────────────

    def propose_note(
        self,
        content:     str,
        source:      str = "agent_reasoning",
        attack_type: str = "",
        context:     str = "",
        extra_tags:  Optional[list[str]] = None,
    ) -> NoteSaveProposal:
        """
        Analyse a snippet and build a NoteSaveProposal for HIL review.
        Auto-detects anomaly gap from keyword scan.
        Does NOT write to disk.
        """
        detected = self._detect_anomaly_keywords(content)
        is_anomaly = len(detected) > 0

        tags = list(extra_tags or [])
        if is_anomaly and "anomaly_gap" not in tags:
            tags.append("anomaly_gap")
        if attack_type and attack_type not in tags:
            tags.append(attack_type.lower().replace(" ", "_"))

        return NoteSaveProposal(
            project_name      = self.project,
            content           = content,
            attack_type       = attack_type,
            source            = source,
            tags              = tags,
            is_anomaly_gap    = is_anomaly,
            context           = context,
            detected_keywords = detected,
        )

    # ── HIL Step 2: Execute ───────────────────────────────────────────────────

    def execute_save_note(self, proposal: NoteSaveProposal) -> Note:
        """
        Write an approved note to notes.jsonl.
        Called ONLY after human approval in hil/project_approver.py.
        """
        content     = proposal.edited_content or proposal.content
        tags        = proposal.edited_tags    or proposal.tags
        attack_type = proposal.edited_attack  or proposal.attack_type
        edited      = bool(proposal.edited_content or proposal.edited_tags or proposal.edited_attack)

        note = Note(
            note_id        = self._make_id(content),
            timestamp      = datetime.now(timezone.utc).isoformat(),
            project        = self.project,
            content        = content,
            attack_type    = attack_type,
            source         = proposal.source,
            tags           = tags,
            is_anomaly_gap = proposal.is_anomaly_gap,
            context        = proposal.context,
            edited         = edited,
        )

        with open(self._notes_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(note.to_dict()) + "\n")

        return note

    # ── Read ops (no HIL) ─────────────────────────────────────────────────────

    def all_notes(self) -> list[Note]:
        """Load all notes from JSONL, newest first."""
        if not self._notes_file.exists():
            return []
        notes = []
        with open(self._notes_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        notes.append(Note.from_dict(json.loads(line)))
                    except json.JSONDecodeError:
                        continue
        return list(reversed(notes))

    def search_notes(self, query: str) -> list[Note]:
        """Full-text search across note content (case-insensitive)."""
        q = query.lower()
        return [n for n in self.all_notes() if q in n.content.lower() or q in n.context.lower()]

    def filter_by_tag(self, tag: str) -> list[Note]:
        return [n for n in self.all_notes() if tag in n.tags]

    def filter_by_attack(self, attack_type: str) -> list[Note]:
        at = attack_type.lower()
        return [n for n in self.all_notes() if at in n.attack_type.lower()]

    def anomaly_gap_notes(self) -> list[Note]:
        return self.filter_by_tag("anomaly_gap")

    def stats(self) -> dict:
        notes = self.all_notes()
        attack_counts: dict[str, int] = {}
        for n in notes:
            if n.attack_type:
                attack_counts[n.attack_type] = attack_counts.get(n.attack_type, 0) + 1
        return {
            "total":       len(notes),
            "anomaly_gap": sum(1 for n in notes if n.is_anomaly_gap),
            "by_attack":   attack_counts,
            "by_source":   {
                s: sum(1 for n in notes if n.source == s)
                for s in {"agent_reasoning", "manual", "web"}
            },
        }

    def delete_note(self, note_id: str) -> bool:
        """Remove a note by ID. Rewrites the JSONL file."""
        notes = self.all_notes()
        filtered = [n for n in notes if n.note_id != note_id]
        if len(filtered) == len(notes):
            return False
        with open(self._notes_file, "w", encoding="utf-8") as f:
            for note in reversed(filtered):   # restore original order
                f.write(json.dumps(note.to_dict()) + "\n")
        return True

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _detect_anomaly_keywords(text: str) -> list[str]:
        text_lower = text.lower()
        return [kw for kw in ANOMALY_KEYWORDS if kw in text_lower]

    @staticmethod
    def _make_id(content: str) -> str:
        h = hashlib.md5(content.encode()).hexdigest()[:10]
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"note_{ts}_{h}"
