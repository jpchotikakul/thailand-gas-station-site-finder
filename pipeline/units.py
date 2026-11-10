"""Thai land-area units and text parsers.

1 rai = 4 ngan = 400 square wah = 1,600 square metres.
Never invent values: return None when a figure is not actually present in the text.
"""
from __future__ import annotations

import html
import re
from typing import Optional

SQM_PER_RAI = 1600.0
SQM_PER_NGAN = 400.0
SQM_PER_WAH = 4.0

# Common typography / spacing issues in listing blurbs.
_CLEAN = (
    (r"&nbsp;|&#160;", " "),
    (r"a(?=\d[\d,]*(?:\.\d+)?\s*(?:sq\.?\s*m|sqm))", " "),  # "a1,648 sqm"
    (r"[\u200b\u200c\u00ad]", ""),
)


def _clean(text: str) -> str:
    text = html.unescape(text or "")
    text = text.replace("\xa0", " ").replace("\u202f", " ")
    for pat, repl in _CLEAN:
        text = re.sub(pat, repl, text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _num(s: str) -> Optional[float]:
    if s is None:
        return None
    s = s.replace(",", "").replace(" ", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# Combined "X rai Y ngan Z wah" (any subset, any order-ish, English or Thai).
_COMBINED = re.compile(
    r"""
    (?:(?P<rai>[\d,]+(?:\.\d+)?)\s*(?:rai|ไร่))
    (?:\s*(?P<ngan>[\d,]+(?:\.\d+)?)\s*(?:ngan|งาน))?
    (?:\s*(?P<wah>[\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*w(?:ah|a|aar)?|square\s*w(?:ah|a)|ตร\.?\s*ว\.?|ตารางวา|วา))?
    |
    (?:(?P<ngan2>[\d,]+(?:\.\d+)?)\s*(?:ngan|งาน))
    (?:\s*(?P<wah2>[\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*w(?:ah|a|aar)?|square\s*w(?:ah|a)|ตร\.?\s*ว\.?|ตารางวา|วา))?
    """,
    re.I | re.X,
)

_SQM = re.compile(
    r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m(?:et(?:re|er)s?)?|sqm|sq\.m|ตร\.?\s*ม\.?|ตารางเมตร)",
    re.I,
)
_RAI_ONLY = re.compile(r"([\d,]+(?:\.\d+)?)\s*(?:rai|ไร่)", re.I)
_WAH_ONLY = re.compile(
    r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*w(?:ah|a|aar)?|square\s*w(?:ah|a)|ตร\.?\s*ว\.?|ตารางวา)\b",
    re.I,
)

# Frontage / width mentions. Avoid matching plot area accidentally.
_FRONTAGE = re.compile(
    r"""
    (?:
        (?:road\s+)?frontage(?:\s+of)? |
        frontage\s*[:\-] |
        หน้ากว้าง(?:ถนน)? |
        กว้างหน้าแปลง |
        กว้างติดถนน
    )
    \s*[:\-]?\s*
    ([\d,]+(?:\.\d+)?)\s*(?:m(?:et(?:re|er)s?)?|ม(?:ีเตอร์|ตร)?\.?)
    |
    ([\d,]+(?:\.\d+)?)\s*(?:m(?:et(?:re|er)s?)?|ม(?:ีเตอร์|ตร)?\.?)\s*
    (?:of\s+)?(?:road\s+)?frontage
    """,
    re.I | re.X,
)

# Road / highway names mentioned in the listing text.
_ROAD = re.compile(
    r"""
    (?:
        (?:on|along|front(?:ing|s)?(?:\s+onto)?|access(?:\s+to)?|beside|off)\s+
        (?:the\s+)?
        (
            (?:highway|hwy|route|ถนน|ทางหลวง(?:แผ่นดิน)?)\s*[\w\-\u0E00-\u0E7F]+
            (?:\s+road)?
            |
            [\w\-\u0E00-\u0E7F]+(?:kasem|phat|mittraphap|sukhumvit|phahonyothin|ramintra|sirat|chalerm|kanchanaphisek)
            (?:\s+road)?
        )
    )
    |
    (
        ถนน[\u0E00-\u0E7F0-9\-]+
        |ทางหลวง(?:แผ่นดิน)?(?:หมายเลข)?\s*\d+
        |(?:highway|hwy|route)\s*\d+
    )
    """,
    re.I | re.X,
)


def parse_area_sqm(*parts: Optional[str]) -> tuple[Optional[float], Optional[str]]:
    """Return (sqm, evidence snippet) from listing title/description text."""
    text = _clean(" ".join(p for p in parts if p))
    if not text:
        return None, None

    best = None
    evidence = None

    def consider(sqm: Optional[float], match: re.Match) -> None:
        nonlocal best, evidence
        if sqm is None or sqm <= 0 or sqm > 50_000_000:
            return
        # Prefer more specific (combined) matches by keeping the first solid one,
        # but replace a weaker wah-only/rai-only if a combined figure appears.
        if best is None:
            best, evidence = sqm, match.group(0).strip()

    for m in _COMBINED.finditer(text):
        rai = _num(m.group("rai"))
        ngan = _num(m.group("ngan") or m.group("ngan2"))
        wah = _num(m.group("wah") or m.group("wah2"))
        if rai is None and ngan is None and wah is None:
            continue
        sqm = (rai or 0) * SQM_PER_RAI + (ngan or 0) * SQM_PER_NGAN + (wah or 0) * SQM_PER_WAH
        # Only accept combined if at least one component was present.
        if sqm > 0:
            consider(sqm, m)
            if rai is not None or (ngan is not None and wah is not None):
                # Strong match; stop at the first full figure.
                return best, evidence

    # Standalone sqm is usually the cleanest published figure.
    m = _SQM.search(text)
    if m:
        consider(_num(m.group(1)), m)
        if best is not None:
            return best, evidence

    m = _RAI_ONLY.search(text)
    if m:
        consider((_num(m.group(1)) or 0) * SQM_PER_RAI, m)
        if best is not None:
            return best, evidence

    m = _WAH_ONLY.search(text)
    if m:
        consider((_num(m.group(1)) or 0) * SQM_PER_WAH, m)

    return best, evidence


def sqm_to_rai(sqm: Optional[float]) -> Optional[float]:
    if sqm is None:
        return None
    return round(sqm / SQM_PER_RAI, 4)


def format_area(sqm: Optional[float]) -> Optional[str]:
    if sqm is None:
        return None
    rai = sqm / SQM_PER_RAI
    if rai >= 1:
        r = int(rai)
        rem = sqm - r * SQM_PER_RAI
        ngan = int(rem / SQM_PER_NGAN)
        wah = (rem - ngan * SQM_PER_NGAN) / SQM_PER_WAH
        parts = [f"{r} rai"]
        if ngan:
            parts.append(f"{ngan} ngan")
        if wah >= 0.05:
            parts.append(f"{wah:.1f}".rstrip("0").rstrip(".") + " sq wah")
        return f"{' '.join(parts)} ({sqm:,.0f} sqm)" if sqm >= 10 else f"{' '.join(parts)} ({sqm:,.1f} sqm)"
    wah = sqm / SQM_PER_WAH
    return f"{wah:.1f}".rstrip("0").rstrip(".") + f" sq wah ({sqm:,.0f} sqm)"


def parse_frontage_m(*parts: Optional[str]) -> tuple[Optional[float], Optional[str]]:
    text = _clean(" ".join(p for p in parts if p))
    if not text:
        return None, None
    m = _FRONTAGE.search(text)
    if not m:
        return None, None
    val = _num(m.group(1) or m.group(2))
    if val is None or val <= 0 or val > 2000:
        return None, None
    return val, m.group(0).strip()


def parse_road_name(*parts: Optional[str]) -> Optional[str]:
    text = _clean(" ".join(p for p in parts if p))
    if not text:
        return None
    m = _ROAD.search(text)
    if not m:
        return None
    name = next((g for g in m.groups() if g), None)
    if not name:
        return None
    name = re.sub(r"\s+", " ", name).strip(" ,.-")
    if len(name) < 3:
        return None
    return name[:80]


def parse_price_thb(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    s = re.sub(r"[฿THB,\s]", "", str(value), flags=re.I)
    # Sometimes trailing .00000003 floats appear in schema.org
    try:
        n = float(s)
    except ValueError:
        return None
    if n <= 0 or n > 1e13:
        return None
    return round(n, 0)
