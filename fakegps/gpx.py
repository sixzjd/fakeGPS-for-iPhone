"""GPX file parsing for trajectory playback."""

import xml.etree.ElementTree as ET
from pathlib import Path


def parse_gpx(filepath):
    """Parse a .gpx file and return list of (lat, lng, elevation, time_str).

    Supports GPX 1.1 format with <trk>/<trkseg>/<trkpt> structure.
    Also supports <wpt> waypoints.
    """
    tree = ET.parse(Path(filepath).expanduser())
    root = tree.getroot()

    # Handle GPX namespace
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    points = []

    # Extract track points
    for trk in root.findall(f"{ns}trk"):
        for seg in trk.findall(f"{ns}trkseg"):
            for pt in seg.findall(f"{ns}trkpt"):
                lat = float(pt.get("lat"))
                lng = float(pt.get("lon"))
                ele_el = pt.find(f"{ns}ele")
                time_el = pt.find(f"{ns}time")
                ele = float(ele_el.text) if ele_el is not None else 0.0
                time_str = time_el.text if time_el is not None else ""
                points.append((lat, lng, ele, time_str))

    # If no tracks, try waypoints
    if not points:
        for wpt in root.findall(f"{ns}wpt"):
            lat = float(wpt.get("lat"))
            lng = float(wpt.get("lon"))
            ele_el = wpt.find(f"{ns}ele")
            time_el = wpt.find(f"{ns}time")
            ele = float(ele_el.text) if ele_el is not None else 0.0
            time_str = time_el.text if time_el is not None else ""
            points.append((lat, lng, ele, time_str))

    return points
