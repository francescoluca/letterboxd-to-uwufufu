# Letterboxd to UwUFUFU Converter

An open-source Python tool that automatically converts your Letterboxd watched movies diary into an interactive worldcup bracket tournament on UwUFUFU.

## Features

* **Smart OMDb Integration:** Fetches high-resolution movie posters with a built-in year-tolerance fallback mechanism to prevent mismatches.
* **Letterboxd Parser:** Reads standard Letterboxd exported CSV files, automatically adapting to different structures (watched logs, watchlists, and custom lists).
* **Secure Auth & Upload:** Securely logs into your UwUFUFU account to create private draft tournaments and bulk-upload movie posters.


## Installation & Usage (Desktop GUI)

### Option A: Use the Pre-built Executable (Recommended)
1. Head over to the **Releases** section of this repository.
2. Download the latest executable file.
3. Double-click to launch the application.

### Option B: Run from Source Code
If you want to run or modify the source code locally:

1. Clone the repository:

   ```bash
   git clone https://github.com/francescoluca/letterboxd-to-uwufufu
   cd letterboxd-to-uwufufu
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Run the application:

   ```bash
   python main.py
   ```
   
## Looking for the CLI version?

If you prefer using the command-line interface (CLI) version of this tool, please check out **v0.1.0** under the **Releases** section of this repository.

## Find a bug?

If you found an issue or would like to submit an improvement to this project, please submit an issue using the **Issues** tab.

## Disclaimer

This tool is a personal open-source side-project. It is not affiliated with, endorsed by, or supported by Letterboxd or UwUFUFU. Use responsibly and respect API rate limits.

## License

Distributed under the MIT License. See LICENSE for more information.