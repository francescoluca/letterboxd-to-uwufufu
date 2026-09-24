# Letterboxd to UwUFUFU Converter

An open-source Python tool that automatically converts your Letterboxd watched movies diary into an interactive worldcup bracket tournament on UwUFUFU.

## Features

* Letterboxd Parser: Reads standard Letterboxd exported CSV files (such as `watched.csv`). You can use any custom CSV file as long as it follows the format, requiring the movie title and release year.
* Smart OMDb Integration: Fetches high-resolution movie posters with a built-in year-tolerance fallback mechanism to prevent mismatches.
* Secure Auth: Automatically logs into your UwUFUFU account using secure terminal input (getpass).
* Automated Injector: Creates a private draft worldcup and bulk-uploads all movie posters via multipart/form-data.

## Prerequisites

* Python 3.8+
* An OMDb API Key (get a free one at omdbapi.com)
* A registered UwUFUFU account

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/francescoluca/letterboxd-to-uwufufu
   cd letterboxd-to-uwufufu
   ```

2. Install dependencies:

   ```bash
   pip install requests python-dotenv
   ```

## Usage

1. Export your watched movies from Letterboxd (Settings -> Data -> Export your data).

2. Run the script passing the path to your CSV file:

   ```bash
   python letterboxdToUwufufu.py path/to/watched.csv
   ```
3. Enter your OMDb API key (if not already configured) and your UwUFUFU credentials securely when prompted.

5. Once completed, head over to UwUFUFU, find your newly created draft tournament, and publish it!

## Find a bug?

If you found an issue or would like to submit an improvement to this project, please submit an issue using the **Issues** tab.

## Disclaimer

This tool is a personal open-source side-project. It is not affiliated with, endorsed by, or supported by Letterboxd or UwUFUFU. Use responsibly and respect API rate limits.

## License

Distributed under the MIT License. See LICENSE for more information.