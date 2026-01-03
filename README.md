# Peer

Activity logging assistant for LLM context and training data.

Peer monitors on-screen activity and stores it locally for use as context for AI assistants or training data for personal models.

> **Warning**: Peer is highly permissive by design. It captures nearly all user activity including keystrokes, mouse clicks, active applications, URLs visited, and optionally screenshots. This data is stored locally and never transmitted without explicit user action, but you should understand what is being logged before running it. Do not run Peer on shared or work computers without appropriate authorization.

## What Gets Tracked

| Data Type | What's Captured | Example |
|-----------|-----------------|---------|
| **Text Input** | All keystrokes aggregated into text chunks | `"I want to search for python tutorials"` |
| **Commands** | Keyboard shortcuts with modifiers | `Ctrl+C`, `Cmd+S`, `Alt+Tab` |
| **Mouse Clicks** | Click position and button | `left click at (1024, 768)` |
| **Active Window** | App name, window title, bundle ID | `Google Chrome - GitHub` |
| **Browser URLs** | Full URL when in Chrome, Safari, Arc, Firefox, Brave, Edge | `https://github.com/user/repo` |
| **Document Paths** | File path when in TextEdit, Preview, Finder, Word, Excel | `~/Documents/notes.txt` |
| **Screenshots** | Full screen captures (mode 2+) | PNG images at strategic moments |
| **Session Events** | Start/stop timestamps with activity stats | Session boundaries |

### Privacy Filtering

Peer attempts to mask sensitive input:
- Password fields (detected by window title containing "password", "login", etc.)
- Input in apps like Keychain Access, 1Password, banking apps
- Content is masked as `****` in these contexts

**However**: This filtering is not foolproof. Sensitive data may still be captured if the context detection fails.

## Installation

```bash
pip install -e .
```

## Usage

```bash
# Start logging (verbose mode shows real-time events)
peer start -v

# Check what's being logged
peer status

# Stop and optionally summarize
peer stop

# Export session to JSON
peer export

# Toggle monitoring with global hotkey
peer hotkey  # Then use Shift+Backspace+Left to toggle
```

## Operating Modes

| Mode | Description |
|------|-------------|
| 1 | Logs only (keystrokes, clicks, windows) |
| 2 | Logs + screenshots |
| 3 | Logs + screenshots + periodic AI summaries |
| 4 | Logs + screenshots + real-time AI feedback |

## Configuration

Copy `.env.example` to `.env`:

```bash
PEER_DATA_DIR=~/.peer          # Storage location
PEER_DEFAULT_MODE=1            # Default mode (1-4)
OPENAI_API_KEY=sk-...          # For AI features
ANTHROPIC_API_KEY=sk-ant-...   # Alternative AI provider
```

## Data Storage

All data stored locally in `~/.peer/`:
- `peer.db` - SQLite database with all events
- `screenshots/` - Captured images
- `exports/` - JSON exports

## Requirements

- Python 3.9+
- macOS (uses Quartz and AppKit for screen/window access)

## License

MIT
