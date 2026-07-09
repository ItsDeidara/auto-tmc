import platform
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

REPO = "999sian/tmc"
API_BASE = "https://api.github.com"

# Order matters: the first matching token wins when classifying an asset name.
_ARCH_ALIASES = {
    "arm64": ("arm64", "aarch64"),
    "x86_64": ("x86_64", "x86-64", "amd64", "x64"),
}


def normalize_arch(machine: str = "") -> str:
    """Map a platform.machine() string onto the arch tokens used in asset names."""
    m = (machine or platform.machine()).lower()
    if m in ("arm64", "aarch64", "armv8", "armv8l"):
        return "arm64"
    if m in ("x86_64", "amd64", "x64", "i686", "i386", "x86"):
        return "x86_64"
    return m


def platform_key() -> str:
    """OS family token used in TMC asset names for the current host."""
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def _classify_os(name: str) -> Optional[str]:
    n = name.lower()
    if "windows" in n or n.endswith(".exe") or ".exe" in n:
        return "windows"
    if "macos" in n or "darwin" in n or "osx" in n:
        return "macos"
    if "linux" in n:
        return "linux"
    return None


def _classify_arch(name: str) -> Optional[str]:
    n = name.lower()
    for arch, aliases in _ARCH_ALIASES.items():
        if any(alias in n for alias in aliases):
            return arch
    return None


class GitHubAPI:
    def __init__(self, token: str = ""):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "AutoTMC-Launcher/1.0",
            }
        )
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def set_token(self, token: str):
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        elif "Authorization" in self.session.headers:
            del self.session.headers["Authorization"]

    def get_releases(self, per_page: int = 20) -> List[Dict[str, Any]]:
        resp = self.session.get(
            f"{API_BASE}/repos/{REPO}/releases",
            params={"per_page": per_page},
            timeout=15,
        )
        resp.raise_for_status()
        return [self._parse_release(r) for r in resp.json()]

    def get_latest_release(self) -> Optional[Dict[str, Any]]:
        releases = self.get_releases(per_page=5)
        return releases[0] if releases else None

    def _parse_release(self, data: dict) -> Dict[str, Any]:
        # Group assets per OS family, then pick the one matching the host CPU
        # architecture. Falling back to any available arch keeps single-arch
        # releases installable. The DB is per-machine, so caching the
        # host-appropriate URL here is correct.
        host_arch = normalize_arch()
        by_os: Dict[str, Dict[str, Dict[str, Any]]] = {
            "windows": {},
            "linux": {},
            "macos": {},
        }

        for asset in data.get("assets", []):
            name: str = asset["name"]
            os_family = _classify_os(name)
            if os_family is None:
                continue

            digest: str = asset.get("digest", "") or ""
            sha256: Optional[str] = digest[7:] if digest.startswith("sha256:") else None

            info: Dict[str, Any] = {
                "url": asset["browser_download_url"],
                "size": asset["size"],
                "sha256": sha256,
                "name": name,
            }
            arch = _classify_arch(name) or "_noarch"
            by_os[os_family][arch] = info

        def pick(os_family: str) -> Optional[Dict[str, Any]]:
            candidates = by_os[os_family]
            if not candidates:
                return None
            if host_arch in candidates:
                return candidates[host_arch]
            # Prefer a real arch over the "_noarch" bucket, else take anything.
            for arch, info in candidates.items():
                if arch != "_noarch":
                    return info
            return next(iter(candidates.values()))

        windows_asset = pick("windows")
        linux_asset = pick("linux")
        macos_asset = pick("macos")

        return {
            "id": data["id"],
            "tag_name": data["tag_name"],
            "release_name": data.get("name", data["tag_name"]),
            "published_at": data.get("published_at", ""),
            "is_prerelease": int(data.get("prerelease", False)),
            "body": data.get("body", ""),
            "windows_url": windows_asset["url"] if windows_asset else None,
            "windows_size": windows_asset["size"] if windows_asset else None,
            "windows_sha256": windows_asset["sha256"] if windows_asset else None,
            "linux_url": linux_asset["url"] if linux_asset else None,
            "linux_size": linux_asset["size"] if linux_asset else None,
            "linux_sha256": linux_asset["sha256"] if linux_asset else None,
            "macos_url": macos_asset["url"] if macos_asset else None,
            "macos_size": macos_asset["size"] if macos_asset else None,
            "macos_sha256": macos_asset["sha256"] if macos_asset else None,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_rate_limit(self) -> Dict[str, Any]:
        resp = self.session.get(f"{API_BASE}/rate_limit", timeout=10)
        resp.raise_for_status()
        return resp.json().get("rate", {})


def _row_get(release: Any, key: str) -> Any:
    """Read a field from either a dict or a sqlite3.Row."""
    if isinstance(release, dict):
        return release.get(key)
    try:
        return release[key]
    except (IndexError, KeyError):
        return None


def select_asset(release: Any) -> Dict[str, Optional[Any]]:
    """Return {'url', 'size', 'sha256'} for the current host OS from a release
    record (dict or sqlite3.Row). Values are None when no asset ships for this
    platform."""
    key = platform_key()
    return {
        "url": _row_get(release, f"{key}_url"),
        "size": _row_get(release, f"{key}_size"),
        "sha256": _row_get(release, f"{key}_sha256"),
    }


def fetch_releases(per_page: int = 20) -> List[Dict[str, Any]]:
    """Latest releases for `REPO`: one GitHub API call, launcher DB/UI shape."""
    return GitHubAPI().get_releases(per_page=per_page)
