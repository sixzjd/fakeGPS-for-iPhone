"""GCJ-02 (Amap/Tencent) <-> WGS-84 (GPS) coordinate conversion."""

import math

_A = 6378245.0
_EE = 0.00669342162296594323


def _transform_lat(x, y):
    r = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    r += (20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)) * 2 / 3
    r += (20 * math.sin(y * math.pi) + 40 * math.sin(y / 3 * math.pi)) * 2 / 3
    r += (160 * math.sin(y / 12 * math.pi) + 320 * math.sin(y * math.pi / 30)) * 2 / 3
    return r


def _transform_lng(x, y):
    r = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    r += (20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)) * 2 / 3
    r += (20 * math.sin(x * math.pi) + 40 * math.sin(x / 3 * math.pi)) * 2 / 3
    r += (150 * math.sin(x / 12 * math.pi) + 300 * math.sin(x / 30 * math.pi)) * 2 / 3
    return r


def _in_china(lat, lng):
    return 0.8293 <= lat <= 55.8271 and 72.004 <= lng <= 137.8347


def _delta(lat, lng):
    dlat = _transform_lat(lng - 105, lat - 35)
    dlng = _transform_lng(lng - 105, lat - 35)
    radlat = lat / 180 * math.pi
    magic = math.sin(radlat)
    magic = 1 - _EE * magic * magic
    sq = math.sqrt(magic)
    dlat = (dlat * 180) / ((_A * (1 - _EE)) / (magic * sq) * math.pi)
    dlng = (dlng * 180) / (_A / sq * math.cos(radlat) * math.pi)
    return dlat, dlng


def gcj02_to_wgs84(lat, lng):
    """Convert GCJ-02 coordinates to WGS-84. Iterative approximation."""
    if not _in_china(lat, lng):
        return lat, lng
    dlat, dlng = _delta(lat, lng)
    wgs_lat, wgs_lng = lat - dlat, lng - dlng
    for _ in range(10):
        dlat2, dlng2 = _delta(wgs_lat, wgs_lng)
        new_lat = lat - dlat2
        new_lng = lng - dlng2
        if abs(new_lat - wgs_lat) < 1e-6 and abs(new_lng - wgs_lng) < 1e-6:
            return new_lat, new_lng
        wgs_lat, wgs_lng = new_lat, new_lng
    return wgs_lat, wgs_lng


def wgs84_to_gcj02(lat, lng):
    """Convert WGS-84 coordinates to GCJ-02."""
    if not _in_china(lat, lng):
        return lat, lng
    dlat, dlng = _delta(lat, lng)
    return lat + dlat, lng + dlng
