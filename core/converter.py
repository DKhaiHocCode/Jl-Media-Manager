"""Probe media and convert it for the Jungle Leopard 9.16" bar (1920x462).

Uses ffmpeg/ffprobe. By default the copies bundled with Jungle Leopard Display are
used read-only (they are not modified); otherwise ffmpeg on PATH.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass

from .settings import app_dir, atomic_write_json, read_json

IS_WIN = sys.platform == "win32"
_FFMPEG_REL = r"resources\app.asar.unpacked\node_modules\@ffmpeg-installer\win32-x64\ffmpeg.exe"
_FFPROBE_REL = r"resources\app.asar.unpacked\node_modules\@ffprobe-installer\win32-x64\ffprobe.exe"


def _creationflags() -> int:
    if not IS_WIN:
        return 0
    # Run in background without a console window and below normal priority,
    # so conversions never make the desktop or Jungle Leopard stutter.
    return 0x08000000 | 0x00004000  # CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS


def find_tools(jl_dir: str | None) -> tuple[str | None, str | None]:
    ffmpeg = ffprobe = None
    if jl_dir:
        cand_mpeg = os.path.join(jl_dir, _FFMPEG_REL)
        cand_probe = os.path.join(jl_dir, _FFPROBE_REL)
        if os.path.isfile(cand_mpeg):
            ffmpeg = cand_mpeg
        if os.path.isfile(cand_probe):
            ffprobe = cand_probe
    return ffmpeg or shutil.which("ffmpeg"), ffprobe or shutil.which("ffprobe")


# --------------------------------------------------------------------------- probing

class ProbeCache:
    """ffprobe results cached by path+size+mtime, so each file is probed once."""

    def __init__(self, ffprobe: str | None, path: str | None = None):
        self.ffprobe = ffprobe
        self.path = path or os.path.join(app_dir(), "probe_cache.json")
        self.data = read_json(self.path, {}) or {}
        self.lock = threading.Lock()
        self.dirty = False

    @staticmethod
    def _key(path: str) -> str | None:
        try:
            st = os.stat(path)
        except OSError:
            return None
        return f"{os.path.normcase(os.path.abspath(path))}|{st.st_size}|{int(st.st_mtime)}"

    def probe(self, path: str) -> dict | None:
        key = self._key(path)
        if key is None:
            return None
        with self.lock:
            if key in self.data:
                return self.data[key]
        info = ffprobe_info(self.ffprobe, path)
        if info is not None:
            with self.lock:
                self.data[key] = info
                self.dirty = True
        return info

    def save(self) -> None:
        with self.lock:
            if self.dirty:
                atomic_write_json(self.path, self.data)
                self.dirty = False


def _rate(value: str | None) -> float:
    try:
        num, _, den = (value or "0/1").partition("/")
        den_f = float(den or 1)
        return float(num) / den_f if den_f else 0.0
    except ValueError:
        return 0.0


def ffprobe_info(ffprobe: str | None, path: str) -> dict | None:
    if not ffprobe:
        return None
    cmd = [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=60, creationflags=_creationflags())
        data = json.loads(out.stdout.decode("utf-8", "replace") or "{}")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    vstreams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    if not vstreams:
        return None
    v = vstreams[0]
    fps = _rate(v.get("avg_frame_rate")) or _rate(v.get("r_frame_rate"))
    try:
        duration = float(data.get("format", {}).get("duration") or v.get("duration") or 0)
    except ValueError:
        duration = 0.0
    rotation = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            try:
                rotation = int(sd["rotation"])
            except (TypeError, ValueError):
                pass
    return {
        "codec": v.get("codec_name", ""),
        "pix_fmt": v.get("pix_fmt", ""),
        "width": int(v.get("width") or 0),
        "height": int(v.get("height") or 0),
        "fps": round(fps, 3),
        "duration": round(duration, 3),
        "rotation": rotation,
        "has_audio": any(s.get("codec_type") == "audio" for s in data.get("streams", [])),
    }


# --------------------------------------------------------------------------- planning

@dataclass
class Plan:
    action: str          # link | transcode | image | skip
    reason: str
    out_ext: str = ""


def plan_for(wp, info: dict | None, s) -> Plan:
    """Decide the cheapest way to get this wallpaper onto the bar."""
    tw, th = s["target_w"], s["target_h"]
    kind = wp.kind
    if not wp.usable:
        return Plan("skip", wp.note or f"{kind} not supported")

    if kind in ("image", "scene"):
        return Plan("image", "crop/scale still to %dx%d JPG" % (tw, th), ".jpg")

    if kind == "gif":
        if s["gif_mode"] == "copy":
            return Plan("link", "GIF used as-is (gif_mode=copy)", ".gif")
        return Plan("transcode", "GIF -> small looping H.264 MP4", ".mp4")

    # video
    if info is None:
        return Plan("transcode", "could not probe; converting to be safe", ".mp4")
    w, h, fps = info["width"], info["height"], info["fps"]
    if info.get("rotation") in (90, -90, 270, -270):
        w, h = h, w
    problems = []
    if info["codec"] != "h264":
        problems.append(f"codec {info['codec']}")
    if info["pix_fmt"] not in ("yuv420p", "yuvj420p"):
        problems.append(info["pix_fmt"] or "pixel format")
    if fps > 60.5:
        problems.append(f"{fps:g} fps")
    if s["crop_mode"] == "precrop":
        aspect_ok = h and abs((w / h) - (tw / th)) / (tw / th) < 0.03
        if not aspect_ok:
            problems.append("needs crop to %dx%d" % (tw, th))
        if w > tw * 1.05:
            problems.append(f"{w}x{h} larger than panel")
    else:  # let Jungle Leopard scale; only shrink very large sources once
        if w > 1920 or h > 1080:
            problems.append(f"{w}x{h} larger than 1080p")
    if s["max_seconds"] and info["duration"] > s["max_seconds"] + 0.5:
        problems.append("trim to %ss" % s["max_seconds"])
    if not problems:
        return Plan("link", "already compatible - no transcoding", os.path.splitext(wp.source)[1].lower())
    return Plan("transcode", ", ".join(problems), ".mp4")


# --------------------------------------------------------------------------- filters

def crop_scale_filter(tw: int, th: int, anchor: str, crop: bool = True) -> str:
    if not crop:  # fit inside 1920x1080 keeping aspect (crop_mode == "jl")
        return "scale='min(1920,iw)':'min(1080,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2"
    a = f"{tw / th:.6f}"  # precomputed: "iw/1920/462" would divide twice
    ow, oh = f"min(iw\\,ih*{a})", f"min(ih\\,iw/{a})"
    try:  # numeric anchor: 0-100 % along the axis that has spare room
        pct = min(100.0, max(0.0, float(anchor)))
        x, y = f"(iw-ow)*{pct / 100:.4f}", f"(ih-oh)*{pct / 100:.4f}"
    except ValueError:
        x = {"left": "0", "right": "iw-ow"}.get(anchor, "(iw-ow)/2")
        y = {"top": "0", "bottom": "ih-oh"}.get(anchor, "(ih-oh)/2")
    return f"crop='{ow}':'{oh}':'{x}':'{y}',scale={tw}:{th}:flags=bicubic,setsar=1"


def build_command(ffmpeg: str, wp, info: dict | None, plan: Plan, s, anchor: str, out_path: str) -> list[str]:
    tw, th = s["target_w"], s["target_h"]
    crop = s["crop_mode"] == "precrop"
    vf = crop_scale_filter(tw, th, anchor, crop)
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error"]

    if plan.action == "image":
        if not crop:
            vf = crop_scale_filter(tw, th, anchor, True)  # stills are always cropped exactly
        return cmd + ["-i", wp.source, "-frames:v", "1", "-vf", vf, "-q:v", "2", out_path]

    threads = s["encoder_threads"] or max(1, (os.cpu_count() or 2) // 2)
    pre, post = [], []
    if s["hwaccel"] and wp.kind == "video":
        pre += ["-hwaccel", "auto"]
    if wp.kind == "gif":
        dur = (info or {}).get("duration") or 1.0
        target = max(float(s["gif_min_seconds"]), dur)
        loops = max(0, math.ceil(target / max(dur, 0.04)) - 1)
        pre += ["-stream_loop", str(loops)]
        post += ["-t", f"{dur * (loops + 1):.3f}"]
    elif s["max_seconds"]:
        post += ["-t", str(s["max_seconds"])]

    fps = (info or {}).get("fps") or 0
    if fps == 0 or fps > s["max_fps"] + 0.5:
        vf += f",fps={s['max_fps']}"
    vf += ",format=yuv420p"
    return (cmd + pre + ["-i", wp.source] + post +
            ["-map", "0:v:0", "-vf", vf, "-an", "-sn", "-dn",
             "-c:v", "libx264", "-preset", s["preset"], "-crf", str(s["crf"]),
             "-profile:v", "high", "-threads", str(threads),
             "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", out_path])


def run_ffmpeg(cmd: list[str], duration: float, on_progress=None, cancel: threading.Event | None = None) -> tuple[bool, str]:
    """Run ffmpeg, reporting 0..1 progress from -progress output. Returns (ok, error)."""
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                creationflags=_creationflags())
    except OSError as exc:
        return False, str(exc)
    err_chunks = []
    t = threading.Thread(target=lambda: err_chunks.append(proc.stderr.read()), daemon=True)
    t.start()
    for raw in proc.stdout:
        if cancel is not None and cancel.is_set():
            proc.kill()
            proc.wait()
            return False, "cancelled"
        line = raw.decode("ascii", "ignore").strip()
        if on_progress and duration > 0 and line.startswith("out_time_us="):
            try:
                on_progress(min(1.0, int(line.split("=", 1)[1]) / 1e6 / duration))
            except ValueError:
                pass
    proc.wait()
    t.join(timeout=5)
    err = (err_chunks[0] if err_chunks else b"").decode("utf-8", "replace").strip()
    return proc.returncode == 0, err[-2000:]
