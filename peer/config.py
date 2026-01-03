"""Configuration management for Peer."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


@dataclass
class Config:
    """Application configuration loaded from environment variables."""

    data_dir: Path = field(default_factory=lambda: Path.home() / ".peer")
    default_mode: int = 1
    screenshot_interval: int = 60  # seconds
    summary_interval: int = 300  # seconds
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None

    def __post_init__(self):
        self.data_dir = Path(self.data_dir)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

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
