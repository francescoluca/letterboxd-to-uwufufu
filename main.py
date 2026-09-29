import argparse
import time
import os
import sys
import getpass
from dotenv import load_dotenv
from src import omdb, uwufufu, parser

def setup_api_key():
    load_dotenv()
    api_key = os.getenv("API_KEY")
    
    if not api_key:
        input_api_key = input("Error: API_KEY not found in environment variables. Insert here: ").strip()
        
        print("Validating API Key...")
        if not omdb.validate_api_key(input_api_key):
            print("Error: Invalid API KEY. If you don't have one get one at omdbapi.com")
            sys.exit(1)
            
        with open(".env", "w") as f:
            f.write(f"API_KEY={input_api_key}\n")
            
        load_dotenv()
        api_key = os.getenv("API_KEY")
        
    return api_key


def main():
    arg_parser = argparse.ArgumentParser(description="Convert Letterboxd CSV to UwUFUFU tournament")
    arg_parser.add_argument("file", help="Path to the Letterboxd CSV file")
    args = arg_parser.parse_args()

    api_key = setup_api_key()

    email = input("Your Uwufufu account email: ")
    password = getpass.getpass("Your UwUFUFU account password: ")
    accessToken = uwufufu.authenticate(email, password)

    raw_movies = parser.extract_movies(args.file)
    if not raw_movies:
        print("No valid movies found in the CSV file.")
        sys.exit(1)


    movies_with_posters = []
    print("\nFetching posters from OMDb...")
    for movie in raw_movies:
        title = movie["title"]
        year = movie["year"]
        
        poster = omdb.get_movie_poster(title, year, api_key)
        
        if poster != "N/A":
            poster_high_res = poster.split("._V1_")[0] + "._V1_QL75_UX1000_.jpg"
            movies_with_posters.append({"title": title, "poster_url": poster_high_res})
            print(f"  [OK] Found poster for: {title} ({year})")
        else:
            print(f"  [!] Poster not found for: {title}")
            
        time.sleep(0.2)

    print("\nCreating tournament on UwUFUFU...")
    game_id = uwufufu.create_worldcup(accessToken)
    for movie in movies_with_posters:
        print(f"  -> Uploading: {movie['title']}...")
        uwufufu.upload_image(accessToken, game_id, movie["title"], movie["poster_url"])

    print("\nProcess completed successfully! You can now publish your tournament on UwUFUFU.")


if __name__ == "__main__":
    main()