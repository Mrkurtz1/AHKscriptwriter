"""Settings management for the AHK Macro Builder."""

import json
import os
from dataclasses import dataclass, asdict
from src.models import CoordMode


DEFAULT_CONFIG_PATH = os.path.join(
    os.path.expanduser("~"), ".ahk_macro_builder", "settings.json"
)


@dataclass
class AppSettings:
    """Application settings with defaults."""
    # Recording
    record_mouse_moves: bool = False
    mouse_move_sample_ms: int = 50
    drag_threshold_px: int = 10
    coord_mode: str = "Screen"  # Screen / Window / Client

    # Window targeting
    target_window_title: str = ""  # for Window/Client coord mode

    # Filtering
    ignore_own_clicks: bool = True  # don't record clicks on the tool's own window

    # Color capture
    color_format: str = "0x"  # "0x" for 0xRRGGBB, "#" for #RRGGBB

    # Replay
    replay_speed_multiplier: float = 1.0
    ahk_exe_path: str = ""  # auto-detect if empty

    # Naming
    macro_naming: str = "timestamp"  # "timestamp" or "incremental"
    macro_prefix: str = "Macro"

    # UI
    window_width: int = 1100
    window_height: int = 700

    def get_coord_mode(self) -> CoordMode:
        return CoordMode(self.coord_mode)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


class SettingsManager:
    """Loads and saves application settings to a JSON file."""

    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self.settings = AppSettings()

    def load(self) -> AppSettings:
        """Load settings from disk, falling back to defaults."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    data = json.load(f)
                self.settings = AppSettings.from_dict(data)
            except (json.JSONDecodeError, TypeError, KeyError):
                self.settings = AppSettings()
        return self.settings

    def save(self):
        """Persist current settings to disk."""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self.settings.to_dict(), f, indent=2)

    def update(self, **kwargs):
        """Update specific settings fields and save."""
        for key, value in kwargs.items():
            if hasattr(self.settings, key):
                setattr(self.settings, key, value)
        self.save()
