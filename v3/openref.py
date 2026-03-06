import os
import re
import sys
import json
import pickle
import random
import urllib.parse
import webbrowser
import threading
import time
import shutil
from datetime import datetime, date, timedelta
from collections import Counter
import random_prompt as _prompts
import compress_images as _compress

# map of subcommand -> (function_name, display_label)
_PROMPT_CMDS: dict[str, tuple[str, str]] = {
    "daily":    ("complete_daily_plan",                    "Daily plan"),
    "pose":     ("complete_pose_prompt",                   "Pose"),
    "anatomy":  ("complete_anatomy_prompt",                "Anatomy"),
    "specific": ("complete_specific_anatomy_prompt",       "Specific anatomy"),
    "motion":   ("complete_anatomy_motion_prompt",         "Anatomy motion"),
    "face":     ("complete_face_prompt",                   "Face"),
    "facepart": ("complete_face_part_prompt",              "Face part"),
    "hands":    ("complete_hand_prompt",                   "Hands"),
    "feet":     ("complete_feet_prompt",                   "Feet"),
    "exercise": ("complete_exercise_prompt",               "Exercise"),
    "daily_ex": ("complete_daily_exercise_prompt",         "Daily exercise"),
    "category": ("complete_category_prompt",               "Category"),
    "random":   ("random_complete_prompt",                 "Random prompt"),
}

# ── Fallback constants (used when settings.json is absent or incomplete) ───────

_FALLBACK_FIREFOX_PATH          = r"C:\Program Files\Mozilla Firefox\firefox.exe"
_FALLBACK_IMAGE_EXTENSIONS      = {".jpg", ".jpeg", ".png", ".webp", ".tiff"}
_FALLBACK_MEM_TIME              = 30    # seconds
_FALLBACK_SEARCH_RESULTS        = 20    # max results returned by the search command
_FALLBACK_COMPRESS_QUALITY      = 85    # default JPEG quality for compress commands
_FALLBACK_SEMI_RAND_PROBABILITY = 0.2   # chance of reusing an already-seen subfolder
_FALLBACK_SEMI_RAND_MAX_TRIES   = 10    # max picks before falling back in semi-random

# Module-level globals — overwritten by apply_settings() at startup
FIREFOX_PATH        = _FALLBACK_FIREFOX_PATH
IMAGE_EXTENSIONS    = _FALLBACK_IMAGE_EXTENSIONS
SEARCH_MAX_RESULTS  = _FALLBACK_SEARCH_RESULTS

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PATHS_FILE  = os.path.join(_SCRIPT_DIR, "ref_paths.json")
CACHE_FILE  = os.path.join(_SCRIPT_DIR, "ref_cache.pkl")
# cache schema: dict[str, list[str]]  →  { folder_path: [img_path, ...] }
LOG_FILE    = os.path.join(_SCRIPT_DIR, "ref_log.tsv")

# Temp HTML file written when grayscale mode is active
_GRAYSCALE_HTML = os.path.join(_SCRIPT_DIR, "_grayscale_tmp.html")

REGISTERED_BROWSERS: set = set()

# ── Settings loader ────────────────────────────────────────────────────────────

def load_settings(settings_path: str | None = None) -> dict:
    """
    Load a settings JSON file.
    Checks the explicit path first, then settings.json next to the script.
    Returns an empty dict (all fallbacks apply) if no file is found.
    """
    candidates: list[str] = []
    if settings_path:
        candidates.append(settings_path)
    candidates.append(os.path.join(_SCRIPT_DIR, "settings.json"))

    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"  [!] Could not read settings file '{path}': {e}")
            break   # stop after the first candidate that exists (even if unreadable)

    return {}


def apply_settings(settings: dict):
    """Write settings values into module-level globals."""
    global FIREFOX_PATH, IMAGE_EXTENSIONS, SEARCH_MAX_RESULTS
    FIREFOX_PATH = settings.get("firefox_path", _FALLBACK_FIREFOX_PATH)
    raw_ext = settings.get("image_extensions")
    IMAGE_EXTENSIONS = (
        {e.lower() for e in raw_ext}
        if isinstance(raw_ext, list)
        else _FALLBACK_IMAGE_EXTENSIONS
    )
    SEARCH_MAX_RESULTS = int(settings.get("search_max_results", _FALLBACK_SEARCH_RESULTS))


def _resolve_settings_path(settings_arg: str | None) -> str:
    """Return the settings file path that will be used for saving."""
    if settings_arg and os.path.exists(settings_arg):
        return settings_arg
    return os.path.join(_SCRIPT_DIR, "settings.json")


def save_settings(settings: dict, settings_file: str):
    """Persist the settings dict back to disk."""
    try:
        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"  [!] Could not save settings to '{settings_file}': {e}")


# ── Cache helpers ──────────────────────────────────────────────────────────────

def load_cache() -> dict[str, list[str]]:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "rb") as f:
                data = pickle.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def save_cache(cache: dict[str, list[str]]):
    with open(CACHE_FILE, "wb") as f:
        pickle.dump(cache, f)


# ── Saved-paths persistence ────────────────────────────────────────────────────

def load_saved_paths() -> tuple[list[str], dict[str, str], dict]:
    """
    Returns (paths, keys, prefs) from the current JSON format.
    File format:
      {
        "folders": [{"path": "...", "key": "xx"}, {"path": "..."}],
        "default_folder_index": 0,
        "default_save_index":   0
      }
    """
    default_prefs = {
        "default_folder_index": 0,
        "default_save_index":   0,
    }

    if not os.path.exists(PATHS_FILE):
        return [], {}, default_prefs

    try:
        with open(PATHS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict) and "folders" in data:
            paths = []
            keys = {}

            for entry in data["folders"]:
                path = str(entry.get("path", ""))
                if not path:
                    continue

                paths.append(path)
                key = entry.get("key", "")
                if key:
                    keys[path] = str(key)

            # Map preferences, falling back to defaults if keys are missing
            prefs = {
                k: int(data.get(k, v))
                for k, v in default_prefs.items()
            }

            return paths, keys, prefs

    except (json.JSONDecodeError, KeyError, ValueError):
        # Silently fail on corrupt JSON or type mismatches
        pass

    return [], {}, default_prefs


def save_paths(paths: list[str], keys: dict[str, str], prefs: dict):
    folders = []
    for p in paths:
        entry: dict = {"path": p}
        k = keys.get(p, "")
        if k:
            entry["key"] = k
        folders.append(entry)
    data: dict = {
        "folders":              folders,
        "default_folder_index": prefs.get("default_folder_index", 0),
        "default_save_index":   prefs.get("default_save_index", 0),
    }
    with open(PATHS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Key helpers ────────────────────────────────────────────────────────────────


def _path_for_key(key: str, paths: list[str], keys: dict[str, str]) -> str | None:
    key_lower = key.lower()
    for path in paths:
        if keys.get(path, "").lower() == key_lower:
            return path
    return None


def _key_in_use(key: str, keys: dict[str, str]) -> bool:
    key_lower = key.lower()
    return any(v.lower() == key_lower for v in keys.values())


def _resolve_folder_arg(arg: str, paths: list[str], keys: dict[str, str]) -> int:
    """
    Resolve a folder argument that may be a 1-based number or a key string.
    Returns a 0-based index, or -1 if not found.
    """
    if arg.isdigit():
        return int(arg) - 1
    p = _path_for_key(arg, paths, keys)
    return paths.index(p) if p is not None else -1


def _bad_folder_arg(arg: str) -> str:
    """Return an appropriate error message for an unresolved folder argument."""
    if arg.isdigit():
        return f"  [!] Number out of range."
    return f"  [!] No folder with key '{arg}'."


# ── Helpers ────────────────────────────────────────────────────────────────────

def time_string_to_seconds(time_str: str) -> int:
    pattern = (
        r'(?:(\d+)(?:h|hrs|hour|hora|horas|hours))'
        r'|(?:(\d+)(?:m|min|minute|minuto|minutos|minutes))'
        r'|(?:(\d+)(?:s|sec|seg|second|seconds|segundo|segundos))'
    )
    total = 0
    for hours, minutes, seconds in re.findall(pattern, time_str):
        if hours:   total += int(hours)   * 3600
        if minutes: total += int(minutes) * 60
        if seconds: total += int(seconds)
    return total


def scan_folder(folder: str) -> list[str]:
    """Recursively scan folder and return all image paths."""
    images = []
    for root, _, files in os.walk(folder):
        for f in files:
            if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS:
                images.append(os.path.join(root, f))
    return images


def _ensure_firefox_registered():
    """Register Firefox with the webbrowser module if not already done."""
    if "firefox" not in REGISTERED_BROWSERS:
        webbrowser.register(
            "firefox", None,
            webbrowser.BackgroundBrowser(FIREFOX_PATH)
        )
        REGISTERED_BROWSERS.add("firefox")


def open_path_in_firefox(path: str):
    if not os.path.exists(path):
        print(f"  [!] File not found: {path}")
        return
    img_url = "file:///" + urllib.parse.quote(os.path.abspath(path).replace("\\", "/"))
    _ensure_firefox_registered()
    webbrowser.get("firefox").open(img_url)


def open_path_with_css(path: str, grayscale: bool, flip: str | None):
    """
    Open *path* in Firefox via a temporary HTML wrapper, applying any
    combination of CSS grayscale and/or flip transforms.

    flip  – None | "h" (scaleX(-1), mirror left-right)
           |       "v" (scaleY(-1), mirror up-down)

    Falls back to plain Firefox if the temp file can't be written.
    The temp file (_GRAYSCALE_HTML) is overwritten on every call.
    """
    if not os.path.exists(path):
        print(f"  [!] File not found: {path}")
        return

    img_url = "file:///" + urllib.parse.quote(os.path.abspath(path).replace("\\", "/"))

    css_filter    = "grayscale(1)" if grayscale else ""
    css_transform = {"h": "scaleX(-1)", "v": "scaleY(-1)"}.get(flip or "", "")

    filter_rule    = f"filter: {css_filter};"       if css_filter    else ""
    transform_rule = f"transform: {css_transform};" if css_transform else ""

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{
    width: 100%; height: 100%;
    background: #222222;
    overflow: hidden;
  }}
  body {{
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  img {{
    max-width: 100vw;
    max-height: 100vh;
    object-fit: contain;
    {filter_rule}
    {transform_rule}
  }}
</style>
</head>
<body>
<img src="{img_url}">
</body>
</html>"""

    try:
        with open(_GRAYSCALE_HTML, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception as e:
        print(f"  [!] Could not write HTML wrapper: {e}")
        open_path_in_firefox(path)
        return

    html_url = "file:///" + urllib.parse.quote(_GRAYSCALE_HTML.replace("\\", "/"))
    _ensure_firefox_registered()
    webbrowser.get("firefox").open(html_url)


def open_image(path: str, grayscale: bool, flip: str | None = None):
    """
    Open an image in Firefox, applying grayscale and/or flip as needed.
    Uses the HTML wrapper whenever either effect is active; raw Firefox otherwise.
    """
    if grayscale or flip:
        open_path_with_css(path, grayscale, flip)
    else:
        open_path_in_firefox(path)


# ── Palette extraction ─────────────────────────────────────────────────────────

def _extract_palette(path: str, n_colors: int = 6) -> list[tuple[int, int, int]]:
    """
    Return *n_colors* dominant RGB colours from *path* using k-means clustering.
    Sorts result from darkest to lightest (by perceived luminance).
    Returns an empty list on any error.
    """
    try:
        from PIL import Image
        import numpy as np
        from sklearn.cluster import KMeans

        img = Image.open(path).convert("RGB")
        # Downsample for speed — 200×200 is plenty for colour extraction
        img.thumbnail((200, 200), Image.LANCZOS)
        pixels = np.array(img).reshape(-1, 3).astype(float)

        km = KMeans(n_clusters=n_colors, n_init=8, random_state=42)
        km.fit(pixels)

        # Weight each cluster by how many pixels it captured
        labels   = km.labels_
        centers  = km.cluster_centers_
        counts   = np.bincount(labels, minlength=n_colors)
        order    = np.argsort(-counts)          # most-common first
        colors   = [tuple(int(c) for c in centers[i]) for i in order]

        # Re-sort by perceived luminance (dark → light) for a clean strip
        def _lum(rgb):
            r, g, b = [x / 255 for x in rgb]
            return 0.2126 * r + 0.7152 * g + 0.0722 * b

        colors.sort(key=_lum)
        return colors

    except Exception as e:
        print(f"  [!] Palette extraction failed: {e}")
        return []


def open_palette(path: str, n_colors: int, grayscale: bool):
    """
    Open *path* in Firefox with a vertical colour-swatch panel on the right.
    Each swatch shows the hex code and RGB values.
    Respects grayscale mode (applies the CSS filter to the image only).
    """
    if not os.path.exists(path):
        print(f"  [!] File not found: {path}")
        return

    kind = "values" if grayscale else "colours"
    name = os.path.basename(path)
    print(f"  🎨 Palette ({n_colors} {kind}) — {name} … ", end="", flush=True)
    colors = _extract_palette(path, n_colors)
    if not colors:
        print("failed — opening image normally.")
        open_image(path, grayscale)
        return
    print("done.")

    img_url = "file:///" + urllib.parse.quote(os.path.abspath(path).replace("\\", "/"))
    filter_rule = "filter: grayscale(1);" if grayscale else ""

    # Build swatch HTML blocks
    # In grayscale mode: convert each colour to its luminance value and show
    # L XX% labels instead — turns the palette into a value-reading tool.
    swatch_items = []
    for r, g, b in colors:
        lum = 0.2126 * r/255 + 0.7152 * g/255 + 0.0722 * b/255
        if grayscale:
            v         = int(round(lum * 255))
            bg_col    = f"rgb({v},{v},{v})"
            lum_pct   = int(round(lum * 100))
            txt_color = "#111" if lum > 0.45 else "#eee"
            swatch_items.append(f"""
        <div class="swatch" style="background:{bg_col};">
          <span class="label" style="color:{txt_color};">
            <strong>L&nbsp;{lum_pct}%</strong>
          </span>
        </div>""")
        else:
            hex_col   = f"#{r:02X}{g:02X}{b:02X}"
            txt_color = "#111" if lum > 0.45 else "#eee"
            swatch_items.append(f"""
        <div class="swatch" style="background:{hex_col};">
          <span class="label" style="color:{txt_color};">
            <strong>{hex_col}</strong><br>
            <small>{r}&nbsp;{g}&nbsp;{b}</small>
          </span>
        </div>""")

    swatches_html = "\n".join(swatch_items)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{
    width: 100%; height: 100%;
    background: #222222;
    overflow: hidden;
    display: flex;
    flex-direction: row;
    align-items: stretch;
  }}
  #img-pane {{
    flex: 1 1 auto;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    min-width: 0;
  }}
  #img-pane img {{
    max-width: 100%;
    max-height: 100vh;
    object-fit: contain;
    {filter_rule}
  }}
  #palette {{
    flex: 0 0 110px;
    display: flex;
    flex-direction: column;
    border-left: 2px solid #111;
  }}
  .swatch {{
    flex: 1 1 0;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    cursor: default;
    transition: flex 0.15s;
  }}
  .swatch:hover {{ flex: 2 1 0; }}
  .label {{
    font-family: monospace;
    font-size: 11px;
    line-height: 1.5;
    text-shadow: 0 1px 2px rgba(0,0,0,0.4);
    pointer-events: none;
  }}
</style>
</head>
<body>
  <div id="img-pane">
    <img src="{img_url}">
  </div>
  <div id="palette">
    {swatches_html}
  </div>
</body>
</html>"""

    try:
        with open(_GRAYSCALE_HTML, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception as e:
        print(f"  [!] Could not write palette HTML: {e}")
        open_image(path, grayscale)
        return

    html_url = "file:///" + urllib.parse.quote(_GRAYSCALE_HTML.replace("\\", "/"))
    _ensure_firefox_registered()
    webbrowser.get("firefox").open(html_url)


# ── Grid overlay ───────────────────────────────────────────────────────────────

def open_grid(path: str, divisions: int, grayscale: bool, flip: str | None):
    """
    Open *path* in Firefox with an SVG rule-of-thirds (or N×N) grid overlay.
    *divisions* = number of rows/columns (default 3 = rule of thirds).
    Respects grayscale and flip.
    """
    if not os.path.exists(path):
        print(f"  [!] File not found: {path}")
        return

    img_url = "file:///" + urllib.parse.quote(os.path.abspath(path).replace("\\", "/"))

    filter_rule    = "filter: grayscale(1);"       if grayscale else ""
    _flip_map      = {'h': 'scaleX(-1)', 'v': 'scaleY(-1)'}
    transform_rule = f"transform: {_flip_map.get(flip or '', '')};" if flip else ""

    # Build SVG lines as percentages so they scale with the image
    step    = 100 / divisions
    lines   = []
    for i in range(1, divisions):
        pct = step * i
        # vertical line
        lines.append(
            f'<line x1="{pct}%" y1="0" x2="{pct}%" y2="100%" '
            f'stroke="rgba(255,255,255,0.55)" stroke-width="1"/>'
        )
        lines.append(
            f'<line x1="{pct}%" y1="0" x2="{pct}%" y2="100%" '
            f'stroke="rgba(0,0,0,0.35)" stroke-width="1" stroke-dasharray="4,4"/>'
        )
        # horizontal line
        lines.append(
            f'<line x1="0" y1="{pct}%" x2="100%" y2="{pct}%" '
            f'stroke="rgba(255,255,255,0.55)" stroke-width="1"/>'
        )
        lines.append(
            f'<line x1="0" y1="{pct}%" x2="100%" y2="{pct}%" '
            f'stroke="rgba(0,0,0,0.35)" stroke-width="1" stroke-dasharray="4,4"/>'
        )

    svg_content   = "\n    ".join(lines)
    grid_label    = "Rule of Thirds" if divisions == 3 else f"{divisions}×{divisions} Grid"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{
    width: 100%; height: 100%;
    background: #222222;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  #frame {{
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    max-width: 100vw;
    max-height: 100vh;
  }}
  #frame img {{
    display: block;
    max-width: 100vw;
    max-height: 100vh;
    object-fit: contain;
    {filter_rule}
    {transform_rule}
  }}
  #grid-svg {{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
  }}
  #grid-label {{
    position: fixed;
    bottom: 8px;
    right: 12px;
    font-family: monospace;
    font-size: 11px;
    color: rgba(255,255,255,0.5);
    text-shadow: 0 1px 3px #000;
    pointer-events: none;
  }}
</style>
</head>
<body>
  <div id="frame">
    <img src="{img_url}">
    <svg id="grid-svg" xmlns="http://www.w3.org/2000/svg">
    {svg_content}
    </svg>
  </div>
  <div id="grid-label">{grid_label}</div>
</body>
</html>"""

    try:
        with open(_GRAYSCALE_HTML, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception as e:
        print(f"  [!] Could not write grid HTML: {e}")
        open_image(path, grayscale, flip)
        return

    html_url = "file:///" + urllib.parse.quote(_GRAYSCALE_HTML.replace("\\", "/"))
    _ensure_firefox_registered()
    webbrowser.get("firefox").open(html_url)


def open_black_tab():
    # Always ensure Firefox is registered before opening a tab — this can be
    # called from background threads before any image has been shown.
    _ensure_firefox_registered()
    webbrowser.get("firefox").open("about:newtab", new=2)


# ── Session log ───────────────────────────────────────────────────────────────

def log_entry(path: str, opening_mode: str, display_mode: str, duration: int):
    """
    Append one line to the session log.
    Format (pipe-separated):  ISO-timestamp | path | opening_mode | display_mode | duration_s
    This is a fire-and-forget call — any error is silently ignored so it never
    slows down or disrupts normal use.
    """
    try:
        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{ts}|{path}|{opening_mode}|{display_mode}|{duration}\n")
    except Exception:
        pass


def _read_log() -> list[dict]:
    """
    Parse the log file into a list of dicts.
    Silently skips malformed lines.
    """
    entries = []
    if not os.path.exists(LOG_FILE):
        return entries
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("|")
                if len(parts) != 5:
                    continue
                ts_str, path, omode, dmode, dur_str = parts
                try:
                    entries.append({
                        "ts":       datetime.fromisoformat(ts_str),
                        "date":     datetime.fromisoformat(ts_str).date(),
                        "path":     path,
                        "omode":    omode,
                        "dmode":    dmode,
                        "duration": int(dur_str),
                    })
                except (ValueError, OverflowError):
                    continue
    except Exception:
        pass
    return entries


def print_stats():
    entries = _read_log()
    if not entries:
        print("  [!] No session log found yet. Images you open will be recorded automatically.")
        return

    today     = date.today()
    week_ago  = today - timedelta(days=6)   # last 7 days including today

    today_entries = [e for e in entries if e["date"] == today]
    week_entries  = [e for e in entries if e["date"] >= week_ago]

    total_count = len(entries)
    today_count = len(today_entries)
    week_count  = len(week_entries)

    # Total logged time (only mem/cycle entries have a meaningful duration)
    total_secs = sum(e["duration"] for e in entries if e["duration"] > 0)

    # Days practiced (unique dates)
    days_practiced = len({e["date"] for e in entries})

    # First session date
    first_date = entries[0]["date"]

    # Top 5 folders
    folder_counts: Counter = Counter(
        os.path.dirname(e["path"]) for e in entries
    )
    top_folders = folder_counts.most_common(5)

    # Mode breakdown (all time)
    mode_counts: Counter = Counter(e["dmode"] for e in entries)

    print(f"\n  Session stats  ({LOG_FILE})")
    print(f"  {'─' * 46}")
    print(f"  Images opened  — today: {today_count}   this week: {week_count}   all time: {total_count}")
    print(f"  Days practiced — {days_practiced}  (since {first_date})")
    if total_secs > 0:
        print(f"  Logged time    — {fmt_time(total_secs)}")
    print(f"  Mode breakdown — " + "   ".join(f"{k}: {v}" for k, v in mode_counts.items()))
    print(f"\n  Top folders (all time):")
    for folder_path, count in top_folders:
        print(f"    {count:>5}×  {folder_path}")
    print()


def print_streak():
    entries = _read_log()
    if not entries:
        print("  [!] No session log found yet.")
        return

    today  = date.today()
    dates  = {e["date"] for e in entries}

    # Walk backwards from today counting consecutive days
    streak = 0
    cursor = today
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)

    # Also compute longest-ever streak
    all_dates = sorted(dates)
    best, run = 1, 1
    for i in range(1, len(all_dates)):
        if (all_dates[i] - all_dates[i-1]).days == 1:
            run += 1
            best = max(best, run)
        else:
            run = 1

    last_date = max(dates)
    gap       = (today - last_date).days

    if streak == 0:
        print(f"  🔥 No current streak  (last session: {last_date}, {gap} day(s) ago)")
    elif streak == 1:
        print(f"  🔥 Streak: 1 day  (started today)")
    else:
        print(f"  🔥 Streak: {streak} day(s) in a row")
    print(f"     Best ever: {best} day(s)   |   Total days practiced: {len(dates)}")


# ── OS integration helpers ─────────────────────────────────────────────────────

def open_in_default_app(path: str):
    """Open *path* in the OS default application for its file type."""
    if not os.path.exists(path):
        print(f"  [!] File not found: {path}")
        return
    try:
        if os.name == "nt":                          # Windows
            os.startfile(path)
        elif sys.platform == "darwin":               # macOS
            import subprocess
            subprocess.Popen(["open", path])
        else:                                        # Linux / BSD
            import subprocess
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        print(f"  [!] Could not open file: {e}")


def reveal_in_explorer(path: str):
    """Open the folder containing *path* and select the file where supported."""
    if not os.path.exists(path):
        print(f"  [!] File not found: {path}")
        return
    try:
        if os.name == "nt":                          # Windows — select the file
            import subprocess
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":               # macOS — reveal in Finder
            import subprocess
            subprocess.Popen(["open", "-R", path])
        else:                                        # Linux — open parent folder
            import subprocess
            subprocess.Popen(["xdg-open", os.path.dirname(path)])
    except Exception as e:
        print(f"  [!] Could not reveal file: {e}")


def fmt_time(seconds: int) -> str:
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    parts = []
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s or not parts: parts.append(f"{s}s")
    return " ".join(parts)


# ── Compress quality helper ────────────────────────────────────────────────────

def _pop_quality(tokens: list[str], default: int) -> tuple[list[str], int]:
    """
    If the last token is a bare integer in [1, 100], pop it and return it as
    the compression quality. Otherwise leave the list unchanged and return
    *default*.

    Examples
    --------
    ["folder", "75"]  →  (["folder"], 75)
    ["path", "2"]     →  (["path", "2"], default)   # "2" is a folder index, not quality
    ["75"]            →  ([], 75)
    ["folder"]        →  (["folder"], default)
    """
    if tokens and tokens[-1].isdigit():
        v = int(tokens[-1])
        if 1 <= v <= 100:
            # Don't pop if the preceding token is "path" — the number is a
            # folder index, not a quality value (matches docstring example).
            if len(tokens) >= 2 and tokens[-2].lower() == "path":
                return tokens, default
            return tokens[:-1], v
    return tokens, default


# ── Unwanted-file helpers ──────────────────────────────────────────────────────

MEDIA = {
    ".png", ".webp", ".jpeg", ".jpg", ".tiff", ".bmp",
    ".mp4", ".mp3", ".wav", ".pdf", ".tif", ".srt", ".psd",
    ".mp4a", ".zip", ".m4v", ".clip", ".kra", ".grd",
    ".abr", ".blend", ".rar",
}


def _is_not_media(filepath: str) -> bool:
    _, ext = os.path.splitext(filepath)
    return ext.lower() not in MEDIA and os.path.isfile(filepath)


def _find_unwanted(directory: str) -> list[str]:
    result = []
    for root, _, files in os.walk(directory):
        for name in files:
            fp = os.path.join(root, name)
            if _is_not_media(fp):
                result.append(fp)
    return result


def _clean_directory(directory: str):
    """Find and interactively delete non-media files in directory."""
    if not os.path.isdir(directory):
        print(f"  [!] Not a valid directory: {directory}")
        return

    print(f"  🔍 Scanning for unwanted files in: {directory}")
    unwanted = _find_unwanted(directory)

    if not unwanted:
        print("  ✔  No unwanted files found.")
        return

    print(f"\n  Found {len(unwanted)} unwanted file(s):")
    for f in unwanted:
        print(f"    - {os.path.relpath(f, directory)}")

    try:
        confirm = input("\n  Delete all of the above? (y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n  [!] Clean cancelled.")
        return

    if confirm == "y":
        deleted, failed = 0, 0
        for f in unwanted:
            try:
                os.remove(f)
                print(f"  🗑  Deleted: {os.path.relpath(f, directory)}")
                deleted += 1
            except Exception as e:
                print(f"  [!] Failed to delete {f}: {e}")
                failed += 1
        print(f"\n  ✔  Done — {deleted} deleted" + (f", {failed} failed." if failed else "."))
    else:
        print("  Deletion cancelled.")


# ── Search helpers ─────────────────────────────────────────────────────────────

def search_images(image_list: list[str], keywords: list[str], max_results: int) -> list[str]:
    """
    Score each image path by keyword relevance and return the top matches.

    Scoring rules (all case-insensitive, applied to the full normalised path):
      +3  per keyword found in the filename (stem only, no extension)
      +2  per keyword found in an immediate parent folder name
      +1  per additional occurrence anywhere in the full path

    Only images with score > 0 are included. Results are sorted highest-score
    first and capped at *max_results*.
    """
    kw_lower = [k.lower() for k in keywords if k]
    if not kw_lower:
        return []

    scored: list[tuple[int, str]] = []

    for img in image_list:
        norm      = os.path.normpath(img)
        filename  = os.path.splitext(os.path.basename(norm))[0].lower()
        parts     = norm.replace("\\", "/").split("/")
        # immediate parent folder name (if any)
        parent    = parts[-2].lower() if len(parts) >= 2 else ""
        full_path = norm.lower()

        score = 0
        for kw in kw_lower:
            if kw in filename:
                score += 3
            elif kw in parent:
                score += 2
            elif kw in full_path:
                score += 1

        if score > 0:
            scored.append((score, img))

    scored.sort(key=lambda x: -x[0])
    results = [img for _, img in scored]

    if len(results) > max_results:
        a     = (len(results) - max_results) * (max_results / len(results))
        aux_1 = int(max_results + a * 0.9)
        pool  = results[:aux_1]
        tail  = results[aux_1:]
        if tail:
            pool.extend(random.sample(tail, max(1, len(tail) // 3)))
        aux_2  = max(1, max_results // 4)   # top results kept in order as anchor
        pool_1 = pool[:aux_2]
        pool_2 = pool[aux_2:]
        random.shuffle(pool_2)
        return (pool_1 + pool_2)[:max_results]
    else:
        random.shuffle(results)
        return results


# ── Semi-random image picker ───────────────────────────────────────────────────

def choose_semi_random_path(
    images: list[str],
    folders_used: dict[str, int],
    probability: float,
    max_tries: int,
) -> str:
    """
    Pick an image while preferring subfolders not yet seen this session.

    Algorithm
    ---------
    Each attempt picks a random image and inspects its parent subfolder:
      - If the subfolder is new → take it immediately and record it.
      - If the subfolder was already used → only take it with *probability*
        (so lower values mean stronger preference for fresh subfolders).

    If every attempt in *max_tries* hit an already-used folder, fall back to
    the candidate whose subfolder was used the *least* so far.

    *folders_used* is updated in-place only when a path is actually returned.
    """
    candidates: list[tuple[str, str]] = []   # (image_path, folder_path) of seen folders

    for _ in range(max_tries):
        path        = random.choice(images)
        folder_path = os.path.dirname(path)

        if folder_path not in folders_used:
            # Unused subfolder — take it immediately
            folders_used[folder_path] = 1
            return path

        # Already-used subfolder — accept with probability
        candidates.append((path, folder_path))
        if random.random() <= probability:
            folders_used[folder_path] += 1
            return path

    # Fallback: pick from the least-used subfolder seen during this round
    if candidates:
        candidates.sort(key=lambda x: folders_used.get(x[1], 0))
        path, folder_path = candidates[0]
        folders_used[folder_path] = folders_used.get(folder_path, 0) + 1
        return path

    # Absolute fallback (only reachable if images is non-empty but max_tries == 0)
    return random.choice(images)


# ── Memory-mode timer ──────────────────────────────────────────────────────────

_timer_thread: threading.Thread | None = None


def _cancel_timer():
    global _timer_thread
    if _timer_thread and _timer_thread.is_alive():
        _timer_thread.cancel_flag = True
        _timer_thread = None


class CancellableTimer(threading.Thread):
    def __init__(self, delay: int):
        super().__init__(daemon=True)
        self.delay       = delay
        self.cancel_flag = False

    def run(self):
        elapsed = 0
        while elapsed < self.delay:
            if self.cancel_flag:
                return
            time.sleep(0.25)
            elapsed += 0.25
        if not self.cancel_flag:
            open_black_tab()
            print(f"\n  ● Time's up! Black tab opened.")
            print("\n> ", end="", flush=True)  # a '\n' disappears here when i start typing


def start_mem_timer(seconds: int):
    global _timer_thread
    _cancel_timer()
    t = CancellableTimer(seconds)
    _timer_thread = t
    t.start()
    print(f"  ⏱  Memory timer: {fmt_time(seconds)}")


# ── Cycle mode ─────────────────────────────────────────────────────────────────

_cycle_thread: threading.Thread | None = None


def _cancel_cycle():
    global _cycle_thread
    if _cycle_thread and _cycle_thread.is_alive():
        _cycle_thread.cancel_flag = True
        _cycle_thread = None


class CycleSession(threading.Thread):
    """
    Automatically advances images every *interval* seconds for *total* seconds.
    Calls *show_next_fn* to open each image (same function as manual <Enter>).
    Opens a black tab when the session ends.
    """
    def __init__(self, interval: int, total: int, show_next_fn):
        super().__init__(daemon=True)
        self.interval     = interval
        self.total        = total
        self.show_next_fn = show_next_fn
        self.cancel_flag  = False

    def _wait(self, seconds: float) -> bool:
        elapsed = 0.0
        while elapsed < seconds:
            if self.cancel_flag:
                return False
            time.sleep(0.25)
            elapsed += 0.25
        return True

    def run(self):
        session_elapsed = 0
        images_shown    = 0

        while session_elapsed < self.total:
            if self.cancel_flag:
                return

            self.show_next_fn(print_flag=False)
            images_shown += 1

            remaining = self.total - session_elapsed
            wait_for  = min(self.interval, remaining)

            if not self._wait(wait_for):
                return

            session_elapsed += self.interval

        if not self.cancel_flag:
            open_black_tab()
            print(
                f"\n  ● Cycle complete — {images_shown} image(s) "
                f"in {fmt_time(self.total)}. Black tab opened."
            )
            print("\n> ", end="", flush=True)


# ── Main loop ──────────────────────────────────────────────────────────────────

HELP_TEXT = """
Commands
────────────────────────────────────────────────────────

  <Enter>               → next image (random or semi-random)
  mem                   → memory mode (uses default time)
  mem 30s / mem 1m30s   → memory mode with custom time
  normal                → switch back to normal mode
  shuffle               → reshuffle the image list
  info                  → show current session settings

  random / rand         → random opening mode (default)
  semi                  → semi-random opening mode
                         (prefers subfolders not yet seen)

  gray / grayscale      → toggle grayscale mode on/off
                         (value studies — images open desaturated)

  stats                 → session statistics (images opened, folders, time)
  streak                → current and best consecutive-day practice streak
  resetlog              → delete all session log data (asks for confirmation)
  log                   → toggle session logging on/off

  open                  → open current image in the system default app
                         (your painting software, image viewer, etc.)
  reveal                → reveal current image in Explorer / Finder

  flip h / horizontal   → reopen current image mirrored left-right
  flip v / vertical     → reopen current image mirrored top-bottom
                             (both work with grayscale mode)

  palette               → show current image + dominant colour swatches
  palette <n>           → extract n colours (default 6, max 12)
                          swatches on the right; respects grayscale

  grid                  → rule-of-thirds grid overlay on current image
  grid <n>              → n×n grid (e.g. grid 4, grid 6)
                          respects grayscale and flip

  cycle [interval] [total]
                        → gesture-drawing session: auto-advance
                          images every <interval>, stop after
                          <total> (prompts if omitted)
                          e.g.  cycle 30s 10m, or cycle 2m 1h
  stop                  → stop an active cycle session

  search [n] <keywords> → search loaded images by filename/path
                          keywords; opens matches one by one.
                          Press <Enter> to advance, 'stop' to
                          exit search mode.
                          e.g.  search hand pose (default max results)
                                search 10 hand pose  (limit to 10)
  search prev           → open a random/semi-random image from
                          the same subfolder as the last image

  save                  → copy current image to the save folder

  compress [q]          → compress current image
  compress folder [q]   → compress all images in current folder
  compress path <#> [q] → compress a saved folder by number
  compress dir <p> [q]  → compress any folder by path
                          q = quality 1–100 (default from settings)

  prompt                → random drawing prompt
  prompt daily          → full daily plan
  prompt list           → list all prompt types
  prompt <type>         → specific prompt (see 'prompt list')

  paths / pp                  → list all saved folders
  path <#|key>                → switch to folder by number or key
  path add <path>             → add & scan a new folder
  path del <#|key>            → remove folder + its cache
  path rename <#|key> <p>     → replace a saved path
  path swap <#|key> <#|key>   → swap two folders
  path insert <#|key> <#|key> → move a folder to another position,
                                shifting the folders in between
                                e.g.  path insert 3 7

  key <#> <key>         → assign a shortcut key to a folder
  key del <#>           → remove the key from a folder
  key rename <#> <key>  → rename a folder's key
  key swap <#> <#>      → swap keys between two folders

  scan                  → re-scan current folder
  scan <#|key>          → re-scan a specific saved folder

  clean                 → check current folder for non-media files
  clean <#|key>         → check a saved folder by number or key
  clean path <path>     → check any folder by path

  set mem <time>        → set default mem time (persistent)
  set search <n>        → set max search results (persistent)
  set compress <n>      → set default compress quality (persistent)
  set semi <prob>       → set semi-random repeat probability (persistent)
                          0.0 = never reuse a subfolder until all seen
                          1.0 = always accept any subfolder (= random)
  set folder <#|key>    → set default startup folder (persistent)
  set save   <#|key>    → set default save folder (persistent)
  set                   → show current defaults & loaded settings

  folder <path>         → load folder temporarily (not added)
  help / h              → show this message
  clear                 → clear the screen
  q / quit / exit       → quit

────────────────────────────────────────────────────────
Usage:  python openref.py [settings.json]
────────────────────────────────────────────────────────
"""


def print_paths(saved_paths: list[str], path_keys: dict[str, str], cache: dict, active_folder: str, save_folder_index: int, default_folder_index: int):
    print(f"\n  Saved folders ({len(saved_paths)}):")
    # Pre-compute display strings so we can measure column widths
    rows = []
    for i, p in enumerate(saved_paths, 1):
        browse_marker  = "►" if p == active_folder else " "
        save_marker    = "💾" if (i - 1) == save_folder_index else "  "
        default_marker = "★" if (i - 1) == default_folder_index else " "
        cached_str     = f"{len(cache[p])}" if p in cache else "not scanned"
        key            = path_keys.get(p)
        key_str        = f"[{key}]" if key else ""
        rows.append((save_marker, default_marker, browse_marker, i, p, cached_str, key_str))

    num_w   = len(str(len(saved_paths)))
    path_w  = max(len(r[4]) for r in rows) if rows else 0
    cache_w = max(len(r[5]) for r in rows) if rows else 0

    for save_marker, default_marker, browse_marker, i, p, cached_str, key_str in rows:
        num_str = f"[{i}]".ljust(num_w + 2)
        line = f"  {save_marker} {default_marker} {browse_marker} {num_str} {p:<{path_w}}  ({cached_str:<{cache_w}})  {key_str}"
        print(line.rstrip())
    print("  (★ = default startup  💾 = save destination  ► = active)\n")


def do_scan(path: str, cache: dict[str, list[str]]) -> list[str] | None:
    """Scan path, update & persist cache. Returns image list or None on failure."""
    if not os.path.isdir(path):
        print(f"  [!] Directory not found: {path}")
        return None
    print(f"  🔍 Scanning {path} …", end="", flush=True)
    found = scan_folder(path)
    if not found:
        # Cache the empty result so repeated scans don't re-walk the filesystem.
        cache[path] = []
        save_cache(cache)
        print(f"\n  [!] No images found in: {path}")
        return None
    cache[path] = found
    save_cache(cache)
    print(f" done — {len(found)} images cached.")
    return found


def main():
    global _cycle_thread, FIREFOX_PATH, IMAGE_EXTENSIONS

    # ── Load settings file ─────────────────────────────────────────────────
    settings_arg  = sys.argv[1] if len(sys.argv) > 1 else None
    settings_file = _resolve_settings_path(settings_arg)
    settings      = load_settings(settings_arg)
    apply_settings(settings)

    # ── Load paths & user prefs ────────────────────────────────────────────
    saved_paths, path_keys, prefs = load_saved_paths()
    cache: dict[str, list[str]] = load_cache()

    default_mem_time:       int   = int(settings.get("default_mem_time",         _FALLBACK_MEM_TIME))
    search_max_results:     int   = int(settings.get("search_max_results",       _FALLBACK_SEARCH_RESULTS))
    compress_quality:       int   = int(settings.get("compress_quality",         _FALLBACK_COMPRESS_QUALITY))
    semi_rand_probability:  float = float(settings.get("semi_rand_probability",  _FALLBACK_SEMI_RAND_PROBABILITY))
    semi_rand_max_tries:    int   = int(settings.get("semi_rand_max_tries",      _FALLBACK_SEMI_RAND_MAX_TRIES))

    # Resolve starting folder from default_folder_index (clamp to valid range)
    def _resolve_default_folder() -> str | None:
        if not saved_paths:
            return None
        di = prefs.get("default_folder_index", 0)
        di = max(0, min(di, len(saved_paths) - 1))
        return saved_paths[di]

    folder  = _resolve_default_folder() or ""
    images: list[str] = []
    index   = 0
    mem_mode      = False
    mem_seconds   = default_mem_time
    opening_mode  = "random"      # "random" | "semi-random"
    grayscale_mode  = False         # toggle: images open via HTML wrapper with CSS grayscale
    logging_enabled = True           # toggle: whether image opens are written to the log
    folders_used: dict[str, int] = {}   # subfolder → times picked (semi-random)
    current_image: str | None = None

    # Lock that guards `images` and `index`, which are shared between the main
    # thread and the CycleSession background thread.
    _image_lock = threading.Lock()

    # Clamp save_folder_index to valid range.
    # Stored as a one-element list so nested scopes can mutate it without nonlocal.
    _sfi_val: int = prefs.get("default_save_index", 0)
    if saved_paths:
        _sfi_val = max(0, min(_sfi_val, len(saved_paths) - 1))
    _sfi: list[int] = [_sfi_val]   # _sfi[0] is the live save_folder_index

    # ── Load images for a folder (cache-first, or scan if missing) ─────────
    def load(path: str, force_scan: bool = False) -> bool:
        nonlocal images, index, folder, folders_used

        if not path:
            print("  [!] No folder specified.")
            return False

        if not force_scan and path in cache:
            imgs = cache[path]
            if not imgs:
                print(f"  [!] No images found in: {path}  (cached — run 'scan' to refresh)")
                return False
            key     = path_keys.get(path)
            key_str = f"  [key: {key}]" if key else ""
            print(f"  ✔  Loaded {len(imgs)} images from cache: {path}{key_str}")
        else:
            imgs = do_scan(path, cache)
            if imgs is None:
                return False

        folder = path
        folders_used = {}   # reset semi-random state on every folder switch
        with _image_lock:
            images = list(imgs)
            random.shuffle(images)
            index  = 0
        return True

    print("=" * 56)
    print("  Openref —  Drawing Practice Tool")
    print("=" * 56)
    print(HELP_TEXT)

    if folder:
        if not load(folder):
            folder = ""

    if not folder or not images:
        if saved_paths:
            print("  [!] Default folder could not be loaded.")
        else:
            print("  No saved folders. Add one with:  path add <path>")
        try:
            new = input("  Enter a folder path to start (or press Enter to skip): ").strip().strip('"')
            if new:
                if load(new):
                    if new not in saved_paths:
                        saved_paths.append(new)
                        prefs["default_folder_index"] = saved_paths.index(new)
                        prefs["default_save_index"]   = saved_paths.index(new)
                        save_paths(saved_paths, path_keys, prefs)
                        print(f"  ✔  Added [{len(saved_paths)}] {new}")
                else:
                    print("  Could not load any images. Continuing without a loaded folder.")
        except (EOFError, KeyboardInterrupt):
            pass

    def show_next(print_flag: bool = True):
        nonlocal index, current_image
        _cancel_timer()

        # Hold the lock while reading/writing index and images so CycleSession's
        # background thread can't cause a data race or IndexError.
        with _image_lock:
            if not images:
                if print_flag:
                    print("  [!] No images loaded. Use 'path add <path>' or 'folder <path>'.")
                return

            if opening_mode == "semi-random":
                # Semi-random: pick by subfolder preference; index not used.
                path  = choose_semi_random_path(
                    images, folders_used, semi_rand_probability, semi_rand_max_tries
                )
                idx   = -1       # no sequential position in this mode
                total = len(images)
            else:
                # Random (sequential shuffle): advance through the shuffled list.
                if index >= len(images):
                    random.shuffle(images)
                    index = 0
                    if print_flag:
                        print("  ↺  Reshuffled image list.")
                path  = images[index]
                idx   = index
                total = len(images)
                index += 1

        current_image = path
        name = os.path.relpath(path, folder) if folder else path
        if print_flag:
            pos_str = f"{idx + 1}/{total}" if opening_mode == "random" else f"~/{total}"
            gray_tag = "  [gray]" if grayscale_mode else ""
            print(f"  [{pos_str}]  {name}{gray_tag}")
        open_image(path, grayscale_mode)
        # Log the event — determine display_mode and duration
        if _cycle_thread and _cycle_thread.is_alive():
            _log_dmode, _log_dur = "cycle", _cycle_thread.interval
        elif mem_mode:
            _log_dmode, _log_dur = "mem", mem_seconds
        else:
            _log_dmode, _log_dur = "normal", 0
        if logging_enabled:
            log_entry(path, opening_mode, _log_dmode, _log_dur)
        if mem_mode:
            start_mem_timer(mem_seconds)

    while True:
        try:
            raw = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  ~~")
            _cancel_timer()
            _cancel_cycle()
            break

        cmd = raw.lower()

        # ── Block commands while a cycle is active ─────────────────────────
        cycle_active = _cycle_thread is not None and _cycle_thread.is_alive()
        if cycle_active and cmd not in ("stop", "q", "quit", "exit", "info"):
            print("  [!] Cycle in progress — type 'stop' to end it.")
            continue

        # ── Quit ───────────────────────────────────────────────────────────
        if cmd in ("q", "quit", "exit"):
            print("\n  ~~")
            _cancel_timer()
            _cancel_cycle()
            break

        # ── Help ───────────────────────────────────────────────────────────
        elif cmd in ("help", "h"):
            print(HELP_TEXT)

        # ── Clear ──────────────────────────────────────────────────────────
        elif cmd in ("clear", "cls"):
            os.system("cls" if os.name == "nt" else "clear")

        # ── Info ───────────────────────────────────────────────────────────
        elif cmd == "info":
            mode_str  = f"memory ({fmt_time(mem_seconds)})" if mem_mode else "normal"
            cycle_str = ""
            if _cycle_thread and _cycle_thread.is_alive():
                cycle_str = (
                    f"\n  Cycle  : {fmt_time(_cycle_thread.interval)}/image, "
                    f"{fmt_time(_cycle_thread.total)} total"
                )
            save_dest   = saved_paths[_sfi[0]] if 0 <= _sfi[0] < len(saved_paths) else "(none)"
            active_key  = path_keys.get(folder)
            key_str     = f"  [key: {active_key}]" if active_key else ""
            img_str     = str(len(images)) if images else "none loaded"
            gray_str    = "on  (value study)" if grayscale_mode else "off"
            print(f"  Folder   : {folder}{key_str}")
            print(f"  Images   : {img_str}")
            print(f"  Mode     : {mode_str}{cycle_str}")
            print(f"  Opening  : {opening_mode}")
            print(f"  Grayscale: {gray_str}")
            print(f"  Logging  : {'on' if logging_enabled else 'OFF (paused)'}")
            print(f"  Save →   : [{_sfi[0] + 1}] {save_dest}")

        # ── Shuffle ────────────────────────────────────────────────────────
        elif cmd == "shuffle":
            with _image_lock:
                random.shuffle(images)
                index = 0
            folders_used.clear()
            print("  ↺  Reshuffled.")

        # ── Stop cycle ─────────────────────────────────────────────────────
        elif cmd == "stop":
            if _cycle_thread and _cycle_thread.is_alive():
                _cancel_cycle()
                print("  ■  Cycle session stopped.")
            else:
                print("  [!] No active cycle session.")

        # ── Opening mode: random ───────────────────────────────────────────
        elif cmd in ("random", "rand"):
            opening_mode = "random"
            print("  ► Opening mode: random.")

        # ── Opening mode: semi-random ──────────────────────────────────────
        elif cmd == "semi":
            opening_mode = "semi-random"
            folders_used.clear()
            print(f"  ► Opening mode: semi-random  (repeat probability: {semi_rand_probability}).")

        # ── Grayscale toggle ───────────────────────────────────────────────
        elif cmd in ("gray", "grayscale"):
            grayscale_mode = not grayscale_mode
            if grayscale_mode:
                print("  ◑  Grayscale ON  — images will open desaturated (value studies).")
            else:
                print("  ●  Grayscale OFF — images will open in full colour.")

        # ── Flip (one-shot mirror of current image) ────────────────────────
        elif cmd == "flip" or cmd.startswith("flip "):
            if current_image is None:
                print("  [!] No image has been opened yet.")
            else:
                arg = cmd[4:].strip()
                if arg in ("h", "horizontal"):
                    flip_dir  = "h"
                    flip_name = "horizontal (left-right)"
                elif arg in ("v", "vertical"):
                    flip_dir  = "v"
                    flip_name = "vertical (top-bottom)"
                else:
                    print("  [?] Usage:  flip h  |  flip horizontal  |  flip v  |  flip vertical")
                    flip_dir = None

                if flip_dir:
                    name     = os.path.relpath(current_image, folder) if folder else current_image
                    gray_tag = "  [gray]" if grayscale_mode else ""
                    print(f"  ↔  Flip {flip_name}{gray_tag}  — {name}")
                    open_image(current_image, grayscale_mode, flip_dir)
                    if mem_mode:
                        start_mem_timer(mem_seconds)

        # ── Palette ────────────────────────────────────────────────────────
        elif cmd == "palette" or cmd.startswith("palette "):
            if current_image is None:
                print("  [!] No image has been opened yet.")
            else:
                arg = cmd[7:].strip()
                if arg.isdigit() and 1 <= int(arg) <= 12:
                    n_pal = int(arg)
                elif arg == "":
                    n_pal = 6
                else:
                    print("  [?] Usage:  palette  |  palette <n>  (n = 1–12)")
                    n_pal = 0
                if n_pal:
                    open_palette(current_image, n_pal, grayscale_mode)
                    if mem_mode:
                        start_mem_timer(mem_seconds)

        # ── Grid overlay ────────────────────────────────────────────────────
        elif cmd == "grid" or cmd.startswith("grid "):
            if current_image is None:
                print("  [!] No image has been opened yet.")
            else:
                arg = cmd[4:].strip()
                if arg == "":
                    divisions = 3
                elif arg.isdigit() and 2 <= int(arg) <= 12:
                    divisions = int(arg)
                else:
                    print("  [?] Usage:  grid  |  grid <n>  (n = 2–12, default 3)")
                    divisions = 0
                if divisions:
                    name      = os.path.relpath(current_image, folder) if folder else current_image
                    gray_tag  = "  [gray]" if grayscale_mode else ""
                    grid_name = "rule of thirds" if divisions == 3 else f"{divisions}×{divisions}"
                    print(f"  ⊞  Grid ({grid_name}){gray_tag}  — {name}")
                    open_grid(current_image, divisions, grayscale_mode, None)
                    if mem_mode:
                        start_mem_timer(mem_seconds)

        # ── Stats ──────────────────────────────────────────────────────────
        elif cmd == "stats":
            print_stats()

        # ── Streak ─────────────────────────────────────────────────────────
        elif cmd == "streak":
            print_streak()

        # ── Reset log ──────────────────────────────────────────────────────
        elif cmd == "resetlog":
            if not os.path.exists(LOG_FILE):
                print("  [!] No log file found — nothing to reset.")
            else:
                try:
                    confirm = input("  This will permanently delete all session history. Are you sure? (yes/n): ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print("\n  [!] Cancelled.")
                    continue
                if confirm == "yes":
                    try:
                        os.remove(LOG_FILE)
                        print("  ✔  Session log deleted.")
                    except Exception as e:
                        print(f"  [!] Could not delete log: {e}")
                else:
                    print("  Cancelled.")

        # ── Log toggle ─────────────────────────────────────────────────────
        elif cmd == "log":
            logging_enabled = not logging_enabled
            if logging_enabled:
                print("  ✔  Logging ON  — sessions will be recorded.")
            else:
                print("  ⏸  Logging OFF — sessions will not be recorded until you type 'log' again.")

        # ── Open in default app ────────────────────────────────────────────
        elif cmd == "open":
            if current_image is None:
                print("  [!] No image has been opened yet.")
            else:
                name = os.path.relpath(current_image, folder) if folder else current_image
                print(f"  ↗  Opening in default app: {name}")
                open_in_default_app(current_image)

        # ── Reveal in Explorer / Finder ─────────────────────────────────────
        elif cmd == "reveal":
            if current_image is None:
                print("  [!] No image has been opened yet.")
            else:
                name = os.path.relpath(current_image, folder) if folder else current_image
                print(f"  📂 Revealing: {name}")
                reveal_in_explorer(current_image)

        # ── Save current image ─────────────────────────────────────────────
        elif cmd == "save":
            if current_image is None:
                print("  [!] No image has been opened yet.")
            elif _sfi[0] >= len(saved_paths):
                print(f"  [!] Save folder [{_sfi[0] + 1}] no longer exists. Use 'set save <#>' to pick another.")
            else:
                dest_folder = saved_paths[_sfi[0]]
                if os.path.abspath(current_image).startswith(os.path.abspath(dest_folder) + os.sep):
                    print(f"  [!] Image is already in the save folder [{_sfi[0] + 1}].")
                else:
                    os.makedirs(dest_folder, exist_ok=True)
                    base, ext = os.path.splitext(os.path.basename(current_image))
                    dest      = os.path.join(dest_folder, base + ext)
                    counter   = 1
                    while os.path.exists(dest):
                        dest = os.path.join(dest_folder, f"{base}_{counter}{ext}")
                        counter += 1
                    shutil.copy2(current_image, dest)
                    print(f"  ✔  Saved → {os.path.relpath(dest, dest_folder)}  (in [{_sfi[0] + 1}] {dest_folder})")
                    if dest_folder in cache:
                        cache[dest_folder].append(dest)
                        save_cache(cache)

        # ── Set: change persistent defaults ───────────────────────────────
        elif cmd == "set" or cmd.startswith("set "):
            sub       = raw[3:].strip()
            sub_lower = sub.lower()

            # set mem <time>
            if sub_lower.startswith("mem "):
                time_str = sub[4:].strip()
                parsed   = time_string_to_seconds(time_str)
                if parsed <= 0:
                    print("  [!] Invalid time. Use formats like: 30s, 1m, 1m30s")
                else:
                    default_mem_time             = parsed
                    settings["default_mem_time"] = parsed
                    save_settings(settings, settings_file)
                    print(f"  ✔  Default mem time → {fmt_time(parsed)}  (saved).")

            # set search <n>
            elif sub_lower.startswith("search "):
                arg = sub[7:].strip()
                if arg.isdigit() and int(arg) > 0:
                    n = int(arg)
                    search_max_results             = n
                    settings["search_max_results"] = n
                    save_settings(settings, settings_file)
                    apply_settings(settings)
                    print(f"  ✔  Search max results → {n}  (saved).")
                else:
                    print("  [!] Usage: set search <positive number>")

            # set compress <quality>
            elif sub_lower.startswith("compress "):
                arg = sub[9:].strip()
                if arg.isdigit() and 1 <= int(arg) <= 100:
                    n = int(arg)
                    compress_quality             = n
                    settings["compress_quality"] = n
                    save_settings(settings, settings_file)
                    print(f"  ✔  Default compress quality → {n}  (saved).")
                else:
                    print("  [!] Usage: set compress <1–100>")

            # set semi <probability>
            elif sub_lower.startswith("semi "):
                arg = sub[5:].strip()
                try:
                    v = float(arg)
                    if not (0.0 <= v <= 1.0):
                        raise ValueError
                    semi_rand_probability             = v
                    settings["semi_rand_probability"] = v
                    save_settings(settings, settings_file)
                    print(f"  ✔  Semi-random repeat probability → {v}  (saved).")
                except ValueError:
                    print("  [!] Usage: set semi <0.0–1.0>  e.g. set semi 0.2")

            # set folder <# or key>
            elif sub_lower.startswith("folder "):
                arg = sub[7:].strip()
                if arg.isdigit():
                    n = int(arg) - 1
                else:
                    p = _path_for_key(arg, saved_paths, path_keys)
                    n = saved_paths.index(p) if p is not None else -1
                if 0 <= n < len(saved_paths):
                    prefs["default_folder_index"] = n
                    save_paths(saved_paths, path_keys, prefs)
                    print(f"  ✔  Default startup folder → [{n + 1}] {saved_paths[n]}  (saved).")
                elif arg.isdigit():
                    print(f"  [!] Number out of range (1–{len(saved_paths)}).")
                else:
                    print(f"  [!] No folder with key '{arg}'.")

            # set save <# or key>
            elif sub_lower.startswith("save "):
                arg = sub[5:].strip()
                if arg.isdigit():
                    n = int(arg) - 1
                else:
                    p = _path_for_key(arg, saved_paths, path_keys)
                    n = saved_paths.index(p) if p is not None else -1
                if 0 <= n < len(saved_paths):
                    _sfi[0] = n
                    prefs["default_save_index"] = n
                    save_paths(saved_paths, path_keys, prefs)
                    print(f"  ✔  Default save folder → [{n + 1}] {saved_paths[n]}  (saved).")
                elif arg.isdigit():
                    print(f"  [!] Number out of range (1–{len(saved_paths)}).")
                else:
                    print(f"  [!] No folder with key '{arg}'.")

            # bare "set" → show current config
            elif sub_lower == "":
                di = prefs.get("default_folder_index", 0)
                df = saved_paths[di] if saved_paths and 0 <= di < len(saved_paths) else "(none)"
                si = prefs.get("default_save_index", 0)
                sf = saved_paths[si] if saved_paths and 0 <= si < len(saved_paths) else "(none)"
                print(f"\n  Settings  ({settings_file}):")
                print(f"    Firefox path         : {FIREFOX_PATH}")
                print(f"    Image extensions     : {', '.join(sorted(IMAGE_EXTENSIONS))}")
                print(f"    Default mem time     : {fmt_time(default_mem_time)}")
                print(f"    Search max results   : {search_max_results}")
                print(f"    Compress quality     : {compress_quality}")
                print(f"    Semi-rand probability: {semi_rand_probability}")
                print(f"    Semi-rand max tries  : {semi_rand_max_tries}")
                print(f"\n  Folder prefs  (ref_paths.json):")
                print(f"    Startup folder       : [{di + 1}] {df}")
                print(f"    Save folder          : [{si + 1}] {sf}")
                print()
            else:
                print("  [?] Usage:  set mem <t>  |  set search <n>  |  set compress <q>  |  set semi <p>  |  set folder <#>  |  set save <#>  |  set")

        # ── Cycle mode ─────────────────────────────────────────────────────
        elif cmd == "cycle" or cmd.startswith("cycle "):
            remainder = raw[5:].strip()
            tokens    = remainder.split() if remainder else []

            interval_secs = 0
            total_secs    = 0

            if len(tokens) >= 2:
                interval_secs = time_string_to_seconds(tokens[0])
                total_secs    = time_string_to_seconds(" ".join(tokens[1:]))
            elif len(tokens) == 1:
                interval_secs = time_string_to_seconds(tokens[0])

            try:
                if interval_secs <= 0:
                    raw_i         = input("  Interval between images (e.g. 30s, 2m): ").strip()
                    interval_secs = time_string_to_seconds(raw_i)
                if total_secs <= 0:
                    raw_t      = input("  Total session time   (e.g. 10m, 1h):   ").strip()
                    total_secs = time_string_to_seconds(raw_t)
            except (EOFError, KeyboardInterrupt):
                print("\n  [!] Cycle setup cancelled.")
                continue

            if interval_secs <= 0 or total_secs <= 0:
                print("  [!] Invalid times. Use formats like: 30s, 1m, 1m30s, 1h")
            elif interval_secs > total_secs:
                print("  [!] Interval can't be longer than the total session time.")
            else:
                n_images = total_secs // interval_secs
                print(
                    f"  ► Cycle session: {fmt_time(interval_secs)}/image "
                    f"× ~{n_images} images = {fmt_time(total_secs)} total."
                )
                print("  Type 'stop' at any time to end the session early.")
                _cancel_cycle()
                t = CycleSession(interval_secs, total_secs, show_next)
                _cycle_thread = t
                t.start()

        # ── Compress ───────────────────────────────────────────────────────
        elif cmd == "compress" or cmd.startswith("compress "):
            # Parse the subcommand using the lowercased cmd, but keep the
            # raw (un-lowercased) version for directory paths.
            sub     = cmd[8:].strip()     # lowercased, for keyword checks
            raw_sub = raw[9:].strip()     # original case, for dir paths

            tokens = sub.split()
            tokens, quality = _pop_quality(tokens, compress_quality)
            sub_clean = " ".join(tokens)  # subcommand without any trailing quality

            # compress  /  compress <quality>
            if sub_clean in ("", "image"):
                if current_image is None:
                    print("  [!] No image has been opened yet.")
                elif not _compress.should_compress(current_image):
                    print("  [!] Image doesn't meet compression criteria (too small or already optimised).")
                else:
                    original_size = os.path.getsize(current_image)
                    print(f"  🗜  Compressing current image (q{quality}) …", end="", flush=True)
                    ok = _compress.compress_image(current_image, quality=quality, backup=False)
                    if ok:
                        new_size = os.path.getsize(current_image)
                        saved_mb = (original_size - new_size) / (1024 * 1024)
                        pct      = saved_mb / (original_size / (1024 * 1024)) * 100
                        print(f" done — saved {saved_mb:.2f} MB ({pct:.1f}%)")
                    else:
                        print(" failed.")

            # compress folder  /  compress folder <quality>
            elif sub_clean == "folder":
                target = folder
                def _run_compress(path, _q=quality):
                    print(f"\n  🗜  Compressing folder (q{_q}): {path}")
                    _compress.process_directory(path, quality=_q)
                    print(f"\n  ✔  Compression finished: {path}")
                    print("\n> ", end="", flush=True)
                threading.Thread(target=_run_compress, args=(target,), daemon=True).start()

            # compress path <#>  /  compress path <#> <quality>
            elif sub_clean.startswith("path "):
                idx_str = sub_clean[5:].strip()
                if idx_str.isdigit():
                    n = int(idx_str) - 1
                    if 0 <= n < len(saved_paths):
                        target = saved_paths[n]
                        def _run_compress_path(path, _n=n, _q=quality):
                            print(f"\n  🗜  Compressing folder [{_n + 1}] (q{_q}): {path}")
                            _compress.process_directory(path, quality=_q)
                            print(f"\n  ✔  Compression finished: {path}")
                            print("  > ", end="", flush=True)
                        threading.Thread(target=_run_compress_path, args=(target,), daemon=True).start()
                    else:
                        print(f"  [!] Number out of range (1–{len(saved_paths)}).")
                else:
                    print("  [!] Usage: compress path <number> [quality]")

            # compress dir <path>  /  compress dir <path> <quality>
            elif sub_clean.startswith("dir"):
                # Quality was already popped from tokens; rebuild the dir portion
                # from raw_sub (preserving original case and spaces in the path),
                # but strip a trailing quality token if one was consumed.
                dir_raw = raw_sub
                if quality != compress_quality:
                    # A quality was parsed — strip the matching trailing token
                    dir_raw = dir_raw.rsplit(None, 1)[0] if dir_raw.rsplit(None, 1)[-1].isdigit() else dir_raw
                target = dir_raw[4:].strip().strip('"') if dir_raw.lower().startswith("dir ") else dir_raw.strip().strip('"')
                if not os.path.isdir(target):
                    print(f"  [!] Directory not found: {target}")
                else:
                    def _run_compress_dir(path, _q=quality):
                        print(f"\n  🗜  Compressing (q{_q}): {path}")
                        _compress.process_directory(path, quality=_q)
                        print(f"\n  ✔  Compression finished: {path}")
                        print("  > ", end="", flush=True)
                    threading.Thread(target=_run_compress_dir, args=(target,), daemon=True).start()

            else:
                print("  [?] Usage: compress [q]  |  compress folder [q]  |  compress path <#> [q]  |  compress dir <path> [q]")

        # ── Prompt ─────────────────────────────────────────────────────────
        elif cmd == "prompt" or cmd.startswith("prompt "):
            sub = cmd[6:].strip()

            if sub in ("", "random"):
                _prompts.random_complete_prompt()
            elif sub == "list":
                print("\n  Available prompt types:")
                for key, (_, label) in _PROMPT_CMDS.items():
                    print(f"    prompt {key:<12} → {label}")
                print()
            elif sub in _PROMPT_CMDS:
                fn_name, label = _PROMPT_CMDS[sub]
                fn = getattr(_prompts, fn_name, None)
                if fn is None:
                    print(f"  [!] Function '{fn_name}' not found in random_prompt.py.")
                else:
                    fn()
            else:
                print(f"  [?] Unknown prompt type: '{sub}'. Use 'prompt list' to see options.")

        # ── Search ─────────────────────────────────────────────────────────
        elif cmd == "search" or cmd.startswith("search "):
            if _cycle_thread and _cycle_thread.is_alive():
                print("  [!] Cannot search while a cycle session is running. Type 'stop' first.")
                continue

            sub = raw[6:].strip()

            # ── search prev ───────────────────────────────────────────────
            if sub.lower() == "prev":
                if current_image is None:
                    print("  [!] No image has been opened yet.")
                    continue
                prev_folder = os.path.dirname(current_image)
                # Collect all images in the same immediate subfolder
                with _image_lock:
                    siblings = [p for p in images if os.path.dirname(p) == prev_folder]
                if not siblings:
                    print(f"  [!] No other images found in: {prev_folder}")
                    continue
                if opening_mode == "semi-random":
                    path = choose_semi_random_path(
                        siblings, folders_used, semi_rand_probability, semi_rand_max_tries
                    )
                else:
                    path = random.choice(siblings)
                current_image = path
                name = os.path.relpath(path, folder) if folder else path
                gray_tag = "  [gray]" if grayscale_mode else ""
                print(f"  [prev folder]  {name}{gray_tag}")
                open_image(path, grayscale_mode)
                _log_dmode2 = "mem" if mem_mode else "normal"
                _log_dur2   = mem_seconds if mem_mode else 0
                if logging_enabled:
                    log_entry(path, opening_mode, _log_dmode2, _log_dur2)
                if mem_mode:
                    start_mem_timer(mem_seconds)
                continue

            if not images:
                print("  [!] No images loaded. Use 'path add <path>' or 'folder <path>'.")
                continue

            # ── Optional leading max-results number ───────────────────────
            # If the first token is a positive integer, use it as the result
            # cap for this search only; the rest are the keywords.
            # e.g.  search 10 hand pose  →  max=10, keywords=["hand","pose"]
            #       search hand pose     →  max=default, keywords=["hand","pose"]
            tokens      = sub.split()
            local_max   = search_max_results
            if tokens and tokens[0].isdigit() and int(tokens[0]) > 0:
                local_max = int(tokens[0])
                tokens    = tokens[1:]
            keywords_str = " ".join(tokens)

            # Prompt for keywords if not supplied inline
            if not keywords_str:
                try:
                    keywords_str = input("  Keywords: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n  [!] Search cancelled.")
                    continue

            if not keywords_str:
                print("  [!] No keywords entered.")
                continue

            keywords = keywords_str.split()
            results  = search_images(images, keywords, local_max)

            if not results:
                print(f"  [!] No results for: '{keywords_str}'")
                continue

            max_label = f"max {local_max}" if local_max != search_max_results else f"max {search_max_results}"
            print(f"  🔍 {len(results)} result(s) for '{keywords_str}' ({max_label}).")
            print("  Press <Enter> to view each image, or 'stop' to exit search.")

            search_idx = 0
            while search_idx < len(results):
                # ── Open the current result ────────────────────────────────
                img_path      = results[search_idx]
                current_image = img_path
                name          = os.path.relpath(img_path, folder) if folder else img_path
                gray_tag      = "  [gray]" if grayscale_mode else ""
                print(f"\n  [{search_idx + 1}/{len(results)}]  {name}{gray_tag}")
                open_image(img_path, grayscale_mode)
                _log_dmode3 = "mem" if mem_mode else "normal"
                _log_dur3   = mem_seconds if mem_mode else 0
                if logging_enabled:
                    log_entry(img_path, opening_mode, _log_dmode3, _log_dur3)
                if mem_mode:
                    start_mem_timer(mem_seconds)
                search_idx += 1

                if search_idx >= len(results):
                    print("  ✔  End of search results.")
                    break

                # ── Prompt loop — only advances to the next image on "" ────
                while True:
                    try:
                        nxt = input("\n(search) > ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        _cancel_timer()
                        print("\n  [!] Search ended.")
                        search_idx = len(results)   # force outer loop to exit
                        break

                    if nxt == "stop":
                        _cancel_timer()
                        print("  ■  Search stopped.")
                        search_idx = len(results)   # force outer loop to exit
                        break
                    elif nxt == "":
                        break   # advance to the next result
                    else:
                        print("  [!] In search mode — press <Enter> for next image or 'stop' to exit.")
                        # stay in the inner loop; image is NOT re-opened

        # ── Scan ───────────────────────────────────────────────────────────
        elif cmd == "scan" or cmd.startswith("scan "):
            rest = raw[4:].strip()

            if rest == "":
                load(folder, force_scan=True)

            elif rest.isdigit():
                n = int(rest) - 1
                if 0 <= n < len(saved_paths):
                    target = saved_paths[n]
                    if target == folder:
                        load(folder, force_scan=True)
                    else:
                        do_scan(target, cache)
                else:
                    print(f"  [!] Number out of range (1–{len(saved_paths)}).")

            else:
                # Try rest as a folder key
                target = _path_for_key(rest, saved_paths, path_keys)
                if target is not None:
                    if target == folder:
                        load(folder, force_scan=True)
                    else:
                        do_scan(target, cache)
                else:
                    print(f"  [!] Usage:  scan  |  scan <number>  |  scan <key>")

        # ── Paths: list ────────────────────────────────────────────────────
        elif cmd in ("paths", "pp"):
            print_paths(saved_paths, path_keys, cache, folder, _sfi[0], prefs.get("default_folder_index", 0))

        # ── Paths: subcommands ─────────────────────────────────────────────
        elif cmd.startswith(("path", "p ")):
            rest       = cmd.partition(" ")[2].strip()
            rest_orig  = raw.partition(" ")[2].strip()
            rest_lower = rest.lower()

            # path add <path>
            if rest_lower.startswith("add "):
                new_path = rest_orig[4:].strip().strip('"')
                if new_path in saved_paths:
                    print(f"  [!] Already in list: {new_path}")
                else:
                    imgs = do_scan(new_path, cache)
                    if imgs is not None:
                        saved_paths.append(new_path)
                        save_paths(saved_paths, path_keys, prefs)
                        print(f"  ✔  Added [{len(saved_paths)}] {new_path}")
                        print_paths(saved_paths, path_keys, cache, folder, _sfi[0], prefs.get("default_folder_index", 0))

            # path del <#|key>
            elif rest_lower.startswith("del "):
                idx_str = rest[4:].strip()
                if not idx_str:
                    print("  [!] Usage: path del <#|key>")
                else:
                    n = _resolve_folder_arg(idx_str, saved_paths, path_keys)
                    if 0 <= n < len(saved_paths):
                        removed = saved_paths.pop(n)
                        path_keys.pop(removed, None)

                        # When the active folder is removed, immediately clear
                        # the image list so <Enter> can't keep opening its stale
                        # images, then auto-switch to folder [1] if one exists.
                        if folder == removed:
                            with _image_lock:
                                images.clear()
                                index = 0
                            folder = ""
                            current_image = None
                            if saved_paths:
                                print(f"  ⚠  Active folder was removed — switching to [1] {saved_paths[0]}")
                                load(saved_paths[0])
                            else:
                                print("  ⚠  Active folder was removed and no folders remain. Add one with: path add <path>")

                        # Adjust persistent indices; print a notice when one resets.
                        def _adjust_index(key: str):
                            v = prefs.get(key, 0)
                            if v == n:
                                prefs[key] = 0
                                print(f"  ℹ  '{key}' reset to [1].")
                            elif v > n:
                                prefs[key] = v - 1

                        _adjust_index("default_folder_index")

                        if _sfi[0] == n:
                            _sfi[0] = 0
                            prefs["default_save_index"] = 0
                            print("  ℹ  Save folder reset to [1].")
                        elif _sfi[0] > n:
                            _sfi[0] -= 1
                            prefs["default_save_index"] = _sfi[0]

                        save_paths(saved_paths, path_keys, prefs)

                        if removed in cache:
                            del cache[removed]
                            save_cache(cache)
                            print(f"  ✔  Removed: {removed}  (cache cleared)")
                        else:
                            print(f"  ✔  Removed: {removed}")

                        if not saved_paths:
                            print("  [!] Path list is now empty — add one with: path add <path>")
                        else:
                            print_paths(saved_paths, path_keys, cache, folder, _sfi[0], prefs.get("default_folder_index", 0))
                    else:
                        print(_bad_folder_arg(idx_str))

            # path swap <#|key> <#|key>
            elif rest_lower.startswith("swap "):
                parts = rest[5:].strip().split(None, 1)
                if len(parts) == 2:
                    a = _resolve_folder_arg(parts[0], saved_paths, path_keys)
                    b = _resolve_folder_arg(parts[1], saved_paths, path_keys)
                    if not (0 <= a < len(saved_paths)):
                        print(_bad_folder_arg(parts[0]))
                    elif not (0 <= b < len(saved_paths)):
                        print(_bad_folder_arg(parts[1]))
                    elif a == b:
                        print("  [!] Can't swap a folder with itself.")
                    else:
                        saved_paths[a], saved_paths[b] = saved_paths[b], saved_paths[a]

                        def _swap_index(key: str):
                            v = prefs.get(key, 0)
                            if v == a:
                                prefs[key] = b
                            elif v == b:
                                prefs[key] = a

                        _swap_index("default_folder_index")
                        _swap_index("default_save_index")

                        if _sfi[0] == a:
                            _sfi[0] = b
                        elif _sfi[0] == b:
                            _sfi[0] = a

                        save_paths(saved_paths, path_keys, prefs)
                        print(f"  ✔  Swapped [{a+1}] and [{b+1}].")
                        print_paths(saved_paths, path_keys, cache, folder, _sfi[0], prefs.get("default_folder_index", 0))
                else:
                    print("  [!] Usage: path swap <#|key> <#|key>")

            # path insert <#|key> <#|key>
            elif rest_lower.startswith("insert "):
                parts = rest[7:].strip().split(None, 1)
                if len(parts) == 2:
                    src = _resolve_folder_arg(parts[0], saved_paths, path_keys)
                    dst = _resolve_folder_arg(parts[1], saved_paths, path_keys)
                    if not (0 <= src < len(saved_paths)):
                        print(_bad_folder_arg(parts[0]))
                    elif not (0 <= dst < len(saved_paths)):
                        print(_bad_folder_arg(parts[1]))
                    elif src == dst:
                        print("  [!] Source and destination are the same folder.")
                    else:
                        item = saved_paths.pop(src)
                        saved_paths.insert(dst, item)

                        # Update all tracked indices to reflect the move.
                        # Items between src and dst shift by ±1; src itself lands at dst.
                        def _adjust_for_insert(v: int) -> int:
                            if v == src:
                                return dst
                            if src < dst and src < v <= dst:
                                return v - 1
                            if src > dst and dst <= v < src:
                                return v + 1
                            return v

                        for key in ("default_folder_index", "default_save_index"):
                            prefs[key] = _adjust_for_insert(prefs.get(key, 0))
                        _sfi[0] = _adjust_for_insert(_sfi[0])

                        save_paths(saved_paths, path_keys, prefs)
                        print(f"  ✔  Moved [{src+1}] to position [{dst+1}].")
                        print_paths(saved_paths, path_keys, cache, folder, _sfi[0], prefs.get("default_folder_index", 0))
                else:
                    print("  [!] Usage: path insert <#|key> <#|key>")

            # path rename <#|key> <new_path>
            elif rest_lower.startswith("rename "):
                parts = rest_orig[7:].strip().split(None, 1)
                if len(parts) == 2:
                    n        = _resolve_folder_arg(parts[0], saved_paths, path_keys)
                    new_path = parts[1].strip().strip('"')
                    if 0 <= n < len(saved_paths):
                        old = saved_paths[n]
                        saved_paths[n] = new_path
                        if old in path_keys:
                            path_keys[new_path] = path_keys.pop(old)
                        save_paths(saved_paths, path_keys, prefs)
                        if old in cache:
                            del cache[old]
                            save_cache(cache)
                        print(f"  ✔  [{n+1}] {old}  →  {new_path}")
                        print(f"  ℹ  Old cache cleared. Run 'scan {n+1}' to scan the new path.")
                        print_paths(saved_paths, path_keys, cache, folder, _sfi[0], prefs.get("default_folder_index", 0))
                    else:
                        print(_bad_folder_arg(parts[0]))
                else:
                    print("  [!] Usage: path rename <#|key> <new path>")

            # path <#> — switch to folder by number
            elif rest.isdigit():
                n = int(rest) - 1
                if 0 <= n < len(saved_paths):
                    load(saved_paths[n])
                else:
                    print(f"  [!] Number out of range (1–{len(saved_paths)}).")

            # path <key> — switch to folder by key
            elif rest and not rest.startswith(("-", "/")):
                target_path = _path_for_key(rest, saved_paths, path_keys)
                if target_path is not None:
                    load(target_path)
                else:
                    print(f"  [?] No folder with key '{rest}'. Use 'paths' to list folders, or 'key <#> <key>' to assign one.")

            # bare "path" → show list
            elif rest == "":
                print_paths(saved_paths, path_keys, cache, folder, _sfi[0], prefs.get("default_folder_index", 0))

            else:
                print("  [?] Unknown path subcommand. Options: add, del, rename, swap, insert, or a number/key.")

        # ── Key management ─────────────────────────────────────────────────
        elif cmd.startswith("key"):
            key_sub      = cmd[3:].strip()
            key_sub_orig = raw[3:].strip()

            if key_sub and not key_sub.startswith(("del", "rename", "swap")):
                parts = key_sub_orig.split(None, 1)
                if len(parts) == 2 and parts[0].isdigit():
                    n       = int(parts[0]) - 1
                    new_key = parts[1].strip()
                    if not (0 <= n < len(saved_paths)):
                        print(f"  [!] Number out of range (1–{len(saved_paths)}).")
                    elif " " in new_key:
                        print("  [!] Keys cannot contain spaces.")
                    elif _key_in_use(new_key, path_keys) and path_keys.get(saved_paths[n], "").lower() != new_key.lower():
                        print(f"  [!] Key '{new_key}' is already used by another folder.")
                    else:
                        target_path = saved_paths[n]
                        old_key     = path_keys.get(target_path)
                        path_keys[target_path] = new_key
                        save_paths(saved_paths, path_keys, prefs)
                        if old_key:
                            print(f"  🔑 [{n+1}] key changed: '{old_key}' → '{new_key}'")
                        else:
                            print(f"  🔑 [{n+1}] key set: '{new_key}'  →  {target_path}")
                else:
                    print("  [!] Usage: key <#> <key>")

            elif key_sub.startswith("del "):
                idx_str = key_sub[4:].strip()
                if idx_str.isdigit():
                    n = int(idx_str) - 1
                    if 0 <= n < len(saved_paths):
                        old_key = path_keys.pop(saved_paths[n], None)
                        if old_key:
                            save_paths(saved_paths, path_keys, prefs)
                            print(f"  🔑 [{n+1}] key '{old_key}' removed.")
                        else:
                            print(f"  [!] Folder [{n+1}] has no key assigned.")
                    else:
                        print(f"  [!] Number out of range (1–{len(saved_paths)}).")
                else:
                    print("  [!] Usage: key del <#>")

            elif key_sub.startswith("rename "):
                parts = key_sub_orig[7:].strip().split(None, 1)
                if len(parts) == 2 and parts[0].isdigit():
                    n       = int(parts[0]) - 1
                    new_key = parts[1].strip()
                    if not (0 <= n < len(saved_paths)):
                        print(f"  [!] Number out of range (1–{len(saved_paths)}).")
                    elif " " in new_key:
                        print("  [!] Keys cannot contain spaces.")
                    elif _key_in_use(new_key, path_keys) and path_keys.get(saved_paths[n], "").lower() != new_key.lower():
                        print(f"  [!] Key '{new_key}' is already used by another folder.")
                    else:
                        target_path = saved_paths[n]
                        old_key     = path_keys.get(target_path)
                        if not old_key:
                            print(f"  [!] Folder [{n+1}] has no key. Use 'key {n+1} <key>' to set one.")
                        else:
                            path_keys[target_path] = new_key
                            save_paths(saved_paths, path_keys, prefs)
                            print(f"  🔑 [{n+1}] key renamed: '{old_key}' → '{new_key}'")
                else:
                    print("  [!] Usage: key rename <#> <new_key>")

            elif key_sub.startswith("swap "):
                parts = key_sub[5:].strip().split()
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    a, b = int(parts[0]) - 1, int(parts[1]) - 1
                    if not (0 <= a < len(saved_paths)):
                        print(f"  [!] Number out of range (1–{len(saved_paths)}).")
                    elif not (0 <= b < len(saved_paths)):
                        print(f"  [!] Number out of range (1–{len(saved_paths)}).")
                    elif a == b:
                        print("  [!] Can't swap a folder's key with itself.")
                    else:
                        pa, pb = saved_paths[a], saved_paths[b]
                        key_a  = path_keys.get(pa)
                        key_b  = path_keys.get(pb)
                        if key_b: path_keys[pa] = key_b
                        else:     path_keys.pop(pa, None)
                        if key_a: path_keys[pb] = key_a
                        else:     path_keys.pop(pb, None)
                        save_paths(saved_paths, path_keys, prefs)
                        ka_str = f"'{key_a}'" if key_a else "(none)"
                        kb_str = f"'{key_b}'" if key_b else "(none)"
                        print(f"  🔑 Keys swapped: [{a+1}] {ka_str} ↔ [{b+1}] {kb_str}")
                else:
                    print("  [!] Usage: key swap <#> <#>")

            else:
                print("  [?] Usage:  key <#> <key>  |  key del <#>  |  key rename <#> <new_key>  |  key swap <#> <#>")

        # ── Temporary folder (unsaved) ─────────────────────────────────────
        elif cmd.startswith("folder "):
            new_path = raw[7:].strip().strip('"')
            load(new_path)

        # ── Normal mode ────────────────────────────────────────────────────
        elif cmd == "normal":
            mem_mode = False
            _cancel_timer()
            print("  ► Normal mode.")

        # ── Memory mode ────────────────────────────────────────────────────
        elif cmd == "mem" or cmd.startswith("mem "):
            mem_mode  = True
            remainder = raw[3:].strip()
            if remainder:
                parsed      = time_string_to_seconds(remainder)
                mem_seconds = parsed if parsed > 0 else default_mem_time
            else:
                mem_seconds = default_mem_time
            print(f"  ► Memory mode — {fmt_time(mem_seconds)} per image.")
            # Always open the next image when entering/re-entering mem mode.
            # The whole point of the command is: show image → cover it after
            # <time>. Using start_mem_timer alone (without show_next) would
            # fire a blank tab with nothing to cover.
            show_next()

        # ── Clean ──────────────────────────────────────────────────────────
        elif cmd == "clean" or cmd.startswith("clean "):
            sub = raw[5:].strip()

            if sub == "":
                _clean_directory(folder)
            elif sub.lower().startswith("path "):
                _clean_directory(sub[5:].strip().strip('"'))
            else:
                # Accept a number or a key
                n = _resolve_folder_arg(sub, saved_paths, path_keys)
                if 0 <= n < len(saved_paths):
                    _clean_directory(saved_paths[n])
                elif sub:
                    print(_bad_folder_arg(sub))
                else:
                    print("  [?] Usage:  clean  |  clean <#|key>  |  clean path <dir>")

        # ── Enter → next image ─────────────────────────────────────────────
        elif cmd == "":
            show_next()

        else:
            print(f"  [?] Unknown command: '{raw}'. Type 'help' for options.")


if __name__ == "__main__":
    main()
