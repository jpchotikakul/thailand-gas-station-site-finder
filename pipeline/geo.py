"""Distance helpers (no third-party geospatial dependency)."""
from __future__ import annotations

import math
from typing import Iterable, Optional

EARTH_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_KM * math.asin(min(1.0, math.sqrt(a)))


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    return haversine_km(lat1, lon1, lat2, lon2) * 1000.0


def point_to_segment_m(lat, lon, a_lat, a_lon, b_lat, b_lon) -> float:
    """Approximate point-to-segment distance in metres (local equirectangular)."""
    # Convert to local metres around the point.
    latr = math.radians(lat)
    x = (lon - a_lon) * math.cos(latr) * 111_320.0
    y = (lat - a_lat) * 110_540.0
    x1 = 0.0
    y1 = 0.0
    x2 = (b_lon - a_lon) * math.cos(latr) * 111_320.0
    y2 = (b_lat - a_lat) * 110_540.0
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x, y)
    t = max(0.0, min(1.0, (x * dx + y * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - t * dx, y - t * dy)


def nearest_points(
    lat: float,
    lon: float,
    points: Iterable[dict],
    radius_km: float,
    limit: int = 12,
) -> list[dict]:
    hits = []
    r2 = radius_km  # compared in km
    for p in points:
        d = haversine_km(lat, lon, p["lat"], p["lon"])
        if d <= r2:
            hits.append((d, p))
    hits.sort(key=lambda x: x[0])
    out = []
    for d, p in hits[:limit]:
        item = dict(p)
        item["distance_km"] = round(d, 2)
        out.append(item)
    return out
