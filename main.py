"""Entry point for Prépa Certif.

Run without arguments → launches the desktop GUI (default for everyone).
Run with `--cli` → falls back to the classic terminal experience.
"""
from __future__ import annotations

import sys


def _run_cli() -> None:
    import json
    from os import getenv

    from dotenv import load_dotenv
    from InquirerPy import inquirer
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel

    from agent import run_certification_agent
    from tools import fetch_certifications

    load_dotenv()
    console = Console()

    with console.status("[bold yellow]Loading certifications...[/bold yellow]", spinner="dots"):
        cert_choices = fetch_certifications()

    console.print()
    cert_name = inquirer.fuzzy(
        message="Select a certification:",
        choices=cert_choices,
        mandatory=True,
    ).execute()

    console.print()
    with console.status("[bold green]Working[/bold green]", spinner="dots") as status:
        text = run_certification_agent(
            cert_name,
            on_status=lambda m: status.update(f"[bold green]{m}[/bold green]"),
        )

    console.print()
    console.print(Panel(
        Markdown(text),
        title=f"[bold green]Results for {cert_name}[/bold green]",
        border_style="green",
        padding=(1, 2),
    ))


def main() -> None:
    if "--cli" in sys.argv[1:]:
        _run_cli()
        return
    from gui import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()
