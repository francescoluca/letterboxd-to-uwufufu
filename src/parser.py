import csv
import sys

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