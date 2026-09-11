"""Built-in and custom place management."""

import json
from pathlib import Path
from .coords import gcj02_to_wgs84

BUILTIN_PLACES = {
    "tiananmen": (39.9073,  116.391215, "天安门"),
    "guomao":    (39.90775, 116.455672, "国贸CBD"),
    "birdnest":  (39.991497, 116.390159, "鸟巢"),
    "shanghai":  (31.240807, 121.485998, "上海外滩"),
    "guangzhou": (23.109,   113.319111, "广州塔"),
    "paris":     (48.8584,  2.2945,    "巴黎埃菲尔铁塔"),
    "newyork":   (40.7580,  -73.9855,  "纽约时代广场"),
    "tokyo":     (35.6586,  139.7454,  "东京塔"),
    "london":    (51.5007,  -0.1246,   "伦敦大本钟"),
    "rome":      (41.8902,  12.4922,   "罗马斗兽场"),
}

_PLACES_FILE = Path.home() / ".fakegps_places"


def _load_custom():
    """Load custom places from disk. Supports both JSON and legacy bash format."""
    if not _PLACES_FILE.exists():
        return {}
    raw = _PLACES_FILE.read_text(encoding="utf-8")
    # Try JSON first
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass
    # Legacy bash format: CUSTOM_name="lat lng"
    places = {}
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("CUSTOM_") and "=" in line:
            key, val = line.split("=", 1)
            name = key[len("CUSTOM_"):]
            val = val.strip('"').strip("'")
            parts = val.split()
            if len(parts) >= 2:
                try:
                    places[name] = (float(parts[0]), float(parts[1]), name)
                except ValueError:
                    pass
    return places


def _save_custom(places):
    """Save custom places to disk as JSON."""
    data = {name: {"lat": v[0], "lng": v[1], "label": v[2]} for name, v in places.items()}
    _PLACES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_places():
    """Return all places (builtin + custom) as dict {name: (lat, lng, label)}."""
    result = dict(BUILTIN_PLACES)
    result.update(_load_custom())
    return result


def get_place(name):
    """Get a place by name. Returns (lat, lng, label) or None."""
    if name in BUILTIN_PLACES:
        return BUILTIN_PLACES[name]
    custom = _load_custom()
    return custom.get(name)


def add_place(name, lat, lng, is_gcj02=True):
    """Add a custom place. Coordinates are GCJ-02 by default (converted to WGS-84)."""
    if is_gcj02:
        lat, lng = gcj02_to_wgs84(lat, lng)
    custom = _load_custom()
    custom[name] = (lat, lng, name)
    _save_custom(custom)


def remove_place(name):
    """Remove a custom place. Returns True if removed."""
    custom = _load_custom()
    if name in custom:
        del custom[name]
        _save_custom(custom)
        return True
    return False


def search_places(query):
    """Fuzzy search places by name or label. Returns list of (name, lat, lng, label)."""
    query = query.lower().strip()
    if not query:
        return []
    all_places = list_places()
    results = []
    for name, (lat, lng, label) in all_places.items():
        if query in name.lower() or query in label.lower():
            results.append((name, lat, lng, label))
    return results


def place_exists(name):
    """Check if a place name exists (builtin or custom)."""
    return name in list_places()
