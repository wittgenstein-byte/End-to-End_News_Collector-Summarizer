import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import json
from config import settings
from services.classifier_service import ensure_categories

def main():
    if not settings.output_file.exists():
        print(f"No file found at {settings.output_file}")
        return

    with open(settings.output_file, 'r', encoding='utf-8') as f:
        news = json.load(f)

    print("=== Categories Before ===")
    before_counts = {}
    for item in news:
        c = item.get("category", "unknown")
        before_counts[c] = before_counts.get(c, 0) + 1
    for k, v in before_counts.items():
        print(f"{k}: {v}")

    # ทำการ Re-classify ทั้งหมด
    updated = ensure_categories(news, force=True)

    print("\n=== Categories After ===")
    after_counts = {}
    for item in news:
        c = item.get("category", "unknown")
        after_counts[c] = after_counts.get(c, 0) + 1
    for k, v in after_counts.items():
        print(f"{k}: {v}")
    
    # Save ทับไฟล์เดิม
    with open(settings.output_file, 'w', encoding='utf-8') as f:
        json.dump(news, f, ensure_ascii=False, indent=2)
        
    print(f"\n✅ Re-classified and saved {updated} articles successfully to {settings.output_file.name}")

if __name__ == '__main__':
    main()
