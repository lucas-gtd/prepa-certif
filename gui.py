"""Desktop GUI for Prépa Certif.

Modern desktop UI inspired by Claude Desktop / Discord / ChatGPT:

* Dark, warm color palette with a single accent color.
* Sidebar + content layout with subtle separators (no Win95 chrome).
* Soft typography (Segoe UI Variable on Windows, system defaults elsewhere).
* Rounded "pill" accent button with hover state.
* Card-style result area, no SUNKEN borders or LabelFrame chrome.
* Full keyboard navigation, screen-reader friendly labels, and clickable
  links (with the raw URL kept inline for copy/paste and accessibility).
* Settings dialog for the API key so users never edit a .env file.
"""
from __future__ import annotations

import os
import platform
import re
import threading
import webbrowser
from pathlib import Path
from queue import Empty, Queue
from tkinter import (
    BOTH,
    DISABLED,
    END,
    FLAT,
    LEFT,
    NORMAL,
    RIGHT,
    TOP,
    W,
    X,
    Y,
    Menu,
    StringVar,
    Tk,
    Toplevel,
    messagebox,
)
from tkinter import font as tkfont
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from dotenv import load_dotenv, set_key

from agent import run_certification_agent
from tools import fetch_certifications

ENV_PATH = Path(__file__).resolve().parent / ".env"
DEFAULT_MODEL_ID = "google/gemma-4-31b-it"

APP_TITLE = "Prépa Certif"
APP_SUBTITLE = "Microsoft Certification Study Planner"


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

class Theme:
    """Modern dark palette inspired by Claude Desktop's warm neutrals."""

    # Surfaces
    bg = "#1f1e1d"          # app background
    sidebar = "#191817"     # sidebar / header background
    surface = "#262524"     # cards, inputs
    surface_hi = "#2f2d2c"  # hover / focus
    border = "#3a3836"

    # Text
    text = "#ececec"
    text_muted = "#a3a09c"
    text_subtle = "#6f6c68"

    # Accent (Claude-ish warm coral)
    accent = "#d97757"
    accent_hi = "#e08a6e"
    accent_pressed = "#c2613f"
    accent_text = "#1a1716"

    # Semantic
    link = "#f0a37f"
    error = "#e06c75"


def _ui_font_family() -> str:
    """Pick a clean, modern UI font available on the host system."""
    families = set(tkfont.families())
    for candidate in (
        "Segoe UI Variable",
        "Segoe UI",
        "SF Pro Text",
        "Inter",
        "Helvetica Neue",
        "Helvetica",
        "Arial",
    ):
        if candidate in families:
            return candidate
    return tkfont.nametofont("TkDefaultFont").cget("family")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ensure_env_file() -> None:
    """Make sure a .env file exists so set_key() can write to it."""
    if not ENV_PATH.exists():
        ENV_PATH.write_text(
            f"OPENROUTER_API_KEY=\nMODEL_ID={DEFAULT_MODEL_ID}\n",
            encoding="utf-8",
        )
    load_dotenv(ENV_PATH, override=True)


def save_settings(api_key: str, model_id: str) -> None:
    ensure_env_file()
    set_key(str(ENV_PATH), "OPENROUTER_API_KEY", api_key)
    set_key(str(ENV_PATH), "MODEL_ID", model_id or DEFAULT_MODEL_ID)
    os.environ["OPENROUTER_API_KEY"] = api_key
    os.environ["MODEL_ID"] = model_id or DEFAULT_MODEL_ID


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------

class SettingsDialog(Toplevel):
    def __init__(self, master: Tk):
        super().__init__(master)
        self.title("Settings")
        self.transient(master)
        self.grab_set()
        self.configure(bg=Theme.bg)
        self.resizable(False, False)
        self.minsize(520, 240)

        ensure_env_file()
        self.api_key_var = StringVar(value=os.getenv("OPENROUTER_API_KEY", ""))
        self.model_var = StringVar(value=os.getenv("MODEL_ID", DEFAULT_MODEL_ID))

        frame = ttk.Frame(self, padding=24, style="Card.TFrame")
        frame.pack(fill=BOTH, expand=True, padx=16, pady=16)

        ttk.Label(frame, text="Settings", style="H1.TLabel").grid(
            row=0, column=0, columnspan=2, sticky=W, pady=(0, 4)
        )
        ttk.Label(
            frame,
            text=(
                "Enter your OpenRouter API key. You can get a free key at "
                "https://openrouter.ai/keys."
            ),
            wraplength=460,
            justify=LEFT,
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky=W, pady=(0, 16))

        ttk.Label(frame, text="OpenRouter API key", style="FieldLabel.TLabel").grid(
            row=2, column=0, columnspan=2, sticky=W, pady=(0, 4)
        )
        key_entry = ttk.Entry(
            frame, textvariable=self.api_key_var, width=44, show="•",
            style="Modern.TEntry",
        )
        key_entry.grid(row=3, column=0, columnspan=2, sticky="ew", ipady=4)

        show_var = StringVar(value="0")

        def toggle_show():
            key_entry.config(show="" if show_var.get() == "1" else "•")

        ttk.Checkbutton(
            frame, text="Show key", variable=show_var, onvalue="1", offvalue="0",
            command=toggle_show, style="Modern.TCheckbutton",
        ).grid(row=4, column=0, sticky=W, pady=(6, 14))

        ttk.Label(frame, text="Model ID", style="FieldLabel.TLabel").grid(
            row=5, column=0, columnspan=2, sticky=W, pady=(0, 4)
        )
        ttk.Entry(
            frame, textvariable=self.model_var, width=44, style="Modern.TEntry",
        ).grid(row=6, column=0, columnspan=2, sticky="ew", ipady=4)

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        btns = ttk.Frame(frame, style="Card.TFrame")
        btns.grid(row=7, column=0, columnspan=2, sticky="e", pady=(20, 0))
        ttk.Button(
            btns, text="Cancel", command=self.destroy, style="Ghost.TButton",
        ).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(
            btns, text="Save", command=self._save, style="Accent.TButton",
            default="active",
        ).pack(side=RIGHT)

        self.bind("<Return>", lambda _e: self._save())
        self.bind("<Escape>", lambda _e: self.destroy())
        key_entry.focus_set()

    def _save(self):
        save_settings(self.api_key_var.get().strip(), self.model_var.get().strip())
        messagebox.showinfo("Settings saved", "Your settings have been saved.", parent=self)
        self.destroy()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class PrepaCertifApp:
    URL_RE = re.compile(r"https?://[^\s)\]]+")

    def __init__(self, root: Tk):
        self.root = root
        self.root.title(f"{APP_TITLE} — {APP_SUBTITLE}")
        self.root.geometry("1100x780")
        self.root.minsize(820, 560)
        self.root.configure(bg=Theme.bg)

        ensure_env_file()

        self._setup_fonts()
        self._setup_style()
        self._build_menu()
        self._build_layout()

        self.cert_choices: list[str] = []
        self.worker: threading.Thread | None = None
        self.queue: Queue = Queue()

        self.root.after(50, self._load_certifications)
        self.root.after(100, self._poll_queue)

        # Keyboard shortcuts
        self.root.bind("<Control-comma>", lambda _e: self.open_settings())
        self.root.bind("<F5>", lambda _e: self.run_search())
        self.root.bind("<Escape>", lambda _e: self.root.focus_set())

    # ---- UI construction ------------------------------------------------
    def _setup_fonts(self) -> None:
        family = _ui_font_family()
        self.ui_family = family

        # Tk built-in named fonts (affects ttk widgets by default)
        for name, size in (
            ("TkDefaultFont", 11),
            ("TkTextFont", 11),
            ("TkMenuFont", 11),
            ("TkHeadingFont", 11),
        ):
            try:
                f = tkfont.nametofont(name)
                f.configure(family=family, size=size)
            except Exception:
                pass

        self.font_body = tkfont.Font(family=family, size=11)
        self.font_body_lg = tkfont.Font(family=family, size=12)
        self.font_h1 = tkfont.Font(family=family, size=20, weight="bold")
        self.font_h2 = tkfont.Font(family=family, size=15, weight="bold")
        self.font_h3 = tkfont.Font(family=family, size=12, weight="bold")
        self.font_brand = tkfont.Font(family=family, size=14, weight="bold")
        self.font_small = tkfont.Font(family=family, size=10)

    def _setup_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        T = Theme
        ui = self.ui_family

        # Base
        style.configure(".", background=T.bg, foreground=T.text, font=(ui, 11))

        # Frames
        style.configure("TFrame", background=T.bg)
        style.configure("Sidebar.TFrame", background=T.sidebar)
        style.configure("Card.TFrame", background=T.surface)
        style.configure("Header.TFrame", background=T.sidebar)

        # Labels
        style.configure("TLabel", background=T.bg, foreground=T.text)
        style.configure("Sidebar.TLabel", background=T.sidebar, foreground=T.text)
        style.configure("SidebarMuted.TLabel",
                        background=T.sidebar, foreground=T.text_muted, font=(ui, 10))
        style.configure("Brand.TLabel",
                        background=T.sidebar, foreground=T.text, font=self.font_brand)
        style.configure("BrandTag.TLabel",
                        background=T.sidebar, foreground=T.accent, font=(ui, 10, "bold"))
        style.configure("H1.TLabel", background=T.bg, foreground=T.text, font=self.font_h1)
        style.configure("H2.TLabel", background=T.bg, foreground=T.text, font=self.font_h2)
        style.configure("Muted.TLabel",
                        background=T.bg, foreground=T.text_muted, font=(ui, 10))
        style.configure("CardMuted.TLabel",
                        background=T.surface, foreground=T.text_muted, font=(ui, 10))
        style.configure("FieldLabel.TLabel",
                        background=T.surface, foreground=T.text_muted,
                        font=(ui, 10, "bold"))
        style.configure("Status.TLabel",
                        background=T.sidebar, foreground=T.text_muted,
                        font=(ui, 10), wraplength=240, justify=LEFT)
        style.configure("StatusBar.TLabel",
                        background=T.sidebar, foreground=T.text_subtle,
                        font=(ui, 9), padding=(12, 6))

        # Separators
        style.configure("TSeparator", background=T.border)

        # Buttons — Accent (filled pill)
        style.configure(
            "Accent.TButton",
            background=T.accent, foreground=T.accent_text,
            font=(ui, 11, "bold"),
            borderwidth=0, focusthickness=0, relief=FLAT, padding=(18, 10),
        )
        style.map(
            "Accent.TButton",
            background=[("active", T.accent_hi), ("pressed", T.accent_pressed),
                        ("disabled", T.surface_hi)],
            foreground=[("disabled", T.text_subtle)],
        )

        # Buttons — Ghost (outline-less, subtle)
        style.configure(
            "Ghost.TButton",
            background=T.surface, foreground=T.text,
            font=(ui, 11), borderwidth=0, focusthickness=0,
            relief=FLAT, padding=(14, 9),
        )
        style.map(
            "Ghost.TButton",
            background=[("active", T.surface_hi), ("pressed", T.border)],
        )

        # Buttons — Sidebar icon-like
        style.configure(
            "Sidebar.TButton",
            background=T.sidebar, foreground=T.text_muted,
            font=(ui, 11), borderwidth=0, focusthickness=0,
            relief=FLAT, padding=(10, 8), anchor="w",
        )
        style.map(
            "Sidebar.TButton",
            background=[("active", T.surface), ("pressed", T.surface_hi)],
            foreground=[("active", T.text)],
        )

        # Entries
        style.configure(
            "Modern.TEntry",
            fieldbackground=T.surface, background=T.surface,
            foreground=T.text, insertcolor=T.text,
            bordercolor=T.border, lightcolor=T.border, darkcolor=T.border,
            borderwidth=1, relief=FLAT, padding=8,
        )
        style.map(
            "Modern.TEntry",
            bordercolor=[("focus", T.accent)],
            lightcolor=[("focus", T.accent)],
            darkcolor=[("focus", T.accent)],
        )

        # Combobox
        style.configure(
            "Modern.TCombobox",
            fieldbackground=T.surface, background=T.surface,
            foreground=T.text, arrowcolor=T.text_muted,
            bordercolor=T.border, lightcolor=T.border, darkcolor=T.border,
            borderwidth=1, relief=FLAT, padding=8,
        )
        style.map(
            "Modern.TCombobox",
            fieldbackground=[("readonly", T.surface), ("disabled", T.surface)],
            foreground=[("disabled", T.text_subtle)],
            bordercolor=[("focus", T.accent)],
            lightcolor=[("focus", T.accent)],
            darkcolor=[("focus", T.accent)],
            arrowcolor=[("active", T.text)],
        )
        # The combobox dropdown listbox isn't a ttk widget — style via option db.
        self.root.option_add("*TCombobox*Listbox.background", T.surface)
        self.root.option_add("*TCombobox*Listbox.foreground", T.text)
        self.root.option_add("*TCombobox*Listbox.selectBackground", T.accent)
        self.root.option_add("*TCombobox*Listbox.selectForeground", T.accent_text)
        self.root.option_add("*TCombobox*Listbox.borderWidth", 0)
        self.root.option_add("*TCombobox*Listbox.font", (ui, 11))

        # Checkbutton
        style.configure(
            "Modern.TCheckbutton",
            background=T.surface, foreground=T.text_muted,
            focuscolor=T.surface, font=(ui, 10),
        )
        style.map(
            "Modern.TCheckbutton",
            background=[("active", T.surface)],
            foreground=[("active", T.text)],
        )

        # Progress bar
        style.configure(
            "Modern.Horizontal.TProgressbar",
            background=T.accent, troughcolor=T.surface,
            bordercolor=T.surface, lightcolor=T.accent, darkcolor=T.accent,
            thickness=4,
        )

    def _build_menu(self) -> None:
        menubar = Menu(self.root)
        filemenu = Menu(menubar, tearoff=0, bg=Theme.surface, fg=Theme.text,
                        activebackground=Theme.accent, activeforeground=Theme.accent_text,
                        borderwidth=0)
        filemenu.add_command(label="Settings…", accelerator="Ctrl+,", command=self.open_settings)
        filemenu.add_separator()
        filemenu.add_command(label="Quit", accelerator="Alt+F4", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=filemenu)

        helpmenu = Menu(menubar, tearoff=0, bg=Theme.surface, fg=Theme.text,
                        activebackground=Theme.accent, activeforeground=Theme.accent_text,
                        borderwidth=0)
        helpmenu.add_command(label="How to use", command=self.show_help)
        helpmenu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=helpmenu)

        self.root.config(menu=menubar)

    def _build_layout(self) -> None:
        T = Theme

        # Root grid: sidebar | content
        self.root.grid_columnconfigure(0, weight=0, minsize=280)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        # ---- Sidebar ----
        sidebar = ttk.Frame(self.root, style="Sidebar.TFrame")
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.configure(width=280)
        sidebar.grid_rowconfigure(4, weight=1)
        sidebar.grid_columnconfigure(0, weight=1)

        # Brand row
        brand = ttk.Frame(sidebar, style="Sidebar.TFrame")
        brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(22, 4))
        # Faux logo dot
        dot = ttk.Frame(brand, style="Sidebar.TFrame", width=10, height=10)
        dot.pack(side=LEFT, padx=(0, 10), pady=(4, 0))
        dot.configure(width=10, height=10)
        # Use a Canvas dot for color
        try:
            import tkinter as tk_  # local
            c = tk_.Canvas(brand, width=12, height=12, bg=T.sidebar,
                           highlightthickness=0, bd=0)
            c.create_oval(1, 1, 11, 11, fill=T.accent, outline="")
            c.pack(side=LEFT, padx=(0, 10), pady=(4, 0))
            dot.destroy()
        except Exception:
            pass

        ttk.Label(brand, text=APP_TITLE, style="Brand.TLabel").pack(side=LEFT)

        ttk.Label(
            sidebar,
            text=APP_SUBTITLE.upper(),
            style="BrandTag.TLabel",
        ).grid(row=1, column=0, sticky=W, padx=20, pady=(0, 22))

        ttk.Separator(sidebar, orient="horizontal").grid(
            row=2, column=0, sticky="ew", padx=20
        )

        # Sidebar navigation / actions
        nav = ttk.Frame(sidebar, style="Sidebar.TFrame")
        nav.grid(row=3, column=0, sticky="ew", padx=12, pady=12)
        nav.grid_columnconfigure(0, weight=1)

        ttk.Button(
            nav, text="⚙   Settings", style="Sidebar.TButton",
            command=self.open_settings,
        ).grid(row=0, column=0, sticky="ew", pady=2)
        ttk.Button(
            nav, text="❓   How to use", style="Sidebar.TButton",
            command=self.show_help,
        ).grid(row=1, column=0, sticky="ew", pady=2)
        ttk.Button(
            nav, text="ℹ    About", style="Sidebar.TButton",
            command=self.show_about,
        ).grid(row=2, column=0, sticky="ew", pady=2)

        # Status panel (bottom of sidebar)
        status_panel = ttk.Frame(sidebar, style="Sidebar.TFrame")
        status_panel.grid(row=5, column=0, sticky="ew", padx=20, pady=(0, 18))
        status_panel.grid_columnconfigure(0, weight=1)

        ttk.Separator(sidebar, orient="horizontal").grid(
            row=4, column=0, sticky="sew", padx=20, pady=(0, 14)
        )

        ttk.Label(status_panel, text="STATUS", style="BrandTag.TLabel").grid(
            row=0, column=0, sticky=W, pady=(0, 6),
        )
        self.status_var = StringVar(value="Loading certifications…")
        self.status_label = ttk.Label(
            status_panel, textvariable=self.status_var, style="Status.TLabel",
        )
        self.status_label.grid(row=1, column=0, sticky="ew")
        self.progress = ttk.Progressbar(
            status_panel, mode="indeterminate",
            style="Modern.Horizontal.TProgressbar",
        )
        self.progress.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.progress.start(80)

        # ---- Content ----
        content = ttk.Frame(self.root, style="TFrame")
        content.grid(row=0, column=1, sticky="nsew")
        content.grid_rowconfigure(2, weight=1)
        content.grid_columnconfigure(0, weight=1)

        # Header
        header = ttk.Frame(content, style="TFrame", padding=(32, 28, 32, 8))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            header, text="Build a study plan", style="H1.TLabel",
        ).pack(anchor=W)
        ttk.Label(
            header,
            text=(
                "Pick a Microsoft certification — we'll gather official Microsoft "
                "Learn paths and curated YouTube videos for you."
            ),
            style="Muted.TLabel", wraplength=820, justify=LEFT,
        ).pack(anchor=W, pady=(6, 0))

        # Picker card
        picker_wrap = ttk.Frame(content, style="TFrame", padding=(32, 8, 32, 8))
        picker_wrap.grid(row=1, column=0, sticky="ew")
        picker_wrap.grid_columnconfigure(0, weight=1)

        card = ttk.Frame(picker_wrap, style="Card.TFrame", padding=18)
        card.grid(row=0, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        row = ttk.Frame(card, style="Card.TFrame")
        row.grid(row=0, column=0, sticky="ew")
        row.grid_columnconfigure(0, weight=1)

        self.cert_var = StringVar()
        self.cert_combo = ttk.Combobox(
            row, textvariable=self.cert_var, state="disabled",
            font=self.font_body_lg, style="Modern.TCombobox",
        )
        self.cert_combo.grid(row=0, column=0, sticky="ew", ipady=6)
        self.cert_combo.bind("<KeyRelease>", self._on_combo_typing)
        self.cert_combo.bind("<Return>", lambda _e: self.run_search())

        self.run_btn = ttk.Button(
            row, text="Find resources", style="Accent.TButton",
            command=self.run_search, state=DISABLED,
        )
        self.run_btn.grid(row=0, column=1, sticky="e", padx=(12, 0))

        ttk.Label(
            card,
            text="Start typing to filter • Press Enter to search • F5 re-runs",
            style="CardMuted.TLabel",
        ).grid(row=1, column=0, sticky=W, pady=(10, 0))

        # Results card
        results_wrap = ttk.Frame(content, style="TFrame", padding=(32, 12, 32, 16))
        results_wrap.grid(row=2, column=0, sticky="nsew")
        results_wrap.grid_rowconfigure(0, weight=1)
        results_wrap.grid_columnconfigure(0, weight=1)

        results_card = ttk.Frame(results_wrap, style="Card.TFrame", padding=2)
        results_card.grid(row=0, column=0, sticky="nsew")
        results_card.grid_rowconfigure(0, weight=1)
        results_card.grid_columnconfigure(0, weight=1)

        self.results = ScrolledText(
            results_card,
            wrap="word",
            font=self.font_body_lg,
            bg=T.surface, fg=T.text,
            insertbackground=T.text,
            selectbackground=T.accent, selectforeground=T.accent_text,
            padx=22, pady=20,
            relief=FLAT, borderwidth=0, highlightthickness=0,
            height=18,
        )
        self.results.grid(row=0, column=0, sticky="nsew")
        # Style the scrollbar that ScrolledText creates
        try:
            self.results.vbar.configure(
                background=T.surface, troughcolor=T.surface,
                activebackground=T.surface_hi, borderwidth=0,
                highlightthickness=0, width=10, elementborderwidth=0,
            )
        except Exception:
            pass

        self.results.tag_configure(
            "h1", font=self.font_h1, spacing3=10, spacing1=10, foreground=T.text,
        )
        self.results.tag_configure(
            "h2", font=self.font_h2, spacing3=8, spacing1=14, foreground=T.accent,
        )
        self.results.tag_configure(
            "h3", font=self.font_h3, spacing3=4, spacing1=8, foreground=T.text,
        )
        self.results.tag_configure(
            "bold", font=(self.ui_family, 12, "bold"), foreground=T.text,
        )
        self.results.tag_configure("muted", foreground=T.text_muted)
        self.results.tag_configure(
            "link", foreground=T.link, underline=True,
        )
        self.results.tag_bind("link", "<Enter>", lambda _e: self.results.config(cursor="hand2"))
        self.results.tag_bind("link", "<Leave>", lambda _e: self.results.config(cursor=""))
        self.results.configure(state=DISABLED)

        self._set_placeholder()

        # Footer status bar
        self.bottom_status = ttk.Label(
            self.root, text="Ready", anchor=W, style="StatusBar.TLabel",
        )
        self.bottom_status.grid(row=1, column=0, columnspan=2, sticky="ew")

    # ---- Behavior --------------------------------------------------------
    def _set_placeholder(self) -> None:
        self.results.configure(state=NORMAL)
        self.results.delete("1.0", END)
        self.results.insert(
            END,
            "Your personalised study plan will appear here.\n\n",
            "h3",
        )
        self.results.insert(
            END,
            "Pick a certification above and press “Find resources” to get "
            "official Microsoft Learn paths and curated YouTube videos.",
            "muted",
        )
        self.results.configure(state=DISABLED)

    def _load_certifications(self) -> None:
        self._set_status("Loading the list of Microsoft certifications…")

        def work():
            try:
                choices = fetch_certifications()
                self.queue.put(("certs", choices))
            except Exception as exc:  # noqa: BLE001
                self.queue.put(("certs_error", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _on_combo_typing(self, event):
        if event.keysym in ("Up", "Down", "Return", "Escape", "Left", "Right", "Tab"):
            return
        typed = self.cert_var.get().lower()
        if not self.cert_choices:
            return
        filtered = [c for c in self.cert_choices if typed in c.lower()] if typed else self.cert_choices
        self.cert_combo["values"] = filtered

    def run_search(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        cert = self.cert_var.get().strip()
        if not cert:
            messagebox.showwarning(
                "Pick a certification",
                "Please select a certification from the list first.",
                parent=self.root,
            )
            return

        if not os.getenv("OPENROUTER_API_KEY"):
            if messagebox.askyesno(
                "API key needed",
                "An OpenRouter API key is required. Open Settings to add one now?",
                parent=self.root,
            ):
                self.open_settings()
            return

        self._set_running(True)
        self._set_status(f"Preparing your study plan for: {cert}")
        self._clear_results()

        def work():
            try:
                text = run_certification_agent(
                    cert, on_status=lambda m: self.queue.put(("status", m))
                )
                self.queue.put(("result", (cert, text)))
            except Exception as exc:  # noqa: BLE001
                self.queue.put(("error", str(exc)))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "certs":
                    self.cert_choices = payload
                    self.cert_combo["values"] = payload
                    self.cert_combo.configure(state="normal")
                    self.run_btn.configure(state=NORMAL)
                    self.progress.stop()
                    self._set_status(
                        f"Loaded {len(payload)} certifications. Pick one and press “Find resources”."
                    )
                    self.cert_combo.focus_set()
                elif kind == "certs_error":
                    self.progress.stop()
                    self._set_status(f"Could not load certifications: {payload}")
                    messagebox.showerror(
                        "Network error",
                        f"Could not fetch the certification list:\n{payload}",
                        parent=self.root,
                    )
                elif kind == "status":
                    self._set_status(payload)
                elif kind == "result":
                    cert, text = payload
                    self._set_running(False)
                    self._set_status(f"Done. Showing results for {cert}.")
                    self._render_markdown(text)
                elif kind == "error":
                    self._set_running(False)
                    self._set_status(f"Error: {payload}")
                    messagebox.showerror("Something went wrong", payload, parent=self.root)
        except Empty:
            pass
        finally:
            self.root.after(100, self._poll_queue)

    def _set_running(self, running: bool) -> None:
        if running:
            self.run_btn.configure(state=DISABLED, text="Working…")
            self.progress.start(80)
            self.bottom_status.configure(text="Working — this can take 30–60 seconds…")
        else:
            self.run_btn.configure(state=NORMAL, text="Find resources")
            self.progress.stop()
            self.bottom_status.configure(text="Ready")

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _clear_results(self) -> None:
        self.results.configure(state=NORMAL)
        self.results.delete("1.0", END)
        self.results.configure(state=DISABLED)

    def _render_markdown(self, text: str) -> None:
        """Render a small subset of Markdown: headings, bullets, bold, links."""
        self.results.configure(state=NORMAL)
        self.results.delete("1.0", END)

        for raw_line in text.splitlines() or [""]:
            line = raw_line.rstrip()
            if line.startswith("### "):
                self.results.insert(END, line[4:] + "\n", "h3")
                continue
            if line.startswith("## "):
                self.results.insert(END, line[3:] + "\n", "h2")
                continue
            if line.startswith("# "):
                self.results.insert(END, line[2:] + "\n", "h1")
                continue
            if line.startswith(("- ", "* ")):
                self.results.insert(END, "   •  ")
                self._insert_with_links_and_bold(line[2:])
                self.results.insert(END, "\n")
                continue
            self._insert_with_links_and_bold(line)
            self.results.insert(END, "\n")

        self.results.configure(state=DISABLED)

    def _insert_with_links_and_bold(self, line: str) -> None:
        pos = 0
        md_link = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
        for m in md_link.finditer(line):
            self._insert_with_bold(line[pos:m.start()])
            self._insert_link(m.group(1), m.group(2))
            pos = m.end()
        remainder = line[pos:]

        pos = 0
        for m in self.URL_RE.finditer(remainder):
            self._insert_with_bold(remainder[pos:m.start()])
            self._insert_link(m.group(0), m.group(0))
            pos = m.end()
        self._insert_with_bold(remainder[pos:])

    def _insert_with_bold(self, text: str) -> None:
        pos = 0
        for m in re.finditer(r"\*\*(.+?)\*\*", text):
            self.results.insert(END, text[pos:m.start()])
            self.results.insert(END, m.group(1), "bold")
            pos = m.end()
        self.results.insert(END, text[pos:])

    def _insert_link(self, label: str, url: str) -> None:
        tag = f"link-{self.results.index(END)}"
        start = self.results.index(END + "-1c")
        self.results.insert(END, label, ("link", tag))
        end = self.results.index(END + "-1c")
        self.results.tag_add(tag, start, end)
        self.results.tag_bind(tag, "<Button-1>", lambda _e, u=url: webbrowser.open(u))
        if label != url:
            self.results.insert(END, f" ({url})", "muted")

    # ---- Dialogs --------------------------------------------------------
    def open_settings(self) -> None:
        SettingsDialog(self.root)

    def show_help(self) -> None:
        messagebox.showinfo(
            "How to use",
            (
                "1. Open Settings (Ctrl+,) and paste your OpenRouter API key.\n"
                "2. Pick a Microsoft certification from the list — start typing "
                "to filter.\n"
                "3. Press “Find resources” (or Enter).\n"
                "4. The assistant will gather official learning paths, "
                "documentation and YouTube videos. Click any link to open it "
                "in your browser."
            ),
            parent=self.root,
        )

    def show_about(self) -> None:
        messagebox.showinfo(
            "About Prépa Certif",
            (
                "Prépa Certif — a friendly desktop helper that builds a "
                "personalised study plan for any Microsoft certification, "
                "powered by AI and official Microsoft Learn resources."
            ),
            parent=self.root,
        )


def main() -> None:
    root = Tk()
    # On Windows, ask for per-monitor DPI awareness so fonts stay crisp.
    if platform.system() == "Windows":
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    PrepaCertifApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
