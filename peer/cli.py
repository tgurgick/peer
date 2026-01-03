"""CLI interface for Peer."""

import json
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from peer import __version__
from peer.config import get_config
from peer.storage import Database

app = typer.Typer(
    name="peer",
    help="Activity logging assistant for LLM context and training data.",
    no_args_is_help=True,
)
console = Console()


def get_db() -> Database:
    """Get the database instance."""
    config = get_config()
    return Database(config.db_path)


@app.command()
def start(
    mode: int = typer.Option(
        None,
        "--mode",
        "-m",
        help="Operating mode (1-4). 1=logs only, 2=+screenshots, 3=+AI summaries, 4=+realtime AI",
    ),
    background: bool = typer.Option(
        False, "--background", "-b", help="Run in background with system tray"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Stream event logs in real time"
    ),
) -> None:
    """Start a new logging session."""
    config = get_config()
    db = get_db()

    # Check for existing active session
    active = db.get_active_session()
    if active:
        console.print(
            f"[yellow]Session already active since {active.start_time}[/yellow]"
        )
        console.print("Use 'peer stop' to end the current session first.")
        raise typer.Exit(1)

    effective_mode = mode if mode is not None else config.default_mode
    if effective_mode < 1 or effective_mode > 4:
        console.print("[red]Mode must be between 1 and 4[/red]")
        raise typer.Exit(1)

    session = db.create_session(mode=effective_mode)

    mode_descriptions = {
        1: "Logs only (silent)",
        2: "Logs + screenshots",
        3: "Logs + screenshots + periodic AI summaries",
        4: "Logs + screenshots + real-time AI feedback",
    }

    console.print(f"[green]Started session:[/green] {session.id[:8]}...")
    console.print(f"[dim]Mode {effective_mode}: {mode_descriptions[effective_mode]}[/dim]")
    console.print(f"[dim]Data directory: {config.data_dir}[/dim]")

    if background:
        console.print("[dim]Running in background with system tray...[/dim]")
        from peer.main import run_background

        run_background(session, config)
    else:
        if verbose:
            console.print("[dim]Verbose mode: streaming events in real time[/dim]")
        console.print("[dim]Press Ctrl+C to stop logging[/dim]")
        from peer.main import run_foreground

        def signal_handler(sig, frame):
            console.print("\n[yellow]Stopping...[/yellow]")
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        run_foreground(session, config, verbose=verbose)


@app.command()
def stop(
    summarize: bool = typer.Option(
        None,
        "--summarize/--no-summarize",
        help="Generate AI summary of session (prompts if not specified)",
    ),
) -> None:
    """Stop the current logging session."""
    db = get_db()
    session = db.get_active_session()

    if not session:
        console.print("[yellow]No active session to stop[/yellow]")
        raise typer.Exit(1)

    # Get session stats
    events = db.get_session_events(session.id)
    screenshots = db.get_session_screenshots(session.id)

    console.print(f"[green]Stopping session:[/green] {session.id[:8]}...")
    console.print(f"[dim]Duration: {_format_duration(session.start_time)}[/dim]")
    console.print(f"[dim]Events: {len(events)}, Screenshots: {len(screenshots)}[/dim]")

    summary = None
    if summarize is None and len(events) > 0:
        summarize = typer.confirm("Generate AI summary of this session?", default=False)

    if summarize:
        console.print("[dim]Generating summary...[/dim]")
        from peer.llm import get_provider

        try:
            provider = get_provider()
            summary = provider.summarize_session(events, screenshots)
            console.print(f"\n[bold]Session Summary:[/bold]\n{summary}\n")
        except Exception as e:
            console.print(f"[red]Failed to generate summary: {e}[/red]")

    db.end_session(session.id, summary=summary, total_cost=session.total_cost)
    console.print("[green]Session ended[/green]")


@app.command()
def status() -> None:
    """Show current session status."""
    db = get_db()
    config = get_config()
    session = db.get_active_session()

    if not session:
        console.print("[dim]No active session[/dim]")
        console.print(f"[dim]Data directory: {config.data_dir}[/dim]")
        return

    events = db.get_session_events(session.id)
    screenshots = db.get_session_screenshots(session.id)

    mode_descriptions = {
        1: "Logs only",
        2: "Logs + screenshots",
        3: "Logs + screenshots + AI summaries",
        4: "Logs + screenshots + real-time AI",
    }

    table = Table(title="Active Session")
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("Session ID", session.id[:8] + "...")
    table.add_row("Started", session.start_time)
    table.add_row("Duration", _format_duration(session.start_time))
    table.add_row("Mode", f"{session.mode} ({mode_descriptions[session.mode]})")
    table.add_row("Events", str(len(events)))
    table.add_row("Screenshots", str(len(screenshots)))
    table.add_row("Total Cost", f"${session.total_cost:.4f}")

    console.print(table)


@app.command()
def export(
    session_id: Optional[str] = typer.Argument(
        None, help="Session ID to export (defaults to current/last session)"
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
) -> None:
    """Export session data to JSON."""
    db = get_db()
    config = get_config()

    if session_id is None:
        session = db.get_active_session()
        if session:
            session_id = session.id
        else:
            console.print("[red]No session ID provided and no active session[/red]")
            raise typer.Exit(1)

    try:
        data = db.export_session_json(session_id)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = config.exports_dir / f"session_{session_id[:8]}_{timestamp}.json"

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(data, f, indent=2)

    console.print(f"[green]Exported to:[/green] {output}")
    console.print(f"[dim]Events: {len(data['events'])}, Screenshots: {len(data['screenshots'])}[/dim]")


@app.command()
def cost() -> None:
    """Show LLM costs for the current session."""
    db = get_db()
    session = db.get_active_session()

    if not session:
        console.print("[dim]No active session[/dim]")
        return

    console.print(f"[bold]Session Cost:[/bold] ${session.total_cost:.4f}")


@app.command()
def screenshot() -> None:
    """Take a manual screenshot and add to current session."""
    db = get_db()
    session = db.get_active_session()

    if not session:
        console.print("[red]No active session. Start one with 'peer start'[/red]")
        raise typer.Exit(1)

    from peer.capture import capture_screen
    from peer.config import get_config

    config = get_config()
    filepath = capture_screen(config.screenshots_dir, session.id)

    if filepath:
        from peer.storage import Screenshot

        screenshot = Screenshot(
            timestamp=datetime.now().isoformat(),
            filepath=str(filepath),
            session_id=session.id,
        )
        db.add_screenshot(screenshot)
        console.print(f"[green]Screenshot saved:[/green] {filepath}")
    else:
        console.print("[red]Failed to capture screenshot[/red]")


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"Peer v{__version__}")


@app.command()
def hotkey() -> None:
    """Run hotkey daemon to toggle monitoring with Shift+Backspace+Left."""
    from peer.hotkey import run_hotkey_daemon

    run_hotkey_daemon()


def _format_duration(start_time: str) -> str:
    """Format duration from start time to now."""
    start = datetime.fromisoformat(start_time)
    delta = datetime.now() - start
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


if __name__ == "__main__":
    app()
