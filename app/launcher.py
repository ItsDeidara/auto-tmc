import stat
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

# tmc_pc.exe on Windows, bare tmc_pc elsewhere. Check both so a mismatched
# install (e.g. a Linux tarball on a case-insensitive FS) still resolves.
EXE_NAMES = ("tmc_pc.exe", "tmc_pc") if sys.platform.startswith("win") else ("tmc_pc", "tmc_pc.exe")


def find_executable(install_dir) -> Optional[Path]:
    d = Path(install_dir)
    for name in EXE_NAMES:
        exe = d / name
        if exe.exists():
            return exe
    return None


class GameLauncher:
    def __init__(self, install_dir: str):
        self.install_dir = Path(install_dir)

    def get_executable(self) -> Optional[Path]:
        return find_executable(self.install_dir)

    def is_ready(self, check_rom: bool = True, check_assets: bool = True) -> Tuple[bool, str]:
        exe = self.get_executable()
        if not exe:
            return False, "Game executable not found. Install the game first."

        if check_rom:
            rom = self.install_dir / "baserom.gba"
            if not rom.exists():
                return False, "baserom.gba not found. Use 'Setup ROM' to configure it."

        if check_assets:
            assets = self.install_dir / "assets"
            if not assets.exists():
                return False, "Assets folder missing. Use 'Extract Assets' first."
            try:
                if not any(assets.iterdir()):
                    return False, "Assets folder is empty. Use 'Extract Assets' first."
            except Exception:
                return False, "Cannot read assets folder."

        return True, "Ready to play."

    def launch(self) -> subprocess.Popen:
        exe = self.get_executable()
        if not exe:
            raise RuntimeError("tmc_pc executable not found in install directory.")

        # Archive extraction drops the exec bit on POSIX; restore it before launch.
        if not sys.platform.startswith("win"):
            try:
                mode = exe.stat().st_mode
                exe.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            except OSError:
                pass

        kwargs = {"cwd": str(self.install_dir)}
        if sys.platform == "win32":
            kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            kwargs["start_new_session"] = True

        return subprocess.Popen([str(exe)], **kwargs)
