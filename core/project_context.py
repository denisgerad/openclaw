"""
core/project_context.py
────────────────────────
ProjectContext: single entry point that bundles ProjectManager,
KnowledgeBase, and NotesEngine for one project.

Usage:
    ctx = ProjectContext("cybershield")
    proposal = ctx.pm.propose_ingest("/downloads/openclaw-stage5.tar.gz")
    kb_proposal = ctx.kb.propose_save(content, title, url)
    note_proposal = ctx.notes.propose_note(snippet, attack_type="sql_injection")

The HIL approver (hil/project_approver.py) receives these proposals,
presents them to the human, then calls:
    ctx.pm.execute_ingest(proposal)
    ctx.kb.execute_save(kb_proposal)
    ctx.notes.execute_save_note(note_proposal)
"""

from pathlib import Path
from core.project_manager import ProjectManager
from core.knowledge_base import KnowledgeBase
from core.notes_engine import NotesEngine


class ProjectContext:
    """
    Aggregates all three project subsystems.
    Constructed once per project per session and reused.
    """

    def __init__(self, project_name: str):
        self.name  = project_name
        self.pm    = ProjectManager(project_name)
        self.kb    = KnowledgeBase(project_name, self.pm.root / "kb")
        self.notes = NotesEngine(project_name, self.pm.root / "notes")

    def summary(self) -> dict:
        m = self.pm.read_manifest()
        return {
            "name":           self.name,
            "root":           str(self.pm.root),
            "description":    m.get("description", ""),
            "active_version": m.get("active_version"),
            "version_count":  len(m.get("versions", [])),
            "kb_docs":        self.kb.count(),
            "notes":          self.notes.stats(),
        }

    @staticmethod
    def list_all() -> list[str]:
        return ProjectManager.list_all_projects()
