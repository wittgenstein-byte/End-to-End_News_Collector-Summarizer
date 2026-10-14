"""
scripts/generate_real_llm_presentation.py
─────────────────────────────────────────────────────────────────
Generates and records real LLM presentation output for a top story
(Nan Floods Crisis) using StoryPresentationService and LLM API.
Saves result to data/real_llm_presentation_output.json.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
from pathlib import Path
from openai import OpenAI

from backend.config import settings
from backend.services.story_presentation_service import StoryPresentationService


def main() -> None:
    # 1. Member articles for real top story: Nan Floods
    articles = [
        {
            "title": "GISTDA ใช้ข้อมูลเชิงพื้นที่ เฝ้าระวัง 11 ชุมชนบ่อเกลือ เสี่ยงเส้นทางถูกตัดขาด",
            "summary": "วันนี้ (22 ส.ค.2569) สำนักงานพัฒนาเทคโนโลยีอวกาศและภูมิสารสนเทศ (องค์การมหาชน) หรือ GISTDA ใช้ข้อมูลเชิงพื้นที่วิเคราะห์ถนนและเส้นทางน้ำ เพื่อสนับสนุนการเฝ้าระวังพื้นที่เสี่ยง จากสถานการณ์ฝนที่ตกต่อเนื่องในพื้นที่ อ.บ่อเกลือ จังหวัดน่าน ทำให้ต้องเฝ้าระวัง 11 ชุมชน ที่มีความเสี่ยงต่อการถูกตัดขาดจากเส้นทางคมนาคม เนื่องจากหลายชุมชนตั้งอยู่ในพื้นที่ภูเขาสูง และมีเส้นทางสัญจรเชื่อมต่ออย่างจำกัด หากเกิดเหตุดินถล่ม",
            "source": "ThaiPBS",
            "url": "https://www.thaipbs.or.th/news/content/509744",
            "fetched_at": "2026-08-22 14:35:12",
        },
        {
            "title": "กรมบัญชีกลางอนุมัติเพิ่ม 100 ล้าน เพิ่มเงินทดรองราชการช่วยน้ำท่วม “น่าน”",
            "summary": "วันนี้ (22 ส.ค.2569) นายธีรพัฒน์ คัชมาตย์ อธิบดีกรมป้องกันและบรรเทาสาธารณภัย เผยว่า ตามที่เกิดสถานการณ์อุทกภัย น้ำป่าไหลหลาก และดินถล่ม ที่ จ.น่าน ในพื้นที่ อ.ภูเพียง อ.ปัว อ.สันติสุข และ อ.ท่าวังผา ประชาชนได้รับความเดือดร้อนเป็นวงกว้าง ซึ่งกรมป้องกันและบรรเทาสาธารณภัย (ปภ.) ได้ขออนุมัติไปยังกรมบัญชีกลางเพื่อขอขยายวงเงินทดรองราชการเพื่อช่วยเหลือผู้ประสบภัยพิบัติกรณีฉุกเฉิน จากเดิมที่ จ.น่าน มีวงเงิน 20 ล้านบาท ขยายเป็น 100 ล้านบาท",
            "source": "ThaiPBS",
            "url": "https://www.thaipbs.or.th/news/content/509750",
            "fetched_at": "2026-08-22 14:35:11",
        },
        {
            "title": "นายกฯ ไปน่าน-อุบลฯ ตรวจน้ำท่วม-เยี่ยมทหารเหยียบทุ่นระเบิด",
            "summary": "วันนี้ (23 ส.ค.2569) นายอนุทิน ชาญวีรกูล นายกรัฐมนตรี และ รมว.มหาดไทย เดินทางจากท่าอากาศยานทหาร 2 กองบิน 6 (บน.6) โดยเครื่องบินของกองทัพบก ลงพื้นที่ตรวจราชการ จ.น่าน และ จ.อุบลราชธานี พร้อมด้วยหน่วยงานที่เกี่ยวข้องร่วมคณะด้วย เพื่อประชุมติดตามสถานการณ์การแก้ไขปัญหาอุทกภัยในพื้นที่ภาคเหนือและมาตรการเยียวยาฟื้นฟู",
            "source": "ThaiPBS",
            "url": "https://www.thaipbs.or.th/news/content/509767",
            "fetched_at": "2026-08-23 14:35:11",
        },
        {
            "title": "Nan flood recovery under way, aid payments prepared",
            "summary": "NAN - Prime Minister Anutin Charnvirakul on Sunday ordered state agencies to speed up flood recovery, compensation payments and infrastructure repairs in Nan and other flood-affected provinces, while maintaining heightened monitoring for further flooding and landslides during the remainder of the rainy season. Chairing a flood-monitoring meeting in Nan attended by cabinet ministers and the governor, the premier instructed the Comptroller General's Department to expedite financial assistance.",
            "source": "Bangkok Post",
            "url": "https://www.bangkokpost.com/thailand/general/3306558/nan-flood-recovery-under-way-aid-payments-prepared",
            "fetched_at": "2026-08-23 14:35:26",
        },
    ]

    client = None
    if settings.llm_api_key and settings.llm_api_key.strip():
        client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)

    service = StoryPresentationService(
        client=client,
        models=list(settings.llm_cascade_models),
        temperature=0.2,
    )

    story_data = {
        "story_id": "story_nan_floods_2026",
        "title": "สถานการณ์น้ำท่วมดินถล่มจังหวัดน่านและการเยียวยาฟื้นฟู",
        "category": "environment",
        "updated_at": "2026-08-23 14:35:26",
        "article_urls": [a["url"] for a in articles],
    }

    print("Generating presentation via StoryPresentationService...")
    presentation = service.present_story(story_data, articles)

    output = {
        "story_id": presentation.story_id,
        "headline": presentation.headline,
        "summary": presentation.summary,
        "timeline": [t.model_dump() for t in presentation.timeline],
        "citations": presentation.citations,
        "is_fallback": presentation.is_fallback,
        "cached": presentation.cached,
        "updated_at": presentation.updated_at,
        "article_count": len(articles),
        "outlets": ["ThaiPBS", "Bangkok Post"],
    }

    output_path = Path("data") / "real_llm_presentation_output.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Successfully saved presentation to {output_path}")
    print(f"Headline: {presentation.headline}")
    print(f"Summary: {presentation.summary}")
    print(f"Is Fallback: {presentation.is_fallback}")
    print(f"Timeline Events: {len(presentation.timeline)}")
    print(f"Citations: {len(presentation.citations)}")


if __name__ == "__main__":
    main()
