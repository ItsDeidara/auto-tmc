import logging
import sys
import threading

import customtkinter as ctk

from ..config import Config
from ..database import Database
from .home_tab import HomeTab
from .releases_tab import ReleasesTab
from .settings_tab import SettingsTab

APP_VERSION = "1.0.0"

_MIN_W = 520
_MIN_H = 340
# Hard cap so old saved window sizes cannot reopen as a near-fullscreen empty shell.
_MAX_W = 760
_MAX_H = 560

_log = logging.getLogger(__name__)


class MainWindow:
    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db

        ctk.set_appearance_mode(config.get("theme", "dark"))
        ctk.set_default_color_theme("blue")
        # Tcl/Tk 9 + HiDPI: avoid fractional scaling bugs that can kill the event loop on Python 3.14.
        try:
            ctk.set_widget_scaling(1.0)
            ctk.set_window_scaling(1.0)
        except Exception:
            pass

        self.root = ctk.CTk()
        self.root.title("TMC PC Launcher")

        # Read screen dimensions in logical pixels (already accounts for DPI scaling).
        # geometry() uses the same unit, so capping to a screen fraction is reliable
        # across 100%, 125%, 150%, 200% display-scaling settings.
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        if sw <= 0 or sh <= 0:
            sw, sh = 1920, 1080

        saved_w = config.get("window_width", 680)
        saved_h = config.get("window_height", 480)

        w = max(_MIN_W, min(saved_w, _MAX_W, int(sw * 0.70)))
        h = max(_MIN_H, min(saved_h, _MAX_H, int(sh * 0.72)))

        # Center on screen
        x = (sw - w) // 2
        y = max(0, (sh - h) // 2 - 20)

        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.minsize(_MIN_W, _MIN_H)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        try:
            self.root.lift()
        except Exception:
            pass
        # Stagger background work on 3.14+ (Tcl 9): simultaneous after() + threads caused flaky exits.
        self._startup_delay_ms = 900 if sys.version_info >= (3, 14) else 200
        self._schedule_startup_refresh()

    def _build_ui(self):
        self.tabview = ctk.CTkTabview(self.root, anchor="nw", corner_radius=6)
        self.tabview.pack(fill="both", expand=True, padx=6, pady=(6, 0))

        home_frame = self.tabview.add("Home")
        releases_frame = self.tabview.add("Releases")
        settings_frame = self.tabview.add("Settings")

        self.home = HomeTab(home_frame, self.root, self.config, self.db)
        self.releases = ReleasesTab(releases_frame, self.root, self.config, self.db)
        self.settings = SettingsTab(
            settings_frame,
            self.root,
            self.config,
            self.db,
            on_state_changed=self.home.refresh_state,
        )

        # Status bar
        bar = ctk.CTkFrame(self.root, height=22, corner_radius=0, fg_color="#181818")
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        ctk.CTkLabel(
            bar,
            text=f"Auto-TMC v{APP_VERSION}  ·  github.com/999sian/tmc",
            font=ctk.CTkFont(size=10),
            text_color="#555555",
        ).pack(side="left", padx=8, pady=2)

    def _on_close(self):
        try:
            self.config.set("window_width", self.root.winfo_width())
            self.config.set("window_height", self.root.winfo_height())
        except Exception:
            pass
        self.root.destroy()

    def _schedule_startup_refresh(self) -> None:
        """After first paint, optionally fetch releases once, then sync every tab from DB."""
        self.root.after(self._startup_delay_ms, self._startup_refresh)

    def _startup_refresh(self) -> None:
        if self.config.get("auto_check_updates", True):

            def worker() -> None:
                """Network only here — SQLite + Tk must run on the main thread."""
                rows: list = []
                try:
                    from ..github_api import fetch_releases

                    rows = list(fetch_releases())
                except Exception as e:
                    _log.warning("Startup release refresh failed: %s", e)

                def apply_on_main() -> None:
                    try:
                        for r in rows:
                            self.db.upsert_release(r)
                    except Exception:
                        _log.exception("Startup DB upsert failed")
                    try:
                        self._apply_startup_refresh_sync()
                    except Exception:
                        _log.exception("Startup UI refresh failed")

                self.root.after(0, apply_on_main)

            threading.Thread(target=worker, daemon=True).start()
        else:
            self._apply_startup_refresh_sync()

    def _apply_startup_refresh_sync(self) -> None:
        try:
            self.home.sync_latest_from_db()
            self.home.refresh_state()
            self.releases._load_cached()
        except Exception:
            _log.exception("Applying startup refresh state failed")

    def run(self) -> None:
        try:
            self.root.mainloop()
        except Exception:
            _log.exception("mainloop() raised")
            raise
        finally:
            _log.info("mainloop() returned")
