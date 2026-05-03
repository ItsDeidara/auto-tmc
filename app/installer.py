import hashlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional, Tuple

import requests

ROM_SHA1 = "b4bd50e4131b027c334547b4524e2dbbd4227130"


class InstallError(Exception):
    pass


class Installer:
    def __init__(
        self,
        install_dir: str,
        on_progress: Optional[Callable[[int, str], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ):
        self.install_dir = Path(install_dir)
        self.on_progress = on_progress or (lambda pct, msg: None)
        self.on_status = on_status or (lambda msg: None)
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def download_and_install(self, url: str, sha256: Optional[str], tag_name: str) -> Path:
        if not url:
            raise InstallError("No download URL provided.")

        self.install_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "release.tar.gz"

            self.on_status(f"Downloading {tag_name}...")
            self._download(url, tmp_path)

            if sha256:
                self.on_status("Verifying integrity (SHA-256)...")
                self._verify_sha256(tmp_path, sha256)

            self.on_status("Extracting files...")
            self._extract(tmp_path, self.install_dir)

        self.on_status("Installation complete.")
        self.on_progress(100, "Done")
        return self.install_dir

    def _download(self, url: str, dest: Path):
        try:
            resp = requests.get(url, stream=True, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise InstallError(f"Download failed: {e}")

        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        chunk_size = 65536

        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if self._cancel.is_set():
                    raise InstallError("Download cancelled.")
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = int(downloaded / total * 80)
                        mb_done = downloaded / 1_048_576
                        mb_total = total / 1_048_576
                        self.on_progress(pct, f"Downloading {mb_done:.1f} / {mb_total:.1f} MB")

    def _verify_sha256(self, path: Path, expected: str):
        sha = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        actual = sha.hexdigest()
        if actual.lower() != expected.lower():
            raise InstallError(
                f"SHA-256 verification failed!\n"
                f"Expected: {expected}\n"
                f"Got:      {actual}"
            )

    def _extract(self, tar_path: Path, dest: Path):
        try:
            tf_handle = tarfile.open(tar_path, "r:gz")
        except tarfile.TarError as e:
            raise InstallError(f"Failed to open archive: {e}")

        with tf_handle as tf:
            members = tf.getmembers()

            # Detect single top-level directory to strip (e.g. tmc_pc-windows-x86_64/)
            top_dirs = set()
            for m in members:
                parts = m.name.split("/")
                top_dirs.add(parts[0])
            strip = (top_dirs.pop() + "/") if len(top_dirs) == 1 else ""

            total = max(len(members), 1)
            dest_resolved = dest.resolve()

            for i, member in enumerate(members):
                if self._cancel.is_set():
                    raise InstallError("Extraction cancelled.")

                name = member.name
                if strip:
                    if name.rstrip("/") == strip.rstrip("/"):
                        continue
                    if name.startswith(strip):
                        name = name[len(strip):]
                    else:
                        continue

                if not name:
                    continue

                # Prevent path traversal
                try:
                    (dest / name).resolve().relative_to(dest_resolved)
                except ValueError:
                    continue

                member.name = name
                try:
                    tf.extract(member, dest, set_attrs=False)
                except Exception:
                    pass

                pct = 80 + int((i + 1) / total * 18)
                self.on_progress(pct, f"Extracting {Path(name).name}")

    @staticmethod
    def validate_rom(rom_path: str) -> Tuple[bool, str]:
        path = Path(rom_path)
        if not path.exists():
            return False, "ROM file not found."
        if path.suffix.lower() != ".gba":
            return False, "File must have a .gba extension."
        if path.stat().st_size == 0:
            return False, "ROM file is empty."

        sha1 = hashlib.sha1()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha1.update(chunk)

        actual = sha1.hexdigest()
        if actual.lower() == ROM_SHA1.lower():
            return True, "ROM validated — SHA-1 matches (USA/BZME)."

        return (
            False,
            f"SHA-1 mismatch. Ensure you have the USA (BZME) version.\n"
            f"Expected: {ROM_SHA1}\n"
            f"Got:      {actual}",
        )

    @staticmethod
    def detect_wsl() -> bool:
        try:
            no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(
                ["wsl", "-e", "echo", "ok"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=no_window if sys.platform == "win32" else 0,
            )
            return result.returncode == 0 and "ok" in result.stdout
        except Exception:
            return False

    @staticmethod
    def has_extract_script(install_dir: str) -> Tuple[bool, str]:
        """Return (found, script_name) for any bundled extract script/executable in install_dir."""
        d = Path(install_dir)
        # Check for asset_extractor (preferred), then fallback to extract scripts
        for name in ("asset_extractor.exe", "asset_extractor", "extract.bat", "extract.sh"):
            if (d / name).exists():
                return True, name
        return False, ""

    def run_extract_script(self, rom_path: str) -> bool:
        """Run asset_extractor, extract.bat (Windows native) or extract.sh (WSL) from the install directory.

        Ensures baserom.gba is in install_dir first, then runs the extraction tool.
        The tool writes assets/ into the install directory.
        """
        rom_dest = self.install_dir / "baserom.gba"
        if rom_path and Path(rom_path).exists() and not rom_dest.exists():
            shutil.copy2(rom_path, rom_dest)
            self.on_status(f"Copied ROM → {rom_dest.name}")

        # Check for asset_extractor first (preferred), then extract scripts
        extractor = self.install_dir / "asset_extractor.exe"
        if not extractor.exists():
            extractor = self.install_dir / "asset_extractor"
        if extractor.exists():
            return self._run_extractor(extractor)

        bat = self.install_dir / "extract.bat"
        sh = self.install_dir / "extract.sh"

        # Prefer native bat on Windows; fall back to sh via WSL
        if bat.exists() and sys.platform == "win32":
            return self._run_bat(bat)
        if sh.exists() and self.detect_wsl():
            return self._run_sh_wsl(sh)
        if bat.exists():
            return self._run_bat(bat)
        if sh.exists():
            return self._run_sh_wsl(sh)

        raise InstallError(
            "No extraction tool found in the install directory.\n"
            "Install a release that includes asset_extractor, extract.bat, or extract.sh."
        )

    def _run_extractor(self, exe: Path) -> bool:
        import time
        import threading

        self.on_status(f"Running {exe.name} — this takes 1-2 minutes...")
        start_time = time.time()
        self.on_progress(0, "Starting asset extraction...")

        # Use Popen to get realtime output
        no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            [str(exe)],
            cwd=str(self.install_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            creationflags=no_window if sys.platform == "win32" else 0,
        )

        # Track progress and output in a separate thread
        def monitor_process():
            total_lines = 0
            asset_count = 0
            last_update = time.time()

            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break

                line = line.strip()
                if line:
                    total_lines += 1
                    # Count assets being processed (look for common patterns)
                    if any(keyword in line.lower() for keyword in ['extracting', 'processing', 'writing', 'creating']):
                        asset_count += 1

                    # Show the line in the log
                    self.on_status(line)

                    # Update progress based on time and activity
                    elapsed = time.time() - start_time
                    if elapsed > 2:  # Don't update too frequently
                        # Estimate progress based on typical extraction patterns
                        # Most extractions take 60-90 seconds, with progress accelerating
                        if elapsed < 30:
                            progress = min(20 + (elapsed / 30) * 30, 50)  # 20-50% in first 30s
                        elif elapsed < 60:
                            progress = min(50 + (elapsed - 30) / 30 * 30, 80)  # 50-80% in next 30s
                        else:
                            progress = min(80 + (elapsed - 60) / 30 * 20, 95)  # 80-95% after 60s

                        # Estimate time remaining
                        if progress > 5:
                            total_estimated = elapsed / (progress / 100)
                            remaining = max(0, total_estimated - elapsed)
                            if remaining < 60:
                                time_str = f"{remaining:.0f}s"
                            else:
                                time_str = f"{remaining/60:.1f}m"
                            self.on_progress(int(progress), f"Extracting assets... ({time_str} remaining)")
                        else:
                            self.on_progress(int(progress), "Extracting assets...")

            # Final progress update
            self.on_progress(100, "Asset extraction complete")

        # Start monitoring thread
        monitor_thread = threading.Thread(target=monitor_process, daemon=True)
        monitor_thread.start()

        # Wait for process to complete with timeout
        try:
            process.wait(timeout=600)  # 10 minute timeout
        except subprocess.TimeoutExpired:
            process.kill()
            raise InstallError(f"{exe.name} timed out after 10 minutes")

        if process.returncode != 0:
            raise InstallError(f"{exe.name} failed (exit {process.returncode})")

        return True

    def _run_bat(self, bat: Path) -> bool:
        self.on_status(f"Running {bat.name} — this takes 1-2 minutes...")
        self.on_progress(10, "Extracting assets")
        no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            ["cmd.exe", "/c", bat.name],
            cwd=str(self.install_dir),
            capture_output=True,
            text=True,
            timeout=300,
            creationflags=no_window if sys.platform == "win32" else 0,
        )
        for line in (result.stdout or "").splitlines()[-30:]:
            if line.strip():
                self.on_status(line)
        if result.returncode != 0:
            raise InstallError(
                f"extract.bat failed (exit {result.returncode}):\n"
                f"{(result.stderr or '')[-1000:]}"
            )
        self.on_progress(98, "Script complete")
        return True

    def _run_sh_wsl(self, sh: Path) -> bool:
        if not self.detect_wsl():
            raise InstallError(
                "extract.sh found but WSL is not available.\n"
                "Run 'wsl --install' in PowerShell, reboot, then try again."
            )
        self.on_status("Running extract.sh via WSL — this takes 1-2 minutes...")
        self.on_progress(10, "Extracting assets via WSL")
        wsl_dir = self._to_wsl_path(self.install_dir)
        result = subprocess.run(
            ["wsl", "-e", "bash", "-c",
             f"cd '{wsl_dir}' && chmod +x extract.sh && bash extract.sh"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        for line in (result.stdout or "").splitlines()[-30:]:
            if line.strip():
                self.on_status(line)
        if result.returncode != 0:
            raise InstallError(
                f"extract.sh failed (exit {result.returncode}):\n"
                f"{(result.stderr or '')[-1000:]}"
            )
        self.on_progress(98, "Script complete")
        return True

    def extract_assets_wsl(self, linux_tar_url: str, rom_path: str) -> bool:
        if not self.detect_wsl():
            raise InstallError("WSL is not available on this system.")

        rom_path_obj = Path(rom_path)
        if not rom_path_obj.exists():
            raise InstallError("ROM file not found.")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            linux_tar = tmp / "linux_release.tar.gz"

            self.on_status("Downloading Linux toolchain for asset extraction...")
            self._download(linux_tar_url, linux_tar)

            self.on_status("Unpacking Linux toolchain...")
            tools_dir = tmp / "tools_extract"
            tools_dir.mkdir()

            with tarfile.open(linux_tar, "r:gz") as tf:
                tf.extractall(tools_dir)

            extracted = list(tools_dir.iterdir())
            if not extracted:
                raise InstallError("Linux tar appears to be empty.")
            src_dir = extracted[0]

            shutil.copy2(rom_path_obj, src_dir / "baserom.gba")

            self.on_status("Running extract.sh via WSL (may take 1-2 minutes)...")
            wsl_src = self._to_wsl_path(src_dir)
            result = subprocess.run(
                ["wsl", "-e", "bash", "-c",
                 f"cd '{wsl_src}' && chmod +x extract.sh && bash extract.sh"],
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode != 0:
                raise InstallError(
                    f"Asset extraction failed (exit {result.returncode}):\n"
                    f"{result.stderr[-1200:]}"
                )

            # Search for the output assets directory
            candidates = [
                src_dir / "build" / "pc" / "assets",
                src_dir / "build" / "assets",
                src_dir / "assets",
            ]
            assets_src = None
            for candidate in candidates:
                if candidate.exists():
                    try:
                        if any(candidate.iterdir()):
                            assets_src = candidate
                            break
                    except Exception:
                        pass

            if not assets_src:
                raise InstallError(
                    "Could not find extracted assets directory after running extract.sh.\n"
                    "Check the WSL output log for errors."
                )

            assets_dest = self.install_dir / "assets"
            if assets_dest.exists():
                shutil.rmtree(assets_dest)
            shutil.copytree(assets_src, assets_dest)
            self.on_status(f"Assets copied to: {assets_dest}")

        return True

    @staticmethod
    def _to_wsl_path(windows_path: Path) -> str:
        p = str(windows_path).replace("\\", "/")
        if len(p) >= 2 and p[1] == ":":
            drive = p[0].lower()
            p = f"/mnt/{drive}{p[2:]}"
        return p

    @staticmethod
    def check_assets(install_dir: str) -> bool:
        assets_dir = Path(install_dir) / "assets"
        if not assets_dir.exists():
            return False
        try:
            return any(assets_dir.iterdir())
        except Exception:
            return False

    @staticmethod
    def setup_rom(rom_path: str, install_dir: str) -> Path:
        dest = Path(install_dir) / "baserom.gba"
        src = Path(rom_path)
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        return dest
