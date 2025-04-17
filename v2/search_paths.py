import os
from rapidfuzz import fuzz
from collections import defaultdict
import random

def search_paths_random(
    paths,
    keywords,
    top_n=5,
    tie_threshold: int = 0
):
    if isinstance(keywords, str):
        keywords = [keywords]

    scored = []
    for path in paths:
        score = max(fuzz.partial_ratio(k, path) for k in keywords)
        scored.append((path, score))

    scored.sort(key=lambda x: -x[1])

    buckets = []
    current_bucket = [scored[0]]
    for path, score in scored[1:]:
        if abs(score - current_bucket[-1][1]) <= tie_threshold:
            current_bucket.append((path, score))
        else:
            buckets.append(current_bucket)
            current_bucket = [(path, score)]
    buckets.append(current_bucket)

    result = []
    for bucket in buckets:
        random.shuffle(bucket)
        for path, score in bucket:
            result.append(path)
            if len(result) >= top_n:
                return result
    return result


def search_diverse_random(
    paths,
    keywords,
    top_n=5,
    tie_threshold: int = 0
):
    if isinstance(keywords, str):
        keywords = [keywords]

    scored = []
    for path in paths:
        score = max(fuzz.partial_ratio(k, path) for k in keywords)
        scored.append((path, score))

    scored.sort(key=lambda x: -x[1])

    buckets = []
    current_bucket = [scored[0]]
    for path, score in scored[1:]:
        if abs(score - current_bucket[-1][1]) <= tie_threshold:
            current_bucket.append((path, score))
        else:
            buckets.append(current_bucket)
            current_bucket = [(path, score)]
    buckets.append(current_bucket)

    selected = []
    used_folders = set()

    for bucket in buckets:
        random.shuffle(bucket)
        for path, score in bucket:
            parent = os.path.dirname(path)
            if parent not in used_folders:
                selected.append(path)
                used_folders.add(parent)
                break  # move on to next bucket
        if len(selected) >= top_n:
            break

    return selected


# --- testing ---
if __name__ == "__main__":
    paths = [
        "/home/user/docs/project1/file1.txt",
        "/home/user/docs/project1/file3.txt",
        "/home/user/docs/project1/file4.txt",
        "/home/user/docs/project1/file5.txt",
        "/home/user/docs/project1/file6.txt",
        "/home/user/docs/project2/file2.txt",
        "/home/user/photos/vacation1/image1.jpg",
        "/home/user/photos/vacation2/file1.jpg",
        "/home/user/music/song1.mp3",
        "/home/user/music/song2.mp3",
        "/home/user/docs/project3/file3.txt",
    ]
    keywords = ["file"]

    print(search_paths_random(paths, keywords, top_n=3, tie_threshold=0))
    print(search_paths_random(paths, keywords, top_n=3, tie_threshold=5))
    print(search_diverse_random(paths, keywords, top_n=4, tie_threshold=2))
