import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


class Database:
    """All public methods are serialized so worker threads cannot corrupt SQLite."""

    def __init__(self, app_data_dir: Path):
        self.db_path = app_data_dir / "auto_tmc.db"
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock:
            with self._connect() as conn:
                conn.executescript("""
                CREATE TABLE IF NOT EXISTS releases (
                    id INTEGER PRIMARY KEY,
                    tag_name TEXT UNIQUE NOT NULL,
                    release_name TEXT,
                    published_at TEXT,
                    is_prerelease INTEGER DEFAULT 1,
                    body TEXT,
                    windows_url TEXT,
                    windows_size INTEGER,
                    windows_sha256 TEXT,
                    linux_url TEXT,
                    linux_size INTEGER,
                    linux_sha256 TEXT,
                    macos_url TEXT,
                    macos_size INTEGER,
                    macos_sha256 TEXT,
                    cached_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS installations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tag_name TEXT NOT NULL,
                    install_path TEXT NOT NULL,
                    installed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    rom_sha1_verified INTEGER DEFAULT 0,
                    assets_extracted INTEGER DEFAULT 0,
                    assets_version TEXT,
                    is_current INTEGER DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tag_name TEXT,
                    platform TEXT,
                    asset_name TEXT,
                    bytes_total INTEGER,
                    bytes_downloaded INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT,
                    error_message TEXT
                );
            """)
                self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection):
        """Additive migrations for DBs created before newer columns existed.
        SQLite has no ADD COLUMN IF NOT EXISTS, so a duplicate-column
        OperationalError just means the migration already ran."""
        for col, decl in (
            ("macos_url", "TEXT"),
            ("macos_size", "INTEGER"),
            ("macos_sha256", "TEXT"),
        ):
            try:
                conn.execute(f"ALTER TABLE releases ADD COLUMN {col} {decl}")
            except sqlite3.OperationalError:
                pass

    def upsert_release(self, release: Dict[str, Any]):
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO releases
                        (id, tag_name, release_name, published_at, is_prerelease, body,
                         windows_url, windows_size, windows_sha256,
                         linux_url, linux_size, linux_sha256,
                         macos_url, macos_size, macos_sha256, cached_at)
                    VALUES
                        (:id, :tag_name, :release_name, :published_at, :is_prerelease, :body,
                         :windows_url, :windows_size, :windows_sha256,
                         :linux_url, :linux_size, :linux_sha256,
                         :macos_url, :macos_size, :macos_sha256, :cached_at)
                    ON CONFLICT(tag_name) DO UPDATE SET
                        release_name=excluded.release_name,
                        published_at=excluded.published_at,
                        body=excluded.body,
                        windows_url=excluded.windows_url,
                        windows_size=excluded.windows_size,
                        windows_sha256=excluded.windows_sha256,
                        linux_url=excluded.linux_url,
                        linux_size=excluded.linux_size,
                        linux_sha256=excluded.linux_sha256,
                        macos_url=excluded.macos_url,
                        macos_size=excluded.macos_size,
                        macos_sha256=excluded.macos_sha256,
                        cached_at=excluded.cached_at
                    """,
                    release,
                )

    def get_releases(self, limit: int = 20) -> List[sqlite3.Row]:
        with self._lock:
            with self._connect() as conn:
                return conn.execute(
                    "SELECT * FROM releases ORDER BY published_at DESC LIMIT ?", (limit,)
                ).fetchall()

    def get_release(self, tag_name: str) -> Optional[sqlite3.Row]:
        with self._lock:
            with self._connect() as conn:
                return conn.execute(
                    "SELECT * FROM releases WHERE tag_name=?", (tag_name,)
                ).fetchone()

    def get_latest_release(self) -> Optional[sqlite3.Row]:
        with self._lock:
            with self._connect() as conn:
                return conn.execute(
                    "SELECT * FROM releases ORDER BY published_at DESC LIMIT 1"
                ).fetchone()

    def add_installation(self, tag_name: str, install_path: str) -> int:
        with self._lock:
            with self._connect() as conn:
                conn.execute("UPDATE installations SET is_current=0")
                cursor = conn.execute(
                    "INSERT INTO installations (tag_name, install_path) VALUES (?,?)",
                    (tag_name, install_path),
                )
                return cursor.lastrowid

    def update_installation(self, install_id: int, **kwargs):
        if not kwargs:
            return
        cols = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [install_id]
        with self._lock:
            with self._connect() as conn:
                conn.execute(f"UPDATE installations SET {cols} WHERE id=?", vals)

    def get_current_installation(self) -> Optional[sqlite3.Row]:
        with self._lock:
            with self._connect() as conn:
                return conn.execute(
                    "SELECT * FROM installations WHERE is_current=1 ORDER BY installed_at DESC LIMIT 1"
                ).fetchone()

    def get_all_installations(self) -> List[sqlite3.Row]:
        with self._lock:
            with self._connect() as conn:
                return conn.execute(
                    "SELECT * FROM installations ORDER BY installed_at DESC"
                ).fetchall()

    def log_download(
        self, tag_name: str, platform: str, asset_name: str, bytes_total: int
    ) -> int:
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    "INSERT INTO downloads (tag_name, platform, asset_name, bytes_total) VALUES (?,?,?,?)",
                    (tag_name, platform, asset_name, bytes_total),
                )
                return cursor.lastrowid

    def update_download(self, dl_id: int, **kwargs):
        if not kwargs:
            return
        cols = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [dl_id]
        with self._lock:
            with self._connect() as conn:
                conn.execute(f"UPDATE downloads SET {cols} WHERE id=?", vals)
