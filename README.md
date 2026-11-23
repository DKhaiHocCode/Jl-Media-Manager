# JL Media Manager

Turns a Wallpaper Engine workshop (`steamapps\workshop\content\431960`) into a library sized for the
**Jungle Leopard 9.16" bar** (`D215-NOR-FL7707N-9.16inch-hor`, 1920×462), and builds playlist folders that
**Jungle Leopard Display** plays with its own *Media → Slideshow* feature.

Jungle Leopard Display stays in charge of the screen (USB link, auto-start, sensor widgets). This tool never
modifies that app, never talks to the device and does not use the COM3 protocol. It only prepares files.

## Requirements

- Windows, Python 3.9+ (tkinter is included with the python.org installer)
- Optional: `pip install -r requirements.txt` (Pillow, for the preview image)
- ffmpeg/ffprobe: reuses the copies bundled with Jungle Leopard Display (run only, never changed).
  If that app is missing, falls back to any ffmpeg on `PATH`.

## Run

```
python app.py            # desktop app (or double-click "JL Media Manager.bat")
python app.py --sync     # headless: rescan and rebuild the last playlist (used at logon)
```

## Usage

1. **Rescan** lists every workshop item and what will happen to it:
   - **✔ no conversion**: already H.264, right shape, ≤ 60 fps. Hard-linked, no copy, no re-encode.
   - **convert once**: e.g. 4K / 120 fps / 16:9 video. Cropped to a 1920×462 band, ≤ 30 fps, H.264, no audio.
     The result is kept in `media\` and never converted again unless the source or settings change.
   - **still**: Scene wallpapers (`scene.pkg` only renders inside Wallpaper Engine) use their preview image.
   - **✖**: web/application wallpapers can't become media files (*Show → Unsupported* lists them).
2. Select a wallpaper. The preview shows a real video frame with the crop band highlighted.
   Drag the **crop slider** (0 = top, 100 = bottom) until the band covers what you want.
   Use **◀ Hide list** to collapse the wallpaper list and give the preview the full width.
   **🗑 Delete folder…** moves the selected wallpaper folders (any type, including unsupported ones) to the
   Recycle Bin after a confirmation that lists names and sizes. Use it to clear leftovers of wallpapers that
   are gone from Wallpaper Engine. It only touches direct sub-folders of the workshop folder, and converted
   copies in the library are kept. If a wallpaper is still subscribed on Steam it may be downloaded again.
   **Theme widgets…** drops ready-made CPU / GPU / disk widgets (number, arc, bar) into one of your
   Jungle Leopard themes so you don't have to design them; then drag, resize and recolour them in
   Jungle Leopard's Theme Editor. Quit Jungle Leopard first; a backup of the theme is saved to
   `%APPDATA%\JLMediaManager\theme_backups\`.
3. Select wallpapers (Ctrl/Shift-click) → **Add selected to playlist** (or double-click).
4. Set **Interval**, then **Build playlist for Jungle Leopard**. Conversions run one at a time at
   below-normal priority on half your CPU cores.
5. **Open folder** — it holds numbered files plus `_HOW_TO_USE.txt`. In Jungle Leopard Display:
   Theme Editor → Create Theme (1920×462) → Add Component → **Media**, full-screen, Cover →
   Load Method **Local Upload** → select all files → turn on **Slideshow**, set **Slide Interval** → save and apply.

The last opened playlist is remembered. **Start with Windows** adds a per-user Run entry (`app.py --sync`)
that converts anything new in the last playlist at logon; its log is `%APPDATA%\JLMediaManager\sync.log`.

## Where things go

| Path | What |
|---|---|
| `%USERPROFILE%\Videos\JL Library\media\` | converted videos/stills (changeable in the app) |
| `...\JL Library\playlists\<name>\` | folder you pick files from in Jungle Leopard |
| `...\JL Library\playlists\<name>.json` | playlist definition (items, interval) |
| `%APPDATA%\JLMediaManager\` | settings, ffprobe cache, preview frames (`thumbs\`), sync log |

Advanced options live in `%APPDATA%\JLMediaManager\settings.json`: `max_fps` (30), `crf` (23),
`max_seconds` (0 = full length), `crop_mode` (`precrop` or `jl` to let Jungle Leopard scale),
`gif_mode` (`mp4` or `copy`), `hwaccel`, and `anchors` (per-wallpaper crop position, 0–100).

## Project layout

```
app.py              entry point (GUI, or --sync)
gui/main_window.py  tkinter window
core/scanner.py     reads the workshop folder, classifies items
core/converter.py   ffprobe/ffmpeg: conversion plan, crop filter, commands
core/library.py     converted-media cache and playlist folders
core/trash.py       Recycle Bin delete with path safety check
core/themes.py      add sensor widgets to Jungle Leopard theme JSON
gui/theme_dialog.py widget picker window
core/jobs.py        build_playlist (shared by GUI and --sync)
core/sync.py        headless logon sync
core/settings.py    settings file and app data folder
core/winstartup.py  "Start with Windows" Run-key entry
```


