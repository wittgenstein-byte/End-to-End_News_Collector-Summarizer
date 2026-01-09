# End-to-End_News_Collector-Summarizer

Seminar Project

## Pipeline Overview

Ingest (RSS/API/Scrape) → Normalize → Dedup → Store Raw → Preprocess → Store Features → Classify (multi-label + confidence) → (Low confidence → LLM route) → Summarize (extractive/abstractive) → Index/Serve

Raw store: เก็บ HTML/JSON ดิบ + metadata ดิบ  
Clean store: เก็บ text ที่ clean แล้ว + structured fields  
Derived store: embedding, tokens, labels, summaries, index

## (1) Data Collection

ลำดับ: RSS/API ก่อน → ถ้าไม่มี/ข้อมูลไม่ครบค่อย scrape fallback  
ทำ normalize ให้เหลือ schema กลาง  
ทำ dedup ทันที (content_hash / url hash)  
เก็บ raw เสมอ (debug ง่าย + reprocess ได้)  
Output: record ที่มี text (หรือ raw_html ที่ยังต้อง extract)

## (2) Data Pre-processing

ทำเป็น “pure function” มากที่สุด: รับ text → คืน clean_text + tokens + embedding  
language detect (ถ้ามีหลายภาษา)  
clean HTML artifacts, boilerplate removal  
ตัดคำ/tokenize (ไทยใช้ tokenizer ที่เหมาะ)  
สร้าง embedding เก็บใน vector store หรือ table แยก  
Output: เติม features + text(cleaned)

## (3) News Classification (Multi-label + LLM delegation)

หัวใจคือ “confidence gating”:  
โมเดลหลัก (เช่น BiLSTM/Transformer) ทำนาย multi-label + probs  
กำหนดเกณฑ์ เช่น
- max_prob < 0.55 หรือ
- entropy สูง หรือ
- labels ขัดกันตามกฎ

→ ส่งเข้า LLM route

LLM ทำหน้าที่ “referee” เฉพาะเคสยาก เพื่อลดต้นทุน  
สำคัญ: เก็บ method=model|llm และ confidence เพื่อ audit/เทรนต่อ  
Output: เติม classification.labels, probs, method, confidence

## (4) Summarization (Extractive + Abstractive)

แนะนำทำ 2 ชั้น:
- Extractive: เอาประโยคสำคัญ/ไฮไลต์ (เร็ว ถูก cheap) → เป็น “หลักฐาน”
- Abstractive: สรุปภาษาคนอ่าน โดยอ้างอิง extractive หรือ text เต็ม

กลยุทธ์ลด hallucination:
- ให้ abstractive “ยึด extractive เป็น context”
- เก็บ key_sentences ไว้แสดง “อ้างอิงจากบทความ”

Output: เติม summaries.extractive และ summaries.abstractive

## Example Pipeline (news-pipeline)

ตัวอย่าง pipeline แบบ runnable อยู่ใน `news-pipeline/` พร้อม dataset จำลองและโมดูลย่อยตามขั้นตอนที่อธิบายไว้ข้างต้น:

```
news-pipeline/
├─ main.py                 # pipeline runner
├─ config.py
├─ pipeline/
│  ├─ ingest.py
│  ├─ preprocess.py
│  ├─ classify.py
│  └─ summarize.py
├─ storage/
│  ├─ db.py
│  └─ models.py
├─ api/
│  └─ main.py
└─ data/
   └─ sample_news.jsonl
```

รันตัวอย่าง:

```
python news-pipeline/main.py
```
