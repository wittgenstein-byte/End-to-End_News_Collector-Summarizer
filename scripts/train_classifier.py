"""
scripts/train_classifier.py
─────────────────────────────────────────────────────────────────
Training and evaluation pipeline for 9-category Thai News Classifier
using ThaiSum and Prachathai-67k datasets.

Target 9 Categories:
- politics
- economy
- technology
- health
- environment
- sports
- entertainment
- society
- world
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import csv
import random
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

import joblib
from pythainlp.corpus import thai_stopwords
from pythainlp.tokenize import word_tokenize
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.svm import LinearSVC

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

csv.field_size_limit(2147483647)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "datasets"
MODEL_DIR = BASE_DIR / "backend" / "model"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

STOPWORDS = set(thai_stopwords())

# ── Category Ground-Truth Rules ──────────────────────────────────
CATEGORY_RULES = {
    "politics": {
        "tags": [
            "การเมือง", "เลือกตั้ง", "politics", "politic", "ข่าวการเมือง",
            "ประยุทธ์ จันทร์โอชา", "คสช.", "กกต.", "รัฐสภา", "รัฐบาล", "พรรคการเมือง",
            "ส.ส.", "ส.ว.", "ประชาธิปไตย", "ชุมนุม", "ม็อบ", "อภิปรายไม่ไว้วางใจ",
            "ร่าง พ.ร.บ.", "พ.ร.บ.", "นายกรัฐมนตรี", "นายกฯ", "ยุบสภา", "ศาลรัฐธรรมนูญ",
            "พรรคก้าวไกล", "พรรคเพื่อไทย", "พรรคพลังประชารัฐ", "พรรคประชาธิปัตย์",
            "มติ ครม.", "คณะรัฐมนตรี", "ทำเนียบรัฐบาล", "รัฐมนตรี"
        ],
        "url_cues": ["/politic", "/politics", "/election", "/parliament", "/governance"]
    },
    "economy": {
        "tags": [
            "เศรษฐกิจ", "การเงิน", "ธุรกิจ", "economy", "business", "finance", "economics",
            "ข่าวเศรษฐกิจ", "ตลาดหุ้น", "หุ้น", "การลงทุน", "ธนาคาร", "เงินเฟ้อ", "ราคาทอง",
            "ราคาน้ำมัน", "งบประมาณ", "ส่งออก", "นำเข้า", "อุตสาหกรรม", "ภาษี", "cryptocurrency",
            "บิตคอยน์", "คนละครึ่ง", "เราไม่ทิ้งกัน", "กสิกร", "ธปท.", "พาณิชย์", "อัตราดอกเบี้ย"
        ],
        "url_cues": ["/economy", "/economic", "/business", "/finance", "/money", "/market", "/stock", "/trade", "/crypto", "/investment"]
    },
    "technology": {
        "tags": [
            "ไอซีที", "ไอที", "เทคโนโลยี", "ดิจิทัล", "tech", "technology", "digital",
            "นวัตกรรม", "สมาร์ทโฟน", "มือถือ", "แกดเจ็ต", "ปัญญาประดิษฐ์", "ai", "5g",
            "คอมพิวเตอร์", "อินเทอร์เน็ต", "แอปพลิเคชัน", "แอป", "กสทช.", "ไซเบอร์",
            "บล็อกเชน", "หุ่นยนต์", "ไอโฟน", "ซอฟต์แวร์", "ฮาร์ดแวร์", "สตาร์ทอัพ",
            "หัวเว่ย", "ซัมซุง", "แอปเปิ้ล", "กูเกิล", "ไมโครซอฟท์"
        ],
        "url_cues": ["/tech", "/technology", "/digital", "/cyber", "/gadget", "/innovation", "/it/"]
    },
    "health": {
        "tags": [
            "สุขภาพ", "สาธารณสุข", "การแพทย์", "health", "medical", "medicine", "อนามัย",
            "โควิด-19", "ไวรัสโคโรนา", "ไวรัสโคโรน่า", "covid-19", "covid", "ไวรัสอู่ฮั่น",
            "วัคซีน", "โรงพยาบาล", "แพทย์", "หมอ", "พยาบาล", "โรคระบาด", "ผู้ป่วย",
            "มะเร็ง", "รักษาโรค", "หน้ากากอนามัย", "กระทรวงสาธารณสุข", "สธ.", "กรมควบคุมโรค",
            "ยารักษาโรค", "ติดเชื้อ", "กักตัว", "swab", "pcr"
        ],
        "url_cues": ["/health", "/healthcare", "/medical", "/medicine", "/wellness", "/covid", "/vaccine"]
    },
    "environment": {
        "tags": [
            "สิ่งแวดล้อม", "environment", "climate", "โลกร้อน", "สภาพภูมิอากาศ",
            "มลพิษ", "pm2.5", "ฝุ่นพิษ", "พลังงานสะอาด", "พลังงานหมุนเวียน",
            "ป่าไม้", "ขยะ", "รีไซเคิล", "ก๊าซเรือนกระจก", "คาร์บอน", "สัตว์ป่า",
            "อนุรักษ์ธรรมชาติ", "ทรัพยากรธรรมชาติ"
        ],
        "url_cues": ["/environment", "/climate", "/green", "/eco", "/sustainability", "/nature", "/pollution", "/pm25"]
    },
    "sports": {
        "tags": [
            "กีฬา", "กีฬาอื่นๆ", "ฟุตบอลยุโรป", "ไทยรัฐเชียร์ไทยแลนด์", "ข่าวกีฬา",
            "ฟุตบอล", "sport", "sports", "football", "soccer", "พรีเมียร์ลีก",
            "ชี้มวยเด็ด", "ชัย ศิษย์อาจารย์บี้", "มวย", "โอลิมปิก", "วอลเลย์บอล",
            "แมนยู", "ลิเวอร์พูล", "ซีเกมส์", "เอเชียนเกมส์", "กอล์ฟ", "เทนนิส", "แบดมินตัน"
        ],
        "url_cues": ["/sport", "/sports", "/football", "/soccer", "/premier-league", "/olympics", "/boxing"]
    },
    "entertainment": {
        "tags": [
            "บันเทิง", "ข่าวบันเทิง", "ดารา", "entertainment", "entertain", "ภาพยนตร์",
            "เพลง", "ละคร", "ซีรีส์", "ศิลปิน", "นักร้อง", "คอนเสิร์ต", "โสมชบา",
            "โสมชบาจ๊ะจ๋า", "นิยาย", "เรื่องย่อละคร", "วงการบันเทิง", "เน็ตฟลิกซ์",
            "movie", "music", "celebrity", "showbiz"
        ],
        "url_cues": ["/entertain", "/entertainment", "/movie", "/music", "/celebrity", "/drama", "/series", "/showbiz"]
    },
    "world": {
        "tags": [
            "ต่างประเทศ", "world", "foreign", "international", "รอบโลก", "ข่าวต่างประเทศ",
            "สหรัฐ", "จีน", "รัสเซีย", "สหรัฐอเมริกา", "ญี่ปุ่น", "เกาหลีใต้", "ฮ่องกง",
            "ยุโรป", "อังกฤษ", "อาเซียน", "สหประชาชาติ", "ยูเครน", "สงคราม", "ทรัมป์", "ไบเดน"
        ],
        "url_cues": ["/world", "/foreign", "/international", "/global", "/around-the-world", "/overseas"]
    },
    "society": {
        "tags": [
            "สังคม", "สิทธิมนุษยชน", "คุณภาพชีวิต", "วัฒนธรรม", "การศึกษา", "แรงงาน",
            "อาชญากรรม", "ไลฟ์สไตล์", "ผู้หญิง", "ความมั่นคง", "ทั่วไทย", "ภูมิภาค",
            "ข่าวทั่วไป", "ข่าวทั่วไทย", "ข่าวภูมิภาค", "ข่าวสังคม", "กระบวนการยุติธรรม",
            "ตำรวจ", "ศาล", "อุบัติเหตุ", "ศาสนา", "ประเพณี", "เชียงใหม่", "กวีประชาไท",
            "น้ำท่วม", "ภัยแล้ง", "ภัยธรรมชาติ", "ไฟป่า", "แผ่นดินไหว", "พายุ"
        ],
        "url_cues": ["/lifestyle", "/living", "/life", "/local", "/society", "/social", "/education", "/crime", "/culture"]
    }
}

SPECIFIC_CATS = {"health", "technology", "sports", "entertainment", "environment", "world", "economy", "politics"}
GENERIC_URL_CUES = {"/local", "/society", "/social", "/lifestyle", "/living", "/life"}

TAG_TO_CAT: dict[str, str] = {}
for cat, data in CATEGORY_RULES.items():
    for t in data["tags"]:
        TAG_TO_CAT[t.lower()] = cat

URL_CUES: list[tuple[str, str]] = []
for cat, data in CATEGORY_RULES.items():
    for cue in data["url_cues"]:
        URL_CUES.append((cue.lower(), cat))


def label_article(item_type: str, item_tags: str, url: str, title: str = "") -> str | None:
    """Label article into 1 of 9 categories based on URL, Type, Tags, and Title."""
    # 1. Specific URL cues
    if url:
        u = unquote(url).lower()
        for cue, cat in URL_CUES:
            if cue not in GENERIC_URL_CUES and cue in u:
                return cat

    # 2. Specific domain tags
    all_tags: list[str] = []
    if item_type:
        all_tags.extend([t.strip().lower() for t in item_type.split(",") if t.strip()])
    if item_tags:
        all_tags.extend([t.strip().lower() for t in item_tags.split(",") if t.strip()])

    matched_cats = [TAG_TO_CAT[t] for t in all_tags if t in TAG_TO_CAT]
    for c in matched_cats:
        if c in SPECIFIC_CATS:
            return c

    # 3. Check title keywords
    if title:
        title_lower = title.lower()
        if any(k in title_lower for k in [
            "โควิด", "covid", "วัคซีน", "โรงพยาบาล", "การแพทย์", "สาธารณสุข", "อนามัย",
            "ติดเชื้อ", "รักษาโรค", "มะเร็ง", "กรมควบคุมโรค", "ไวรัสโคโรนา", "ผู้ป่วย", "สธ."
        ]):
            return "health"
        if any(k in title_lower for k in [
            "สมาร์ทโฟน", "แอปพลิเคชัน", "ปัญญาประดิษฐ์", "นวัตกรรม", "ไอที", "เทคโนโลยี",
            "หุ่นยนต์", "ไอโฟน", "คอมพิวเตอร์", "ดิจิทัล", "5g", "บล็อกเชน", "ไซเบอร์", "แอป", "มือถือ"
        ]):
            return "technology"
        if any(k in title_lower for k in [
            "นายกฯ", "นายกรัฐมนตรี", "คณะรัฐมนตรี", "ครม.", "รัฐสภา", "สภาผู้แทน", "อภิปราย", "พ.ร.บ.", "ศาลรัฐธรรมนูญ", "รัฐบาล", "พรรค", "เลือกตั้ง"
        ]):
            return "politics"
        if any(k in title_lower for k in [
            "ฟุตบอล", "พรีเมียร์ลีก", "กีฬา", "แชมป์", "โอลิมปิก", "ซีเกมส์", "นักกีฬา", "ผลบอล"
        ]):
            return "sports"
        if any(k in title_lower for k in [
            "สิ่งแวดล้อม", "โลกร้อน", "pm 2.5", "pm2.5", "มลพิษ", "พลังงานสะอาด", "ก๊าซเรือนกระจก"
        ]):
            return "environment"

    # 4. Generic URL cues
    if url:
        u = unquote(url).lower()
        for cue, cat in URL_CUES:
            if cue in u:
                return cat

    if matched_cats:
        return matched_cats[0]

    return None


def thai_tokenize_doc(text: str) -> str:
    """Tokenize Thai text and filter stopwords, returning space-separated tokens."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text.lower().strip())
    tokens = word_tokenize(text, engine="newmm")
    cleaned_tokens = [
        tok.strip()
        for tok in tokens
        if tok.strip() and len(tok.strip()) > 1 and tok.strip() not in STOPWORDS and not tok.strip().isnumeric()
    ]
    return " ".join(cleaned_tokens)


def load_dataset(samples_per_class: int = 800) -> tuple[list[str], list[str]]:
    """Load and balance dataset across all 9 categories from ThaiSum and Prachathai."""
    print("Loading data from ThaiSum and Prachathai...")
    categorized_samples: dict[str, list[str]] = {cat: [] for cat in CATEGORY_RULES}

    # 1. Load ThaiSum (Validation & Test) - High quality mainstream news
    thaisum_files = [DATA_DIR / "thaisum_val.csv", DATA_DIR / "thaisum_test.csv"]
    for fpath in thaisum_files:
        if not fpath.exists():
            continue
        print(f"Reading {fpath.name}...")
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                title = (row.get("title") or "").strip()
                cat = label_article(row.get("type", ""), row.get("tags", ""), row.get("url", ""), title=title)
                if not cat:
                    continue
                summary = (row.get("summary") or "").strip()
                body = (row.get("body") or "").strip()
                snippet = summary if summary else body[:300]
                content = f"{title} {title} {snippet}"
                if len(content) < 20:
                    continue
                categorized_samples[cat].append(content)

    # 2. Load Technology (ICT) and Environment from Prachathai-67k
    prachathai_file = DATA_DIR / "prachathai_67k.csv"
    if prachathai_file.exists():
        print(f"Reading {prachathai_file.name} for ICT / Technology...")
        with open(prachathai_file, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                labels_raw = row.get("labels", "")
                if "ไอซีที" in labels_raw or "เทคโนโลยี" in labels_raw:
                    title = (row.get("title") or "").strip()
                    body = (row.get("body_text") or "").strip()
                    content = f"{title} {title} {body[:300]}"
                    if len(content) >= 20:
                        categorized_samples["technology"].append(content)

    print("\nTotal Collected Samples per Category:")
    for cat, items in categorized_samples.items():
        print(f"  {cat:15s}: {len(items):,}")

    # Balance samples
    random.seed(42)
    X: list[str] = []
    y: list[str] = []

    for cat, items in categorized_samples.items():
        if len(items) > samples_per_class:
            sampled = random.sample(items, samples_per_class)
        else:
            sampled = items
        X.extend(sampled)
        y.extend([cat] * len(sampled))

    print(f"\nFinal Balanced Dataset: {len(X):,} total samples")
    class_counts = Counter(y)
    for cat, cnt in sorted(class_counts.items()):
        print(f"  {cat:15s}: {cnt:,}")

    return X, y


def main():
    X_raw, y = load_dataset(samples_per_class=800)

    print("\nTokenizing Thai texts with PyThaiNLP (newmm)...")
    X_tokens = [thai_tokenize_doc(doc) for doc in X_raw]

    # Filter any empty docs
    valid_data = [(x, label) for x, label in zip(X_tokens, y) if len(x.strip()) > 0]
    X_tokens = [item[0] for item in valid_data]
    y = [item[1] for item in valid_data]

    # Train / Test Split (80% Train, 20% Test)
    X_train, X_test, y_train, y_test = train_test_split(
        X_tokens, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"Train size: {len(X_train):,}, Test size: {len(X_test):,}")

    # Feature Extraction (TF-IDF)
    print("\nBuilding TF-IDF Vectorizer (max_features=25000, ngram_range=(1,2))...")
    vectorizer = TfidfVectorizer(
        max_features=25000,
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=2,
    )
    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec = vectorizer.transform(X_test)
    print(f"TF-IDF Feature Space: {X_train_vec.shape[1]:,} features")

    # ── Model 1: Standard LinearSVC ──────────────────────────────
    print("\n" + "=" * 60)
    print("Training Model 1: LinearSVC (C=1.0)...")
    svm_model = LinearSVC(C=1.0, random_state=42)
    svm_model.fit(X_train_vec, y_train)
    y_pred_svm = svm_model.predict(X_test_vec)
    acc_svm = accuracy_score(y_test, y_pred_svm)
    f1_svm = f1_score(y_test, y_pred_svm, average="macro")
    print(f"LinearSVC Accuracy: {acc_svm:.4f} | Macro F1: {f1_svm:.4f}")

    # ── Model 2: Logistic Regression ─────────────────────────────
    print("\n" + "=" * 60)
    print("Training Model 2: Logistic Regression (C=1.0)...")
    lr_model = LogisticRegression(C=1.0, max_iter=500, random_state=42)
    lr_model.fit(X_train_vec, y_train)
    y_pred_lr = lr_model.predict(X_test_vec)
    acc_lr = accuracy_score(y_test, y_pred_lr)
    f1_lr = f1_score(y_test, y_pred_lr, average="macro")
    print(f"Logistic Regression Accuracy: {acc_lr:.4f} | Macro F1: {f1_lr:.4f}")

    # ── Model 3: Calibrated LinearSVC (Outputs true Probabilities) ──
    print("\n" + "=" * 60)
    print("Training Model 3: CalibratedClassifierCV(LinearSVC) for true probabilities...")
    calibrated_svm = CalibratedClassifierCV(LinearSVC(C=1.0, random_state=42), cv=3)
    calibrated_svm.fit(X_train_vec, y_train)
    y_pred_cal = calibrated_svm.predict(X_test_vec)
    acc_cal = accuracy_score(y_test, y_pred_cal)
    f1_cal = f1_score(y_test, y_pred_cal, average="macro")
    print(f"Calibrated LinearSVC Accuracy: {acc_cal:.4f} | Macro F1: {f1_cal:.4f}")

    # ── Detailed Classification Report of Best Model ─────────────
    best_model = calibrated_svm if f1_cal >= f1_svm else svm_model
    best_pred = y_pred_cal if f1_cal >= f1_svm else y_pred_svm
    best_name = "Calibrated LinearSVC" if f1_cal >= f1_svm else "LinearSVC"

    print("\n" + "=" * 60)
    print(f"BEST MODEL BENCHMARK REPORT: {best_name}")
    print("=" * 60)
    print(classification_report(y_test, best_pred, digits=4))

    # ── Save Models ──────────────────────────────────────────────
    vec_path = MODEL_DIR / "tfidf_vectorizer.pkl"
    svm_path = MODEL_DIR / "svm_classifier.pkl"
    
    print(f"Saving vectorizer to {vec_path}...")
    joblib.dump(vectorizer, vec_path, compress=3)

    print(f"Saving classifier to {svm_path}...")
    joblib.dump(best_model, svm_path, compress=3)

    print("\n[SUCCESS] Model training and export completed successfully!")


if __name__ == "__main__":
    main()
