"""
services/classifier_service.py
─────────────────────────────────────────────────────────────────

SOLID  S — classify text เท่านั้น ไม่รู้จัก HTTP / storage
SOLID  O — เพิ่มหมวดใหม่ได้โดยเพิ่ม entry ใน _RULES ไม่แก้ logic
GRASP  Information Expert — รู้จัก keyword ของแต่ละหมวด
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from urllib.parse import unquote, urlparse

from pythainlp.tokenize import word_tokenize

# ── URL Priority Rules ────────────────────────────────────────────
_URL_CUES: dict[str, str] = {
    # ── Politics ──────────────────────────────────────────────────────
    "/politics": "politics",
    "-politics": "politics",
    "politics-": "politics",
    "/politic": "politics",
    "-politic": "politics",
    "politic-": "politics",
    "/parliament": "politics",
    "/election": "politics",
    "/governance": "politics",
    "/การเมือง": "politics",
    "/รัฐบาล": "politics",
    "/เลือกตั้ง": "politics",
    "/สภา": "politics",

    # ── Economy / Business / Finance ──────────────────────────────────
    "/economy": "economy",
    "-economy": "economy",
    "economy-": "economy",
    "/economic": "economy",
    "-economic": "economy",
    "economic-": "economy",
    "/economics": "economy",
    "/business": "economy",
    "-business": "economy",
    "business-": "economy",
    "/finance": "economy",
    "-finance": "economy",
    "finance-": "economy",
    "/financial": "economy",
    "/money": "economy",
    "/wealth": "economy",
    "/market": "economy",
    "/stock": "economy",
    "/trade": "economy",
    "/crypto": "economy",
    "/investment": "economy",
    "/banking": "economy",
    "/เศรษฐกิจ": "economy",
    "/การเงิน": "economy",
    "/ธุรกิจ": "economy",
    "/หุ้น": "economy",
    "/การค้า": "economy",
    "/การลงทุน": "economy",

    # ── Technology ────────────────────────────────────────────────────
    "/technology": "technology",
    "-technology": "technology",
    "technology-": "technology",
    "/technologies": "technology",
    "/tech": "technology",
    "-tech": "technology",
    "tech-": "technology",
    "/digital": "technology",
    "-digital": "technology",
    "digital-": "technology",
    "/cyber": "technology",
    "-cyber": "technology",
    "/cyberbiz": "technology",
    "/gadget": "technology",
    "/innovation": "technology",
    "/it/": "technology",
    "/it-": "technology",
    "-it/": "technology",
    "/เทคโนโลยี": "technology",
    "/ดิจิทัล": "technology",
    "/ไซเบอร์": "technology",
    "/ไอที": "technology",
    "/นวัตกรรม": "technology",

    # ── Health ────────────────────────────────────────────────────────
    "/health": "health",
    "-health": "health",
    "health-": "health",
    "/healthcare": "health",
    "/medical": "health",
    "-medical": "health",
    "medical-": "health",
    "/medicine": "health",
    "/wellness": "health",
    "/covid": "health",
    "/vaccine": "health",
    "/disease": "health",
    "/สุขภาพ": "health",
    "/สาธารณสุข": "health",
    "/การแพทย์": "health",
    "/อนามัย": "health",

    # ── Environment ───────────────────────────────────────────────────
    "/environment": "environment",
    "-environment": "environment",
    "environment-": "environment",
    "/climate": "environment",
    "-climate": "environment",
    "climate-": "environment",
    "/green": "environment",
    "-green": "environment",
    "green-": "environment",
    "/eco": "environment",
    "-eco": "environment",
    "eco-": "environment",
    "/sustainability": "environment",
    "/nature": "environment",
    "/pollution": "environment",
    "/wildlife": "environment",
    "/pm25": "environment",
    "/pm2-5": "environment",
    "/สิ่งแวดล้อม": "environment",
    "/สภาพภูมิอากาศ": "environment",
    "/โลกร้อน": "environment",
    "/มลพิษ": "environment",

    # ── Society ───────────────────────────────────────────────────────
    "/society": "society",
    "-society": "society",
    "society-": "society",
    "/social": "society",
    "-social": "society",
    "social-": "society",
    "/education": "society",
    "-education": "society",
    "education-": "society",
    "/crime": "society",
    "-crime": "society",
    "crime-": "society",
    "/community": "society",
    "/culture": "society",
    "/lifestyle": "society",
    "-lifestyle": "society",
    "lifestyle-": "society",
    "/life": "society",
    "-life": "society",
    "life-": "society",
    "/living": "society",
    "/quality-of-life": "society",
    "/quality-life": "society",
    "/local": "society",
    "-local": "society",
    "local-": "society",
    "/สังคม": "society",
    "/การศึกษา": "society",
    "/อาชญากรรม": "society",
    "/คุณภาพชีวิต": "society",
    "/ไลฟ์สไตล์": "society",
    "/วัฒนธรรม": "society",
    "/ชุมชน": "society",
    "/ท้องถิ่น": "society",

    # ── Sports ────────────────────────────────────────────────────────
    "/sports": "sports",
    "-sports": "sports",
    "sports-": "sports",
    "/sport": "sports",
    "-sport": "sports",
    "sport-": "sports",
    "/football": "sports",
    "-football": "sports",
    "football-": "sports",
    "/soccer": "sports",
    "/premier-league": "sports",
    "/olympics": "sports",
    "/motorsport": "sports",
    "/tennis": "sports",
    "/golf": "sports",
    "/boxing": "sports",
    "/กีฬา": "sports",
    "/ฟุตบอล": "sports",
    "/มวย": "sports",
    "/ผลบอล": "sports",

    # ── Entertainment ─────────────────────────────────────────────────
    "/entertainment": "entertainment",
    "-entertainment": "entertainment",
    "entertainment-": "entertainment",
    "/entertain": "entertainment",
    "-entertain": "entertainment",
    "entertain-": "entertainment",
    "/pop/": "entertainment",
    "/pop-culture": "entertainment",
    "/pop-music": "entertainment",
    "/k-pop": "entertainment",
    "/kpop": "entertainment",
    "/t-pop": "entertainment",
    "/j-pop": "entertainment",
    "/movie": "entertainment",
    "/movies": "entertainment",
    "/music": "entertainment",
    "/celebrity": "entertainment",
    "/celeb": "entertainment",
    "/drama": "entertainment",
    "/series": "entertainment",
    "/showbiz": "entertainment",
    "/บันเทิง": "entertainment",
    "/ดารา": "entertainment",
    "/ละคร": "entertainment",
    "/ซีรีส์": "entertainment",
    "/เพลง": "entertainment",
    "/ภาพยนตร์": "entertainment",

    # ── World ─────────────────────────────────────────────────────────
    "/world": "world",
    "-world": "world",
    "world-": "world",
    "/foreign": "world",
    "-foreign": "world",
    "foreign-": "world",
    "/international": "world",
    "-international": "world",
    "international-": "world",
    "/global": "world",
    "-global": "world",
    "global-": "world",
    "/around-the-world": "world",
    "/overseas": "world",
    "/ต่างประเทศ": "world",
    "/รอบโลก": "world",
    "/อินเตอร์": "world",
    "/ข่าวต่างประเทศ": "world",
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
        "กอ.รมน.","ความมั่นคง","ฝ่ายความมั่นคง","กองทัพ","ทหาร",
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
        "หมอ","พยาบาล","คลินิก","การรักษา","รักษาพยาบาล","ยารักษาโรค","วิธีรักษา","ผ่าตัด","วิจัย",
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


# ── ML & Transformer Models Loading ──────────────────────────────
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent

try:
    import joblib  # type: ignore[import-untyped]
    _TFIDF = joblib.load(_BASE_DIR / "model" / "tfidf_vectorizer.pkl")
    _SVM = joblib.load(_BASE_DIR / "model" / "svm_classifier.pkl")
except Exception as e:
    _TFIDF = None
    _SVM = None
    print(f"Warning: ML model not loaded: {e}")

_WANGCHAN_DIR = _BASE_DIR / "model" / "wangchanberta_classifier"
_WANGCHAN_TOKENIZER = None
_WANGCHAN_MODEL = None


def get_wangchanberta():
    """Lazy load WangchanBERTa model safely by verifying all required files exist."""
    global _WANGCHAN_TOKENIZER, _WANGCHAN_MODEL
    if _WANGCHAN_MODEL is not None and _WANGCHAN_TOKENIZER is not None:
        return _WANGCHAN_TOKENIZER, _WANGCHAN_MODEL

    if not _WANGCHAN_DIR.exists():
        return None, None

    # 1. ตรวจสอบไฟล์ Config
    has_config = (_WANGCHAN_DIR / "config.json").exists()

    # 2. ตรวจสอบไฟล์ Model Weights (ต้องมี safetensors หรือ bin)
    has_weights = (
        (_WANGCHAN_DIR / "model.safetensors").exists()
        or (_WANGCHAN_DIR / "pytorch_model.bin").exists()
    )

    # 3. ตรวจสอบไฟล์ Tokenizer (ต้องมี SentencePiece หรือ tokenizer.json)
    has_tokenizer = (
        (_WANGCHAN_DIR / "sentencepiece.bpe.model").exists()
        or (_WANGCHAN_DIR / "tokenizer.json").exists()
    )

    # หากไฟล์ไม่ครบ ให้ข้ามทันทีโดยไม่ต้องเสียเวลาเสี่ยงรัน from_pretrained
    if not (has_config and has_weights and has_tokenizer):
        return None, None

    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        _WANGCHAN_TOKENIZER = AutoTokenizer.from_pretrained(str(_WANGCHAN_DIR), use_fast=False)
        _WANGCHAN_MODEL = AutoModelForSequenceClassification.from_pretrained(str(_WANGCHAN_DIR))
        _WANGCHAN_MODEL.eval()
        return _WANGCHAN_TOKENIZER, _WANGCHAN_MODEL
    except Exception as e:
        print(f"Warning: WangchanBERTa failed to load: {e}")
        return None, None


_ML_MAPPING = {
    "politics": "politics",
    "economy": "economy",
    "economics": "economy",
    "technology": "technology",
    "health": "health",
    "environment": "environment",
    "sports": "sports",
    "entertainment": "entertainment",
    "society": "society",
    "social": "society",
    "world": "world",
}
_ML_EXPERTISE = set(_RULES.keys())


def predict_with_wangchanberta(text: str) -> tuple[str, str, float] | None:
    """ทำนายหมวดหมู่ด้วยโมเดล Fine-tuned WangchanBERTa (Deep Learning Transformer)"""
    tokenizer, model = get_wangchanberta()
    if tokenizer is None or model is None:
        return None

    try:
        import torch

        inputs = tokenizer(
            text,
            truncation=True,
            max_length=128,
            padding=True,
            return_tensors="pt",
        )
        with torch.no_grad():
            outputs = model(**inputs)
            logits = outputs.logits
            probs = torch.softmax(logits, dim=1)[0]
            max_idx = int(torch.argmax(probs).item())
            conf = float(probs[max_idx].item())
            pred_label = model.config.id2label[max_idx]

        category = _ML_MAPPING.get(pred_label, _DEFAULT_CATEGORY)
        return category, f"WangchanBERTa ({pred_label})", conf
    except Exception:
        return None


# ── Denoising phrases for ML ───────────────────────────────────────
# คำบอกเล่าข่าวโซเชียลทั่วไปที่ชอบเบี่ยงคะแนน TF-IDF เข้า Technology โดยไม่ตั้งใจ
_DENOISE_PHRASES = (
    "ในโลกออนไลน์",
    "โลกออนไลน์",
    "ชาวเน็ต",
    "โซเชียลมีเดีย",
    "โลกโซเชียล",
    "เพจดัง",
    "เพจเฟซบุ๊ก",
    "คลิปไวรัล",
    "แชร์ว่อน",
    "แห่แชร์",
    "คอมเมนต์",
)

# ── High-Specificity Domain Cues ──────────────────────────────────
# คำเฉพาะทางระดับสูงที่ระบุหมวดหมู่ชัดเจนในหัวข้อข่าว (Title Priority)
_HIGH_SPECIFICITY_CUES: dict[str, tuple[str, ...]] = {
    "politics": (
        "กอ.รมน.", "กอ.รมน.ภาค", "ความมั่นคง", "ชายแดนใต้", "ศอ.บต.",
        "รัฐสภา", "สภาผู้แทนราษฎร", "วุฒิสภา", "อภิปรายไม่ไว้วางใจ",
        "นายกรัฐมนตรี", "คณะรัฐมนตรี", "ยุบสภา", "เลือกตั้งซ่อม",
        "พรรคการเมือง", "กฎหมายประชามติ", "ศาลรัฐธรรมนูญ", "ป.ป.ช.",
    ),
    "environment": (
        "น้ำท่วม", "อุทกภัย", "น้ำป่าไหลหลาก", "น้ำป่า", "แม่น้ำเอ่อล้น", "น้ำล้นตลิ่ง",
        "ดินถล่ม", "โคลนถล่ม", "พายุหมุน", "พายุดีเปรสชัน", "ไต้ฝุ่น", "สึนามิ",
        "แผ่นดินไหว", "pm2.5", "pm 2.5", "มลพิษทางอากาศ", "วิกฤตโลกร้อน", "ภาวะโลกร้อน",
        "ก๊าซเรือนกระจก", "ปะการังฟอกขาว", "ไฟป่า", "ภัยแล้ง", "ภัยพิบัติ",
    ),
    "technology": (
        "ยานยนต์ไฟฟ้า", "รถยนต์ไฟฟ้า", "รถ ev", "รถยนต์ ev", "วิศวกรรมยานยนต์ไฟฟ้า",
        "ปัญญาประดิษฐ์", "generative ai", "chatgpt", "ชิปเซ็ต", "เซมิคอนดักเตอร์",
        "ไมโครชิป", "ไซเบอร์ซีเคียวริตี้", "แฮกเกอร์", "ควอนตัมคอมพิวเตอร์",
        "บล็อกเชน", "สมาร์ทโฟนเรือธง", "ระบบ 5g", "ปัญญาประดิษฐ์ ai",
    ),
    "entertainment": (
        "นักแสดง", "ดาราสาว", "ดาราชาย", "นักร้อง", "วงการบันเทิง", "คู่รักดารา",
        "เตียงหัก", "แฉแหลก", "เมียน้อย", "ละครดัง", "ซีรีส์ดัง",
        "แฟนมีตติ้ง", "คอนเสิร์ต", "ภาพยนตร์ใหม่", "บ็อกซ์ออฟฟิศ", "เพลงฮิต",
        "อัลบั้มใหม่", "เปิดตัวภาพยนตร์", "เปิดตัวซีรีส์", "นางเอก", "พระเอก",
        "ดาราดัง", "เปิ้ล ไอริณ", "ไอริณ",
    ),
    "sports": (
        "ฟุตบอล", "พรีเมียร์ลีก", "ไทยลีก", "ผลบอล", "ยูฟ่า", "แชมเปียนส์ลีก",
        "วอลเลย์บอล", "โอลิมปิก", "ซีเกมส์", "เอเชียนเกมส์", "เหรียญทอง",
        "มวยไทย", "ฟอร์มูล่าวัน", "formula 1", "แบดมินตัน",
    ),
    "health": (
        "กระทรวงสาธารณสุข", "กรมควบคุมโรค", "องค์การอนามัยโลก", "วัคซีน",
        "โรคระบาด", "ไข้หวัดใหญ่", "ติดเชื้อ", "มะเร็ง", "ยารักษาโรค",
        "แพทย์เตือน", "โรงพยาบาล", "ผู้ป่วย",
    ),
}


def predict_with_ml(text: str) -> tuple[str, str, float]:
    """ฟังก์ชันเรียกใช้โมเดล SVM/LinearSVC และคืนค่า (หมวด, วิธีคิด, ความมั่นใจ)"""
    if _TFIDF is None or _SVM is None:
        return _DEFAULT_CATEGORY, "ML (Failed to load)", 0.0
    try:
        lower = text.lower().strip()
        # กรองคำเล่าเรื่องโซเชียลมีเดียทั่วไปออก เพื่อไม่ให้บิดเบือนคะแนนไปหมวด technology
        for phrase in _DENOISE_PHRASES:
            lower = lower.replace(phrase, " ")

        tokens = word_tokenize(lower, engine="newmm")
        cleaned_tokens = [
            tok.strip()
            for tok in tokens
            if tok.strip() and len(tok.strip()) > 1 and not tok.strip().isnumeric()
        ]
        token_str = " ".join(cleaned_tokens[:500])
        vec = _TFIDF.transform([token_str])

        # 1. ลองหาความมั่นใจ (Confidence Score)
        if hasattr(_SVM, "predict_proba"):
            probs = _SVM.predict_proba(vec)[0]
            max_idx = probs.argmax()
            conf = float(probs[max_idx])
            pred_label = _SVM.classes_[max_idx]
        elif hasattr(_SVM, "decision_function"):
            import numpy as np
            scores = _SVM.decision_function(vec)[0]
            if hasattr(scores, "__len__"):
                e_x = np.exp(scores - np.max(scores))
                probs = e_x / e_x.sum()
                max_idx = probs.argmax()
                conf = float(probs[max_idx])
                pred_label = _SVM.classes_[max_idx]
            else:
                conf = 1.0 / (1.0 + np.exp(-abs(scores)))
                pred_label = _SVM.classes_[1] if scores > 0 else _SVM.classes_[0]
        else:
            pred_label = _SVM.predict(vec)[0]
            conf = 0.6

        category = _ML_MAPPING.get(pred_label, _DEFAULT_CATEGORY)
        return category, f"ML ({pred_label})", conf
    except Exception:
        return _DEFAULT_CATEGORY, "ML (Error)", 0.0

# ── URL and Main Classifier ───────────────────────────────────────

def get_category_from_url(url: str) -> tuple[str, str] | None:
    """
    ตรวจจับหมวดหมู่จาก URL (Fast-path Tier 1)
    - รองรับการ decode percent-encoded (เช่น %E0%B8%81%E0%B8%B2%E0%B8%A3%E0%B9%80%E0%B8%A1%E0%B8%B7%E0%B8%AD%E0%B8%87)
    - ตรวจ path segment ที่ตรงกับ cue หรือหมวดหมู่ตรงๆ
    - ตรวจ substring patterns ใน URL path + query
    คืนค่า (category_id, method_description) หรือ None ถ้าไม่ตรงกับหมวดใด
    """
    if not url or not isinstance(url, str):
        return None

    try:
        decoded_url = unquote(url).lower().strip()
        parsed = urlparse(decoded_url)

        # 0. Domain Lock / Priority (e.g. techhub.in.th -> technology)
        if "techhub.in.th" in decoded_url or "techhub.in.th" in (parsed.netloc or ""):
            return "technology", "Domain Priority (techhub.in.th)"

        path = parsed.path.rstrip("/")

        # 1. เช็ก exact path segment จากขวาไปซ้าย (leaf category สำคัญที่สุด เช่น /category/culture/entertainment -> entertainment)
        segments = [s.strip() for s in path.split("/") if s.strip()]
        for seg in reversed(segments):
            seg_slash = f"/{seg}"
            if seg_slash in _URL_CUES:
                return _URL_CUES[seg_slash], f"URL Priority ({seg_slash})"
            if seg in _URL_CUES:
                return _URL_CUES[seg], f"URL Priority ({seg})"

        # 2. เช็ก pattern cues ใน decoded URL path + query
        path_query = f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path
        for cue, cat in _URL_CUES.items():
            if cue in path_query:
                return cat, f"URL Priority ({cue})"

        # 3. เช็กใน decoded_url ทั้งหมดเป็น fallback
        for cue, cat in _URL_CUES.items():
            if cue in decoded_url:
                return cat, f"URL Priority ({cue})"
    except Exception:
        pass

    return None


def classify(text: str) -> tuple[str, str]:
    """
    จำแนกข้อความเป็น 1 ใน 9 หมวด พร้อมบอกว่าแยกด้วยวิธีไหน
    Flow การทำงานแบบ Hybrid Architecture:
    1. Fast Primary Engine (Calibrated LinearSVC): ประมวลผลรวดเร็ว (~2ms)
       - ถ้า LinearSVC มั่นใจสูง (conf >= 0.50) -> คืนผลลัพธ์ของ LinearSVC ทันที
    2. Deep Learning Escalation (WangchanBERTa):
       - ถ้า LinearSVC มั่นใจน้อย (< 0.50) -> ส่งต่อให้ WangchanBERTa วิเคราะห์บริบทเชิงลึก
       - ถ้า WangchanBERTa โหลดได้และมั่นใจ (conf >= 0.35) -> คืนผลลัพธ์ของ WangchanBERTa
    3. Fallback to LinearSVC:
       - ถ้า WangchanBERTa ไม่พร้อมหรือมั่นใจต่ำ -> ใช้ LinearSVC (ถ้า conf >= 0.25)
    4. Fallback Engine: Keyword & Compound Rules (กรณีทุกโมเดลไม่มั่นใจ < 0.25)
    5. Default Fallback: 'society'
    """
    if not text or not text.strip():
        return _DEFAULT_CATEGORY, "Fallback (Empty Text)"

    # 1. รัน Fast Primary Engine (Calibrated LinearSVC)
    ml_cat, ml_method, ml_conf = predict_with_ml(text)

    # ก) ถ้า LinearSVC มั่นใจสูง (>= 0.50) ให้ใช้ผลของ LinearSVC ทันที (Fast-path ~2ms)
    if ml_conf >= 0.50 and not ml_method.startswith("ML (Failed") and not ml_method.startswith("ML (Error"):
        return ml_cat, f"{ml_method} (conf={ml_conf:.2f})"

    # 2. ถ้า LinearSVC มั่นใจน้อย (< 0.50) ส่งต่อให้ WangchanBERTa ช่วยตัดสินแบบ Hybrid
    wb_result = predict_with_wangchanberta(text)
    if wb_result is not None:
        wb_cat, wb_method, wb_conf = wb_result
        if wb_conf >= 0.35:
            return wb_cat, f"Hybrid: {wb_method} (conf={wb_conf:.2f}, SVC={ml_conf:.2f})"

    # 3. ถ้า WangchanBERTa ไม่พร้อมหรือมั่นใจต่ำ แต่ LinearSVC ยังพอมีความมั่นใจ (>= 0.25)
    if ml_conf >= 0.25 and not ml_method.startswith("ML (Failed") and not ml_method.startswith("ML (Error"):
        return ml_cat, f"{ml_method} (conf={ml_conf:.2f})"

    # 4. Fallback Engine: Keyword & Compound Rules
    lower = text.lower()
    tokens = word_tokenize(lower)
    tokens_set = set(tokens)

    scores: dict[str, float] = {}
    for category, tokenized_kws in _TOKENIZED_RULES.items():
        score = 0.0
        for kl, kw_tokens in tokenized_kws:
            count = 0
            if len(kw_tokens) == 1:
                count = tokens.count(kw_tokens[0])
            elif len(kw_tokens) > 1:
                kw_len = len(kw_tokens)
                for i in range(len(tokens) - kw_len + 1):
                    if tokens[i:i+kw_len] == kw_tokens:
                        count += 1
            if count > 0:
                weight = 2.0 if len(kl) > 4 else 1.0
                score += count * weight

        if category in _TOKENIZED_COMPOUND_RULES:
            for rule_tokens_list in _TOKENIZED_COMPOUND_RULES[category]:
                valid = True
                for word_parts in rule_tokens_list:
                    if not all(p in tokens_set for p in word_parts):
                        valid = False
                        break
                if valid:
                    score += 5.0

        scores[category] = score

    sorted_cats = sorted(scores.keys(), key=lambda c: scores[c], reverse=True)
    top1 = sorted_cats[0]
    score1 = scores[top1]

    if score1 > 0:
        return top1, f"Rule-based (ML Low Confidence Fallback: {ml_conf:.2f})"

    return _DEFAULT_CATEGORY, f"Fallback (Default, ML conf: {ml_conf:.2f})"


def get_category_from_cues(cues: list[str] | str | None) -> tuple[str, str] | None:
    """
    ตรวจจับหมวดหมู่จาก Category Cues (เช่น hidden URLs ใน DOM, breadcrumbs, RSS categories)
    คืนค่า (category_id, method_description) หรือ None ถ้าไม่ตรง
    """
    if not cues:
        return None

    cue_list = [cues] if isinstance(cues, str) else list(cues)

    for raw_cue in cue_list:
        if not raw_cue or not isinstance(raw_cue, str):
            continue
        cue = raw_cue.strip()
        if not cue:
            continue

        # 1. ถ้า cue เป็น URL หรือ path (เช่น https://thestandard.co/category/pop/ หรือ /category/politics)
        if "/" in cue or "." in cue:
            url_match = get_category_from_url(cue)
            if url_match:
                cat, _ = url_match
                return cat, f"Category Cue ({cue})"

        # 2. ตรวจสอบชื่อหมวดหมู่ภาษาไทย / ภาษาอังกฤษตรงๆ
        cue_lower = cue.lower()
        if cue_lower in _VALID_CATEGORIES:
            return cue_lower, f"Category Cue ({cue})"

        # Check in _URL_CUES (e.g. "การเมือง", "บันเทิง", "เศรษฐกิจ", "politics")
        if cue_lower in _URL_CUES:
            return _URL_CUES[cue_lower], f"Category Cue ({cue})"
        cue_slash = f"/{cue_lower}"
        if cue_slash in _URL_CUES:
            return _URL_CUES[cue_slash], f"Category Cue ({cue})"

        # 3. ตรวจสอบ High Specificity Cues ก่อนเสมอ
        for cat, h_cues in _HIGH_SPECIFICITY_CUES.items():
            for h_cue in h_cues:
                if h_cue in cue_lower:
                    return cat, f"Category Cue ({cue})"

        # 4. Check if cue matches keywords in _RULES (exact or specific phrase length >= 6)
        for cat, kws in _RULES.items():
            for kw in kws:
                kw_l = kw.lower()
                if kw_l == cue_lower or (len(kw_l) >= 6 and kw_l in cue_lower):
                    return cat, f"Category Cue ({cue})"

    return None


def classify_article(
    title: str,
    summary: str = "",
    url: str = "",
    category_cues: list[str] | str | None = None,
) -> tuple[str, str]:
    """
    จำแนกบทความโดยเช็ก:
    1. URL Priority (Tier 1: Fast-path จาก Main Article URL)
    2. Hidden Category Cues (Tier 1.5: จาก Hidden URLs ใน DOM, breadcrumbs, RSS categories)
    3. High-Specificity Domain Cues ในหัวข้อข่าว (Title Domain Cues)
    4. Primary ML Classifier (Tier 2: LinearSVC / WangchanBERTa)
    5. Fallback Keyword Rules (Tier 3)
    """
    # 1. Main Article URL
    if url:
        url_match = get_category_from_url(url)
        if url_match:
            return url_match

    # 2. Hidden Category URLs & DOM/RSS Cues
    if category_cues:
        cue_match = get_category_from_cues(category_cues)
        if cue_match:
            return cue_match

    # 3. ตรวจสอบ High-Specificity Cues ในหัวข้อข่าว (Title Priority)
    title_lower = (title or "").lower()
    for cat, cues in _HIGH_SPECIFICITY_CUES.items():
        for cue in cues:
            if cue in title_lower:
                return cat, f"Rule ({cat})"

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
        has_method = bool(item.get("classification_method"))
        if not force and current in _VALID_CATEGORIES and has_method:
            continue
        title = (item.get("title") or "").strip()
        summary = (item.get("summary") or "").strip()
        url = item.get("url", "")
        category_cues = item.get("category_cues")
        cat, method = classify_article(title, summary, url=url, category_cues=category_cues)
        item["category"] = cat
        item["classification_method"] = method
        updated += 1
    return updated
