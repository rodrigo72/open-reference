import os
import re
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

# ── Config ───────────────────────────────────────────────────────────────────

DEFAULT_FOLDER   = r"C:\Users\rodri\Desktop\Refs\RefsVM"
FIREFOX_PATH     = r"C:\Program Files\Mozilla Firefox\firefox.exe"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tiff"}
DEFAULT_MEM_TIME = 30   # seconds

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PATHS_FILE   = os.path.join(_SCRIPT_DIR, "ref_paths.json")
CACHE_FILE   = os.path.join(_SCRIPT_DIR, "ref_cache.pkl")
# cache schema: dict[str, list[str]]  →  { folder_path: [img_path, ...] }

REGISTERED_BROWSERS: set = set()

# ── Cache helpers ─────────────────────────────────────────────────────────────

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


# ── Saved-paths persistence ───────────────────────────────────────────────────

def load_saved_paths() -> tuple[list[str], dict[str, str]]:
    """
    Returns (paths, keys) where keys maps path → key string.
    Supports both the legacy list format and the new dict format.
    """
    if os.path.exists(PATHS_FILE):
        try:
            with open(PATHS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Legacy format: plain list of path strings
            if isinstance(data, list):
                paths = [str(p) for p in data]
                return paths, {}
            # New format: {"paths": [...], "keys": {path: key, ...}}
            if isinstance(data, dict):
                paths = [str(p) for p in data.get("paths", [])]
                raw_keys = data.get("keys", {})
                keys = {str(k): str(v) for k, v in raw_keys.items() if v}
                return paths, keys
        except Exception:
            pass
    return [DEFAULT_FOLDER], {}


def save_paths(paths: list[str], keys: dict[str, str]):
    data = {
        "paths": paths,
        "keys":  {p: k for p, k in keys.items() if k},   # omit blank keys
    }
    with open(PATHS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Key helpers ───────────────────────────────────────────────────────────────

def _key_for(path: str, keys: dict[str, str]) -> str | None:
    """Return the key assigned to *path*, or None."""
    return keys.get(path)


def _path_for_key(key: str, paths: list[str], keys: dict[str, str]) -> str | None:
    """Return the path that owns *key* (case-insensitive), or None."""
    key_lower = key.lower()
    for path in paths:
        if keys.get(path, "").lower() == key_lower:
            return path
    return None


def _key_in_use(key: str, keys: dict[str, str]) -> bool:
    """True if *key* is already assigned to any path."""
    key_lower = key.lower()
    return any(v.lower() == key_lower for v in keys.values())


# ── Helpers ───────────────────────────────────────────────────────────────────

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
    webbrowser.get("firefox").open('about:newtab', new=2)


def fmt_time(seconds: int) -> str:
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    parts = []
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s or not parts: parts.append(f"{s}s")
    return " ".join(parts)

# ── Unwanted-file helpers ─────────────────────────────────────────────────────

MEDIA = {
    '.png', '.webp', '.jpeg', '.jpg', '.tiff', '.bmp',
    '.mp4', '.mp3', '.wav', '.pdf', '.tif', '.srt', '.psd',
    '.mp4a', '.zip', '.m4v', '.clip', '.kra', '.grd',
    '.abr', '.blend', '.rar',
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


# ── Memory-mode timer ─────────────────────────────────────────────────────────

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


# ── Cycle mode ────────────────────────────────────────────────────────────────

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
        self.interval      = interval
        self.total         = total
        self.show_next_fn  = show_next_fn
        self.cancel_flag   = False

    def _wait(self, seconds: float) -> bool:
        """Sleep in small steps; return False if cancelled before the wait ends."""
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

            self.show_next_fn()
            images_shown += 1

            # Don't wait past the end of the session
            remaining = self.total - session_elapsed
            wait_for  = min(self.interval, remaining)

            if not self._wait(wait_for):
                return                          # cancelled mid-wait

            session_elapsed += self.interval

        if not self.cancel_flag:
            open_black_tab()
            print(
                f"\n  ● Cycle complete — {images_shown} image(s) "
                f"in {fmt_time(self.total)}. Black tab opened."
            )
            print("Press <Enter> for next image, or type a command: ", end="", flush=True)


# ── Main loop ─────────────────────────────────────────────────────────────────

HELP_TEXT = """
Commands
────────────────────────────────────────────────────────
  <Enter>              → next random image
  mem                  → memory mode (default {default}s)
  mem 30s / mem 1m30s  → memory mode with custom time
  normal               → switch back to normal mode
  shuffle              → reshuffle the image list
  info                 → show current settings

  cycle [interval] [total]
                       → gesture-drawing session: auto-advance
                         images every <interval>, stop after
                         <total> (prompts if omitted)
                         e.g.  cycle 30s 10m
                               cycle 2m 1h
  stop                 → stop an active cycle session

  save                 → copy current image to the save folder
  saveto <#>           → change save destination to folder [#]

  compress             → compress current image
  compress folder      → compress all images in current folder
  compress path <#>    → compress a saved folder by number
  compress dir <path>  → compress any folder by path

  prompt               → random drawing prompt
  prompt daily         → full daily plan
  prompt list          → list all prompt types
  prompt <type>        → specific prompt (see 'prompt list')

  paths                → list all saved folders
  path <# or key>      → switch to folder by number or key
  path add <path>      → add & scan a new folder
  path del <#>         → remove folder + its cache
  path rename <#> <p>  → replace a saved path
  path swap <#> <#>    → swap two folders by number

  key <#> <key>        → assign a shortcut key to a folder
  key del <#>          → remove the key from a folder
  key rename <#> <key> → rename a folder's key
  key swap <#> <#>     → swap keys between two folders

  scan                 → re-scan current folder
  scan <#>             → re-scan a specific saved folder
  
  clean                → check current folder for non-media files
  clean <#>            → check a saved folder by number
  clean path <path>    → check any folder by path

  folder <path>        → load folder temporarily (no save)
  help                 → show this message
  clear                → clear the screen
  q / quit / exit      → quit
────────────────────────────────────────────────────────
""".format(default=DEFAULT_MEM_TIME)


def print_paths(saved_paths: list[str], path_keys: dict[str, str], cache: dict, active_folder: str, save_folder_index: int):
    print(f"\n  Saved folders ({len(saved_paths)}):")
    for i, p in enumerate(saved_paths, 1):
        browse_marker = "►" if p == active_folder else " "
        save_marker   = "💾" if (i - 1) == save_folder_index else "  "
        cached_str    = f"{len(cache[p])} imgs" if p in cache else "not scanned"
        key           = path_keys.get(p)
        key_str       = f"  [key: {key}]" if key else ""
        print(f"  {save_marker} {browse_marker} [{i}] {p}  ({cached_str}){key_str}")
    print()


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
    global _cycle_thread
    saved_paths, path_keys = load_saved_paths()
    cache: dict[str, list[str]] = load_cache()

    folder  = saved_paths[0]
    images: list[str] = []
    index   = 0
    mem_mode     = False
    mem_seconds  = DEFAULT_MEM_TIME
    current_image: str | None = None
    save_folder_index: int = 0   # index into saved_paths used by 'save'

    # ── Load images for a folder (cache-first, or scan if missing) ────────
    def load(path: str, force_scan: bool = False) -> bool:
        nonlocal images, index, folder

        if not force_scan and path in cache:
            imgs = cache[path]
            key  = path_keys.get(path)
            key_str = f"  [key: {key}]" if key else ""
            print(f"  ✔  Loaded {len(imgs)} images from cache: {path}{key_str}")
        else:
            imgs = do_scan(path, cache)
            if imgs is None:
                return False

        folder = path
        images = list(imgs)          # copy so shuffling doesn't mutate the cache
        random.shuffle(images)
        index  = 0
        return True

    print("=" * 56)
    print("  Ref Viewer  —  Drawing Practice Tool")
    print("=" * 56)
    print(HELP_TEXT)

    if not load(folder):
        new = input("Enter a folder path to start: ").strip().strip('"')
        if not load(new):
            print("Could not load any images. Exiting.")
            return

    def show_next():
        nonlocal index, current_image
        _cancel_timer()
        if index >= len(images):
            random.shuffle(images)
            index = 0
            print("  ↺  Reshuffled image list.")
        path = images[index]
        index += 1
        current_image = path
        name = os.path.relpath(path, folder)
        print(f"  [{index}/{len(images)}]  {name}")
        open_path_in_firefox(path)
        if mem_mode:
            start_mem_timer(mem_seconds)

    while True:
        try:
            raw = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n~~")
            _cancel_timer()
            _cancel_cycle()
            break

        cmd = raw.lower()

        # ── Block commands while a cycle is active ────────────────────────
        cycle_active = _cycle_thread is not None and _cycle_thread.is_alive()
        if cycle_active and cmd not in ("stop", "q", "quit", "exit", "info"):
            print("  [!] Cycle in progress — type 'stop' to end it.")
            continue

        # ── Quit ──────────────────────────────────────────────────────────
        if cmd in ("q", "quit", "exit"):
            print("  ~~")
            _cancel_timer()
            _cancel_cycle()
            break

        # ── Help ──────────────────────────────────────────────────────────
        elif cmd == "help":
            print(HELP_TEXT)

        # ── Clear ─────────────────────────────────────────────────────────
        elif cmd == "clear" or cmd == "cls":
            os.system('cls' if os.name == 'nt' else 'clear')

        # ── Info ──────────────────────────────────────────────────────────
        elif cmd == "info":
            mode_str = f"memory ({fmt_time(mem_seconds)})" if mem_mode else "normal"
            cycle_str = ""
            if _cycle_thread and _cycle_thread.is_alive():
                cycle_str = (
                    f"\n  Cycle  : {fmt_time(_cycle_thread.interval)}/image, "
                    f"{fmt_time(_cycle_thread.total)} total"
                )
            save_dest = saved_paths[save_folder_index] if save_folder_index < len(saved_paths) else "(none)"
            active_key = path_keys.get(folder)
            key_str = f"  [key: {active_key}]" if active_key else ""
            print(f"  Folder : {folder}{key_str}")
            print(f"  Images : {len(images)}")
            print(f"  Mode   : {mode_str}{cycle_str}")
            print(f"  Save → : [{save_folder_index + 1}] {save_dest}")

        # ── Shuffle ───────────────────────────────────────────────────────
        elif cmd == "shuffle":
            random.shuffle(images)
            index = 0
            print("  ↺  Reshuffled.")

        # ── Stop cycle ────────────────────────────────────────────────────
        elif cmd == "stop":
            if _cycle_thread and _cycle_thread.is_alive():
                _cancel_cycle()
                print("  ■  Cycle session stopped.")
            else:
                print("  [!] No active cycle session.")

        # ── Save current image to the chosen save folder ──────────────────
        elif cmd == "save":
            if current_image is None:
                print("  [!] No image has been opened yet.")
            elif save_folder_index >= len(saved_paths):
                print(f"  [!] Save folder [{save_folder_index + 1}] no longer exists. Use 'saveto <#>' to pick another.")
            else:
                dest_folder = saved_paths[save_folder_index]
                if os.path.abspath(current_image).startswith(os.path.abspath(dest_folder) + os.sep):
                    print(f"  [!] Image is already in the save folder [{save_folder_index + 1}].")
                else:
                    os.makedirs(dest_folder, exist_ok=True)
                    base, ext  = os.path.splitext(os.path.basename(current_image))
                    dest       = os.path.join(dest_folder, base + ext)
                    counter    = 1
                    while os.path.exists(dest):
                        dest = os.path.join(dest_folder, f"{base}_{counter}{ext}")
                        counter += 1
                    shutil.copy2(current_image, dest)
                    print(f"  ✔  Saved → {os.path.relpath(dest, dest_folder)}  (in [{save_folder_index + 1}] {dest_folder})")
                    # Update cache so next scan picks it up
                    if dest_folder in cache:
                        cache[dest_folder].append(dest)
                        save_cache(cache)

        # ── saveto <#>: change save destination folder ────────────────────
        elif cmd.startswith("saveto "):
            idx_str = cmd[7:].strip()
            if idx_str.isdigit():
                n = int(idx_str) - 1
                if 0 <= n < len(saved_paths):
                    save_folder_index = n
                    print(f"  💾 Save folder set to [{n + 1}] {saved_paths[n]}")
                else:
                    print(f"  [!] Number out of range (1–{len(saved_paths)}).")
            else:
                print("  [!] Usage: saveto <number>")

        # ── Cycle mode ────────────────────────────────────────────────────
        elif cmd == "cycle" or cmd.startswith("cycle "):
            remainder = raw[5:].strip()
            tokens    = remainder.split() if remainder else []

            interval_secs = 0
            total_secs    = 0

            # Try to parse up to two time values from inline args
            if len(tokens) >= 2:
                interval_secs = time_string_to_seconds(tokens[0])
                total_secs    = time_string_to_seconds(" ".join(tokens[1:]))
            elif len(tokens) == 1:
                interval_secs = time_string_to_seconds(tokens[0])

            # Prompt for anything not supplied (or invalid)
            try:
                if interval_secs <= 0:
                    raw_i = input("  Interval between images (e.g. 30s, 2m): ").strip()
                    interval_secs = time_string_to_seconds(raw_i)
                if total_secs <= 0:
                    raw_t = input("  Total session time   (e.g. 10m, 1h):   ").strip()
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
                print(f"  Type 'stop' at any time to end the session early.")
                _cancel_cycle()                      # cancel any previous cycle
                t = CycleSession(interval_secs, total_secs, show_next)
                _cycle_thread = t
                t.start()

        # ── Compress ──────────────────────────────────────────────────────
        elif cmd == "compress" or cmd.startswith("compress "):
            sub = cmd[8:].strip()   # everything after "compress"

            if sub == "" or sub == "image":
                # ── Compress current image ────────────────────────────────
                if current_image is None:
                    print("  [!] No image has been opened yet.")
                elif not _compress.should_compress(current_image):
                    print(f"  [!] Image doesn't meet compression criteria (too small or already optimised).")
                else:
                    original_size = os.path.getsize(current_image)
                    print(f"  🗜  Compressing current image …", end="", flush=True)
                    ok = _compress.compress_image(current_image, quality=85, backup=False)
                    if ok:
                        new_size = os.path.getsize(current_image)
                        saved_mb  = (original_size - new_size) / (1024 * 1024)
                        pct       = saved_mb / (original_size / (1024 * 1024)) * 100
                        print(f" done — saved {saved_mb:.2f} MB ({pct:.1f}%)")
                        # update cache entry in case filename changed (bmp→png)
                        if current_image in images:
                            images[images.index(current_image)] = current_image
                    else:
                        print(f" failed.")

            elif sub == "folder":
                # ── Compress current folder in background thread ───────────
                target = folder
                def _run_compress(path):
                    print(f"\n  🗜  Compressing folder: {path}")
                    _compress.process_directory(path, quality=85)
                    print(f"\n  ✔  Compression finished: {path}")
                    print("  > ", end="", flush=True)
                t = threading.Thread(target=_run_compress, args=(target,), daemon=True)
                t.start()

            elif sub.startswith("path "):
                # ── Compress a saved folder by number ─────────────────────
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
                        t = threading.Thread(target=_run_compress_path, args=(target,), daemon=True)
                        t.start()
                    else:
                        print(f"  [!] Number out of range (1–{len(saved_paths)}).")
                else:
                    print("  [!] Usage: compress path <number>")

            elif sub.startswith("dir "):
                # ── Compress an arbitrary directory given by the user ──────
                target = sub[4:].strip().strip('"')
                if not os.path.isdir(target):
                    print(f"  [!] Directory not found: {target}")
                else:
                    def _run_compress_dir(path):
                        print(f"\n  🗜  Compressing: {path}")
                        _compress.process_directory(path, quality=85)
                        print(f"\n  ✔  Compression finished: {path}")
                        print("  > ", end="", flush=True)
                    t = threading.Thread(target=_run_compress_dir, args=(target,), daemon=True)
                    t.start()

            else:
                print("  [?] Usage: compress  |  compress folder  |  compress path <#>  |  compress dir <path>")

        # ── Prompt ────────────────────────────────────────────────────────
        elif cmd == "prompt" or cmd.startswith("prompt "):
            sub = cmd[6:].strip()

            if sub == "" or sub == "random":
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

        # ── Scan ──────────────────────────────────────────────────────────
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
                print("  [!] Usage:  scan   OR   scan <number>")

        # ── Paths: list ───────────────────────────────────────────────────
        elif cmd == "paths":
            print_paths(saved_paths, path_keys, cache, folder, save_folder_index)

        # ── Paths: subcommands ────────────────────────────────────────────
        elif cmd.startswith(("path", "p ")):
            rest = cmd.partition(" ")[2].strip()
            rest_orig = raw.partition(" ")[2].strip()   # preserves original case
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
                        save_paths(saved_paths, path_keys)
                        print(f"  ✔  Added [{len(saved_paths)}] {new_path}")
                        print_paths(saved_paths, path_keys, cache, folder, save_folder_index)

            # path del <#>
            elif rest_lower.startswith("del "):
                idx_str = rest[4:].strip()
                try:
                    n = int(idx_str) - 1
                    if 0 <= n < len(saved_paths):
                        removed = saved_paths.pop(n)
                        # Remove its key if any
                        path_keys.pop(removed, None)
                        save_paths(saved_paths, path_keys)
                        # Adjust save_folder_index if needed
                        if save_folder_index == n:
                            save_folder_index = 0
                            print(f"  ℹ  Save folder reset to [1] (deleted folder was the save target).")
                        elif save_folder_index > n:
                            save_folder_index -= 1
                        if removed in cache:
                            del cache[removed]
                            save_cache(cache)
                            print(f"  ✔  Removed: {removed}  (cache cleared)")
                        else:
                            print(f"  ✔  Removed: {removed}")
                        if not saved_paths:
                            print("  [!] Path list is now empty — add one with: path add <path>")
                        else:
                            print_paths(saved_paths, path_keys, cache, folder, save_folder_index)
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
                        # Keep save_folder_index pointing at the same folder
                        if save_folder_index == a:
                            save_folder_index = b
                        elif save_folder_index == b:
                            save_folder_index = a
                        save_paths(saved_paths, path_keys)
                        print(f"  ✔  Swapped [{a+1}] and [{b+1}].")
                        print_paths(saved_paths, path_keys, cache, folder, save_folder_index)
                else:
                    print("  [!] Usage: path swap <#> <#>")

            # path rename <#> <new_path>
            elif rest_lower.startswith("rename "):
                parts = rest_orig[7:].strip().split(None, 1)
                if len(parts) == 2:
                    try:
                        n = int(parts[0]) - 1
                        new_path = parts[1].strip().strip('"')
                        if 0 <= n < len(saved_paths):
                            old = saved_paths[n]
                            saved_paths[n] = new_path
                            # Move the key to the new path if present
                            if old in path_keys:
                                path_keys[new_path] = path_keys.pop(old)
                            save_paths(saved_paths, path_keys)
                            if old in cache:
                                del cache[old]
                                save_cache(cache)
                            print(f"  ✔  [{n+1}] {old}  →  {new_path}")
                            print(f"  ℹ  Old cache cleared. Run 'scan {n+1}' to scan the new path.")
                            print_paths(saved_paths, path_keys, cache, folder, save_folder_index)
                        else:
                            print(f"  [!] Number out of range (1–{len(saved_paths)}).")
                    except ValueError:
                        print("  [!] Usage: path rename <number> <new path>")
                else:
                    print("  [!] Usage: path rename <number> <new path>")

            # path <#>  — switch to folder by number
            elif rest.isdigit():
                n = int(rest) - 1
                if 0 <= n < len(saved_paths):
                    load(saved_paths[n])
                else:
                    print(f"  [!] Number out of range (1–{len(saved_paths)}).")

            # path <key>  — switch to folder by key
            elif rest and not rest.startswith(("-", "/")):
                target_path = _path_for_key(rest, saved_paths, path_keys)
                if target_path is not None:
                    load(target_path)
                else:
                    print(f"  [?] No folder with key '{rest}'. Use 'paths' to list folders, or 'key <#> <key>' to assign one.")

            # bare "path" → show list
            elif rest == "":
                print_paths(saved_paths, path_keys, cache, folder, save_folder_index)
            else:
                print("  [?] Unknown path subcommand. Options: add, del, rename, swap, key, or a number/key.")

        # ── path key ───────────────────────────────────────────────
        elif cmd.startswith("key"):
            key_sub = cmd[3:].strip()           # everything after "key"
            key_sub_orig = cmd[3:].strip()      # original-case version

            # path key <#> <key>  — assign a key to a folder
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
                        save_paths(saved_paths, path_keys)
                        if old_key:
                            print(f"  🔑 [{n+1}] key changed: '{old_key}' → '{new_key}'")
                        else:
                            print(f"  🔑 [{n+1}] key set: '{new_key}'  →  {target_path}")
                else:
                    print("  [!] Usage: key <#> <key>")

            # path key del <#>  — remove a key from a folder
            elif key_sub.startswith("del "):
                idx_str = key_sub[4:].strip()
                if idx_str.isdigit():
                    n = int(idx_str) - 1
                    if 0 <= n < len(saved_paths):
                        target_path = saved_paths[n]
                        old_key     = path_keys.pop(target_path, None)
                        if old_key:
                            save_paths(saved_paths, path_keys)
                            print(f"  🔑 [{n+1}] key '{old_key}' removed.")
                        else:
                            print(f"  [!] Folder [{n+1}] has no key assigned.")
                    else:
                        print(f"  [!] Number out of range (1–{len(saved_paths)}).")
                else:
                    print("  [!] Usage: key del <#>")

            # path key rename <#> <new_key>  — rename a folder's key
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
                            print(f"  [!] Folder [{n+1}] has no key assigned. Use 'path key {n+1} <key>' to set one.")
                        else:
                            path_keys[target_path] = new_key
                            save_paths(saved_paths, path_keys)
                            print(f"  🔑 [{n+1}] key renamed: '{old_key}' → '{new_key}'")
                else:
                    print("  [!] Usage: key rename <#> <new_key>")

            # path key swap <#> <#>  — swap keys between two folders
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
                        pa, pb   = saved_paths[a], saved_paths[b]
                        key_a    = path_keys.get(pa)
                        key_b    = path_keys.get(pb)
                        # Perform the swap
                        if key_b:
                            path_keys[pa] = key_b
                        else:
                            path_keys.pop(pa, None)
                        if key_a:
                            path_keys[pb] = key_a
                        else:
                            path_keys.pop(pb, None)
                        save_paths(saved_paths, path_keys)
                        ka_str = f"'{key_a}'" if key_a else "(none)"
                        kb_str = f"'{key_b}'" if key_b else "(none)"
                        print(f"  🔑 Keys swapped: [{a+1}] {ka_str} ↔ [{b+1}] {kb_str}")
                else:
                    print("  [!] Usage: key swap <#> <#>")
            # bare "path key"
            else:
                print("  [?] Usage:  key <#> <key>  |  key del <#>  |  key rename <#> <new_key>  |  key swap <#> <#>")

        # ── Temporary folder (unsaved) ────────────────────────────────────
        elif cmd.startswith("folder "):
            new_path = raw[7:].strip().strip('"')
            load(new_path)

        # ── Normal mode ───────────────────────────────────────────────────
        elif cmd == "normal":
            mem_mode = False
            _cancel_timer()
            print("  ► Normal mode.")

        # ── Memory mode ───────────────────────────────────────────────────
        elif cmd == "mem" or cmd.startswith("mem "):
            mem_mode = True
            remainder = raw[3:].strip()
            if remainder:
                parsed = time_string_to_seconds(remainder)
                mem_seconds = parsed if parsed > 0 else DEFAULT_MEM_TIME
            else:
                mem_seconds = DEFAULT_MEM_TIME
            print(f"  ► Memory mode — {fmt_time(mem_seconds)} per image.")
            show_next()

        # ── Clean: find & delete non-media files ──────────────────────────
        elif cmd == "clean" or cmd.startswith("clean "):
            sub = raw[5:].strip()

            if sub == "":
                # Current active folder
                _clean_directory(folder)

            elif sub.isdigit():
                # Saved folder by number
                n = int(sub) - 1
                if 0 <= n < len(saved_paths):
                    _clean_directory(saved_paths[n])
                else:
                    print(f"  [!] Number out of range (1–{len(saved_paths)}).")

            elif sub.lower().startswith("path "):
                # Arbitrary path
                custom = sub[5:].strip().strip('"')
                _clean_directory(custom)

            else:
                print("  [?] Usage:  clean  |  clean <#>  |  clean path <dir>")

        # ── Enter → next image ────────────────────────────────────────────
        elif cmd == "":
            show_next()

        else:
            print(f"  [?] Unknown command: '{raw}'. Type 'help' for options.")


if __name__ == "__main__":
    main()
