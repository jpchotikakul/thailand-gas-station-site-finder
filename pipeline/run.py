#!/usr/bin/env python3
"""Run the full pipeline: collect → enrich → score → write docs/data/listings.json."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.collect import CACHE, collect, now_iso, log
from pipeline.enrich import DPT_VIEWER, enrich
from pipeline.score import DEFAULT_WEIGHTS, score_all


OUT = ROOT / "docs" / "data" / "listings.json"

BLOCKED_SOURCES = [
    {
        "name": "DDproperty",
        "url": "https://www.ddproperty.com/",
        "reason": "Cloudflare managed challenge (HTTP 403). Not collected; captchas are not bypassed.",
    },
    {
        "name": "Hipflat",
        "url": "https://www.hipflat.co.th/",
        "reason": "HTTP 401 Access Denied on a public robots.txt request. Not collected.",
    },
    {
        "name": "Baania",
        "url": "https://www.baania.com/",
        "reason": "Cloudflare IP block (HTTP 403). Not collected.",
    },
    {
        "name": "Livinginsider (sitemap)",
        "url": "https://www.livinginsider.com/",
        "reason": "robots.txt allows listing pages but the sitemap was blocked by CloudFront (403) from this crawler. Not collected in this run.",
    },
    {
        "name": "Kaidee / home.co.th search APIs",
        "url": "https://www.kaidee.com/",
        "reason": "Search/API paths are disallowed in robots.txt. Individual listing harvest was not implemented for this release.",
    },
]



def compact_competitors(comp):
    if not comp:
        return comp
    seen, all_st = set(), []
    for key in ("km1", "km3", "km5", "km10"):
        for s in (comp.get(key) or {}).get("stations") or []:
            ident = (round(s.get("lat") or 0, 5), round(s.get("lon") or 0, 5), s.get("name"), s.get("distance_km"))
            if ident in seen:
                continue
            seen.add(ident)
            all_st.append({"name": s.get("name"), "brand": s.get("brand"), "distance_km": s.get("distance_km"), "lat": s.get("lat"), "lon": s.get("lon")})
    all_st.sort(key=lambda x: x.get("distance_km") or 99)
    all_st = all_st[:12]
    out = {"status": comp.get("status"), "note": comp.get("note")}
    for rad, key in ((1, "km1"), (3, "km3"), (5, "km5"), (10, "km10")):
        bucket = comp.get(key) or {}
        out[key] = {"count": bucket.get("count"), "stations": all_st if key == "km10" else []}
    return out


def compact_generators(gen):
    if not gen:
        return gen
    out = {"status": gen.get("status"), "note": gen.get("note")}
    for k, v in gen.items():
        if k in ("status", "note") or not isinstance(v, dict):
            continue
        items = [{"name": it.get("name"), "distance_km": it.get("distance_km")} for it in (v.get("items") or [])[:4]]
        out[k] = {"count": v.get("count"), "items": items}
    return out


def slim(rec: dict) -> dict:
    """Drop bulky internal-only fields before publishing."""
    photos = rec.get("photos") or []
    # Keep a few photo URLs (hotlinked from the listing CDN).
    out = {
        "id": rec.get("id"),
        "source": rec.get("source"),
        "sources": rec.get("sources") or [rec.get("source")],
        "source_url": rec.get("source_url"),
        "also_listed_at": rec.get("also_listed_at") or [],
        "title": rec.get("title"),
        "description": (rec.get("description") or "")[:600] or rec.get("description"),
        "photos": photos[:8],
        "province": rec.get("province"),
        "province_th": rec.get("province_th"),
        "district": rec.get("district"),
        "subdistrict": rec.get("subdistrict"),
        "address_text": rec.get("address_text"),
        "listed_date": rec.get("listed_date"),
        "scraped_at": rec.get("scraped_at"),
        "coordinates": rec.get("coordinates"),
        "price_thb": rec.get("price_thb"),
        "area_sqm": rec.get("area_sqm"),
        "area_rai": rec.get("area_rai"),
        "area_display": rec.get("area_display"),
        "price_per_rai": rec.get("price_per_rai"),
        "frontage_m": rec.get("frontage_m"),
        "road": rec.get("road"),
        "traffic_potential": rec.get("traffic_potential"),
        "official_traffic_volume": rec.get("official_traffic_volume"),
        "competitors": compact_competitors(rec.get("competitors")),
        "generators": compact_generators(rec.get("generators")),
        "intersection_proxy": rec.get("intersection_proxy"),
        "pin_quality": rec.get("pin_quality"),
        "zoning": rec.get("zoning"),
        "scores": rec.get("scores"),
        "advantages": rec.get("advantages"),
        "risks": rec.get("risks"),
    }
    return out


def build_meta(raw: dict, listings: list[dict]) -> dict:
    src_counts = Counter(r.get("source") for r in listings)
    provs = sorted({r.get("province") for r in listings if r.get("province")})
    with_coords = sum(1 for r in listings if (r.get("coordinates") or {}).get("value"))
    high = sum(1 for r in listings if (r.get("scores") or {}).get("band") == "high")
    suspect = sum(1 for r in listings if (r.get("pin_quality") or {}).get("suspect"))
    prices = [
        (r.get("price_per_rai") or {}).get("value")
        for r in listings
        if (r.get("price_per_rai") or {}).get("value")
    ]
    avg_ppr = round(sum(prices) / len(prices), 0) if prices else None
    return {
        "generated_at": now_iso(),
        "timezone": "Asia/Bangkok",
        "listings_count": len(listings),
        "with_coordinates": with_coords,
        "high_potential_count": high,
        "suspect_pin_count": suspect,
        "average_price_per_rai": avg_ppr,
        "sources": dict(src_counts),
        "source_notes": raw.get("source_notes") or {},
        "source_errors_sample": (raw.get("source_errors") or [])[:30],
        "blocked_sources": BLOCKED_SOURCES,
        "provinces_covered": provs,
        "province_count": len(provs),
        "default_weights": DEFAULT_WEIGHTS,
        "dpt_city_plan_viewer": DPT_VIEWER,
        "field_provenance": {
            "verified": "Taken from the public listing (title, card, description, or schema.org fields) — not used for map pins.",
            "listing_pin": "Seller-placed pin published with the listing. Approximate, not a surveyed parcel location.",
            "calculated": "Derived only from verified listing figures (for example price ÷ area).",
            "estimated": "Derived from OpenStreetMap, a locality geocode, or a documented proxy. Not a surveyed or official figure.",
            "unavailable": "Not present in the listing and not inferred. Shown as “Data not available.”",
            "imputed_neutral": "Factor scored at a neutral default (50) because a non-location input was missing.",
            "imputed_penalty": "Factor scored at a penalty default (35) because location data was missing.",
        },
        "pin_quality_method": (
            "Listing pins are compared with OpenStreetMap major-road geometry. A pin is flagged "
            "'Pin may be inaccurate' if it falls within a class-based carriageway buffer "
            "(about 8–14 m of a centre-line, or within 8 m of any major road) or within 25 m of "
            "two differently named or classed roads (a junction / interchange proxy). "
            "Derived road distances, competitor counts and demand-generator counts then carry a reduced-confidence note. "
            "This is a data-quality flag, not proof that the land is on the road."
        ),
        "traffic_method": (
            "Official Department of Highways traffic volumes were not matched to individual sites. "
            "Traffic potential is a 0–100 proxy from OSM road class, lanes (when tagged), distance to a major road, "
            "nearby major roads, and nearby industrial/commercial/institutional activity. It is labelled Estimated."
        ),
        "zoning_method": (
            f"Zoning is not guessed. See the official DPT city-plan viewer: {DPT_VIEWER}"
        ),
        "disclaimer": (
            "This is a site-selection screening tool, not investment, legal, or engineering advice. "
            "Always verify the title deed (chanote), access rights, zoning, and on-the-ground conditions "
            "with a surveyor and the local authorities before making a decision."
        ),
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--max-pages", type=int, default=3)
    p.add_argument("--delay", type=float, default=1.25)
    p.add_argument("--sources", default="dotproperty,fazwaz")
    p.add_argument("--skip-collect", action="store_true", help="Reuse pipeline/cache/raw_listings.json")
    p.add_argument("--skip-geocode", action="store_true")
    args = p.parse_args(argv)

    raw_path = CACHE / "raw_listings.json"
    if args.skip_collect and raw_path.exists():
        log(f"[run] reusing {raw_path}")
        raw = json.loads(raw_path.read_text("utf-8"))
    else:
        sources = [s.strip() for s in args.sources.split(",") if s.strip()]
        raw = collect(max_pages=args.max_pages, delay=args.delay, sources=sources)

    listings = raw.get("listings") or []
    log(f"[run] enriching {len(listings)} listings")
    enrich(listings, skip_geocode=args.skip_geocode)
    log("[run] scoring")
    score_all(listings)
    slimmed = [slim(r) for r in listings]
    meta = build_meta(raw, slimmed)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta, "listings": slimmed}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"[run] wrote {OUT} ({OUT.stat().st_size:,} bytes, {len(slimmed)} listings, {meta['province_count']} provinces)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
