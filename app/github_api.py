from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

REPO = "999sian/tmc"
API_BASE = "https://api.github.com"


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
        windows_asset: Optional[Dict] = None
        linux_asset: Optional[Dict] = None

        for asset in data.get("assets", []):
            name: str = asset["name"]
            sha256: Optional[str] = None
            digest: str = asset.get("digest", "") or ""
            if digest.startswith("sha256:"):
                sha256 = digest[7:]

            info: Dict[str, Any] = {
                "url": asset["browser_download_url"],
                "size": asset["size"],
                "sha256": sha256,
                "name": name,
            }

            if "windows" in name.lower():
                windows_asset = info
            elif "linux" in name.lower():
                linux_asset = info

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
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_rate_limit(self) -> Dict[str, Any]:
        resp = self.session.get(f"{API_BASE}/rate_limit", timeout=10)
        resp.raise_for_status()
        return resp.json().get("rate", {})


def fetch_releases(per_page: int = 20) -> List[Dict[str, Any]]:
    """Latest releases for `REPO`: one GitHub API call, launcher DB/UI shape."""
    return GitHubAPI().get_releases(per_page=per_page)
