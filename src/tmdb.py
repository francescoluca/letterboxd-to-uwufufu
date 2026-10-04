import requests

from src.config import TMDB_API_KEY
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w780"

def validate_api_key():
    url = "https://api.themoviedb.org/3/authentication"
    params = {"api_key": TMDB_API_KEY}
    try:
        response = requests.get(url, params=params, timeout=10)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

def get_movie_poster(title, year):
    url = f"{BASE_URL}/search/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "year": year
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if data.get("results"):
            try:
                target_year = int(year)
            except ValueError:
                target_year = 0

            for movie in data["results"]:
                release_date = movie.get("release_date") or ""                
                if release_date[:4] == str(year):
                    poster_path = movie.get("poster_path")
                    if poster_path:
                        return f"{IMAGE_BASE_URL}{poster_path}"

            for movie in data["results"]:
                release_date = movie.get("release_date") or ""
                if release_date:
                    try:
                        tmdb_year = int(release_date[:4])
                        if abs(tmdb_year - target_year) <= 1:
                            poster_path = movie.get("poster_path")
                            if poster_path:
                                return f"{IMAGE_BASE_URL}{poster_path}"
                    except ValueError:
                        continue
    except Exception:
        pass
        
    return "N/A"