import os
import sys

MEDIA = {'.png', '.webp', '.jpeg', '.jpg', '.tiff', '.bmp', '.mp4', '.mp3', '.wav', '.pdf'}


def is_not_image_or_video(filepath):
    _, ext = os.path.splitext(filepath)
    return ext.lower() not in MEDIA and os.path.isfile(filepath)


def find_unwanted_files(directory):
    unwanted_files = []
    for root, dirs, files in os.walk(directory):
        for name in files:
            filepath = os.path.join(root, name)
            if is_not_image_or_video(filepath):
                unwanted_files.append(filepath)
    return unwanted_files

def find_and_delete_unwanted_files(directory):
    if not os.path.isdir(directory):
        print(f"Error: '{directory}' is not a valid directory.")
        sys.exit(1)

    unwanted_files = find_unwanted_files(directory)

    if unwanted_files:
        print("Found unwanted files:")
        for unwanted_file in unwanted_files:
            print(f" - {unwanted_file}")

        confirm = input("\nDo you want to delete these files? (y/n): ").strip().lower()
        if confirm == 'y':
            for unwanted_file in unwanted_files:
                try:
                    os.remove(unwanted_file)
                    print(f"Deleted: {unwanted_file}")
                except Exception as e:
                    print(f"Failed to delete {unwanted_file}: {e}")
        else:
            print("Deletion cancelled.")
    else:
        print("No unwanted files found.")


if __name__ == "__main__":
    directory = ""
    find_and_delete_unwanted_files(directory)