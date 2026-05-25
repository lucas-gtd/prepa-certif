"""Desktop GUI for Prépa Certif.

Built with Tkinter (standard library) so it works out of the box on
Windows/macOS/Linux without extra runtime dependencies. The interface is
designed to be approachable for non-technical users and accessible:

* Large, resizable fonts and high-contrast-friendly colors.
* Full keyboard navigation (Tab/Shift-Tab, Enter to run, Esc to cancel).
* Searchable certification picker (start typing to filter).
* Screen reader friendly: every control has a visible label, the live status
  area uses a labelled region, and results are exposed as plain selectable
  text rather than custom-drawn widgets.
* Clickable links in the result view (with keyboard alternative: links are
  also listed as plain URLs the user can copy).
* Settings dialog for the API key so users never have to edit a .env file.
"""
from __future__ import annotations

import os
import re
import threading
import webbrowser
from pathlib import Path
from queue import Empty, Queue
from tkinter import (
    BOTH,
    DISABLED,
    END,
    LEFT,
    NORMAL,
    RIGHT,
    SUNKEN,
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

APP_TITLE = "Prépa Certif — Microsoft Certification Study Planner"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ensure_env_file() -> None:
    """Make sure a .env file exists so set_key() can write to it."""
    if not ENV_PATH.exists():
        ENV_PATH.write_text(f"OPENROUTER_API_KEY=\nMODEL_ID={DEFAULT_MODEL_ID}\n", encoding="utf-8")
    load_dotenv(ENV_PATH, override=True)


def save_settings(api_key: str, model_id: str) -> None:
    ensure_env_file()
    set_key(str(ENV_PATH), "OPENROUTER_API_KEY", api_key)
    set_key(str(ENV_PATH), "MODEL_ID", model_id or DEFAULT_MODEL_ID)
    # Make changes visible to the current process immediately.
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
        self.resizable(False, False)
        self.minsize(460, 200)

        ensure_env_file()
        self.api_key_var = StringVar(value=os.getenv("OPENROUTER_API_KEY", ""))
        self.model_var = StringVar(value=os.getenv("MODEL_ID", DEFAULT_MODEL_ID))

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill=BOTH, expand=True)

        intro = ttk.Label(
            frame,
            text=(
                "Enter your OpenRouter API key. You can get a free key at "
                "https://openrouter.ai/keys."
            ),
            wraplength=420,
            justify=LEFT,
        )
        intro.grid(row=0, column=0, columnspan=2, sticky=W, pady=(0, 12))

        ttk.Label(frame, text="OpenRouter API key:").grid(row=1, column=0, sticky=W, pady=4)
        key_entry = ttk.Entry(frame, textvariable=self.api_key_var, width=40, show="•")
        key_entry.grid(row=1, column=1, sticky="ew", pady=4)

        show_var = StringVar(value="0")

        def toggle_show():
            key_entry.config(show="" if show_var.get() == "1" else "•")

        ttk.Checkbutton(
            frame, text="Show key", variable=show_var, onvalue="1", offvalue="0",
            command=toggle_show,
        ).grid(row=2, column=1, sticky=W)

        ttk.Label(frame, text="Model ID:").grid(row=3, column=0, sticky=W, pady=4)
        ttk.Entry(frame, textvariable=self.model_var, width=40).grid(row=3, column=1, sticky="ew", pady=4)

        frame.columnconfigure(1, weight=1)

        btns = ttk.Frame(frame)
        btns.grid(row=4, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(btns, text="Save", command=self._save, default="active").pack(side=RIGHT)

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
        self.root.title(APP_TITLE)
        self.root.geometry("960x720")
        self.root.minsize(720, 520)

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
        # Larger default fonts for readability.
        self.base_font = tkfont.nametofont("TkDefaultFont")
        self.base_font.configure(size=11)
        self.text_font = tkfont.nametofont("TkTextFont")
        self.text_font.configure(size=11)
        self.heading_font = tkfont.Font(family=self.base_font.cget("family"), size=16, weight="bold")
        self.body_font = tkfont.Font(family=self.base_font.cget("family"), size=12)
        self.h2_font = tkfont.Font(family=self.base_font.cget("family"), size=13, weight="bold")

    def _setup_style(self) -> None:
        style = ttk.Style()
        # 'clam' is consistent across platforms and respects custom colors.
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TButton", padding=8)
        style.configure("Accent.TButton", padding=10, font=(self.base_font.cget("family"), 12, "bold"))
        style.configure("TLabel", padding=2)
        style.configure("Header.TLabel", font=self.heading_font)
        style.configure("Status.TLabel", padding=6)

    def _build_menu(self) -> None:
        menubar = Menu(self.root)
        filemenu = Menu(menubar, tearoff=0)
        filemenu.add_command(label="Settings…", accelerator="Ctrl+,", command=self.open_settings)
        filemenu.add_separator()
        filemenu.add_command(label="Quit", accelerator="Alt+F4", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=filemenu)

        helpmenu = Menu(menubar, tearoff=0)
        helpmenu.add_command(label="How to use", command=self.show_help)
        helpmenu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=helpmenu)

        self.root.config(menu=menubar)

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill=BOTH, expand=True)

        header = ttk.Label(
            outer,
            text="Microsoft Certification Study Planner",
            style="Header.TLabel",
        )
        header.pack(anchor=W)

        subtitle = ttk.Label(
            outer,
            text=(
                "Pick a certification and we'll gather official Microsoft Learn "
                "resources and curated YouTube videos for you."
            ),
            wraplength=900,
            justify=LEFT,
        )
        subtitle.pack(anchor=W, pady=(2, 12))

        # Picker row
        picker = ttk.Frame(outer)
        picker.pack(fill=X)

        ttk.Label(picker, text="Certification:").pack(side=LEFT, padx=(0, 8))

        self.cert_var = StringVar()
        self.cert_combo = ttk.Combobox(
            picker, textvariable=self.cert_var, state="disabled", width=60,
            font=self.body_font,
        )
        self.cert_combo.pack(side=LEFT, fill=X, expand=True)
        self.cert_combo.bind("<KeyRelease>", self._on_combo_typing)
        self.cert_combo.bind("<Return>", lambda _e: self.run_search())

        self.run_btn = ttk.Button(
            picker, text="Find resources  (Enter)", style="Accent.TButton",
            command=self.run_search, state=DISABLED,
        )
        self.run_btn.pack(side=LEFT, padx=(8, 0))

        # Tip
        tip = ttk.Label(
            outer,
            text="Tip: start typing to filter the list. Press Enter to search. F5 re-runs.",
            foreground="#555555",
        )
        tip.pack(anchor=W, pady=(6, 12))

        # Status / progress
        status_frame = ttk.LabelFrame(outer, text="Status", padding=8)
        status_frame.pack(fill=X)
        self.status_var = StringVar(value="Loading certifications…")
        self.status_label = ttk.Label(
            status_frame, textvariable=self.status_var, style="Status.TLabel",
            wraplength=900, justify=LEFT,
        )
        self.status_label.pack(side=LEFT, fill=X, expand=True)
        self.progress = ttk.Progressbar(status_frame, mode="indeterminate", length=140)
        self.progress.pack(side=RIGHT, padx=(8, 0))
        self.progress.start(80)

        # Results
        results_frame = ttk.LabelFrame(outer, text="Results", padding=8)
        results_frame.pack(fill=BOTH, expand=True, pady=(12, 0))

        self.results = ScrolledText(
            results_frame,
            wrap="word",
            font=self.body_font,
            bg="#ffffff",
            fg="#111111",
            insertbackground="#111111",
            padx=10,
            pady=10,
            relief=SUNKEN,
            borderwidth=1,
            height=18,
        )
        self.results.pack(fill=BOTH, expand=True)
        self.results.tag_configure("h1", font=self.heading_font, spacing3=8, spacing1=8)
        self.results.tag_configure("h2", font=self.h2_font, spacing3=6, spacing1=10, foreground="#0a5fb0")
        self.results.tag_configure("bold", font=(self.body_font.cget("family"), 12, "bold"))
        self.results.tag_configure("link", foreground="#0645AD", underline=True)
        self.results.tag_bind("link", "<Enter>", lambda _e: self.results.config(cursor="hand2"))
        self.results.tag_bind("link", "<Leave>", lambda _e: self.results.config(cursor=""))
        self.results.configure(state=DISABLED)

        self._set_placeholder()

        # Bottom status bar
        self.bottom_status = ttk.Label(
            self.root, text="Ready", anchor=W, relief=SUNKEN, padding=(8, 4),
        )
        self.bottom_status.pack(side=TOP, fill=X)

    # ---- Behavior --------------------------------------------------------
    def _set_placeholder(self) -> None:
        self.results.configure(state=NORMAL)
        self.results.delete("1.0", END)
        self.results.insert(
            END,
            "Your study plan will appear here once you pick a certification "
            "and press \"Find resources\".\n",
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
        # Filter the dropdown list as the user types.
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
                        f"Loaded {len(payload)} certifications. Pick one and press \"Find resources\"."
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
            self.run_btn.configure(state=NORMAL, text="Find resources  (Enter)")
            self.progress.stop()
            self.bottom_status.configure(text="Ready")

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _clear_results(self) -> None:
        self.results.configure(state=NORMAL)
        self.results.delete("1.0", END)
        self.results.configure(state=DISABLED)

    def _render_markdown(self, text: str) -> None:
        """Render a small subset of Markdown into the Text widget.

        We deliberately keep this simple and predictable rather than pulling in
        a heavy HTML renderer: headings, bullets, bold, and clickable links.
        """
        self.results.configure(state=NORMAL)
        self.results.delete("1.0", END)

        for raw_line in text.splitlines() or [""]:
            line = raw_line.rstrip()
            if line.startswith("## "):
                self.results.insert(END, line[3:] + "\n", "h2")
                continue
            if line.startswith("# "):
                self.results.insert(END, line[2:] + "\n", "h1")
                continue
            if line.startswith(("- ", "* ")):
                self.results.insert(END, "  •  ")
                self._insert_with_links_and_bold(line[2:])
                self.results.insert(END, "\n")
                continue
            self._insert_with_links_and_bold(line)
            self.results.insert(END, "\n")

        self.results.configure(state=DISABLED)

    def _insert_with_links_and_bold(self, line: str) -> None:
        # Handle markdown [text](url) first, then bare URLs, then **bold**.
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
        # Keyboard alternative: append the URL in parentheses for screen readers
        # and copy/paste users when the label is not itself a URL.
        if label != url:
            self.results.insert(END, f" ({url})")

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
                "3. Press \"Find resources\" (or Enter).\n"
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
    PrepaCertifApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
