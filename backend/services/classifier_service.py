"""
services/classifier_service.py
─────────────────────────────────────────────────────────────────

SOLID  S — classify text เท่านั้น ไม่รู้จัก HTTP / storage
SOLID  O — เพิ่มหมวดใหม่ได้โดยเพิ่ม entry ใน _RULES ไม่แก้ logic
GRASP  Information Expert — รู้จัก keyword ของแต่ละหมวด
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

# ── Keyword rules ─────────────────────────────────────────────────
# แต่ละหมวดมี Thai + English keywords
# น้ำหนัก: คำยาว (>4 ตัวอักษร) × 2, คำสั้น × 1

_RULES: dict[str, list[str]] = {
    "politics": [
        # Thai
        "การเมือง","รัฐสภา","สภา","รัฐบาล","นายก","รัฐมนตรี",
        "พรรค","เลือกตั้ง","ผู้สมัคร","ส.ส.","ส.ว.","กฎหมาย","ราชกิจจา",
        "กระทรวง","ทบวง","กรม","ปฏิวัติ","รัฐประหาร","ประชาธิปไตย",
        "นโยบาย","มติ","ร่าง พ.ร.บ.","พ.ร.บ.","สิทธิ","เสรีภาพ",
        # English
        "politics","parliament","government","minister","election",
        "senator","congress","vote","policy","legislation","bill",
        "democrat","republican","cabinet","prime minister","president",
        "referendum","constitution","coup","protest","rally",
    ],
    "economy": [
        # Thai
        "เศรษฐกิจ","ธนาคาร","หุ้น","ตลาด","ลงทุน","บาท","ดอลลาร์",
        "จีดีพี","เงินเฟ้อ","อัตราดอกเบี้ย","งบประมาณ","ส่งออก","นำเข้า",
        "การค้า","ภาษี","หนี้","ธปท.","ตลาดหุ้น","กสิกร","กรุงไทย",
        "ราคา","ต้นทุน","กำไร","รายได้","เงินทุน","สินค้า","บริการ", "น้ำมัน",
        "เอสเอ็มอี","วิสาหกิจ","อุตสาหกรรม","แรงงาน","จ้างงาน","สวัสดิการ","เงินเดือน","ค่าจ้าง",
        # English
        "economy","stock","market","investment","inflation","interest rate",
        "gdp","trade","bank","financial","revenue","profit","fiscal",
        "monetary","budget","forex","fund","startup","ipo","crypto",
        "recession","growth","export","import","tariff","tax","debt",
        "oil","commodity","labor","employment","wage","salary","unemployment",
    ],
    "technology": [
        # Thai
        "เทคโนโลยี","ปัญญาประดิษฐ์","ซอฟต์แวร์","แอปพลิเคชัน","สตาร์ทอัพ",
        "ดิจิทัล","ไซเบอร์","บล็อกเชน","คริปโต","เมตาเวิร์ส","โดรน",
        "หุ่นยนต์","อีวี","สมาร์ทโฟน","แท็บเล็ต","คอมพิวเตอร์","อินเทอร์เน็ต",
        "คลาวด์","บิ๊กดาต้า","แฮกเกอร์","ข้อมูล",
        # English
        "technology","ai","artificial intelligence","software","app","startup",
        "digital","cyber","blockchain","crypto","metaverse","robot","drone",
        "smartphone","chip","algorithm","cloud","data","machine learning",
        "deep learning","neural","openai","google","apple","microsoft",
        "samsung","tesla","spacex","electric vehicle","5g","quantum",
    ],
    "health": [
        # Thai
        "สุขภาพ","โรค","วัคซีน","โรงพยาบาล","แพทย์","ยา","ระบาด","ผู้ป่วย",
        "มะเร็ง","เบาหวาน","ความดัน","สาธารณสุข","อนามัย","กระทรวงสาธารณสุข",
        "หมอ","พยาบาล","คลินิก","รักษา","ผ่าตัด","วิจัย","ยา",
        "โควิด","ไข้หวัด","ไวรัส","แบคทีเรีย","เชื้อ","กักกัน",
        # English
        "health","disease","vaccine","hospital","doctor","medicine",
        "pandemic","patient","cancer","diabetes","virus","outbreak",
        "treatment","surgery","clinical","who","fda","mental health",
        "obesity","nutrition","exercise","drug","pharmaceutical",
    ],
    "environment": [
        # Thai
        "สิ่งแวดล้อม","ภูมิอากาศ","คาร์บอน","โลกร้อน","ป่าไม้","น้ำ",
        "มลพิษ","พลังงาน","โซลาร์","ลม","ฝุ่น","pm2.5","ความหลากหลาย",
        "ทะเล","ปะการัง","น้ำท่วม","แล้ง","แผ่นดินไหว","ไฟป่า",
        "รีไซเคิล","ขยะ","พลาสติก","สัตว์ป่า","อนุรักษ์",
        # English
        "environment","climate","carbon","global warming","forest","pollution",
        "energy","solar","wind","biodiversity","sustainability","emission",
        "greenhouse","recycling","flood","drought","earthquake","wildfire",
        "ocean","coral","plastic","wildlife","conservation","renewable",
        "cop","paris agreement","net zero",
    ],
    "society": [
        # Thai
        "สังคม","ชุมชน","ครอบครัว","การศึกษา","โรงเรียน","มหาวิทยาลัย",
        "นักเรียน","นักศึกษา","เด็ก","ผู้สูงอายุ","คนพิการ","ความยากจน",
        "อาชีพ","แรงงาน","การจ้างงาน","สวัสดิการ","ชนกลุ่มน้อย",
        "ศาสนา","วัฒนธรรม","ประเพณี","เทศกาล","สิทธิมนุษยชน","ความเท่าเทียม",
        # English
        "society","community","education","school","university","student",
        "family","poverty","welfare","labor","employment","inequality",
        "religion","culture","tradition","festival","human rights",
        "gender","diversity","immigration","homeless","social",
    ],
    "sports": [
        # Thai
        "ฟุตบอล","กีฬา","แข่งขัน","นักกีฬา","แชมป์","ลีก","ทีม",
        "โอลิมปิก","วอลเลย์บอล","บาสเกตบอล","มวย","เทนนิส","กอล์ฟ",
        "ว่ายน้ำ","วิ่ง","ไตรกีฬา","สนุกเกอร์","แบดมินตัน","มวยไทย",
        "เซปักตะกร้อ","เอเชียนเกมส์","ซีเกมส์",
        # English
        "football","soccer","basketball","tennis","golf","athlete",
        "championship","league","olympics","match","tournament","score",
        "win","loss","stadium","coach","transfer","premier league",
        "nba","nfl","formula 1","f1","swimming","marathon","boxing",
        "badminton","volleyball","cricket","rugby","cycling",
    ],
    "entertainment": [
        # Thai
        "ภาพยนตร์","ดารา","นักร้อง","คอนเสิร์ต","เพลง","ซีรีส์","รางวัล",
        "ละคร","อนิเมะ","สตรีมมิ่ง","ฮิต","บันเทิง","ศิลปิน","วงดนตรี",
        "อัลบั้ม","เปิดตัว","แฟนคลับ","ไอดอล","บ็อกซ์ออฟฟิศ",
        # English
        "movie","film","actor","singer","concert","music","series",
        "award","oscar","grammy","celebrity","entertainment","streaming",
        "album","netflix","youtube","spotify","box office","premiere",
        "trailer","k-pop","kdrama","anime","manga","game","esports",
    ],
    "world": [
        # Thai
        "สหรัฐ","จีน","รัสเซีย","ยุโรป","สหประชาชาติ","นาโต้","อาเซียน",
        "ทูต","สงคราม","ความขัดแย้ง","ทหาร","ระหว่างประเทศ","ต่างประเทศ",
        "ญี่ปุ่น","เกาหลี","อินเดีย","ออสเตรเลีย","อิสราเอล","อิหร่าน",
        "ยูเครน","ปาเลสไตน์","ตะวันออกกลาง","อาหรับ",
        # English
        "usa","china","russia","europe","united nations","nato","asean",
        "war","conflict","military","international","foreign","diplomat",
        "sanction","treaty","japan","korea","india","australia",
        "israel","iran","ukraine","palestine","middle east","africa",
        "latin america","summit","g7","g20","imf","world bank",
    ],
}

# หมวดที่ใช้เป็น fallback เมื่อ score = 0 ทุกหมวด
_DEFAULT_CATEGORY = "society"


# ── Main classifier ───────────────────────────────────────────────

def classify(text: str) -> str:
    """
    จำแนกข้อความเป็น 1 ใน 9 หมวด
    คืน category id เช่น "politics", "economy" ฯลฯ
    """
    if not text or not text.strip():
        return _DEFAULT_CATEGORY

    lower = text.lower()
    scores: dict[str, float] = {}

    for category, keywords in _RULES.items():
        score = 0.0
        for kw in keywords:
            kl = kw.lower()
            if kl in lower:
                # คำยาวกว่า 4 ตัวอักษร → น้ำหนัก 2x
                weight = 2.0 if len(kl) > 4 else 1.0
                # นับจำนวนครั้งที่พบ
                count = lower.count(kl)
                score += count * weight
        scores[category] = score

    best = max(scores, key=lambda c: scores[c])
    return best if scores[best] > 0 else _DEFAULT_CATEGORY


def classify_article(title: str, summary: str = "") -> str:
    """
    จำแนกบทความโดยรวม title + summary
    title มีน้ำหนักมากกว่า (× 3) เพราะกระชับและตรงประเด็น
    """
    combined = f"{title} {title} {title} {summary}"
    return classify(combined)


# ── Batch helpers ────────────────────────────────────────────────
_VALID_CATEGORIES = set(_RULES.keys())


def ensure_categories(news: list[dict], *, force: bool = False) -> int:
    """
    เติม/แก้ category ให้ข่าวใน news list
    - ถ้า force=False: จะเติมเฉพาะที่ไม่มีหรือไม่อยู่ใน list ที่รองรับ
    - ถ้า force=True : จะ re-classify ทั้งหมด
    คืนจำนวนรายการที่ถูกอัปเดต
    """
    updated = 0
    for item in news:
        if not isinstance(item, dict):
            continue
        current = item.get("category")
        if not force and current in _VALID_CATEGORIES:
            continue
        title = (item.get("title") or "").strip()
        summary = (item.get("summary") or "").strip()
        item["category"] = classify_article(title, summary)
        updated += 1
    return updated
