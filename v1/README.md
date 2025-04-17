# open-reference

Command-line tool for opening random images or videos from specified directories

## csv file

```csv
key;path;type;description
ar;C:\arquitecture;image;Example description for architecture images
vi;C:\videos;video;Example description for video files
```

- key: Short identifier
- path: Directory where the files are stored
- type: Media type
- description: A short description of the category

Supported media types: image, video

## usage

- `python3 open_reference.py references.csv ar` - Opens a random image in C:\arquitecture (recursive) with the default viewer
- `python3 open_reference.py references.csv vi firefox` - Opens a random video in C:\arquitecture with Firefox (supported viewers: firefox, chrome, default
)
- `python3 open_reference.py references.csv reload` - Updates the data files containing the paths of each category (a `data` folder with `pkl` files is created if it does not exist already)

### terminal mode

To enter terminal mode, use:
`python3 open_reference.py references.csv terminal`

#### commands

- \[type\] \[viewer\] : Opens a random image of the specified type in the specified viewer 
- reload : Reloads the data files
- cycle : Starts a cycle to open files at regular intervals. Arguments: type, viewer, total time, interval time. Example: `cycle ar default 10min 1m20s`. To stop, press any key.
- cache: Displays the number of files in the cache for each category.
- cache_size: Displays the total size of the cache.
- help : Displays help text
- exit : Exits the program

