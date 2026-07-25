import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable, Optional

import customtkinter as ctk

from ..config import Config
from ..database import Database
from ..installer import Installer

C_SUCCESS = "#2ea44f"
C_WARNING = "#f0883e"
C_ERROR = "#f85149"
C_DIM = "#8b949e"
C_CARD = "#242424"
C_BORDER = "#333333"


class SettingsTab:
    def __init__(
        self,
        parent,
        root,
        config: Config,
        db: Database,
        on_state_changed: Optional[Callable[[], None]] = None,
    ):
        self.parent = parent
        self.root = root
        self.config = config
        self.db = db
        self._on_state_changed = on_state_changed

        self._build_ui()
        self._load_values()

    # ----------------------------------------------------------------- build

    def _section(self, parent, title: str) -> ctk.CTkFrame:
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(
            wrap, text=title.upper(),
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=C_DIM,
        ).pack(anchor="w", pady=(0, 2))
        card = ctk.CTkFrame(
            wrap, fg_color=C_CARD,
            corner_radius=6, border_width=1, border_color=C_BORDER,
        )
        card.pack(fill="x")
        return card

    def _row(self, parent, label: str, width: int = 148) -> ctk.CTkFrame:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(
            row, text=label, font=ctk.CTkFont(size=12), width=width, anchor="w"
        ).pack(side="left")
        right = ctk.CTkFrame(row, fg_color="transparent")
        right.pack(side="left", fill="x", expand=True)
        return right

    def _build_ui(self):
        scroll = ctk.CTkScrollableFrame(self.parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=6, pady=6)

        # Installation
        inst = self._section(scroll, "Installation")

        r1 = self._row(inst, "Install Directory")
        self.entry_dir = ctk.CTkEntry(r1, width=260, height=28, placeholder_text="Not set")
        self.entry_dir.pack(side="left", padx=(0, 8))
        ctk.CTkButton(r1, text="Browse…", width=72, height=28, command=self._browse_dir).pack(side="left", padx=(0, 4))
        ctk.CTkButton(r1, text="Open", width=72, height=28, command=self._open_folder).pack(side="left")

        r2 = self._row(inst, "Installed Version")
        self.lbl_ver = ctk.CTkLabel(r2, text="—", text_color=C_DIM, anchor="w")
        self.lbl_ver.pack(side="left")

        # ROM
        rom_card = self._section(scroll, "ROM Configuration")

        r3 = self._row(rom_card, "ROM Path (baserom.gba)")
        self.entry_rom = ctk.CTkEntry(r3, width=260, height=28, placeholder_text="Not set")
        self.entry_rom.pack(side="left", padx=(0, 6))
        ctk.CTkButton(r3, text="Browse…", width=72, height=28, command=self._browse_rom).pack(side="left", padx=(0, 4))
        ctk.CTkButton(r3, text="Validate", width=72, height=28, command=self._validate_rom).pack(side="left")

        r4 = self._row(rom_card, "ROM Status")
        self.lbl_rom = ctk.CTkLabel(r4, text="—", text_color=C_DIM, anchor="w")
        self.lbl_rom.pack(side="left")

        ctk.CTkLabel(
            rom_card,
            text="  USA (BZME)  ·  SHA-1: b4bd50e4131b027c334547b4524e2dbbd4227130",
            font=ctk.CTkFont(size=9), text_color=C_DIM,
        ).pack(anchor="w", padx=10, pady=(0, 6))

        # Updates
        upd = self._section(scroll, "Updates")

        r5 = self._row(upd, "Auto-check on startup")
        self.sw_auto = ctk.CTkSwitch(r5, text="", command=self._save_auto)
        self.sw_auto.pack(side="left")

        r6 = self._row(upd, "Check interval")
        self.menu_interval = ctk.CTkOptionMenu(
            r6,
            values=["1 hour", "6 hours", "12 hours", "24 hours", "7 days"],
            width=160,
            command=self._save_interval,
        )
        self.menu_interval.pack(side="left")

        # Controls & About
        about = self._section(scroll, "Controls & About")

        controls = (
            "Tab / Right trigger   Hold to fast-forward\n"
            "F11 / Alt+Enter       Toggle fullscreen\n"
            "F12                   Cycle upscaler (Nearest → xBRZ Linear → xBRZ Nearest → Linear)"
        )
        ctk.CTkLabel(
            about, text=controls,
            font=ctk.CTkFont(family="Consolas", size=10),
            justify="left", anchor="w",
        ).pack(anchor="w", padx=10, pady=8)

        btn_row = ctk.CTkFrame(about, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkButton(
            btn_row, text="View on GitHub", width=140,
            command=lambda: webbrowser.open("https://github.com/999sian/tmc"),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row, text="View Releases", width=140,
            command=lambda: webbrowser.open("https://github.com/999sian/tmc/releases"),
        ).pack(side="left")

    # ----------------------------------------------------------------- load

    def _load_values(self):
        d = self.config.get("install_dir", "")
        if d:
            self.entry_dir.insert(0, d)

        rom = self.config.get("rom_path", "")
        if rom:
            self.entry_rom.insert(0, rom)

        installed = self.config.get("installed_version", "")
        self.lbl_ver.configure(
            text=installed or "Not installed",
            text_color="white" if installed else C_DIM,
        )

        if self.config.get("auto_check_updates"):
            self.sw_auto.select()

        hours_map = {1: "1 hour", 6: "6 hours", 12: "12 hours", 24: "24 hours", 168: "7 days"}
        hours = self.config.get("check_interval_hours", 24)
        self.menu_interval.set(hours_map.get(hours, "24 hours"))

        if rom and Path(rom).exists():
            valid, msg = Installer.validate_rom(rom)
            self._persist_rom_validation(rom, valid, msg, update_entry=False)
        else:
            self._refresh_rom_status()

    # ----------------------------------------------------------------- handlers

    def _browse_dir(self):
        d = filedialog.askdirectory(title="Select Installation Directory", parent=self.root)
        if d:
            self.entry_dir.delete(0, "end")
            self.entry_dir.insert(0, d)
            self.config.set("install_dir", d)

    def _open_folder(self):
        d = self.entry_dir.get() or self.config.get("install_dir", "")
        if not (d and Path(d).exists()):
            messagebox.showinfo(
                "Folder Not Found",
                "Install directory not configured or does not exist.",
                parent=self.root,
            )
            return
        try:
            self._open_path(d)
        except Exception as e:
            messagebox.showerror(
                "Open Folder", f"Could not open folder:\n{e}", parent=self.root
            )

    @staticmethod
    def _open_path(path: str):
        """Open a folder in the OS file manager, cross-platform.
        os.startfile exists only on Windows."""
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def _browse_rom(self):
        f = filedialog.askopenfilename(
            title="Select baserom.gba",
            filetypes=[("GBA ROM", "*.gba"), ("All files", "*.*")],
            parent=self.root,
        )
        if f:
            self.entry_rom.delete(0, "end")
            self.entry_rom.insert(0, f)
            self.config.set("rom_path", f)
            valid, msg = Installer.validate_rom(f)
            self._persist_rom_validation(f, valid, msg, update_entry=False)

    def _validate_rom(self):
        path = (self.entry_rom.get() or "").strip() or self.config.get("rom_path", "")
        if not path:
            messagebox.showinfo("No ROM", "Select a ROM file first.", parent=self.root)
            return
        if not Path(path).exists():
            messagebox.showwarning("ROM Missing", f"File not found:\n{path}", parent=self.root)
            self._refresh_rom_status()
            return
        valid, msg = Installer.validate_rom(path)
        self._persist_rom_validation(path, valid, msg, update_entry=False)
        if valid:
            messagebox.showinfo("ROM Valid", msg, parent=self.root)
        else:
            messagebox.showwarning("ROM Invalid", msg, parent=self.root)

    def _persist_rom_validation(
        self, path: str, valid: bool, msg: str, *, update_entry: bool
    ) -> None:
        """Keep DB, config, install folder, and Home tab in sync with SHA-1 result."""
        self.config.set("rom_path", path)
        if update_entry:
            self.entry_rom.delete(0, "end")
            self.entry_rom.insert(0, path)

        inst = self.db.get_current_installation()
        if inst:
            self.db.update_installation(inst["id"], rom_sha1_verified=1 if valid else 0)
        else:
            self.config.set("rom_sha1_verified", 1 if valid else 0)

        install_dir = self.config.get("install_dir", "")
        if valid and install_dir and Path(install_dir).exists():
            try:
                Installer.setup_rom(path, install_dir)
            except Exception:
                pass

        self.lbl_rom.configure(
            text=("✓ " if valid else "✗ ") + msg,
            text_color=C_SUCCESS if valid else C_ERROR,
        )
        if self._on_state_changed:
            self._on_state_changed()

    def _refresh_rom_status(self):
        path = self.config.get("rom_path", "")
        if not path:
            self.lbl_rom.configure(text="— Not set", text_color=C_DIM)
            return
        if not Path(path).exists():
            self.lbl_rom.configure(text="✗ File not found", text_color=C_ERROR)
            return
        inst = self.db.get_current_installation()
        verified = bool(inst["rom_sha1_verified"]) if inst else bool(
            self.config.get("rom_sha1_verified", 0)
        )
        if verified:
            self.lbl_rom.configure(text="✓ Validated (SHA-1 OK)", text_color=C_SUCCESS)
        else:
            self.lbl_rom.configure(
                text="Present (click Validate to check SHA-1)", text_color=C_WARNING
            )

    def _save_auto(self):
        self.config.set("auto_check_updates", bool(self.sw_auto.get()))

    def _save_interval(self, value: str):
        mapping = {"1 hour": 1, "6 hours": 6, "12 hours": 12, "24 hours": 24, "7 days": 168}
        self.config.set("check_interval_hours", mapping.get(value, 24))
