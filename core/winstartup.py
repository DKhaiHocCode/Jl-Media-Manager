"""Optional start-with-Windows via the per-user Run key (no admin rights needed)."""
from __future__ import annotations

import os
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "JLMediaManager"


def _command(script: str) -> str:
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        pyw = exe[:-10] + "pythonw.exe"
        if os.path.isfile(pyw):
            exe = pyw  # no console window at logon
    # --sync: rescan, convert anything new in the last playlist, then exit.
    return f'"{exe}" "{os.path.abspath(script)}" --sync'


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool, script: str) -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE, 0, winreg.REG_SZ, _command(script))
        else:
            try:
                winreg.DeleteValue(key, VALUE)
            except FileNotFoundError:
                pass
    return True
