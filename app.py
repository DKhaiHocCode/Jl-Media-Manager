"""JL Media Manager - Wallpaper Engine workshop -> Jungle Leopard 9.16" LCD.

    python app.py           open the desktop utility
    python app.py --sync    headless: rescan + rebuild the last playlist (used at logon)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    if "--sync" in sys.argv:
        from core.sync import run_sync
        sys.exit(run_sync())
    from gui.main_window import run_gui
    run_gui()
