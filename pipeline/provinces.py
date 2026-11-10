"""Thailand's 77 provinces: English, Thai, and public-site URL slugs."""
from __future__ import annotations

# (english, thai, primary slug, extra slugs)
PROVINCES: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("Amnat Charoen", "อำนาจเจริญ", "amnat-charoen", ()),
    ("Ang Thong", "อ่างทอง", "ang-thong", ()),
    ("Bangkok", "กรุงเทพมหานคร", "bangkok", ("krung-thep-maha-nakhon", "krung-thep")),
    ("Bueng Kan", "บึงกาฬ", "bueng-kan", ("buengkan",)),
    ("Buri Ram", "บุรีรัมย์", "buri-ram", ("buriram",)),
    ("Chachoengsao", "ฉะเชิงเทรา", "chachoengsao", ()),
    ("Chai Nat", "ชัยนาท", "chai-nat", ("chainat",)),
    ("Chaiyaphum", "ชัยภูมิ", "chaiyaphum", ()),
    ("Chanthaburi", "จันทบุรี", "chanthaburi", ()),
    ("Chiang Mai", "เชียงใหม่", "chiang-mai", ("chiangmai",)),
    ("Chiang Rai", "เชียงราย", "chiang-rai", ("chiangrai",)),
    ("Chon Buri", "ชลบุรี", "chon-buri", ("chonburi", "chon buri")),
    ("Chumphon", "ชุมพร", "chumphon", ()),
    ("Kalasin", "กาฬสินธุ์", "kalasin", ()),
    ("Kamphaeng Phet", "กำแพงเพชร", "kamphaeng-phet", ("kamphaengphet",)),
    ("Kanchanaburi", "กาญจนบุรี", "kanchanaburi", ()),
    ("Khon Kaen", "ขอนแก่น", "khon-kaen", ("khonkaen",)),
    ("Krabi", "กระบี่", "krabi", ()),
    ("Lampang", "ลำปาง", "lampang", ()),
    ("Lamphun", "ลำพูน", "lamphun", ()),
    ("Loei", "เลย", "loei", ()),
    ("Lop Buri", "ลพบุรี", "lop-buri", ("lopburi",)),
    ("Mae Hong Son", "แม่ฮ่องสอน", "mae-hong-son", ("maehongson",)),
    ("Maha Sarakham", "มหาสารคาม", "maha-sarakham", ("mahasarakham",)),
    ("Mukdahan", "มุกดาหาร", "mukdahan", ()),
    ("Nakhon Nayok", "นครนายก", "nakhon-nayok", ()),
    ("Nakhon Pathom", "นครปฐม", "nakhon-pathom", ()),
    ("Nakhon Phanom", "นครพนม", "nakhon-phanom", ()),
    ("Nakhon Ratchasima", "นครราชสีมา", "nakhon-ratchasima", ("korat",)),
    ("Nakhon Sawan", "นครสวรรค์", "nakhon-sawan", ()),
    ("Nakhon Si Thammarat", "นครศรีธรรมราช", "nakhon-si-thammarat", ()),
    ("Nan", "น่าน", "nan", ()),
    ("Narathiwat", "นราธิวาส", "narathiwat", ()),
    ("Nong Bua Lam Phu", "หนองบัวลำภู", "nong-bua-lam-phu", ("nong-bua-lamphu", "nongbualamphu")),
    ("Nong Khai", "หนองคาย", "nong-khai", ("nongkhai",)),
    ("Nonthaburi", "นนทบุรี", "nonthaburi", ()),
    ("Pathum Thani", "ปทุมธานี", "pathum-thani", ("pathumthani",)),
    ("Pattani", "ปัตตานี", "pattani", ()),
    ("Phangnga", "พังงา", "phangnga", ("phang-nga", "phang nga")),
    ("Phatthalung", "พัทลุง", "phatthalung", ()),
    ("Phayao", "พะเยา", "phayao", ()),
    ("Phetchabun", "เพชรบูรณ์", "phetchabun", ()),
    ("Phetchaburi", "เพชรบุรี", "phetchaburi", ()),
    ("Phichit", "พิจิตร", "phichit", ()),
    ("Phitsanulok", "พิษณุโลก", "phitsanulok", ()),
    ("Phra Nakhon Si Ayutthaya", "พระนครศรีอยุธยา", "phra-nakhon-si-ayutthaya", ("ayutthaya",)),
    ("Phrae", "แพร่", "phrae", ()),
    ("Phuket", "ภูเก็ต", "phuket", ()),
    ("Prachin Buri", "ปราจีนบุรี", "prachin-buri", ("prachinburi",)),
    ("Prachuap Khiri Khan", "ประจวบคีรีขันธ์", "prachuap-khiri-khan", ("prachuap", "hua-hin")),
    ("Ranong", "ระนอง", "ranong", ()),
    ("Ratchaburi", "ราชบุรี", "ratchaburi", ()),
    ("Rayong", "ระยอง", "rayong", ()),
    ("Roi Et", "ร้อยเอ็ด", "roi-et", ("roiet",)),
    ("Sa Kaeo", "สระแก้ว", "sa-kaeo", ("sakaeo",)),
    ("Sakon Nakhon", "สกลนคร", "sakon-nakhon", ()),
    ("Samut Prakan", "สมุทรปราการ", "samut-prakan", ("samutprakan",)),
    ("Samut Sakhon", "สมุทรสาคร", "samut-sakhon", ()),
    ("Samut Songkhram", "สมุทรสงคราม", "samut-songkhram", ()),
    ("Saraburi", "สระบุรี", "saraburi", ()),
    ("Satun", "สตูล", "satun", ()),
    ("Si Sa Ket", "ศรีสะเกษ", "si-sa-ket", ("sisaket", "si-saket")),
    ("Sing Buri", "สิงห์บุรี", "sing-buri", ("singburi",)),
    ("Songkhla", "สงขลา", "songkhla", ()),
    ("Sukhothai", "สุโขทัย", "sukhothai", ()),
    ("Suphan Buri", "สุพรรณบุรี", "suphan-buri", ("suphanburi",)),
    ("Surat Thani", "สุราษฎร์ธานี", "surat-thani", ("suratthani", "koh-samui", "ko-samui")),
    ("Surin", "สุรินทร์", "surin", ()),
    ("Tak", "ตาก", "tak", ()),
    ("Trang", "ตรัง", "trang", ()),
    ("Trat", "ตราด", "trat", ()),
    ("Ubon Ratchathani", "อุบลราชธานี", "ubon-ratchathani", ()),
    ("Udon Thani", "อุดรธานี", "udon-thani", ("udonthani",)),
    ("Uthai Thani", "อุทัยธานี", "uthai-thani", ()),
    ("Uttaradit", "อุตรดิตถ์", "uttaradit", ()),
    ("Yala", "ยะลา", "yala", ()),
    ("Yasothon", "ยโสธร", "yasothon", ()),
]

EN_TO_TH = {en: th for en, th, *_ in PROVINCES}
SLUG_TO_PROVINCE: dict[str, tuple[str, str]] = {}
for en, th, slug, extra in PROVINCES:
    for s in (slug, *extra):
        SLUG_TO_PROVINCE[s.lower()] = (en, th)
        SLUG_TO_PROVINCE[s.lower().replace("-", "")] = (en, th)
        SLUG_TO_PROVINCE[s.lower().replace("-", " ")] = (en, th)

# Common English variants seen on listing sites.
_ALIASES = {
    "chonburi": "Chon Buri",
    "chon buri": "Chon Buri",
    "buriram": "Buri Ram",
    "lopburi": "Lop Buri",
    "prachinburi": "Prachin Buri",
    "suphanburi": "Suphan Buri",
    "singburi": "Sing Buri",
    "phang nga": "Phangnga",
    "phang-nga": "Phangnga",
    "ayutthaya": "Phra Nakhon Si Ayutthaya",
    "phra nakhon si ayutthaya": "Phra Nakhon Si Ayutthaya",
    "krung thep maha nakhon": "Bangkok",
    "krung thep": "Bangkok",
    "sisaket": "Si Sa Ket",
    "si saket": "Si Sa Ket",
    "korat": "Nakhon Ratchasima",
    "pattaya": "Chon Buri",  # city, not a province — keep as Chon Buri
    "hua hin": "Prachuap Khiri Khan",
    "ko samui": "Surat Thani",
    "koh samui": "Surat Thani",
    "koh phangan": "Surat Thani",
    "ko phangan": "Surat Thani",
}



def _norm(name: str) -> str:
    return " ".join(name.lower().replace("_", " ").replace("-", " ").split())


def resolve_province_name(name: str | None) -> tuple[str | None, str | None]:
    """Return (English, Thai) province names, or (None, None) if unknown."""
    if not name:
        return None, None
    raw = name.strip()
    key = _norm(raw)
    compact = key.replace(" ", "")
    if key in { _norm(en): (en, th) for en, th, *_ in PROVINCES }:
        pass
    lookup = {}
    for en, th, slug, extra in PROVINCES:
        lookup[_norm(en)] = (en, th)
        lookup[_norm(th)] = (en, th)
        lookup[_norm(slug)] = (en, th)
        lookup[slug.replace("-", "")] = (en, th)
        for s in extra:
            lookup[_norm(s)] = (en, th)
            lookup[s.replace("-", "").replace(" ", "")] = (en, th)
    for k, en in _ALIASES.items():
        lookup[_norm(k)] = (en, EN_TO_TH[en])
        lookup[k.replace("-", "").replace(" ", "")] = (en, EN_TO_TH[en])
    if key in lookup:
        return lookup[key]
    if compact in lookup:
        return lookup[compact]
    # Last token sometimes is the province ("..., Prachuap Khiri Khan")
    return None, None


def slugs_for(en: str) -> list[str]:
    for name, _th, slug, extra in PROVINCES:
        if name == en:
            out = [slug, *extra]
            # also try de-hyphenated form
            if "-" in slug:
                out.append(slug.replace("-", ""))
            # unique, preserve order
            seen = set()
            uniq = []
            for s in out:
                s = s.replace(" ", "-")
                if s not in seen:
                    seen.add(s)
                    uniq.append(s)
            return uniq
    return []


def unslug(value: str | None) -> str | None:
    if not value:
        return None
    value = value.replace("_", " ").replace("-", " ").strip()
    value = " ".join(p.capitalize() if not p.isupper() else p for p in value.split())
    return value or None
