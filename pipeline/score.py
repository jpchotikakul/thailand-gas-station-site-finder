"""Configurable 0-100 suitability model.

Default weights (must sum to 100):
  traffic 30, road_access 20, land_size 15, competition 15, demand 10, price_value 10

Missing-factor rule (documented, not invented):
  * If a factor can be computed from published or OSM-derived inputs, use that 0-100 score
    and mark the factor "computed".
  * If the factor is location-dependent and coordinates are missing, use 35 (penalized) and
    mark the factor "imputed_penalty".
  * If the factor is not location-dependent but an input is missing (e.g. no asking price),
    use 50 (neutral) and mark the factor "imputed_neutral".
  Overall score is the weighted average of all six factors (imputed values included so the
  weights still add to 100). Completeness is the share of weight that came from computed
  factors, not imputations. The UI exposes both numbers and lets users change the weights.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

DEFAULT_WEIGHTS = {
    "traffic": 30,
    "road_access": 20,
    "land_size": 15,
    "competition": 15,
    "demand": 10,
    "price_value": 10,
}

FACTOR_LABELS = {
    "traffic": "Traffic potential",
    "road_access": "Road access & visibility",
    "land_size": "Land size & suitability",
    "competition": "Competition",
    "demand": "Surrounding demand generators",
    "price_value": "Land price / value",
}


def _has_coords(rec: dict) -> bool:
    return bool((rec.get("coordinates") or {}).get("value"))


def score_land_size(rec: dict) -> tuple[Optional[float], str, str]:
    area = (rec.get("area_rai") or {}).get("value")
    if area is None:
        area_sqm = (rec.get("area_sqm") or {}).get("value")
        if area_sqm:
            area = area_sqm / 1600.0
    if area is None:
        return 50.0, "imputed_neutral", "Land area was not stated, so this factor is scored as neutral (50)."
    # Typical Thai petrol station plots are about 0.5–5 rai; a larger service plaza may use more.
    if area < 0.25:
        s, why = 18, "Under 0.25 rai — usually too small for a standard station."
    elif area < 0.5:
        s, why = 42, "0.25–0.5 rai — tight for a standard station, possible for a small plot."
    elif area < 1:
        s, why = 72, "0.5–1 rai — workable for a compact station."
    elif area <= 4:
        s, why = 95, "1–4 rai — a typical size for a petrol / service station."
    elif area <= 10:
        s, why = 88, "4–10 rai — suitable for a larger service plaza."
    elif area <= 25:
        s, why = 74, "10–25 rai — usable, though larger than a typical station (may allow extra retail)."
    elif area <= 80:
        s, why = 55, "25–80 rai — a large holding; only part of the plot may be needed."
    else:
        s, why = 42, "Over 80 rai — very large / likely agricultural; treat as a land bank, not a single station plot."
    return float(s), "computed", why


def score_traffic(rec: dict) -> tuple[Optional[float], str, str]:
    proxy = rec.get("traffic_proxy") or {}
    if proxy.get("score") is None:
        if not _has_coords(rec):
            return 35.0, "imputed_penalty", "No coordinates, so traffic potential cannot be estimated. Factor scored 35 (penalty), not a traffic count."
        return 35.0, "imputed_penalty", "A traffic proxy could not be built. Factor scored 35 (penalty)."
    return float(proxy["score"]), "computed", proxy.get("note") or "OSM-based traffic proxy."


def score_road(rec: dict) -> tuple[float, str, str]:
    if not _has_coords(rec):
        # A listing-stated road name alone is not enough to score access.
        if (rec.get("road_name_listing") or {}).get("value"):
            return 55.0, "imputed_neutral", "A road is named on the listing but access cannot be measured without coordinates. Neutral 55."
        return 35.0, "imputed_penalty", "No coordinates and no stated road access. Factor scored 35 (penalty)."
    road = rec.get("road") or {}
    hw = (road.get("highway") or {}).get("value")
    dist = (road.get("distance_m") or {}).get("value")
    lanes = (road.get("lanes") or {}).get("value")
    frontage = (rec.get("frontage_m") or {}).get("value")
    if hw is None and dist is None:
        return 35.0, "imputed_penalty", "No major road was found near the coordinates. Factor scored 35 (penalty)."

    class_s = {
        "motorway": 80,  # high traffic but access may be restricted — slightly below trunk
        "trunk": 92,
        "primary": 84,
        "secondary": 68,
        "tertiary": 48,
        "other": 32,
    }.get(hw, 50)
    if dist is None:
        prox = 50
    elif dist <= 25:
        prox = 96
    elif dist <= 60:
        prox = 85
    elif dist <= 150:
        prox = 70
    elif dist <= 400:
        prox = 50
    elif dist <= 1500:
        prox = 28
    else:
        prox = 12
    parts = [class_s * 0.55, prox * 0.35]
    den = 0.90
    note_bits = [f"nearest OSM road class={hw or 'unknown'}", f"distance={dist if dist is not None else 'n/a'} m"]
    if lanes:
        lane_s = 90 if lanes >= 4 else 75 if lanes >= 3 else 60 if lanes == 2 else 40
        parts.append(lane_s * 0.05)
        den += 0.05
        note_bits.append(f"lanes={lanes}")
    if frontage:
        front_s = 95 if frontage >= 40 else 80 if frontage >= 25 else 65 if frontage >= 15 else 45
        parts.append(front_s * 0.10)
        den += 0.10
        note_bits.append(f"frontage={frontage} m (from listing)")
    score = sum(parts) / den
    return round(score, 1), "computed", "Road access from OSM (and listing frontage when stated). " + "; ".join(note_bits) + "."


def score_competition(rec: dict) -> tuple[float, str, str]:
    comp = rec.get("competitors") or {}
    if comp.get("status") == "unavailable" or not _has_coords(rec):
        return 35.0, "imputed_penalty", "Competition cannot be measured without coordinates. Factor scored 35 (penalty)."
    n1 = (comp.get("km1") or {}).get("count")
    n3 = (comp.get("km3") or {}).get("count")
    n5 = (comp.get("km5") or {}).get("count")
    n10 = (comp.get("km10") or {}).get("count")
    if n1 is None:
        return 35.0, "imputed_penalty", "Competitor counts are unavailable. Factor scored 35 (penalty)."

    # Higher score = more attractive (less cannibalisation, but not a total void).
    if n1 >= 4:
        s = 18
        why = f"{n1} stations already within 1 km — heavy immediate competition."
    elif n1 == 3:
        s = 28
        why = "3 stations within 1 km — crowded."
    elif n1 == 2:
        s = 40
        why = "2 stations within 1 km — notable competition."
    elif n1 == 1:
        s = 58
        why = "1 station within 1 km — some competition on the doorstep."
    else:
        # none within 1 km
        if (n3 or 0) == 0 and (n5 or 0) == 0:
            demand = rec.get("demand_score_hint")
            s = 48
            why = "No OSM fuel stations within 5 km. That can mean a gap or a very quiet location — check demand generators."
        elif (n3 or 0) == 0:
            s = 80
            why = "No station within 3 km, some within 5–10 km — a possible local gap."
        elif n3 <= 2:
            s = 86
            why = f"No station within 1 km and only {n3} within 3 km — relatively open."
        elif n3 <= 4:
            s = 70
            why = f"No station within 1 km, {n3} within 3 km — moderate."
        else:
            s = 52
            why = f"No station within 1 km, but {n3} within 3 km — the corridor is already served."
    if (n10 or 0) >= 15 and s > 40:
        s -= 8
        why += f" ({n10} stations within 10 km.)"
    return float(max(10, min(95, s))), "computed", why + " Counts are from OpenStreetMap and may be incomplete."


def score_demand(rec: dict) -> tuple[float, str, str]:
    gen = rec.get("generators") or {}
    if gen.get("status") == "unavailable" or not _has_coords(rec):
        return 35.0, "imputed_penalty", "Demand generators cannot be measured without coordinates. Factor scored 35 (penalty)."

    def c(key):
        return ((gen.get(key) or {}).get("count") or 0)

    raw = 0.0
    raw += min(28, c("industrial_10km") * 9)
    raw += min(16, c("malls_5km") * 7)
    raw += min(10, c("supermarkets_5km") * 3)
    raw += min(8, min(c("convenience_3km"), 10) * 0.8)
    raw += min(8, min(c("restaurants_3km"), 15) * 0.5)
    raw += min(8, c("ev_chargers_5km") * 3)
    raw += min(10, c("schools_5km") * 1.1 + c("hospitals_5km") * 3)
    raw += min(12, c("attractions_10km") * 4 + c("hotels_5km") * 1.2)
    raw += min(10, c("towns_10km") * 3)
    # 0 raw -> 20 (isolated); strong cluster -> ~90
    s = min(92, 18 + raw)
    why = (
        f"OSM nearby: industrial {c('industrial_10km')} (10 km), malls {c('malls_5km')}, "
        f"towns {c('towns_10km')}, schools {c('schools_5km')}, hospitals {c('hospitals_5km')}, "
        f"attractions {c('attractions_10km')}."
    )
    return float(round(s, 1)), "computed", why


def provincial_medians(listings: list[dict]) -> tuple[dict[str, float], Optional[float]]:
    buckets: dict[str, list[float]] = defaultdict(list)
    all_p = []
    for rec in listings:
        ppr = (rec.get("price_per_rai") or {}).get("value")
        if not ppr:
            continue
        all_p.append(ppr)
        prov = rec.get("province") or "_unknown"
        buckets[prov].append(ppr)

    def median(vals: list[float]) -> float:
        vals = sorted(vals)
        mid = len(vals) // 2
        if len(vals) % 2:
            return vals[mid]
        return (vals[mid - 1] + vals[mid]) / 2.0

    meds = {k: median(v) for k, v in buckets.items() if len(v) >= 3}
    national = median(all_p) if len(all_p) >= 5 else None
    return meds, national


def score_price(rec: dict, meds: dict[str, float], national: Optional[float]) -> tuple[float, str, str]:
    ppr = (rec.get("price_per_rai") or {}).get("value")
    if not ppr:
        return 50.0, "imputed_neutral", "Price per rai is unknown, so this factor is scored as neutral (50)."
    prov = rec.get("province")
    baseline = meds.get(prov) if prov else None
    source = f"the median asking price per rai in {prov} in this dataset"
    if baseline is None:
        baseline = national
        source = "the national median asking price per rai in this dataset"
    if not baseline:
        return 50.0, "imputed_neutral", "Not enough priced listings to compare value. Neutral 50."
    ratio = ppr / baseline  # <1 cheaper than typical
    # Cheaper than median = higher value score (better entry cost). Very cheap may be a location discount.
    if ratio <= 0.4:
        s = 90
    elif ratio <= 0.7:
        s = 82
    elif ratio <= 0.9:
        s = 72
    elif ratio <= 1.1:
        s = 60
    elif ratio <= 1.4:
        s = 48
    elif ratio <= 2.0:
        s = 35
    else:
        s = 22
    why = (
        f"Asking {ppr:,.0f} THB/rai vs {source} ({baseline:,.0f} THB/rai), ratio {ratio:.2f}. "
        "Lower asking prices score higher on value; they are not automatically better sites."
    )
    return float(s), "computed", why


def advantages_and_risks(rec: dict) -> tuple[list[str], list[str]]:
    adv, risks = [], []
    scores = rec.get("scores") or {}
    factors = scores.get("factors") or {}

    coords = rec.get("coordinates") or {}
    if not coords.get("value"):
        risks.append("Location is not mapped — coordinates were not published and could not be geocoded precisely.")
    elif coords.get("precision") == "area_centroid":
        risks.append("Coordinates look like an area centroid (several listings share this point), not a surveyed parcel.")
    elif coords.get("precision") == "locality_geocode":
        risks.append("Coordinates are a locality geocode (estimated), not a surveyed parcel location.")

    road = rec.get("road") or {}
    hw = (road.get("highway") or {}).get("value")
    dist = (road.get("distance_m") or {}).get("value")
    if hw in ("trunk", "primary", "motorway") and dist is not None and dist <= 80:
        adv.append(f"Close to a {hw} road ({dist:.0f} m, from OpenStreetMap).")
    elif hw in ("trunk", "primary") and dist is not None and dist <= 250:
        adv.append(f"Near a {hw} road ({dist:.0f} m, from OpenStreetMap).")
    if dist is not None and dist > 2000:
        risks.append(f"About {dist/1000:.1f} km from the nearest mapped major road — access may be poor for a high-traffic station.")
    if (rec.get("frontage_m") or {}).get("value"):
        adv.append(f"Listing states road frontage of {(rec['frontage_m']['value'])} m.")
    if (rec.get("road_name_listing") or {}).get("value"):
        adv.append(f"Listing mentions {(rec['road_name_listing']['value'])}.")

    lanes = (road.get("lanes") or {}).get("value")
    if lanes and lanes >= 4:
        adv.append(f"Nearest major road is tagged in OSM with {lanes} lanes.")

    comp = rec.get("competitors") or {}
    n1 = (comp.get("km1") or {}).get("count")
    n3 = (comp.get("km3") or {}).get("count")
    if n1 == 0 and n3 is not None and n3 <= 2 and _has_coords(rec):
        adv.append("No competing OSM fuel station within 1 km, and few within 3 km.")
    if isinstance(n1, int) and n1 >= 3:
        risks.append(f"{n1} OSM fuel stations already within 1 km.")
    elif isinstance(n1, int) and n1 >= 1:
        risks.append(f"{n1} OSM fuel station(s) within 1 km.")

    gen = rec.get("generators") or {}
    if ((gen.get("industrial_10km") or {}).get("count") or 0) >= 1:
        first = ((gen.get("industrial_10km") or {}).get("items") or [{}])[0]
        name = first.get("name") or "an industrial area"
        d = first.get("distance_km")
        adv.append(f"Industrial land use nearby ({name}" + (f", {d} km" if d is not None else "") + ").")
    if ((gen.get("malls_5km") or {}).get("count") or 0) >= 1:
        adv.append("Shopping / mall uses within 5 km (OpenStreetMap).")
    if ((gen.get("towns_10km") or {}).get("count") or 0) == 0 and ((gen.get("industrial_10km") or {}).get("count") or 0) == 0:
        if _has_coords(rec):
            risks.append("Few mapped towns or industrial areas within 10 km — local demand may be thin.")

    area = (rec.get("area_rai") or {}).get("value")
    if area is not None and area < 0.5:
        risks.append(f"Plot is only {area:.2f} rai — may be tight for a standard station.")
    elif area is not None and 1 <= area <= 10:
        adv.append(f"Plot size ({area:.2f} rai) is in a typical range for a station or small service plaza.")
    elif area is not None and area > 80:
        risks.append(f"Very large plot ({area:.0f} rai) — confirm that a station is the intended use.")

    ppr = (rec.get("price_per_rai") or {}).get("value")
    pv = (factors.get("price_value") or {})
    if ppr and pv.get("status") == "computed" and (pv.get("score") or 0) >= 75:
        adv.append("Asking price per rai is below the typical level in this dataset.")
    if ppr and pv.get("status") == "computed" and (pv.get("score") or 0) <= 30:
        risks.append("Asking price per rai is high relative to this dataset.")

    if (rec.get("traffic_proxy") or {}).get("band") == "high":
        adv.append("Traffic-potential proxy is high (road class and nearby activity — not an official count).")
    if (rec.get("traffic_proxy") or {}).get("band") == "low":
        risks.append("Traffic-potential proxy is low. There is no official traffic count for this site.")

    risks.append("Zoning / city-plan (ผังเมือง) was not available; confirm land use with the local authority and a title deed (chanote).")
    # Keep lists short and unique
    def uniq(items: list[str]) -> list[str]:
        seen = set()
        out = []
        for x in items:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out
    return uniq(adv), uniq(risks)


def score_listing(rec: dict, meds: dict[str, float], national: Optional[float], weights: dict[str, float] | None = None) -> dict:
    weights = dict(weights or DEFAULT_WEIGHTS)
    total_w = sum(weights.values()) or 1.0
    # normalize to 100
    weights = {k: (v / total_w) * 100.0 for k, v in weights.items()}

    fns = {
        "traffic": lambda r: score_traffic(r),
        "road_access": lambda r: score_road(r),
        "land_size": lambda r: score_land_size(r),
        "competition": lambda r: score_competition(r),
        "demand": lambda r: score_demand(r),
        "price_value": lambda r: score_price(r, meds, national),
    }
    factors = {}
    computed_weight = 0.0
    overall = 0.0
    for key, fn in fns.items():
        val, status, note = fn(rec)
        factors[key] = {
            "label": FACTOR_LABELS[key],
            "score": None if val is None else round(float(val), 1),
            "status": status,
            "note": note,
            "weight": round(weights[key], 2),
        }
        overall += (val or 0) * weights[key]
        if status == "computed":
            computed_weight += weights[key]
    overall = round(overall / 100.0, 1)
    if overall >= 70:
        band = "high"
    elif overall >= 45:
        band = "medium"
    else:
        band = "low"
    completeness = round(computed_weight / 100.0, 3)
    rec["scores"] = {
        "overall": overall,
        "band": band,
        "completeness": completeness,
        "factors": factors,
        "weights_used": {k: round(v, 2) for k, v in weights.items()},
        "missing_rule": "imputed_penalty=35 when location data is missing; imputed_neutral=50 when a non-location input (price/area) is missing; computed factors use only stated or OSM-derived inputs.",
    }
    rec["traffic_potential"] = {
        "band": (rec.get("traffic_proxy") or {}).get("band"),
        "score": (rec.get("traffic_proxy") or {}).get("score"),
        "status": (rec.get("traffic_proxy") or {}).get("status") or "unavailable",
        "note": (rec.get("traffic_proxy") or {}).get("note") or "Data not available.",
    }
    adv, risks = advantages_and_risks(rec)
    rec["advantages"] = adv
    rec["risks"] = risks
    return rec["scores"]


def score_all(listings: list[dict], weights: dict[str, float] | None = None) -> list[dict]:
    meds, national = provincial_medians(listings)
    for rec in listings:
        score_listing(rec, meds, national, weights)
    listings.sort(key=lambda r: (-(r.get("scores") or {}).get("overall") or 0, r.get("title") or ""))
    return listings
