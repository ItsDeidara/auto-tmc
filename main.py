import atexit
import logging
import os
import sys
import traceback

# ── log file sits next to main.py ────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
try:
    os.chdir(BASE_DIR)
except OSError:
    pass
LOG_PATH = os.path.join(BASE_DIR, "error.log")


def _flush_all_handlers() -> None:
    for h in logging.root.handlers:
        try:
            h.flush()
        except Exception:
            pass


class _FlushFileHandler(logging.FileHandler):
    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        try:
            self.flush()
        except Exception:
            pass


def _configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    if root.handlers:
        return
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = _FlushFileHandler(LOG_PATH, mode="a", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)
    con = logging.StreamHandler(sys.stderr)
    con.setLevel(logging.WARNING)
    con.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root.addHandler(con)


_configure_logging()
log = logging.getLogger("main")

for _lib in ("urllib3", "asyncio"):
    logging.getLogger(_lib).setLevel(logging.WARNING)


@atexit.register
def _on_exit():
    log.info("Process exiting (atexit)")
    _flush_all_handlers()


def _show_fatal(msg: str):
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror(
            "Auto-TMC — Fatal Error",
            f"{msg}\n\nFull details saved to:\n{LOG_PATH}",
        )
        r.destroy()
    except Exception:
        pass
    finally:
        _flush_all_handlers()


def _excepthook(exc_type, exc_value, exc_tb):
    log.critical("Unhandled exception:\n%s",
                 "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
    _flush_all_handlers()
    _show_fatal(f"{exc_type.__name__}: {exc_value}")


sys.excepthook = _excepthook


def main():
    log.info("Session start — Python %s", sys.version.split()[0])
    log.debug("BASE_DIR: %s", BASE_DIR)
    sys.path.insert(0, BASE_DIR)

    try:
        log.debug("Importing app modules")
        from app.config import Config
        from app.database import Database
        from app.ui.main_window import MainWindow
        log.debug("Imports OK")
    except BaseException:
        log.critical("Import failed:\n%s", traceback.format_exc())
        _flush_all_handlers()
        _show_fatal(f"Failed to import modules:\n\n{traceback.format_exc()}")
        sys.exit(1)

    try:
        config = Config()
        db = Database(config.app_data_dir)
        window = MainWindow(config, db)

        def _tk_cb_error(exc, val, tb):
            log.error("Tkinter callback exception:\n%s",
                      "".join(traceback.format_exception(exc, val, tb)))
            _flush_all_handlers()

        window.root.report_callback_exception = _tk_cb_error

        log.info("Entering main loop")
        _flush_all_handlers()
        window.run()
        log.info("Main loop exited cleanly")
        _flush_all_handlers()

    except KeyboardInterrupt:
        log.info("KeyboardInterrupt — exiting")
        _flush_all_handlers()
        raise
    except SystemExit:
        raise
    except BaseException:
        log.critical("Runtime error:\n%s", traceback.format_exc())
        _flush_all_handlers()
        _show_fatal(f"Crashed on startup:\n\n{traceback.format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    main()
