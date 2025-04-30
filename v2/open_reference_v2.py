import os
import pickle
import webbrowser
import urllib.parse
import sys
import random
import time
from enum import Enum
import threading
import re
import csv
import json
from datetime import datetime
import traceback
import random_prompt
import search_paths
from compress_images import process_directory
from check_files import find_and_delete_unwanted_files


class MediaType(Enum):
    IMAGE = "image"
    VIDEO = "video"
    

class ViewerType(Enum):
    FIREFOX = "firefox"
    ZEN = "zen"
    CHROME = "chrome"
    DEFAULT = "default"


REFERENCES = {}
SETTINGS = {}
HELP_TEXT = ""

e = threading.Event()

FOLDERS_USED = {}
STATS = {}
CUSTOM_CYCLES = {}
REGISTERED_BROWSERS = set()

prev_image = ""
prev_path = ""

TRACEBACK = True


def get_paths(directory, type):
    match type:
        case MediaType.IMAGE:
            extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff')
        case MediaType.VIDEO:
            extensions = ('.mp4', '.mp4a')
        case _:
            return []
        
    paths = []

    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(extensions):
                paths.append(os.path.join(root, file))

    return paths


def is_file_in_data_folder(category):
    file_path = os.path.join(SETTINGS['data_folder'], f"{category}.pkl")
    return os.path.isfile(file_path)


def open_path_in_firefox(path: str):
    if not os.path.exists(path):
        print(f"Error: The specified file ({path}) does not exist.")
        return
    img_url = 'file:///' + urllib.parse.quote(os.path.abspath(path))
    if 'firefox' not in REGISTERED_BROWSERS:
        webbrowser.register('firefox', None, webbrowser.BackgroundBrowser(SETTINGS['viewers']['firefox']))
        REGISTERED_BROWSERS.add('firefox')
    webbrowser.get('firefox').open(img_url)


def open_path_in_zen(path: str):
    if not os.path.exists(path):
        print(f"Error: The specified file ({path}) does not exist.")
        return
    img_url = 'file:///' + urllib.parse.quote(os.path.abspath(path))
    if 'zen' not in REGISTERED_BROWSERS:
        webbrowser.register('zen', None, webbrowser.BackgroundBrowser(SETTINGS['viewers']['zen']))
        REGISTERED_BROWSERS.add('zen')
    webbrowser.get('zen').open(img_url)
    
    
def open_path_in_chrome(path: str):
    if not os.path.exists(path):
        print(f"Error: The specified file ({path}) does not exist.")
        return
    img_url = urllib.parse.quote(os.path.abspath(path))
    if 'chrome' not in REGISTERED_BROWSERS:
        webbrowser.register('chrome', None, webbrowser.BackgroundBrowser(SETTINGS['viewers']['chrome']))
        REGISTERED_BROWSERS.add('chrome')
    webbrowser.get('chrome').open(img_url)


def save_data_for_category(category, image_paths):
    if not os.path.exists(SETTINGS['data_folder']):
        os.makedirs(SETTINGS['data_folder'])

    file_path = os.path.join(SETTINGS['data_folder'], f"{category}.pkl")
    with open(file_path, "wb") as file:
        pickle.dump(image_paths, file)
        print(f"Data for category '{category}' saved to {file_path}.")


def load_data_for_category(category):
    file_path = os.path.join(SETTINGS['data_folder'], f"{category}.pkl")
    with open(file_path, "rb") as file:
        return pickle.load(file)


def init_data_structure_for_category(category):
    if category not in REFERENCES:
        print(f"Invalid category '{category}'.")
        return None

    print(f"Initializing data for category: {category}")
    start_time = time.time()
    paths = get_paths(REFERENCES[category][0], REFERENCES[category][1])        
    save_data_for_category(category, paths)
    print(f"Data for '{category}' initialized in {time.time() - start_time:.2f} seconds.")
    return paths


def time_string_to_seconds(time_str):
    pattern = r'(?:(\d+)(?:h|hrs|hour|hora|horas|hours))|(?:(\d+)(?:m|min|minute|minuto|minutos|minutes))|(?:(\d+)(?:s|sec|seg|second|seconds|segundo|segundos))' 
    total_seconds = 0
    matches = re.findall(pattern, time_str)
    for hours, minutes, seconds in matches:
        if hours:
            total_seconds += int(hours) * 3600
        if minutes:
            total_seconds += int(minutes) * 60
        if seconds:
            total_seconds += int(seconds)
    return total_seconds


def get_viewer_type_from_value(value: str) -> ViewerType | None:
    for viewer_type in ViewerType:
        if viewer_type.value == value:
            return viewer_type
    return None


def save_stats(stats_path):
    with open(stats_path, "w") as file:
        json.dump(STATS, file, indent=4)


def match_viewer_to_open_path(viewer_type, path):
    global prev_path
    prev_path = path

    if viewer_type == ViewerType.DEFAULT:
        viewer_type = get_viewer_type_from_value(SETTINGS['default_viewer'])
    match viewer_type:
        case ViewerType.FIREFOX:
            open_path_in_firefox(path)
        case ViewerType.ZEN:
            open_path_in_zen(path)
        case ViewerType.CHROME:
            open_path_in_chrome(path)
        case _:
            print("Unknown ViewerType.")
            return False
    return True


def choose_semi_random_path(paths, probability_repeat_folder) -> str:
    max_tries = SETTINGS['semi_rand_path_max_tries']
    tries = []
    while (max_tries > 0):
        max_tries -= 1
        path = random.choice(paths)
        folder_path = os.path.dirname(path)
        if folder_path in FOLDERS_USED:
            # print("Directory already used.")
            FOLDERS_USED[folder_path] += 1
            tries.append((path, FOLDERS_USED[folder_path]))
            if random.random() <= probability_repeat_folder:
                return path
            # print("Trying again ...")
        else:
            FOLDERS_USED[folder_path] = 1
            return path
    
    tries.sort(key=lambda x: x[1])
    return tries[-1][0]


def open_file_in_viewer(type: str, viewer: ViewerType, cache: dict, prob: float):
    start_time = time.time()
    if type not in cache:
        print("Not found in cache.")
        if is_file_in_data_folder(type):
            print(f"Loading data for category '{type}' from file ...")
            cache[type] = load_data_for_category(type)
        else:
            print('Category file not found. Creating data structure ...')
            cache[type] = init_data_structure_for_category(type)
    
    if cache[type]:
        path = choose_semi_random_path(cache[type], prob)  
        global prev_image
        prev_image = path
        if match_viewer_to_open_path(viewer, path) is False:
            return
        print(f"Time taken: {time.time() - start_time:.2f} seconds.")
        STATS['types'][type] = 1 if type not in STATS['types'] else STATS['types'][type] + 1
        STATS['viewers'][viewer.value] = 1 if viewer.value not in STATS['viewers'] else STATS['viewers'][viewer.value] + 1
    else:
        print(f"No files found for category '{type}'.")  


def wait_for_enter(e, timeout):
    input("Press Enter to stop ...\n")  # timeout not used
    e.set()


def cycle(total_seconds: int, interval_seconds: int, type_str: str, viewer: ViewerType, cache: dict, e, prob: float):
    end_time = time.time() + total_seconds
    counter = 0
    start_time = time.time()
    while time.time() < end_time and not e.is_set():
        open_file_in_viewer(type_str, viewer, cache, prob)
        counter += 1
        e.wait(timeout=interval_seconds)
    time_used = time.strftime("%H:%M:%S", time.gmtime(time.time() - start_time))
    print(f"\n{counter} files in {time_used}.")
    print(" --- End of cycle! --- ")
    STATS['cycles'].append({
        'date': datetime.now().__str__(),
        'type': type_str,
        'viewer': viewer.value,
        'time_used': time_used,
        'interval_seconds': interval_seconds,
        'total_files': counter
    })


def reload_aux(cache):
    type = input("Choose a type (or all): ").lower()
    if type == 'all':            
        print("Reloading data for all categories.")
        for category in REFERENCES:
            paths = init_data_structure_for_category(category)
            cache[category] = paths
        print()
    elif type in REFERENCES:
        cache[type] = init_data_structure_for_category(type)
    else:
        print("Invalid type.")


def set_prob_aux():
    new_prob = input("Choose a new probability for repeating a folder: ")
    try:
        new_prob = float(new_prob)
        if (new_prob > 1 or new_prob < 0):
            print("Invalid.")
        else:
            return new_prob
    except:
        print("Invalid.")
        if TRACEBACK:
                print(traceback.format_exc())
    return None


def cycle_aux(prev_type, cache, e, prob):
    type = input("Choose a type: ").lower()
    if type not in REFERENCES:
        print("Invalid type. Default / previous was chosen.")
        type = prev_type
    
    viewer = input("Choose a viewer: ").lower()
    viewer = get_viewer_type_from_value(viewer)
    if viewer is None:
        print("Invalid. Default was chosen.")
        viewer = ViewerType.DEFAULT
    
    total_time_str = input("Total time: ").lower()
    total_seconds = time_string_to_seconds(total_time_str)
    if total_seconds <= 0:
        print("Invalid. Total time <= 0. Default was chosen.")
        total_seconds = 30 * 60
    
    interval_time_str = input("Interval time: ").lower()
    interval_seconds = time_string_to_seconds(interval_time_str)
    if interval_seconds <= 0:
        print("Invalid. Interval time <= 0. Default was chosen.")
        interval_seconds = 90
    
    print(f"Choices: {type} - {viewer} - {total_seconds} - {interval_seconds}")
    
    input_thread = threading.Thread(target=wait_for_enter, args=(e, total_seconds))
    input_thread.start()            
    
    cycle(total_seconds, interval_seconds, type, viewer, cache, e, prob)
    input_thread.join()
    e.clear()
    return type


def prompt_daily_plan_aux():
    date = datetime.now().date().__str__()
    daily_plans_to_set = set(STATS['prompts']['daily_plans'])
    if date in daily_plans_to_set:
        print('Daily plan already generated today.')
    else:
        random_prompt.complete_daily_plan()
        STATS['prompts']['daily_plans'].append(date)

    
def prompt_cycle_aux(cache):
    choice = ''
    print("\n - Type 'exit' to exit cycle mode")
    while True:
        choice = input("\n> (cycle) Prompt type: ").lower()
        if choice == 'exit':
            break
        else:
            prompt_aux_2(cache, choice, cycle=False)


def prompt_aux_2(cache, choice, cycle=True):
    match choice:
        case 'dp' : prompt_daily_plan_aux()
        case 'a'  : random_prompt.complete_anatomy_prompt()
        case 'am' : random_prompt.complete_anatomy_motion_prompt()
        case 'as' : random_prompt.complete_specific_anatomy_prompt()
        case 'f'  : random_prompt.complete_face_prompt()
        case 'fp' : random_prompt.complete_face_part_prompt()
        case 'e'  : random_prompt.complete_exercise_prompt()
        case 'de' : random_prompt.complete_daily_exercise_prompt()
        case 'c'  : random_prompt.complete_category_prompt()
        case 'cycle': 
            if cycle: 
                prompt_cycle_aux(cache) 
            else: 
                print("Invalid.")
        case _    : random_prompt.random_complete_prompt()
    
    if choice != "":
        if choice not in STATS['prompts']:
            STATS['prompts'][choice] = 1
        else:
            STATS['prompts'][choice] += 1


def prompt_aux(cache):
    print(
"""
\tDaily plan - dp
\tAnatomy - a
\tAnatomy (motion) - am
\tAnatomy (specific) - as
\tFace - f
\tFace part - fp
\tExercise - e
\tDaily exercise - de
\tCategory - c
\tCyle mode - cycle
\tRandom - «enter»
""")
    choice_2 = input("> Prompt type: ")
    prompt_aux_2(cache, choice_2, cycle=True)


def else_aux(choice, cache, prob, prev_type):
    args = choice.split()
    if len(args) == 0:
        type = prev_type
    else:
        type = args[0]
        prev_type = type
    
    if type not in REFERENCES:
        print("Invalid type.")
        return
    
    if len(args) > 1:
        aux = get_viewer_type_from_value(args[1])
        viewer = aux if aux is not None else ViewerType.DEFAULT
    else:
        viewer = ViewerType.DEFAULT
    
    open_file_in_viewer(type, viewer, cache, prob)
    return prev_type


def search_aux(prev_type, cache):
    type = input("Choose a type: ").lower()
    if type not in REFERENCES:
        print("Invalid type. Default / previous was chosen.")
        type = prev_type

    if type not in cache:
        print("Not found in cache.")
        if is_file_in_data_folder(type):
            print(f"Loading data for category '{type}' from file ...")
            cache[type] = load_data_for_category(type)
        else:
            print('Category file not found. Creating data structure ...')
            cache[type] = init_data_structure_for_category(type)
    
    viewer = input("Choose a viewer: ").lower()
    viewer = get_viewer_type_from_value(viewer)
    if viewer is None:
        print("Invalid. Default was chosen.")
        viewer = ViewerType.DEFAULT

    keywords = input("Keywords (separated by a ','): ").split(',')
    diverse = input("Diverse folders? (y/n) ").lower()
    if diverse == 'y':
        results = search_paths.search_diverse_random(cache[type], keywords)
    else:
        results = search_paths.search_paths_random(cache[type], keywords)
    
    for result_path in results:
        match_viewer_to_open_path(viewer, result_path)
        input('Press «Enter» to view the next image ...')
    
    return type


def search_prev_aux(prev_t, cache, top_n=6):
    if prev_t == "":
        prev_t = SETTINGS['default_type']
    if prev_t not in cache:
        print("Not found in cache.")
        if is_file_in_data_folder(prev_t):
            print(f"Loading data for category '{prev_t}' from file ...")
            cache[prev_t] = load_data_for_category(prev_t)
        else:
            print('Category file not found. Creating data structure ...')
            cache[prev_t] = init_data_structure_for_category(prev_t)
    
    global prev_path
    if prev_path != "":
        results = search_paths.search_paths_random(cache[prev_t], [prev_path], top_n=top_n)   
        if top_n > 1:
            for result_path in results[1:]:
                match_viewer_to_open_path(viewer, result_path)
                input('Press «Enter» to view the next image ...')
        else:
            match_viewer_to_open_path(viewer, results[0])
    else:
        print("No previous path found.")


def enter_quality_aux(default=80):
    quality = input('Enter quality level (0-100): ')
    if quality == '':
        quality = default
        print(f'Default quality chosen: {quality}.')
    else:
        quality = int(quality)
    return quality
        

def compress_aux():
    try:
        chosen_type = input("Choose a type (or all or normal path): ").lower()
        if chosen_type == 'all':            
            for value in REFERENCES.values():
                quality = enter_quality_aux()
                process_directory(value[0], quality=quality)
        elif chosen_type in REFERENCES:
            quality = enter_quality_aux()
            process_directory(REFERENCES[chosen_type][0], quality=quality)
        else:
            dir_path = chosen_type
            if dir_path == '':
                dir_path = SETTINGS['default_compress_path']
                print("Default directory path for compression was chosen.")

            if not os.path.isdir(dir_path):
                print('Directory does not exist')
            else:
                quality = enter_quality_aux()
                process_directory(dir_path, quality=quality)
    except:
        print("An error occurred.")


def check_files_aux():
    chosen_type = input("Choose a type (or all): ").lower()
    if chosen_type == 'all':            
        for value in REFERENCES.values():
            find_and_delete_unwanted_files(value[0])
    elif chosen_type in REFERENCES:
        find_and_delete_unwanted_files(REFERENCES[chosen_type][0])
    else:
        print("Invalid type.")


def custom_cycle_aux(prev_type: str, cache: dict, e, prob: float):
    print(json.dumps(CUSTOM_CYCLES, indent=4))
    try:
        cycle_id = input("> Choose an id: ")
        if cycle_id in CUSTOM_CYCLES:
            for cycle_obj in CUSTOM_CYCLES[cycle_id]:
                cycle_type = cycle_obj["type"]
                if cycle_type not in REFERENCES:
                    print("Invalid type. Default / previous was chosen.")
                    cycle_type = prev_type
                
                viewer = get_viewer_type_from_value(cycle_obj["viewer"])
                if viewer is None:
                    print("Invalid. Default was chosen.")
                    viewer = ViewerType.DEFAULT
                
                total_seconds = time_string_to_seconds(cycle_obj["total_time"].lower())
                if total_seconds <= 0:
                    print("Invalid. Total time <= 0. Default was chosen.")
                    total_seconds = 10 * 60
                
                interval_seconds = time_string_to_seconds(cycle_obj["interval_time"].lower())
                if interval_seconds <= 0:
                    print("Invalid. Interval time <= 0. Default was chosen.")
                    interval_seconds = 90
                
                print(f"Choices: {cycle_type} - {viewer} - {total_seconds} - {interval_seconds}")
                
                input_thread = threading.Thread(target=wait_for_enter, args=(e, total_seconds))
                input_thread.start()            
                
                cycle(total_seconds, interval_seconds, cycle_type, viewer, cache, e, prob)
                input_thread.join()
                e.clear()
            return cycle_type
        else:
            print("Invalid id.")
    except Exception as oops:
        print(f"An unexpected error occurred: {oops}")
        if TRACEBACK:
            print(traceback.format_exc())

    return prev_type


def terminal_mode(stats_path):
    cache = {}
    print(HELP_TEXT)
    
    prob = SETTINGS['repeat_folder_probability']
    prev_type = SETTINGS['default_type']

    global prev_image
    global e

    while True:
        choice = input("\nCommand: ").lower()
        
        if choice == "reload":
            reload_aux(cache)
        elif choice == "exit":
            save_stats(stats_path)
            break
        elif choice == "help":
            print(HELP_TEXT)
        elif choice == "clear":
            os.system('cls' if os.name == 'nt' else 'clear')
        elif choice == 'get_prob':
            print('Probability of repeating a folder after being randomly selected: ', prob)
        elif choice == "set_prob":
            r = set_prob_aux()
            if r is not None: prob = r
        elif choice == "cache":
            print(f"{len(cache)} element(s) in cache")
            if len(cache) > 0:
                for key, value in cache.items():
                    print(f"\t{key}: {len(value)} paths")
        elif choice == "cache_size":
            total_size = sys.getsizeof(cache)
            for key, value in cache.items():
                total_size += sys.getsizeof(key)
                total_size += sys.getsizeof(value)
            total_size_mb = total_size / (1024 * 1024)
            print(f"Total cache size: {total_size_mb:.4f} mb")
        elif choice == "rand":
            random_type = random.choice(list(REFERENCES.keys()))
            prev_type = random_type
            open_file_in_viewer(random_type, ViewerType.DEFAULT, cache, 1)
        elif choice == "stats":
            print("\nTypes:")
            print(f"{STATS['types']}")
            print("\nViewers:")
            print(f"{STATS['viewers']}")
            print("\nCycles:")
            for el in STATS['cycles']:
                print(f"{el}")
            print("\nPrompts:")
            print(f"{STATS['prompts']}")
        elif choice == "cycle":
            prev_type = cycle_aux(prev_type, cache, e, prob)
        elif choice == 'prompt' or choice == 'p':
            prompt_aux(cache)
        elif choice == 's' or choice == 'search':
            prev_type = search_aux(prev_type, cache)
        elif choice == 'sp' or choice == 'searchp':
            search_prev_aux(prev_type, cache)
        elif choice == 'compress':
            compress_aux()
        elif choice == 'check':
            check_files_aux()
        elif choice == 'custom_cycle' or choice == 'cc':
            prev_type = custom_cycle_aux(prev_type, cache, e, prob)
        else:
            prev_type = else_aux(choice, cache, prob, prev_type)  


if __name__ == '__main__':
    
    if len(sys.argv) > 1:
        settings_path = sys.argv[1]
        
        try:
            with open(settings_path, "r") as jsonfile1:
                SETTINGS = json.load(jsonfile1)

            references_path = SETTINGS['references_csv']

            with open(references_path, newline='') as csvfile:
                reader = csv.DictReader(csvfile, delimiter=',')
                for row in reader:
                    key = row['key']
                    path = row['path']
                    description = row['description']
                    media_type = MediaType[row['type'].upper()]
                    REFERENCES[key] = (path, media_type, description)
            
            stats_path = SETTINGS['stats_json']

            with open(stats_path, "r") as jsonfile2:
                STATS = json.load(jsonfile2)

            with open(SETTINGS['custom_cycles_path'], 'r') as jsonfile3:
                CUSTOM_CYCLES = json.load(jsonfile3)

            if not REFERENCES:
                print("The dictionary is empty.")
            else:            
                types_str = ""
                for key, (_, _, desc) in REFERENCES.items():
                    types_str += f'\n\t{key} - {desc}'

                viewers_str = ""
                for key in SETTINGS['viewers'].keys():
                    viewers_str += f'\n\t{key}'
                
                HELP_TEXT = f"""
Viewers: {viewers_str}
        
Types: {types_str}
        
Commands:
\tOpen a random file - [type] [viewer]
\tReload each category - reload
\tStart a cycle - cycle
\tShow this text - help
\tPrint statistics - stats
\tProbability of repeating a folder - get_prob
\tSet new probability - set_prob
\tShow elements in cache - cache
\tShow cache size - cache_size
\tExit program - exit
\tRandom image - rand
\tGenerate random drawing prompt - prompt | p
\tSearch image (paths) by keywords - search | s
\tSearch previous path - search_prev | sp
\tCompress images - compress
\tCheck for unwanted files - check
\tChoose custom cycle - custom_cycle | cc
"""
            
                choice = next(iter(REFERENCES))
                viewer = ViewerType.DEFAULT
                
                if len(sys.argv) > 2:
                    choice = sys.argv[2]
                
                if choice == "terminal":
                    terminal_mode(stats_path)
                else:          
                    print('Only "terminal mode" is available.')
        
        except FileNotFoundError:
            print("Error: File was not found.")
            if TRACEBACK:
                print(traceback.format_exc())
        except IsADirectoryError:
            print(f"Error: Path is a directory, not a file.")
            if TRACEBACK:
                print(traceback.format_exc())
        except IOError as e:
            print(f"Error: An I/O error occurred: {e}")
            if TRACEBACK:
                print(traceback.format_exc())
        except KeyError as e:
            print(f"Error: Missing expected column in CSV: {e}")
            if TRACEBACK:
                print(traceback.format_exc())
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            if TRACEBACK:
                print(traceback.format_exc())
    
    else:
        print("settings.json file needed.")
