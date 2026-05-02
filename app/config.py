import json
import os
from pathlib import Path
from typing import Any


class Config:
    DEFAULTS: dict = {
        "install_dir": "",
        "rom_path": "",
        "rom_sha1_verified": 0,  # used when no installation row yet; DB wins once installed
        "assets_dir": "",
        "auto_check_updates": True,
        "check_interval_hours": 24,
        "installed_version": "",
        "installed_release_id": None,
        "theme": "dark",
        "window_width": 680,
        "window_height": 480,
    }

    def __init__(self):
        self.app_data_dir = Path(os.environ.get("APPDATA", Path.home())) / "AutoTMC"
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.app_data_dir / "config.json"
        self._data = self._load()

    def _load(self) -> dict:
        if self.config_path.exists():
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    stored = json.load(f)
                return {**self.DEFAULTS, **stored}
            except Exception:
                pass
        return self.DEFAULTS.copy()

    def save(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        self._data[key] = value
        self.save()

    def __getitem__(self, key: str) -> Any:
        return self._data.get(key)

    def __setitem__(self, key: str, value: Any):
        self.set(key, value)
