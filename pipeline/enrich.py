"""Geocode (when precise enough), flag shared coordinates, enrich from OpenStreetMap.

Official Thai traffic-count datasets are not bundled: if a clean public file is not
available, traffic remains an OSM-based proxy and is labelled Estimated.
Zoning / city-plan (ผังเมือง) is not available via a public API; it is left as
Data not available with a link to the official DPT viewer.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from .geo import haversine_km, nearest_points, point_to_segment_m
from .httputil import USER_AGENT, fetch
from .collect import now_iso, log

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "pipeline" / "cache"

TH_BBOX = (5.5, 97.3, 20.6, 105.8)  # s, w, n, e
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
)
NOMINATIM = "https://nominatim.openstreetmap.org/search"
DPT_VIEWER = "https://oneplan.dpt.go.th/"

# Highway classes we treat as "major" for a gas-station site.
MAJOR_HIGHWAYS = {
    "motorway": 100,
    "motorway_link": 85,
    "trunk": 92,
    "trunk_link": 78,
    "primary": 80,
    "primary_link": 68,
    "secondary": 62,
    "secondary_link": 52,
    "tertiary": 45,
    "tertiary_link": 38,
}
# We download these classes as ways (plus tertiary for completeness of "road type" filter).
ROAD_CLASSES = "motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary"


def _overpass(query: str, cache_name: str, timeout: int = 45) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / cache_name
    if path.exists() and path.stat().st_size > 100:
        log(f"[osm] using cache {path} ({path.stat().st_size:,} bytes)")
        return json.loads(path.read_text("utf-8"))
    body = query.encode("utf-8")
    last_err = None
    for endpoint in OVERPASS_ENDPOINTS:
        log(f"[osm] querying {endpoint} for {cache_name} ...")
        req = urllib.request.Request(
            endpoint,
            data=body,
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
                "Accept": "application/json",
            },
            method="POST",
        )
        # Overpass expects `data=...`
        data = urllib.parse.urlencode({"data": query}).encode()
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            payload = json.loads(raw.decode("utf-8"))
            path.write_bytes(raw)
            log(f"[osm] wrote {path} ({len(raw):,} bytes, {len(payload.get('elements') or [])} elements)")
            return payload
        except Exception as e:
            last_err = e
            log(f"[osm] {endpoint} failed: {type(e).__name__}: {e}")
            time.sleep(5)
    raise RuntimeError(f"Overpass failed for {cache_name}: {last_err}")


def _elements_to_points(payload: dict, name_fallback: str = "") -> list[dict]:
    points = []
    for el in payload.get("elements") or []:
        tags = el.get("tags") or {}
        if el.get("type") == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            c = el.get("center") or {}
            lat, lon = c.get("lat"), c.get("lon")
        if lat is None or lon is None:
            continue
        name = tags.get("name") or tags.get("name:en") or tags.get("brand") or tags.get("operator") or name_fallback
        brand = tags.get("brand") or tags.get("operator")
        points.append(
            {
                "lat": float(lat),
                "lon": float(lon),
                "name": name,
                "brand": brand,
                "osm_id": f"{el.get('type')}/{el.get('id')}",
                "tags": {k: tags[k] for k in ("highway", "amenity", "shop", "tourism", "landuse", "lanes", "name:th") if k in tags},
            }
        )
    return points


def _ways_to_roads(payload: dict) -> list[dict]:
    roads = []
    for el in payload.get("elements") or []:
        if el.get("type") != "way":
            continue
        geom = el.get("geometry") or []
        if len(geom) < 2:
            continue
        tags = el.get("tags") or {}
        hw = tags.get("highway")
        coords = [(float(p["lat"]), float(p["lon"])) for p in geom if "lat" in p and "lon" in p]
        if len(coords) < 2:
            continue
        lats = [c[0] for c in coords]
        lons = [c[1] for c in coords]
        lanes = tags.get("lanes")
        try:
            lanes_n = int(str(lanes).split(";")[0].split("-")[0]) if lanes else None
        except ValueError:
            lanes_n = None
        roads.append(
            {
                "name": tags.get("name") or tags.get("name:en") or tags.get("ref") or None,
                "ref": tags.get("ref"),
                "highway": hw,
                "lanes": lanes_n,
                "coords": coords,
                "min_lat": min(lats),
                "max_lat": max(lats),
                "min_lon": min(lons),
                "max_lon": max(lons),
            }
        )
    return roads



GEOFABRIK_SHP_URL = "https://download.geofabrik.de/asia/thailand-latest-free.shp.zip"
GEOFABRIK_ZIP = "thailand-latest-free.shp.zip"

# Geofabrik GIS "fclass" values we care about (see their OSM GIS format PDF).
POI_GROUPS = {
    "fuel": {"fuel"},
    "ev": {"charging_station"},
    "mall": {"mall", "department_store", "wholesale"},
    "supermarket": {"supermarket"},
    "convenience": {"convenience"},
    "hospital": {"hospital"},
    "school": {"school", "university", "college"},
    "restaurant": {"restaurant", "fast_food", "cafe"},
    "attraction": {"attraction", "theme_park", "zoo", "museum", "monument", "viewpoint"},
    "hotel": {"hotel", "motel", "guest_house"},
}
ROAD_FCLASS = {
    "motorway", "motorway_link", "trunk", "trunk_link",
    "primary", "primary_link", "secondary", "secondary_link", "tertiary", "tertiary_link",
}


def _download_geofabrik_zip() -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    dest = CACHE / GEOFABRIK_ZIP
    if dest.exists() and dest.stat().st_size > 1_000_000:
        log(f"[osm] using cached Geofabrik zip {dest} ({dest.stat().st_size:,} bytes)")
        return dest
    log(f"[osm] downloading Geofabrik shapefile extract ({GEOFABRIK_SHP_URL}) …")
    req = urllib.request.Request(GEOFABRIK_SHP_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=600) as resp, open(dest, "wb") as out:
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)
    log(f"[osm] downloaded {dest} ({dest.stat().st_size:,} bytes)")
    return dest


def _extract_geofabrik(zip_path: Path) -> Path:
    import zipfile
    dest = CACHE / "geofabrik_shp"
    needed_prefixes = (
        "gis_osm_pois_free_1",
        "gis_osm_pois_a_free_1",
        "gis_osm_roads_free_1",
        "gis_osm_landuse_a_free_1",
        "gis_osm_places_free_1",
        "gis_osm_traffic_free_1",
        "gis_osm_traffic_a_free_1",
    )
    dest.mkdir(parents=True, exist_ok=True)
    have = {p.stem for p in dest.glob("gis_osm_*")}
    if all(any(h.startswith(pref) for h in have) or any(dest.glob(pref + ".*")) for pref in needed_prefixes):
        # Require the .shp for each prefix
        if all((dest / f"{pref}.shp").exists() for pref in needed_prefixes):
            return dest
    log(f"[osm] extracting needed shapefiles into {dest}")
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        for name in names:
            base = Path(name).name
            if any(base.startswith(pref) for pref in needed_prefixes):
                target = dest / base
                if not target.exists():
                    with zf.open(name) as src, open(target, "wb") as out:
                        out.write(src.read())
    return dest


def _shp_field_map(reader) -> dict:
    # pyshp fields: [name, type, size, decimal], first entry is DeletionFlag
    return {f[0].lower(): i for i, f in enumerate(reader.fields[1:])}


def _iter_shape_records(reader):
    """Yield shape+record pairs, skipping empty or unreadable geometries."""
    import shapefile as _sf
    n = len(reader)
    for i in range(n):
        try:
            yield reader.shapeRecord(i)
        except _sf.ShapefileException:
            continue
        except Exception:
            continue


def _load_geofabrik_layers() -> dict:
    try:
        import shapefile
    except ImportError as e:
        raise RuntimeError(
            "Overpass is unreachable and pyshp is not installed. "
            "pip install pyshp (see pipeline/requirements.txt) to use the Geofabrik fallback."
        ) from e

    dest = _extract_geofabrik(_download_geofabrik_zip())
    layers = {k: [] for k in (
        "fuel", "ev", "mall", "supermarket", "convenience",
        "hospital", "school", "restaurant", "attraction", "hotel",
        "industrial", "town", "roads",
    )}

    def rec_point(lat, lon, name, fclass):
        return {
            "lat": float(lat),
            "lon": float(lon),
            "name": name or fclass,
            "brand": None,
            "osm_id": None,
            "tags": {"fclass": fclass} if fclass else {},
        }

    # Point POIs
    pois = dest / "gis_osm_pois_free_1.shp"
    if pois.exists():
        r = shapefile.Reader(str(pois), encoding="utf-8")
        fmap = _shp_field_map(r)
        i_name, i_class = fmap.get("name"), fmap.get("fclass")
        n = 0
        for sr in _iter_shape_records(r):
            shape, rec = sr.shape, sr.record
            if not shape.points:
                continue
            lon, lat = shape.points[0]
            fclass = (rec[i_class] if i_class is not None else "") or ""
            name = rec[i_name] if i_name is not None else ""
            for key, classes in POI_GROUPS.items():
                if fclass in classes:
                    layers[key].append(rec_point(lat, lon, name, fclass))
                    break
            n += 1
        log(f"[osm] geofabrik POIs scanned: {n}")

    # Fuel stations are in the Geofabrik "traffic" shapefile (not the generic POI file).
    def _load_points_from(shp_name, wanted, dest_key, area=False):
        path = dest / shp_name
        if not path.exists():
            return 0
        r = shapefile.Reader(str(path), encoding="utf-8")
        fmap = _shp_field_map(r)
        i_name, i_class = fmap.get("name"), fmap.get("fclass")
        added = 0
        for sr in _iter_shape_records(r):
            shape, rec = sr.shape, sr.record
            if not shape.points:
                continue
            fclass = (rec[i_class] if i_class is not None else "") or ""
            if fclass not in wanted:
                continue
            if area:
                lons = [p[0] for p in shape.points]
                lats = [p[1] for p in shape.points]
                lon, lat = sum(lons) / len(lons), sum(lats) / len(lats)
            else:
                lon, lat = shape.points[0]
            name = rec[i_name] if i_name is not None else fclass
            layers[dest_key].append(rec_point(lat, lon, name, fclass))
            added += 1
        return added

    n_fuel = _load_points_from("gis_osm_traffic_free_1.shp", {"fuel"}, "fuel", area=False)
    n_fuel_a = _load_points_from("gis_osm_traffic_a_free_1.shp", {"fuel"}, "fuel", area=True)
    # Dedupe polygon centroids that sit on an already-loaded fuel node (~75 m).
    if n_fuel and n_fuel_a:
        nodes = layers["fuel"][:n_fuel]
        extras = []
        for p in layers["fuel"][n_fuel:]:
            if any(abs(p["lat"] - q["lat"]) < 0.0007 and abs(p["lon"] - q["lon"]) < 0.0007 for q in nodes):
                continue
            extras.append(p)
        layers["fuel"] = nodes + extras
    log(f"[osm] geofabrik fuel points {n_fuel}, area {n_fuel_a}, after dedupe {len(layers['fuel'])}")

    # Area POIs (malls, some attractions) — use shape centroid
    pois_a = dest / "gis_osm_pois_a_free_1.shp"
    if pois_a.exists():
        r = shapefile.Reader(str(pois_a), encoding="utf-8")
        fmap = _shp_field_map(r)
        i_name, i_class = fmap.get("name"), fmap.get("fclass")
        for sr in _iter_shape_records(r):
            shape, rec = sr.shape, sr.record
            if not shape.points:
                continue
            lons = [p[0] for p in shape.points]
            lats = [p[1] for p in shape.points]
            lon, lat = sum(lons) / len(lons), sum(lats) / len(lats)
            fclass = (rec[i_class] if i_class is not None else "") or ""
            name = rec[i_name] if i_name is not None else ""
            for key, classes in POI_GROUPS.items():
                if fclass in classes:
                    layers[key].append(rec_point(lat, lon, name, fclass))
                    break

    # Landuse industrial
    land = dest / "gis_osm_landuse_a_free_1.shp"
    if land.exists():
        r = shapefile.Reader(str(land), encoding="utf-8")
        fmap = _shp_field_map(r)
        i_name, i_class = fmap.get("name"), fmap.get("fclass")
        for sr in _iter_shape_records(r):
            rec, shape = sr.record, sr.shape
            fclass = (rec[i_class] if i_class is not None else "") or ""
            if fclass != "industrial" or not shape.points:
                continue
            lons = [p[0] for p in shape.points]
            lats = [p[1] for p in shape.points]
            name = rec[i_name] if i_name is not None else "Industrial area"
            layers["industrial"].append(rec_point(sum(lats) / len(lats), sum(lons) / len(lons), name, "industrial"))

    # Towns / cities
    places = dest / "gis_osm_places_free_1.shp"
    if places.exists():
        r = shapefile.Reader(str(places), encoding="utf-8")
        fmap = _shp_field_map(r)
        i_name, i_class = fmap.get("name"), fmap.get("fclass")
        for sr in _iter_shape_records(r):
            rec, shape = sr.record, sr.shape
            fclass = (rec[i_class] if i_class is not None else "") or ""
            if fclass not in ("city", "town") or not shape.points:
                continue
            lon, lat = shape.points[0]
            name = rec[i_name] if i_name is not None else fclass
            layers["town"].append(rec_point(lat, lon, name, fclass))

    # Major roads
    roads_path = dest / "gis_osm_roads_free_1.shp"
    if roads_path.exists():
        r = shapefile.Reader(str(roads_path), encoding="utf-8")
        fmap = _shp_field_map(r)
        i_name, i_class, i_ref = fmap.get("name"), fmap.get("fclass"), fmap.get("ref")
        n = 0
        kept = 0
        for sr in _iter_shape_records(r):
            n += 1
            if n % 250000 == 0:
                log(f"[osm] roads scanned {n:,} (kept {kept:,}) …")
            rec, shape = sr.record, sr.shape
            fclass = (rec[i_class] if i_class is not None else "") or ""
            if fclass not in ROAD_FCLASS or len(shape.points) < 2:
                continue
            coords = [(p[1], p[0]) for p in shape.points]  # lat, lon
            lats = [c[0] for c in coords]
            lons = [c[1] for c in coords]
            layers["roads"].append(
                {
                    "name": rec[i_name] if i_name is not None else None,
                    "ref": rec[i_ref] if i_ref is not None else None,
                    "highway": fclass,
                    "lanes": None,  # not present in the free Geofabrik shapefile
                    "coords": coords,
                    "min_lat": min(lats),
                    "max_lat": max(lats),
                    "min_lon": min(lons),
                    "max_lon": max(lons),
                }
            )
            kept += 1
        log(f"[osm] geofabrik roads scanned: {n}, major kept: {kept}")

    for k, v in layers.items():
        if k != "roads":
            log(f"[osm] {k}: {len(v)} points")
        else:
            log(f"[osm] roads: {len(v)} ways")
    return layers



def load_osm_layers() -> dict:
    dest = CACHE / "geofabrik_shp"
    if (dest / "gis_osm_pois_free_1.shp").exists() and (dest / "gis_osm_roads_free_1.shp").exists():
        log("[osm] using extracted Geofabrik shapefiles")
        return _load_geofabrik_layers()
    try:
        return _load_overpass_layers()
    except Exception as e:
        log(f"[osm] Overpass path failed ({type(e).__name__}: {e}); falling back to Geofabrik shapefile extract.")
        return _load_geofabrik_layers()


def _load_overpass_layers() -> dict:
    s, w, n, e = TH_BBOX
    bbox = f"{s},{w},{n},{e}"
    layers = {}

    fuel_q = f'[out:json][timeout:180];(nwr["amenity"="fuel"]({bbox}););out center;'
    layers["fuel"] = _elements_to_points(_overpass(fuel_q, "osm_fuel.json"), "Fuel station")

    ev_q = f'[out:json][timeout:180];(nwr["amenity"="charging_station"]({bbox}););out center;'
    layers["ev"] = _elements_to_points(_overpass(ev_q, "osm_ev.json"), "EV charger")

    shop_q = f"""[out:json][timeout:180];(
      nwr["shop"~"^(supermarket|mall|department_store|wholesale)$"]({bbox});
      nwr["shop"="convenience"]({bbox});
    );out center;"""
    shops = _elements_to_points(_overpass(shop_q, "osm_shops.json"))
    layers["mall"] = [p for p in shops if (p.get("tags") or {}).get("shop") in ("mall", "department_store", "wholesale")]
    layers["supermarket"] = [p for p in shops if (p.get("tags") or {}).get("shop") == "supermarket"]
    layers["convenience"] = [p for p in shops if (p.get("tags") or {}).get("shop") == "convenience"]

    amenity_q = f"""[out:json][timeout:180];(
      nwr["amenity"~"^(hospital|university|college)$"]({bbox});
      nwr["amenity"="school"]({bbox});
      nwr["amenity"~"^(restaurant|fast_food)$"]({bbox});
    );out center;"""
    try:
        am = _elements_to_points(_overpass(amenity_q, "osm_amenities.json"))
    except Exception as e:
        log(f"[osm] amenities query failed ({e}); retrying without restaurants")
        amenity_q = f"""[out:json][timeout:180];(
          nwr["amenity"~"^(hospital|university|college|school)$"]({bbox});
        );out center;"""
        am = _elements_to_points(_overpass(amenity_q, "osm_amenities_core.json"))
    layers["hospital"] = [p for p in am if (p.get("tags") or {}).get("amenity") == "hospital"]
    layers["school"] = [p for p in am if (p.get("tags") or {}).get("amenity") in ("school", "university", "college")]
    layers["restaurant"] = [p for p in am if (p.get("tags") or {}).get("amenity") in ("restaurant", "fast_food")]

    tour_q = f"""[out:json][timeout:180];(
      nwr["tourism"~"^(attraction|theme_park|zoo|museum|hotspot)$"]({bbox});
      nwr["tourism"="hotel"]({bbox});
    );out center;"""
    tours = _elements_to_points(_overpass(tour_q, "osm_tourism.json"))
    layers["attraction"] = [p for p in tours if (p.get("tags") or {}).get("tourism") in ("attraction", "theme_park", "zoo", "museum")]
    layers["hotel"] = [p for p in tours if (p.get("tags") or {}).get("tourism") == "hotel"]

    ind_q = f"""[out:json][timeout:180];(
      nwr["landuse"="industrial"]({bbox});
      nwr["industrial"]({bbox});
    );out center;"""
    layers["industrial"] = _elements_to_points(_overpass(ind_q, "osm_industrial.json"), "Industrial area")

    # Markets / town centres as demand proxies
    place_q = f'[out:json][timeout:120];(nwr["place"~"^(city|town)$"]({bbox}););out center;'
    layers["town"] = _elements_to_points(_overpass(place_q, "osm_towns.json"))

    road_q = f'[out:json][timeout:240];way["highway"~"^({ROAD_CLASSES})$"]({bbox});out tags geom;'
    try:
        layers["roads"] = _ways_to_roads(_overpass(road_q, "osm_roads.json"))
    except Exception as e:
        log(f"[osm] full road extract failed ({e}); trying motorway/trunk/primary only")
        road_q = f'[out:json][timeout:240];way["highway"~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link)$"]({bbox});out tags geom;'
        layers["roads"] = _ways_to_roads(_overpass(road_q, "osm_roads_major.json"))

    for k, v in layers.items():
        if k != "roads":
            log(f"[osm] {k}: {len(v)} points")
        else:
            log(f"[osm] roads: {len(v)} ways")
    return layers


def flag_shared_coordinates(listings: list[dict]) -> None:
    groups = defaultdict(list)
    for rec in listings:
        c = (rec.get("coordinates") or {}).get("value")
        if not c:
            continue
        key = (round(float(c["lat"]), 5), round(float(c["lon"]), 5))
        groups[key].append(rec)
    for key, recs in groups.items():
        if len(recs) < 3:
            continue
        note = (
            f"{len(recs)} listings share this exact published point, so it is treated as an "
            "area / locality centroid rather than a surveyed parcel location."
        )
        for rec in recs:
            field = rec["coordinates"]
            field["status"] = "estimated"
            field["precision"] = "area_centroid"
            field["note"] = note
            field["shared_count"] = len(recs)
    # Unique or pairs keep listing-published status, with a precision tag.
    for rec in listings:
        field = rec.get("coordinates") or {}
        if field.get("value") and "precision" not in field:
            field["precision"] = "listing"
            field["status"] = field.get("status") or "verified"


def _nominatim_geocode(query: str, cache: dict) -> Optional[dict]:
    if query in cache:
        return cache[query]
    params = urllib.parse.urlencode(
        {
            "q": query,
            "format": "jsonv2",
            "limit": 1,
            "countrycodes": "th",
            "addressdetails": 1,
        }
    )
    url = f"{NOMINATIM}?{params}"
    time.sleep(1.1)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log(f"[nominatim] failed for {query!r}: {e}")
        cache[query] = None
        return None
    if not data:
        cache[query] = None
        return None
    hit = data[0]
    rec = {
        "lat": float(hit["lat"]),
        "lon": float(hit["lon"]),
        "display_name": hit.get("display_name"),
        "osm_type": hit.get("osm_type"),
        "class": hit.get("class"),
        "type": hit.get("type"),
    }
    cache[query] = rec
    return rec


def geocode_missing(listings: list[dict]) -> None:
    """Only geocode when subdistrict + district + province are present (precise enough)."""
    cache_path = CACHE / "nominatim.json"
    cache = json.loads(cache_path.read_text("utf-8")) if cache_path.exists() else {}
    n = 0
    for rec in listings:
        if (rec.get("coordinates") or {}).get("value"):
            continue
        sub = rec.get("subdistrict")
        dist = rec.get("district")
        prov = rec.get("province")
        if not (sub and dist and prov):
            # Not precise enough — leave as Data not available.
            continue
        query = f"{sub}, {dist}, {prov}, Thailand"
        hit = _nominatim_geocode(query, cache)
        n += 1
        if not hit:
            continue
        rec["coordinates"] = {
            "value": {"lat": hit["lat"], "lon": hit["lon"]},
            "status": "estimated",
            "precision": "locality_geocode",
            "note": (
                "Coordinates were not published on the listing. This point is a Nominatim "
                f"centroid for “{query}” and is approximate, not a parcel survey."
            ),
            "geocode_query": query,
        }
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    log(f"[nominatim] attempted {n} geocodes (cached unique queries: {len(cache)})")


def _grid_index(roads: list[dict], cell: float = 0.15) -> dict:
    """Bucket roads by bbox cells for faster nearest-road lookup."""
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, road in enumerate(roads):
        r0 = int(math_floor(road["min_lat"] / cell))
        r1 = int(math_floor(road["max_lat"] / cell))
        c0 = int(math_floor(road["min_lon"] / cell))
        c1 = int(math_floor(road["max_lon"] / cell))
        for rr in range(r0, r1 + 1):
            for cc in range(c0, c1 + 1):
                buckets[(rr, cc)].append(i)
    return {"cell": cell, "buckets": buckets}


def math_floor(x: float) -> int:
    import math
    return math.floor(x)


def nearest_road(lat: float, lon: float, roads: list[dict], index: dict, search_km: float = 8.0) -> Optional[dict]:
    cell = index["cell"]
    # search window in degrees (~search_km)
    ddeg = search_km / 100.0
    r0 = int(math_floor((lat - ddeg) / cell))
    r1 = int(math_floor((lat + ddeg) / cell))
    c0 = int(math_floor((lon - ddeg) / cell))
    c1 = int(math_floor((lon + ddeg) / cell))
    seen = set()
    best = None
    best_d = search_km * 1000.0
    for rr in range(r0, r1 + 1):
        for cc in range(c0, c1 + 1):
            for idx in index["buckets"].get((rr, cc), ()):
                if idx in seen:
                    continue
                seen.add(idx)
                road = roads[idx]
                # bbox reject
                if road["max_lat"] + ddeg < lat or road["min_lat"] - ddeg > lat:
                    continue
                if road["max_lon"] + ddeg < lon or road["min_lon"] - ddeg > lon:
                    continue
                coords = road["coords"]
                for i in range(len(coords) - 1):
                    d = point_to_segment_m(lat, lon, coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])
                    if d < best_d:
                        best_d = d
                        best = road
    if not best:
        return None
    return {
        "name": best.get("name"),
        "ref": best.get("ref"),
        "highway": best.get("highway"),
        "lanes": best.get("lanes"),
        "distance_m": round(best_d, 1),
    }


def _intersections_near(lat, lon, roads: list[dict], index: dict, radius_m: float = 800) -> int:
    """Proxy: count distinct major-road ways within radius (not a true node intersection)."""
    cell = index["cell"]
    ddeg = (radius_m / 1000.0) / 80.0
    r0 = int(math_floor((lat - ddeg) / cell))
    r1 = int(math_floor((lat + ddeg) / cell))
    c0 = int(math_floor((lon - ddeg) / cell))
    c1 = int(math_floor((lon + ddeg) / cell))
    count = 0
    seen = set()
    for rr in range(r0, r1 + 1):
        for cc in range(c0, c1 + 1):
            for idx in index["buckets"].get((rr, cc), ()):
                if idx in seen:
                    continue
                seen.add(idx)
                road = roads[idx]
                if road["highway"] not in ("motorway", "trunk", "primary", "secondary", "motorway_link", "trunk_link", "primary_link"):
                    continue
                coords = road["coords"]
                for i in range(len(coords) - 1):
                    d = point_to_segment_m(lat, lon, coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])
                    if d <= radius_m:
                        count += 1
                        break
    return count


def enrich_listing(rec: dict, layers: dict, road_index: dict) -> None:
    rec["zoning"] = {
        "value": None,
        "status": "unavailable",
        "note": (
            "Thai city-plan (ผังเมือง) zoning is not published as an open API. "
            f"Check the official DPT city-plan viewer at {DPT_VIEWER} and confirm with the local authority. "
            "This tool does not guess zoning."
        ),
        "viewer_url": DPT_VIEWER,
    }
    rec["official_traffic_volume"] = {
        "value": None,
        "status": "unavailable",
        "note": (
            "No official Department of Highways traffic-count figure was matched to this site. "
            "Traffic potential below is a proxy index, not a vehicle count."
        ),
    }

    coords = (rec.get("coordinates") or {}).get("value")
    if not coords:
        rec["osm"] = {
            "status": "unavailable",
            "note": "Nearby roads, competitors and demand generators cannot be measured without coordinates.",
        }
        rec["road"] = {
            "name": rec.get("road_name_listing") or {"value": None, "status": "unavailable", "note": "Data not available."},
            "highway": {"value": None, "status": "unavailable", "note": "Data not available."},
            "lanes": {"value": None, "status": "unavailable", "note": "Data not available."},
            "distance_m": {"value": None, "status": "unavailable", "note": "Data not available."},
        }
        rec["competitors"] = _empty_competitors()
        rec["generators"] = _empty_generators()
        rec["traffic_proxy"] = {
            "score": None,
            "band": None,
            "status": "unavailable",
            "note": "Traffic potential cannot be estimated without a location.",
            "components": {},
        }
        return

    lat, lon = float(coords["lat"]), float(coords["lon"])
    road = nearest_road(lat, lon, layers.get("roads") or [], road_index, search_km=12.0) if layers.get("roads") else None
    listing_road = (rec.get("road_name_listing") or {}).get("value")

    if road:
        rec["road"] = {
            "name": {
                "value": listing_road or road.get("name") or road.get("ref"),
                "status": "verified" if listing_road else ("estimated" if (road.get("name") or road.get("ref")) else "unavailable"),
                "note": (
                    "Road name taken from the listing text."
                    if listing_road
                    else (
                        "Nearest OpenStreetMap highway to the published/estimated coordinates."
                        if (road.get("name") or road.get("ref"))
                        else "The nearest OSM highway has no name tag."
                    )
                ),
            },
            "highway": {
                "value": _highway_group(road.get("highway")),
                "osm_value": road.get("highway"),
                "status": "estimated",
                "note": "OpenStreetMap highway class of the nearest major road.",
            },
            "lanes": {
                "value": road.get("lanes"),
                "status": "estimated" if road.get("lanes") else "unavailable",
                "note": "OpenStreetMap lanes tag on the nearest major road. Missing when OSM has no lanes value."
                if road.get("lanes")
                else "OpenStreetMap has no lanes tag on the nearest major road.",
            },
            "distance_m": {
                "value": road.get("distance_m"),
                "status": "estimated",
                "note": "Straight-line distance from the site coordinates to the nearest mapped major road (not a driveway survey).",
            },
            "ref": road.get("ref"),
        }
    else:
        rec["road"] = {
            "name": rec.get("road_name_listing") or {"value": None, "status": "unavailable", "note": "Data not available."},
            "highway": {"value": None, "status": "unavailable", "note": "No major OSM road was found within 12 km."},
            "lanes": {"value": None, "status": "unavailable", "note": "Data not available."},
            "distance_m": {"value": None, "status": "unavailable", "note": "Data not available."},
        }

    # Competitors
    fuel = layers.get("fuel") or []
    stations_10 = nearest_points(lat, lon, fuel, 10.0, limit=40)
    rec["competitors"] = {
        "status": "estimated",
        "note": "Existing stations from OpenStreetMap (amenity=fuel). Counts depend on OSM completeness and may miss or include outdated sites.",
        "km1": _bucket(stations_10, 1.0, 10),
        "km3": _bucket(stations_10, 3.0, 12),
        "km5": _bucket(stations_10, 5.0, 15),
        "km10": _bucket(stations_10, 10.0, 15),
    }

    # Demand generators
    def pack(key, radius, limit, label):
        pts = nearest_points(lat, lon, layers.get(key) or [], radius, limit=limit)
        return {
            "count": len(pts) if radius >= 10 or True else len(pts),
            "items": [
                {"name": p.get("name") or label, "brand": p.get("brand"), "distance_km": p["distance_km"]}
                for p in pts
            ],
        }

    # counts within 5 km (and 10 km for industrial / towns)
    rec["generators"] = {
        "status": "estimated",
        "note": "Nearby places from OpenStreetMap. Completeness varies by area.",
        "industrial_10km": pack("industrial", 10.0, 8, "Industrial area"),
        "malls_5km": pack("mall", 5.0, 8, "Mall"),
        "supermarkets_5km": pack("supermarket", 5.0, 8, "Supermarket"),
        "convenience_3km": pack("convenience", 3.0, 8, "Convenience store"),
        "restaurants_3km": pack("restaurant", 3.0, 8, "Restaurant"),
        "ev_chargers_5km": pack("ev", 5.0, 8, "EV charger"),
        "schools_5km": pack("school", 5.0, 8, "School"),
        "hospitals_5km": pack("hospital", 5.0, 6, "Hospital"),
        "attractions_10km": pack("attraction", 10.0, 8, "Attraction"),
        "hotels_5km": pack("hotel", 5.0, 8, "Hotel"),
        "towns_10km": pack("town", 10.0, 6, "Town"),
    }
    # Restore true counts (nearest_points is capped). Recompute counts only.
    rec["generators"]["convenience_3km"]["count_capped"] = True
    rec["generators"]["restaurants_3km"]["count_capped"] = True

    inter = _intersections_near(lat, lon, layers.get("roads") or [], road_index, 800) if layers.get("roads") else 0
    rec["intersection_proxy"] = {
        "major_roads_within_800m": inter,
        "status": "estimated",
        "note": "Count of distinct major OSM ways (motorway/trunk/primary/secondary) within 800 m — a proxy for intersections and access, not a surveyed junction or U-turn inventory.",
    }

    rec["traffic_proxy"] = build_traffic_proxy(rec)
    rec["osm"] = {"status": "estimated", "note": "OpenStreetMap overlay computed around the site coordinates.", "retrieved_at": now_iso()}


def _highway_group(hw: Optional[str]) -> Optional[str]:
    if not hw:
        return None
    if hw.startswith("motorway"):
        return "motorway"
    if hw.startswith("trunk"):
        return "trunk"
    if hw.startswith("primary"):
        return "primary"
    if hw.startswith("secondary"):
        return "secondary"
    if hw.startswith("tertiary"):
        return "tertiary"
    return "other"


def _bucket(stations: list[dict], radius: float, limit: int) -> dict:
    inside = [s for s in stations if s["distance_km"] <= radius + 1e-9]
    return {
        "count": len(inside),
        "stations": [
            {
                "name": s.get("name") or "Fuel station",
                "brand": s.get("brand"),
                "distance_km": s["distance_km"],
                "lat": s.get("lat"),
                "lon": s.get("lon"),
            }
            for s in inside[:limit]
        ],
    }


def _empty_competitors() -> dict:
    empty = {"count": None, "stations": []}
    return {
        "status": "unavailable",
        "note": "Competition cannot be measured without coordinates.",
        "km1": dict(empty),
        "km3": dict(empty),
        "km5": dict(empty),
        "km10": dict(empty),
    }


def _empty_generators() -> dict:
    return {
        "status": "unavailable",
        "note": "Demand generators cannot be measured without coordinates.",
    }


def build_traffic_proxy(rec: dict) -> dict:
    """0-100 proxy. Never presented as an official vehicle count."""
    components = {}
    road = rec.get("road") or {}
    hw = (road.get("highway") or {}).get("value")
    lanes = (road.get("lanes") or {}).get("value")
    dist = (road.get("distance_m") or {}).get("value")
    inter = (rec.get("intersection_proxy") or {}).get("major_roads_within_800m")
    gen = rec.get("generators") or {}

    class_score = {
        "motorway": 98,
        "trunk": 90,
        "primary": 78,
        "secondary": 62,
        "tertiary": 44,
        "other": 30,
    }.get(hw)
    components["road_class"] = class_score

    if lanes:
        if lanes >= 6:
            components["lanes"] = 90
        elif lanes >= 4:
            components["lanes"] = 80
        elif lanes >= 3:
            components["lanes"] = 70
        elif lanes == 2:
            components["lanes"] = 55
        else:
            components["lanes"] = 35
    else:
        components["lanes"] = None

    if dist is not None:
        if dist <= 30:
            components["proximity"] = 95
        elif dist <= 80:
            components["proximity"] = 80
        elif dist <= 200:
            components["proximity"] = 60
        elif dist <= 500:
            components["proximity"] = 40
        elif dist <= 2000:
            components["proximity"] = 22
        else:
            components["proximity"] = 8
    else:
        components["proximity"] = None

    if inter is not None:
        components["intersections"] = min(90, 30 + inter * 15)
    else:
        components["intersections"] = None

    # Demand activity around the site
    def c(path, default=0):
        node = gen.get(path) or {}
        return node.get("count") if node.get("count") is not None else default

    activity = 0
    activity += min(25, (c("industrial_10km") or 0) * 8)
    activity += min(15, (c("malls_5km") or 0) * 6)
    activity += min(10, (c("supermarkets_5km") or 0) * 3)
    activity += min(8, min(c("convenience_3km") or 0, 8))
    activity += min(8, min(c("restaurants_3km") or 0, 10) * 0.6)
    activity += min(10, (c("attractions_10km") or 0) * 4 + (c("hotels_5km") or 0) * 1.5)
    activity += min(8, (c("schools_5km") or 0) * 1.2 + (c("hospitals_5km") or 0) * 3)
    activity += min(8, (c("towns_10km") or 0) * 3)
    components["activity"] = min(90, 10 + activity)

    present = [v for k, v in components.items() if v is not None]
    if not present or class_score is None and components["proximity"] is None:
        return {
            "score": None,
            "band": None,
            "status": "unavailable",
            "note": "Not enough location or road data to build a traffic proxy.",
            "components": components,
        }

    # Weighted blend of available components; missing ones are skipped (not invented).
    weights = {
        "road_class": 0.40,
        "lanes": 0.10,
        "proximity": 0.15,
        "intersections": 0.10,
        "activity": 0.25,
    }
    num = den = 0.0
    for k, w in weights.items():
        if components[k] is not None:
            num += components[k] * w
            den += w
    score = round(num / den, 1) if den else None
    band = None
    if score is not None:
        band = "high" if score >= 70 else "medium" if score >= 45 else "low"
    return {
        "score": score,
        "band": band,
        "status": "estimated",
        "note": (
            "Proxy index from OpenStreetMap road class, lanes (if tagged), distance to a major road, "
            "nearby major roads, and nearby industrial / commercial / institutional activity. "
            "This is not an official traffic count."
        ),
        "components": components,
    }


def enrich(listings: list[dict], skip_geocode: bool = False) -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    flag_shared_coordinates(listings)
    if not skip_geocode:
        geocode_missing(listings)
        flag_shared_coordinates(listings)
    layers = load_osm_layers()
    road_index = _grid_index(layers.get("roads") or []) if layers.get("roads") else {"cell": 0.15, "buckets": {}}
    for i, rec in enumerate(listings, 1):
        enrich_listing(rec, layers, road_index)
        if i % 100 == 0:
            log(f"[enrich] {i}/{len(listings)}")
    log(f"[enrich] done {len(listings)} listings")
    return listings
