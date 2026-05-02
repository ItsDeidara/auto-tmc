import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple


class GameLauncher:
    def __init__(self, install_dir: str):
        self.install_dir = Path(install_dir)

    def get_executable(self) -> Optional[Path]:
        exe = self.install_dir / "tmc_pc.exe"
        return exe if exe.exists() else None

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
            raise RuntimeError("tmc_pc.exe not found in install directory.")

        kwargs = {"cwd": str(self.install_dir)}
        if sys.platform == "win32":
            kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )

        return subprocess.Popen([str(exe)], **kwargs)
