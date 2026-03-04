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

_FALLBACK_FIREFOX_PATH     = r"C:\Program Files\Mozilla Firefox\firefox.exe"
_FALLBACK_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tiff"}
_FALLBACK_MEM_TIME         = 30   # seconds
_FALLBACK_SEARCH_RESULTS   = 20   # max results returned by the search command

# Module-level globals — overwritten by apply_settings() at startup
FIREFOX_PATH        = _FALLBACK_FIREFOX_PATH
IMAGE_EXTENSIONS    = _FALLBACK_IMAGE_EXTENSIONS
SEARCH_MAX_RESULTS  = _FALLBACK_SEARCH_RESULTS

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PATHS_FILE  = os.path.join(_SCRIPT_DIR, "ref_paths.json")
CACHE_FILE  = os.path.join(_SCRIPT_DIR, "ref_cache.pkl")
# cache schema: dict[str, list[str]]  →  { folder_path: [img_path, ...] }

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
    Returns (paths, keys, prefs).

    prefs holds user-changeable persistent defaults:
      default_folder_index  int  – which saved path to load on startup
      default_save_index    int  – which saved path 'save' copies into

    File format (current):
      {
        "folders": [{"path": "...", "key": "xx"}, {"path": "..."}],
        "default_folder_index": 0,
        "default_save_index":   0
      }
    Legacy formats (auto-migrated on next save):   # TODO: remove the legacy formats
      plain list of path strings
      {"paths": [...], "keys": {...}, ...}
    """
    default_prefs: dict = {
        "default_folder_index": 0,
        "default_save_index":   0,
    }

    if os.path.exists(PATHS_FILE):
        try:
            with open(PATHS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Legacy format 1: plain list of path strings
            if isinstance(data, list):
                paths = [str(p) for p in data]
                return paths, {}, default_prefs

            if isinstance(data, dict):
                # # Legacy format 2: separate "paths" list + "keys" dict
                # if "paths" in data and "folders" not in data:
                #     paths    = [str(p) for p in data.get("paths", [])]
                #     raw_keys = data.get("keys", {})
                #     keys     = {str(k): str(v) for k, v in raw_keys.items() if v}
                #     prefs    = {
                #         "default_folder_index": int(data.get("default_folder_index", 0)),
                #         "default_save_index":   int(data.get("default_save_index", 0)),
                #     }
                #     return paths, keys, prefs

                # Current format: list of folder objects
                if "folders" in data:
                    paths = []
                    keys  = {}
                    for entry in data["folders"]:
                        p = str(entry.get("path", ""))
                        if not p:
                            continue
                        paths.append(p)
                        k = entry.get("key", "")
                        if k:
                            keys[p] = str(k)
                    prefs = {
                        "default_folder_index": int(data.get("default_folder_index", 0)),
                        "default_save_index":   int(data.get("default_save_index", 0)),
                    }
                    return paths, keys, prefs

        except Exception:
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

def _key_for(path: str, keys: dict[str, str]) -> str | None:
    return keys.get(path)


def _path_for_key(key: str, paths: list[str], keys: dict[str, str]) -> str | None:
    key_lower = key.lower()
    for path in paths:
        if keys.get(path, "").lower() == key_lower:
            return path
    return None


def _key_in_use(key: str, keys: dict[str, str]) -> bool:
    key_lower = key.lower()
    return any(v.lower() == key_lower for v in keys.values())


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


def open_path_in_firefox(path: str):
    if not os.path.exists(path):
        print(f"  [!] File not found: {path}")
        return
    img_url = "file:///" + urllib.parse.quote(os.path.abspath(path).replace("\\", "/"))
    if "firefox" not in REGISTERED_BROWSERS:
        webbrowser.register(
            "firefox", None,
            webbrowser.BackgroundBrowser(FIREFOX_PATH)
        )
        REGISTERED_BROWSERS.add("firefox")
    webbrowser.get("firefox").open(img_url)


def open_black_tab():
    webbrowser.get("firefox").open("about:newtab", new=2)


def fmt_time(seconds: int) -> str:
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    parts = []
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s or not parts: parts.append(f"{s}s")
    return " ".join(parts)


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
            # Each keyword contributes its weight at most once — repeated
            # occurrences of the same keyword don't add anything, but each
            # distinct keyword that matches does.
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
            print("Press <Enter> for next image, or type a command: ", end="", flush=True)


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
  <Enter>              → next random image
  mem                  → memory mode (uses default time)
  mem 30s / mem 1m30s  → memory mode with custom time
  normal               → switch back to normal mode
  shuffle              → reshuffle the image list
  info                 → show current session settings

  cycle [interval] [total]
                       → gesture-drawing session: auto-advance
                         images every <interval>, stop after
                         <total> (prompts if omitted)
                         e.g.  cycle 30s 10m
                               cycle 2m 1h
  stop                 → stop an active cycle session

  search <keywords>    → search loaded images by filename/path
                         keywords; opens matches one by one.
                         Press <Enter> to advance, 'stop' to
                         exit search mode. Max results come
                         from settings (search_max_results).
                         e.g.  search hand pose
                               search torso front

  save                 → copy current image to the save folder

  compress             → compress current image
  compress folder      → compress all images in current folder
  compress path <#>    → compress a saved folder by number
  compress dir <path>  → compress any folder by path

  prompt               → random drawing prompt
  prompt daily         → full daily plan
  prompt list          → list all prompt types
  prompt <type>        → specific prompt (see 'prompt list')

  paths                → list all saved folders
  path <#|key>         → switch to folder by number or key
  path add <path>      → add & scan a new folder
  path del <#>         → remove folder + its cache
  path rename <#> <p>  → replace a saved path
  path swap <#> <#>    → swap two folders by number

  key <#> <key>        → assign a shortcut key to a folder
  key del <#>          → remove the key from a folder
  key rename <#> <key> → rename a folder's key
  key swap <#> <#>     → swap keys between two folders

  scan                 → re-scan current folder
  scan <#|key>         → re-scan a specific saved folder

  clean                → check current folder for non-media files
  clean <#>            → check a saved folder by number
  clean path <path>    → check any folder by path

  set mem <time>       → set default mem time (persistent)
                         e.g.  set mem 45s  |  set mem 2m
  set search <n>       → set max search results (persistent)
                         e.g.  set search 10  |  set search 50
  set folder <#|key>   → set default startup folder (persistent)
  set save   <#|key>   → set default save folder (persistent)
  set                  → show current defaults & loaded settings

  folder <path>        → load folder temporarily (not added)
  help                 → show this message
  clear                → clear the screen
  q / quit / exit      → quit
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
        cached_str     = f"{len(cache[p])} imgs" if p in cache else "not scanned"
        key            = path_keys.get(p)
        key_str        = f"[key: {key}]" if key else ""
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

    default_mem_time:   int = int(settings.get("default_mem_time",   _FALLBACK_MEM_TIME))
    search_max_results: int = int(settings.get("search_max_results", _FALLBACK_SEARCH_RESULTS))

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
    mem_mode    = False
    mem_seconds = default_mem_time
    current_image: str | None = None

    # Clamp save_folder_index to valid range.
    # Stored as a one-element list so nested scopes can mutate it without nonlocal.
    _sfi_val: int = prefs.get("default_save_index", 0)
    if saved_paths:
        _sfi_val = max(0, min(_sfi_val, len(saved_paths) - 1))
    _sfi: list[int] = [_sfi_val]   # _sfi[0] is the live save_folder_index

    # ── Load images for a folder (cache-first, or scan if missing) ─────────
    def load(path: str, force_scan: bool = False) -> bool:
        nonlocal images, index, folder

        if not path:
            print("  [!] No folder specified.")
            return False

        if not force_scan and path in cache:
            imgs    = cache[path]
            key     = path_keys.get(path)
            key_str = f"  [key: {key}]" if key else ""
            print(f"  ✔  Loaded {len(imgs)} images from cache: {path}{key_str}")
        else:
            imgs = do_scan(path, cache)
            if imgs is None:
                return False

        folder = path
        images = list(imgs)
        random.shuffle(images)
        index  = 0
        return True

    print("=" * 56)
    print("  Ref Viewer  —  Drawing Practice Tool")
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
        if not images:
            print("  [!] No images loaded. Use 'path add <path>' or 'folder <path>'.")
            return
        if index >= len(images):
            random.shuffle(images)
            index = 0
            print("  ↺  Reshuffled image list.")
        path = images[index]
        index += 1
        current_image = path
        name = os.path.relpath(path, folder) if folder else path
        if print_flag:
            print(f"  [{index}/{len(images)}]  {name}")
        open_path_in_firefox(path)
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
        elif cmd == "help":
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
            print(f"  Folder : {folder}{key_str}")
            print(f"  Images : {img_str}")
            print(f"  Mode   : {mode_str}{cycle_str}")
            print(f"  Save → : [{_sfi[0] + 1}] {save_dest}")

        # ── Shuffle ────────────────────────────────────────────────────────
        elif cmd == "shuffle":
            random.shuffle(images)
            index = 0
            print("  ↺  Reshuffled.")

        # ── Stop cycle ─────────────────────────────────────────────────────
        elif cmd == "stop":
            if _cycle_thread and _cycle_thread.is_alive():
                _cancel_cycle()
                print("  ■  Cycle session stopped.")
            else:
                print("  [!] No active cycle session.")

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
                    default_mem_time                  = parsed
                    settings["default_mem_time"]      = parsed
                    save_settings(settings, settings_file)
                    print(f"  ✔  Default mem time → {fmt_time(parsed)}  (saved to settings.json).")

            # set search <n>
            elif sub_lower.startswith("search "):
                arg = sub[7:].strip()
                if arg.isdigit() and int(arg) > 0:
                    n = int(arg)
                    search_max_results                 = n
                    settings["search_max_results"]     = n
                    save_settings(settings, settings_file)
                    print(f"  ✔  Search max results → {n}  (saved to settings.json).")
                else:
                    print("  [!] Usage: set search <positive number>")

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
                    print(f"  [!] Number out of range (1\u2013{len(saved_paths)}).")
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
                    print(f"  [!] Number out of range (1\u2013{len(saved_paths)}).")
                else:
                    print(f"  [!] No folder with key '{arg}'.")


            # bare "set" → show current config
            elif sub_lower == "":
                di = prefs.get("default_folder_index", 0)
                df = saved_paths[di] if saved_paths and 0 <= di < len(saved_paths) else "(none)"
                si = prefs.get("default_save_index", 0)
                sf = saved_paths[si] if saved_paths and 0 <= si < len(saved_paths) else "(none)"
                print(f"\n  Settings  ({settings_file}):")
                print(f"    Firefox path     : {FIREFOX_PATH}")
                print(f"    Image extensions : {', '.join(sorted(IMAGE_EXTENSIONS))}")
                print(f"    Default mem time : {fmt_time(default_mem_time)}")
                print(f"    Search max results: {search_max_results}")
                print(f"\n  Folder prefs  (ref_paths.json):")
                print(f"    Startup folder   : [{di + 1}] {df}")
                print(f"    Save folder      : [{si + 1}] {sf}")
                print()
            else:
                print("  [?] Usage:  set mem <time>  |  set search <n>  |  set folder <#>  |  set save <#>  |  set")

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
            sub = cmd[8:].strip()

            if sub in ("", "image"):
                if current_image is None:
                    print("  [!] No image has been opened yet.")
                elif not _compress.should_compress(current_image):
                    print("  [!] Image doesn't meet compression criteria (too small or already optimised).")
                else:
                    original_size = os.path.getsize(current_image)
                    print("  🗜  Compressing current image …", end="", flush=True)
                    ok = _compress.compress_image(current_image, quality=85, backup=False)
                    if ok:
                        new_size = os.path.getsize(current_image)
                        saved_mb = (original_size - new_size) / (1024 * 1024)
                        pct      = saved_mb / (original_size / (1024 * 1024)) * 100
                        print(f" done — saved {saved_mb:.2f} MB ({pct:.1f}%)")
                    else:
                        print(" failed.")

            elif sub == "folder":
                target = folder
                def _run_compress(path):
                    print(f"\n  🗜  Compressing folder: {path}")
                    _compress.process_directory(path, quality=85)
                    print(f"\n  ✔  Compression finished: {path}")
                    print("  > ", end="", flush=True)
                threading.Thread(target=_run_compress, args=(target,), daemon=True).start()

            elif sub.startswith("path "):
                idx_str = sub[5:].strip()
                if idx_str.isdigit():
                    n = int(idx_str) - 1
                    if 0 <= n < len(saved_paths):
                        target = saved_paths[n]
                        def _run_compress_path(path):
                            print(f"\n  🗜  Compressing folder [{n+1}]: {path}")
                            _compress.process_directory(path, quality=85)
                            print(f"\n  ✔  Compression finished: {path}")
                            print("  > ", end="", flush=True)
                        threading.Thread(target=_run_compress_path, args=(target,), daemon=True).start()
                    else:
                        print(f"  [!] Number out of range (1–{len(saved_paths)}).")
                else:
                    print("  [!] Usage: compress path <number>")

            elif sub.startswith("dir "):
                target = sub[4:].strip().strip('"')
                if not os.path.isdir(target):
                    print(f"  [!] Directory not found: {target}")
                else:
                    def _run_compress_dir(path):
                        print(f"\n  🗜  Compressing: {path}")
                        _compress.process_directory(path, quality=85)
                        print(f"\n  ✔  Compression finished: {path}")
                        print("  > ", end="", flush=True)
                    threading.Thread(target=_run_compress_dir, args=(target,), daemon=True).start()

            else:
                print("  [?] Usage: compress  |  compress folder  |  compress path <#>  |  compress dir <path>")

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
            if not images:
                print("  [!] No images loaded. Use 'path add <path>' or 'folder <path>'.")
                continue

            keywords_str = raw[6:].strip()

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
            results  = search_images(images, keywords, search_max_results)

            if not results:
                print(f"  [!] No results for: '{keywords_str}'")
                continue

            print(
                f"  🔍 {len(results)} result(s) for '{keywords_str}' "
                f"(max {search_max_results})."
            )
            print("  Press <Enter> to view each image, or 'stop' to exit search.")

            search_idx = 0
            while search_idx < len(results):
                img_path      = results[search_idx]
                current_image = img_path
                name          = os.path.relpath(img_path, folder) if folder else img_path
                print(f"\n  [{search_idx + 1}/{len(results)}]  {name}")
                open_path_in_firefox(img_path)
                if mem_mode:
                    start_mem_timer(mem_seconds)

                search_idx += 1

                # Last result — no further prompt needed
                if search_idx >= len(results):
                    print(f"  ✔  End of search results.")
                    break

                # Prompt for next action
                try:
                    nxt = input("\n(search)> ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    _cancel_timer()
                    print("\n  [!] Search ended.")
                    break

                if nxt == "stop":
                    _cancel_timer()
                    print("  ■  Search stopped.")
                    break
                elif nxt == "":
                    continue   # advance to the next result
                else:
                    # Anything else: warn and stay on the same index to re-prompt
                    print(f"  [!] In search mode — press <Enter> for next image or 'stop' to exit.")
                    search_idx -= 1   # undo the advance so the same image shows again

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
        elif cmd == "paths":
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

            # path del <#>
            elif rest_lower.startswith("del "):
                idx_str = rest[4:].strip()
                try:
                    n = int(idx_str) - 1
                    if 0 <= n < len(saved_paths):
                        removed = saved_paths.pop(n)
                        path_keys.pop(removed, None)

                        # Adjust persistent indices
                        def _adjust_index(key: str):
                            v = prefs.get(key, 0)
                            if v == n:
                                prefs[key] = 0
                            elif v > n:
                                prefs[key] = v - 1

                        _adjust_index("default_folder_index")
                        _adjust_index("default_save_index")

                        if _sfi[0] == n:
                            _sfi[0] = 0
                            print("  ℹ  Save folder reset to [1].")
                        elif _sfi[0] > n:
                            _sfi[0] -= 1

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
                        print(f"  [!] Number out of range (1–{len(saved_paths)}).")
                except ValueError:
                    print("  [!] Usage: path del <number>")

            # path swap <#> <#>
            elif rest_lower.startswith("swap "):
                parts = rest[5:].strip().split()
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    a, b = int(parts[0]) - 1, int(parts[1]) - 1
                    if not (0 <= a < len(saved_paths)):
                        print(f"  [!] Number out of range (1–{len(saved_paths)}).")
                    elif not (0 <= b < len(saved_paths)):
                        print(f"  [!] Number out of range (1–{len(saved_paths)}).")
                    elif a == b:
                        print("  [!] Can't swap a folder with itself.")
                    else:
                        saved_paths[a], saved_paths[b] = saved_paths[b], saved_paths[a]

                        # Keep all index references pointing at the same logical folder
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
                    print("  [!] Usage: path swap <#> <#>")

            # path rename <#> <new_path>
            elif rest_lower.startswith("rename "):
                parts = rest_orig[7:].strip().split(None, 1)
                if len(parts) == 2:
                    try:
                        n        = int(parts[0]) - 1
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
                            print(f"  [!] Number out of range (1–{len(saved_paths)}).")
                    except ValueError:
                        print("  [!] Usage: path rename <number> <new path>")
                else:
                    print("  [!] Usage: path rename <number> <new path>")

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
                print("  [?] Unknown path subcommand. Options: add, del, rename, swap, or a number/key.")

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
            show_next()

        # ── Clean ──────────────────────────────────────────────────────────
        elif cmd == "clean" or cmd.startswith("clean "):
            sub = raw[5:].strip()

            if sub == "":
                _clean_directory(folder)
            elif sub.isdigit():
                n = int(sub) - 1
                if 0 <= n < len(saved_paths):
                    _clean_directory(saved_paths[n])
                else:
                    print(f"  [!] Number out of range (1–{len(saved_paths)}).")
            elif sub.lower().startswith("path "):
                _clean_directory(sub[5:].strip().strip('"'))
            else:
                print("  [?] Usage:  clean  |  clean <#>  |  clean path <dir>")

        # ── Enter → next image ─────────────────────────────────────────────
        elif cmd == "":
            show_next()

        else:
            print(f"  [?] Unknown command: '{raw}'. Type 'help' for options.")


if __name__ == "__main__":
    main()
