"""Shared work routines used by both the GUI and the headless --sync mode."""
from __future__ import annotations

import threading

from .converter import ProbeCache
from .library import Library


def build_playlist(pl: dict, by_id: dict, s, lib: Library, probe: ProbeCache, ffmpeg: str | None,
                   log=print, progress=None, cancel: threading.Event | None = None) -> tuple[str | None, int, int]:
    """Convert (only what's needed) and materialise a playlist folder.

    Returns (folder, ok_count, failed_count). progress(i, n, fraction_of_current).
    """
    files, failed = [], 0
    ids = pl["items"]
    for i, wid in enumerate(ids):
        if cancel is not None and cancel.is_set():
            log("Cancelled.")
            return None, len(files), failed
        wp = by_id.get(wid)
        if wp is None:
            log(f"[{i + 1}/{len(ids)}] {wid}: no longer in the workshop folder, skipped")
            failed += 1
            continue
        info = probe.probe(wp.source) if wp.kind in ("video", "gif") and wp.usable else None
        cb = (lambda f, i=i: progress(i, len(ids), f)) if progress else None
        if progress:
            progress(i, len(ids), 0.0)
        path, msg = lib.prepare(wp, info, s, ffmpeg, cb, cancel)
        log(f"[{i + 1}/{len(ids)}] {wp.title}: {msg}")
        if path:
            files.append((wp.title, path))
        else:
            failed += 1
    probe.save()
    if not files:
        return None, 0, failed
    folder = lib.materialise(pl, files)
    if progress:
        progress(len(ids), len(ids), 1.0)
    return folder, len(files), failed
