"""Headless mode: rescan the workshop and rebuild the last playlist (run at logon)."""
from __future__ import annotations

import os

from .converter import ProbeCache, find_tools
from .jobs import build_playlist
from .library import Library
from .scanner import scan_workshop
from .settings import Settings, app_dir


def run_sync() -> int:
    s = Settings()
    log_path = os.path.join(app_dir(), "sync.log")
    with open(log_path, "w", encoding="utf-8") as fh:
        def log(msg):
            fh.write(msg + "\n")
            fh.flush()
        name = s.get("last_playlist")
        if not name:
            log("No previous playlist; nothing to do.")
            return 0
        ffmpeg, ffprobe = find_tools(s["jl_dir"])
        lib = Library(s["library_dir"])
        by_id = {w.id: w for w in scan_workshop(s["workshop_dir"])}
        pl = lib.load_playlist(name)
        folder, ok, failed = build_playlist(pl, by_id, s, lib, ProbeCache(ffprobe), ffmpeg, log)
        log(f"Done: {ok} ready, {failed} failed -> {folder}")
    return 0
