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

WINDOW_WIDTH = 560
WINDOW_HEIGHT = 580
MAX_CSV_FILES = 5
CSV_PATHS_SEPARATOR = "|"


class LetterboxdToUwufufuApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Letterboxd to UwUFUFU Converter")
        self.root.resizable(False, False)
        self.root.configure(bg="#f8f9fa")

        self._build_csv_section()
        self._build_auth_section()
        self._build_controls()
        self._build_log_section()
        self._resize_window()

    def _build_csv_section(self):
        frame = tk.LabelFrame(
            self.root,
            text=f" 1. Letterboxd CSV (up to {MAX_CSV_FILES}) ",
            bg="#f8f9fa",
            font=("Arial", 9, "bold")
        )
        frame.pack(fill="x", padx=15, pady=(15, 5), ipady=5)

        self.csv_rows_frame = tk.Frame(frame, bg="#f8f9fa")
        self.csv_rows_frame.pack(fill="x")
        self.csv_rows = []

        options = tk.Frame(frame, bg="#f8f9fa")
        options.pack(fill="x", padx=10, pady=(3, 0))

        self.add_csv_btn = tk.Button(
            options,
            text="+ Add CSV",
            command=self.add_csv_row,
            width=10,
            bg="#e2e3e5",
            relief="groove"
        )
        self.add_csv_btn.pack(side="left")

        mode = os.getenv("csv_mode")
        if mode not in parser.COMBINE_MODES:
            mode = parser.UNION
        self.combine_mode = tk.StringVar(value=mode)

        self.mode_buttons = []
        for text, value in (
            ("Intersection", parser.INTERSECTION),
            ("Union", parser.UNION)
        ):
            btn = tk.Radiobutton(
                options,
                text=text,
                value=value,
                variable=self.combine_mode,
                bg="#f8f9fa"
            )
            btn.pack(side="right")
            self.mode_buttons.append(btn)

        tk.Label(options, text="Combine:", bg="#f8f9fa").pack(side="right")

        saved = os.getenv("csv_paths") or os.getenv("csv_path") or ""
        paths = [p for p in saved.split(CSV_PATHS_SEPARATOR) if p]
        for path in paths[:MAX_CSV_FILES] or [""]:
            self.add_csv_row(path)

    def add_csv_row(self, path=""):
        if len(self.csv_rows) >= MAX_CSV_FILES:
            return

        row = tk.Frame(self.csv_rows_frame, bg="#f8f9fa")
        row.pack(fill="x")

        entry = tk.Entry(row, width=45, font=("Arial", 9))
        entry.pack(side="left", padx=(10, 5), pady=3)
        entry.insert(0, path)

        tk.Button(
            row,
            text="Browse...",
            command=lambda: self.browse_file(entry),
            width=10,
            bg="#e2e3e5",
            relief="groove"
        ).pack(side="left", padx=5, pady=3)

        remove_btn = tk.Button(
            row,
            text="✕",
            command=lambda: self.remove_csv_row(row),
            width=2,
            bg="#e2e3e5",
            relief="groove"
        )
        remove_btn.pack(side="left", padx=(0, 5), pady=3)

        self.csv_rows.append((row, entry, remove_btn))
        self._refresh_csv_controls()

    def remove_csv_row(self, row):
        if len(self.csv_rows) <= 1:
            return

        self.csv_rows = [r for r in self.csv_rows if r[0] is not row]
        row.destroy()
        self._refresh_csv_controls()

    def _refresh_csv_controls(self):
        multiple = len(self.csv_rows) > 1
        multiple_state = tk.NORMAL if multiple else tk.DISABLED

        for _, _, remove_btn in self.csv_rows:
            remove_btn.config(state=multiple_state)

        for btn in self.mode_buttons:
            btn.config(state=multiple_state)

        self.add_csv_btn.config(
            state=tk.NORMAL
            if len(self.csv_rows) < MAX_CSV_FILES
            else tk.DISABLED
        )

        self._resize_window()

    def _resize_window(self):
        # Grow the window by one row height for each extra CSV row
        self.root.update_idletasks()
        row_height = self.csv_rows[0][0].winfo_reqheight()
        extra = (len(self.csv_rows) - 1) * row_height
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT + extra}")

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

    def browse_file(self, entry):
        filename = filedialog.askopenfilename(
            filetypes=[
                ("CSV Files", "*.csv"),
                ("All Files", "*.*")
            ]
        )

        if filename:
            entry.delete(0, tk.END)
            entry.insert(0, filename)

    def start_process(self):
        csv_paths = [
            path for _, entry, _ in self.csv_rows
            if (path := entry.get().strip())
        ]
        mode = self.combine_mode.get()
        email = self.email_entry.get().strip()
        password = self.pass_entry.get().strip()

        if not all((csv_paths, email, password)):
            messagebox.showerror(
                "Missing Fields",
                "Please fill in all fields "
                "(at least one CSV file, Email, and Password)."
            )
            return

        missing = [path for path in csv_paths if not os.path.isfile(path)]
        if missing:
            messagebox.showerror(
                "File Not Found",
                "The following CSV files could not be found:\n"
                + "\n".join(missing)
            )
            return

        self.start_btn.config(state=tk.DISABLED, bg="#6c757d")
        self.progress["value"] = 0
        self.log_area.delete("1.0", tk.END)

        encrypted_password = cipher.encrypt(password.encode()).decode()

        CONFIG_FILE.write_text(
            f"email={email}\n"
            f"password={encrypted_password}\n"
            f"csv_paths={CSV_PATHS_SEPARATOR.join(csv_paths)}\n"
            f"csv_mode={mode}\n"
        )

        threading.Thread(
            target=self.run_conversion,
            args=(csv_paths, mode, email, password),
            daemon=True
        ).start()

    def run_conversion(self, csv_paths, mode, email, password):
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

            # 3. Read CSV files
            movie_lists = []

            for csv_path in csv_paths:
                self.log(
                    f"Reading movies from CSV: {os.path.basename(csv_path)}..."
                )
                movies = parser.extract_movies(csv_path)
                self.log(f"  {len(movies)} movies read.")
                movie_lists.append(movies)

            raw_movies = parser.combine_movies(movie_lists, mode)

            if len(csv_paths) > 1:
                self.log(
                    f"{mode.capitalize()} of {len(csv_paths)} files: "
                    f"{len(raw_movies)} unique movies."
                )

            if not raw_movies:
                if len(csv_paths) > 1 and mode == parser.INTERSECTION:
                    self.log(
                        "Error: No movies are present in all "
                        "the selected CSV files."
                    )
                else:
                    self.log(
                        "Error: No valid movies found in the selected CSV."
                    )
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
