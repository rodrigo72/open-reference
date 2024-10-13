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


class MediaType(Enum):
    IMAGE = "image"
    VIDEO = "video"
    

class ViewerType(Enum):
    FIREFOX = "firefox"
    CHROME = "chrome"
    DEFAULT = "default"


REFERENCES = {}
DATA_FOLDER = "data"
FIREFOX_PATH = 'C:\\Program Files\\Mozilla Firefox\\firefox.exe'
CHROME_PATH = "C:\\Program Files\\Google\Chrome\\Application\\chrome.exe"
HELP_TEXT = """
    Viewers:
        Firefox
        Chrome
        Default
        
    Commands:
        Open a random file - [type] [viewer]
        Reload each category - reload
        Start a cycle - cycle
        Show this text - help
        Exit program - exit
        """
        

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


def get_viewer_type_from_value(value: str) -> MediaType | None:
    for viewer_type in ViewerType:
        if viewer_type.value == value:
            return viewer_type
    return None


def is_file_in_data_folder(category):
    file_path = os.path.join(DATA_FOLDER, f"{category}.pkl")
    return os.path.isfile(file_path)


def open_path_in_firefox(path: str):
    if not os.path.exists(path):
        print("Error: The specified file does not exist.")
        return
    img_url = 'file:\\\\\\' + urllib.parse.quote(os.path.abspath(path))
    webbrowser.register('firefox', None, webbrowser.BackgroundBrowser(FIREFOX_PATH))
    webbrowser.get('firefox').open(img_url)
    
    
def open_path_in_chrome(path: str):
    if not os.path.exists(path):
        print("Error: The specified file does not exist.")
        return
    img_url = urllib.parse.quote(os.path.abspath(path))
    webbrowser.register('chrome', None, webbrowser.BackgroundBrowser(CHROME_PATH))
    webbrowser.get('chrome').open(img_url)
    
    
def open_path_in_default_viewer(img_path: str):
    if not os.path.exists(img_path):
        print("Error: The specified file does not exist.")
        return
    os.startfile(img_path)


def save_data_for_category(category, image_paths):
    if not os.path.exists(DATA_FOLDER):
        os.makedirs(DATA_FOLDER)

    file_path = os.path.join(DATA_FOLDER, f"{category}.pkl")
    with open(file_path, "wb") as file:
        pickle.dump(image_paths, file)
        print(f"Data for category '{category}' saved to {file_path}.")


def load_data_for_category(category):
    file_path = os.path.join(DATA_FOLDER, f"{category}.pkl")
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


def main(ref_choice: str, viewer_type: ViewerType):
    ref_choice = ref_choice.lower()

    if ref_choice == "help":
        print(HELP_TEXT)
        return
    elif ref_choice == "reload":
        print("Reloading data for all categories.")
        for category in REFERENCES:
            init_data_structure_for_category(category)
        return
    elif ref_choice not in REFERENCES:
        print("Invalid choice.")
        return

    start_time = time.time()
    if is_file_in_data_folder(ref_choice):
        print(f"Loading data for category: {ref_choice}")
        references = load_data_for_category(ref_choice)
        print(f"Number of items: {len(references)}")
    else:
        references = init_data_structure_for_category(ref_choice)
        if references is None:
            return

    if references:
        path = random.choice(references)
        match viewer_type:
            case ViewerType.FIREFOX:
                open_path_in_firefox(path)
            case ViewerType.CHROME:
                open_path_in_chrome(path)
            case ViewerType.DEFAULT:
                open_path_in_default_viewer(path)
            case _:
                print("Unknown ViewerType.")
                return
        print(f"Time taken: {time.time() - start_time:.2f} seconds.")
    else:
        print(f"No images found for category '{ref_choice}'.")


def open_file_in_viewer(type: str, viewer: ViewerType, cache: dict):
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
        path = random.choice(cache[type])    
        match viewer:
            case ViewerType.FIREFOX:
                open_path_in_firefox(path)
            case ViewerType.CHROME:
                open_path_in_chrome(path)
            case ViewerType.DEFAULT:
                open_path_in_default_viewer(path)
            case _:
                print("Unknown ViewerType.")
                return
        print(f"Time taken: {time.time() - start_time:.2f} seconds.")
    else:
        print(f"No files found for category '{type}'.")  


def wait_for_enter(e, timeout):
    input("Press Enter to stop ...\n")
    e.set()


def cycle(total_seconds: int, interval_seconds: int, type: str, viewer: ViewerType, cache: dict, e):
    end_time = time.time() + total_seconds
    counter = 0
    start_time = time.time()
    while time.time() < end_time and not e.is_set():
        open_file_in_viewer(type, viewer, cache)
        counter += 1
        e.wait(timeout=interval_seconds)
    time_used = time.strftime("%H:%M:%S", time.gmtime(time.time() - start_time))
    print(f"\n{counter} files in {time_used}.")
    print(" --- End of cycle! --- ")
    

def terminal_mode():
    cache = {}
    print(HELP_TEXT)
        
    while True:
        print()
        choice = input("Command: ").lower()
        
        if choice == "reload":
            print("Reloading data for all categories.")
            for category in REFERENCES:
               paths = init_data_structure_for_category(category)
               cache[category] = paths
            print()
        elif choice == "exit":
            break
        elif choice == "help":
            print(HELP_TEXT)
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
        elif choice == "cycle":
            type = input("Choose a type: ").lower()
            if type not in REFERENCES:
                print("Invalid type. Default was chosen.")
                type = "fb"
            
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
            
            e = threading.Event()
            input_thread = threading.Thread(target=wait_for_enter, args=(e, total_seconds))
            input_thread.start()            
            
            cycle(total_seconds, interval_seconds, type, viewer, cache, e)
            input_thread.join()
            e.clear()

        else:
            args = choice.split()
            type = next(iter(REFERENCES)) if len(args) == 0 else args[0]
            
            if type not in REFERENCES:
                print("Invalid type.")
                continue
            
            if len(args) > 1:
                aux = get_viewer_type_from_value(args[1])
                viewer = aux if aux is not None else ViewerType.DEFAULT
            else:
                viewer = ViewerType.DEFAULT
            
            open_file_in_viewer(type, viewer, cache)  
       

if __name__ == '__main__':
    
    if len(sys.argv) > 1:
        references_path = sys.argv[1]
        
        try:
            with open(references_path, newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    key = row['key']
                    path = row['path']
                    description = row['description']
                    media_type = MediaType[row['type'].upper()]
                    REFERENCES[key] = (path, media_type, description)
                    
            if not REFERENCES:
                print("The dictionary is empty.")
            else:            
                types_str = ""
                for key, (_, _, desc) in REFERENCES.items():
                    types_str += f'\n\t{key} - {desc}'
                
                HELP_TEXT = f"""
Viewers:
\tFirefox
\tChrome
\tDefault
        
Types: {types_str}
        
Commands:
\tOpen a random file - [type] [viewer]
\tReload each category - reload
\tStart a cycle - cycle
\tShow this text - help
\tExit program - exit
"""
            
                choice = next(iter(REFERENCES))
                viewer = ViewerType.DEFAULT
                
                if len(sys.argv) > 2:
                    choice = sys.argv[2]
                
                if choice == "terminal":
                    terminal_mode()
                else:          
                    if len(sys.argv) > 3:
                        aux = get_viewer_type_from_value(sys.argv[3])
                        viewer = aux if aux is not None else viewer
                    main(choice, viewer)
        
        except FileNotFoundError:
            print(f"Error: The file '{references_path}' was not found.")
        except IsADirectoryError:
            print(f"Error: The path '{references_path}' is a directory, not a file.")
        except IOError as e:
            print(f"Error: An I/O error occurred: {e}")
        except KeyError as e:
            print(f"Error: Missing expected column in CSV: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
    
    else:
        print("CSV file needed.")
