"""Discover and classify Wallpaper Engine workshop items.

Only reads project.json and directory listings; media files are never opened here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from .settings import read_json

VIDEO_EXT = (".mp4", ".webm", ".mkv", ".mov", ".avi")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
GIF_EXT = (".gif",)

# kinds the converter can turn into something Jungle Leopard plays
USABLE_KINDS = ("video", "image", "gif", "scene")


@dataclass
class Wallpaper:
    id: str
    title: str
    kind: str                 # video | image | gif | scene | web | application | unknown
    folder: str
    source: str | None        # media file to use (for scenes: the preview still)
    preview: str | None
    size: int = 0             # bytes of the source file
    wp_type: str = ""         # raw "type" from project.json
    note: str = ""
    tags: list = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return self.kind in USABLE_KINDS and bool(self.source) and os.path.isfile(self.source)


def _size(path: str | None) -> int:
    try:
        return os.path.getsize(path) if path else 0
    except OSError:
        return 0


def _top_files(folder: str) -> list[str]:
    try:
        return [e.name for e in os.scandir(folder) if e.is_file()]
    except OSError:
        return []


def _first(files, exts, exclude_preview=True):
    for name in sorted(files):
        low = name.lower()
        if exclude_preview and low.startswith("preview"):
            continue
        if low.endswith(exts):
            return name
    return None


def classify_item(folder: str) -> Wallpaper:
    wid = os.path.basename(os.path.normpath(folder))
    files = _top_files(folder)
    lower = {f.lower(): f for f in files}
    project = read_json(os.path.join(folder, "project.json"), {}) or {}
    if not isinstance(project, dict):
        project = {}

    title = project.get("title") if isinstance(project.get("title"), str) else ""
    title = title.strip() or wid
    wp_type = str(project.get("type") or "").lower()
    main = project.get("file") if isinstance(project.get("file"), str) else ""
    tags = project.get("tags") if isinstance(project.get("tags"), list) else []

    preview_name = project.get("preview") if isinstance(project.get("preview"), str) else None
    if not preview_name or preview_name.lower() not in lower:
        preview_name = next((lower[n] for n in ("preview.jpg", "preview.png", "preview.gif") if n in lower), None)
    else:
        preview_name = lower[preview_name.lower()]
    preview = os.path.join(folder, preview_name) if preview_name else None

    def mk(kind, src_name=None, note="", src_path=None):
        src = src_path or (os.path.join(folder, src_name) if src_name else None)
        return Wallpaper(wid, title, kind, folder, src, preview, _size(src), wp_type, note, tags)

    main_low = main.lower()
    main_exists = main_low in lower

    # 1) video wallpapers
    if wp_type == "video" or main_low.endswith(VIDEO_EXT):
        name = lower[main_low] if main_exists and main_low.endswith(VIDEO_EXT) else _first(files, VIDEO_EXT)
        if name:
            return mk("video", name)
        return mk("unknown", note="video wallpaper but no video file found")

    # 2) scene wallpapers: scene.pkg is only renderable by Wallpaper Engine -> use preview
    if wp_type == "scene" or "scene.pkg" in lower or "scene.json" in lower:
        if preview:
            return mk("scene", src_path=preview, note="scene.pkg can't render outside Wallpaper Engine; using preview")
        return mk("scene", note="scene without preview")

    # 3) plain image / gif wallpapers
    if main_low.endswith(GIF_EXT) and main_exists:
        return mk("gif", lower[main_low])
    if main_low.endswith(IMAGE_EXT) and main_exists:
        return mk("image", lower[main_low])

    # 4) web / application: not convertible, but salvage a bundled gif/image if present
    if wp_type in ("web", "application") or main_low.endswith((".html", ".htm", ".exe")) or \
            any(f.lower().endswith((".html", ".exe")) for f in files):
        kind = "application" if (wp_type == "application" or main_low.endswith(".exe")
                                 or any(f.lower().endswith(".exe") for f in files)) else "web"
        gif = _first(files, GIF_EXT)
        if gif:
            return mk("gif", gif, note=f"animation bundled with a {kind} wallpaper")
        return mk(kind, note=f"{kind} wallpapers can't be converted to media")

    # 5) no project.json: guess from files
    for kind, exts in (("video", VIDEO_EXT), ("gif", GIF_EXT), ("image", IMAGE_EXT)):
        name = _first(files, exts)
        if name:
            return mk(kind, name, note="guessed from files")
    return mk("unknown", note="unrecognised item")


def scan_workshop(root: str) -> list[Wallpaper]:
    items = []
    try:
        entries = sorted(os.scandir(root), key=lambda e: e.name)
    except OSError:
        return items
    for entry in entries:
        if entry.is_dir():
            items.append(classify_item(entry.path))
    order = {k: i for i, k in enumerate(("video", "gif", "image", "scene", "web", "application", "unknown"))}
    items.sort(key=lambda w: (order.get(w.kind, 99), w.title.lower()))
    return items
