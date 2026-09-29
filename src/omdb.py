import requests


def validate_api_key(api_key):
    try:
        api_check = requests.get(f"http://www.omdbapi.com/?apikey={api_key}&", timeout=10)
        return api_check.json().get("Error") != "Invalid API key!"
    except requests.exceptions.RequestException:
        return False
    

def get_movie_poster(title, year,api_key):
    api_response = requests.get("https://www.omdbapi.com/",params={"apikey": api_key, "t": title, "y": year})        
    data = api_response.json()
    if data.get("Response") == "True":
        return data.get("Poster")
    api_response = requests.get(
        "https://www.omdbapi.com/",
        params={"apikey": api_key, "t": title},
        timeout=10
    )
    data = api_response.json()
    if data.get("Response") == "True":
        print(f"  [Info] Found '{title}' by title only (ignoring year mismatch)")
        return data.get("Poster")

    return "N/A"