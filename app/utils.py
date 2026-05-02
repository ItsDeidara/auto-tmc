from datetime import datetime, timedelta, timezone


def format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    elif n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    elif n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.1f} GB"


def format_relative_time(iso_str: str) -> str:
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - dt

        if delta < timedelta(minutes=1):
            return "just now"
        elif delta < timedelta(hours=1):
            mins = int(delta.total_seconds() / 60)
            return f"{mins} minute{'s' if mins != 1 else ''} ago"
        elif delta < timedelta(days=1):
            hours = int(delta.total_seconds() / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif delta < timedelta(days=30):
            days = delta.days
            return f"{days} day{'s' if days != 1 else ''} ago"
        elif delta < timedelta(days=365):
            months = delta.days // 30
            return f"{months} month{'s' if months != 1 else ''} ago"
        else:
            years = delta.days // 365
            return f"{years} year{'s' if years != 1 else ''} ago"
    except Exception:
        return iso_str


def format_datetime(iso_str: str) -> str:
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        day = str(dt.day)
        return dt.strftime(f"%B {day}, %Y")
    except Exception:
        return iso_str


def compare_versions(a: str, b: str) -> int:
    def normalize(v: str):
        v = v.lstrip("v")
        parts = v.split("-", 1)
        try:
            nums = [int(x) for x in parts[0].split(".")]
        except ValueError:
            nums = [0]
        pre = parts[1] if len(parts) > 1 else ""
        return nums, pre

    na, pa = normalize(a)
    nb, pb = normalize(b)

    for i in range(max(len(na), len(nb))):
        va = na[i] if i < len(na) else 0
        vb = nb[i] if i < len(nb) else 0
        if va < vb:
            return -1
        elif va > vb:
            return 1

    if pa == pb:
        return 0
    if not pa and pb:
        return 1
    if pa and not pb:
        return -1
    return (pa > pb) - (pa < pb)


def is_newer(candidate: str, installed: str) -> bool:
    if not installed:
        return True
    return compare_versions(candidate, installed) > 0
