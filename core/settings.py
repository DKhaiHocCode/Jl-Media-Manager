"""Persistent settings for JL Media Manager (stored in %APPDATA%\\JLMediaManager)."""
from __future__ import annotations

import json
import os
import tempfile

APP_NAME = "JLMediaManager"

# Values discovered during the Phase 1 inspection of this PC.
DEFAULTS = {
    "workshop_dir": r"C:\Program Files (x86)\Steam\steamapps\workshop\content\431960",
    "library_dir": os.path.join(os.path.expanduser("~"), "Videos", "JL Library"),
    "jl_dir": r"C:\Program Files\Jungle Leopard Display",
    # Device reports 1920x462 landscape (D215-NOR-FL7707N-9.16inch-hor).
    "target_w": 1920,
    "target_h": 462,
    # crop_mode: "precrop" = crop a 1920x462 band once (recommended);
    #            "jl"      = let Jungle Leopard scale/cover, only fix incompatible files.
    "crop_mode": "precrop",
    "crop_anchor": "center",          # top | center | bottom (left/right for tall bands)
    "max_fps": 30,                    # Jungle Leopard "balanced" live rate is 30
    "crf": 23,
    "preset": "veryfast",
    "max_seconds": 0,                 # 0 = keep full length
    "gif_mode": "mp4",                # mp4 | copy
    "gif_min_seconds": 6,
    "hwaccel": False,                 # try GPU decode for 4K/HEVC sources
    "encoder_threads": 0,             # 0 = half the CPU cores
    "start_with_windows": False,
    "last_playlist": None,
    "anchors": {},                    # per-wallpaper crop anchor overrides {id: anchor}
}


def app_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def atomic_write_json(path: str, data) -> None:
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def read_json(path: str, default=None):
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


class Settings(dict):
    def __init__(self, path: str | None = None):
        super().__init__(DEFAULTS)
        self.path = path or os.path.join(app_dir(), "settings.json")
        stored = read_json(self.path, {}) or {}
        if isinstance(stored, dict):
            self.update({k: v for k, v in stored.items() if k in DEFAULTS})
        self["anchors"] = dict(self.get("anchors") or {})

    def save(self) -> None:
        atomic_write_json(self.path, dict(self))

    def anchor_for(self, wallpaper_id: str) -> str:
        return self["anchors"].get(wallpaper_id, self["crop_anchor"])
