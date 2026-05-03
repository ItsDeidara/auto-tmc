import shutil
import threading
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk

from ..config import Config
from ..database import Database
from ..installer import InstallError, Installer
from ..launcher import GameLauncher
from ..github_api import fetch_releases
from ..utils import format_bytes, is_newer

C_SUCCESS = "#2ea44f"
C_WARNING = "#f0883e"
C_ERROR = "#f85149"
C_DIM = "#8b949e"
C_ACCENT = "#3b8ed0"
C_CARD = "#242424"
C_BORDER = "#333333"


class HomeTab:
    def __init__(self, parent, root, config: Config, db: Database):
        self.parent = parent
        self.root = root
        self.config = config
        self.db = db
        self._action_buttons: list = []
        self._install_id: Optional[int] = None
        self._latest_release: Optional[dict] = None

        self._build_ui()
        self.refresh_state()

    # ------------------------------------------------------------------ build

    def _build_ui(self):
        # Bottom: action buttons + optional progress only (log lives in the stretchy middle).
        self._bottom_stack = ctk.CTkFrame(self.parent, fg_color="transparent")
        self._build_actions()
        self._build_progress()
        self._bottom_stack.pack(side="bottom", fill="x", padx=4, pady=(0, 2))

        # Main column: header + cards (natural height) + log (row weight 1 fills dead space).
        self._main = ctk.CTkFrame(self.parent, fg_color="transparent")
        self._main.pack(fill="both", expand=True, padx=4, pady=(2, 2))
        self._main.grid_columnconfigure(0, weight=1)
        self._main.grid_rowconfigure(2, weight=1)

        self._build_header()

        self._grid = ctk.CTkFrame(self._main, fg_color="transparent")
        self._grid.grid(row=1, column=0, sticky="new", pady=(0, 0))
        self._grid.columnconfigure(0, weight=1)
        self._grid.columnconfigure(1, weight=1)

        left = ctk.CTkFrame(self._grid, fg_color="transparent")
        # sticky="nw" — do not stretch the short column to match the tall one (dead zone).
        left.grid(row=0, column=0, sticky="nw", padx=(0, 4))
        self._build_install_card(left)

        right = ctk.CTkFrame(self._grid, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nw", padx=(4, 0))
        self._build_update_card(right)

        # ROM & Assets spans both columns so SHA-1 can use full window width.
        rom_wide = ctk.CTkFrame(self._grid, fg_color="transparent")
        rom_wide.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        rom_wide.columnconfigure(0, weight=1)
        self._build_rom_card(rom_wide)

        self._build_log_area()

    def _build_header(self):
        hdr = ctk.CTkFrame(self._main, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 2))

        ctk.CTkLabel(
            hdr, text="TMC PC Launcher",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            hdr,
            text="Minish Cap — PC port (experimental)",
            font=ctk.CTkFont(size=9),
            text_color=C_DIM,
        ).pack(anchor="w")

    def _card(self, parent, title: str) -> ctk.CTkFrame:
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="x", pady=(0, 2))
        ctk.CTkLabel(
            wrap, text=title.upper(),
            font=ctk.CTkFont(size=8, weight="bold"),
            text_color=C_DIM,
        ).pack(anchor="w", pady=(0, 0))
        card = ctk.CTkFrame(
            wrap, fg_color=C_CARD,
            corner_radius=6, border_width=1, border_color=C_BORDER,
        )
        card.pack(fill="x")
        return card

    def _stat_row(
        self,
        parent,
        label: str,
        value: str = "—",
        color: str = C_DIM,
        *,
        value_wrap: int = 200,
    ) -> ctk.CTkLabel:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=5, pady=0)
        ctk.CTkLabel(
            row, text=label,
            font=ctk.CTkFont(size=9), text_color=C_DIM,
            width=72, anchor="w",
        ).pack(side="left")
        val = ctk.CTkLabel(
            row,
            text=value,
            font=ctk.CTkFont(size=9),
            text_color=color,
            anchor="w",
            justify="left",
            wraplength=value_wrap,
        )
        val.pack(side="left", fill="x", expand=True)
        return val

    def _build_install_card(self, parent):
        card = self._card(parent, "Installation")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", pady=1)
        self.lbl_version = self._stat_row(inner, "Version")
        self.lbl_path = self._stat_row(inner, "Path")
        self.lbl_exe = self._stat_row(inner, "Executable")

    def _build_rom_card(self, parent):
        ROM_SHA1 = "b4bd50e4131b027c334547b4524e2dbbd4227130"

        card = self._card(parent, "ROM & Assets")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", pady=1)
        self.lbl_rom = self._stat_row(inner, "ROM", value_wrap=900)
        self.lbl_assets = self._stat_row(inner, "Assets", value_wrap=900)

        ctk.CTkFrame(inner, fg_color=C_BORDER, height=1).pack(fill="x", padx=5, pady=(0, 2))

        ctk.CTkLabel(
            inner,
            text="Required SHA-1 (USA retail, BZME)",
            font=ctk.CTkFont(size=8),
            text_color=C_DIM,
        ).pack(anchor="w", padx=5, pady=(0, 2))

        hash_row = ctk.CTkFrame(inner, fg_color="transparent")
        hash_row.pack(fill="x", padx=5, pady=(0, 1))
        hash_row.columnconfigure(0, weight=1)
        self._lbl_sha_full = ctk.CTkLabel(
            hash_row,
            text=ROM_SHA1,
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color="#cccccc",
            anchor="w",
        )
        self._lbl_sha_full.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._btn_copy_sha1 = ctk.CTkButton(
            hash_row,
            text="Copy",
            width=52,
            height=24,
            font=ctk.CTkFont(size=9),
            fg_color="#3a3a3a",
            hover_color="#4a4a4a",
            command=lambda: self._copy_sha1(ROM_SHA1),
        )
        self._btn_copy_sha1.grid(row=0, column=1, sticky="e")

    def _build_update_card(self, parent):
        card = self._card(parent, "Updates")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", pady=1)
        self.lbl_cur_ver = self._stat_row(inner, "Installed")
        self.lbl_latest_ver = self._stat_row(inner, "Latest")
        self.lbl_upd_status = self._stat_row(inner, "Status")

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(fill="x", padx=5, pady=(1, 1))
        self.btn_check = ctk.CTkButton(
            btn_row, text="Check for Updates", width=132, height=24,
            command=lambda: self._run_task(self._check_updates_task),
        )
        self.btn_check.pack(side="left")
        self._action_buttons.append(self.btn_check)

    def _build_log_area(self) -> None:
        self._log_container = ctk.CTkFrame(self._main, fg_color="transparent")
        self._log_container.grid(row=2, column=0, sticky="nsew", pady=(4, 0))
        self._log_container.grid_columnconfigure(0, weight=1)
        self._log_container.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            self._log_container,
            text="Operation log",
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=C_DIM,
        ).grid(row=0, column=0, sticky="w", pady=(0, 2))

        self._log_box = ctk.CTkTextbox(
            self._log_container,
            height=80,
            font=ctk.CTkFont(family="Consolas", size=10),
            state="disabled",
            fg_color=C_CARD,
            border_width=1,
            border_color=C_BORDER,
        )
        self._log_box.grid(row=1, column=0, sticky="nsew")

        def _sync_log_height(_event: Optional[object] = None) -> None:
            try:
                self._log_container.update_idletasks()
                total = self._log_container.winfo_height()
                # Leave room for title row + padding; grow textbox to fill remainder.
                usable = max(56, total - 28)
                self._log_box.configure(height=usable)
            except Exception:
                pass

        self._log_container.bind("<Configure>", lambda e: _sync_log_height(e))
        self.root.after_idle(_sync_log_height)

    def _build_actions(self):
        self._actions_row = ctk.CTkFrame(self._bottom_stack, fg_color="transparent")
        row = self._actions_row
        row.pack(fill="x", pady=(0, 0))

        self.btn_install = ctk.CTkButton(
            row, text="Install / Update", width=122, height=26,
            fg_color=C_ACCENT, hover_color="#2d6fa8",
            command=self._on_install_click,
        )
        self.btn_install.pack(side="left", padx=(0, 4))

        self.btn_rom = ctk.CTkButton(
            row, text="Setup ROM", width=96, height=26,
            fg_color="#3a3a3a", hover_color="#4a4a4a",
            command=self._setup_rom,
        )
        self.btn_rom.pack(side="left", padx=(0, 4))

        self.btn_assets = ctk.CTkButton(
            row, text="Extract Assets", width=112, height=26,
            fg_color="#3a3a3a", hover_color="#4a4a4a",
            command=self._extract_assets,
        )
        self.btn_assets.pack(side="left", padx=(0, 4))

        self.btn_launch = ctk.CTkButton(
            row, text="Launch ▶", width=102, height=26,
            fg_color="#3a3a3a", hover_color="#4a4a4a",
            command=self._launch_game,
        )
        self.btn_launch.pack(side="left")

        for b in [self.btn_install, self.btn_rom, self.btn_assets, self.btn_launch]:
            self._action_buttons.append(b)

    def _build_progress(self):
        self._progress_frame = ctk.CTkFrame(
            self._bottom_stack, fg_color=C_CARD,
            corner_radius=6, border_width=1, border_color=C_BORDER,
        )
        inner = ctk.CTkFrame(self._progress_frame, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=6)

        self._prog_bar = ctk.CTkProgressBar(inner, mode="determinate", height=12)
        self._prog_bar.set(0)
        self._prog_bar.pack(fill="x", pady=(0, 4))

        self._prog_lbl = ctk.CTkLabel(
            inner, text="Starting...",
            font=ctk.CTkFont(size=11), text_color=C_DIM,
        )
        self._prog_lbl.pack(anchor="w")

    def _copy_sha1(self, sha1: str):
        self.root.clipboard_clear()
        self.root.clipboard_append(sha1)
        self._btn_copy_sha1.configure(text="Copied!", fg_color=C_SUCCESS, hover_color="#25803a")
        self.root.after(
            2000,
            lambda: self._btn_copy_sha1.configure(
                text="Copy", fg_color="#3a3a3a", hover_color="#4a4a4a"
            ),
        )

    # ----------------------------------------------------------------- state

    def sync_latest_from_db(self) -> None:
        row = self.db.get_latest_release()
        self._latest_release = dict(row) if row else None

    def refresh_state(self):
        inst = self.db.get_current_installation()
        install_dir = self.config.get("install_dir", "")

        if inst:
            self._install_id = inst["id"]
            tag = inst["tag_name"]
            path = inst["install_path"]
            self.lbl_version.configure(text=tag, text_color="white")
            disp = path if len(path) <= 48 else "..." + path[-45:]
            self.lbl_path.configure(text=disp, text_color=C_DIM)
        else:
            self._install_id = None
            self.lbl_version.configure(text="Not installed", text_color=C_DIM)
            disp = install_dir[:48] if install_dir else "Not configured"
            self.lbl_path.configure(text=disp, text_color=C_DIM)

        if install_dir:
            exe = Path(install_dir) / "tmc_pc.exe"
            if exe.exists():
                self.lbl_exe.configure(text="✓ Found", text_color=C_SUCCESS)
            else:
                self.lbl_exe.configure(text="✗ Not found — install first", text_color=C_ERROR)
        else:
            self.lbl_exe.configure(text="— Install dir not set", text_color=C_DIM)

        rom_path = self.config.get("rom_path", "")
        if rom_path and Path(rom_path).exists():
            rom_ok = bool(inst["rom_sha1_verified"]) if inst else bool(
                self.config.get("rom_sha1_verified", 0)
            )
            if rom_ok:
                self.lbl_rom.configure(text="✓ Validated (SHA-1 OK)", text_color=C_SUCCESS)
            else:
                self.lbl_rom.configure(text="⚠ Present, not validated", text_color=C_WARNING)
        else:
            self.lbl_rom.configure(text="✗ Not configured", text_color=C_ERROR)

        if install_dir and Installer.check_assets(install_dir):
            self.lbl_assets.configure(text="✓ Extracted", text_color=C_SUCCESS)
        else:
            self.lbl_assets.configure(text="✗ Not found — extract assets", text_color=C_ERROR)

        installed_ver = (inst["tag_name"] if inst else "") or self.config.get("installed_version", "")
        self.lbl_cur_ver.configure(
            text=installed_ver or "Not installed",
            text_color="white" if installed_ver else C_DIM,
        )

        if self._latest_release:
            latest_tag = self._latest_release.get("tag_name", "")
            self.lbl_latest_ver.configure(text=latest_tag, text_color="white")
            if not installed_ver:
                self.lbl_upd_status.configure(text="Not installed", text_color=C_WARNING)
            elif is_newer(latest_tag, installed_ver):
                self.lbl_upd_status.configure(text="⚠ Update available!", text_color=C_WARNING)
            else:
                self.lbl_upd_status.configure(text="✓ Up to date", text_color=C_SUCCESS)
        else:
            self.lbl_latest_ver.configure(text="Not checked yet", text_color=C_DIM)
            self.lbl_upd_status.configure(text="—", text_color=C_DIM)

        # Colour launch button green when ready
        if install_dir:
            launcher = GameLauncher(install_dir)
            ready, _ = launcher.is_ready()
            self.btn_launch.configure(
                fg_color=C_SUCCESS if ready else "#3a3a3a",
                hover_color="#25803a" if ready else "#4a4a4a",
            )

    # --------------------------------------------------------------- threads

    def _run_task(self, func, *args):
        self._set_busy(True)
        self._show_progress()

        def runner():
            try:
                func(*args)
            except InstallError as e:
                self.root.after(0, lambda msg=str(e): self._show_error(msg))
            except Exception as e:
                self.root.after(0, lambda msg=str(e): self._show_error(f"Unexpected error: {msg}"))
            finally:
                self.root.after(0, self._on_task_done)

        threading.Thread(target=runner, daemon=True).start()

    def _set_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        for btn in self._action_buttons:
            try:
                btn.configure(state=state)
            except Exception:
                pass

    def _show_progress(self):
        self._prog_bar.set(0)
        self._prog_lbl.configure(text="Starting...")
        self._progress_frame.pack(fill="x", pady=(0, 4), before=self._actions_row)

    def _hide_progress(self):
        self._progress_frame.pack_forget()

    def _on_task_done(self):
        self._set_busy(False)
        self._hide_progress()
        self.refresh_state()

    def _show_error(self, msg: str):
        self._append_log(f"ERROR: {msg}")
        messagebox.showerror("Error", msg, parent=self.root)

    def _on_progress(self, pct: int, msg: str):
        self.root.after(0, lambda p=pct, m=msg: self._update_prog(p, m))

    def _update_prog(self, pct: int, msg: str):
        self._prog_bar.set(pct / 100)
        self._prog_lbl.configure(text=f"{msg} ({pct}%)")

    def _on_status(self, msg: str):
        self.root.after(0, lambda m=msg: self._append_log(m))

    def _append_log(self, msg: str):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", f"{msg}\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    # --------------------------------------------------------------- actions

    def _check_updates_task(self):
        self._on_status("Checking for updates...")
        self._on_progress(10, "Fetching releases")
        releases: list = []
        try:
            releases = list(fetch_releases())
        except Exception as e:
            self.root.after(0, lambda msg=str(e): self._show_error(f"Could not load releases:\n{msg}"))
            return

        snap = list(releases)

        def finish_on_main() -> None:
            try:
                for r in snap:
                    self.db.upsert_release(r)
                self._on_progress(90, "Done")
                if snap:
                    self._latest_release = snap[0]
                db_latest = self.db.get_latest_release()
                if db_latest and not self._latest_release:
                    self._latest_release = dict(db_latest)
                self.refresh_state()
                tag = snap[0]["tag_name"] if snap else "none"
                self._on_status(f"Checked: {len(snap)} release(s) found. Latest: {tag}")
            except Exception as e:
                self._show_error(str(e))

        self.root.after(0, finish_on_main)

    def _on_install_click(self):
        install_dir = self.config.get("install_dir", "")
        if not install_dir:
            install_dir = filedialog.askdirectory(
                title="Choose Installation Directory", parent=self.root
            )
            if not install_dir:
                return
            self.config.set("install_dir", install_dir)

        if not self._latest_release:
            try:
                releases = fetch_releases()
                for r in releases:
                    self.db.upsert_release(r)
                if releases:
                    self._latest_release = releases[0]
                else:
                    messagebox.showwarning(
                        "No Releases", "No releases found.", parent=self.root
                    )
                    return
            except Exception as e:
                messagebox.showerror(
                    "Releases", f"Could not load releases:\n{e}", parent=self.root
                )
                return

        self._run_task(self._install_task, self._latest_release, install_dir)

    def _install_task(self, release: dict, install_dir: str):
        url = release.get("windows_url")
        sha256 = release.get("windows_sha256")
        tag = release.get("tag_name", "unknown")
        size = release.get("windows_size") or 0

        if not url:
            raise InstallError("No Windows asset found for this release.")

        self._on_status(f"Installing {tag}  ({format_bytes(size)})...")

        installer = Installer(
            install_dir=install_dir,
            on_progress=self._on_progress,
            on_status=self._on_status,
        )
        installer.download_and_install(url, sha256, tag)

        inst_id = self.db.add_installation(tag, install_dir)
        self._install_id = inst_id
        self.config.set("installed_version", tag)
        self.config.set("installed_release_id", release.get("id"))

        rom_path = self.config.get("rom_path", "")
        if rom_path and Path(rom_path).exists():
            dest_rom = Path(install_dir) / "baserom.gba"
            if not dest_rom.exists():
                Installer.setup_rom(rom_path, install_dir)
                self.db.update_installation(inst_id, rom_sha1_verified=1)

            # Auto-run extract script if bundled and assets not yet present
            has_script, script_name = Installer.has_extract_script(install_dir)
            if has_script and not Installer.check_assets(install_dir):
                self._on_status(f"Found {script_name} — running asset extraction...")
                sub = Installer(
                    install_dir=install_dir,
                    on_progress=self._on_progress,
                    on_status=self._on_status,
                )
                try:
                    sub.run_extract_script(rom_path)
                    if Installer.check_assets(install_dir):
                        self.db.update_installation(inst_id, assets_extracted=1)
                        self._on_status("Assets extracted.")
                    else:
                        self._on_status("Warning: assets/ not found after extract — retry via Extract Assets button.")
                except InstallError as e:
                    self._on_status(f"Auto-extract failed (retry manually): {e}")

        self._on_status(f"Installed to: {install_dir}")

    def _setup_rom(self):
        rom_path = filedialog.askopenfilename(
            title="Select baserom.gba",
            filetypes=[("GBA ROM", "*.gba"), ("All files", "*.*")],
            parent=self.root,
        )
        if not rom_path:
            return

        valid, msg = Installer.validate_rom(rom_path)
        if valid:
            messagebox.showinfo("ROM Validated", msg, parent=self.root)
        else:
            proceed = messagebox.askyesno(
                "ROM Validation Failed",
                f"{msg}\n\nUse this ROM anyway? (Game may not work correctly)",
                parent=self.root,
            )
            if not proceed:
                return

        self.config.set("rom_path", rom_path)
        install_dir = self.config.get("install_dir", "")
        if install_dir and Path(install_dir).exists():
            Installer.setup_rom(rom_path, install_dir)
            if self._install_id:
                self.db.update_installation(
                    self._install_id, rom_sha1_verified=1 if valid else 0
                )
            else:
                self.config.set("rom_sha1_verified", 1 if valid else 0)
        else:
            self.config.set("rom_sha1_verified", 1 if valid else 0)
        self._append_log(f"ROM configured: {rom_path}")
        self.refresh_state()

    def _extract_assets(self):
        install_dir = self.config.get("install_dir", "")
        if not install_dir:
            messagebox.showinfo(
                "Install First", "Install the game before extracting assets.", parent=self.root
            )
            return

        # Priority 1: bundled extract script (extract.bat / extract.sh in install dir)
        has_script, script_name = Installer.has_extract_script(install_dir)
        if has_script:
            rom_path = self.config.get("rom_path", "")
            if not rom_path or not Path(rom_path).exists():
                messagebox.showwarning(
                    "ROM Required",
                    "Set up your ROM first (Setup ROM button), then extract assets.",
                    parent=self.root,
                )
                return
            ok = messagebox.askyesno(
                "Extract Assets",
                f"{script_name} found in the install folder.\n\n"
                "This uses the bundled tools to extract game assets from your ROM.\n"
                "Takes 1-2 minutes. Continue?",
                parent=self.root,
            )
            if ok:
                self._run_task(self._script_extract_task, rom_path, install_dir)
            return

        # Priority 2: WSL fallback — download Linux tar and run its extract.sh
        latest = self._latest_release
        if not latest:
            db_row = self.db.get_latest_release()
            latest = dict(db_row) if db_row else None

        linux_url = latest.get("linux_url") if latest else None
        has_wsl = Installer.detect_wsl()

        if has_wsl and linux_url:
            choice = messagebox.askyesnocancel(
                "Extract Assets — WSL",
                "No bundled extract script found in install folder.\n"
                "WSL detected — can download Linux tools and auto-extract.\n\n"
                "Yes    — Auto-extract via WSL\n"
                "No     — Browse to an existing assets/ folder\n"
                "Cancel — Skip",
                parent=self.root,
            )
            if choice is True:
                rom_path = self.config.get("rom_path", "")
                if not rom_path or not Path(rom_path).exists():
                    messagebox.showwarning("ROM Required", "Set up your ROM first.", parent=self.root)
                    return
                self._run_task(self._wsl_extract_task, linux_url, rom_path, install_dir)
            elif choice is False:
                self._browse_assets(install_dir)
            return

        # Priority 3: manual browse or instructions
        choice = messagebox.askyesno(
            "Extract Assets — Manual",
            "No extract script found and WSL is not available.\n\n"
            "Browse to an existing 'assets' folder?\n"
            "(No = show manual extraction instructions)",
            parent=self.root,
        )
        if choice:
            self._browse_assets(install_dir)
        else:
            messagebox.showinfo(
                "Manual Asset Extraction",
                "Option A — Use a release with extract.bat bundled.\n\n"
                "Option B — Enable WSL, then retry:\n"
                "  wsl --install   (run in PowerShell as admin, then reboot)\n\n"
                "Option C — Build manually:\n"
                "  1. git clone https://github.com/999sian/tmc\n"
                "  2. Install xmake (https://xmake.io)\n"
                "  3. Place baserom.gba in the repo folder\n"
                "  4. Run: xmake extract_assets\n"
                "  5. Copy build/pc/assets/ → your install folder\n\n"
                "Then use 'Browse existing assets folder' above.",
                parent=self.root,
            )

    def _browse_assets(self, install_dir: str):
        src = filedialog.askdirectory(
            title="Select assets source folder", parent=self.root
        )
        if not src:
            return

        src_path = Path(src)
        dest = Path(install_dir) / "assets"

        if src_path.name == "assets":
            copy_src = src_path
        else:
            sub = src_path / "assets"
            copy_src = sub if sub.exists() else src_path

        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(copy_src, dest)

        if self._install_id:
            self.db.update_installation(self._install_id, assets_extracted=1)

        self.refresh_state()
        messagebox.showinfo("Assets Copied", f"Assets copied to:\n{dest}", parent=self.root)

    def _script_extract_task(self, rom_path: str, install_dir: str):
        installer = Installer(
            install_dir=install_dir,
            on_progress=self._on_progress,
            on_status=self._on_status,
        )
        installer.run_extract_script(rom_path)
        if not Installer.check_assets(install_dir):
            raise InstallError(
                "Extract script finished but assets/ folder is missing.\n"
                "Check the operation log — the script may have reported an error."
            )
        if self._install_id:
            self.db.update_installation(self._install_id, assets_extracted=1)
        self._on_status("Assets extracted successfully!")

    def _wsl_extract_task(self, linux_url: str, rom_path: str, install_dir: str):
        installer = Installer(
            install_dir=install_dir,
            on_progress=self._on_progress,
            on_status=self._on_status,
        )
        installer.extract_assets_wsl(linux_url, rom_path)
        if self._install_id:
            self.db.update_installation(self._install_id, assets_extracted=1)
        self._on_status("Asset extraction complete!")

    def _launch_game(self):
        install_dir = self.config.get("install_dir", "")
        if not install_dir:
            messagebox.showinfo("Not Installed", "Install the game first.", parent=self.root)
            return

        launcher = GameLauncher(install_dir)
        ready, reason = launcher.is_ready()
        if not ready:
            messagebox.showwarning("Not Ready to Launch", reason, parent=self.root)
            return

        try:
            launcher.launch()
            self._append_log("Game launched.")
        except Exception as e:
            messagebox.showerror("Launch Failed", str(e), parent=self.root)
