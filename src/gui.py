import os
import sys
import math
import time
import zlib
import base64
import ctypes
import struct
import warnings
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import font as tkfont
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import customtkinter as ctk
from dotenv import load_dotenv
from cryptography.fernet import Fernet

from src import tmdb, uwufufu, parser
from src.config import ENCRYPTION_KEY


CONFIG_FILE = Path.home() / ".uwufufu_converter.env"
load_dotenv(CONFIG_FILE)
cipher = Fernet(ENCRYPTION_KEY)

CSV_PATHS_SEPARATOR = "|"
START_TEXT = "Create tournament"
MODE_LABELS = {parser.UNION: "Union", parser.INTERSECTION: "Intersection"}
MODE_HELP = {
    parser.UNION: "Every movie that appears in at least one file.",
    parser.INTERSECTION: "Only the movies that appear in every file.",
}
QUALITY_LABELS = {tmdb.STANDARD_QUALITY: "Standard", tmdb.HIGH_QUALITY: "High"}
QUALITY_HELP = {
    tmdb.STANDARD_QUALITY: "Sharp enough for most screens, quick to upload.",
    tmdb.HIGH_QUALITY: "Sharper posters, but uploads take 2-3 times longer.",
}
THEMES = ("light", "dark", "system")

# Posters uploaded at the same time. 4 was the fastest in tests: with more,
# the uploads just share the same upload bandwidth
UPLOAD_WORKERS = 4

# Layout: a 3x2 workbench of file cards on the left, a tool panel on the right
GRID_COLUMNS = 3
GRID_ROWS = 2
MAX_CSV_FILES = GRID_COLUMNS * GRID_ROWS
PANEL_WIDTH = 360
CARD_WIDTH = 172
CARD_HEIGHT = 200
CARD_GAP = 14
WORKBENCH_PADDING = 24
GRID_WIDTH = GRID_COLUMNS * CARD_WIDTH + (GRID_COLUMNS - 1) * CARD_GAP
GRID_HEIGHT = GRID_ROWS * CARD_HEIGHT + (GRID_ROWS - 1) * CARD_GAP
WINDOW_WIDTH = GRID_WIDTH + 2 * WORKBENCH_PADDING + 1 + PANEL_WIDTH

# Palette modelled on Stirling PDF's light and dark themes: (light, dark)
PAPER = ("#f5f4f1", "#141416")
SURFACE = ("#fafafa", "#1a1a1d")
CARD = ("#ffffff", "#202023")
INPUT_BG = ("#ffffff", "#141416")
THUMB = ("#f0efeb", "#18181b")
PAGE = ("#ffffff", "#27272a")
TRACK = ("#e9e7e2", "#27272a")
TRACK_HOVER = ("#dfddd7", "#333338")
SELECTED = ("#ffffff", "#3f3f46")
BORDER = ("#e5e7eb", "#28282d")
SLOT_BORDER = ("#e6e4df", "#1f1f23")
INPUT_BORDER = ("#d1d5db", "#3f3f46")
INK = ("#373530", "#fafafa")
MUTED = ("#4b5563", "#a1a1aa")
DIMMED = ("#868e96", "#8b8b93")
PREVIEW_TEXT = ("#9ca3af", "#71717a")
LINK = ("#2563eb", "#60a5fa")
PRIMARY = ("#3b82f6", "#3b82f6")
PRIMARY_HOVER = ("#2563eb", "#2563eb")
SUCCESS = ("#16a34a", "#22c55e")
WARNING = ("#d97706", "#f59e0b")
DANGER = ("#dc2626", "#f87171")
DANGER_SUBTLE = ("#fdecec", "#2f1e21")
DANGER_HOVER = ("#fbdada", "#3a2023")
WHITE = ("#ffffff", "#ffffff")
ICON_TILE = "#373530"
SUN = "#f59e0b"
MOON = "#6366f1"

# The theme button morphs between a sun (frame 0) and a moon (last frame)
THEME_ICON_SIZE = 20
THEME_ICON_FRAMES = 16
THEME_ICON_FRAME_MS = 16

MONO_FONT = {"nt": "Consolas"}.get(os.name, "Menlo")
DWMWA_CAPTION_COLOR = 35

PRIMARY_STYLE = {
    "fg_color": PRIMARY,
    "hover_color": PRIMARY_HOVER,
    "text_color": WHITE
}
STOP_STYLE = {
    "fg_color": DANGER_SUBTLE,
    "hover_color": DANGER_HOVER,
    "text_color": DANGER
}

LOG_COLORS = {
    "step": INK,
    "detail": MUTED,
    "warn": WARNING,
    "error": DANGER,
    "success": SUCCESS,
    "placeholder": DIMMED,
}

SAVED_THEME = os.getenv("theme")
if SAVED_THEME not in THEMES:
    SAVED_THEME = "system"
ctk.set_appearance_mode(SAVED_THEME)


class ConversionStopped(Exception):
    pass


def render_icon(size=64, radius=14):
    """A tournament bracket, white on a dark rounded tile."""
    image = tk.PhotoImage(width=size, height=size)

    for y in range(size):
        # Inset each row near the top and bottom to round the corners
        dy = max(radius - y, y - (size - 1 - radius), 0)
        inset = radius - int((radius ** 2 - dy ** 2) ** 0.5) if dy else 0
        image.put(ICON_TILE, to=(inset, y, size - inset, y + 1))

    for box in (
        (14, 17, 35, 22),
        (14, 42, 35, 47),
        (30, 17, 35, 47),
        (30, 30, 50, 35)
    ):
        image.put("#ffffff", to=box)

    return image


def png_image(size, rows):
    """Wrap rows of RGBA bytes in a PNG that Tk can show with real alpha."""
    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    raw = b"".join(b"\x00" + row for row in rows)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return tk.PhotoImage(data=base64.b64encode(png).decode())


def _segment_distance(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    h = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    h = max(0.0, min(1.0, h))
    return math.hypot(px - ax - dx * h, py - ay - dy * h)


def theme_icon_pixels(t, size):
    """
    RGBA rows of the theme icon part-way through its morph: t=0 is a sun,
    t=1 a crescent moon. Shapes are signed distance fields, which gives
    anti-aliased edges without supersampling.
    """
    e = t * t * (3 - 2 * t)  # ease in and out

    disc = 0.19 + 0.17 * e
    # A shadow disc slides in from the top right to bite out the crescent
    shadow_x = 1.05 - 0.35 * e
    shadow_y = -0.05 + 0.37 * e
    # Rays are gone before the crescent forms, so no specks are left over
    ray_scale = max(0.0, 1 - e / 0.7)
    spin = e * math.pi / 2

    rays = []
    for k in range(8):
        angle = spin + k * math.pi / 4
        inner, outer = 0.31, 0.31 + 0.12 * ray_scale
        rays.append((
            0.5 + math.cos(angle) * inner, 0.5 + math.sin(angle) * inner,
            0.5 + math.cos(angle) * outer, 0.5 + math.sin(angle) * outer
        ))

    sun, moon = (
        [int(c[i:i + 2], 16) for i in (1, 3, 5)] for c in (SUN, MOON)
    )
    rgb = bytes(round(a + (b - a) * e) for a, b in zip(sun, moon))

    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            px, py = (x + 0.5) / size, (y + 0.5) / size
            d = max(
                math.hypot(px - 0.5, py - 0.5) - disc,
                0.30 - math.hypot(px - shadow_x, py - shadow_y)
            )
            if ray_scale > 0.02:
                for ray in rays:
                    d = min(
                        d,
                        _segment_distance(px, py, *ray) - 0.035 * ray_scale
                    )
            alpha = max(0.0, min(1.0, 0.5 - d * size))
            row += rgb + bytes((round(alpha * 255),))
        rows.append(bytes(row))
    return rows


def clip(text, limit):
    return text if len(text) <= limit else text[:limit - 1] + "…"


def save_setting(key, value):
    lines = []
    if CONFIG_FILE.exists():
        lines = [
            line for line in CONFIG_FILE.read_text().splitlines()
            if not line.startswith(f"{key}=")
        ]
    CONFIG_FILE.write_text("\n".join(lines + [f"{key}={value}"]) + "\n")


def open_with_default_app(path):
    """Open a file the way double-clicking it in the file manager would."""
    if os.name == "nt":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class LetterboxdToUwufufuApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Letterboxd to UwUFUFU Converter")
        self.root.resizable(False, False)
        self.root.configure(fg_color=PAPER)

        self.icon = render_icon()
        self.root.iconphoto(True, self.icon)
        # Calling iconbitmap() stops CustomTkinter from swapping in its logo
        self.root.iconbitmap()

        self.stop_event = threading.Event()
        self.previews = {}
        self.theme = SAVED_THEME
        self.theme_icons = {}
        self.icon_animation = 0
        self._build_fonts()

        saved = os.getenv("csv_paths") or os.getenv("csv_path") or ""
        self.csv_paths = [
            p for p in saved.split(CSV_PATHS_SEPARATOR) if p
        ][:MAX_CSV_FILES]

        mode = os.getenv("csv_mode")
        if mode not in parser.COMBINE_MODES:
            mode = parser.UNION
        self.combine_mode = ctk.StringVar(value=MODE_LABELS[mode])

        quality = os.getenv("poster_quality")
        if quality not in tmdb.POSTER_QUALITIES:
            quality = tmdb.STANDARD_QUALITY
        self.poster_quality = ctk.StringVar(value=QUALITY_LABELS[quality])

        self.workbench = ctk.CTkFrame(self.root, fg_color="transparent")
        self.workbench.pack(side="left", fill="y")

        ctk.CTkFrame(
            self.root,
            width=1,
            corner_radius=0,
            fg_color=BORDER
        ).pack(side="left", fill="y")

        self.panel = ctk.CTkFrame(
            self.root,
            corner_radius=0,
            fg_color=SURFACE
        )
        self.panel.pack(side="left", fill="both", expand=True)

        self._build_workbench()
        self._build_panel()
        self._refresh_files()
        self._resize_window()

        # CustomTkinter recolours its own widgets when the theme changes;
        # the log colours and the title bar are ours to update
        ctk.AppearanceModeTracker.add(self._apply_theme, self.root)
        self._apply_theme(ctk.get_appearance_mode())

    def _build_fonts(self):
        # Stirling uses Inter, falling back to the system UI font
        families = tkfont.families()
        family = "Inter" if "Inter" in families else (
            tkfont.nametofont("TkDefaultFont").actual("family")
        )
        semibold = f"{family} Semibold"

        def strong(size):
            if semibold in families:
                return ctk.CTkFont(family=semibold, size=size)
            return ctk.CTkFont(family=family, size=size, weight="bold")

        self.title_font = strong(18)
        self.heading_font = strong(14)
        self.label_font = strong(13)
        self.button_font = strong(14)
        self.body_font = ctk.CTkFont(family=family, size=13)
        self.small_font = ctk.CTkFont(family=family, size=12)
        self.preview_font = ctk.CTkFont(family=family, size=10)
        self.mono_font = ctk.CTkFont(family=MONO_FONT, size=12)

    def _resize_window(self):
        self.root.update_idletasks()
        scaling = ctk.ScalingTracker.get_window_scaling(self.root)
        height = self.root.winfo_reqheight() / scaling
        self.root.geometry(f"{WINDOW_WIDTH}x{round(height)}")

    # ---- Theme --------------------------------------------------------------

    def _apply_theme(self, mode):
        index = 1 if mode == "Dark" else 0

        for level, color in LOG_COLORS.items():
            self.log_area.tag_config(level, foreground=color[index])

        # Dark mode offers the sun to switch back, light mode the moon
        self._show_theme_icon(0 if index else THEME_ICON_FRAMES)

        if os.name == "nt":
            # Paint the Windows 11 title bar with the window background
            try:
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                hex_color = PAPER[index]
                color = ctypes.c_int(int(
                    hex_color[5:7] + hex_color[3:5] + hex_color[1:3], 16
                ))
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    DWMWA_CAPTION_COLOR,
                    ctypes.byref(color),
                    ctypes.sizeof(color)
                )
            except Exception:
                pass

    def toggle_theme(self):
        to_dark = ctk.get_appearance_mode() == "Light"
        self.theme = "dark" if to_dark else "light"
        ctk.set_appearance_mode(self.theme)
        save_setting("theme", self.theme)

        # Switch first so the click feels instant, then morph the icon from
        # the old symbol to the new one
        start, end = (THEME_ICON_FRAMES, 0) if to_dark else (0, THEME_ICON_FRAMES)
        self._show_theme_icon(start)
        self._play_theme_icon(start, end)

    def _play_theme_icon(self, start, end):
        # A newer animation (a quick double click) cancels this one
        self.icon_animation += 1
        animation = self.icon_animation
        step = 1 if end > start else -1

        def show(index):
            if animation == self.icon_animation:
                self._show_theme_icon(index)

        for n, index in enumerate(range(start + step, end + step, step), 1):
            self.root.after(
                n * THEME_ICON_FRAME_MS,
                lambda index=index: show(index)
            )

    def _theme_icon(self, index):
        scaling = ctk.ScalingTracker.get_widget_scaling(self.root)
        size = round(THEME_ICON_SIZE * scaling)

        if (index, size) not in self.theme_icons:
            rows = theme_icon_pixels(index / THEME_ICON_FRAMES, size)
            self.theme_icons[index, size] = png_image(size, rows)
        return self.theme_icons[index, size]

    def _show_theme_icon(self, index):
        # CustomTkinter warns that a PhotoImage won't follow display
        # scaling; this one is already rendered at the scaled size
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.theme_btn.configure(image=self._theme_icon(index))

    # ---- Shared widgets -----------------------------------------------------

    def _label(self, parent, text, font=None, color=INK, **kwargs):
        options = {"height": 0, "anchor": "w", "justify": "left"}
        options.update(kwargs)
        return ctk.CTkLabel(
            parent,
            text=text,
            font=font or self.body_font,
            text_color=color,
            **options
        )

    def _segmented(self, parent, values, variable, command=None):
        selector = ctk.CTkSegmentedButton(
            parent,
            values=values,
            variable=variable,
            command=command,
            height=32,
            corner_radius=8,
            border_width=3,
            font=self.body_font,
            fg_color=TRACK,
            selected_color=SELECTED,
            selected_hover_color=SELECTED,
            unselected_color=TRACK,
            unselected_hover_color=TRACK_HOVER,
            text_color=INK,
            text_color_disabled=PREVIEW_TEXT
        )
        # CustomTkinter sizes each segment by its text, so longer labels get
        # wider segments; a uniform group keeps them all the same width
        for index in range(len(values)):
            selector.grid_columnconfigure(index, uniform="segment")
        return selector

    def _entry(self, parent, **kwargs):
        entry = ctk.CTkEntry(
            parent,
            height=36,
            corner_radius=8,
            border_width=1,
            fg_color=INPUT_BG,
            border_color=INPUT_BORDER,
            text_color=INK,
            placeholder_text_color=PREVIEW_TEXT,
            font=self.body_font,
            **kwargs
        )
        entry.bind("<FocusIn>", lambda e: entry.configure(border_color=PRIMARY))
        entry.bind(
            "<FocusOut>",
            lambda e: entry.configure(border_color=INPUT_BORDER)
        )
        return entry

    # ---- Workbench ----------------------------------------------------------

    def _build_workbench(self):
        top = ctk.CTkFrame(self.workbench, fg_color="transparent")
        top.pack(
            fill="x",
            padx=WORKBENCH_PADDING,
            pady=(WORKBENCH_PADDING, 16)
        )

        self.view = ctk.StringVar(value="Files")
        self._segmented(
            top,
            ["Files", "Activity"],
            self.view,
            command=self._show_view
        ).pack(side="left")

        self.file_count_label = self._label(
            top, "", self.small_font, DIMMED
        )
        self.file_count_label.pack(side="right")

        area = ctk.CTkFrame(
            self.workbench,
            width=GRID_WIDTH,
            height=GRID_HEIGHT,
            fg_color="transparent"
        )
        area.pack(
            fill="both",
            expand=True,
            padx=WORKBENCH_PADDING,
            pady=(0, WORKBENCH_PADDING)
        )
        area.pack_propagate(False)

        self.file_grid = ctk.CTkFrame(area, fg_color="transparent")

        self.log_area = ctk.CTkTextbox(
            area,
            corner_radius=12,
            border_width=1,
            border_spacing=12,
            fg_color=CARD,
            border_color=BORDER,
            text_color=MUTED,
            font=self.mono_font,
            wrap="word",
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=INPUT_BORDER
        )
        self._append_log("Activity will appear here.", "placeholder")

        self.views = {"Files": self.file_grid, "Activity": self.log_area}
        self._show_view("Files")

    def _show_view(self, name):
        self.view.set(name)
        for view_name, widget in self.views.items():
            if view_name == name:
                widget.pack(fill="both", expand=True)
            else:
                widget.pack_forget()

    def _refresh_files(self):
        for child in self.file_grid.winfo_children():
            child.destroy()

        # Every slot of the grid is always filled, so the cards stretch
        # evenly over the whole workbench
        rows = []
        for i in range(GRID_ROWS):
            row = ctk.CTkFrame(self.file_grid, fg_color="transparent")
            row.pack(fill="both", expand=True, pady=(CARD_GAP if i else 0, 0))
            rows.append(row)

        count = len(self.csv_paths)
        for i in range(MAX_CSV_FILES):
            row, column = divmod(i, GRID_COLUMNS)

            if i < count:
                card = self._file_card(rows[row], self.csv_paths[i])
            elif i == count:
                card = self._add_card(rows[row])
            else:
                card = self._empty_slot(rows[row])

            card.pack(
                side="left",
                fill="both",
                expand=True,
                padx=(CARD_GAP if column else 0, 0)
            )

        self.file_count_label.configure(text=f"{count} of {MAX_CSV_FILES} files")
        self.files_summary.configure(
            text=f"{count} file{'s' if count != 1 else ''} selected"
            if count else "No files selected",
            text_color=INK if count else DIMMED
        )

        self.mode_selector.configure(
            state=tk.NORMAL if count > 1 else tk.DISABLED
        )
        self._update_mode_help()

    def _preview(self, path):
        """Return the movies in a CSV (for the card preview) and any problem."""
        if not os.path.isfile(path):
            return [], "File not found"

        if path not in self.previews:
            try:
                movies = parser.extract_movies(path)
                self.previews[path] = (
                    movies,
                    None if movies else "No movies found"
                )
            except (Exception, SystemExit):
                self.previews[path] = ([], "Can't read this file")

        return self.previews[path]

    def _card_frame(self, parent, **kwargs):
        options = {
            "width": CARD_WIDTH,
            "height": CARD_HEIGHT,
            "corner_radius": 12,
            "border_width": 1,
            "border_color": BORDER
        }
        options.update(kwargs)
        card = ctk.CTkFrame(parent, **options)
        card.pack_propagate(False)
        return card

    def _make_clickable(self, card, command, skip=()):
        def enter(_):
            card.configure(border_color=PRIMARY)

        def leave(_):
            # Moving onto a child widget also fires <Leave>, so only reset
            # once the pointer has really left the card
            inside = card.winfo_containing(*card.winfo_pointerxy())
            name = str(inside)
            if not (name == str(card) or name.startswith(f"{card}.")):
                card.configure(border_color=BORDER)

        def bind(widget):
            if widget in skip:
                return
            tk.Misc.bind(widget, "<Enter>", enter, add="+")
            tk.Misc.bind(widget, "<Leave>", leave, add="+")
            tk.Misc.bind(widget, "<Button-1>", lambda _: command(), add="+")
            for child in widget.winfo_children():
                bind(child)

        bind(card)
        tk.Frame.configure(card, cursor="hand2")

    def _file_card(self, parent, path):
        movies, problem = self._preview(path)
        card = self._card_frame(parent, fg_color=CARD)

        # Packed bottom-up so the thumbnail takes whatever height is left
        self._label(
            card,
            problem or f"{len(movies)} movies",
            self.small_font,
            DANGER if problem else MUTED
        ).pack(side="bottom", fill="x", padx=12, pady=(2, 12))

        self._label(
            card,
            clip(os.path.basename(path), 22),
            self.label_font
        ).pack(side="bottom", fill="x", padx=12)

        # A page-like thumbnail listing the first titles in the file
        thumb = ctk.CTkFrame(
            card,
            width=10,
            height=10,
            corner_radius=8,
            fg_color=THUMB
        )
        thumb.pack(fill="both", expand=True, padx=8, pady=(8, 10))
        thumb.pack_propagate(False)

        page = ctk.CTkFrame(
            thumb,
            width=10,
            height=10,
            corner_radius=4,
            border_width=1,
            border_color=BORDER,
            fg_color=PAGE
        )
        page.pack(fill="both", expand=True, padx=24, pady=(16, 0))
        page.pack_propagate(False)

        for movie in movies[:16]:
            self._label(
                page,
                clip(movie["title"], 18),
                self.preview_font,
                PREVIEW_TEXT
            ).pack(fill="x", padx=8, pady=(4, 0))

        remove_btn = ctk.CTkButton(
            card,
            text="×",
            command=lambda: self.remove_csv(path),
            width=24,
            height=24,
            corner_radius=12,
            border_width=1,
            fg_color=CARD,
            hover_color=SURFACE,
            border_color=BORDER,
            bg_color=THUMB,
            text_color=MUTED,
            font=self.body_font
        )
        remove_btn.place(relx=1, x=-14, y=14, anchor="ne")

        if os.path.isfile(path):
            self._make_clickable(
                card,
                lambda: self.open_csv(path),
                skip=(remove_btn,)
            )

        return card

    def _add_card(self, parent):
        card = self._card_frame(parent, fg_color=SURFACE)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.place(relx=0.5, rely=0.5, anchor="center")

        add_btn = ctk.CTkButton(
            inner,
            text="Add CSV",
            command=self.browse_files,
            width=110,
            height=34,
            corner_radius=8,
            font=self.label_font,
            **PRIMARY_STYLE
        )
        add_btn.pack()

        self._label(
            inner,
            f"Up to {MAX_CSV_FILES} Letterboxd\nexports",
            self.small_font,
            DIMMED,
            justify="center"
        ).pack(pady=(10, 0))

        self._make_clickable(card, self.browse_files, skip=(add_btn,))
        return card

    def _empty_slot(self, parent):
        return self._card_frame(
            parent,
            fg_color="transparent",
            border_color=SLOT_BORDER
        )

    def open_csv(self, path):
        try:
            open_with_default_app(path)
        except OSError as e:
            messagebox.showerror("Can't Open File", f"{path}\n\n{e}")

    def browse_files(self):
        filenames = filedialog.askopenfilenames(
            filetypes=[
                ("CSV Files", "*.csv"),
                ("All Files", "*.*")
            ]
        )

        for filename in filenames:
            if len(self.csv_paths) >= MAX_CSV_FILES:
                break
            if filename not in self.csv_paths:
                self.csv_paths.append(filename)

        self._refresh_files()

    def remove_csv(self, path):
        self.csv_paths.remove(path)
        self._refresh_files()

    # ---- Tool panel ---------------------------------------------------------

    def _build_panel(self):
        content = ctk.CTkFrame(self.panel, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=(20, 18))

        header = ctk.CTkFrame(content, fg_color="transparent")
        header.pack(fill="x")

        self._label(header, "Letterboxd to UwUFUFU", self.title_font).pack(
            side="left"
        )

        # The button only lays out an image it is created with, so start
        # with the icon for the current theme (see _show_theme_icon)
        dark = ctk.get_appearance_mode() == "Dark"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.theme_btn = ctk.CTkButton(
                header,
                text="",
                image=self._theme_icon(0 if dark else THEME_ICON_FRAMES),
                command=self.toggle_theme,
                width=32,
                height=32,
                corner_radius=8,
                fg_color="transparent",
                hover_color=TRACK
            )
        self.theme_btn.pack(side="right")

        self._label(
            content,
            "Build a UwUFUFU bracket tournament from your "
            "Letterboxd CSV exports.",
            self.body_font,
            MUTED,
            wraplength=PANEL_WIDTH - 40
        ).pack(fill="x", pady=(2, 0))

        body = self._step(content, 1, "Files")
        self.files_summary = self._label(body, "", self.body_font)
        self.files_summary.pack(fill="x")
        self._label(
            body,
            "Click a file in the workbench to open it.",
            self.small_font,
            DIMMED
        ).pack(fill="x", pady=(2, 0))

        body = self._step(content, 2, "Settings")
        self._label(body, "Combine files", self.label_font).pack(fill="x")

        self.mode_selector = self._segmented(
            body,
            list(MODE_LABELS.values()),
            self.combine_mode,
            command=lambda _: self._update_mode_help()
        )
        self.mode_selector.pack(fill="x", pady=(4, 0))

        self.mode_help = self._label(body, "", self.small_font, DIMMED)
        self.mode_help.pack(fill="x", pady=(4, 0))

        self._label(body, "Poster quality", self.label_font).pack(
            fill="x", pady=(12, 0)
        )

        self._segmented(
            body,
            list(QUALITY_LABELS.values()),
            self.poster_quality,
            command=lambda _: self._update_quality_help()
        ).pack(fill="x", pady=(4, 0))

        self.quality_help = self._label(body, "", self.small_font, DIMMED)
        self.quality_help.pack(fill="x", pady=(4, 0))
        self._update_quality_help()

        body = self._step(content, 3, "UwUFUFU account")
        self._label(body, "Email", self.label_font).pack(fill="x")

        self.email_entry = self._entry(body, placeholder_text="you@example.com")
        self.email_entry.pack(fill="x", pady=(4, 8))

        if email := os.getenv("email"):
            self.email_entry.insert(0, email)

        pass_head = ctk.CTkFrame(body, fg_color="transparent")
        pass_head.pack(fill="x")
        self._label(pass_head, "Password", self.label_font).pack(side="left")

        self.pass_toggle = ctk.CTkButton(
            pass_head,
            text="Show",
            command=self._toggle_password,
            width=0,
            height=0,
            fg_color="transparent",
            hover=False,
            text_color=LINK,
            font=self.small_font
        )
        self.pass_toggle.pack(side="right")

        self.pass_entry = self._entry(body, show="•")
        self.pass_entry.pack(fill="x", pady=(4, 0))

        if encrypted := os.getenv("password"):
            try:
                self.pass_entry.insert(
                    0,
                    cipher.decrypt(encrypted.encode()).decode()
                )
            except Exception:
                pass

        self.start_btn = ctk.CTkButton(
            content,
            text=START_TEXT,
            command=self.start_process,
            height=40,
            corner_radius=8,
            text_color_disabled=DIMMED,
            font=self.button_font,
            **PRIMARY_STYLE
        )
        self.start_btn.pack(fill="x", pady=(16, 0))

        body = self._step(content, 4, "Review")
        status = ctk.CTkFrame(body, fg_color="transparent")
        status.pack(fill="x")

        self.status_label = self._label(
            status, "Not started", self.body_font, DIMMED
        )
        self.status_label.pack(side="left")

        self.percent_label = self._label(status, "", self.small_font, MUTED)
        self.percent_label.pack(side="right")

        # Starts track-coloured: an empty bar would still draw a dot
        self.progress = ctk.CTkProgressBar(
            body,
            height=6,
            corner_radius=3,
            fg_color=TRACK,
            progress_color=TRACK
        )
        self.progress.set(0)
        self.progress.pack(fill="x", pady=(10, 0))

    def _step(self, parent, number, title):
        ctk.CTkFrame(
            parent,
            height=1,
            corner_radius=0,
            fg_color=BORDER
        ).pack(fill="x", pady=(14, 12))

        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.pack(fill="x")
        self._label(
            head, str(number), self.heading_font, DIMMED, width=22
        ).pack(side="left")
        self._label(head, title, self.heading_font).pack(side="left")

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.pack(fill="x", padx=(22, 0), pady=(8, 0))
        return body

    def _selected_mode(self):
        return next(
            value for value, label in MODE_LABELS.items()
            if label == self.combine_mode.get()
        )

    def _update_mode_help(self):
        if len(self.csv_paths) > 1:
            text = MODE_HELP[self._selected_mode()]
        else:
            text = "Add another file to combine them."
        self.mode_help.configure(text=text)

    def _selected_quality(self):
        return next(
            value for value, label in QUALITY_LABELS.items()
            if label == self.poster_quality.get()
        )

    def _update_quality_help(self):
        self.quality_help.configure(
            text=QUALITY_HELP[self._selected_quality()]
        )

    def _toggle_password(self):
        hidden = self.pass_toggle.cget("text") == "Show"
        self.pass_entry.configure(show="" if hidden else "•")
        self.pass_toggle.configure(text="Hide" if hidden else "Show")

    # ---- Log and progress ---------------------------------------------------

    def log(self, message, level="detail"):
        self.root.after(0, lambda: self._append_log(message, level))

    def step(self, message):
        self.set_status(message.strip())
        self.log(message, "step")

    def _append_log(self, message, level):
        self.log_area.configure(state=tk.NORMAL)
        self.log_area.insert(tk.END, message + "\n", level)
        self.log_area.configure(state=tk.DISABLED)
        self.log_area.see(tk.END)

    def _clear_log(self):
        self.log_area.configure(state=tk.NORMAL)
        self.log_area.delete("1.0", tk.END)
        self.log_area.configure(state=tk.DISABLED)

    def set_status(self, text):
        self.root.after(
            0,
            lambda: self.status_label.configure(text=text, text_color=INK)
        )

    def set_progress(self, value):
        self.root.after(0, lambda: self._show_progress(value))

    def _show_progress(self, value):
        self.progress.set(value / 100)
        self.percent_label.configure(text=f"{value:.0f}%")

    # ---- Conversion ---------------------------------------------------------

    def start_process(self):
        csv_paths = list(self.csv_paths)
        mode = self._selected_mode()
        quality = self._selected_quality()
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

        self.stop_event.clear()
        self.start_btn.configure(
            text="Stop",
            command=self.stop_process,
            **STOP_STYLE
        )
        self.progress.configure(progress_color=PRIMARY)
        self._show_progress(0)
        self._clear_log()
        self._show_view("Activity")

        encrypted_password = cipher.encrypt(password.encode()).decode()

        CONFIG_FILE.write_text(
            f"email={email}\n"
            f"password={encrypted_password}\n"
            f"csv_paths={CSV_PATHS_SEPARATOR.join(csv_paths)}\n"
            f"csv_mode={mode}\n"
            f"poster_quality={quality}\n"
            f"theme={self.theme}\n"
        )

        threading.Thread(
            target=self.run_conversion,
            args=(csv_paths, mode, quality, email, password),
            daemon=True
        ).start()

    def stop_process(self):
        # The worker checks this between requests, so it stops at the next one
        self.stop_event.set()
        self.start_btn.configure(state=tk.DISABLED, text="Stopping…")
        self.status_label.configure(text="Stopping after the current request…")

    def _check_stop(self):
        if self.stop_event.is_set():
            raise ConversionStopped

    def run_conversion(self, csv_paths, mode, quality, email, password):
        outcome = "failed"
        game_id = None
        uploaded = 0
        no_poster = []

        try:
            self.step("Checking API key…")
            if not tmdb.validate_api_key():
                self.log("Invalid TMDb API key.", "error")
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        "API Error",
                        "The API key provided is invalid."
                    )
                )
                return
            self.set_progress(10)
            self._check_stop()

            self.step("Signing in to UwUFUFU…")
            try:
                access_token = uwufufu.authenticate(email, password)
            except SystemExit:
                self.log(
                    "Sign-in failed. Check your email, password "
                    "and connection.",
                    "error"
                )
                return
            if not access_token:
                self.log("UwUFUFU didn't return an access token.", "error")
                return
            self.set_progress(20)

            movie_lists = []

            for csv_path in csv_paths:
                self._check_stop()
                self.step(f"Reading {os.path.basename(csv_path)}…")
                movies = parser.extract_movies(csv_path)
                self.log(f"  {len(movies)} movies")
                movie_lists.append(movies)

            raw_movies = parser.combine_movies(movie_lists, mode)

            if len(csv_paths) > 1:
                self.log(
                    f"  {mode.capitalize()} of {len(csv_paths)} files: "
                    f"{len(raw_movies)} movies"
                )

            if not raw_movies:
                if len(csv_paths) > 1 and mode == parser.INTERSECTION:
                    self.log(
                        "No movie appears in every selected file.",
                        "error"
                    )
                else:
                    self.log(
                        "No movies found in the selected CSV.",
                        "error"
                    )
                return

            self.step(f"Fetching posters for {len(raw_movies)} movies…")

            movies_with_posters = []

            for i, movie in enumerate(raw_movies, 1):
                self._check_stop()
                title = movie["title"]
                year = movie["year"]

                poster = tmdb.get_movie_poster(title, year, quality)

                if poster != "N/A":
                    movies_with_posters.append({
                        "title": title,
                        "poster_url": poster
                    })
                    self.log(f"  {title} ({year})")
                else:
                    no_poster.append(f"{title} ({year})")
                    self.log(f"  {title} ({year}): no poster found", "warn")

                self.set_status(f"Fetching posters {i}/{len(raw_movies)}")
                self.set_progress(20 + i / len(raw_movies) * 50)
                time.sleep(0.1)

            if not movies_with_posters:
                self.log("No posters found for these movies.", "error")
                return

            self._check_stop()
            self.step("\nCreating a private draft on UwUFUFU…")
            game_id = uwufufu.create_worldcup(access_token)
            self.log(f"  Draft created (ID {game_id})")
            self.set_progress(75)

            self.step("Uploading posters…")
            total = len(movies_with_posters)
            pool = ThreadPoolExecutor(UPLOAD_WORKERS)

            try:
                futures = {
                    pool.submit(
                        self._upload_poster, access_token, game_id, movie
                    ): movie
                    for movie in movies_with_posters
                }

                for done, future in enumerate(as_completed(futures), 1):
                    response = future.result()
                    if response is None:
                        continue

                    title = futures[future]["title"]
                    if response.ok:
                        uploaded += 1
                        self.log(f"  {title}")
                    else:
                        self.log(
                            f"  {title}: upload failed "
                            f"(HTTP {response.status_code})",
                            "warn"
                        )

                    self.set_status(f"Uploading posters {done}/{total}")
                    self.set_progress(75 + done / total * 25)
            finally:
                # If an error ends the loop early, drop the queued uploads
                pool.shutdown(cancel_futures=True)

            self._check_stop()

            self.log(
                "\nDone. Open the tournament on UwUFUFU, click Edit, "
                "then publish it.",
                "success"
            )
            self._report_missing_posters(no_poster)
            outcome = "done"

        except ConversionStopped:
            outcome = "stopped"
            self.log("\nStopped.", "step")
            if game_id is not None:
                self.log(
                    f"The draft (ID {game_id}) keeps the {uploaded} posters "
                    "uploaded so far. You can delete it on UwUFUFU.",
                    "warn"
                )

        except Exception as e:
            self.log(f"\nSomething went wrong: {e}", "error")
            self.root.after(
                0,
                lambda: messagebox.showerror(
                    "Error",
                    f"An error occurred during execution:\n{e}"
                )
            )

        finally:
            self.root.after(
                0,
                lambda: self._process_finished(outcome, len(no_poster))
            )

    def _upload_poster(self, access_token, game_id, movie):
        # Posters still queued when Stop is pressed are skipped
        if self.stop_event.is_set():
            return None
        return uwufufu.upload_image(
            access_token,
            game_id,
            movie["title"],
            movie["poster_url"]
        )

    def _report_missing_posters(self, movies):
        if not movies:
            return

        self.log(f"\nMovies without a poster ({len(movies)})", "warn")
        for movie in movies:
            self.log(f"  {movie}")
        self.log(
            "\nSorry, we couldn't find a poster for these movies, so they "
            "aren't in the tournament. You can add them manually when you "
            "edit it on UwUFUFU.",
            "step"
        )

    def _process_finished(self, outcome, missing_posters=0):
        self.start_btn.configure(
            state=tk.NORMAL,
            text=START_TEXT,
            command=self.start_process,
            **PRIMARY_STYLE
        )

        if outcome == "stopped":
            self.progress.configure(progress_color=DIMMED)
            self.status_label.configure(text="Stopped", text_color=MUTED)
            return

        if outcome == "failed":
            self.progress.configure(progress_color=DANGER)
            self.status_label.configure(
                text="Failed. See Activity for details.",
                text_color=DANGER
            )
            return

        self._show_progress(100)
        self.progress.configure(progress_color=SUCCESS)
        self.status_label.configure(
            text="Tournament ready",
            text_color=SUCCESS
        )

        message = (
            "Tournament created and populated successfully on UwUFUFU!\n\n"
            "Open it on UwUFUFU, click Edit, then publish it."
        )
        if missing_posters == 1:
            message += (
                "\n\n1 movie had no poster and was left out. "
                "See Activity for details."
            )
        elif missing_posters:
            message += (
                f"\n\n{missing_posters} movies had no poster and were "
                "left out. See Activity for the list."
            )
        messagebox.showinfo("Success", message)


if __name__ == "__main__":
    root = ctk.CTk()
    LetterboxdToUwufufuApp(root)
    root.mainloop()
