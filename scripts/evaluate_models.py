"""
scripts/evaluate_models.py
─────────────────────────────────────────────────────────────────
Comprehensive Evaluation and Comparison Script:
1. Calibrated LinearSVC (TF-IDF)
2. WangchanBERTa (Fine-tuned Transformer)
3. 3-Tier Unified Classifier System (Rules + ML)

Evaluates on 9 categories with Accuracy, Macro F1, Confusion Matrix,
and Latency Benchmarking.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import csv
import json
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

import joblib
import numpy as np
import torch
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from transformers import AutoModelForSequenceClassification, AutoTokenizer

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

csv.field_size_limit(2147483647)

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

DATA_DIR = BASE_DIR / "data" / "datasets"
MODEL_DIR = BASE_DIR / "backend" / "model"

from backend.services.classifier_service import (
    classify,
    classify_article,
    predict_with_ml,
    predict_with_wangchanberta,
)

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
LABEL2ID = {cat: i for i, cat in enumerate(CATEGORIES)}
ID2LABEL = {i: cat for i, cat in enumerate(CATEGORIES)}

from scripts.train_classifier import CATEGORY_RULES, label_article, thai_tokenize_doc


def load_test_dataset(samples_per_class: int = 800) -> tuple[list[str], list[str], list[str], list[str]]:
    """Loads balanced dataset and returns train/test splits."""
    print("Loading evaluation dataset from ThaiSum & Prachathai...")
    categorized_samples: dict[str, list[str]] = {cat: [] for cat in CATEGORY_RULES}

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
                snippet = summary if summary else body[:300]
                content = f"{title} {title} {snippet}"
                if len(content) >= 20:
                    categorized_samples[cat].append(content)

    # 2. Prachathai ICT
    prachathai_file = DATA_DIR / "prachathai_67k.csv"
    if prachathai_file.exists():
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

    random.seed(42)
    X: list[str] = []
    y: list[str] = []

    for cat in CATEGORIES:
        items = categorized_samples[cat]
        sampled = random.sample(items, min(samples_per_class, len(items)))
        X.extend(sampled)
        y.extend([cat] * len(sampled))

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"Total Test Set Samples: {len(X_test):,} ({len(X_test)//len(CATEGORIES)} per category)")
    return X_train, X_test, y_train, y_test


def evaluate_linearsvc(X_test: list[str], y_test: list[str]):
    print("\n" + "=" * 70)
    print("1. EVALUATING CALIBRATED LINEARSVC (TF-IDF)")
    print("=" * 70)

    t0 = time.time()
    y_pred = []
    for text in X_test:
        cat, _, _ = predict_with_ml(text)
        y_pred.append(cat)
    total_time = time.time() - t0
    latency_ms = (total_time / len(X_test)) * 1000

    acc = accuracy_score(y_test, y_pred)
    f1_macro = f1_score(y_test, y_pred, average="macro")
    f1_weighted = f1_score(y_test, y_pred, average="weighted")

    print(f"Accuracy:        {acc:.4f} ({acc*100:.2f}%)")
    print(f"Macro F1:        {f1_macro:.4f}")
    print(f"Weighted F1:     {f1_weighted:.4f}")
    print(f"Avg Latency:     {latency_ms:.2f} ms / article")
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, digits=4))

    cm = confusion_matrix(y_test, y_pred, labels=CATEGORIES)
    return {
        "name": "Calibrated LinearSVC",
        "accuracy": acc,
        "macro_f1": f1_macro,
        "weighted_f1": f1_weighted,
        "latency_ms": latency_ms,
        "cm": cm,
        "preds": y_pred,
    }


def evaluate_wangchanberta(X_test: list[str], y_test: list[str], max_eval_samples: int = 180):
    print("\n" + "=" * 70)
    print("2. EVALUATING WANGCHANBERTA (TRANSFORMER)")
    print("=" * 70)

    # Subsample for CPU latency if needed
    if len(X_test) > max_eval_samples:
        indices = np.linspace(0, len(X_test) - 1, max_eval_samples, dtype=int)
        sub_X = [X_test[i] for i in indices]
        sub_y = [y_test[i] for i in indices]
    else:
        sub_X = X_test
        sub_y = y_test

    t0 = time.time()
    y_pred = []
    for text in sub_X:
        res = predict_with_wangchanberta(text)
        if res:
            y_pred.append(res[0])
        else:
            y_pred.append("society")
    total_time = time.time() - t0
    latency_ms = (total_time / len(sub_X)) * 1000

    acc = accuracy_score(sub_y, y_pred)
    f1_macro = f1_score(sub_y, y_pred, average="macro", zero_division=0)
    f1_weighted = f1_score(sub_y, y_pred, average="weighted", zero_division=0)

    print(f"Evaluated on {len(sub_X)} test samples.")
    print(f"Accuracy:        {acc:.4f} ({acc*100:.2f}%)")
    print(f"Macro F1:        {f1_macro:.4f}")
    print(f"Weighted F1:     {f1_weighted:.4f}")
    print(f"Avg Latency:     {latency_ms:.2f} ms / article")
    print("\nClassification Report:")
    print(classification_report(sub_y, y_pred, digits=4, zero_division=0))

    cm = confusion_matrix(sub_y, y_pred, labels=CATEGORIES)
    return {
        "name": "WangchanBERTa",
        "accuracy": acc,
        "macro_f1": f1_macro,
        "weighted_f1": f1_weighted,
        "latency_ms": latency_ms,
        "cm": cm,
        "preds": y_pred,
    }


def evaluate_unified_system(X_test: list[str], y_test: list[str]):
    print("\n" + "=" * 70)
    print("3. EVALUATING UNIFIED 3-TIER CASCADE CLASSIFIER")
    print("=" * 70)

    t0 = time.time()
    y_pred = []
    methods_used = Counter()

    for text in X_test:
        cat, method = classify(text)
        y_pred.append(cat)
        method_group = method.split()[0]
        methods_used[method_group] += 1

    total_time = time.time() - t0
    latency_ms = (total_time / len(X_test)) * 1000

    acc = accuracy_score(y_test, y_pred)
    f1_macro = f1_score(y_test, y_pred, average="macro")
    f1_weighted = f1_score(y_test, y_pred, average="weighted")

    print(f"Accuracy:        {acc:.4f} ({acc*100:.2f}%)")
    print(f"Macro F1:        {f1_macro:.4f}")
    print(f"Weighted F1:     {f1_weighted:.4f}")
    print(f"Avg Latency:     {latency_ms:.2f} ms / article")
    print("\nRouting Breakdown:")
    for method, count in methods_used.most_common():
        pct = (count / len(X_test)) * 100
        print(f"  {method:20s}: {count:5d} ({pct:5.1f}%)")

    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, digits=4))

    cm = confusion_matrix(y_test, y_pred, labels=CATEGORIES)
    return {
        "name": "Unified 3-Tier System",
        "accuracy": acc,
        "macro_f1": f1_macro,
        "weighted_f1": f1_weighted,
        "latency_ms": latency_ms,
        "cm": cm,
        "preds": y_pred,
    }


def main():
    _, X_test, _, y_test = load_test_dataset(samples_per_class=800)

    res_svm = evaluate_linearsvc(X_test, y_test)
    res_wb = evaluate_wangchanberta(X_test, y_test, max_eval_samples=180)
    res_unified = evaluate_unified_system(X_test, y_test)

    print("\n" + "=" * 70)
    print("SUMMARY COMPARISON OF ALL MODELS & PIPELINES")
    print("=" * 70)
    print(f"{'Engine':<25} | {'Accuracy':<10} | {'Macro F1':<10} | {'Latency (ms)':<12}")
    print("-" * 70)
    for r in [res_svm, res_wb, res_unified]:
        print(f"{r['name']:<25} | {r['accuracy']*100:>8.2f}% | {r['macro_f1']:>10.4f} | {r['latency_ms']:>10.2f} ms")
    print("=" * 70)


if __name__ == "__main__":
    main()
