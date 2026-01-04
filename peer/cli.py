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


@app.command()
def sessions() -> None:
    """List all recorded sessions."""
    db = get_db()
    all_sessions = db.get_all_sessions(limit=20)

    if not all_sessions:
        console.print("[dim]No sessions found[/dim]")
        return

    table = Table(title="Sessions")
    table.add_column("ID", style="cyan")
    table.add_column("Started")
    table.add_column("Ended")
    table.add_column("Mode")
    table.add_column("Status")

    for s in all_sessions:
        status = "[green]active[/green]" if s.end_time is None else "[dim]ended[/dim]"
        end = s.end_time[:19] if s.end_time else "-"
        table.add_row(
            s.id[:8] + "...",
            s.start_time[:19],
            end,
            str(s.mode),
            status,
        )

    console.print(table)


@app.command()
def stats() -> None:
    """Show database statistics."""
    db = get_db()
    stats = db.get_stats()

    table = Table(title="Database Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")

    table.add_row("Sessions", str(stats["sessions"]))
    table.add_row("Total Events", str(stats["events"]))
    table.add_row("Screenshots", str(stats["screenshots"]))

    console.print(table)

    if stats["event_breakdown"]:
        console.print("\n[bold]Event Breakdown:[/bold]")
        for event_type, count in sorted(stats["event_breakdown"].items(), key=lambda x: -x[1]):
            console.print(f"  {event_type}: {count}")


@app.command()
def delete(
    before: Optional[str] = typer.Option(
        None, "--before", help="Delete events before this date (YYYY-MM-DD)"
    ),
    app_name: Optional[str] = typer.Option(
        None, "--app", help="Delete events from this app"
    ),
    event_type: Optional[str] = typer.Option(
        None, "--type", help="Delete events of this type (click, text, window_change, etc.)"
    ),
    session_id: Optional[str] = typer.Option(
        None, "--session", help="Delete a specific session and all its data"
    ),
    url_pattern: Optional[str] = typer.Option(
        None, "--url", help="Delete window events matching this URL pattern"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip confirmation prompt"
    ),
) -> None:
    """Delete events from the database.

    Examples:
        peer delete --before 2024-01-01
        peer delete --app "1Password"
        peer delete --type click
        peer delete --session abc12345
        peer delete --url "privatesite.com"
    """
    db = get_db()

    if not any([before, app_name, event_type, session_id, url_pattern]):
        console.print("[red]Specify at least one filter: --before, --app, --type, --session, or --url[/red]")
        raise typer.Exit(1)

    # Build description of what will be deleted
    descriptions = []
    if before:
        descriptions.append(f"events before {before}")
    if app_name:
        descriptions.append(f"events from app '{app_name}'")
    if event_type:
        descriptions.append(f"events of type '{event_type}'")
    if session_id:
        descriptions.append(f"session {session_id[:8]}... and all its data")
    if url_pattern:
        descriptions.append(f"window events matching URL '{url_pattern}'")

    if not force:
        console.print(f"[yellow]This will delete: {', '.join(descriptions)}[/yellow]")
        if not typer.confirm("Are you sure?"):
            console.print("[dim]Cancelled[/dim]")
            raise typer.Exit(0)

    total_deleted = 0

    if before:
        count = db.delete_events_before(before)
        console.print(f"Deleted {count} events before {before}")
        total_deleted += count

    if app_name:
        count = db.delete_events_by_app(app_name)
        console.print(f"Deleted {count} events from '{app_name}'")
        total_deleted += count

    if event_type:
        count = db.delete_events_by_type(event_type)
        console.print(f"Deleted {count} events of type '{event_type}'")
        total_deleted += count

    if session_id:
        if db.delete_session(session_id):
            console.print(f"Deleted session {session_id[:8]}...")
        else:
            console.print(f"[yellow]Session {session_id[:8]}... not found[/yellow]")

    if url_pattern:
        count = db.delete_events_matching_url(url_pattern)
        console.print(f"Deleted {count} events matching URL '{url_pattern}'")
        total_deleted += count

    console.print(f"[green]Done. Total events deleted: {total_deleted}[/green]")


@app.command()
def redact(
    pattern: str = typer.Argument(..., help="Regex pattern to match text to redact"),
    replacement: str = typer.Option(
        "[REDACTED]", "--replacement", "-r", help="Replacement text"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Skip confirmation prompt"
    ),
) -> None:
    """Redact sensitive text from events.

    Searches text events for the given pattern and replaces matches.

    Examples:
        peer redact "api_key_[a-zA-Z0-9]+"
        peer redact "password123" --replacement "****"
        peer redact "secret-\\w+" -f
    """
    db = get_db()

    if not force:
        console.print(f"[yellow]This will redact text matching pattern: {pattern}[/yellow]")
        if not typer.confirm("Are you sure?"):
            console.print("[dim]Cancelled[/dim]")
            raise typer.Exit(0)

    count = db.redact_text_matching(pattern, replacement)
    console.print(f"[green]Redacted {count} text events[/green]")


@app.command()
def compact(
    pulsetime: float = typer.Option(
        30.0, "--pulsetime", "-p", help="Max seconds between events to merge"
    ),
) -> None:
    """Compact the database by merging similar events.

    Merges consecutive click events within the pulsetime window,
    reducing storage while preserving activity information.

    Inspired by ActivityWatch's heartbeat merging pattern.
    """
    db = get_db()

    console.print("[dim]Compacting database...[/dim]")
    before_stats = db.get_stats()

    results = db.compact(pulsetime)

    after_stats = db.get_stats()
    saved = before_stats["events"] - after_stats["events"]

    console.print(f"[green]Merged {results['events_merged']} click events[/green]")
    console.print(f"[dim]Events: {before_stats['events']} → {after_stats['events']} ({saved} saved)[/dim]")


@app.command()
def blocklist(
    add: Optional[str] = typer.Option(None, "--add", "-a", help="Add an app to blocklist"),
    remove: Optional[str] = typer.Option(None, "--remove", "-r", help="Remove an app from blocklist"),
) -> None:
    """Manage the app blocklist.

    Blocked apps are never logged, providing privacy for sensitive applications.

    Examples:
        peer blocklist                  # Show current blocklist
        peer blocklist --add "Slack"    # Block Slack
        peer blocklist --remove "Slack" # Unblock Slack
    """
    config = get_config()

    if add:
        config.block_app(add)
        console.print(f"[green]Added '{add}' to blocklist[/green]")
    elif remove:
        config.unblock_app(remove)
        console.print(f"[green]Removed '{remove}' from blocklist[/green]")

    # Show current blocklist
    console.print("\n[bold]Blocked Apps:[/bold]")
    for app in sorted(config.blocked_apps):
        console.print(f"  - {app}")

    if config.blocked_bundles - {
        "com.1password.1password", "com.apple.keychainaccess",
        "com.lastpass.LastPass", "com.bitwarden.desktop", "com.dashlane.Dashlane"
    }:
        console.print("\n[bold]Blocked Bundle IDs:[/bold]")
        for bundle in sorted(config.blocked_bundles):
            console.print(f"  - {bundle}")

    console.print(f"\n[dim]Blocklist saved to: {config.data_dir / 'blocklist.json'}[/dim]")


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
