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
| **AFK Status** | Away-from-keyboard detection | `afk` after 3min idle, `active` on return |

### Privacy Features

- **App Blocklist**: Password managers (1Password, Keychain, etc.) are blocked by default
- **Incognito Detection**: Private browsing windows skip URL capture
- **Sensitive Context Masking**: Password fields show `****` instead of actual input
- **Data Management**: Delete or redact events after capture

Manage blocked apps:
```bash
peer blocklist                  # Show blocked apps
peer blocklist --add "Slack"    # Block an app
peer blocklist --remove "Slack" # Unblock an app
```

**Note**: Privacy filtering is not foolproof. Sensitive data may still be captured if context detection fails.

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
peer hotkey  # Then use Ctrl+Shift+Left to toggle

# Data management
peer stats                      # Show database statistics
peer sessions                   # List all sessions
peer delete --before 2024-01-01 # Delete old events
peer delete --app "1Password"   # Delete events from an app
peer redact "password123"       # Redact sensitive text
peer compact                    # Merge redundant events
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

## Acknowledgements

Several features in Peer were inspired by [ActivityWatch](https://activitywatch.net/), an excellent open-source time tracker (MPL-2.0 license):

- **AFK Detection**: Idle state tracking based on system input activity
- **Heartbeat/Merge Pattern**: Combining consecutive similar events to reduce storage
- **Incognito Detection**: Respecting browser private mode
- **Data Management**: User control over deletion and retention

ActivityWatch focuses on productivity analytics ("how much time on X?") while Peer captures detailed activity for LLM context. They complement each other well.

## License

MIT
