"""Send wallpaper folders to the Windows Recycle Bin (recoverable), with a path safety check."""
from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes

_FO_DELETE = 3
_FLAGS = 0x0040 | 0x0010 | 0x0004 | 0x0400  # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI


class _SHFILEOPSTRUCT(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort),
                ("fAnyOperationsAborted", wintypes.BOOL), ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", wintypes.LPCWSTR)]


def folder_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def is_workshop_item(workshop_dir: str, folder: str, wallpaper_id: str) -> bool:
    """Only a direct child of the workshop folder, named by its id, may be deleted."""
    root = os.path.normcase(os.path.realpath(workshop_dir))
    target = os.path.normcase(os.path.realpath(folder))
    return (os.path.isdir(folder) and os.path.dirname(target) == root
            and os.path.basename(target) == wallpaper_id)


def recycle(folder: str) -> bool:
    """Move a folder to the Recycle Bin. Returns True on success."""
    if sys.platform != "win32":
        return False
    op = _SHFILEOPSTRUCT(None, _FO_DELETE, os.path.abspath(folder) + "\0\0", None, _FLAGS, False, None, None)
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0 and not op.fAnyOperationsAborted
