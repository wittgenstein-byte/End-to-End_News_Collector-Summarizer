"""
core/thai_normalizer.py
─────────────────────────────────────────────────────────────────
SOLID  S — Specialized Thai NLP text normalization, entity alias resolution,
           and hierarchical location parsing.
SOLID  O — Extensible dictionaries for aliases, acronyms, and location maps.
GRASP  Information Expert — Canonical Thai provincial, district, and entity rules.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re

# Thai digit translation table: ๐-๙ -> 0-9
_THAI_DIGIT_MAP = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

# Zero-width and invisible characters
_ZERO_WIDTH_PATTERN = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\ufeff]")
_WHITESPACE_COLLAPSE = re.compile(r"[ \t\u00a0]+")

# Canonical Thai news acronyms mapping
_ACRONYM_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?<![ก-๙a-zA-Z0-9])รพ\."), "โรงพยาบาล"),
    (re.compile(r"(?<![ก-๙a-zA-Z0-9])สภ\."), "สถานีตำรวจภูธร"),
    (re.compile(r"(?<![ก-๙a-zA-Z0-9])สน\."), "สถานีตำรวจนครบาล"),
    (re.compile(r"(?<![ก-๙a-zA-Z0-9])บก\."), "กองบังคับการ"),
    (re.compile(r"(?<![ก-๙a-zA-Z0-9])อบต\."), "องค์การบริหารส่วนตำบล"),
    (re.compile(r"(?<![ก-๙a-zA-Z0-9])อบจ\."), "องค์การบริหารส่วนจังหวัด"),
    (re.compile(r"(?<![ก-๙a-zA-Z0-9])สตช\."), "สำนักงานตำรวจแห่งชาติ"),
    (re.compile(r"(?<![ก-๙a-zA-Z0-9])กทม\."), "กรุงเทพมหานคร"),
    (re.compile(r"กรุงเทพฯ"), "กรุงเทพมหานคร"),
]

# Canonical 77 provinces of Thailand
THAI_PROVINCES: frozenset[str] = frozenset({
    "กรุงเทพมหานคร", "กระบี่", "กาญจนบุรี", "กาฬสินธุ์", "กำแพงเพชร",
    "ขอนแก่น", "จันทบุรี", "ฉะเชิงเทรา", "ชลบุรี", "ชัยนาท", "ชัยภูมิ",
    "ชุมพร", "เชียงราย", "เชียงใหม่", "ตรัง", "ตราด", "ตาก", "นครนายก",
    "นครปฐม", "นครพนม", "นครราชสีมา", "นครศรีธรรมราช", "นครสวรรค์",
    "นนทบุรี", "นราธิวาส", "น่าน", "บึงกาฬ", "บุรีรัมย์", "ปทุมธานี",
    "ประจวบคีรีขันธ์", "ปราจีนบุรี", "ปัตตานี", "พระนครศรีอยุธยา",
    "พะเยา", "พังงา", "พัทลุง", "พิจิตร", "พิษณุโลก", "เพชรบุรี",
    "เพชรบูรณ์", "แพร่", "ภูเก็ต", "มหาสารคาม", "มุกดาหาร", "แม่ฮ่องสอน",
    "ยโสธร", "ยะลา", "ร้อยเอ็ด", "ระนอง", "ระยอง", "ราชบุรี", "ลพบุรี",
    "ลำปาง", "ลำพูน", "เลย", "ศรีสะเกษ", "สกลนคร", "สงขลา", "สตูล",
    "สมุทรปราการ", "สมุทรสงคราม", "สมุทรสาคร", "สระแก้ว", "สระบุรี",
    "สิงห์บุรี", "สุโขทัย", "สุพรรณบุรี", "สุราษฎร์ธานี", "สุรินทร์",
    "หนองคาย", "หนองบัวลำภู", "อ่างทอง", "อำนาจเจริญ", "อุดรธานี",
    "อุตรดิตถ์", "อุทัยธานี", "อุบลราชธานี",
})

# Province informal nicknames and variations to canonical name
PROVINCE_ALIASES: dict[str, str] = {
    "อยุธยา": "พระนครศรีอยุธยา",
    "กรุงเทพ": "กรุงเทพมหานคร",
    "กทม": "กรุงเทพมหานคร",
    "กทม.": "กรุงเทพมหานคร",
    "โคราช": "นครราชสีมา",
    "แปดริ้ว": "ฉะเชิงเทรา",
    "ปากน้ำ": "สมุทรปราการ",
    "เมืองคอน": "นครศรีธรรมราช",
}

# Common prominent districts/amphoe mapped to province
DISTRICT_TO_PROVINCE: dict[str, str] = {
    "หาดใหญ่": "สงขลา",
    "สะเดา": "สงขลา",
    "เมืองสงขลา": "สงขลา",
    "จะนะ": "สงขลา",
    "เทพา": "สงขลา",
    "นาทวี": "สงขลา",
    "ศรีสาคร": "นราธิวาส",
    "สุไหงโก-ลก": "นราธิวาส",
    "สุไหงโกลก": "นราธิวาส",
    "ตากใบ": "นราธิวาส",
    "ระแงะ": "นราธิวาส",
    "รือเสาะ": "นราธิวาส",
    "บาเจาะ": "นราธิวาส",
    "เจาะไอร้อง": "นราธิวาส",
    "ยี่งอ": "นราธิวาส",
    "เวียงสา": "น่าน",
    "แม่จริม": "น่าน",
    "ปัว": "น่าน",
    "ท่าวังผา": "น่าน",
    "เมืองน่าน": "น่าน",
    "นาน้อย": "น่าน",
    "สันติสุข": "น่าน",
    "บ่อเกลือ": "น่าน",
    "ฝาง": "เชียงใหม่",
    "แม่ริม": "เชียงใหม่",
    "สันทราย": "เชียงใหม่",
    "หางดง": "เชียงใหม่",
    "ดอยสะเก็ด": "เชียงใหม่",
    "จอมทอง": "เชียงใหม่",
    "เชียงดาว": "เชียงใหม่",
    "แม่แตง": "เชียงใหม่",
    "เมืองเชียงใหม่": "เชียงใหม่",
    "แม่สาย": "เชียงราย",
    "เชียงแสน": "เชียงราย",
    "แม่จัน": "เชียงราย",
    "เทิง": "เชียงราย",
    "เมืองเชียงราย": "เชียงราย",
    "หัวหิน": "ประจวบคีรีขันธ์",
    "ปราณบุรี": "ประจวบคีรีขันธ์",
    "เมืองประจวบคีรีขันธ์": "ประจวบคีรีขันธ์",
    "เบตง": "ยะลา",
    "บันนังสตา": "ยะลา",
    "รามัน": "ยะลา",
    "เมืองยะลา": "ยะลา",
    "บางละมุง": "ชลบุรี",
    "พัทยา": "ชลบุรี",
    "ศรีราชา": "ชลบุรี",
    "สัตหีบ": "ชลบุรี",
    "เมืองชลบุรี": "ชลบุรี",
    "พานทอง": "ชลบุรี",
    "บางปะอิน": "พระนครศรีอยุธยา",
    "เสนา": "พระนครศรีอยุธยา",
    "บางไทร": "พระนครศรีอยุธยา",
    "วังน้อย": "พระนครศรีอยุธยา",
    "อุทัย": "พระนครศรีอยุธยา",
    "นครหลวง": "พระนครศรีอยุธยา",
    "ถลาง": "ภูเก็ต",
    "กะทู้": "ภูเก็ต",
    "เมืองภูเก็ต": "ภูเก็ต",
    "เกาะสมุย": "สุราษฎร์ธานี",
    "เกาะพะงัน": "สุราษฎร์ธานี",
    "บ้านดอน": "สุราษฎร์ธานี",
    "เมืองสุราษฎร์ธานี": "สุราษฎร์ธานี",
}

# Notable sub-locations / landmarks / venues mapped to (sub_location_name, district, province)
LANDMARK_MAP: dict[str, tuple[str, str | None, str | None]] = {
    "วัดพนัญเชิง": ("วัดพนัญเชิง", "พระนครศรีอยุธยา", "พระนครศรีอยุธยา"),
    "วัดใหญ่ชัยมงคล": ("วัดใหญ่ชัยมงคล", "พระนครศรีอยุธยา", "พระนครศรีอยุธยา"),
    "วัดพระแก้ว": ("วัดพระแก้ว", "พระนคร", "กรุงเทพมหานคร"),
    "ดอยสุเทพ": ("ดอยสุเทพ", "เมืองเชียงใหม่", "เชียงใหม่"),
    "ดอยอินทนนท์": ("ดอยอินทนนท์", "จอมทอง", "เชียงใหม่"),
    "แม่น้ำเจ้าพระยา": ("แม่น้ำเจ้าพระยา", None, None),
    "แม่น้ำป่าสัก": ("แม่น้ำป่าสัก", None, "พระนครศรีอยุธยา"),
    "แม่น้ำน่าน": ("แม่น้ำน่าน", None, "น่าน"),
    "แม่น้ำปิง": ("แม่น้ำปิง", None, "เชียงใหม่"),
    "แม่น้ำยม": ("แม่น้ำยม", None, "สุโขทัย"),
    "แม่น้ำวัง": ("แม่น้ำวัง", None, "ลำปาง"),
    "กว๊านพะเยา": ("กว๊านพะเยา", "เมืองพะเยา", "พะเยา"),
    "มูโนะ": ("มูโนะ", "สุไหงโก-ลก", "นราธิวาส"),
    "เกาะพีพี": ("เกาะพีพี", "เมืองกระบี่", "กระบี่"),
}

# Canonical entity alias dictionary
ENTITY_ALIASES: dict[str, str] = {
    "บิ๊กต่าย": "กิตติ์รัฐ พันธุ์เพ็ชร์",
    "พล.ต.อ.กิตติ์รัฐ": "กิตติ์รัฐ พันธุ์เพ็ชร์",
    "พล.ต.อ.กิตติ์รัฐ พันธุ์เพ็ชร์": "กิตติ์รัฐ พันธุ์เพ็ชร์",
    "บิ๊กต่อ": "ต่อศักดิ์ สุขวิมล",
    "พล.ต.อ.ต่อศักดิ์": "ต่อศักดิ์ สุขวิมล",
    "บิ๊กโจ๊ก": "สุรเชษฐ์ หักพาล",
    "พล.ต.อ.สุรเชษฐ์": "สุรเชษฐ์ หักพาล",
    "นายกฯ อิ๊งค์": "แพทองธาร ชินวัตร",
    "นายกอิ๊งค์": "แพทองธาร ชินวัตร",
    "อุ๊งอิ๊ง": "แพทองธาร ชินวัตร",
    "อุ๊งอิ๊งค์": "แพทองธาร ชินวัตร",
    "แพทองธาร": "แพทองธาร ชินวัตร",
    "แพทองธาร ชินวัตร": "แพทองธาร ชินวัตร",
    "เศรษฐา": "เศรษฐา ทวีสิน",
    "นายกฯ นิด": "เศรษฐา ทวีสิน",
    "เศรษฐา ทวีสิน": "เศรษฐา ทวีสิน",
    "พิธา": "พิธา ลิ้มเจริญรัตน์",
    "ทิม พิธา": "พิธา ลิ้มเจริญรัตน์",
    "สตช.": "สำนักงานตำรวจแห่งชาติ",
    "สำนักงานตำรวจแห่งชาติ": "สำนักงานตำรวจแห่งชาติ",
    "ผบ.ตร.": "ผบ.ตร.",
}


def normalize_thai_text(text: str) -> str:
    """
    Standardize Thai text:
    - Convert Thai digits (๐-๙) to Arabic digits (0-9).
    - Remove zero-width spaces and invisible formatting tokens.
    - Expand standard Thai news acronyms (e.g. รพ., สภ., สน., กทม.).
    - Collapse excessive spaces.
    """
    if not text:
        return ""

    # Translate Thai digits
    t = text.translate(_THAI_DIGIT_MAP)

    # Strip zero-width chars
    t = _ZERO_WIDTH_PATTERN.sub("", t)

    # Standardize acronyms
    for pattern, replacement in _ACRONYM_MAP:
        t = pattern.sub(replacement, t)

    # Collapse duplicate whitespace
    t = _WHITESPACE_COLLAPSE.sub(" ", t).strip()
    return t


def resolve_entity_alias(entity: str) -> str:
    """
    Map entity surface mentions/nicknames to canonical name representation.
    """
    clean = entity.strip().strip(" \t\n\r()[]{}\"'“”‘’«»,;:-_")
    if not clean:
        return ""
    if clean in ENTITY_ALIASES:
        return ENTITY_ALIASES[clean]
    if clean in PROVINCE_ALIASES:
        return PROVINCE_ALIASES[clean]
    return clean


def canonicalize_province(name: str) -> str | None:
    """
    Strip prefix ('จ.', 'จังหวัด') and return canonical 77 province name if recognized.
    """
    raw = name.strip()
    # Strip common prefixes
    for prefix in ("จังหวัด", "จ."):
        if raw.startswith(prefix):
            raw = raw[len(prefix):].strip()
            break

    if raw in THAI_PROVINCES:
        return raw
    if raw in PROVINCE_ALIASES:
        return PROVINCE_ALIASES[raw]
    return None


def canonicalize_district(name: str) -> str | None:
    """
    Strip prefix ('อ.', 'อำเภอ', 'เขต') and return canonical district name if recognized.
    """
    raw = name.strip()
    for prefix in ("อำเภอ", "อ.", "เขต"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):].strip()
            break

    if raw in DISTRICT_TO_PROVINCE:
        return raw
    return None


def parse_thai_locations(locations: list[str] | str) -> dict[str, list[str]]:
    """
    Classify input location entities into hierarchical levels:
    - 'provinces': Canonical 77 provinces
    - 'districts': Canonical districts / amphoe
    - 'sub_locations': Specific venues, temples, rivers, subdistricts
    """
    if isinstance(locations, str):
        candidates = [locations]
    else:
        candidates = list(locations)

    found_provinces: list[str] = []
    found_districts: list[str] = []
    found_sub_locations: list[str] = []

    for item in candidates:
        if not item or not isinstance(item, str):
            continue
        clean = item.strip()
        if not clean:
            continue

        # Check landmarks first
        matched_landmark = False
        for lm_name, (sub_loc, dist, prov) in LANDMARK_MAP.items():
            if lm_name in clean:
                if sub_loc not in found_sub_locations:
                    found_sub_locations.append(sub_loc)
                if dist and dist not in found_districts:
                    found_districts.append(dist)
                if prov and prov not in found_provinces:
                    found_provinces.append(prov)
                matched_landmark = True
                break
        if matched_landmark:
            continue

        # Check if province
        prov = canonicalize_province(clean)
        if prov:
            if prov not in found_provinces:
                found_provinces.append(prov)
            continue

        # Check if district
        dist = canonicalize_district(clean)
        if dist:
            if dist not in found_districts:
                found_districts.append(dist)
            mapped_prov = DISTRICT_TO_PROVINCE.get(dist)
            if mapped_prov and mapped_prov not in found_provinces:
                found_provinces.append(mapped_prov)
            continue

        # Check subdistrict prefix ('ต.', 'ตำบล') or venue prefix ('วัด', 'แยก', 'สะพาน', 'ถนน', 'ถ.')
        if clean.startswith(("ต.", "ตำบล", "วัด", "แยก", "สะพาน", "แม่น้ำ", "เกาะ", "ดอย", "ถ.", "ถนน", "โรงพยาบาล", "รพ.")):
            if clean not in found_sub_locations:
                found_sub_locations.append(clean)
            continue

        # General location fallback if it contains province names
        for p in THAI_PROVINCES:
            if p in clean:
                if p not in found_provinces:
                    found_provinces.append(p)
                break

    return {
        "provinces": found_provinces,
        "districts": found_districts,
        "sub_locations": found_sub_locations,
    }


def is_province_only_match(locs_a: dict[str, list[str]], locs_b: dict[str, list[str]]) -> bool:
    """
    Returns True if the only overlap between two location sets is at the province level
    (e.g., both mention 'เชียงใหม่' or 'อยุธยา', but zero shared districts and zero shared sub-locations).
    """
    prov_a = set(locs_a.get("provinces", []))
    prov_b = set(locs_b.get("provinces", []))
    dist_a = set(locs_a.get("districts", []))
    dist_b = set(locs_b.get("districts", []))
    sub_a = set(locs_a.get("sub_locations", []))
    sub_b = set(locs_b.get("sub_locations", []))

    shared_provinces = prov_a & prov_b
    shared_districts = dist_a & dist_b
    shared_sub = sub_a & sub_b

    # If they share at least one province, but NO districts and NO sub-locations
    return bool(shared_provinces and not shared_districts and not shared_sub)


def has_sublocation_conflict(locs_a: dict[str, list[str]], locs_b: dict[str, list[str]]) -> bool:
    """
    Returns True if both events specify locations that contradict each other:
    1. Both specify districts within the same province, but different ones (e.g. 'ฝาง' vs 'แม่ริม').
    2. Both specify distinct provinces and have zero province overlap.
    """
    prov_a = set(locs_a.get("provinces", []))
    prov_b = set(locs_b.get("provinces", []))
    dist_a = set(locs_a.get("districts", []))
    dist_b = set(locs_b.get("districts", []))

    # Case 1: Distinct provinces and zero overlap
    if prov_a and prov_b and not (prov_a & prov_b):
        return True

    # Case 2: In same province, but different non-overlapping districts
    return bool((prov_a & prov_b) and dist_a and dist_b and not (dist_a & dist_b))
