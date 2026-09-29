import csv
import sys

def extract_movies(csv_path):
    movies = []
    try:
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
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
                        movies.append({"title": title, "year": year})
                        
    except FileNotFoundError:
        print(f"Error: File '{csv_path}' not found.")
        sys.exit(1)
        
    return movies