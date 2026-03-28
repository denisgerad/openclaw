"""
hil/project_approver.py
────────────────────────
HIL approval layer for the three project automation flows.

Handles three proposal types, each with approve / reject / edit:
  1. IngestProposal    — file versioning (ProjectManager)
  2. KBSaveProposal    — knowledge base save (KnowledgeBase)
  3. NoteSaveProposal  — notes save (NotesEngine)

For Streamlit, use the *_streamlit variants which take decisions
from st.session_state rather than blocking for input().
"""

import json
from colorama import Fore, Style, init as colorama_init
from core.project_manager import ProjectManager, IngestProposal, ProjectVersion
from core.knowledge_base import KnowledgeBase, KBSaveProposal
from core.notes_engine import NotesEngine, NoteSaveProposal, Note

colorama_init(autoreset=True)


def _header(text: str, color: str = Fore.CYAN):
    print(f"\n{color}{'─' * 62}")
    print(f"  {text}")
    print(f"{'─' * 62}{Style.RESET_ALL}")


def _divider():
    print(f"{Fore.WHITE}{'·' * 62}{Style.RESET_ALL}")


def _prompt(label: str = "openclaw › ") -> str:
    return input(f"{Fore.CYAN}  {label}{Style.RESET_ALL}").strip()


# ══════════════════════════════════════════════════════════════
# 1. FILE INGEST HIL
# ══════════════════════════════════════════════════════════════

def review_ingest(proposal: IngestProposal) -> str:
    """
    Present file ingest proposal to human.
    Returns "approved" | "rejected" | "edited".
    """
    _header(f"📦  HIL REVIEW — FILE INGEST  →  {proposal.version_name.upper()}", Fore.BLUE)
    print(f"  {Fore.GREEN}Project    : {Style.RESET_ALL}{proposal.project_name}")
    print(f"  {Fore.GREEN}File       : {Style.RESET_ALL}{proposal.source_path.name}")
    print(f"  {Fore.GREEN}Type       : {Style.RESET_ALL}{proposal.archive_type}")
    print(f"  {Fore.GREEN}Size       : {Style.RESET_ALL}{proposal.size_kb} KB")
    print(f"  {Fore.GREEN}SHA-256    : {Style.RESET_ALL}{proposal.sha256}")
    print(f"  {Fore.GREEN}Version    : {Style.RESET_ALL}{proposal.version_name}  →  {proposal.dest_path}")
    _divider()
    print(f"  {Fore.CYAN}Contents ({len(proposal.file_list)} shown):{Style.RESET_ALL}")
    for f in proposal.file_list[:15]:
        print(f"    {Fore.WHITE}{f}{Style.RESET_ALL}")
    if len(proposal.file_list) > 15:
        print(f"    {Fore.WHITE}... and more{Style.RESET_ALL}")

    _header("Decision", Fore.CYAN)
    print(f"  {Fore.GREEN}[y]{Style.RESET_ALL} Approve — extract to {proposal.version_name}/")
    print(f"  {Fore.RED}[n]{Style.RESET_ALL} Reject")
    print(f"  {Fore.YELLOW}[e]{Style.RESET_ALL} Edit version notes before approving")
    print()

    while True:
        choice = _prompt().lower()
        if choice == "y":
            proposal.decision = "approved"
            print(f"\n{Fore.GREEN}  ✓ Approved. Extracting...{Style.RESET_ALL}\n")
            return "approved"
        elif choice == "n":
            proposal.decision = "rejected"
            print(f"\n{Fore.RED}  ✗ Rejected.{Style.RESET_ALL}\n")
            return "rejected"
        elif choice == "e":
            print(f"  Enter version notes (press Enter to finish):")
            proposal.notes    = _prompt("notes › ")
            proposal.decision = "edited"
            print(f"\n{Fore.YELLOW}  ✎ Notes saved. Extracting...{Style.RESET_ALL}\n")
            return "edited"
        else:
            print(f"  {Fore.RED}Enter y, n, or e{Style.RESET_ALL}")


def execute_ingest(
    proposal: IngestProposal,
    pm: ProjectManager,
) -> ProjectVersion:
    """Execute after HIL approval."""
    version = pm.execute_ingest(proposal)
    print(f"{Fore.GREEN}  ✓ Extracted {version.file_count} files → {version.path}{Style.RESET_ALL}")
    return version


# ══════════════════════════════════════════════════════════════
# 2. KB SAVE HIL
# ══════════════════════════════════════════════════════════════

def review_kb_save(proposal: KBSaveProposal) -> str:
    """
    Present KB save proposal to human.
    Returns "approved" | "rejected" | "edited".
    """
    dup_warn = f"  {Fore.RED}⚠ Near-duplicate detected!{Style.RESET_ALL}\n" if proposal.is_duplicate else ""
    _header(f"📚  HIL REVIEW — KNOWLEDGE BASE SAVE", Fore.CYAN)
    if dup_warn:
        print(dup_warn)
    print(f"  {Fore.GREEN}Project    : {Style.RESET_ALL}{proposal.project_name}")
    print(f"  {Fore.GREEN}Title      : {Style.RESET_ALL}{proposal.title}")
    print(f"  {Fore.GREEN}Source     : {Style.RESET_ALL}{proposal.source}")
    print(f"  {Fore.GREEN}Tags       : {Style.RESET_ALL}{', '.join(proposal.tags) or '(none)'}")
    print(f"  {Fore.GREEN}Chunks     : {Style.RESET_ALL}{len(proposal.chunks)}")
    _divider()
    print(f"  {Fore.CYAN}Content preview:{Style.RESET_ALL}")
    print(f"  {Fore.WHITE}{proposal.content[:400]}{'...' if len(proposal.content) > 400 else ''}{Style.RESET_ALL}")

    if proposal.near_duplicates:
        _divider()
        print(f"  {Fore.YELLOW}Similar existing documents:{Style.RESET_ALL}")
        for r in proposal.near_duplicates[:3]:
            print(f"    {r.similarity_pct}% match — {r.title}  [{r.source[:60]}]")

    _header("Decision", Fore.CYAN)
    print(f"  {Fore.GREEN}[y]{Style.RESET_ALL} Approve — save to ChromaDB")
    print(f"  {Fore.RED}[n]{Style.RESET_ALL} Reject")
    print(f"  {Fore.YELLOW}[e]{Style.RESET_ALL} Edit tags/content before saving")
    print()

    while True:
        choice = _prompt().lower()
        if choice == "y":
            proposal.decision = "approved"
            print(f"\n{Fore.GREEN}  ✓ Approved. Saving...{Style.RESET_ALL}\n")
            return "approved"
        elif choice == "n":
            proposal.decision = "rejected"
            print(f"\n{Fore.RED}  ✗ Rejected.{Style.RESET_ALL}\n")
            return "rejected"
        elif choice == "e":
            print(f"  New tags (comma-separated, or Enter to keep '{', '.join(proposal.tags)}'):")
            tag_input = _prompt("tags › ")
            if tag_input:
                proposal.edited_tags = [t.strip() for t in tag_input.split(",") if t.strip()]
            print(f"  Edit content? Paste replacement then type END on new line, or Enter to keep:")
            first = _prompt("content › ")
            if first:
                lines = [first]
                while True:
                    line = input("  ")
                    if line.strip() == "END":
                        break
                    lines.append(line)
                proposal.edited_content = "\n".join(lines)
            proposal.decision = "edited"
            print(f"\n{Fore.YELLOW}  ✎ Edits saved. Saving to KB...{Style.RESET_ALL}\n")
            return "edited"
        else:
            print(f"  {Fore.RED}Enter y, n, or e{Style.RESET_ALL}")


def execute_kb_save(proposal: KBSaveProposal, kb: KnowledgeBase) -> int:
    """Execute after HIL approval."""
    chunks = kb.execute_save(proposal)
    print(f"{Fore.GREEN}  ✓ Saved {chunks} chunk(s) to ChromaDB{Style.RESET_ALL}")
    return chunks


# ══════════════════════════════════════════════════════════════
# 3. NOTE SAVE HIL
# ══════════════════════════════════════════════════════════════

def review_note_save(proposal: NoteSaveProposal) -> str:
    """
    Present note save proposal to human.
    Returns "approved" | "rejected" | "edited".
    """
    anomaly_color = Fore.YELLOW if proposal.is_anomaly_gap else Fore.CYAN
    anomaly_label = "🔴 ANOMALY GAP" if proposal.is_anomaly_gap else "📝 REASONING NOTE"
    _header(f"📝  HIL REVIEW — NOTE SAVE  [{anomaly_label}]", anomaly_color)

    print(f"  {Fore.GREEN}Project      : {Style.RESET_ALL}{proposal.project_name}")
    print(f"  {Fore.GREEN}Source       : {Style.RESET_ALL}{proposal.source}")
    print(f"  {Fore.GREEN}Attack type  : {Style.RESET_ALL}{proposal.attack_type or '(not specified)'}")
    print(f"  {Fore.GREEN}Tags         : {Style.RESET_ALL}{', '.join(proposal.tags) or '(none)'}")
    if proposal.is_anomaly_gap and proposal.detected_keywords:
        print(f"  {Fore.YELLOW}Triggered by : {Style.RESET_ALL}{', '.join(proposal.detected_keywords)}")
    _divider()
    print(f"  {Fore.CYAN}Snippet:{Style.RESET_ALL}")
    print(f"  {Fore.WHITE}{proposal.content[:500]}{'...' if len(proposal.content) > 500 else ''}{Style.RESET_ALL}")
    if proposal.context:
        _divider()
        print(f"  {Fore.CYAN}Task context:{Style.RESET_ALL}")
        print(f"  {Fore.WHITE}{proposal.context[:200]}{Style.RESET_ALL}")

    _header("Decision", Fore.CYAN)
    print(f"  {Fore.GREEN}[y]{Style.RESET_ALL} Approve — save note")
    print(f"  {Fore.RED}[n]{Style.RESET_ALL} Reject")
    print(f"  {Fore.YELLOW}[e]{Style.RESET_ALL} Edit tags / attack type / content before saving")
    print()

    while True:
        choice = _prompt().lower()
        if choice == "y":
            proposal.decision = "approved"
            print(f"\n{Fore.GREEN}  ✓ Approved. Saving note...{Style.RESET_ALL}\n")
            return "approved"
        elif choice == "n":
            proposal.decision = "rejected"
            print(f"\n{Fore.RED}  ✗ Rejected.{Style.RESET_ALL}\n")
            return "rejected"
        elif choice == "e":
            print(f"  Attack type (Enter to keep '{proposal.attack_type}'):")
            at = _prompt("attack › ")
            if at:
                proposal.edited_attack = at
            print(f"  Tags (comma-separated, Enter to keep):")
            ti = _prompt("tags › ")
            if ti:
                proposal.edited_tags = [t.strip() for t in ti.split(",") if t.strip()]
            print(f"  Edit content? Paste then type END, or Enter to keep:")
            first = _prompt("content › ")
            if first:
                lines = [first]
                while True:
                    line = input("  ")
                    if line.strip() == "END":
                        break
                    lines.append(line)
                proposal.edited_content = "\n".join(lines)
            proposal.decision = "edited"
            print(f"\n{Fore.YELLOW}  ✎ Edits saved. Saving note...{Style.RESET_ALL}\n")
            return "edited"
        else:
            print(f"  {Fore.RED}Enter y, n, or e{Style.RESET_ALL}")


def execute_note_save(proposal: NoteSaveProposal, notes: NotesEngine) -> Note:
    """Execute after HIL approval."""
    note = notes.execute_save_note(proposal)
    tag_str = ", ".join(note.tags)
    gap_flag = "  🔴 anomaly_gap" if note.is_anomaly_gap else ""
    print(f"{Fore.GREEN}  ✓ Note saved  [{note.note_id}]  tags: {tag_str}{gap_flag}{Style.RESET_ALL}")
    return note
