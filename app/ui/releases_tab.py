import sys
import threading
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk

from ..config import Config
from ..database import Database
from ..installer import InstallError, Installer
from ..github_api import fetch_releases
from ..utils import format_bytes, format_datetime

C_SUCCESS = "#2ea44f"
C_WARNING = "#f0883e"
C_ERROR = "#f85149"
C_DIM = "#8b949e"
C_ACCENT = "#3b8ed0"
C_CARD = "#242424"
C_BORDER = "#333333"
C_SEL = "#2d5f8a"


class ReleasesTab:
    def __init__(self, parent, root, config: Config, db: Database):
        self.parent = parent
        self.root = root
        self.config = config
        self.db = db
        self._releases: list = []
        self._selected_card: Optional[ctk.CTkFrame] = None
        self._selected_release: Optional[dict] = None

        self._build_ui()
        # Load from DB cache; delay a bit longer on 3.14+ so startup refresh does not pile on.
        delay = 750 if sys.version_info >= (3, 14) else 200
        self.root.after(delay, self._load_cached)

    def _build_ui(self):
        top = ctk.CTkFrame(self.parent, fg_color="transparent")
        top.pack(fill="x", padx=6, pady=(4, 4))

        ctk.CTkLabel(
            top, text="Releases",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(side="left")

        self.btn_refresh = ctk.CTkButton(
            top, text="↻ Refresh", width=88, height=28,
            command=self._load_releases,
        )
        self.btn_refresh.pack(side="right")

        # Main pane
        pane = ctk.CTkFrame(self.parent, fg_color="transparent")
        pane.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        pane.columnconfigure(0, weight=2)
        pane.columnconfigure(1, weight=3)
        pane.rowconfigure(0, weight=1)

        # Left: release list
        self._list_frame = ctk.CTkScrollableFrame(pane, fg_color="transparent")
        self._list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        self._lbl_empty = ctk.CTkLabel(
            self._list_frame,
            text="No releases loaded.\nClick Refresh.",
            font=ctk.CTkFont(size=12), text_color=C_DIM,
        )
        self._lbl_empty.pack(pady=24)

        # Right: notes
        right = ctk.CTkFrame(pane, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        self.lbl_notes_title = ctk.CTkLabel(
            right,
            text="Select a release to view notes",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        )
        self.lbl_notes_title.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        self.notes_box = ctk.CTkTextbox(
            right,
            font=ctk.CTkFont(family="Consolas", size=10),
            state="disabled", wrap="word",
            fg_color=C_CARD, border_width=1, border_color=C_BORDER,
        )
        self.notes_box.grid(row=1, column=0, sticky="nsew")

    # ---------------------------------------------------------------- load

    def _load_releases(self):
        threading.Thread(target=self._load_task, daemon=True).start()

    def _load_cached(self):
        """Show whatever is already in the local DB (offline)."""
        rows = self.db.get_releases()
        if rows:
            self._releases = [dict(r) for r in rows]
            self._display(self._releases)

    def _load_task(self):
        self.root.after(0, lambda: self.btn_refresh.configure(state="disabled", text="Loading..."))

        releases: list = []
        err: Optional[Exception] = None
        try:
            releases = list(fetch_releases())
        except Exception as e:
            err = e

        def apply_on_main() -> None:
            try:
                if releases:
                    for r in releases:
                        self.db.upsert_release(r)
                    self._releases = releases
                    self._display(releases)
                elif err is not None:
                    cached = self.db.get_releases()
                    if cached:
                        fallback = [dict(r) for r in cached]
                        self._releases = fallback
                        self._display(fallback)
                    messagebox.showwarning(
                        "Refresh Failed",
                        f"Could not load releases:\n{err}",
                        parent=self.root,
                    )
            finally:
                self.btn_refresh.configure(state="normal", text="↻  Refresh")

        self.root.after(0, apply_on_main)

    # ---------------------------------------------------------------- display

    def _display(self, releases: list):
        for w in self._list_frame.winfo_children():
            w.destroy()

        if not releases:
            ctk.CTkLabel(
                self._list_frame,
                text="No releases found.",
                font=ctk.CTkFont(size=12), text_color=C_DIM,
            ).pack(pady=24)
            return

        installed_ver = self.config.get("installed_version", "")
        first_card = None
        first_release = None

        for release in releases:
            card = self._make_card(release, installed_ver)
            if first_card is None:
                first_card = card
                first_release = release

        if first_card and first_release:
            self._select(first_release, first_card)

    def _make_card(self, release: dict, installed_ver: str) -> ctk.CTkFrame:
        tag = release.get("tag_name", "")
        name = release.get("release_name", tag)
        pub = format_datetime(release.get("published_at", ""))
        is_pre = bool(release.get("is_prerelease", 0))
        is_installed = tag == installed_ver
        win_size = release.get("windows_size") or 0
        lin_size = release.get("linux_size") or 0

        card = ctk.CTkFrame(
            self._list_frame, fg_color=C_CARD,
            corner_radius=6, border_width=1,
            border_color=C_ACCENT if is_installed else C_BORDER,
        )
        card.pack(fill="x", pady=(0, 4))

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="x", padx=8, pady=5)

        # Tag line
        tag_row = ctk.CTkFrame(content, fg_color="transparent")
        tag_row.pack(fill="x")
        ctk.CTkLabel(
            tag_row, text=tag, font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left")

        if is_pre:
            badge = ctk.CTkFrame(tag_row, fg_color="#3a2000", corner_radius=4)
            badge.pack(side="left", padx=(6, 0))
            ctk.CTkLabel(
                badge, text="PRE",
                font=ctk.CTkFont(size=8, weight="bold"),
                text_color=C_WARNING,
            ).pack(padx=4, pady=0)

        if is_installed:
            badge2 = ctk.CTkFrame(tag_row, fg_color="#0a2010", corner_radius=4)
            badge2.pack(side="left", padx=(4, 0))
            ctk.CTkLabel(
                badge2, text="INSTALLED",
                font=ctk.CTkFont(size=8, weight="bold"),
                text_color=C_SUCCESS,
            ).pack(padx=4, pady=0)

        # Release name
        if name and name != tag:
            ctk.CTkLabel(
                content, text=name,
                font=ctk.CTkFont(size=11), text_color=C_DIM, anchor="w",
            ).pack(fill="x", pady=(1, 0))

        ctk.CTkLabel(
            content, text=pub,
            font=ctk.CTkFont(size=10), text_color=C_DIM, anchor="w",
        ).pack(fill="x")

        sizes = []
        if win_size:
            sizes.append(f"Win {format_bytes(win_size)}")
        if lin_size:
            sizes.append(f"Linux {format_bytes(lin_size)}")
        if sizes:
            ctk.CTkLabel(
                content, text="  •  ".join(sizes),
                font=ctk.CTkFont(size=10), text_color=C_DIM, anchor="w",
            ).pack(fill="x")

        if not is_installed:
            btn_row = ctk.CTkFrame(content, fg_color="transparent")
            btn_row.pack(fill="x", pady=(4, 0))
            ctk.CTkButton(
                btn_row, text="Install this version", width=140, height=28,
                command=lambda r=release: self._install_release(r),
            ).pack(side="right")

        # Click-to-select on any widget in the card
        for w in [card, content, tag_row]:
            w.bind("<Button-1>", lambda e, r=release, c=card: self._select(r, c))

        return card

    def _select(self, release: dict, card: ctk.CTkFrame):
        # Reset previous selection border
        if self._selected_card and self._selected_card.winfo_exists():
            prev_tag = (self._selected_release or {}).get("tag_name", "")
            installed = self.config.get("installed_version", "")
            self._selected_card.configure(
                border_color=C_ACCENT if prev_tag == installed else C_BORDER
            )

        self._selected_card = card
        self._selected_release = release
        card.configure(border_color=C_SEL)

        tag = release.get("tag_name", "")
        name = release.get("release_name", tag)
        self.lbl_notes_title.configure(text=name or tag)

        body = release.get("body") or "No release notes available."
        self.notes_box.configure(state="normal")
        self.notes_box.delete("1.0", "end")
        self.notes_box.insert("1.0", body)
        self.notes_box.configure(state="disabled")

    # ---------------------------------------------------------------- install

    def _install_release(self, release: dict):
        tag = release.get("tag_name", "unknown")
        install_dir = self.config.get("install_dir", "")

        if not install_dir:
            install_dir = filedialog.askdirectory(
                title="Choose Installation Directory", parent=self.root
            )
            if not install_dir:
                return
            self.config.set("install_dir", install_dir)

        ok = messagebox.askyesno(
            "Confirm Install",
            f"Install {tag} to:\n{install_dir}\n\n"
            "This will replace any existing installation.",
            parent=self.root,
        )
        if not ok:
            return

        self.btn_refresh.configure(state="disabled", text="Installing...")

        def task():
            try:
                installer = Installer(install_dir=install_dir)
                url = release.get("windows_url", "")
                if not url:
                    raise InstallError("No Windows asset for this release.")
                installer.download_and_install(url, release.get("windows_sha256"), tag)

                def commit_on_main() -> None:
                    try:
                        self.db.add_installation(tag, install_dir)
                        self.config.set("installed_version", tag)
                        messagebox.showinfo("Installed", f"{tag} installed!", parent=self.root)
                        self._display(self._releases)
                    finally:
                        self.btn_refresh.configure(state="normal", text="↻  Refresh")

                self.root.after(0, commit_on_main)
            except Exception as e:
                err = str(e)

                def show_err() -> None:
                    messagebox.showerror("Install Failed", err, parent=self.root)
                    self.btn_refresh.configure(state="normal", text="↻  Refresh")

                self.root.after(0, show_err)

        threading.Thread(target=task, daemon=True).start()
