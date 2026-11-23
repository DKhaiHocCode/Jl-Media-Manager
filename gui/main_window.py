"""Main tkinter window."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from core import winstartup
from core.converter import ProbeCache, find_tools, plan_for
from core.jobs import build_playlist
from core.library import Library, safe_playlist_name
from core.scanner import scan_workshop
from core.settings import Settings, app_dir
from core.trash import folder_size, is_workshop_item, recycle

from .theme_dialog import ThemeDialog

try:
    from PIL import Image, ImageTk  # optional, only for thumbnails
except ImportError:
    Image = ImageTk = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIND_LABEL = {"video": "Video", "gif": "GIF", "image": "Image", "scene": "Scene (still)",
              "web": "Web", "application": "Application", "unknown": "Unknown"}
FILTERS = ["All usable", "Video", "GIF", "Image", "Scene (still)", "Unsupported", "Everything"]


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("JL Media Manager - Jungle Leopard 9.16\" (1920x462)")
        self.geometry("1280x800")
        self.minsize(1000, 640)
        self.s = Settings()
        self.ffmpeg, self.ffprobe = find_tools(self.s["jl_dir"])
        self.probe = ProbeCache(self.ffprobe)
        self.lib = Library(self.s["library_dir"])
        self.items, self.by_id, self.info = [], {}, {}
        self.q: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.thumb = None
        self._prev_job = None
        self.playlist = None
        self._build()
        self.after(100, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._log(f"ffmpeg: {self.ffmpeg or 'NOT FOUND'}")
        self._log(f"ffprobe: {self.ffprobe or 'NOT FOUND'}")
        self._load_playlists(self.s.get("last_playlist"))
        self.rescan()

    # ---------------------------------------------------------------- layout
    def _build(self):
        top = ttk.Frame(self, padding=6)
        top.pack(fill="x")
        self.btn_list = ttk.Button(top, text="◀ Hide list", width=11, command=self._toggle_list)
        self.btn_list.pack(side="left", padx=(0, 8))
        ttk.Label(top, text="Workshop:").pack(side="left")
        self.var_ws = tk.StringVar(value=self.s["workshop_dir"])
        ttk.Entry(top, textvariable=self.var_ws, width=60).pack(side="left", padx=4)
        ttk.Button(top, text="Browse…", command=self._browse_ws).pack(side="left")
        ttk.Button(top, text="Rescan", command=self.rescan).pack(side="left", padx=4)
        ttk.Button(top, text="Theme widgets…", command=lambda: ThemeDialog(self)).pack(side="left")
        ttk.Label(top, text="Show:").pack(side="left", padx=(12, 2))
        self.var_filter = tk.StringVar(value=FILTERS[0])
        cb = ttk.Combobox(top, textvariable=self.var_filter, values=FILTERS, state="readonly", width=14)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_tree())
        ttk.Label(top, text="Search:").pack(side="left", padx=(12, 2))
        self.var_search = tk.StringVar()
        self.var_search.trace_add("write", lambda *a: self._refresh_tree())
        ttk.Entry(top, textvariable=self.var_search, width=20).pack(side="left")

        self.body = body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=6)

        # wallpaper list
        left = ttk.Frame(body)
        cols = ("type", "res", "fps", "size", "plan")
        self.tree = ttk.Treeview(left, columns=cols, selectmode="extended")
        self.tree.heading("#0", text="Title")
        self.tree.column("#0", width=300)
        for c, t, w in zip(cols, ("Type", "Resolution", "FPS", "Size", "What happens"),
                           (100, 90, 50, 70, 300)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.tag_configure("off", foreground="#999999")
        self.tree.tag_configure("link", foreground="#1b7f2a")
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._show_selected())
        self.tree.bind("<Double-1>", lambda e: self.add_selected())
        self.left = left
        body.add(left, weight=3)

        # right side: preview + playlist
        self.right = right = ttk.Frame(body, padding=(8, 0))
        body.add(right, weight=2)
        right.bind("<Configure>", lambda e: self._schedule_preview())
        self.canvas = tk.Label(right, text="(preview)", background="#111", foreground="#888",
                               width=60, height=8)
        self.canvas.pack(fill="x")
        self.var_detail = tk.StringVar()
        self.lbl_detail = ttk.Label(right, textvariable=self.var_detail, wraplength=460, justify="left")
        self.lbl_detail.pack(fill="x", pady=4)

        row = ttk.Frame(right)
        row.pack(fill="x")
        ttk.Label(row, text="Crop band (top ↔ bottom):").pack(side="left")
        self.var_anchor = tk.DoubleVar(value=50)
        self._loading = False
        self._prev_path = None
        ttk.Scale(row, from_=0, to=100, variable=self.var_anchor, length=160,
                  command=lambda v: self._set_anchor()).pack(side="left", padx=4)
        ttk.Button(row, text="Add selected to playlist →", command=self.add_selected).pack(side="right")
        ttk.Button(row, text="🗑 Delete folder…", command=self.delete_selected).pack(side="right", padx=4)

        plf = ttk.LabelFrame(right, text="Playlist", padding=6)
        plf.pack(fill="both", expand=True, pady=6)
        r1 = ttk.Frame(plf)
        r1.pack(fill="x")
        self.var_pl = tk.StringVar()
        self.cb_pl = ttk.Combobox(r1, textvariable=self.var_pl, state="readonly", width=22)
        self.cb_pl.pack(side="left")
        self.cb_pl.bind("<<ComboboxSelected>>", lambda e: self._open_playlist(self.var_pl.get()))
        ttk.Button(r1, text="New", command=self._new_playlist).pack(side="left", padx=2)
        ttk.Button(r1, text="Delete", command=self._delete_playlist).pack(side="left")
        ttk.Label(r1, text="Interval (s):").pack(side="left", padx=(10, 2))
        self.var_interval = tk.IntVar(value=15)
        sp = ttk.Spinbox(r1, from_=3, to=3600, textvariable=self.var_interval, width=6,
                         command=self._save_playlist)
        sp.pack(side="left")
        sp.bind("<FocusOut>", lambda e: self._save_playlist())

        r2 = ttk.Frame(plf)
        r2.pack(fill="both", expand=True, pady=4)
        self.lst = tk.Listbox(r2, selectmode="extended", activestyle="none")
        self.lst.pack(side="left", fill="both", expand=True)
        btns = ttk.Frame(r2)
        btns.pack(side="left", fill="y", padx=4)
        for t, c in (("▲ Up", lambda: self._move(-1)), ("▼ Down", lambda: self._move(1)),
                     ("Remove", self._remove)):
            ttk.Button(btns, text=t, command=c, width=9).pack(pady=2)

        r3 = ttk.Frame(plf)
        r3.pack(fill="x")
        self.btn_build = ttk.Button(r3, text="Build playlist for Jungle Leopard", command=self.build)
        self.btn_build.pack(side="left")
        ttk.Button(r3, text="Open folder", command=self._open_folder).pack(side="left", padx=4)
        ttk.Button(r3, text="Cancel", command=self.cancel.set).pack(side="left")

        bottom = ttk.Frame(self, padding=6)
        bottom.pack(fill="x")
        self.var_startup = tk.BooleanVar(value=winstartup.is_enabled())
        ttk.Checkbutton(bottom, text="Start with Windows (re-sync last playlist at logon)",
                        variable=self.var_startup, command=self._toggle_startup).pack(side="left")
        ttk.Label(bottom, text="Library:").pack(side="left", padx=(16, 2))
        self.var_lib = tk.StringVar(value=self.s["library_dir"])
        ttk.Entry(bottom, textvariable=self.var_lib, width=45, state="readonly").pack(side="left")
        ttk.Button(bottom, text="Change…", command=self._browse_lib).pack(side="left", padx=4)
        self.pb = ttk.Progressbar(bottom, length=220, maximum=1.0)
        self.pb.pack(side="right")
        self.var_status = tk.StringVar(value="Ready")
        ttk.Label(bottom, textvariable=self.var_status).pack(side="right", padx=8)

        self.txt = tk.Text(self, height=7, state="disabled", background="#fafafa")
        self.txt.pack(fill="x", padx=6, pady=(0, 6))

    # --------------------------------------------------------------- helpers
    def _log(self, msg):
        self.txt.configure(state="normal")
        self.txt.insert("end", msg + "\n")
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def _post(self, *msg):
        self.q.put(msg)

    def _poll(self):
        try:
            while True:
                m = self.q.get_nowait()
                kind = m[0]
                if kind == "log":
                    self._log(m[1])
                elif kind == "status":
                    self.var_status.set(m[1])
                elif kind == "progress":
                    self.pb["value"] = m[1]
                elif kind == "scanned":
                    self._on_scanned(m[1])
                elif kind == "probed":
                    self.info[m[1]] = m[2]
                    self._update_row(m[1])
                elif kind == "done":
                    self.busy = False
                    self.btn_build.state(["!disabled"])
                    if m[1]:
                        self._log(f"Playlist folder ready: {m[1]}")
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _bg(self, fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()

    # ---------------------------------------------------------------- scan
    def rescan(self):
        path = self.var_ws.get().strip()
        self.s["workshop_dir"] = path
        self.s.save()
        self.var_status.set("Scanning…")
        self._bg(lambda: self._post("scanned", scan_workshop(path)))

    def _on_scanned(self, items):
        self.items = items
        self.by_id = {w.id: w for w in items}
        counts = {}
        for w in items:
            counts[w.kind] = counts.get(w.kind, 0) + 1
        self._log("Scanned %d items: %s" % (len(items), ", ".join(f"{KIND_LABEL[k]} {v}" for k, v in counts.items())))
        self.var_status.set(f"{len(items)} wallpapers")
        self._refresh_tree()
        self._refresh_playlist_list()
        todo = [w for w in items if w.usable and w.kind in ("video", "gif")]
        self._bg(self._probe_all, todo)

    def _probe_all(self, todo):
        for w in todo:  # ffprobe reads headers only; results are cached
            self._post("probed", w.id, self.probe.probe(w.source))
        self.probe.save()

    def _visible(self, w):
        f = self.var_filter.get()
        q = self.var_search.get().strip().lower()
        if q and q not in w.title.lower() and q not in w.id:
            return False
        if f == "Everything":
            return True
        if f == "Unsupported":
            return not w.usable
        if f == "All usable":
            return w.usable
        return w.usable and KIND_LABEL[w.kind] == f

    def _row_values(self, w):
        info = self.info.get(w.id)
        res = f"{info['width']}x{info['height']}" if info else ""
        fps = f"{info['fps']:g}" if info else ""
        p = plan_for(w, info, self.s)
        text = {"link": "✔ no conversion", "transcode": "convert once", "image": "still",
                "skip": "✖"}[p.action] + f" – {p.reason}"
        anchor = self.s["anchors"].get(w.id)
        if anchor and p.action in ("transcode", "image"):
            text += f" [{anchor}]"
        tag = "off" if p.action == "skip" else ("link" if p.action == "link" else "")
        return (KIND_LABEL[w.kind], res, fps, human(w.size) if w.size else "", text), tag

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for w in self.items:
            if self._visible(w):
                vals, tag = self._row_values(w)
                self.tree.insert("", "end", iid=w.id, text=w.title, values=vals, tags=(tag,))

    def _update_row(self, wid):
        w = self.by_id.get(wid)
        if w and self.tree.exists(wid):
            vals, tag = self._row_values(w)
            self.tree.item(wid, values=vals, tags=(tag,))

    def _show_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        w = self.by_id[sel[-1]]
        self._loading = True
        self.var_anchor.set(self._pct(self.s.anchor_for(w.id)))
        self._loading = False
        info = self.info.get(w.id)
        d = [f"{w.title}  (#{w.id})", f"Type: {KIND_LABEL[w.kind]}   Size: {human(w.size)}"]
        if info:
            d.append(f"{info['codec']} {info['width']}x{info['height']} @ {info['fps']:g} fps, "
                     f"{info['duration']:.1f} s")
        d.append("Plan: " + plan_for(w, info, self.s).reason)
        if w.note:
            d.append("Note: " + w.note)
        if len(sel) > 1:
            d.append(f"({len(sel)} selected)")
        self.var_detail.set("\n".join(d))
        self._thumb(self._frame_for(w) or w.preview)

    def _frame_for(self, w):
        """A real frame of the video (preview.gif is usually a square crop, so its crop band lies)."""
        if w.kind not in ("video", "gif") or not (self.ffmpeg and w.source):
            return None
        out = os.path.join(app_dir(), "thumbs", f"{w.id}_l.jpg")
        if not os.path.isfile(out):
            os.makedirs(os.path.dirname(out), exist_ok=True)
            try:
                subprocess.run([self.ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
                                "-ss", "1", "-i", w.source, "-frames:v", "1", "-vf", "scale=1280:-2", out],
                               timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except (OSError, subprocess.SubprocessError):
                return None
        return out if os.path.isfile(out) else None

    @staticmethod
    def _pct(anchor):
        try:
            return float(anchor)
        except ValueError:
            return {"top": 0, "left": 0, "bottom": 100, "right": 100}.get(anchor, 50)

    def _thumb(self, path):
        self._prev_path = path
        if not (Image and path and os.path.isfile(path)):
            self.canvas.configure(image="", text="(no preview)" if Image else "(install Pillow for previews)")
            return
        try:
            with Image.open(path) as im:
                im.seek(0)
                im = im.convert("RGB")
                im.thumbnail(self._preview_box())
                w, h = im.size
                bh = min(h, round(w * self.s["target_h"] / self.s["target_w"]))
                if bh < h:  # darken what the crop will cut off
                    top = round((h - bh) * self.var_anchor.get() / 100)
                    box = (0, top, w, top + bh)
                    out = Image.blend(im, Image.new("RGB", im.size), 0.6)
                    out.paste(im.crop(box), box)
                    im = out
                self.thumb = ImageTk.PhotoImage(im)
            self.canvas.configure(image=self.thumb, text="", width=0, height=0)
        except Exception:  # broken preview files should not crash the UI
            self.canvas.configure(image="", text="(preview unreadable)")

    def _preview_box(self):
        """Largest preview that fits the right column (grows when the list is hidden)."""
        w = max(300, self.right.winfo_width() - 16)
        frac = 0.5 if str(self.left) in self.body.panes() else 0.62
        h = max(200, int(self.winfo_height() * frac))
        return w, h

    def _schedule_preview(self):
        """Re-render the preview after the right column was resized (debounced)."""
        if self._prev_job:
            self.after_cancel(self._prev_job)
        self._prev_job = self.after(120, self._redraw_preview)

    def _redraw_preview(self):
        self._prev_job = None
        self.lbl_detail.configure(wraplength=max(300, self.right.winfo_width() - 16))
        if self._prev_path:
            self._thumb(self._prev_path)

    def _toggle_list(self):
        if str(self.left) in self.body.panes():
            self.body.forget(self.left)
            self.btn_list.configure(text="▶ Show list")
        else:
            self.body.insert(0, self.left, weight=3)
            self.btn_list.configure(text="◀ Hide list")

    def _set_anchor(self):
        if self._loading:
            return
        a = str(round(self.var_anchor.get()))
        for wid in self.tree.selection():
            if float(a) == self._pct(self.s["crop_anchor"]):
                self.s["anchors"].pop(wid, None)
            else:
                self.s["anchors"][wid] = a
            self._update_row(wid)
        self._thumb(self._prev_path)
        self.s.save()

    # ------------------------------------------------------------ playlists
    def _refresh_playlist_list(self):
        names = self.lib.list_playlists()
        self.cb_pl["values"] = names
        self.lst.delete(0, "end")
        if self.playlist:
            for wid in self.playlist["items"]:
                w = self.by_id.get(wid)
                self.lst.insert("end", f"{KIND_LABEL[w.kind]:<13} {w.title}" if w else f"(missing) {wid}")

    def _load_playlists(self, name):
        names = self.lib.list_playlists()
        if not names:
            self.playlist = {"name": "Default", "interval": 15, "items": []}
            self.lib.save_playlist(self.playlist)
            name = "Default"
        self._open_playlist(name if name in self.lib.list_playlists() else self.lib.list_playlists()[0])

    def _open_playlist(self, name):
        self.playlist = self.lib.load_playlist(name)
        self.var_pl.set(name)
        self.var_interval.set(self.playlist["interval"])
        self.s["last_playlist"] = name   # remember the previous playlist
        self.s.save()
        self._refresh_playlist_list()

    def _save_playlist(self):
        if not self.playlist:
            return
        try:
            self.playlist["interval"] = max(3, int(self.var_interval.get()))
        except (tk.TclError, ValueError):
            pass
        self.lib.save_playlist(self.playlist)

    def _new_playlist(self):
        name = simpledialog.askstring("New playlist", "Playlist name:", parent=self)
        if not name:
            return
        name = safe_playlist_name(name)
        self.playlist = {"name": name, "interval": 15, "items": []}
        self.lib.save_playlist(self.playlist)
        self._open_playlist(name)

    def _delete_playlist(self):
        if self.playlist and messagebox.askyesno(
                "Delete playlist", f"Delete playlist '{self.playlist['name']}' and its folder?\n"
                                   "(Converted media in the library is kept.)"):
            self.lib.delete_playlist(self.playlist["name"])
            self.playlist = None
            self._load_playlists(None)

    def add_selected(self):
        if not self.playlist:
            return
        added = 0
        for wid in self.tree.selection():
            w = self.by_id[wid]
            if w.usable and wid not in self.playlist["items"]:
                self.playlist["items"].append(wid)
                added += 1
        self._save_playlist()
        self._refresh_playlist_list()
        self.var_status.set(f"Added {added}")

    def delete_selected(self):
        """Send the selected wallpaper folders to the Recycle Bin (frees the workshop folder)."""
        ws = self.s["workshop_dir"]
        targets = [self.by_id[i] for i in self.tree.selection()
                   if is_workshop_item(ws, self.by_id[i].folder, i)]
        if not targets or self.busy:
            return
        sizes = {w.id: folder_size(w.folder) for w in targets}
        names = "\n".join(f"• {w.title}  (#{w.id}, {human(sizes[w.id])})" for w in targets[:12])
        if len(targets) > 12:
            names += f"\n… and {len(targets) - 12} more"
        if not messagebox.askyesno(
                "Delete wallpaper folders",
                f"Move {len(targets)} folder(s) ({human(sum(sizes.values()))}) from the workshop folder "
                f"to the Recycle Bin?\n\n{names}\n\n"
                "If the wallpaper is still subscribed on Steam, Steam may download it again - "
                "unsubscribe in the Workshop to remove it for good.\n"
                "Converted copies in the library are kept.", icon="warning"):
            return
        done = 0
        for w in targets:
            if recycle(w.folder):
                done += 1
                self.s["anchors"].pop(w.id, None)
                if self.playlist and w.id in self.playlist["items"]:
                    self.playlist["items"].remove(w.id)
                self._log(f"Deleted {w.title} (#{w.id}) -> Recycle Bin")
            else:
                self._log(f"Could not delete {w.folder} (permission denied or in use?)")
        self._save_playlist()
        self.s.save()
        self.var_status.set(f"Deleted {done}/{len(targets)}")
        self.rescan()

    def _move(self, d):
        sel = list(self.lst.curselection())
        items = self.playlist["items"]
        order = sel if d < 0 else reversed(sel)
        for i in order:
            j = i + d
            if 0 <= j < len(items):
                items[i], items[j] = items[j], items[i]
        self._save_playlist()
        self._refresh_playlist_list()
        for i in sel:
            if 0 <= i + d < len(items):
                self.lst.selection_set(i + d)

    def _remove(self):
        for i in sorted(self.lst.curselection(), reverse=True):
            del self.playlist["items"][i]
        self._save_playlist()
        self._refresh_playlist_list()

    # ---------------------------------------------------------------- build
    def build(self):
        if self.busy or not self.playlist or not self.playlist["items"]:
            return
        if not self.ffmpeg:
            messagebox.showerror("ffmpeg missing", "ffmpeg was not found (Jungle Leopard's copy or PATH).")
            return
        self._save_playlist()
        self.busy = True
        self.cancel.clear()
        self.btn_build.state(["disabled"])
        pl = dict(self.playlist, items=list(self.playlist["items"]))

        def work():
            def prog(i, n, f):
                self._post("progress", (i + f) / max(n, 1))
                self._post("status", f"Item {min(i + 1, n)}/{n}")
            folder, ok, failed = build_playlist(pl, self.by_id, self.s, self.lib, self.probe, self.ffmpeg,
                                                lambda m: self._post("log", m), prog, self.cancel)
            self._post("status", f"{ok} ready, {failed} failed")
            self._post("done", folder)
        self._bg(work)

    def _open_folder(self):
        if not self.playlist:
            return
        folder = os.path.join(self.lib.playlist_dir, safe_playlist_name(self.playlist["name"]))
        if not os.path.isdir(folder):
            folder = self.lib.root
        os.makedirs(folder, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606
        else:
            subprocess.Popen(["xdg-open", folder])

    # ------------------------------------------------------------- settings
    def _browse_ws(self):
        d = filedialog.askdirectory(initialdir=self.var_ws.get())
        if d:
            self.var_ws.set(d)
            self.rescan()

    def _browse_lib(self):
        d = filedialog.askdirectory(initialdir=self.s["library_dir"])
        if d:
            self.s["library_dir"] = d
            self.s.save()
            self.var_lib.set(d)
            self.lib = Library(d)
            self.playlist = None
            self._load_playlists(None)

    def _toggle_startup(self):
        ok = winstartup.set_enabled(self.var_startup.get(), os.path.join(ROOT, "app.py"))
        if not ok:
            self._log("Start with Windows is only available on Windows.")
            self.var_startup.set(False)
        self.s["start_with_windows"] = self.var_startup.get()
        self.s.save()

    def _close(self):
        self.cancel.set()
        self._save_playlist()
        self.probe.save()
        self.s.save()
        self.destroy()


def run_gui() -> None:
    App().mainloop()
