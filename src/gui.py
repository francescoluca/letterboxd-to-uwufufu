import os
import re
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
from tkinterdnd2 import TkinterDnD, DND_FILES, COPY

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

# Layout: a scrolling list of files on the left, a tool panel card on the
# right, both sitting on the sage canvas
VIEW_WIDTH = 544
VIEW_HEIGHT = 414
PANEL_WIDTH = 360
PANEL_PADDING = 24
ROW_GAP = 8
ROW_PADDING = 16
WORKBENCH_PADDING = 24
WINDOW_WIDTH = VIEW_WIDTH + 3 * WORKBENCH_PADDING + PANEL_WIDTH

# Colours follow DESIGN.md: white cards on a sage canvas, near-black ink and
# no colour accent: primary actions are solid ink. Dark mode flips the
# canvas to ink, as the design's dark bands do
PAPER = ("#e8ebe6", "#0e0f0c")
CARD = ("#ffffff", "#1b1d19")
CARD_HOVER = ("#f3f5f1", "#22251f")
CARD_SELECTED = ("#eceee9", "#262823")
CARD_SELECTED_HOVER = ("#e2e5df", "#2d302a")
# Nothing has a border, so inputs are sage fills on the white card
INPUT_BG = ("#e8ebe6", "#0e0f0c")
INPUT_FOCUS = ("#dde1da", "#000000")
TRACK = ("#e8ebe6", "#2a2d27")
TRACK_HOVER = ("#dde1da", "#353831")
SELECTED = ("#d4d7d1", "#3a3d36")
SCROLLBAR = ("#c6cac2", "#3a3d36")
INPUT_BORDER = ("#868685", "#5b5d58")
INK = ("#0e0f0c", "#e8ebe6")
MUTED = ("#454745", "#b4b6b2")
DIMMED = ("#868685", "#868685")
PREVIEW_TEXT = ("#a8aaa6", "#5b5d58")
PRIMARY = ("#0e0f0c", "#e8ebe6")
PRIMARY_HOVER = ("#2a2d27", "#ffffff")
ON_PRIMARY = ("#ffffff", "#0e0f0c")
SUCCESS = ("#2ead4b", "#2ead4b")
WARNING = ("#b86700", "#ffd11a")
DANGER = ("#d03238", "#ff6b70")
DANGER_SUBTLE = ("#e8ebe6", "#320707")
DANGER_HOVER = ("#dde1da", "#451010")
ICON_TILE = "#0e0f0c"
ICON_MARK = "#ffffff"
SUN = "#e8ebe6"
MOON = "#0e0f0c"

# The theme button morphs between a sun (frame 0) and a moon (last frame)
THEME_ICON_SIZE = 20
THEME_ICON_FRAMES = 16
THEME_ICON_FRAME_MS = 16

# The tick, folder and cross are drawn like the theme icon, with strokes about
# as thick as the sun's rays
ICON_SIZE = 18
ICON_STROKE = 0.045  # half a stroke's width

MONO_FONT = {"nt": "Consolas"}.get(os.name, "Menlo")
DWMWA_CAPTION_COLOR = 35

PRIMARY_STYLE = {
    "fg_color": PRIMARY,
    "hover_color": PRIMARY_HOVER,
    "text_color": ON_PRIMARY
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
    """A tournament bracket, white on an ink rounded tile."""
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
        image.put(ICON_MARK, to=box)

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


def sdf_pixels(size, layers):
    """
    RGBA rows of shapes given as signed distance fields, which gives
    anti-aliased edges without supersampling. Each layer is a distance
    function over the unit square and the colour to fill it with, painted
    over the layers before it.
    """
    layers = [
        (distance, [int(color[i:i + 2], 16) for i in (1, 3, 5)])
        for distance, color in layers
    ]

    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            px, py = (x + 0.5) / size, (y + 0.5) / size
            rgb, alpha = [0, 0, 0], 0.0
            for distance, color in layers:
                a = max(0.0, min(1.0, 0.5 - distance(px, py) * size))
                total = a + alpha * (1 - a)
                if total:
                    rgb = [
                        (c * a + below * alpha * (1 - a)) / total
                        for c, below in zip(color, rgb)
                    ]
                alpha = total
            row += bytes(round(c) for c in rgb) + bytes((round(alpha * 255),))
        rows.append(bytes(row))
    return rows


def theme_icon_pixels(t, size):
    """
    RGBA rows of the theme icon part-way through its morph: t=0 is a sun,
    t=1 a crescent moon.
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
    color = "#" + "".join(
        f"{round(a + (b - a) * e):02x}" for a, b in zip(sun, moon)
    )

    def distance(px, py):
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
        return d

    return sdf_pixels(size, [(distance, color)])


def _strokes(*lines):
    """Distance to lines through points, with round ends and joins."""
    segments = [(a, b) for line in lines for a, b in zip(line, line[1:])]
    return lambda px, py: min(
        _segment_distance(px, py, *a, *b) for a, b in segments
    ) - ICON_STROKE


def _arc_points(x0, y0, radius, large, sweep, x1, y1, steps=8):
    # A circular arc from its endpoints to its centre, as in the SVG spec
    # (appendix B.2.4), then cut into short straight segments
    mx, my = (x0 - x1) / 2, (y0 - y1) / 2
    half_chord = math.hypot(mx, my)
    radius = max(radius, half_chord)
    k = math.sqrt(max(0.0, (radius / half_chord) ** 2 - 1))
    if large == sweep:
        k = -k
    cx, cy = (x0 + x1) / 2 + k * my, (y0 + y1) / 2 - k * mx

    start = math.atan2(y0 - cy, x0 - cx)
    turn = math.atan2(y1 - cy, x1 - cx) - start
    if sweep and turn < 0:
        turn += 2 * math.pi
    elif not sweep and turn > 0:
        turn -= 2 * math.pi

    return [
        (
            cx + radius * math.cos(start + turn * n / steps),
            cy + radius * math.sin(start + turn * n / steps)
        )
        for n in range(1, steps + 1)
    ]


def svg_lines(path, grid=24):
    """
    The lines an SVG path draws, as points in the unit square. Only knows
    the M, L, H, V, Z and circular A commands that icon sets use.
    """
    tokens = re.findall(r"[A-Za-z]|-?(?:\d+\.?\d*|\.\d+)", path)
    lines, x, y, i, command = [], 0.0, 0.0, 0, None

    def take(count):
        nonlocal i
        i += count
        return [float(token) for token in tokens[i - count:i]]

    while i < len(tokens):
        if tokens[i].isalpha():
            command = tokens[i]
            i += 1
        relative = command.islower()
        dx, dy = (x, y) if relative else (0.0, 0.0)
        kind = command.upper()

        if kind == "M":
            px, py = take(2)
            x, y = px + dx, py + dy
            lines.append([(x, y)])
            # Further pairs after a move are lines
            command = "l" if relative else "L"
            continue
        if kind == "Z":
            x, y = lines[-1][0]
            lines[-1].append((x, y))
            continue

        if kind == "L":
            px, py = take(2)
            x, y = px + dx, py + dy
            points = [(x, y)]
        elif kind == "H":
            x = take(1)[0] + dx
            points = [(x, y)]
        elif kind == "V":
            y = take(1)[0] + dy
            points = [(x, y)]
        elif kind == "A":
            radius, _, _, large, sweep, px, py = take(7)
            points = _arc_points(
                x, y, radius, large, sweep, px + dx, py + dy
            )
            x, y = px + dx, py + dy
        else:
            raise ValueError(f"Unsupported path command {command}")
        lines[-1].extend(points)

    return [[(px / grid, py / grid) for px, py in line] for line in lines]


# Lucide's folder-open (lucide.dev, ISC licence), on its 24px grid
FOLDER_PATH = (
    "m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 "
    "1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 "
    "1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"
)


def _ring(px, py):
    return abs(math.hypot(px - 0.5, py - 0.5) - 0.44) - 0.055


def _disc(px, py):
    return math.hypot(px - 0.5, py - 0.5) - 0.495


# Each icon is its layers, bottom first, painted in the colours given
ICONS = {
    "cross": (_strokes(((0.3, 0.3), (0.7, 0.7)), ((0.7, 0.3), (0.3, 0.7))),),
    "folder": (_strokes(*svg_lines(FOLDER_PATH)),),
    "box": (_ring,),
    "ticked": (_disc, _strokes(((0.29, 0.52), (0.44, 0.66), (0.72, 0.36)))),
}


def icon_pixels(name, colors, size):
    return sdf_pixels(size, list(zip(ICONS[name], colors)))


def clip(text, limit):
    return text if len(text) <= limit else text[:limit - 1] + "…"


def pointer_inside(widget):
    # winfo_containing gives the innermost widget, which may be a child
    inside = str(widget.winfo_containing(*widget.winfo_pointerxy()))
    return inside == str(widget) or inside.startswith(f"{widget}.")


def save_setting(key, value):
    lines = []
    if CONFIG_FILE.exists():
        lines = [
            line for line in CONFIG_FILE.read_text().splitlines()
            if not line.startswith(f"{key}=")
        ]
    CONFIG_FILE.write_text("\n".join(lines + [f"{key}={value}"]) + "\n")


def show_in_file_manager(path):
    """Open the folder holding a file, with the file selected if possible."""
    if os.name == "nt":
        # Explorer only understands backslashes, and wants the path quoted
        # right after the comma
        subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


class IconCheckbox(ctk.CTkFrame):
    """
    A round checkbox ticked with the app's drawn icons, in place of
    CTkCheckBox, whose tick comes from a font. It only shows what select()
    and deselect() say, so a click just runs the command.
    """

    def __init__(self, app, parent, text, command):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.command = command
        self.enabled = True

        self.box = app._icon_label(self, "box", INPUT_BORDER)
        self.box.pack(side="left")
        self.text = None
        if text:
            self.text = app._label(self, text)
            self.text.pack(side="left", padx=(6, 0))

        def bind(widget):
            tk.Misc.bind(widget, "<Button-1>", self._click, add="+")
            for child in widget.winfo_children():
                bind(child)

        bind(self)
        tk.Frame.configure(self, cursor="hand2")

    def _click(self, _):
        if self.enabled:
            self.command()

    def select(self):
        self.app._set_icon(self.box, "ticked", PRIMARY, ON_PRIMARY)

    def deselect(self):
        self.app._set_icon(self.box, "box", INPUT_BORDER)

    def set_enabled(self, enabled):
        self.enabled = enabled
        if self.text:
            self.text.configure(text_color=INK if enabled else DIMMED)
        tk.Frame.configure(self, cursor="hand2" if enabled else "")


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
        self.file_rows = {}
        self.theme = SAVED_THEME
        self.theme_icons = {}
        self.icon_animation = 0
        self.icons = {}
        self.icon_widgets = set()
        self._build_fonts()

        # An empty csv_paths means every file was removed, so only fall back
        # to the older csv_path setting when there is none
        saved = os.getenv("csv_paths")
        if saved is None:
            saved = os.getenv("csv_path") or ""
        self.csv_paths = [p for p in saved.split(CSV_PATHS_SEPARATOR) if p]

        # The files ticked for the tournament. Settings saved before files
        # could be unticked used every file listed
        selected = os.getenv("csv_selected")
        if selected is None:
            self.selection = set(self.csv_paths)
        else:
            self.selection = (
                set(selected.split(CSV_PATHS_SEPARATOR)) & set(self.csv_paths)
            )

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

        # A white card on the sage canvas: the contrast is the elevation,
        # so it needs no border or shadow
        self.panel = ctk.CTkFrame(
            self.root,
            corner_radius=24,
            fg_color=CARD
        )
        self.panel.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(0, WORKBENCH_PADDING),
            pady=WORKBENCH_PADDING
        )

        self._build_workbench()
        self._build_panel()
        self._refresh_files()
        self._enable_file_drop()
        self._resize_window()

        # CustomTkinter recolours its own widgets when the theme changes;
        # the log colours and the title bar are ours to update
        ctk.AppearanceModeTracker.add(self._apply_theme, self.root)
        self._apply_theme(ctk.get_appearance_mode())

    def _build_fonts(self):
        # DESIGN.md sets everything in Inter at weight 600 for emphasis and
        # 900 for the headline, falling back to the system UI font
        families = tkfont.families()
        family = "Inter" if "Inter" in families else (
            tkfont.nametofont("TkDefaultFont").actual("family")
        )

        def weighted(names, size):
            # Tk only knows normal and bold, so heavier and lighter weights
            # come from the families a font installs for them
            for name in names:
                if name in families:
                    return ctk.CTkFont(family=name, size=size)
            return ctk.CTkFont(family=family, size=size, weight="bold")

        def strong(size):
            return weighted(
                (f"{family} SemiBold", f"{family} Semibold"), size
            )

        self.title_font = weighted(
            (f"{family} Black", "Inter Black", "Segoe UI Black"), 34
        )
        self.subtitle_font = strong(20)
        self.heading_font = strong(16)
        self.label_font = strong(14)
        self.button_font = strong(16)
        self.body_font = ctk.CTkFont(family=family, size=14)
        self.small_font = ctk.CTkFont(family=family, size=12)
        self.link_font = strong(12)
        self.link_font.configure(underline=True)
        self.mono_font = ctk.CTkFont(family=MONO_FONT, size=12)

        # The eye from Windows' icon font (11, then 10); other systems get
        # words instead
        symbols = next(
            (
                name for name in ("Segoe Fluent Icons", "Segoe MDL2 Assets")
                if name in families
            ),
            None
        )
        if symbols:
            self.eye_icons = {False: "\ue890", True: "\ued1a"}  # View, Hide
            self.eye_font = ctk.CTkFont(family=symbols, size=16)
        else:
            self.eye_icons = {False: "Show", True: "Hide"}
            self.eye_font = self.link_font

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

        # Rows destroyed since leave their icons behind
        self.icon_widgets = {w for w in self.icon_widgets if w.winfo_exists()}
        for widget in self.icon_widgets:
            self._paint_icon(widget, index)

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

    # ---- Icons --------------------------------------------------------------

    def _icon(self, name, colors, index=None):
        """A drawn icon (see ICONS) in the colours of a theme, by default
        the current one."""
        if index is None:
            index = 1 if ctk.get_appearance_mode() == "Dark" else 0
        scaling = ctk.ScalingTracker.get_widget_scaling(self.root)
        size = round(ICON_SIZE * scaling)
        shades = tuple(color[index] for color in colors)

        if (name, shades, size) not in self.icons:
            self.icons[name, shades, size] = png_image(
                size, icon_pixels(name, shades, size)
            )
        return self.icons[name, shades, size]

    def _paint_icon(self, widget, index=None):
        name, colors = widget.drawn_icon
        # Already rendered at the scaled size, as in _show_theme_icon
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            widget.configure(image=self._icon(name, colors, index))

    def _set_icon(self, widget, name, *colors):
        # Remembered, so _apply_theme can repaint it in the new theme
        widget.drawn_icon = name, colors
        self.icon_widgets.add(widget)
        self._paint_icon(widget)

    def _icon_label(self, parent, name, *colors):
        # Created with an image, the only way CustomTkinter lays one out
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            label = ctk.CTkLabel(
                parent,
                text="",
                image=self._icon(name, colors),
                width=0,
                height=0
            )
        self._set_icon(label, name, *colors)
        return label

    def _icon_button(self, parent, name, command, color=MUTED, **kwargs):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            button = ctk.CTkButton(
                parent,
                text="",
                image=self._icon(name, (color,)),
                command=command,
                width=32,
                height=32,
                corner_radius=16,
                fg_color="transparent",
                hover_color=TRACK,
                **kwargs
            )
        self._set_icon(button, name, color)
        return button

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

    def _segmented(self, parent, values, variable, command=None, track=TRACK,
                   track_hover=TRACK_HOVER):
        # A pill track; the chosen segment takes a soft grey fill, since
        # solid ink is kept for primary actions
        selector = ctk.CTkSegmentedButton(
            parent,
            values=values,
            variable=variable,
            command=command,
            height=36,
            corner_radius=18,
            border_width=3,
            font=self.label_font,
            fg_color=track,
            selected_color=SELECTED,
            selected_hover_color=SELECTED,
            unselected_color=track,
            unselected_hover_color=track_hover,
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
            height=40,
            corner_radius=12,
            border_width=0,
            fg_color=INPUT_BG,
            text_color=INK,
            placeholder_text_color=DIMMED,
            font=self.body_font,
            **kwargs
        )
        def fill(color):
            # Borderless, so the fill darkens a little while typing. Buttons
            # placed inside the field, like the eye, follow it
            entry.configure(fg_color=color)
            for child in entry.winfo_children():
                if isinstance(child, ctk.CTkButton):
                    child.configure(fg_color=color, bg_color=color)

        entry.bind("<FocusIn>", lambda e: fill(INPUT_FOCUS))
        entry.bind("<FocusOut>", lambda e: fill(INPUT_BG))
        return entry

    def _checkbox(self, parent, text, command):
        return IconCheckbox(self, parent, text, command)

    # ---- Workbench ----------------------------------------------------------

    def _build_workbench(self):
        # The headline sits on the sage canvas, beside the tool card, as in
        # DESIGN.md's split hero
        hero = ctk.CTkFrame(self.workbench, fg_color="transparent")
        hero.pack(fill="x", padx=WORKBENCH_PADDING, pady=(WORKBENCH_PADDING, 0))

        self._label(hero, "Letterboxd to UwUFUFU", self.title_font).grid(
            row=0, column=0, sticky="w"
        )
        self._label(
            hero,
            "Build a UwUFUFU bracket tournament from your "
            "Letterboxd CSV exports.",
            self.body_font,
            MUTED
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))
        hero.grid_columnconfigure(0, weight=1)

        # The button only lays out an image it is created with, so start
        # with the icon for the current theme (see _show_theme_icon)
        dark = ctk.get_appearance_mode() == "Dark"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.theme_btn = ctk.CTkButton(
                hero,
                text="",
                image=self._theme_icon(0 if dark else THEME_ICON_FRAMES),
                command=self.toggle_theme,
                width=36,
                height=36,
                corner_radius=18,
                fg_color=CARD,
                hover_color=TRACK_HOVER
            )
        self.theme_btn.grid(row=0, column=1, sticky="e")

        top = ctk.CTkFrame(self.workbench, fg_color="transparent")
        top.pack(
            fill="x",
            padx=WORKBENCH_PADDING,
            pady=(WORKBENCH_PADDING, 16)
        )

        self.view = ctk.StringVar(value="Files")
        # On the sage canvas the track is white, like the cards below it
        self._segmented(
            top,
            ["Files", "Activity"],
            self.view,
            command=self._show_view,
            track=CARD,
            track_hover=TRACK
        ).pack(side="left")

        self.file_count_label = self._label(
            top, "", self.small_font, DIMMED
        )
        self.file_count_label.pack(side="right")

        area = ctk.CTkFrame(
            self.workbench,
            width=VIEW_WIDTH,
            height=VIEW_HEIGHT,
            fg_color="transparent"
        )
        area.pack(
            fill="both",
            expand=True,
            padx=WORKBENCH_PADDING,
            pady=(0, WORKBENCH_PADDING)
        )
        area.pack_propagate(False)

        self.file_view = ctk.CTkFrame(area, fg_color="transparent")
        self._build_file_view()

        self.log_area = ctk.CTkTextbox(
            area,
            corner_radius=24,
            border_width=0,
            border_spacing=16,
            fg_color=CARD,
            text_color=MUTED,
            font=self.mono_font,
            wrap="word",
            scrollbar_button_color=SCROLLBAR,
            scrollbar_button_hover_color=INPUT_BORDER
        )
        self._append_log("Activity will appear here.", "placeholder")

        self.views = {"Files": self.file_view, "Activity": self.log_area}
        self._show_view("Files")

    def _build_file_view(self):
        toolbar = ctk.CTkFrame(self.file_view, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 12))

        # Lined up with the checkboxes of the rows below
        self.select_all_box = self._checkbox(
            toolbar, "Select all", self.toggle_all
        )
        self.select_all_box.pack(side="left", padx=(ROW_PADDING, 0))

        ctk.CTkButton(
            toolbar,
            text="Add CSV",
            command=self.browse_files,
            width=104,
            height=36,
            corner_radius=18,
            font=self.label_font,
            **PRIMARY_STYLE
        ).pack(side="right")

        self.file_list = ctk.CTkScrollableFrame(
            self.file_view,
            corner_radius=0,
            fg_color="transparent"
        )
        # Re-check when the rows or the space for them change
        self.file_list.bind("<Configure>", self._fit_file_list, add="+")
        self.file_list._parent_canvas.bind(
            "<Configure>", self._fit_file_list, add="+"
        )

        # Stands in for the list until a file is added
        self.empty_state = ctk.CTkFrame(
            self.file_view,
            corner_radius=24,
            fg_color=CARD
        )
        message = ctk.CTkFrame(self.empty_state, fg_color="transparent")
        message.place(relx=0.5, rely=0.5, anchor="center")

        self._label(message, "No CSV files yet", self.subtitle_font).pack()
        self._label(
            message,
            "Drag your Letterboxd exports here,\n"
            "or click to choose them.",
            self.body_font,
            MUTED,
            justify="center"
        ).pack(pady=(8, 0))

        self._make_clickable(
            self.empty_state,
            self.browse_files,
            lambda hover: self.empty_state.configure(
                fg_color=CARD_HOVER if hover else CARD
            )
        )

        # Covers the list while files are dragged over it
        self.drop_overlay = ctk.CTkFrame(
            self.file_view,
            corner_radius=24,
            fg_color=CARD_HOVER
        )
        message = ctk.CTkFrame(self.drop_overlay, fg_color="transparent")
        message.place(relx=0.5, rely=0.5, anchor="center")

        self._label(message, "Drop to add", self.subtitle_font).pack()
        self._label(
            message,
            "Only CSV files are added.",
            self.body_font,
            MUTED,
            justify="center"
        ).pack(pady=(8, 0))

    def _enable_file_drop(self):
        # tkdnd ships builds for the common systems only; elsewhere files
        # can still be added with Add CSV
        try:
            TkinterDnD._require(self.root)
        except Exception:
            return

        # A drop on a row or the empty state reaches the view holding them
        self.file_view.drop_target_register(DND_FILES)
        self.file_view.dnd_bind("<<DropEnter>>", self._drag_enter)
        self.file_view.dnd_bind("<<DropLeave>>", self._drag_leave)
        self.file_view.dnd_bind("<<Drop>>", self._drop_files)

    def _drag_enter(self, event):
        self.drop_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.drop_overlay.lift()
        return event.action

    def _drag_leave(self, event):
        self.drop_overlay.place_forget()
        return event.action

    def _drop_files(self, event):
        self.drop_overlay.place_forget()
        # Paths with spaces arrive wrapped in braces, as a Tcl list
        self.add_files(
            path for path in self.root.tk.splitlist(event.data)
            if path.lower().endswith(".csv") and os.path.isfile(path)
        )
        return COPY

    def _show_view(self, name):
        self.view.set(name)
        for view_name, widget in self.views.items():
            if view_name == name:
                widget.pack(fill="both", expand=True)
            else:
                widget.pack_forget()

    def _fit_file_list(self, _=None):
        # The list scrolls with the mouse wheel only. CTkScrollableFrame
        # (5.2.2) shows its scrollbar again when it lays itself out, so hide
        # it each time
        self.file_list._scrollbar.grid_remove()
        canvas = self.file_list._parent_canvas
        if self.file_list.winfo_reqheight() <= canvas.winfo_height():
            canvas.yview_moveto(0)

    def _refresh_files(self):
        for child in self.file_list.winfo_children():
            child.destroy()
        self.file_rows.clear()

        for path in self.csv_paths:
            self._file_row(path)

        if self.csv_paths:
            self.empty_state.pack_forget()
            self.file_list.pack(fill="both", expand=True)
        else:
            self.file_list.pack_forget()
            self.empty_state.pack(fill="both", expand=True)

        self._update_selection()

    def _preview(self, path):
        """Return the movies in a CSV and any problem that stops its use."""
        if not os.path.isfile(path):
            return [], "File not found"

        # Keyed by modification time, so a file edited since is read again
        key = path, os.path.getmtime(path)
        if key not in self.previews:
            try:
                movies = parser.extract_movies(path)
                self.previews[key] = (
                    movies,
                    None if movies else "No movies found"
                )
            except (Exception, SystemExit):
                self.previews[key] = ([], "Can't read this file")

        return self.previews[key]

    def _make_clickable(self, card, command, hover, skip=()):
        def leave(_):
            # Moving onto a child widget also fires <Leave>, so only reset
            # once the pointer has really left the card
            if not pointer_inside(card):
                hover(False)

        def bind(widget):
            if widget in skip:
                return
            tk.Misc.bind(widget, "<Enter>", lambda _: hover(True), add="+")
            tk.Misc.bind(widget, "<Leave>", leave, add="+")
            tk.Misc.bind(widget, "<Button-1>", lambda _: command(), add="+")
            for child in widget.winfo_children():
                bind(child)

        bind(card)
        tk.Frame.configure(card, cursor="hand2")

    def _file_row(self, path):
        movies, problem = self._preview(path)
        account = parser.export_account(path)

        row = ctk.CTkFrame(
            self.file_list,
            corner_radius=16,
            fg_color=CARD
        )
        row.pack(fill="x", pady=(0, ROW_GAP))
        row.grid_columnconfigure(1, weight=1)

        check = self._checkbox(row, "", lambda: self.toggle_csv(path))
        check.grid(row=0, column=0, rowspan=2, padx=(ROW_PADDING, 12))

        name = self._label(
            row, clip(os.path.basename(path), 40), self.label_font
        )
        name.grid(row=0, column=1, sticky="ew", pady=(14, 0))

        self._label(
            row,
            f"Letterboxd account: {account or 'unknown'}",
            self.small_font,
            MUTED if account else DIMMED
        ).grid(row=1, column=1, sticky="ew", pady=(2, 14))

        count = len(movies)
        self._label(
            row,
            problem or f"{count} movie{'s' if count != 1 else ''}",
            self.small_font,
            DANGER if problem else MUTED
        ).grid(row=0, column=2, rowspan=2, padx=(12, 0))

        exists = os.path.isfile(path)
        open_btn = self._icon_button(
            row,
            "folder",
            lambda: self.show_csv(path),
            MUTED if exists else PREVIEW_TEXT,
            state=tk.NORMAL if exists else tk.DISABLED
        )
        open_btn.grid(row=0, column=3, rowspan=2, padx=(12, 0))

        remove_btn = self._icon_button(
            row, "cross", lambda: self.remove_csv(path)
        )
        remove_btn.grid(row=0, column=4, rowspan=2, padx=(4, 12))

        self.file_rows[path] = row, check, name
        self._make_clickable(
            row,
            lambda: self.toggle_csv(path),
            lambda hover: row.configure(fg_color=self._row_fill(path, hover)),
            skip=(check, open_btn, remove_btn)
        )
        self._style_row(path)

    def _style_row(self, path):
        """Show whether a file goes into the tournament."""
        row, check, name = self.file_rows[path]
        selected = path in self.selection

        if selected:
            check.select()
        else:
            check.deselect()

        row.configure(fg_color=self._row_fill(path, pointer_inside(row)))
        name.configure(text_color=INK if selected else MUTED)

    def _row_fill(self, path, hover):
        # Rows are borderless cards that darken a little on hover
        if path in self.selection:
            return CARD_SELECTED_HOVER if hover else CARD_SELECTED
        return CARD_HOVER if hover else CARD

    def show_csv(self, path):
        try:
            show_in_file_manager(path)
        except OSError as e:
            messagebox.showerror("Can't Open Folder", f"{path}\n\n{e}")

    def browse_files(self):
        filenames = filedialog.askopenfilenames(
            filetypes=[
                ("CSV Files", "*.csv"),
                ("All Files", "*.*")
            ]
        )
        self.add_files(filenames)

    def add_files(self, filenames):
        # New files start unselected, so adding one never changes what
        # already goes into the tournament. Paths are kept with forward
        # slashes, as the file dialog gives them, so a dropped file already
        # in the list isn't added twice
        for filename in filenames:
            filename = Path(filename).as_posix()
            if filename not in self.csv_paths:
                self.csv_paths.append(filename)

        self._refresh_files()
        self._save_files()

    def remove_csv(self, path):
        self.csv_paths.remove(path)
        self.selection.discard(path)
        self._refresh_files()
        self._save_files()

    def toggle_csv(self, path):
        if path in self.selection:
            self.selection.remove(path)
        else:
            self.selection.add(path)
        self._style_row(path)
        self._update_selection()
        self._save_files()

    def _save_files(self):
        # Saved on every change, so the list survives closing the app
        # without creating a tournament
        save_setting("csv_paths", CSV_PATHS_SEPARATOR.join(self.csv_paths))
        save_setting(
            "csv_selected",
            CSV_PATHS_SEPARATOR.join(self._selected_paths())
        )

    def toggle_all(self):
        # Selects every file, or none once they all are
        if self.selection == set(self.csv_paths):
            self.selection = set()
        else:
            self.selection = set(self.csv_paths)

        for path in self.csv_paths:
            self._style_row(path)
        self._update_selection()
        self._save_files()

    def _selected_paths(self):
        # In list order, which is the order the files are combined in
        return [path for path in self.csv_paths if path in self.selection]

    def _update_selection(self):
        count = len(self._selected_paths())
        total = len(self.csv_paths)

        if total and count == total:
            self.select_all_box.select()
        else:
            self.select_all_box.deselect()
        self.select_all_box.set_enabled(bool(total))

        self.file_count_label.configure(
            text=f"{count} of {total} selected" if total else ""
        )

        if not total:
            summary = "No files added"
        elif not count:
            summary = "No files selected"
        else:
            summary = (
                f"{count} of {total} file{'s' if total != 1 else ''} selected"
            )
        self.files_summary.configure(
            text=summary,
            text_color=INK if count else DIMMED
        )

        self.mode_selector.configure(
            state=tk.NORMAL if count > 1 else tk.DISABLED
        )
        self._update_mode_help()

    # ---- Tool panel ---------------------------------------------------------

    def _build_panel(self):
        content = ctk.CTkFrame(self.panel, fg_color="transparent")
        content.pack(
            fill="both",
            expand=True,
            padx=PANEL_PADDING,
            pady=PANEL_PADDING
        )

        body = self._step(content, "Files")
        self.files_summary = self._label(body, "", self.body_font)
        self.files_summary.pack(fill="x")
        self._label(
            body,
            "Only the selected files go into the tournament.",
            self.small_font,
            DIMMED
        ).pack(fill="x", pady=(2, 0))

        body = self._step(content, "Settings")
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

        body = self._step(content, "UwUFUFU account")
        self._label(body, "Email", self.label_font).pack(fill="x")

        self.email_entry = self._entry(body, placeholder_text="you@example.com")
        self.email_entry.pack(fill="x", pady=(4, 8))

        if email := os.getenv("email"):
            self.email_entry.insert(0, email)

        self._label(body, "Password", self.label_font).pack(fill="x")

        self.pass_entry = self._entry(body, show="•")
        self.pass_entry.pack(fill="x", pady=(4, 0))

        # The eye sits inside the field, on the right
        self.password_visible = False
        self.pass_toggle = ctk.CTkButton(
            self.pass_entry,
            text=self.eye_icons[False],
            command=self._toggle_password,
            width=28,
            height=28,
            fg_color=INPUT_BG,
            bg_color=INPUT_BG,
            hover=False,
            text_color=MUTED,
            font=self.eye_font
        )
        self.pass_toggle.place(relx=1, rely=0.5, x=-8, anchor="e")

        # Keep typed text clear of the eye. CustomTkinter only resets this
        # padding when the display scaling changes
        scaling = ctk.ScalingTracker.get_widget_scaling(self.root)
        self.pass_entry._entry.grid_configure(
            padx=(round(12 * scaling), round(44 * scaling))
        )

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
            height=48,
            corner_radius=24,
            text_color_disabled=DIMMED,
            font=self.button_font,
            **PRIMARY_STYLE
        )
        self.start_btn.pack(fill="x", pady=(20, 0))

        body = self._step(content, "Review")
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
            height=8,
            corner_radius=4,
            fg_color=TRACK,
            progress_color=TRACK
        )
        self.progress.set(0)
        self.progress.pack(fill="x", pady=(10, 0))

    def _step(self, parent, title):
        # Whitespace, not rules, separates the steps
        first = not parent.winfo_children()
        self._label(parent, title, self.heading_font).pack(
            fill="x", pady=(0 if first else 24, 0)
        )

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.pack(fill="x", pady=(8, 0))
        return body

    def _selected_mode(self):
        return next(
            value for value, label in MODE_LABELS.items()
            if label == self.combine_mode.get()
        )

    def _update_mode_help(self):
        if len(self._selected_paths()) > 1:
            text = MODE_HELP[self._selected_mode()]
        else:
            text = "Select two or more files to combine them."
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
        self.password_visible = not self.password_visible
        self.pass_entry.configure(show="" if self.password_visible else "•")
        self.pass_toggle.configure(
            text=self.eye_icons[self.password_visible]
        )

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
        # Unselected files are left out of every check and of the tournament
        csv_paths = self._selected_paths()
        mode = self._selected_mode()
        quality = self._selected_quality()
        email = self.email_entry.get().strip()
        password = self.pass_entry.get().strip()

        if not csv_paths:
            messagebox.showerror(
                "No Files Selected",
                "Select at least one CSV file under Files to include it "
                "in the tournament."
            )
            return

        if not all((email, password)):
            messagebox.showerror(
                "Missing Fields",
                "Please fill in all fields (Email and Password)."
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

        if not any(self._preview(path)[0] for path in csv_paths):
            messagebox.showerror(
                "No Movies Found",
                "None of the selected CSV files contains any movies. "
                "Select a Letterboxd export with at least one movie."
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
            f"csv_paths={CSV_PATHS_SEPARATOR.join(self.csv_paths)}\n"
            f"csv_selected={CSV_PATHS_SEPARATOR.join(csv_paths)}\n"
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
