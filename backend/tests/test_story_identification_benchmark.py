"""
tests/test_story_identification_benchmark.py
─────────────────────────────────────────────────────────────────
SOLID  S — Comprehensive Stage A & Stage B ground-truth benchmark suite.
GRASP  Information Expert — Evaluates exact event identity, multi-day
       corroboration, syndicated duplicate detection, follow-up lineage,
       hard vetoes, tie resolution, and read-only trending gates.
POLICY Zero Test Leakage — Pure in-memory / temporary repo isolation.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np

from backend.repo.macro_event_repo import InMemoryMacroEventRepository
from backend.repo.news_repo import NewsRepositoryPort
from backend.repo.story_repo import FileStoryRepository
from backend.schemas.macro_event_schema import MacroEventRecord
from backend.schemas.news_schema import ArticleRecord
from backend.schemas.story_schema import (
    EventTimeEvidence,
    StoryRecord,
    TypedEventAnchors,
)
from backend.services.macro_event_service import MacroEventService
from backend.services.story_service import StoryService
from backend.services.trending_service import TrendingService


class InMemoryEngagementRepository:
    def record_event(self, url: str, event_type: str) -> dict[str, int]:
        return {"clicks": 0, "summaries": 0, "bookmarks": 0}

    def get_engagement(self, url: str) -> dict[str, int]:
        return {"clicks": 0, "summaries": 0, "bookmarks": 0}

    def get_all_engagements(self) -> dict[str, dict[str, int]]:
        return {}

    def clear_all(self) -> None:
        pass


def _unit_vector(dim: int = 768, index: int = 0) -> list[float]:
    v = np.zeros(dim, dtype=np.float32)
    v[index] = 1.0
    return [float(x) for x in v]


def _perturbed_vector(base: list[float], cos_sim: float, perturb_idx: int = 1) -> list[float]:
    v = np.zeros(len(base), dtype=np.float32)
    v[0] = float(cos_sim)
    v[perturb_idx] = float(np.sqrt(max(0.0, 1.0 - cos_sim**2)))
    norm = np.linalg.norm(v)
    if norm > 1e-9:
        v /= norm
    return [float(x) for x in v]


# ── Benchmark Suite ────────────────────────────────────────────────


class TestStageAStoryIdentificationBenchmark:
    """Benchmark evaluation for Stage A Article-to-Story Assignment."""

    def test_category_1_hard_contradiction_veto(self) -> None:
        """Contradictory event time intervals reject SAME_EVENT even with high semantic similarity."""
        with TemporaryDirectory() as tmp_dir:
            story_repo = FileStoryRepository(data_file=Path(tmp_dir) / "stories.json")
            macro_repo = InMemoryMacroEventRepository()
            service = StoryService(story_repo=story_repo, macro_service=MacroEventService(macro_repo=macro_repo, story_repo=story_repo))

            dt_story = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
            dt_article = datetime(2026, 8, 14, 15, 0, 0, tzinfo=timezone.utc)
            base_vec = _unit_vector(768, 0)

            # Existing story anchored to Aug 10, with last_article_at within candidate window
            story = StoryRecord(
                title="เพลิงไหม้โรงงานกิ่งแก้ว สมุทรปราการ",
                category="society",
                created_at=dt_story,
                updated_at=dt_story,
                first_article_at=dt_story,
                last_article_at=dt_article - timedelta(hours=5),
                centroid=base_vec,
                seed_embedding=base_vec,
                medoid_embedding=base_vec,
                event_time=EventTimeEvidence(
                    start_utc=dt_story,
                    end_utc=dt_story,
                    precision="datetime",
                    confidence="explicit",
                ),
                typed_anchors=TypedEventAnchors(
                    event_locations=["กิ่งแก้ว", "สมุทรปราการ"],
                    actions=["เพลิงไหม้"],
                ),
            )
            story_repo.save_story(story)

            # Incoming article 4 days later referring explicitly to Aug 14 (interval gap > 72h)
            high_sim_vec = _perturbed_vector(base_vec, 0.90)

            new_article = ArticleRecord(
                title="เหตุเพลิงไหม้โรงงานแห่งใหม่ เมื่อวันที่ 14 ส.ค. 2569",
                summary="เกิดเหตุเพลิงไหม้ครั้งใหม่",
                source="ThaiPBS",
                url="https://thaipbs.or.th/fire-2",
                category="society",
                fetched_at=dt_article.strftime("%Y-%m-%d %H:%M:%S"),
            )

            res_story, is_new = service.assign_article(new_article, article_embedding=high_sim_vec)
            # MUST NOT merge into Aug 10 story due to Hard Contradiction Veto
            assert is_new is True
            assert res_story.story_id != story.story_id

    def test_category_2_independent_outlet_corroboration_promotes_to_verified(self) -> None:
        """Independent report from distinct outlet corroborating pending story promotes to verified."""
        with TemporaryDirectory() as tmp_dir:
            story_repo = FileStoryRepository(data_file=Path(tmp_dir) / "stories.json")
            macro_repo = InMemoryMacroEventRepository()
            service = StoryService(story_repo=story_repo, macro_service=MacroEventService(macro_repo=macro_repo, story_repo=story_repo))

            dt = datetime(2026, 8, 20, 10, 0, 0, tzinfo=timezone.utc)
            vec = _unit_vector(768, 0)

            # Story initially created in pending_review
            story = StoryRecord(
                title="รถบัสทัศนศึกษาประสบอุบัติเหตุไฟไหม้",
                category="society",
                verification_status="pending_review",
                conflict_type="borderline_similarity",
                created_at=dt,
                updated_at=dt,
                first_article_at=dt,
                last_article_at=dt,
                article_urls=["https://thaipbs.or.th/bus-fire"],
                article_count=1,
                outlets=["ThaiPBS"],
                outlet_count=1,
                centroid=vec,
                seed_embedding=vec,
                medoid_embedding=vec,
                typed_anchors=TypedEventAnchors(
                    event_locations=["ถนนวิภาวดีรังสิต", "ปทุมธานี"],
                    actions=["เกิดอุบัติเหตุ", "ไฟไหม้"],
                ),
            )
            story_repo.save_story(story)

            # Second article from distinct outlet with independent phrasing
            art2 = ArticleRecord(
                title="ด่วน รถบัสคณะนักเรียนเกิดเพลิงลุกไหม้ ถนนวิภาวดีรังสิต",
                summary="เจ้าหน้าที่เร่งระดมฉีดน้ำควบคุมเพลิง รถบัสโรงเรียน",
                source="The Standard",
                url="https://thestandard.co/bus-fire",
                category="society",
                fetched_at=dt.strftime("%Y-%m-%d %H:%M:%S"),
            )
            sim_vec2 = _perturbed_vector(vec, 0.88)

            res_story, is_new = service.assign_article(art2, article_embedding=sim_vec2)
            assert is_new is False
            assert res_story.story_id == story.story_id
            # Corroborated by independent outlet -> Promoted to verified!
            assert res_story.verification_status == "verified"
            assert res_story.conflict_type is None

    def test_category_3_syndicated_duplicate_remains_pending(self) -> None:
        """Near-verbatim syndicated duplicate from different outlet does NOT satisfy independent promotion."""
        with TemporaryDirectory() as tmp_dir:
            story_repo = FileStoryRepository(data_file=Path(tmp_dir) / "stories.json")
            macro_repo = InMemoryMacroEventRepository()
            service = StoryService(story_repo=story_repo, macro_service=MacroEventService(macro_repo=macro_repo, story_repo=story_repo))

            dt = datetime(2026, 8, 20, 10, 0, 0, tzinfo=timezone.utc)
            vec = _unit_vector(768, 0)

            # Story initially created in pending_review
            story = StoryRecord(
                title="แถลงการณ์ด่วนสถานการณ์น้ำท่วมฉับพลัน",
                category="environment",
                verification_status="pending_review",
                conflict_type="borderline_similarity",
                created_at=dt,
                updated_at=dt,
                first_article_at=dt,
                last_article_at=dt,
                article_urls=["https://outlet-a.com/flood-statement"],
                article_count=1,
                outlets=["Outlet A"],
                outlet_count=1,
                centroid=vec,
                seed_embedding=vec,
                medoid_embedding=vec,
                typed_anchors=TypedEventAnchors(
                    event_locations=["เชียงราย"],
                    actions=["แถลงการณ์"],
                ),
            )
            story_repo.save_story(story)

            # Wire syndication with nearly verbatim text and explicit wire attribution
            art_syndicated = ArticleRecord(
                title="แถลงการณ์ด่วนสถานการณ์น้ำท่วมฉับพลัน",
                summary="แถลงการณ์ด่วนสถานการณ์น้ำท่วมฉับพลัน ขอบคุณข้อมูลจาก Outlet A",
                source="Outlet B",
                url="https://outlet-b.com/republished",
                category="environment",
                fetched_at=dt.strftime("%Y-%m-%d %H:%M:%S"),
            )

            res_story, is_new = service.assign_article(art_syndicated, article_embedding=vec)
            assert is_new is False
            assert res_story.story_id == story.story_id
            # INVARIANT: Syndicated duplicate must keep verification_status as pending_review
            assert res_story.verification_status == "pending_review"

    def test_category_4_direct_follow_up_progression(self) -> None:
        """Progression shift (e.g. incident -> arrest) creates follow-up Story linked via antecedent_story_id."""
        with TemporaryDirectory() as tmp_dir:
            story_repo = FileStoryRepository(data_file=Path(tmp_dir) / "stories.json")
            macro_repo = InMemoryMacroEventRepository()
            macro_service = MacroEventService(macro_repo=macro_repo, story_repo=story_repo)
            service = StoryService(story_repo=story_repo, macro_service=macro_service)

            dt1 = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
            vec1 = _unit_vector(768, 0)

            # Story 1: Crime incident
            story1 = StoryRecord(
                title="คนร้ายบุกเดี่ยว คดีชิงทองเชียงใหม่",
                category="crime",
                verification_status="verified",
                created_at=dt1,
                updated_at=dt1,
                first_article_at=dt1,
                last_article_at=dt1,
                centroid=vec1,
                seed_embedding=vec1,
                medoid_embedding=vec1,
                typed_anchors=TypedEventAnchors(
                    event_locations=["เชียงใหม่"],
                    actions=["ชิงทอง", "ปล้น"],
                    targets=["ร้านทอง"],
                    storyline_anchor="คดีชิงทองเชียงใหม่",
                ),
            )
            story_repo.save_story(story1)
            macro_service.assign_event(story1)

            # Day 3: Police arrest perpetrator (progression action verb 'จับกุม', 'รวบ')
            dt2 = datetime(2026, 8, 3, 14, 0, 0, tzinfo=timezone.utc)
            vec2 = _perturbed_vector(vec1, 0.72)

            art2 = ArticleRecord(
                title="ตำรวจรวบตัวคนร้าย คดีชิงทองเชียงใหม่ สารภาพติดหนี้พนัน",
                summary="เจ้าหน้าที่ตำรวจสืบสวนภาค 5 จับกุมผู้ต้องหา คดีชิงทองเชียงใหม่ ได้สำเร็จ",
                source="ThaiPBS",
                url="https://thaipbs.or.th/gold-arrest",
                category="crime",
                fetched_at=dt2.strftime("%Y-%m-%d %H:%M:%S"),
            )

            res_story, is_new = service.assign_article(art2, article_embedding=vec2)
            assert is_new is True
            assert res_story.story_id != story1.story_id
            assert res_story.metadata.get("antecedent_story_id") == story1.story_id
            # Authoritative lineage: both stories must share the same macro_event_id!
            assert res_story.macro_event_id is not None
            assert res_story.macro_event_id == story1.macro_event_id


class TestStageBMacroEventBenchmark:
    """Benchmark evaluation for Stage B Story-to-MacroEvent Linking."""

    def test_step_0_authoritative_lineage_inheritance(self) -> None:
        """Step 0 guarantees follow-up stories inherit antecedent macro with updates relation."""
        with TemporaryDirectory() as tmp_dir:
            story_repo = FileStoryRepository(data_file=Path(tmp_dir) / "stories.json")
            macro_repo = InMemoryMacroEventRepository()
            macro_service = MacroEventService(macro_repo=macro_repo, story_repo=story_repo)

            dt = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
            vec = _unit_vector(768, 0)

            # Antecedent story
            ant_story = StoryRecord(
                title="น้ำท่วมน่าน มวลน้ำหลากท่วมหลายตำบล",
                category="environment",
                verification_status="verified",
                created_at=dt,
                updated_at=dt,
                centroid=vec,
                typed_anchors=TypedEventAnchors(
                    event_locations=["น่าน"],
                    actions=["น้ำท่วม"],
                    storyline_anchor="น้ำท่วมน่าน",
                ),
            )
            story_repo.save_story(ant_story)
            ant_macro, is_new_ant = macro_service.assign_event(ant_story)
            assert is_new_ant is True

            # Follow-up story referencing ant_story
            dt2 = dt + timedelta(days=2)
            follow_story = StoryRecord(
                title="เร่งฟื้นฟูหลังน้ำลด ผู้ว่าฯ น่าน ลงพื้นที่แจกถุงยังชีพ",
                category="environment",
                verification_status="verified",
                created_at=dt2,
                updated_at=dt2,
                centroid=_perturbed_vector(vec, 0.70),
                typed_anchors=TypedEventAnchors(
                    event_locations=["น่าน"],
                    actions=["ฟื้นฟู", "แจกถุงยังชีพ"],
                    storyline_anchor="น้ำท่วมน่าน",
                ),
            )
            story_repo.save_story(follow_story)

            macro, is_new = macro_service.assign_event(follow_story, antecedent_story_id=ant_story.story_id)
            assert is_new is False
            assert macro.macro_event_id == ant_macro.macro_event_id
            assert follow_story.macro_event_id == ant_macro.macro_event_id
            assert follow_story.macro_association_status == "linked"

            # Must contain updates relation from follow_story to ant_story
            updates_rels = [
                r for r in macro.relations
                if r.source_event_id == follow_story.story_id
                and r.target_event_id == ant_story.story_id
                and r.relation_type == "updates"
            ]
            assert len(updates_rels) == 1

    def test_stage_b_hard_veto_against_generic_roles_only(self) -> None:
        """Shared anchors consisting solely of actor_roles (e.g. นายกรัฐมนตรี) veto merge -> creates new macro."""
        with TemporaryDirectory() as tmp_dir:
            story_repo = FileStoryRepository(data_file=Path(tmp_dir) / "stories.json")
            macro_repo = InMemoryMacroEventRepository()
            macro_service = MacroEventService(macro_repo=macro_repo, story_repo=story_repo)

            dt = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
            vec1 = _unit_vector(768, 0)
            vec2 = _perturbed_vector(vec1, 0.85)

            # Existing Macro 1: Economy conference
            macro1 = MacroEventRecord(
                title="นายกฯ ร่วมประชุมเวทีเศรษฐกิจโลก",
                category="economy",
                status="active",
                created_at=dt,
                updated_at=dt,
                centroid=vec1,
                typed_anchors=TypedEventAnchors(
                    actor_roles=["นายกรัฐมนตรี", "รัฐบาล"],
                    actions=["ประชุม"],
                ),
                child_event_ids=["story_econ_1"],
            )
            macro_repo.save_macro_event(macro1)

            # Story 2: Disaster relief inspection (shares ONLY generic role 'นายกรัฐมนตรี')
            story2 = StoryRecord(
                title="นายกฯ ลงพื้นที่ตรวจสถานการณ์น้ำท่วมเชียงราย",
                category="environment",
                verification_status="verified",
                created_at=dt,
                updated_at=dt,
                centroid=vec2,
                typed_anchors=TypedEventAnchors(
                    actor_roles=["นายกรัฐมนตรี"],
                    actions=["ตรวจน้ำท่วม"],
                    event_locations=["เชียงราย"],
                ),
            )
            story_repo.save_story(story2)

            # score_macro must return 0.0 due to Hard Veto
            score = macro_service.score_macro(story2, macro1)
            assert score == 0.0

            # assign_event must NOT link to macro1; must create a new MacroEventRecord
            res_macro, is_new = macro_service.assign_event(story2)
            assert is_new is True
            assert res_macro.macro_event_id != macro1.macro_event_id
            assert story2.macro_association_status == "new_macro"

    def test_stage_b_competing_macros_tie_holds_as_pending_macro(self) -> None:
        """Two candidate macros with score >= 0.62 and margin < 0.05 hold as pending_macro."""
        with TemporaryDirectory() as tmp_dir:
            story_repo = FileStoryRepository(data_file=Path(tmp_dir) / "stories.json")
            macro_repo = InMemoryMacroEventRepository()
            macro_service = MacroEventService(macro_repo=macro_repo, story_repo=story_repo)

            dt = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
            vec = _unit_vector(768, 0)

            # Two nearly identical competing macro storylines
            macro_a = MacroEventRecord(
                title="วิกฤตน้ำท่วมลุ่มน้ำยม พะเยา",
                category="environment",
                status="active",
                created_at=dt,
                updated_at=dt,
                centroid=vec,
                typed_anchors=TypedEventAnchors(
                    event_locations=["พะเยา"],
                    actions=["น้ำท่วม"],
                ),
                child_event_ids=["m_a_1"],
            )
            macro_b = MacroEventRecord(
                title="วิกฤตน้ำท่วมลุ่มน้ำยม แพร่",
                category="environment",
                status="active",
                created_at=dt,
                updated_at=dt,
                centroid=vec,
                typed_anchors=TypedEventAnchors(
                    event_locations=["แพร่"],
                    actions=["น้ำท่วม"],
                ),
                child_event_ids=["m_b_1"],
            )
            macro_repo.save_macro_event(macro_a)
            macro_repo.save_macro_event(macro_b)

            # Incoming story spanning both border areas
            story = StoryRecord(
                title="มวลน้ำยมทะลักข้ามรอยต่อพะเยา-แพร่",
                category="environment",
                verification_status="verified",
                created_at=dt,
                updated_at=dt,
                centroid=vec,
                typed_anchors=TypedEventAnchors(
                    event_locations=["พะเยา", "แพร่"],
                    actions=["น้ำท่วม"],
                ),
            )
            story_repo.save_story(story)

            res_macro, is_new = macro_service.assign_event(story)
            assert res_macro is None
            assert is_new is False
            assert story.macro_event_id is None
            assert story.macro_association_status == "pending_macro"
            assert story.pending_macro_reason == "competing_macros_margin_tie"
            assert len(story.candidate_macro_ids) == 2


class TestReadOnlyTrendingGuarantees:
    """Benchmark evaluation for Contract B & P0.2 Strictly Read-Only Trending."""

    def test_unassigned_articles_omitted_and_counted(self) -> None:
        """Articles without a story_id are omitted from primary trending and counted in unassigned_article_count."""
        dt = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
        class MockRepo(NewsRepositoryPort):
            def load_news(self) -> list[dict[str, Any]]:
                return [
                    {
                        "title": "ข่าวที่ยังไม่ได้จัดกลุ่ม A",
                        "summary": "...",
                        "source": "ThaiPBS",
                        "url": "https://thaipbs.or.th/unassigned-1",
                        "fetched_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "story_id": None,
                    },
                    {
                        "title": "ข่าวที่ยังไม่ได้จัดกลุ่ม B",
                        "summary": "...",
                        "source": "The Standard",
                        "url": "https://thestandard.co/unassigned-2",
                        "fetched_at": dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "story_id": "",
                    },
                ]
            def save_news(self, data: list[dict[str, Any]]) -> None:
                raise AssertionError("Must not write to news repo!")
            def load_seen(self) -> set[str]:
                return set()
            def save_seen(self, seen: set[str]) -> None:
                pass

        service = TrendingService(news_repo=MockRepo(), engagement_repo=InMemoryEngagementRepository())
        res = service.get_trending_articles(limit=5, now=dt)

        assert res.total == 0
        assert len(res.trending) == 0
        assert res.unassigned_article_count == 2
        assert res.pending_review_count == 0

    def test_pending_review_stories_strictly_excluded_from_trending(self) -> None:
        """Stories with verification_status == pending_review are excluded from get_trending_stories."""
        with TemporaryDirectory() as tmp_dir:
            story_repo = FileStoryRepository(data_file=Path(tmp_dir) / "stories.json")
            dt = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)

            # Story 1: Verified
            s1 = StoryRecord(
                title="เรื่องที่ผ่านการยืนยันแล้ว",
                category="politics",
                status="active",
                verification_status="verified",
                created_at=dt,
                updated_at=dt,
                article_urls=["https://thaipbs.or.th/pol-1"],
                article_count=1,
                outlets=["ThaiPBS"],
            )
            # Story 2: Pending Review
            s2 = StoryRecord(
                title="เรื่องที่ยังรอการตรวจสอบ",
                category="politics",
                status="active",
                verification_status="pending_review",
                conflict_type="same_event_tie",
                created_at=dt,
                updated_at=dt,
                article_urls=["https://thaipbs.or.th/pending-1"],
                article_count=1,
                outlets=["ThaiPBS"],
            )
            story_repo.save_story(s1)
            story_repo.save_story(s2)

            class EmptyNews(NewsRepositoryPort):
                def load_news(self) -> list[dict[str, Any]]:
                    return []
                def save_news(self, data: list[dict[str, Any]]) -> None:
                    pass
                def load_seen(self) -> set[str]:
                    return set()
                def save_seen(self, seen: set[str]) -> None:
                    pass

            service = TrendingService(
                news_repo=EmptyNews(),
                engagement_repo=InMemoryEngagementRepository(),
                story_repo=story_repo,
            )

            trending_stories = service.get_trending_stories(limit=10, now=dt)
            story_ids = [s.story_id for s in trending_stories]
            assert s1.story_id in story_ids
            assert s2.story_id not in story_ids

    def test_pending_macro_included_in_story_trending_but_excluded_from_macro_trending(self) -> None:
        """A verified story with macro_association_status == pending_macro participates in story trending but not macro trending."""
        with TemporaryDirectory() as tmp_dir:
            story_repo = FileStoryRepository(data_file=Path(tmp_dir) / "stories.json")
            macro_repo = InMemoryMacroEventRepository()
            dt = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)

            # Story with pending_macro
            story = StoryRecord(
                title="ประเด็นข่าวที่รอเชื่อมโยงมหากาพย์",
                category="society",
                status="active",
                verification_status="verified",
                macro_association_status="pending_macro",
                macro_event_id=None,
                created_at=dt,
                updated_at=dt,
                article_urls=["https://thaipbs.or.th/soc-1"],
                article_count=1,
                outlets=["ThaiPBS"],
            )
            story_repo.save_story(story)

            # Macro with no child stories
            macro = MacroEventRecord(
                title="มหากาพย์สังคม",
                category="society",
                status="active",
                created_at=dt,
                updated_at=dt,
                child_event_ids=[],
            )
            macro_repo.save_macro_event(macro)

            class EmptyNews(NewsRepositoryPort):
                def load_news(self) -> list[dict[str, Any]]:
                    return []
                def save_news(self, data: list[dict[str, Any]]) -> None:
                    pass
                def load_seen(self) -> set[str]:
                    return set()
                def save_seen(self, seen: set[str]) -> None:
                    pass

            service = TrendingService(
                news_repo=EmptyNews(),
                engagement_repo=InMemoryEngagementRepository(),
                story_repo=story_repo,
            )

            # 1. Included in Story Trending
            story_clusters = service.get_trending_stories(limit=10, now=dt)
            assert any(c.story_id == story.story_id for c in story_clusters)

            # 2. Excluded from Macro Trending
            macro_clusters = service.get_trending_macro_events(limit=10, now=dt)
            assert len(macro_clusters) == 0
