"""
services/classifier_service.py
─────────────────────────────────────────────────────────────────

SOLID  S — classify text เท่านั้น ไม่รู้จัก HTTP / storage
SOLID  O — เพิ่มหมวดใหม่ได้โดยเพิ่ม entry ใน _RULES ไม่แก้ logic
GRASP  Information Expert — รู้จัก keyword ของแต่ละหมวด
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations
from pythainlp.tokenize import word_tokenize

# ── URL Priority Rules ────────────────────────────────────────────
_URL_CUES = {
    "/sport": "sports",
    "-sport": "sports",
    "sport-": "sports",
    "/entertainment": "entertainment",
    "/foreign": "world",
    "/world": "world",
    "/tech": "technology",
    "/health": "health",
    "/society": "society",
    "/environment": "environment"
}

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
        "oil","fuel","petrol","diesel","commodity","labor","employment","wage","salary","unemployment",
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
        "มลพิษ","โซลาร์","ลม","ฝุ่น","pm2.5","ความหลากหลาย",
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
        "เซปักตะกร้อ","เอเชียนเกมส์","ซีเกมส์","ชนะ", "แพ้", "เสมอ", "ถล่ม", "แต้ม", "ตารางคะแนน",
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

# ── Compound rules (AND logic) ────────────────────────────────────
# เพิ่มมิติของบริบทเข้าไปใน Rule เช่น "พลังงาน" ถ้านำไปใช้ร่วมกับคำอื่นๆ
_COMPOUND_RULES: dict[str, list[tuple[str, ...]]] = {
    "economy": [
        ("พลังงาน", "วิกฤต"),
        ("พลังงาน", "ราคา"),
        ("พลังงาน", "แพง"),
        ("พลังงาน", "ต้นทุน"),
        ("พลังงาน", "ขาดแคลน"),
        ("พลังงาน", "ค่าไฟ"),
        ("พลังงาน", "ค่าน้ำมัน"),
        ("พลังงาน", "นโยบาย"),
        ("energy", "shortage"),
    ("fuel", "shortage"),
    ],
    "environment": [
        ("พลังงาน", "สะอาด"),
        ("พลังงาน", "ทดแทน"),
        ("พลังงาน", "หมุนเวียน"),
        ("พลังงาน", "แสงอาทิตย์"),
        ("พลังงาน", "ลม"),
        ("พลังงาน", "น้ำ"),
        ("พลังงาน", "ยั่งยืน"),
        ("พลังงาน", "สีเขียว"),
    ]
}

# หมวดที่ใช้เป็น fallback เมื่อ score = 0 ทุกหมวด
_DEFAULT_CATEGORY = "society"


# Pre-tokenize เพื่อลดภาระโหลดและเพิ่มความเร็วแบบสุดขีด
_TOKENIZED_RULES: dict[str, list[tuple[str, list[str]]]] = {}
for cat, kw_list in _RULES.items():
    _TOKENIZED_RULES[cat] = [(kw.lower(), word_tokenize(kw.lower())) for kw in kw_list]

_TOKENIZED_COMPOUND_RULES: dict[str, list[list[list[str]]]] = {}
for cat, rules in _COMPOUND_RULES.items():
    _TOKENIZED_COMPOUND_RULES[cat] = []
    for rule in rules:
        # เก็บเป็น list ของ list of tokens สำหรับแต่ละกลุ่มคำ
        _TOKENIZED_COMPOUND_RULES[cat].append([word_tokenize(w.lower()) for w in rule])


# ── ML Models Loading ─────────────────────────────────────────────
from pathlib import Path
import joblib

_BASE_DIR = Path(__file__).resolve().parent.parent

try:
    _TFIDF = joblib.load(_BASE_DIR / "model" / "tfidf_vectorizer.pkl")
    _SVM = joblib.load(_BASE_DIR / "model" / "svm_classifier.pkl")
except Exception as e:
    _TFIDF = None
    _SVM = None
    print(f"Warning: ML model not loaded: {e}")

_ML_MAPPING = {
    "economics": "economy",
    "politics": "politics",
    "social": "society"
}
_ML_EXPERTISE = set(_ML_MAPPING.values())

def predict_with_ml(text: str) -> tuple[str, str, float]:
    """ฟังก์ชันเรียกใช้โมเดล SVM และคืนค่า (หมวด, วิธีคิด, ความมั่นใจ)"""
    if _TFIDF is None or _SVM is None:
        return _DEFAULT_CATEGORY, "ML (Failed to load)", 0.0
    try:
        # ตัดข้อความให้เหลือแค่ 500 คำแรก (ป้องกัน Max Sequence Length และการตีความไกลกู่ไม่กลับ)
        cropped_text = " ".join(text.split()[:500])
        vec = _TFIDF.transform([cropped_text])
        
        # 1. ลองหาความมั่นใจ (Confidence Score)
        if hasattr(_SVM, "predict_proba"):
            probs = _SVM.predict_proba(vec)[0]
            max_idx = probs.argmax()
            conf = float(probs[max_idx])
            pred_label = _SVM.classes_[max_idx]
        elif hasattr(_SVM, "decision_function"):
            # สำหรับ LinearSVC ที่ไม่มี proba เราใช้ Softmax แปลงจาก Decision Score
            import numpy as np
            scores = _SVM.decision_function(vec)[0]
            # กรณี Binary class (1 score) vs Multi-class (n scores)
            if hasattr(scores, "__len__"):
                e_x = np.exp(scores - np.max(scores))
                probs = e_x / e_x.sum()
                max_idx = probs.argmax()
                conf = float(probs[max_idx])
                pred_label = _SVM.classes_[max_idx]
            else:
                # Binary class
                conf = 1.0 / (1.0 + np.exp(-abs(scores)))
                pred_label = _SVM.classes_[1] if scores > 0 else _SVM.classes_[0]
        else:
            pred_label = _SVM.predict(vec)[0]
            conf = 0.6 # หรือตั้งค่ากลางๆ ไว้
            
        return _ML_MAPPING.get(pred_label, _DEFAULT_CATEGORY), f"ML ({pred_label})", conf
    except Exception:
        return _DEFAULT_CATEGORY, "ML (Error)", 0.0

# ── Main classifier ───────────────────────────────────────────────

def classify_article(title: str, summary: str = "", url: str = "") -> tuple[str, str]:
    """
    ใช้งานง่ายแบบ one-stop: โยน (title, summary, url) เข้ามา
    ให้ความสำคัญกับ URL ก่อน (Fast-path Priority)
    ถ้าไม่มีก็เอา title + summary มารวมกันแบบถ่วงน้ำหนัก (title * 3)
    และคืนค่า (category_id, classification_method)
    """
    if url:
        url_lower = url.lower()
        for cue, cat in _URL_CUES.items():
            if cue in url_lower:
                return cat, f"URL Priority ({cue})"

    combined = f"{title} {title} {title} {summary}"
    return classify(combined)

def classify(text: str) -> tuple[str, str]:
    """
    จำแนกข้อความเป็น 1 ใน 9 หมวด พร้อมบอกว่าแยกด้วยวิธีไหน
    คืนค่า (category_id, classification_method)
    """
    if not text or not text.strip():
        return _DEFAULT_CATEGORY, "Fallback (Empty Text)"

    lower = text.lower()
    # ตัดคำเพื่อแก้ปัญหา Substring matching (เช่น "น้ำ" ไปตรงกับใน "น้ำมัน")
    tokens = word_tokenize(lower)
    tokens_set = set(tokens)
    
    scores: dict[str, float] = {}

    for category, tokenized_kws in _TOKENIZED_RULES.items():
        score = 0.0
        
        # 1. ให้คะแนนจาก Keyword เดี่ยว หรือ N-gram แบบติดกัน
        for kl, kw_tokens in tokenized_kws:
            count = 0
            if len(kw_tokens) == 1:
                # เช็กแบบ Exact Match เป็นชิ้นๆ
                count = tokens.count(kw_tokens[0])
            elif len(kw_tokens) > 1:
                # เช็กแบบ Exact Match สำหรับกลุ่มคำ (phrase)
                kw_len = len(kw_tokens)
                for i in range(len(tokens) - kw_len + 1):
                    if tokens[i:i+kw_len] == kw_tokens:
                        count += 1
                        
            if count > 0:
                # คำยาวกว่า 4 ตัวอักษร → น้ำหนัก 2x
                weight = 2.0 if len(kl) > 4 else 1.0
                score += count * weight
                
        # 2. ให้คะแนนจาก Compound Rules (บริบทร่วม - ไม่จำเป็นต้องอยู่ติดกัน)
        if category in _TOKENIZED_COMPOUND_RULES:
            for rule_tokens_list in _TOKENIZED_COMPOUND_RULES[category]:
                valid = True
                for word_parts in rule_tokens_list:
                    # ตรวจว่าทุก token ในคำย่อยนั้นอยู่ใน text ที่ถูกตัดคำแล้วหรือไม่
                    if not all(p in tokens_set for p in word_parts):
                        valid = False
                        break
                
                if valid:
                    # ตรงตามเงื่อนไข AND จับคู่ได้ทุกคำ จะได้คะแนนพิเศษ
                    score += 5.0  # ให้คะแนนสูงพิเศษเพราะบริบทชัดเจน
                    
        scores[category] = score

    # 3. Routing Logic (ระบบจราจรที่ "ดีขึ้นจริง" - รองรับ Full Text Markdown)
    
    # หาหมวดอันดับ 1 และอันดับ 2
    sorted_cats = sorted(scores.keys(), key=lambda c: scores[c], reverse=True)
    top1 = sorted_cats[0]
    top2 = sorted_cats[1] if len(sorted_cats) > 1 else None
    
    score1 = scores[top1]
    score2 = scores[top2] if top2 else 0.0

    # --- ด่านที่ 1: ตรวจสอบหมวดนอกเหนือจาก ML (Fast-Track) ---
    # ถ้า Rule-based บอกว่าเป็นหมวดที่ ML ไม่รู้จัก (Sports, Entertainment, World, ฯลฯ)
    # และคะแนนห่างจากที่ 2 พอสมควร (>= 5.0 เพื่อกันคะแนนเฟ้อจากข่าวที่เนื้อหายาว) 
    # ห้ามส่งให้ ML ตรวจเด็ดขาด! เพราะ ML จะพาออกทะเล
    if top1 not in _ML_EXPERTISE and (score1 - score2) >= 5.0:
        return top1, f"Rule-based (Domain Expert: {top1}, score={score1:.1f})"

    # --- ด่านที่ 2: ตรวจสอบหมวดที่ ML เชี่ยวชาญ หรือกรณีหา Keyword ไม่เจอ ---
    # เราจะเรียก ML เฉพาะเมื่อ:
    # 1. Rule-based บอกว่าเป็น Politics, Economy, Society (เพื่อให้ ML Verified บริบท)
    # 2. Rule-based หา Keyword ไม่เจอเลย (score1 == 0)
    
    ml_cat, ml_method, ml_conf = predict_with_ml(text)

    # กฎการตัดสินใจสุดท้าย:
    # ก) ถ้า ML มั่นใจพอ (>= 0.5) ให้เชื่อ ML (เพราะ ML เข้าใจบริบท 3 หมวดนี้ดีกว่า Rule-based)
    if ml_conf >= 0.5:
        return ml_cat, f"{ml_method} (conf={ml_conf:.2f})"
    
    # ข) ถ้า ML ไม่มั่นใจ (< 0.5) ให้กลับมาใช้ Rule-based ดั้งเดิม (ถ้ามีคะแนน) หรือ Default
    if score1 > 0:
        return top1, f"Rule-based (ML Low Confidence: {ml_conf:.2f})"

    return _DEFAULT_CATEGORY, f"Fallback (Default, ML conf: {ml_conf:.2f})"


def classify_article(title: str, summary: str = "", url: str = "") -> tuple[str, str]:
    """
    จำแนกบทความโดยเช็ก URL ก่อน ถ้าไม่มีค่อยรวม title + summary
    คืนค่า (category, method)
    """
    if url:
        url_lower = url.lower()
        for cue, cat in _URL_CUES.items():
            if cue in url_lower:
                return cat, f"URL Priority ({cue})"

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
        url = item.get("url", "")
        cat, method = classify_article(title, summary, url=url)
        item["category"] = cat
        item["classification_method"] = method
        updated += 1
    return updated
