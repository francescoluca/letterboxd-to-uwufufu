import os
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from pathlib import Path

from dotenv import load_dotenv
from cryptography.fernet import Fernet

from src import tmdb, uwufufu, parser
from src.config import ENCRYPTION_KEY


CONFIG_FILE = Path.home() / ".uwufufu_converter.env"
load_dotenv(CONFIG_FILE)
cipher = Fernet(ENCRYPTION_KEY)


class LetterboxdToUwufufuApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Letterboxd to UwUFUFU Converter")
        self.root.geometry("560x550")
        self.root.resizable(False, False)
        self.root.configure(bg="#f8f9fa")

        self._build_csv_section()
        self._build_auth_section()
        self._build_controls()
        self._build_log_section()

    def _build_csv_section(self):
        frame = tk.LabelFrame(
            self.root,
            text=" 1. Letterboxd CSV ",
            bg="#f8f9fa",
            font=("Arial", 9, "bold")
        )
        frame.pack(fill="x", padx=15, pady=(15, 5), ipady=5)

        self.file_entry = tk.Entry(frame, width=48, font=("Arial", 9))
        self.file_entry.pack(side="left", padx=(10, 5), pady=5)

        if path := os.getenv("csv_path"):
            self.file_entry.insert(0, path)

        tk.Button(
            frame,
            text="Browse...",
            command=self.browse_file,
            width=10,
            bg="#e2e3e5",
            relief="groove"
        ).pack(side="left", padx=5, pady=5)

    def _build_auth_section(self):
        frame = tk.LabelFrame(
            self.root,
            text=" 2. UwUFUFU Credentials ",
            bg="#f8f9fa",
            font=("Arial", 9, "bold")
        )
        frame.pack(fill="x", padx=15, pady=5, ipady=5)

        tk.Label(frame, text="Email:", bg="#f8f9fa").grid(
            row=0, column=0, sticky="w", padx=10, pady=2
        )

        self.email_entry = tk.Entry(frame, width=45)
        self.email_entry.grid(row=0, column=1, padx=5, pady=2)

        if email := os.getenv("email"):
            self.email_entry.insert(0, email)

        tk.Label(frame, text="Password:", bg="#f8f9fa").grid(
            row=1, column=0, sticky="w", padx=10, pady=2
        )

        self.pass_entry = tk.Entry(frame, width=45, show="*")
        self.pass_entry.grid(row=1, column=1, padx=5, pady=2)

        if encrypted := os.getenv("password"):
            try:
                self.pass_entry.insert(
                    0,
                    cipher.decrypt(encrypted.encode()).decode()
                )
            except Exception:
                pass

    def _build_controls(self):
        self.start_btn = tk.Button(
            self.root,
            text="START CONVERSION",
            bg="#28a745",
            fg="white",
            font=("Arial", 10, "bold"),
            command=self.start_process,
            height=2
        )
        self.start_btn.pack(fill="x", padx=15, pady=(10, 5))

        self.progress = ttk.Progressbar(
            self.root,
            mode="determinate",
            maximum=100
        )
        self.progress.pack(fill="x", padx=15, pady=(0, 10))

    def _build_log_section(self):
        frame = tk.LabelFrame(
            self.root,
            text=" Execution Log ",
            bg="#f8f9fa",
            font=("Arial", 9, "bold")
        )
        frame.pack(
            fill="both",
            expand=True,
            padx=15,
            pady=(0, 15)
        )

        self.log_area = scrolledtext.ScrolledText(
            frame,
            width=66,
            height=9,
            font=("Consolas", 8),
            bg="#ffffff"
        )
        self.log_area.pack(fill="both", expand=True, padx=5, pady=5)

    def log(self, message):
        self.root.after(0, lambda: self._append_log(message))

    def _append_log(self, message):
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)

    def set_progress(self, value):
        self.root.after(0, lambda: self.progress.configure(value=value))

    def browse_file(self):
        filename = filedialog.askopenfilename(
            filetypes=[
                ("CSV Files", "*.csv"),
                ("All Files", "*.*")
            ]
        )

        if filename:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, filename)

    def start_process(self):
        csv_path = self.file_entry.get().strip()
        email = self.email_entry.get().strip()
        password = self.pass_entry.get().strip()

        if not all((csv_path, email, password)):
            messagebox.showerror(
                "Missing Fields",
                "Please fill in all fields (CSV file, Email, and Password)."
            )
            return

        self.start_btn.config(state=tk.DISABLED, bg="#6c757d")
        self.progress["value"] = 0
        self.log_area.delete("1.0", tk.END)

        encrypted_password = cipher.encrypt(password.encode()).decode()

        CONFIG_FILE.write_text(
            f"email={email}\n"
            f"password={encrypted_password}\n"
            f"csv_path={csv_path}\n"
        )

        threading.Thread(
            target=self.run_conversion,
            args=(csv_path, email, password),
            daemon=True
        ).start()

    def run_conversion(self, csv_path, email, password):
        try:
            # 1. API key
            self.log("Verifying API Key...")
            if not tmdb.validate_api_key():
                self.log("Error: Invalid API Key.")
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        "API Error",
                        "The API key provided is invalid."
                    )
                )
                return
            self.set_progress(10)

            # 2. Authentication
            self.log("Authenticating to UwUFUFU...")
            try:
                access_token = uwufufu.authenticate(email, password)
            except SystemExit:
                self.log("Login failed: check your UwUFUFU credentials and connection.")
                return
            if not access_token:
                self.log("Login failed: UwUFUFU did not return an access token.")
                return
            self.set_progress(20)

            # 3. Read CSV
            self.log(
                f"Reading movies from CSV: {os.path.basename(csv_path)}..."
            )
            raw_movies = parser.extract_movies(csv_path)

            if not raw_movies:
                self.log("Error: No valid movies found in the selected CSV.")
                return

            self.log(f"Found {len(raw_movies)} movies. Fetching posters...")

            # 4. Fetch posters
            movies_with_posters = []

            for i, movie in enumerate(raw_movies, 1):
                title = movie["title"]
                year = movie["year"]

                poster = tmdb.get_movie_poster(title, year)

                if poster != "N/A":
                    movies_with_posters.append({
                        "title": title,
                        "poster_url": poster
                    })
                    self.log(f"  [OK] {title} ({year})")
                else:
                    self.log(f"  [!] Poster not found for: {title}")

                self.set_progress(20 + i / len(raw_movies) * 50)
                time.sleep(0.1)

            if not movies_with_posters:
                self.log(
                    "Error: Could not retrieve any posters "
                    "for the given movies."
                )
                return

            # 5. Create tournament
            self.log("\nCreating private draft tournament on UwUFUFU...")
            game_id = uwufufu.create_worldcup(access_token)
            self.log(
                f"Tournament created successfully! (ID: {game_id})"
            )
            self.set_progress(75)

            # 6. Upload posters
            self.log("Uploading movie posters...")

            for i, movie in enumerate(movies_with_posters, 1):
                self.log(f"  -> Uploading: {movie['title']}...")

                uwufufu.upload_image(
                    access_token,
                    game_id,
                    movie["title"],
                    movie["poster_url"]
                )

                self.set_progress(
                    75 + i / len(movies_with_posters) * 25
                )

            self.log("\nProcess completed successfully!")
            self.root.after(
                0,
                lambda: messagebox.showinfo(
                    "Success",
                    "Tournament created and populated successfully "
                    "on UwUFUFU!"
                )
            )

        except Exception as e:
            self.log(f"\nAn unexpected error occurred: {e}")
            self.root.after(
                0,
                lambda: messagebox.showerror(
                    "Error",
                    f"An error occurred during execution:\n{e}"
                )
            )

        finally:
            self.root.after(0, self._process_finished)

    def _process_finished(self):
        self.progress["value"] = 100
        self.start_btn.config(
            state=tk.NORMAL,
            bg="#28a745"
        )


if __name__ == "__main__":
    root = tk.Tk()
    LetterboxdToUwufufuApp(root)
    root.mainloop()
