### Openref - Drawing Practice Tool

#### Commands

```txt
<Enter>               → next image (random or semi-random)
mem                   → memory mode (uses default time)
mem 30s / mem 1m30s   → memory mode with custom time
normal                → switch back to normal mode
shuffle               → reshuffle the image list
info                  → show current session settings

random / rand         → random opening mode (default)
semi                  → semi-random opening mode
                       (prefers subfolders not yet seen)

cycle [interval] [total]
                      → gesture-drawing session: auto-advance
                        images every <interval>, stop after
                        <total> (prompts if omitted)
                        e.g.  cycle 30s 10m, or cycle 2m 1h
stop                  → stop an active cycle session

search \[n] <keywords> → search loaded images by filename/path
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

paths / pp            → list all saved folders
path <#|key>          → switch to folder by number or key
path add <path>       → add & scan a new folder
path del <#|key>      → remove folder + its cache
path rename <#|key> <p> → replace a saved path
path swap <#|key> <#|key> → swap two folders

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
```

#### Usage  

python openref.py \[settings.json\]
