"""Organised media library + playlists for Jungle Leopard.

Layout under the library folder:
    media/videos/<id>_<title>[_<anchor>].mp4    converted once, reused afterwards
    media/images/<id>_<title>[_<anchor>].jpg
    playlists/<name>.json                        playlist definition (items, interval)
    playlists/<name>/01 - <title>.mp4 ...        ready-to-pick folder for Jungle Leopard
    library.json                                 manifest: what was produced from what
Pass-through ("already compatible") videos are not copied into media/; the playlist
folder gets a hard link to the original when possible (no extra disk space).
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import threading

from .converter import Plan, build_command, plan_for, run_ffmpeg
from .settings import atomic_write_json, read_json

_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def slug(text: str, limit: int = 60) -> str:
    text = _BAD.sub("_", text).strip(" ._") or "untitled"
    return text[:limit].rstrip(" ._")


def safe_playlist_name(name: str) -> str:
    return slug(name, 40)


def _source_sig(path: str) -> str:
    st = os.stat(path)
    return f"{st.st_size}:{int(st.st_mtime)}"


def _settings_sig(s, plan: Plan, anchor: str) -> str:
    keys = ("target_w", "target_h", "crop_mode", "max_fps", "crf", "preset", "max_seconds",
            "gif_mode", "gif_min_seconds")
    raw = "|".join(str(s[k]) for k in keys) + f"|{plan.action}|{anchor}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


class Library:
    def __init__(self, root: str):
        self.root = root
        self.manifest_path = os.path.join(root, "library.json")
        self.manifest = read_json(self.manifest_path, {}) or {}
        self.lock = threading.Lock()

    # ------------------------------------------------------------------ media
    def output_for(self, wp, plan: Plan, anchor: str) -> str:
        sub = "images" if plan.out_ext == ".jpg" else "videos"
        tag = "" if anchor == "center" or plan.action == "link" else f"_{anchor}"
        return os.path.join(self.root, "media", sub, f"{wp.id}_{slug(wp.title, 50)}{tag}{plan.out_ext}")

    def entry_key(self, wp, anchor: str) -> str:
        return f"{wp.id}@{anchor}"

    def cached_output(self, wp, plan: Plan, s, anchor: str) -> str | None:
        """Return an existing up-to-date output, so nothing is converted twice."""
        if plan.action == "link":
            return wp.source
        e = self.manifest.get(self.entry_key(wp, anchor))
        if not e:
            return None
        try:
            if (e["source"] == wp.source and e["source_sig"] == _source_sig(wp.source)
                    and e["settings_sig"] == _settings_sig(s, plan, anchor) and os.path.isfile(e["output"])):
                return e["output"]
        except (KeyError, OSError):
            return None
        return None

    def prepare(self, wp, info, s, ffmpeg, on_progress=None, cancel=None) -> tuple[str | None, str]:
        """Make sure a Jungle-Leopard-ready file exists for wp. Returns (path, message)."""
        anchor = s.anchor_for(wp.id)
        plan = plan_for(wp, info, s)
        if plan.action == "skip":
            return None, f"skipped: {plan.reason}"
        cached = self.cached_output(wp, plan, s, anchor)
        if cached:
            return cached, ("used original (" + plan.reason + ")") if plan.action == "link" else "already in library"
        if not ffmpeg:
            return None, "ffmpeg not found"
        out = self.output_for(wp, plan, anchor)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        tmp = out + ".part" + plan.out_ext
        cmd = build_command(ffmpeg, wp, info, plan, s, anchor, tmp)
        duration = (info or {}).get("duration") or 0
        if s["max_seconds"]:
            duration = min(duration or s["max_seconds"], s["max_seconds"])
        if wp.kind == "gif":
            duration = max(duration, float(s["gif_min_seconds"]))
        ok, err = run_ffmpeg(cmd, duration, on_progress, cancel)
        if not ok or not os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
            return None, f"conversion failed: {err or 'unknown error'}"
        os.replace(tmp, out)
        with self.lock:
            self.manifest[self.entry_key(wp, anchor)] = {
                "id": wp.id, "title": wp.title, "kind": wp.kind, "source": wp.source,
                "source_sig": _source_sig(wp.source), "settings_sig": _settings_sig(s, plan, anchor),
                "output": out, "reason": plan.reason,
            }
            atomic_write_json(self.manifest_path, self.manifest)
        return out, f"converted ({plan.reason})"

    # -------------------------------------------------------------- playlists
    @property
    def playlist_dir(self) -> str:
        return os.path.join(self.root, "playlists")

    def list_playlists(self) -> list[str]:
        try:
            return sorted(f[:-5] for f in os.listdir(self.playlist_dir) if f.endswith(".json"))
        except OSError:
            return []

    def load_playlist(self, name: str) -> dict:
        data = read_json(os.path.join(self.playlist_dir, f"{name}.json"), None)
        if not isinstance(data, dict):
            data = {}
        return {"name": name, "interval": int(data.get("interval", 15)), "items": list(data.get("items", []))}

    def save_playlist(self, pl: dict) -> None:
        name = safe_playlist_name(pl["name"])
        atomic_write_json(os.path.join(self.playlist_dir, f"{name}.json"),
                          {"name": name, "interval": int(pl["interval"]), "items": pl["items"]})

    def delete_playlist(self, name: str) -> None:
        try:
            os.remove(os.path.join(self.playlist_dir, f"{name}.json"))
        except OSError:
            pass
        shutil.rmtree(os.path.join(self.playlist_dir, name), ignore_errors=True)

    def materialise(self, pl: dict, files: list[tuple[str, str]]) -> str:
        """Fill playlists/<name>/ with numbered links: files = [(title, path), ...]."""
        folder = os.path.join(self.playlist_dir, safe_playlist_name(pl["name"]))
        os.makedirs(folder, exist_ok=True)
        for old in os.listdir(folder):  # this folder is owned by the tool
            p = os.path.join(folder, old)
            if os.path.isfile(p):
                os.remove(p)
        width = max(2, len(str(len(files))))
        for i, (title, src) in enumerate(files, 1):
            dst = os.path.join(folder, f"{i:0{width}d} - {slug(title, 50)}{os.path.splitext(src)[1].lower()}")
            try:
                os.link(src, dst)        # hard link: no extra disk space (same drive)
            except OSError:
                shutil.copy2(src, dst)   # different drive or not permitted
        with open(os.path.join(folder, "_HOW_TO_USE.txt"), "w", encoding="utf-8") as fh:
            fh.write(
                f"Playlist: {pl['name']}\nItems: {len(files)}\nSlide interval: {pl['interval']} s\n\n"
                "In Jungle Leopard Display:\n"
                " 1. Theme Editor > Create Theme (1920x462).\n"
                " 2. Add Component > Media, size it to the full screen (Cover).\n"
                " 3. Load Method: Local Upload > select ALL media files in this folder.\n"
                f" 4. Turn on Slideshow, set Slide Interval to {pl['interval']} s, transition Fade.\n"
                " 5. Save the theme and apply it. Jungle Leopard remembers it and auto-starts.\n")
        return folder
