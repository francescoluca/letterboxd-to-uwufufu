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
            poster_path = data["results"][0].get("poster_path")
            if poster_path:
                return f"{IMAGE_BASE_URL}{poster_path}"
    except Exception:
        pass
        
    return "N/A"