"""Collect public land-for-sale listings from sites that allow crawling.

Sources attempted (see README / docs/about.html for the full audit):
  - DotProperty (dotproperty.co.th) — primary: JSON-LD ItemList includes coordinates.
  - FazWaz (fazwaz.com) — supplementary search-card pages (no coordinates in HTML).
  - Thailand-Property — same publishing group as DotProperty; used only if unique URLs appear.
Skipped (blocked or disallowed for this crawler): DDproperty, Hipflat, Baania,
Livinginsider sitemap (CloudFront 403), home.co.th /search and /api, FazWaz /api and /graphql.
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

from .httputil import fetch, FetchResult
from .provinces import PROVINCES, resolve_province_name, slugs_for, unslug
from .units import format_area, parse_area_sqm, parse_frontage_m, parse_price_thb, parse_road_name, sqm_to_rai

TZ = timezone(timedelta(hours=7))
ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "pipeline" / "cache"

SOURCE_NOTES: dict[str, str] = {}
SOURCE_ERRORS: list[dict[str, Any]] = []


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def log(msg: str) -> None:
    print(msg, flush=True)


def _json_ld_blocks(html: str) -> list[Any]:
    out = []
    for raw in re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.I | re.S,
    ):
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return out


def _item_list(html: str) -> Optional[dict]:
    for block in _json_ld_blocks(html):
        if isinstance(block, dict) and block.get("@type") == "ItemList":
            return block
        if isinstance(block, list):
            for item in block:
                if isinstance(item, dict) and item.get("@type") == "ItemList":
                    return item
    return None


def _fazwaz_json_scripts(html: str) -> list[Any]:
    out = []
    for raw in re.findall(
        r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.I | re.S,
    ):
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return out


def _title_of(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _note_error(source: str, url: str, result: FetchResult) -> None:
    SOURCE_ERRORS.append(
        {
            "source": source,
            "url": url,
            "status": result.status,
            "error": result.error,
            "blocked": result.blocked,
        }
    )


def _empty_field(status: str = "unavailable", note: Optional[str] = None) -> dict:
    return {"value": None, "status": status, "note": note or "Data not available."}


def _field(value, status: str, note: Optional[str] = None) -> dict:
    return {"value": value, "status": status, "note": note}


def _coords_valid(lat, lon) -> bool:
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return False
    # Thailand bounding box (with a small margin)
    return 5.4 <= lat <= 20.7 and 97.1 <= lon <= 105.8


def _fazwaz_unit_id(text: str | None) -> Optional[str]:
    if not text:
        return None
    m = re.search(r"(?:unit/|u)(\d{5,9})", text, re.I)
    return m.group(1) if m else None


def _normalize_photo(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    url = url.strip()
    if not url.startswith("http"):
        return None
    # Prefer a reasonably large but not original-size derivative when present.
    return url.split(" ")[0]


# --------------- DotProperty ---------------

def parse_dotproperty_listing(item: dict, page_url: str, scraped_at: str) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    node = item.get("item", item)
    if not isinstance(node, dict):
        return None
    url = node.get("url") or ""
    title = html.unescape(node.get("name") or "").strip()
    if not url or not title:
        return None
    about = node.get("about") or {}
    address = (about.get("address") or {}) if isinstance(about, dict) else {}
    geo = (about.get("geo") or {}) if isinstance(about, dict) else {}
    offers = node.get("offers") or {}
    desc = node.get("description") or ""
    # schema descriptions sometimes contain &nbsp; and HTML remnants
    desc = re.sub(r"<[^>]+>", " ", str(desc))
    desc = html.unescape(re.sub(r"\s+", " ", desc).strip())

    region = unslug(address.get("addressRegion"))
    locality = unslug(address.get("addressLocality"))
    street = unslug(address.get("streetAddress"))
    prov_en, prov_th = resolve_province_name(region) if region else (None, None)
    if not prov_en and region:
        # Sometimes addressRegion is already "Chiang-mai"
        prov_en, prov_th = resolve_province_name(region)

    lat, lon = geo.get("latitude"), geo.get("longitude")
    has_coords = _coords_valid(lat, lon)

    area_sqm, area_ev = parse_area_sqm(title, desc)
    frontage, front_ev = parse_frontage_m(title, desc)
    road = parse_road_name(title, desc)
    price = parse_price_thb(offers.get("price") if isinstance(offers, dict) else None)

    photo = _normalize_photo(node.get("image"))
    unit_id = _fazwaz_unit_id(photo) or _fazwaz_unit_id(url)

    listed = node.get("datePosted")

    rec = {
        "id": "dotproperty:" + (urlparse(url).path.rstrip("/").split("/")[-1] or unit_id or title[:40]),
        "source": "DotProperty",
        "source_url": url,
        "title": title,
        "description": desc[:1500] if desc else None,
        "photos": [photo] if photo else [],
        "province": prov_en,
        "province_th": prov_th,
        "district": locality,
        "subdistrict": street,
        "address_text": ", ".join(p for p in (street, locality, prov_en or region, "Thailand") if p),
        "listed_date": listed,
        "scraped_at": scraped_at,
        "external_ids": {"fazwaz_unit": unit_id},
        "collected_from_page": page_url,
        "price_thb": _field(price, "verified", "Asking price published on the listing.") if price else _empty_field(),
        "area_sqm": (
            _field(area_sqm, "verified", f"Parsed from listing text: “{area_ev}”.")
            if area_sqm
            else _empty_field("unavailable", "Land area was not stated in the listing card or description.")
        ),
        "frontage_m": (
            _field(frontage, "verified", f"Stated in the listing text: “{front_ev}”.")
            if frontage
            else _empty_field("unavailable", "Road frontage was not stated in the listing text.")
        ),
        "road_name_listing": (
            _field(road, "verified", "Road or highway name mentioned in the listing text.")
            if road
            else _empty_field("unavailable", "No road name was stated in the listing text.")
        ),
        "coordinates": (
            _field(
                {"lat": float(lat), "lon": float(lon)},
                "listing_pin",
                "Listing pin (seller-placed, approximate). Published with the listing, not a surveyed parcel location.",
            )
            if has_coords
            else _empty_field("unavailable", "The listing did not publish coordinates.")
        ),
    }
    rec["area_rai"] = (
        _field(sqm_to_rai(area_sqm), "calculated", "Converted from listing area (1 rai = 1,600 sqm).")
        if area_sqm
        else _empty_field()
    )
    rec["area_display"] = format_area(area_sqm) if area_sqm else None
    if price and area_sqm and area_sqm > 0:
        rec["price_per_rai"] = _field(
            round(price / (area_sqm / 1600.0), 0),
            "calculated",
            "Asking price divided by land area in rai. Both inputs come from the listing.",
        )
    else:
        rec["price_per_rai"] = _empty_field(
            "unavailable",
            "Price per rai is only calculated when both asking price and land area are known.",
        )
    return rec


def collect_dotproperty(max_pages: int, delay: float) -> list[dict]:
    listings: list[dict] = []
    seen_urls: set[str] = set()
    scraped_at = now_iso()
    resolved_slugs: dict[str, str] = {}

    def add_from_html(html: str, page_url: str, result_ok: bool) -> tuple[int, Optional[int]]:
        if not result_ok:
            return 0, None
        block = _item_list(html)
        if not block:
            return 0, None
        declared = block.get("numberOfItems")
        try:
            declared_n = int(declared) if declared is not None else None
        except (TypeError, ValueError):
            declared_n = None
        added = 0
        for el in block.get("itemListElement") or []:
            rec = parse_dotproperty_listing(el, page_url, scraped_at)
            if not rec:
                continue
            url = rec["source_url"]
            if url in seen_urls:
                continue
            seen_urls.add(url)
            listings.append(rec)
            added += 1
        return added, declared_n

    # National page first (helps discover popular slugs + a first batch).
    national = "https://www.dotproperty.co.th/en/land-for-sale"
    log(f"[dotproperty] national {national}")
    res = fetch(national, delay=delay)
    if not res.ok:
        _note_error("DotProperty", national, res)
        SOURCE_NOTES["DotProperty"] = f"National land page failed ({res.status} {res.error or ''})."
        log(f"  FAILED {res.status} {res.error}")
    else:
        added, declared = add_from_html(res.body, res.final_url, True)
        log(f"  {added} listings, declared total={declared}, title={_title_of(res.body)[:80]}")
        SOURCE_NOTES["DotProperty"] = f"Public land-for-sale pages (JSON-LD ItemList). National declared total: {declared}."
        # a few national pages for freshness, then province pages for coverage
        n_pages = min(max_pages, max(1, ((declared or 30) + 29) // 30))
        for page in range(2, n_pages + 1):
            url = f"https://www.dotproperty.co.th/en/land-for-sale?page={page}"
            r = fetch(url, delay=delay)
            if not r.ok:
                _note_error("DotProperty", url, r)
                log(f"  page {page} failed {r.status}")
                if r.blocked:
                    SOURCE_NOTES["DotProperty"] += " Later pages were blocked."
                    break
                continue
            a, _ = add_from_html(r.body, r.final_url, True)
            log(f"  national page {page}: +{a}")

    for en, th, slug, _extra in PROVINCES:
        slugs = slugs_for(en)
        chosen = resolved_slugs.get(en)
        declared = None
        if not chosen:
            for s in slugs:
                url = f"https://www.dotproperty.co.th/en/land-for-sale/{s}"
                r = fetch(url, delay=delay)
                if r.status == 404:
                    continue
                if not r.ok:
                    _note_error("DotProperty", url, r)
                    if r.blocked:
                        log(f"  [{en}] blocked on {s}")
                        break
                    continue
                if "Page Not Found" in _title_of(r.body):
                    continue
                added, declared = add_from_html(r.body, r.final_url, True)
                if added == 0 and not declared:
                    continue
                chosen = s
                resolved_slugs[en] = s
                log(f"  [{en}/{th}] slug={s} +{added} declared={declared}")
                break
            else:
                log(f"  [{en}] no working DotProperty slug among {slugs}")
                continue
        else:
            declared = None

        if not chosen:
            continue
        # Remaining pages for this province
        # If we already fetched page 1 while resolving slug, start at 2.
        total = declared or 30
        last_page = min(max_pages, max(1, (int(total) + 29) // 30))
        start = 2
        for page in range(start, last_page + 1):
            url = f"https://www.dotproperty.co.th/en/land-for-sale/{chosen}?page={page}"
            r = fetch(url, delay=delay)
            if not r.ok:
                _note_error("DotProperty", url, r)
                log(f"  [{en}] page {page} failed {r.status}")
                if r.blocked:
                    break
                continue
            a, d = add_from_html(r.body, r.final_url, True)
            if d:
                total = d
                last_page = min(max_pages, max(last_page, (int(total) + 29) // 30))
            log(f"  [{en}] page {page}: +{a}")
            if a == 0:
                break

    log(f"[dotproperty] collected {len(listings)} unique listings")
    return listings


# --------------- FazWaz ---------------

def parse_fazwaz_card(unit_id: str, card: dict, page_url: str, scraped_at: str) -> Optional[dict]:
    if not isinstance(card, dict):
        return None
    if (card.get("propertyType") or "").lower() != "land" and card.get("propertyTypeId") not in (12, "12"):
        return None
    url = card.get("detailUrl") or ""
    title = html.unescape(card.get("name") or "").strip()
    if not url or not title:
        return None
    address = card.get("formatted_address") or ""
    parts = [p.strip() for p in address.split(",") if p.strip()]
    # Typical: "Khao Sai, Tap Khlo, Phichit, Thailand"
    country = parts[-1] if parts and "thailand" in parts[-1].lower() else None
    loc_parts = parts[:-1] if country else parts
    prov_en = prov_th = None
    district = subdistrict = None
    if loc_parts:
        prov_en, prov_th = resolve_province_name(loc_parts[-1])
        if prov_en:
            loc_parts = loc_parts[:-1]
        if len(loc_parts) >= 2:
            subdistrict, district = loc_parts[0], loc_parts[1]
        elif len(loc_parts) == 1:
            district = loc_parts[0]

    area_sqm, area_ev = parse_area_sqm(title, card.get("area") or "", address)
    # card.area is usually like "9,600 SqM"
    if area_sqm is None:
        area_sqm, area_ev = parse_area_sqm(card.get("area") or "")
    frontage, front_ev = parse_frontage_m(title)
    road = parse_road_name(title, address)
    price = parse_price_thb(card.get("price"))
    photo = _normalize_photo(card.get("thumbnail"))
    uid = str(unit_id)

    rec = {
        "id": f"fazwaz:{uid}",
        "source": "FazWaz",
        "source_url": url,
        "title": title,
        "description": None,
        "photos": [photo] if photo else [],
        "province": prov_en,
        "province_th": prov_th,
        "district": district,
        "subdistrict": subdistrict,
        "address_text": address or None,
        "listed_date": None,
        "scraped_at": scraped_at,
        "external_ids": {"fazwaz_unit": uid},
        "collected_from_page": page_url,
        "price_thb": _field(price, "verified", "Asking price published on the listing card.") if price else _empty_field(),
        "area_sqm": (
            _field(area_sqm, "verified", f"Parsed from listing card: “{area_ev}”.")
            if area_sqm
            else _empty_field()
        ),
        "frontage_m": (
            _field(frontage, "verified", f"Stated in the listing text: “{front_ev}”.")
            if frontage
            else _empty_field("unavailable", "Road frontage was not stated on the listing card.")
        ),
        "road_name_listing": (
            _field(road, "verified", "Road or highway name mentioned on the listing card.")
            if road
            else _empty_field()
        ),
        # FazWaz public HTML does not include coordinates; enrichment may geocode a precise locality.
        "coordinates": _empty_field(
            "unavailable",
            "The public FazWaz listing card does not include GPS coordinates.",
        ),
    }
    rec["area_rai"] = (
        _field(sqm_to_rai(area_sqm), "calculated", "Converted from listing area (1 rai = 1,600 sqm).")
        if area_sqm
        else _empty_field()
    )
    rec["area_display"] = format_area(area_sqm) if area_sqm else None
    if price and area_sqm and area_sqm > 0:
        rec["price_per_rai"] = _field(
            round(price / (area_sqm / 1600.0), 0),
            "calculated",
            "Asking price divided by land area in rai. Both inputs come from the listing.",
        )
    else:
        rec["price_per_rai"] = _empty_field(
            "unavailable",
            "Price per rai is only calculated when both asking price and land area are known.",
        )
    return rec


def collect_fazwaz(max_pages: int, delay: float) -> list[dict]:
    listings: list[dict] = []
    seen: set[str] = set()
    scraped_at = now_iso()

    def add_from_html(html: str, page_url: str) -> tuple[int, Optional[int]]:
        scripts = _fazwaz_json_scripts(html)
        declared = None
        cards = None
        for sc in scripts:
            if isinstance(sc, dict) and "data" in sc and isinstance(sc["data"], dict):
                try:
                    declared = int(sc["data"].get("actuallyTotal") or sc["data"].get("total") or 0) or None
                except (TypeError, ValueError):
                    declared = None
            if isinstance(sc, dict) and sc and all(isinstance(v, dict) and "detailUrl" in v for v in list(sc.values())[:3]):
                cards = sc
        if not cards:
            return 0, declared
        added = 0
        for uid, card in cards.items():
            rec = parse_fazwaz_card(uid, card, page_url, scraped_at)
            if not rec:
                continue
            if rec["source_url"] in seen or rec["id"] in seen:
                continue
            seen.add(rec["source_url"])
            seen.add(rec["id"])
            listings.append(rec)
            added += 1
        return added, declared

    national = "https://www.fazwaz.com/land-for-sale/thailand"
    log(f"[fazwaz] national {national}")
    res = fetch(national, delay=delay)
    if not res.ok:
        _note_error("FazWaz", national, res)
        SOURCE_NOTES["FazWaz"] = f"National land page failed ({res.status} {res.error or ''})."
        log(f"  FAILED {res.status} {res.error}")
        return listings
    added, declared = add_from_html(res.body, res.final_url)
    log(f"  +{added} declared={declared}")
    SOURCE_NOTES["FazWaz"] = f"Public land-for-sale search pages (embedded JSON cards). National declared total: {declared}."

    n_pages = min(max_pages, max(1, ((declared or 30) + 29) // 30))
    for page in range(2, n_pages + 1):
        url = f"https://www.fazwaz.com/land-for-sale/thailand?page={page}"
        r = fetch(url, delay=delay)
        if not r.ok:
            _note_error("FazWaz", url, r)
            log(f"  national page {page} failed {r.status}")
            if r.blocked:
                break
            continue
        a, _ = add_from_html(r.body, r.final_url)
        log(f"  national page {page}: +{a}")

    for en, th, slug, _extra in PROVINCES:
        slugs = slugs_for(en)
        chosen = None
        declared = None
        for s in slugs:
            url = f"https://www.fazwaz.com/land-for-sale/thailand/{s}"
            r = fetch(url, delay=delay)
            if r.status == 404:
                continue
            if not r.ok:
                _note_error("FazWaz", url, r)
                if r.blocked:
                    log(f"  [{en}] blocked")
                    break
                continue
            if "has not been found" in (r.body or "").lower() or "404" in _title_of(r.body):
                continue
            a, declared = add_from_html(r.body, r.final_url)
            chosen = s
            log(f"  [{en}/{th}] slug={s} +{a} declared={declared}")
            break
        if not chosen:
            log(f"  [{en}] no working FazWaz slug")
            continue
        total = declared or 30
        last_page = min(max_pages, max(1, (int(total) + 29) // 30))
        for page in range(2, last_page + 1):
            url = f"https://www.fazwaz.com/land-for-sale/thailand/{chosen}?page={page}"
            r = fetch(url, delay=delay)
            if not r.ok:
                _note_error("FazWaz", url, r)
                log(f"  [{en}] page {page} failed {r.status}")
                if r.blocked:
                    break
                continue
            a, d = add_from_html(r.body, r.final_url)
            log(f"  [{en}] page {page}: +{a}")
            if a == 0:
                break

    log(f"[fazwaz] collected {len(listings)} unique listings")
    return listings


# --------------- Merge / dedupe ---------------

def _key_parts(rec: dict) -> tuple:
    """Identity for *cross-source* dedupe only.

    Within a single harvest, listings are already unique by URL. We only merge
    two records when they clearly describe the same FazWaz unit (shared unit id
    in a FazWaz URL or a FazWaz CDN photo). We do not merge on rounded
    coordinates + price, because many distinct plots share an area centroid.
    """
    uid = (rec.get("external_ids") or {}).get("fazwaz_unit")
    url = rec.get("source_url") or ""
    if uid and ("fazwaz.com" in url or "cdn.fazwaz.com" in " ".join(rec.get("photos") or [])):
        return ("unit", str(uid))
    return ("url", url)


def merge_listings(*groups: list[dict]) -> list[dict]:
    """Prefer the record that already has coordinates, then the one with more photos/area."""
    by: dict[tuple, dict] = {}
    order: list[tuple] = []

    def score(rec: dict) -> tuple:
        has_c = 1 if (rec.get("coordinates") or {}).get("value") else 0
        has_area = 1 if (rec.get("area_sqm") or {}).get("value") else 0
        photos = len(rec.get("photos") or [])
        desc = 1 if rec.get("description") else 0
        return (has_c, has_area, desc, photos)

    for rec in (x for g in groups for x in g):
        k = _key_parts(rec)
        if k not in by:
            by[k] = rec
            order.append(k)
            continue
        old = by[k]
        if score(rec) > score(old):
            # Keep both source URLs
            rec = dict(rec)
            rec["also_listed_at"] = list(
                {*(old.get("also_listed_at") or []), old.get("source_url")}
            )
            rec["sources"] = list({old.get("source"), rec.get("source")})
            by[k] = rec
        else:
            old.setdefault("also_listed_at", [])
            if rec.get("source_url") and rec["source_url"] not in old["also_listed_at"]:
                old["also_listed_at"].append(rec["source_url"])
            # If the winner lacks coords / area, fill from the other
            if not (old.get("coordinates") or {}).get("value") and (rec.get("coordinates") or {}).get("value"):
                old["coordinates"] = rec["coordinates"]
            if not (old.get("area_sqm") or {}).get("value") and (rec.get("area_sqm") or {}).get("value"):
                old["area_sqm"] = rec["area_sqm"]
                old["area_rai"] = rec.get("area_rai")
                old["area_display"] = rec.get("area_display")
                old["price_per_rai"] = rec.get("price_per_rai") or old.get("price_per_rai")
            if not old.get("description") and rec.get("description"):
                old["description"] = rec["description"]
            if rec.get("photos"):
                photos = list(dict.fromkeys((old.get("photos") or []) + rec["photos"]))
                old["photos"] = photos[:8]
    return [by[k] for k in order]


def collect(max_pages: int = 3, delay: float = 1.25, sources: Optional[list[str]] = None) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    sources = sources or ["dotproperty", "fazwaz"]
    groups = []
    if "dotproperty" in sources:
        groups.append(collect_dotproperty(max_pages, delay))
        _dump_partial("dotproperty", groups[-1])
    if "fazwaz" in sources:
        groups.append(collect_fazwaz(max_pages, delay))
        _dump_partial("fazwaz", groups[-1])
    merged = merge_listings(*groups)
    payload = {
        "collected_at": now_iso(),
        "listings": merged,
        "source_notes": SOURCE_NOTES,
        "source_errors": SOURCE_ERRORS,
        "counts_before_merge": {i: len(g) for i, g in enumerate(groups)},
        "count": len(merged),
    }
    out = CACHE / "raw_listings.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=None), encoding="utf-8")
    log(f"[collect] wrote {out} ({len(merged)} listings after merge)")
    return payload


def _dump_partial(name: str, listings: list[dict]) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"raw_{name}.json"
    path.write_text(json.dumps({"listings": listings, "count": len(listings)}, ensure_ascii=False), encoding="utf-8")
    log(f"  cached {path}")


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Collect public Thai land-for-sale listings")
    p.add_argument("--max-pages", type=int, default=3, help="Max search pages per province (and national)")
    p.add_argument("--delay", type=float, default=1.25, help="Seconds between requests")
    p.add_argument("--sources", default="dotproperty,fazwaz")
    args = p.parse_args(argv)
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    collect(max_pages=args.max_pages, delay=args.delay, sources=sources)
    return 0


if __name__ == "__main__":
    sys.exit(main())
