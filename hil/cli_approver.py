"""
hil/cli_approver.py
────────────────────
Human-in-the-Loop approval layer — Terminal CLI edition.

Flow:
  1. Orchestrator stages a destructive/outbound action into ContextBundle
  2. This module intercepts it, prints a rich preview, and waits for input
  3. Human types: y (approve) | n (reject) | e (edit) | ? (explain)
  4. Decision + optional edit is written back to ContextBundle
  5. Caller (main.py) executes or skips based on hil_decision

Color coding:
  GREEN   → safe read-only info
  YELLOW  → staged action preview
  RED     → delete / irreversible
  CYAN    → prompts / guidance
"""

import os
from typing import Optional
from colorama import Fore, Style, init as colorama_init

from context.context_bundle import ContextBundle
from orchestrator.connectors.gmail import GmailConnector

colorama_init(autoreset=True)

# Actions that require HIL — sourced from .env with fallback
_HIL_ACTIONS = set(
    os.getenv("HIL_REQUIRED_ACTIONS", "reply,delete,send,trash").split(",")
)


def _header(text: str, color: str = Fore.CYAN) -> None:
    width = 60
    print(f"\n{color}{'─' * width}")
    print(f"  {text}")
    print(f"{'─' * width}{Style.RESET_ALL}")


def _divider() -> None:
    print(f"{Fore.WHITE}{'·' * 60}{Style.RESET_ALL}")


def requires_hil(action: str) -> bool:
    """Return True if this action must be approved before execution."""
    return action.lower() in _HIL_ACTIONS


def review_and_decide(bundle: ContextBundle) -> str:
    """
    Present the staged action to the human and record their decision.

    Modifies bundle.hil_decision in place.
    Returns the decision: "approved" | "rejected" | "edited".
    """
    action = bundle.draft_action
    content = bundle.draft_content
    target_id = bundle.draft_target_id

    if not action:
        return "no_action"

    is_delete = action in ("delete", "trash")
    action_color = Fore.RED if is_delete else Fore.YELLOW

    _header(f"⚠  HIL REVIEW  —  Action: {action.upper()}", action_color)

    # Show context of what mail is being acted on
    if bundle.active_mail:
        m = bundle.active_mail
        print(f"{Fore.GREEN}  Mail subject : {Style.RESET_ALL}{m.subject}")
        print(f"{Fore.GREEN}  From         : {Style.RESET_ALL}{m.sender}")
        print(f"{Fore.GREEN}  Date         : {Style.RESET_ALL}{m.date}")
        print(f"{Fore.GREEN}  Message ID   : {Style.RESET_ALL}{target_id}")

    _divider()

    if is_delete:
        print(f"{Fore.RED}  ⚠  This will move the message to Trash.")
        print(f"  It can be recovered from Trash within 30 days.{Style.RESET_ALL}")
    else:
        print(f"{Fore.YELLOW}  Draft content to be sent:{Style.RESET_ALL}\n")
        print(f"{Fore.WHITE}{_indent(content)}{Style.RESET_ALL}")

    _divider()

    # Show execution history context
    if bundle.execution_history:
        print(f"{Fore.CYAN}  Steps completed so far:{Style.RESET_ALL}")
        print(bundle.history_summary())

    _header("Your decision", Fore.CYAN)
    print(f"  {Fore.GREEN}[y]{Style.RESET_ALL} Approve and execute")
    print(f"  {Fore.RED}[n]{Style.RESET_ALL} Reject — skip this action")
    if not is_delete:
        print(f"  {Fore.YELLOW}[e]{Style.RESET_ALL} Edit the draft before sending")
    print(f"  {Fore.CYAN}[?]{Style.RESET_ALL} Show orchestrator reasoning")
    print()

    while True:
        choice = input(f"{Fore.CYAN}  openclaw › {Style.RESET_ALL}").strip().lower()

        if choice == "y":
            bundle.hil_decision = "approved"
            print(f"\n{Fore.GREEN}  ✓ Approved. Executing...{Style.RESET_ALL}\n")
            return "approved"

        elif choice == "n":
            bundle.hil_decision = "rejected"
            reason = input(
                f"{Fore.RED}  Optional — reason for rejection (or Enter to skip): "
                f"{Style.RESET_ALL}"
            ).strip()
            bundle.record_step(
                action=action,
                status="hil_rejected",
                input_summary=f"Staged: {action} on {target_id}",
                output_summary=f"Rejected by human. Reason: {reason or 'none given'}",
                hil_approved=False,
            )
            bundle.clear_hil_stage()
            print(f"\n{Fore.RED}  ✗ Rejected. Action skipped.{Style.RESET_ALL}\n")
            return "rejected"

        elif choice == "e" and not is_delete:
            print(
                f"\n{Fore.YELLOW}  Edit mode — paste your revised text below.\n"
                f"  Type END on a new line when done:{Style.RESET_ALL}\n"
            )
            lines = []
            while True:
                line = input()
                if line.strip() == "END":
                    break
                lines.append(line)
            bundle.draft_content = "\n".join(lines)
            bundle.hil_decision = "edited"
            print(f"\n{Fore.YELLOW}  ✎ Draft updated. Executing with edited content...{Style.RESET_ALL}\n")
            return "edited"

        elif choice == "?":
            print(f"\n{Fore.CYAN}  Orchestrator notes:{Style.RESET_ALL}")
            print(f"  {bundle.orchestrator_notes or '(no notes recorded)'}\n")
            print(f"  Goal: {bundle.task_goal}\n")

        else:
            print(f"{Fore.RED}  Unknown input. Enter y, n, e, or ?{Style.RESET_ALL}")


def execute_approved_action(
    bundle: ContextBundle,
    gmail: Optional[GmailConnector] = None,
) -> bool:
    """
    Execute whatever action was staged in the bundle, post-approval.
    Called by main.py only when bundle.hil_decision in ("approved", "edited").

    Returns True on success, False on error.
    """
    action = bundle.draft_action
    content = bundle.draft_content
    target_id = bundle.draft_target_id

    try:
        if action == "send" and bundle.draft_to and gmail:
            # New outbound email (not a reply)
            sent_id = gmail.send_new(
                to_address=bundle.draft_to,
                subject=bundle.draft_subject or "(no subject)",
                body=content,
            )
            bundle.record_step(
                action="send",
                status="success",
                input_summary=f"New email to {bundle.draft_to} — {bundle.draft_subject}",
                output_summary=f"Sent. Message ID: {sent_id}",
                hil_approved=True,
            )
            print(f"{Fore.GREEN}  ✓ Email sent to {bundle.draft_to}. Message ID: {sent_id}{Style.RESET_ALL}")

        elif action == "reply" and gmail:
            m = bundle.active_mail
            if m is None and target_id:
                data = gmail.get_message(target_id)
                m = data["meta"]
                bundle.active_mail = m
            sent_id = gmail.reply(
                original_message_id=m.message_id,
                thread_id=m.thread_id,
                reply_body=content,
                reply_to_address=m.sender,
                original_subject=m.subject,
            )
            bundle.record_step(
                action="reply",
                status="success",
                input_summary=f"Reply to {m.sender} re: {m.subject}",
                output_summary=f"Sent. Message ID: {sent_id}",
                hil_approved=True,
            )
            print(f"{Fore.GREEN}  ✓ Reply sent. Message ID: {sent_id}{Style.RESET_ALL}")

        elif action in ("delete", "trash") and gmail:
            gmail.trash(target_id)
            bundle.record_step(
                action="trash",
                status="success",
                input_summary=f"Trash message: {target_id}",
                output_summary="Message moved to Trash.",
                hil_approved=True,
            )
            print(f"{Fore.GREEN}  ✓ Message moved to Trash.{Style.RESET_ALL}")

        else:
            print(f"{Fore.RED}  ✗ Unknown action or missing connector: {action}{Style.RESET_ALL}")
            return False

        bundle.clear_hil_stage()
        return True

    except Exception as e:
        bundle.record_step(
            action=action,
            status="failed",
            input_summary=str(target_id),
            output_summary=str(e),
            hil_approved=True,
            error=str(e),
        )
        print(f"{Fore.RED}  ✗ Execution failed: {e}{Style.RESET_ALL}")
        return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _indent(text: str, spaces: int = 4) -> str:
    if not text:
        return ""
    prefix = " " * spaces
    return "\n".join(prefix + line for line in text.splitlines())
