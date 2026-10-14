from __future__ import annotations

import pytest

from backend.services.classifier_service import (
    classify_article,
    ensure_categories,
    get_category_from_url,
)


class TestURLPriorityClassification:
    @pytest.mark.parametrize(
        'url,expected_category',
        [
            ('https://www.matichon.co.th/politics', 'politics'),
            ('https://www.matichon.co.th/politics/news_5835054', 'politics'),
            ('https://www.matichon.co.th/economy/news_5835055', 'economy'),
            ('https://www.matichon.co.th/sport/news_5835056', 'sports'),
            ('https://www.matichon.co.th/entertainment/news_5835087', 'entertainment'),
            ('https://www.matichon.co.th/foreign/news_5835057', 'world'),
            ('https://www.matichon.co.th/lifestyle/news_5835049', 'society'),
            ('https://www.matichon.co.th/local/quality-life/news_5835016', 'society'),
            ('https://www.bangkokpost.com/thailand/politics/123456', 'politics'),
            ('https://www.bangkokpost.com/business/123456', 'economy'),
            ('https://www.bangkokpost.com/sports/123456', 'sports'),
            ('https://www.bangkokpost.com/world/123456', 'world'),
            ('https://www.bangkokpost.com/tech/123456', 'technology'),
            ('https://www.bangkokpost.com/life/123456', 'society'),
            ('https://thestandard.co/category/news/politics/', 'politics'),
            ('https://thestandard.co/category/news/business/', 'economy'),
            ('https://thestandard.co/category/news/world/', 'world'),
            ('https://thestandard.co/category/news/tech/', 'technology'),
            ('https://thestandard.co/category/news/environment/', 'environment'),
            ('https://www.thaipbs.or.th/news/politic', 'politics'),
            ('https://www.thaipbs.or.th/news/economy', 'economy'),
            ('https://www.thaipbs.or.th/news/sport', 'sports'),
            ('https://www.thaipbs.or.th/news/tech', 'technology'),
            ('https://www.thaipbs.or.th/news/environment', 'environment'),
            ('https://www.thaipbs.or.th/news/health', 'health'),
            ('https://www.khaosod.co.th/politics/news_10369414', 'politics'),
            ('https://www.khaosod.co.th/sports/news_10369204', 'sports'),
            ('https://www.khaosod.co.th/entertainment/news_10369371', 'entertainment'),
            ('https://www.khaosod.co.th/around-the-world/news_12345', 'world'),
            ('https://www.thairath.co.th/news/politic/12345', 'politics'),
            ('https://www.thairath.co.th/news/business/12345', 'economy'),
            ('https://www.thairath.co.th/news/foreign/12345', 'world'),
            ('https://www.pptvhd36.com/news/%E0%B8%81%E0%B8%B2%E0%B8%A3%E0%B9%80%E0%B8%A1%E0%B8%B7%E0%B8%AD%E0%B8%87/1234', 'politics'),
            ('https://www.pptvhd36.com/news/%E0%B9%80%E0%B8%A8%E0%B8%A3%E0%B8%A9%E0%B8%90%E0%B8%81%E0%B8%B4%E0%B8%88/1234', 'economy'),
            ('https://www.pptvhd36.com/news/%E0%B8%95%E0%B9%88%E0%B8%B2%E0%B8%87%E0%B8%9B%E0%B8%A3%E0%B8%B0%E0%B9%80%E0%B8%97%E0%B8%A8/1234', 'world'),
            ('https://www.pptvhd36.com/news/%E0%B8%81%E0%B8%B5%E0%B8%AC%E0%B8%B2/1234', 'sports'),
        ],
    )
    def test_url_priority_classification(self, url: str, expected_category: str):
        match = get_category_from_url(url)
        assert match is not None, f'Failed to match URL: {url}'
        cat, method = match
        assert cat == expected_category
        assert method.startswith('URL Priority')

        cat_art, method_art = classify_article('', '', url=url)
        assert cat_art == expected_category
        assert method_art.startswith('URL Priority')

    def test_fallback_when_no_url_match(self):
        cat, method = classify_article(
            title='นายกฯ แถลงผลการประชุมคณะรัฐมนตรี ร่าง พ.ร.บ. งบประมาณ',
            summary='ที่ประชุม ครม. มีมติเห็นชอบนโยบายใหม่',
            url='https://example.com/article/12345',
        )
        assert cat == 'politics'
        assert not method.startswith('URL Priority')

    def test_ensure_categories_batch(self):
        articles = [
            {
                'title': 'ข่าว 1',
                'summary': 'สรุป 1',
                'url': 'https://www.matichon.co.th/politics/news_123',
            },
            {
                'title': 'ข่าว 2',
                'summary': 'สรุป 2',
                'url': 'https://www.bangkokpost.com/business/456',
            },
        ]
        updated = ensure_categories(articles, force=True)
        assert updated == 2
        assert articles[0]['category'] == 'politics'
        assert 'URL Priority' in articles[0]['classification_method']
        assert articles[1]['category'] == 'economy'
        assert 'URL Priority' in articles[1]['classification_method']


class TestNineCategoriesClassification:
    @pytest.mark.parametrize(
        'title,summary,expected_category',
        [
            (
                'นายกฯ แถลงผลการประชุมคณะรัฐมนตรี ร่าง พ.ร.บ. งบประมาณ',
                'ที่ประชุม ครม. มีมติเห็นชอบนโยบายใหม่และเตรียมเสนอรัฐสภา',
                'politics',
            ),
            (
                'ตลาดหุ้นไทยปิดบวก นักลงทุนแห่ซื้อหุ้นกลุ่มธนาคาร',
                'ดัชนีตลาดหลักทรัพย์ปรับตัวขึ้น ท่ามกลางภาวะเงินเฟ้อที่ชะลอตัว',
                'economy',
            ),
            (
                'เปิดตัวสมาร์ทโฟนเรือธงรุ่นใหม่ พร้อมชิปเซ็ต AI และระบบ 5G',
                'นวัตกรรมดิจิทัลรุ่นล่าสุดรองรับแอปพลิเคชันและการประมวลผลอัจฉริยะ',
                'technology',
            ),
            (
                'กระทรวงสาธารณสุขเตือนประชาชนระวังไข้หวัดใหญ่ระบาด',
                'แพทย์แนะฉีดวัคซีนป้องกันโรคและเข้ารับการรักษาที่โรงพยาบาล',
                'health',
            ),
            (
                'วิกฤตโลกร้อนส่งผลให้ค่าฝุ่น PM 2.5 เกินมาตรฐานในหลายพื้นที่',
                'นักวิชาการสิ่งแวดล้อมเรียกร้องลดการปล่อยก๊าซเรือนกระจกและพลังงานฟอสซิล',
                'environment',
            ),
            (
                'ผลบอลพรีเมียร์ลีก แมนยูคว้าชัยชนะ เก็บ 3 แต้มสำคัญ',
                'ศึกฟุตบอลอังกฤษนัดสำคัญ ทีมเจ้าบ้านโชว์ฟอร์มเยี่ยมเอาชนะคู่แข่ง',
                'sports',
            ),
            (
                'ดาราสาวชื่อดังเปิดตัวภาพยนตร์เรื่องใหม่ แฟนคลับแห่ต้อนรับ',
                'งานเปิดตัวซีรีส์และเพลงประกอบละครที่ได้รับความนิยม',
                'entertainment',
            ),
            (
                'สหรัฐฯ และจีนเจรจาความร่วมมือทางการทูตระหว่างประเทศ',
                'ผู้นำสองชาติมหาอำนาจร่วมประชุมสุดยอดผู้นำระดับโลก',
                'world',
            ),
            (
                'กระทรวงศึกษาธิการ และชุมชนร่วมจัดกิจกรรมวันเด็กแห่งชาติ',
                'การศึกษา พัฒนาคุณภาพชีวิตและสวัสดิการสังคมเพื่อเยาวชนในพื้นที่ต่างจังหวัด',
                'society',
            ),
        ],
    )
    def test_nine_categories_classification(
        self, title: str, summary: str, expected_category: str
    ):
        cat, method = classify_article(title=title, summary=summary, url='')
        assert cat == expected_category, (
            f"Expected '{expected_category}' for '{title}', got '{cat}' via '{method}'"
        )

