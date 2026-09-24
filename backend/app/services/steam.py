import json
import re
import urllib.request
from typing import Optional

STEAM_CLASS_RE = re.compile(r"^steam_app_(\d+)$", re.IGNORECASE)

def steam_app_id(window_class: str) -> Optional[str]:
    m = STEAM_CLASS_RE.match(window_class.strip())
    return m.group(1) if m else None

def fetch_steam_name(app_id: str, timeout: float = 6.0) -> Optional[str]:
    """Game name from the Steam Store API. Returns None on any network error."""
    url = (
        "https://store.steampowered.com/api/appdetails"
        f"?appids={app_id}&filters=basic&l=english"
    )
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.load(resp)
    except Exception as e:
        print(f"Steam lookup failed for appid {app_id}: {e}")
        return None

    entry = data.get(str(app_id)) or {}
    if not entry.get("success"):
        return None
    name = (entry.get("data") or {}).get("name")
    return name.strip() if name else None
