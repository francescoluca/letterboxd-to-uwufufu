import os
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from dotenv import load_dotenv
from src import omdb, uwufufu, parser

load_dotenv()

class LetterboxdToUwufufuApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Letterboxd to UwUFUFU Converter")
        self.root.geometry("560x520")
        self.root.resizable(False, False)

        self.root.configure(bg="#f8f9fa")

        frame_csv = tk.LabelFrame(root, text=" 1. Letterboxd Data ", bg="#f8f9fa", font=("Arial", 9, "bold"))
        frame_csv.pack(fill="x", padx=15, pady=(15, 5), ipady=5)

        self.file_entry = tk.Entry(frame_csv, width=48, font=("Arial", 9))
        self.file_entry.pack(side="left", padx=(10, 5), pady=5)

        existing_file_entry = os.getenv("csv_path")
        if existing_file_entry:
            self.file_entry.insert(0, existing_file_entry)

        browse_btn = tk.Button(frame_csv, text="Browse...", command=self.browse_file, width=10, bg="#e2e3e5", relief="groove")
        browse_btn.pack(side="left", padx=5, pady=5)

        frame_omdb = tk.LabelFrame(root, text=" 2. OMDb API Configuration ", bg="#f8f9fa", font=("Arial", 9, "bold"))
        frame_omdb.pack(fill="x", padx=15, pady=5, ipady=5)

        self.api_entry = tk.Entry(frame_omdb, width=64, font=("Arial", 9))
        self.api_entry.pack(side="left", padx=10, pady=5)
        
        existing_api_key = os.getenv("API_KEY")
        if existing_api_key:
            self.api_entry.insert(0, existing_api_key)

        frame_auth = tk.LabelFrame(root, text=" 3. UwUFUFU Credentials ", bg="#f8f9fa", font=("Arial", 9, "bold"))
        frame_auth.pack(fill="x", padx=15, pady=5, ipady=5)

        tk.Label(frame_auth, text="Email:", bg="#f8f9fa", font=("Arial", 9)).grid(row=0, column=0, sticky="w", padx=10, pady=2)
        self.email_entry = tk.Entry(frame_auth, width=45, font=("Arial", 9))
        self.email_entry.grid(row=0, column=1, padx=5, pady=2)

        existing_email = os.getenv("email")
        if existing_email:
            self.email_entry.insert(0, existing_email)

        tk.Label(frame_auth, text="Password:", bg="#f8f9fa", font=("Arial", 9)).grid(row=1, column=0, sticky="w", padx=10, pady=2)
        self.pass_entry = tk.Entry(frame_auth, width=45, font=("Arial", 9), show="*")
        self.pass_entry.grid(row=1, column=1, padx=5, pady=2)

        existing_password = os.getenv("password")
        if existing_password:
            self.pass_entry.insert(0, existing_password)

        self.start_btn = tk.Button(
            root, text="START CONVERSION", bg="#28a745", fg="white", 
            font=("Arial", 10, "bold"), command=self.start_process, height=2
        )
        self.start_btn.pack(fill="x", padx=15, pady=10)

        frame_log = tk.LabelFrame(root, text=" Execution Log ", bg="#f8f9fa", font=("Arial", 9, "bold"))
        frame_log.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        self.log_area = scrolledtext.ScrolledText(frame_log, width=66, height=9, font=("Consolas", 8), bg="#ffffff")
        self.log_area.pack(fill="both", expand=True, padx=5, pady=5)

    def log(self, message):
        def append_log():
            self.log_area.insert(tk.END, message + "\n")
            self.log_area.see(tk.END)
        self.root.after(0, append_log)

    def browse_file(self):
        filename = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
        if filename:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, filename)

    def start_process(self):
        csv_path = self.file_entry.get().strip()
        api_key = self.api_entry.get().strip()
        email = self.email_entry.get().strip()
        password = self.pass_entry.get().strip()

        if not csv_path or not api_key or not email or not password:
            messagebox.showerror("Missing Fields", "Please fill in all fields (CSV file, OMDb API Key, Email, and Password).")
            return

        self.start_btn.config(state=tk.DISABLED, bg="#6c757d")
        self.log_area.delete("1.0", tk.END)

        with open(".env", "w") as f:
            f.write(f"API_KEY={api_key}\n")
            f.write(f"email={email}\n")
            f.write(f"password={password}\n")
            f.write(f"csv_path={csv_path}\n")

        threading.Thread(
            target=self.run_conversion, 
            args=(csv_path, api_key, email, password), 
            daemon=True
        ).start()

    def run_conversion(self, csv_path, api_key, email, password):
        try:
            self.log("Verifying OMDb API Key...")
            if not omdb.validate_api_key(api_key):
                self.log("Error: Invalid OMDb API Key.")
                messagebox.showerror("API Error", "The OMDb API key provided is invalid.")
                return

            self.log("Authenticating to UwUFUFU...")
            access_token = uwufufu.authenticate(email, password)
            if not access_token:
                return

            self.log(f"Reading movies from CSV: {os.path.basename(csv_path)}...")
            raw_movies = parser.extract_movies(csv_path)
            if not raw_movies:
                self.log("Error: No valid movies found in the selected CSV.")
                return

            self.log(f"Found {len(raw_movies)} movies. Fetching posters from OMDb...")
            movies_with_posters = []
            
            for movie in raw_movies:
                title = movie["title"]
                year = movie["year"]
                
                poster = omdb.get_movie_poster(title, year, api_key)
                if poster != "N/A":
                    poster_high_res = poster.split("._V1_")[0] + "._V1_QL75_UX1000_.jpg"
                    movies_with_posters.append({"title": title, "poster_url": poster_high_res})
                    self.log(f"  [OK] {title} ({year})")
                else:
                    self.log(f"  [!] Poster not found for: {title}")
                
                time.sleep(0.1)  

            if not movies_with_posters:
                self.log("Error: Could not retrieve any posters for the given movies.")
                return

            self.log("\nCreating private draft tournament on UwUFUFU...")
            game_id = uwufufu.create_worldcup(access_token)
            self.log(f"Tournament created successfully! (ID: {game_id})")

            self.log("Uploading movie posters...")
            for movie in movies_with_posters:
                self.log(f"  -> Uploading: {movie['title']}...")
                uwufufu.upload_image(access_token, game_id, movie["title"], movie["poster_url"])

            self.log("\nProcess completed successfully!")
            messagebox.showinfo("Success", "Tournament created and populated successfully on UwUFUFU!")

        except Exception as e:
            self.log(f"\nAn unexpected error occurred: {e}")
            messagebox.showerror("Error", f"An error occurred during execution:\n{e}")
        finally:
            self.start_btn.config(state=tk.NORMAL, bg="#28a745")