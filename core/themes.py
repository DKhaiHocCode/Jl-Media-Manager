"""Add ready-made sensor widgets (CPU/GPU/disk) to Jungle Leopard themes.

Saved themes are plain JSON in %APPDATA%/Jungle_Leopard_Display/themes. A widget is one entry in the
theme's "children" list; its look and position are edited afterwards in Jungle Leopard's Theme Editor.
"""
from __future__ import annotations

import copy
import glob
import json
import os
import random
import shutil
import string
import subprocess
import time

from .settings import app_dir, atomic_write_json

# data source key -> (label, value range used by arc/bar)
SOURCES = {
    "cpuLayout_temperature": ("CPU temperature", (0, 100)),
    "cpuLayout_utilization": ("CPU usage", (0, 100)),
    "cpuLayout_powerDraw": ("CPU power", (0, 250)),
    "cpuLayout_currentRefreshRate": ("CPU clock", (0, 6000)),
    "cpuLayout_name": ("CPU name", None),
    "graphics_temperature": ("GPU temperature", (0, 100)),
    "graphics_utilization": ("GPU usage", (0, 100)),
    "graphics_currentRefreshRate": ("GPU clock", (0, 3000)),
    "graphics_name": ("GPU name", None),
    "diskLayout_temperature": ("Disk temperature", (0, 100)),
    "diskLayout_utilization": ("Disk usage", (0, 100)),
    "time_current": ("Current time", None),
}

# Shapes copied from the sensor widgets of the stock 9.16" theme; x/y are the editor's default drop spot.
_COMMON = {"_chosed": False, "_checked": False, "_group": "常规控件"}
KINDS = {
    "data": {"label": "Number", **_COMMON, "icon": "data", "type": "data", "tx": 0, "ty": 0, "scale": [2, 2],
             "children": {"keepRatio": True, "x": 938.5, "y": 228.8, "rotate": 0, "align": "center",
                          "fontFamily": "Bahnschrift", "fontSize": 24, "color": "255,255,255,1",
                          "tofixCount": 0}},
    "arc": {"label": "Arc", **_COMMON, "icon": "cycle", "type": "arc", "tx": 0, "ty": 0, "scale": [1, 1],
            "children": {"keepRatio": True, "x": 864, "y": 141.2, "rotate": 0, "borderWidth": 0,
                         "radiusWidth": 50, "strokeWidth": 7, "gapDegree": 203, "trailColor": "126,211,33,1",
                         "borderBgColor": ["155,155,155,1", "155,155,155,1"], "borderBgType": "cut",
                         "width": 240, "height": 240}},
    "progress": {"label": "Bar", **_COMMON, "icon": "loading", "type": "progress", "tx": 0, "ty": 0,
                 "scale": [0.4, 0.4],
                 "children": {"keepRatio": True, "x": 576, "y": 201.6, "rotate": 0, "width": 960, "height": 96,
                              "borderRadius": 16, "borderWidth": 0, "borderColor": "255,255,255,1",
                              "borderStyle": "solid", "trailColor": "74,74,74,1",
                              "borderBgColor": ["155,155,155,1", "255,255,255,1"], "borderBgType": "cut"}},
}


def themes_dir() -> str:
    return os.path.join(os.environ.get("APPDATA", ""), "Jungle_Leopard_Display", "themes")


def list_themes(folder: str | None = None) -> list[dict]:
    """[{path, label, width, height, widgets}] for every theme file."""
    out = []
    for path in sorted(glob.glob(os.path.join(folder or themes_dir(), "*.json"))):
        try:
            with open(path, encoding="utf-8-sig") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and "deviceWidth" in d:
            out.append({"path": path, "label": d.get("label", os.path.basename(path)),
                        "width": d["deviceWidth"], "height": d["deviceHeight"],
                        "widgets": len([c for c in d.get("children", []) if isinstance(c, dict)])})
    return out


def jl_running() -> bool:
    """True if Jungle Leopard Display is open (it would overwrite edits made to its theme files)."""
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Jungle Leopard Display.exe", "/NH"],
                           capture_output=True, text=True, timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return "Jungle Leopard Display" in r.stdout
    except (OSError, subprocess.SubprocessError):
        return False


def _new_id() -> str:
    return f"{int(time.time() * 1000)}_" + "".join(random.choices(string.ascii_letters + string.digits, k=4))


def make_widget(kind: str, source: str, index: int) -> dict:
    w = copy.deepcopy(KINDS[kind])
    wid = _new_id()
    w.update(id=wid, value=wid, key=wid, index=index)
    w["children"]["dataSource"] = source
    rng = SOURCES[source][1]
    if kind in ("arc", "progress"):
        w["children"]["dataRange"] = list(rng or (0, 100))
    return w


def add_widgets(theme_path: str, specs: list[tuple[str, str]], backup_dir: str | None = None) -> str:
    """Append widgets [(kind, source), ...] to a theme file. Returns the backup path."""
    with open(theme_path, encoding="utf-8-sig") as fh:
        d = json.load(fh)
    backup_dir = backup_dir or os.path.join(app_dir(), "theme_backups")
    os.makedirs(backup_dir, exist_ok=True)
    backup = os.path.join(backup_dir, f"{time.strftime('%Y%m%d-%H%M%S')}_{os.path.basename(theme_path)}")
    shutil.copy2(theme_path, backup)
    children = d.setdefault("children", [])
    nxt = max([c.get("index", 0) for c in children if isinstance(c, dict)] + [-1]) + 1
    for i, (kind, source) in enumerate(specs):
        children.append(make_widget(kind, source, nxt + i))
        time.sleep(0.002)  # keep ids unique
    atomic_write_json(theme_path, d)
    return backup
