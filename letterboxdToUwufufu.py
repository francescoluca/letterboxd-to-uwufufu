import requests
import csv
import argparse
import time
import os
from dotenv import load_dotenv

load_dotenv() 

api_key = os.getenv("API_KEY")

parser = argparse.ArgumentParser()
parser.add_argument("file", help="CSV path file")
args = parser.parse_args()

with open(args.file) as f:
    reader = csv.reader(f)
    next(reader)    #to skip header
    for row in reader:
        title = row[1]
        api_response = requests.get("https://www.omdbapi.com/",params={"apikey": api_key, "t": title})        
        movie_data = api_response.json()

        poster = movie_data.get("Poster", "N/A")
        print(f"{title}: {poster}")
        time.sleep(0.2)