import csv
import re
import sys
from pathlib import Path

UNION = "union"
INTERSECTION = "intersection"
COMBINE_MODES = (UNION, INTERSECTION)

# Letterboxd names its data export letterboxd-<username>-<yyyy-mm-dd-hh-mm>-utc
# and unzipping it gives a folder with the same name
EXPORT_FOLDER = re.compile(r"letterboxd-([\w-]+)-\d{4}(?:-\d{2}){4}-utc")


def export_account(csv_path):
    """Return the Letterboxd username of the export a CSV belongs to.

    Only an export folder says whose data it holds, so a CSV anywhere else
    (or in a renamed folder) gives None rather than a guess.
    """
    for folder in Path(csv_path).parents:
        if match := EXPORT_FOLDER.fullmatch(folder.name):
            return match[1]
    return None


def _movie_key(movie):
    # Same film in different exports may differ only by case or spacing
    title = " ".join(movie["title"].split()).casefold()
    return title, movie["year"]


def combine_movies(movie_lists, mode=UNION):
    """Combine several movie lists, keeping each movie once.

    union: every movie found in at least one list.
    intersection: only movies found in all lists.
    Order follows the first appearance across the lists.
    """
    if mode not in COMBINE_MODES:
        raise ValueError(f"Unknown combine mode: {mode}")

    if not movie_lists:
        return []

    common_keys = None
    if mode == INTERSECTION:
        common_keys = set.intersection(
            *({_movie_key(m) for m in movies} for movies in movie_lists)
        )

    combined = []
    seen = set()

    for movies in movie_lists:
        for movie in movies:
            key = _movie_key(movie)
            if key in seen:
                continue
            if common_keys is not None and key not in common_keys:
                continue
            seen.add(key)
            combined.append(movie)

    return combined


def extract_movies(csv_path):
    def process_file(encoding_type):
        local_movies = []
        with open(csv_path, encoding=encoding_type) as f:
            first_line = f.readline()
            f.seek(0)
            delimiter = ';' if ';' in first_line else ','
            
            reader = csv.reader(f, delimiter=delimiter)
            reading_movies = False
            
            for row in reader:
                if not row:
                    continue
                
                if "Year" in row or "Position" in row:   
                    reading_movies = True
                    continue
                
                if reading_movies and len(row) >= 3:
                    title = row[1].strip()
                    year = row[2].strip()
                    
                    if title and year and year != "Year" and title != "Name":
                        local_movies.append({"title": title, "year": year})
        return local_movies

    try:
        try:
            return process_file("utf-8")
        except UnicodeDecodeError:
            return process_file("latin-1")
            
    except FileNotFoundError:
        print(f"Error: File '{csv_path}' not found.")
        sys.exit(1)