"""
scripts/train_wangchanberta.py
─────────────────────────────────────────────────────────────────
Fine-tuning script for WangchanBERTa on 9-Category Thai News Classification.
Supports both CPU and GPU execution.

Model: airesearch/wangchanberta-base-att-spm-uncased
Output: backend/model/wangchanberta_classifier/
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

import numpy as np
import torch
from torch.optim import AdamW
from torch.utils.data import DataLoader, Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

csv.field_size_limit(2147483647)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "datasets"
MODEL_OUTPUT_DIR = BASE_DIR / "backend" / "model" / "wangchanberta_classifier"

CATEGORIES = [
    "economy",
    "entertainment",
    "environment",
    "health",
    "politics",
    "society",
    "sports",
    "technology",
    "world",
]

ID2LABEL = {i: cat for i, cat in enumerate(CATEGORIES)}
LABEL2ID = {cat: i for i, cat in enumerate(CATEGORIES)}

# ── Ground Truth Rules ──────────────────────────────────────────
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
    if url:
        u = unquote(url).lower()
        for cue, cat in URL_CUES:
            if cue not in GENERIC_URL_CUES and cue in u:
                return cat

    all_tags: list[str] = []
    if item_type:
        all_tags.extend([t.strip().lower() for t in item_type.split(",") if t.strip()])
    if item_tags:
        all_tags.extend([t.strip().lower() for t in item_tags.split(",") if t.strip()])

    matched_cats = [TAG_TO_CAT[t] for t in all_tags if t in TAG_TO_CAT]
    for c in matched_cats:
        if c in SPECIFIC_CATS:
            return c

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

    if url:
        u = unquote(url).lower()
        for cue, cat in URL_CUES:
            if cue in u:
                return cat

    if matched_cats:
        return matched_cats[0]

    return None


def clean_thai_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class NewsClassificationDataset(Dataset):
    def __init__(self, texts: list[str], labels: list[int], tokenizer, max_length: int = 128):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.texts)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        text = self.texts[idx]
        label = self.labels[idx]

        encoding = self.tokenizer(
            text,
            truncation=True,
            max_length=self.max_length,
            padding="max_length",
            return_tensors="pt",
        )

        item = {key: val.squeeze(0) for key, val in encoding.items()}
        item["labels"] = torch.tensor(label, dtype=torch.long)
        return item


def load_balanced_data(samples_per_class: int = 600) -> tuple[list[str], list[int]]:
    print("Loading data for WangchanBERTa...")
    categorized_samples: dict[str, list[str]] = {cat: [] for cat in CATEGORIES}

    # 1. ThaiSum
    for fpath in [DATA_DIR / "thaisum_val.csv", DATA_DIR / "thaisum_test.csv"]:
        if not fpath.exists():
            continue
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                title = (row.get("title") or "").strip()
                cat = label_article(row.get("type", ""), row.get("tags", ""), row.get("url", ""), title=title)
                if not cat:
                    continue
                summary = (row.get("summary") or "").strip()
                body = (row.get("body") or "").strip()
                snippet = summary if summary else body[:250]
                content = clean_thai_text(f"{title} {snippet}")
                if len(content) >= 20:
                    categorized_samples[cat].append(content)

    # 2. Prachathai (ICT/Technology)
    prachathai_file = DATA_DIR / "prachathai_67k.csv"
    if prachathai_file.exists():
        with open(prachathai_file, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                labels_raw = row.get("labels", "")
                if "ไอซีที" in labels_raw or "เทคโนโลยี" in labels_raw:
                    title = (row.get("title") or "").strip()
                    body = (row.get("body_text") or "").strip()
                    content = clean_thai_text(f"{title} {body[:250]}")
                    if len(content) >= 20:
                        categorized_samples["technology"].append(content)

    random.seed(42)
    X: list[str] = []
    y: list[int] = []

    for cat in CATEGORIES:
        items = categorized_samples[cat]
        if len(items) > samples_per_class:
            sampled = random.sample(items, samples_per_class)
        else:
            sampled = items
        X.extend(sampled)
        y.extend([LABEL2ID[cat]] * len(sampled))

    print(f"Loaded {len(X):,} samples across 9 categories.")
    for cat in CATEGORIES:
        cnt = y.count(LABEL2ID[cat])
        print(f"  {cat:15s}: {cnt:,}")

    return X, y


def train_epoch(model, dataloader, optimizer, scheduler, device):
    model.train()
    total_loss = 0.0

    for batch in dataloader:
        optimizer.zero_grad()
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        labels = batch["labels"].to(device)

        outputs = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            labels=labels,
        )

        loss = outputs.loss
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        scheduler.step()

        total_loss += loss.item()

    return total_loss / len(dataloader)


def evaluate(model, dataloader, device):
    model.eval()
    all_preds: list[int] = []
    all_labels: list[int] = []
    total_loss = 0.0

    with torch.no_grad():
        for batch in dataloader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)

            outputs = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=labels,
            )

            total_loss += outputs.loss.item()
            logits = outputs.logits
            preds = torch.argmax(logits, dim=1).cpu().numpy()
            all_preds.extend(preds)
            all_labels.extend(labels.cpu().numpy())

    acc = accuracy_score(all_labels, all_preds)
    f1 = f1_score(all_labels, all_preds, average="macro")
    avg_loss = total_loss / len(dataloader)
    return acc, f1, avg_loss, all_preds, all_labels


def main():
    parser = argparse.ArgumentParser(description="Fine-tune WangchanBERTa for News Classification")
    parser.add_argument("--epochs", type=int, default=2, help="Number of training epochs")
    parser.add_argument("--batch_size", type=int, default=8, help="Batch size")
    parser.add_argument("--lr", type=float, default=2e-5, help="Learning rate")
    parser.add_argument("--max_length", type=int, default=128, help="Max sequence length")
    parser.add_argument("--samples_per_class", type=int, default=400, help="Samples per category")
    parser.add_argument("--model_name", type=str, default="airesearch/wangchanberta-base-att-spm-uncased")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    # 1. Load Data
    X, y = load_balanced_data(samples_per_class=args.samples_per_class)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # 2. Tokenizer & Datasets
    print(f"Loading Tokenizer: {args.model_name}...")
    tokenizer = AutoTokenizer.from_pretrained(args.model_name, use_fast=False)

    train_dataset = NewsClassificationDataset(X_train, y_train, tokenizer, max_length=args.max_length)
    test_dataset = NewsClassificationDataset(X_test, y_test, tokenizer, max_length=args.max_length)

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=args.batch_size, shuffle=False)

    # 3. Model
    print(f"Loading Model: {args.model_name} (9 classes)...")
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model_name,
        num_labels=9,
        id2label=ID2LABEL,
        label2id=LABEL2ID,
    )
    model.to(device)

    # 4. Optimizer & Scheduler
    optimizer = AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    total_steps = len(train_loader) * args.epochs
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=int(total_steps * 0.1),
        num_training_steps=total_steps,
    )

    # 5. Training Loop
    print("\n" + "=" * 60)
    print(f"Starting Fine-Tuning ({args.epochs} Epochs, {len(train_loader)} batches/epoch)...")
    print("=" * 60)

    best_f1 = 0.0

    for epoch in range(1, args.epochs + 1):
        start_t = time.time()
        train_loss = train_epoch(model, train_loader, optimizer, scheduler, device)
        val_acc, val_f1, val_loss, preds, labels = evaluate(model, test_loader, device)
        elapsed = time.time() - start_t

        print(
            f"Epoch {epoch:02d}/{args.epochs:02d} [{elapsed:.1f}s] | "
            f"Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f} | "
            f"Val Acc: {val_acc:.4f} | Val Macro-F1: {val_f1:.4f}"
        )

        if val_f1 > best_f1:
            best_f1 = val_f1
            print(f"  -> Best model updated (Macro F1: {best_f1:.4f}). Saving to {MODEL_OUTPUT_DIR}...")
            MODEL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(MODEL_OUTPUT_DIR)
            tokenizer.save_pretrained(MODEL_OUTPUT_DIR)

    # 6. Final Evaluation
    print("\n" + "=" * 60)
    print("Final Model Benchmark Report:")
    print("=" * 60)
    target_names = [ID2LABEL[i] for i in range(9)]
    print(classification_report(labels, preds, target_names=target_names, digits=4))

    print(f"\n[SUCCESS] Fine-tuned WangchanBERTa saved to: {MODEL_OUTPUT_DIR}")


if __name__ == "__main__":
    main()
