"""Dialog: drop ready-made CPU/GPU/disk widgets into a Jungle Leopard theme."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from core import themes

KIND_NAMES = {"Number": "data", "Arc": "arc", "Bar": "progress"}


class ThemeDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Add widgets to a Jungle Leopard theme")
        self.geometry("620x520")
        self.transient(parent)
        self.themes = []
        self.pending: list[tuple[str, str]] = []

        ttk.Label(self, text="1. Theme (close Jungle Leopard Display first):").pack(anchor="w", padx=8, pady=(8, 2))
        self.lst = tk.Listbox(self, height=7, exportselection=False)
        self.lst.pack(fill="x", padx=8)

        ttk.Label(self, text="2. Widget:").pack(anchor="w", padx=8, pady=(8, 2))
        row = ttk.Frame(self)
        row.pack(fill="x", padx=8)
        self.var_kind = tk.StringVar(value="Number")
        ttk.Combobox(row, textvariable=self.var_kind, values=list(KIND_NAMES), state="readonly",
                     width=10).pack(side="left")
        self.labels = {v[0]: k for k, v in themes.SOURCES.items()}
        self.var_src = tk.StringVar(value="CPU temperature")
        ttk.Combobox(row, textvariable=self.var_src, values=list(self.labels), state="readonly",
                     width=24).pack(side="left", padx=6)
        ttk.Button(row, text="Add to list", command=self._queue).pack(side="left")

        ttk.Label(self, text="3. Will be added:").pack(anchor="w", padx=8, pady=(8, 2))
        self.pend = tk.Listbox(self, height=8)
        self.pend.pack(fill="both", expand=True, padx=8)
        row2 = ttk.Frame(self)
        row2.pack(fill="x", padx=8, pady=8)
        ttk.Button(row2, text="Remove", command=self._unqueue).pack(side="left")
        ttk.Button(row2, text="Write to theme", command=self._write).pack(side="right")
        ttk.Label(self, wraplength=590, foreground="#555", text=(
            "New widgets appear near the middle of the screen. Open the theme in Jungle Leopard's Theme "
            "Editor to drag, resize and recolour them. A backup of the theme is kept in "
            "%APPDATA%/JLMediaManager/theme_backups.")).pack(anchor="w", padx=8, pady=(0, 8))
        self._load()

    def _load(self):
        self.themes = themes.list_themes()
        self.lst.delete(0, "end")
        for t in self.themes:
            self.lst.insert("end", f"{t['label']}   ({t['width']}x{t['height']}, {t['widgets']} widgets)")
        for i, t in enumerate(self.themes):  # preselect the first 1920x462 theme
            if (t["width"], t["height"]) == (1920, 462):
                self.lst.selection_set(i)
                break

    def _queue(self):
        kind, src = KIND_NAMES[self.var_kind.get()], self.labels[self.var_src.get()]
        if kind in ("arc", "progress") and themes.SOURCES[src][1] is None:
            messagebox.showinfo("Not for this widget", "Names and time can only be shown as a Number.", parent=self)
            return
        self.pending.append((kind, src))
        self.pend.insert("end", f"{self.var_kind.get()}: {self.var_src.get()}")

    def _unqueue(self):
        for i in reversed(self.pend.curselection()):
            self.pend.delete(i)
            del self.pending[i]

    def _write(self):
        sel = self.lst.curselection()
        if not sel or not self.pending:
            messagebox.showinfo("Nothing to do", "Pick a theme and add at least one widget.", parent=self)
            return
        if themes.jl_running():
            messagebox.showwarning("Close Jungle Leopard", "Jungle Leopard Display is running and would overwrite "
                                   "the change. Quit it (also from the tray), then try again.", parent=self)
            return
        t = self.themes[sel[0]]
        backup = themes.add_widgets(t["path"], self.pending)
        messagebox.showinfo("Done", f"Added {len(self.pending)} widget(s) to '{t['label']}'.\n"
                            f"Backup: {backup}", parent=self)
        self.pending.clear()
        self.pend.delete(0, "end")
        self._load()
