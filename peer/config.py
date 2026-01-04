"""Configuration management for Peer."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

from dotenv import load_dotenv


# Default apps to never log (privacy-sensitive)
DEFAULT_BLOCKED_APPS: Set[str] = {
    "1Password",
    "Keychain Access",
    "LastPass",
    "Bitwarden",
    "Dashlane",
    "Keeper",
    "KeePassXC",
}

# Default bundle IDs to never log
DEFAULT_BLOCKED_BUNDLES: Set[str] = {
    "com.1password.1password",
    "com.apple.keychainaccess",
    "com.lastpass.LastPass",
    "com.bitwarden.desktop",
    "com.dashlane.Dashlane",
}


@dataclass
class Config:
    """Application configuration loaded from environment variables."""

    data_dir: Path = field(default_factory=lambda: Path.home() / ".peer")
    default_mode: int = 1
    screenshot_interval: int = 60  # seconds
    summary_interval: int = 300  # seconds
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    blocked_apps: Set[str] = field(default_factory=lambda: DEFAULT_BLOCKED_APPS.copy())
    blocked_bundles: Set[str] = field(default_factory=lambda: DEFAULT_BLOCKED_BUNDLES.copy())
    afk_timeout: int = 180  # seconds before considered AFK

    def __post_init__(self):
        self.data_dir = Path(self.data_dir)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        self._load_blocklist()

    def _load_blocklist(self) -> None:
        """Load user blocklist from config file if it exists."""
        blocklist_file = self.data_dir / "blocklist.json"
        if blocklist_file.exists():
            try:
                with open(blocklist_file) as f:
                    data = json.load(f)
                    if "apps" in data:
                        self.blocked_apps.update(data["apps"])
                    if "bundles" in data:
                        self.blocked_bundles.update(data["bundles"])
            except Exception:
                pass  # Ignore invalid config

    def save_blocklist(self) -> None:
        """Save current blocklist to config file."""
        blocklist_file = self.data_dir / "blocklist.json"
        with open(blocklist_file, "w") as f:
            json.dump({
                "apps": sorted(self.blocked_apps),
                "bundles": sorted(self.blocked_bundles),
            }, f, indent=2)

    def is_app_blocked(self, app_name: str, bundle_id: Optional[str] = None) -> bool:
        """Check if an app should be blocked from logging."""
        if app_name in self.blocked_apps:
            return True
        if bundle_id and bundle_id in self.blocked_bundles:
            return True
        return False

    def block_app(self, app_name: str) -> None:
        """Add an app to the blocklist."""
        self.blocked_apps.add(app_name)
        self.save_blocklist()

    def unblock_app(self, app_name: str) -> None:
        """Remove an app from the blocklist."""
        self.blocked_apps.discard(app_name)
        self.save_blocklist()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "peer.db"

    @property
    def screenshots_dir(self) -> Path:
        return self.data_dir / "screenshots"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @classmethod
    def from_env(cls, dotenv_path: Optional[Path] = None) -> "Config":
        """Load configuration from environment variables."""
        if dotenv_path:
            load_dotenv(dotenv_path)
        else:
            load_dotenv()

        data_dir = os.getenv("PEER_DATA_DIR", str(Path.home() / ".peer"))

        return cls(
            data_dir=Path(data_dir).expanduser(),
            default_mode=int(os.getenv("PEER_DEFAULT_MODE", "1")),
            screenshot_interval=int(os.getenv("PEER_SCREENSHOT_INTERVAL", "60")),
            summary_interval=int(os.getenv("PEER_SUMMARY_INTERVAL", "300")),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            afk_timeout=int(os.getenv("PEER_AFK_TIMEOUT", "180")),
        )


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def init_config(config: Config) -> None:
    """Initialize the global configuration."""
    global _config
    _config = config
