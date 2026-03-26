"""
main.py
────────
OpenClaw — entry point.

All orchestration logic lives in orchestrator/router.py.
main.py handles only: connector init, user input, session display.
"""

import os
from dotenv import load_dotenv
from colorama import Fore, Style, init as colorama_init
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()
colorama_init(autoreset=True)
console = Console()

from context.context_bundle import ContextBundle
from orchestrator.connectors.gmail import GmailConnector
from orchestrator.connectors.web_search import WebSearchConnector
from orchestrator.router import Router


def print_session_summary(bundle: ContextBundle) -> None:
    table = Table(title="Session Summary", border_style="cyan", show_header=True)
    table.add_column("Step",   style="dim", width=6)
    table.add_column("Action", width=20)
    table.add_column("Status", width=14)
    table.add_column("HIL",    width=12)
    table.add_column("Output", style="dim")

    for s in bundle.execution_history:
        color = "green" if s.status == "success" else (
            "yellow" if "pending" in s.status else "red")
        hil = ("[green]approved[/green]" if s.hil_approved is True else
               "[red]rejected[/red]"    if s.hil_approved is False else "—")
        table.add_row(
            str(s.step_number), s.action,
            f"[{color}]{s.status}[/{color}]",
            hil, s.output_summary[:60],
        )

    console.print(table)
    console.print(f"\n[bold]Total loops:[/bold] {bundle.loop_count}")
    if bundle.final_answer:
        console.print(Panel(
            bundle.final_answer[:500],
            title="[bold green]Final Answer[/bold green]",
            border_style="green",
        ))


def main():
    console.print(Panel.fit(
        "[bold cyan]OpenClaw[/bold cyan] — Agentic Email Automation\n"
        "[dim]Mistral · Gmail · Tavily · HIL[/dim]",
        border_style="cyan",
    ))

    # ── Init connectors ───────────────────────────────────────────────────────
    console.print("\n[dim]Connecting to Gmail (OAuth2)...[/dim]")
    try:
        gmail = GmailConnector()
        console.print("[green]  ✓ Gmail authenticated[/green]")
    except FileNotFoundError as e:
        console.print(f"[red]  ✗ {e}[/red]")
        console.print(
            "\n[yellow]Setup: Download credentials.json from Google Cloud Console\n"
            "  APIs & Services → Credentials → OAuth 2.0 Client IDs → Download JSON\n"
            "  Save to: config/credentials.json[/yellow]"
        )
        return

    console.print("[dim]Connecting to Tavily...[/dim]")
    try:
        web_search = WebSearchConnector()
        console.print("[green]  ✓ Tavily ready[/green]")
    except ValueError as e:
        console.print(f"[red]  ✗ {e}[/red]")
        return

    router = Router(gmail=gmail, web_search=web_search)
    console.print("[green]  ✓ Orchestrator ready[/green]\n")

    # ── Task input ────────────────────────────────────────────────────────────
    console.print("[bold]What would you like OpenClaw to do?[/bold]")
    console.print("[dim]Examples:[/dim]")
    for ex in [
        "Summarise my 5 most recent unread emails",
        "Find emails from alice@example.com and draft a polite follow-up",
        "Search for invoice emails from last month and list them",
        "Find the email about Project Phoenix and delete it",
        "Find unread Q3 report emails, search web for context, draft a reply",
    ]:
        console.print(f"  [dim]•[/dim] {ex}")
    console.print()

    task = input(f"{Fore.CYAN}openclaw › {Style.RESET_ALL}").strip()
    if not task:
        console.print("[red]No task given. Exiting.[/red]")
        return

    # ── Run ───────────────────────────────────────────────────────────────────
    bundle = ContextBundle(task_goal=task)
    router.run(bundle)

    # ── Summary ───────────────────────────────────────────────────────────────
    console.print()
    print_session_summary(bundle)


if __name__ == "__main__":
    main()
