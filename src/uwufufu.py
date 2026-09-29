#Returns Uwufufu access token
import requests
import sys

def authenticate(email, password):
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
        return accessToken
    except requests.exceptions.HTTPError as err:
        if r_login.status_code == 401:
            print("Login failed: Incorrect email or password.")
        else:
            print(f"Server error during login: {err}")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Connection error: {e}")
        sys.exit(1)

def create_worldcup(accessToken):
    headers = {"Authorization": f"Bearer {accessToken}"}
    
    r_game = requests.post("https://api.uwufufu.com/v1/games", headers = headers,
                        json={"title": "letterboxdToUwufufu", "description": "...", "visibility": "IS_CLOSED", "categoryId": 16})
    
    game_id = r_game.json().get("id")
    return game_id

def upload_image(accessToken, game_id, title, poster_url):
    headers = {"Authorization": f"Bearer {accessToken}"}
    upload_url = "https://api.uwufufu.com/v1/selections/image"
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

    return r_upload