import requests
import csv
import argparse
import time
import os
import sys
import getpass
from dotenv import load_dotenv

load_dotenv() 

api_key = os.getenv("API_KEY")

parser = argparse.ArgumentParser()
parser.add_argument("file", help="CSV path file")
args = parser.parse_args()
movies = []
email = input("Your Uwufufu account email: ")
password = getpass.getpass("Your UwUFUFU account password: ")
try:
    r_login = requests.post(
        "https://api.uwufufu.com/v1/auth/login",
        json={"email": email, "password": password},
    )
    
    r_login.raise_for_status() 
    
    login_data = r_login.json()
    accessToken = login_data.get("accessToken")
    
    if not accessToken:
        print("Login failed: Server did not return an access token")
        sys.exit(1)
        
    print("Successfully logged in")

except requests.exceptions.HTTPError as err:
    if r_login.status_code == 401:
        print("Login failed: Incorrect email or password.")
    else:
        print(f"Server error during login: {err}")
    sys.exit(1)
except requests.exceptions.RequestException as e:
    print(f"Connection error: {e}")
    sys.exit(1)


with open(args.file) as f:
    reader = csv.reader(f)
    next(reader)    #to skip header
    for row in reader:
        title = row[1]
        api_response = requests.get("https://www.omdbapi.com/",params={"apikey": api_key, "t": title})        
        movie_data = api_response.json()

        poster = movie_data.get("Poster", "N/A")
        if poster != "N/A":
            poster_high_res = poster.split("._V1_")[0] + "._V1_QL75_UX1000_.jpg"
            movies.append({"title": title, "poster_url": poster_high_res})
        else:
            print(f" Poster not found for: {title}")        
        time.sleep(0.2)


headers = {"Authorization": f"Bearer {accessToken}"}

r_game = requests.post("https://api.uwufufu.com/v1/games", headers = headers,
                  json={"title": "letterboxdToUwufufu", "description": "...", "visibility": "IS_CLOSED", "categoryId": 16})

game_id = r_game.json().get("id")

upload_url = "https://api.uwufufu.com/v1/selections/image"

for movie in movies:
    title = movie["title"]
    poster_url = movie["poster_url"]
    print(f"Caricamento di: {title}...")
    img_response = requests.get(poster_url)

    payload_data = {
        "type": "selection",
        "worldcupId": str(game_id),
        "name": title
    }
    
    payload_files = {
        "file": (f"{title}.jpg", img_response.content, "image/jpeg")
    }

    r_upload = requests.post(
        upload_url, 
        headers=headers, 
        data=payload_data, 
        files=payload_files
    )