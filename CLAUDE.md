# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Peer is an experimental activity logging assistant designed to monitor and relay on-screen activity. It captures user actions on local systems and browser for use as LLM context or training data for a digital twin.

## Development Commands

```bash
# Install dependencies
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"

# Run the CLI
peer --help
peer start              # Start logging (mode 1)
peer start --mode 2     # Start with screenshots
peer start --background # Run with system tray
peer stop               # Stop session
peer status             # Show current session
peer export             # Export session to JSON
peer screenshot         # Manual screenshot capture

# Run tests
pytest

# Lint
ruff check peer/
ruff format peer/
```

## Architecture

```
peer/
├── cli.py           # Typer CLI entry point
├── main.py          # Event coordinator, runs the logging loop
├── config.py        # Configuration from env vars
├── modes.py         # Operating mode definitions (1-4)
├── tray.py          # macOS system tray (pystray)
├── logger/          # Activity capture
│   ├── keyboard.py  # Keystroke capture (pynput)
│   ├── mouse.py     # Click tracking (pynput)
│   └── window.py    # Active window tracking (pyobjc)
├── capture/
│   └── screen.py    # Screenshot capture (Quartz)
├── storage/
│   └── database.py  # SQLite storage with JSON export
├── llm/
│   ├── base.py      # Abstract LLM provider
│   ├── openai_provider.py
│   ├── anthropic_provider.py
│   └── cost.py      # Usage cost tracking
└── privacy/
    └── filter.py    # Sensitive data redaction
```

## Key Patterns

- **Event-driven**: Loggers emit events to callbacks, `EventCoordinator` in `main.py` routes them to storage
- **Provider abstraction**: LLM providers implement `LLMProvider` base class for easy extension
- **Privacy-first**: `privacy/filter.py` masks keystrokes in password contexts and redacts secrets before LLM calls

## Data Storage

- Database: `~/.peer/peer.db` (SQLite)
- Screenshots: `~/.peer/screenshots/YYYY-MM-DD/session_id/`
- Exports: `~/.peer/exports/`

## Configuration

Copy `.env.example` to `.env` and configure:
- `PEER_DATA_DIR` - Storage location
- `PEER_DEFAULT_MODE` - Default operating mode (1-4)
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` - For AI features

## Security Requirements

- Never store passwords, .env variables, or other sensitive data
- Redact sensitive information before sending to LLMs
- All data stored locally for privacy
