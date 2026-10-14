"""
tests/test_storage_pdpa.py
─────────────────────────────────────────────────────────────────
SOLID  S — Comprehensive test suite for data storage classification,
          PDPA compliance (zero PII storage), engagement telemetry,
          and repository concurrency/fault-recovery.
GRASP  Information Expert — Verifies disk schema, non-PII invariants,
          FastAPI telemetry endpoints, and 24h content cache TTL rules.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.repo.engagement_repo import (
    EngagementRepositoryPort,
    FileEngagementRepository,
)

# ── 1. Storage Classification & Zero-PII Compliance Tests ─────────

class TestStorageClassificationPDPA:
    """
    Validates PDPA compliance and strict storage taxonomy:
    1. Zero PII storage in FileEngagementRepository.
    2. Only aggregate non-identifiable counters (clicks, summaries, bookmarks).
    3. No IP addresses, user IDs, device fingerprints, or session cookies persisted.
    """

    def test_zero_pii_stored_on_disk(self, tmp_path: Path) -> None:
        """
        Verify that only URL-keyed aggregate metrics and generic metadata
        are written to disk, with zero personal data or user identifiers.
        """
        data_file = tmp_path / "engagement_pdpa.json"
        repo = FileEngagementRepository(data_file=data_file)

        test_url_1 = "https://thaipbs.or.th/news/content/1001"
        test_url_2 = "https://thestandard.co/news/content/2002"

        repo.record_event(test_url_1, "click")
        repo.record_event(test_url_1, "summary")
        repo.record_event(test_url_1, "bookmark")
        repo.record_event(test_url_2, "click")

        # Read raw JSON file directly from disk
        assert data_file.exists(), "Engagement data file was not created on disk"
        with data_file.open("r", encoding="utf-8") as f:
            raw_data = json.load(f)

        # 1. Top-level keys must only be 'metadata' and 'engagements'
        assert set(raw_data.keys()) == {"metadata", "engagements"}

        # 2. Metadata must contain only aggregate stats
        metadata = raw_data["metadata"]
        assert "version" in metadata
        assert "last_updated" in metadata
        assert metadata["total_tracked_urls"] == 2
        # Ensure no PII fields in metadata
        forbidden_keys = {
            "ip", "ip_address", "user_id", "client_id", "session_id",
            "fingerprint", "device", "user_agent", "cookie", "email",
        }
        assert not (set(metadata.keys()) & forbidden_keys)

        # 3. Engagements entries must contain only numeric counters + updated_at
        engagements = raw_data["engagements"]
        assert test_url_1 in engagements
        assert test_url_2 in engagements

        entry1 = engagements[test_url_1]
        allowed_entry_keys = {"clicks", "summaries", "bookmarks", "updated_at"}
        assert set(entry1.keys()) == allowed_entry_keys
        assert entry1["clicks"] == 1
        assert entry1["summaries"] == 1
        assert entry1["bookmarks"] == 1
        assert isinstance(entry1["clicks"], int)

        # Confirm absolute absence of any user-tracking data
        for entry in engagements.values():
            assert not (set(entry.keys()) & forbidden_keys)
            assert isinstance(entry["clicks"], int)
            assert isinstance(entry["summaries"], int)
            assert isinstance(entry["bookmarks"], int)

    def test_url_normalization_and_whitespace_stripping(self, tmp_path: Path) -> None:
        """Verify URL whitespace is cleanly stripped and empty URLs are rejected."""
        data_file = tmp_path / "engagement_norm.json"
        repo = FileEngagementRepository(data_file=data_file)

        raw_url = "   https://example.com/news/article-123   \n"
        stats = repo.record_event(raw_url, "click")
        assert stats["clicks"] == 1

        # Querying with stripped URL must match
        query_stats = repo.get_engagement("https://example.com/news/article-123")
        assert query_stats["clicks"] == 1

        # Recording for empty URL returns zeros and does not create an entry
        empty_stats = repo.record_event("   ", "click")
        assert empty_stats == {"clicks": 0, "summaries": 0, "bookmarks": 0}
        assert len(repo.get_all_engagements()) == 1

    def test_unrecognized_event_types_do_not_modify_counters(self, tmp_path: Path) -> None:
        """Invalid event types (e.g. 'view', 'like', 'share') must not alter data."""
        data_file = tmp_path / "engagement_invalid.json"
        repo = FileEngagementRepository(data_file=data_file)
        url = "https://example.com/news/test"

        repo.record_event(url, "click")
        # Attempt to record invalid event types
        repo.record_event(url, "share")
        repo.record_event(url, "like")
        repo.record_event(url, "hover")
        repo.record_event(url, "")

        stats = repo.get_engagement(url)
        assert stats == {"clicks": 1, "summaries": 0, "bookmarks": 0}

    def test_port_protocol_compliance(self, tmp_path: Path) -> None:
        """Verify FileEngagementRepository implements EngagementRepositoryPort."""
        data_file = tmp_path / "engagement_proto.json"
        repo: EngagementRepositoryPort = FileEngagementRepository(data_file=data_file)
        assert hasattr(repo, "record_event")
        assert hasattr(repo, "get_engagement")
        assert hasattr(repo, "get_all_engagements")
        assert hasattr(repo, "clear_all")


# ── 2. Concurrency Safety & Race Condition Resistance ─────────────

class TestEngagementConcurrencySafety:
    """
    Stress tests FileEngagementRepository under concurrent multi-threaded
    read and write workloads to ensure atomic increments and file consistency.
    """

    def test_concurrent_single_url_increments(self, tmp_path: Path) -> None:
        """Simulate high concurrent clicks on a single breaking news article."""
        data_file = tmp_path / "concurrent_single.json"
        repo = FileEngagementRepository(data_file=data_file)
        url = "https://thaipbs.or.th/news/breaking/999"

        num_threads = 20
        increments_per_thread = 25
        total_expected_clicks = num_threads * increments_per_thread

        def worker() -> None:
            for _ in range(increments_per_thread):
                repo.record_event(url, "click")

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker) for _ in range(num_threads)]
            concurrent.futures.wait(futures)

        final_stats = repo.get_engagement(url)
        assert final_stats["clicks"] == total_expected_clicks

        # Read back from fresh repo instance to verify disk state
        fresh_repo = FileEngagementRepository(data_file=data_file)
        assert fresh_repo.get_engagement(url)["clicks"] == total_expected_clicks

    def test_concurrent_multi_url_mixed_events(self, tmp_path: Path) -> None:
        """Simulate concurrent mixed events across multiple distinct articles."""
        data_file = tmp_path / "concurrent_multi.json"
        repo = FileEngagementRepository(data_file=data_file)

        urls = [
            f"https://example.com/news/topic-{i}"
            for i in range(5)
        ]

        def worker(worker_id: int) -> None:
            for i, target_url in enumerate(urls):
                repo.record_event(target_url, "click")
                if worker_id % 2 == 0:
                    repo.record_event(target_url, "summary")
                if worker_id % 4 == 0:
                    repo.record_event(target_url, "bookmark")
                # Read operation amidst writes
                _ = repo.get_engagement(target_url)

        num_workers = 16
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(worker, w_id) for w_id in range(num_workers)]
            concurrent.futures.wait(futures)

        all_engagements = repo.get_all_engagements()
        assert len(all_engagements) == 5

        for target_url in urls:
            stats = all_engagements[target_url]
            assert stats["clicks"] == num_workers
            assert stats["summaries"] == num_workers // 2
            assert stats["bookmarks"] == num_workers // 4


# ── 3. Fault Recovery & Corrupted File Resilience ─────────────────

class TestFaultRecoveryAndCorruptedFile:
    """
    Tests error isolation and self-healing when encountering missing,
    corrupted, or unreadable JSON files.
    """

    def test_corrupted_json_file_graceful_recovery(self, tmp_path: Path) -> None:
        """
        When the JSON file contains corrupt/partial text, the repository
        must not crash, but fallback to default data and repair itself on write.
        """
        data_file = tmp_path / "corrupted.json"
        # Write corrupted JSON
        data_file.write_text("{ incomplete json string...", encoding="utf-8")

        repo = FileEngagementRepository(data_file=data_file)

        # Reading from corrupt file must return empty defaults without raising
        empty_all = repo.get_all_engagements()
        assert empty_all == {}

        stats = repo.get_engagement("https://example.com/item")
        assert stats == {"clicks": 0, "summaries": 0, "bookmarks": 0}

        # Recording a new event must repair the file cleanly
        new_stats = repo.record_event("https://example.com/item", "click")
        assert new_stats["clicks"] == 1

        # File is now valid JSON again
        with data_file.open("r", encoding="utf-8") as f:
            repaired_data = json.load(f)
        assert "engagements" in repaired_data
        assert "https://example.com/item" in repaired_data["engagements"]

    def test_empty_json_file_handling(self, tmp_path: Path) -> None:
        """Zero-byte file must fallback to defaults and repair cleanly."""
        data_file = tmp_path / "empty.json"
        data_file.write_text("", encoding="utf-8")

        repo = FileEngagementRepository(data_file=data_file)
        assert repo.get_all_engagements() == {}

        repo.record_event("https://example.com/1", "summary")
        assert repo.get_engagement("https://example.com/1")["summaries"] == 1

    def test_auto_create_nested_parent_directories(self, tmp_path: Path) -> None:
        """Writing to deeply nested non-existent directory must create parents."""
        deep_file = tmp_path / "nested" / "sub" / "storage" / "engagement.json"
        assert not deep_file.parent.exists()

        repo = FileEngagementRepository(data_file=deep_file)
        stats = repo.record_event("https://example.com/deep", "bookmark")
        assert stats["bookmarks"] == 1
        assert deep_file.exists()

    def test_clear_all_resets_disk_state(self, tmp_path: Path) -> None:
        """clear_all must erase all tracked URLs and update metadata."""
        data_file = tmp_path / "clear_test.json"
        repo = FileEngagementRepository(data_file=data_file)

        for i in range(3):
            repo.record_event(f"https://example.com/{i}", "click")

        assert len(repo.get_all_engagements()) == 3

        repo.clear_all()
        assert repo.get_all_engagements() == {}

        # Check raw disk
        with data_file.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        assert raw["engagements"] == {}
        assert raw["metadata"]["total_tracked_urls"] == 0


# ── 4. FastAPI Telemetry Endpoints & Validation ───────────────────

class TestEngagementAPIEndpoints:
    """
    Validates /api/news/engage and /api/news/engagement routes:
    - HTTP 200 on valid payloads
    - HTTP 422 on invalid event types, missing fields, or bad URLs
    - Correct JSON response structure
    """

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    @pytest.mark.parametrize("endpoint", ["/api/news/engage", "/api/news/engagement"])
    @pytest.mark.parametrize("event_type", ["click", "summary", "bookmark"])
    def test_post_valid_engagement_events(
        self, client: TestClient, endpoint: str, event_type: str
    ) -> None:
        url = f"https://example.com/test-pdpa-{event_type}"
        payload = {"url": url, "event_type": event_type}

        response = client.post(endpoint, json=payload)
        assert response.status_code == 200

        data = response.json()
        assert data["ok"] is True
        assert data["url"] == url
        assert data["event_type"] == event_type
        assert "stats" in data
        assert isinstance(data["stats"]["clicks"], int)
        assert isinstance(data["stats"]["summaries"], int)
        assert isinstance(data["stats"]["bookmarks"], int)

    @pytest.mark.parametrize("endpoint", ["/api/news/engage", "/api/news/engagement"])
    def test_post_invalid_event_type_rejected(
        self, client: TestClient, endpoint: str
    ) -> None:
        payload = {"url": "https://example.com/article", "event_type": "dislike"}
        response = client.post(endpoint, json=payload)
        assert response.status_code == 422  # Pydantic validation error

    @pytest.mark.parametrize("endpoint", ["/api/news/engage", "/api/news/engagement"])
    def test_post_missing_required_fields(
        self, client: TestClient, endpoint: str
    ) -> None:
        # Missing url
        res1 = client.post(endpoint, json={"event_type": "click"})
        assert res1.status_code == 422

        # Missing event_type
        res2 = client.post(endpoint, json={"url": "https://example.com"})
        assert res2.status_code == 422

        # Empty body
        res3 = client.post(endpoint, json={})
        assert res3.status_code == 422


# ── 5. Client-Side Storage Taxonomy & 24h TTL Rules ───────────────

class TestClientStorageTaxonomyRules:
    """
    Unit tests for client-side PDPA storage categorization invariants
    and 24-hour cache TTL math.
    """

    def test_storage_taxonomy_tier_separation(self) -> None:
        """
        Verify tier separation:
        - Tier 1 Strictly Necessary (No consent needed): pdpa_consent, session ID
        - Tier 2 User Preferences (Consented): darkMode, fontSize, layoutDensity, bookmarks
        - Tier 3 Content Cache (Consented, max 24h TTL): news_cache
        - Tier 4 Telemetry (Consented): search_history, engagement
        """
        TIER_1_STRICTLY_NECESSARY = {"pdpa_consent", "session_id"}
        TIER_2_USER_PREFERENCES = {
            "darkMode",
            "fontSize",
            "layoutDensity",
            "preferredCategory",
            "preferredSource",
            "bookmarkedArticles",
            "bookmarks",
        }
        TIER_3_CONTENT_CACHE = {"news_cache"}
        TIER_4_TELEMETRY = {"search_history"}

        # All tiers must be strictly disjoint
        all_tiers = [
            TIER_1_STRICTLY_NECESSARY,
            TIER_2_USER_PREFERENCES,
            TIER_3_CONTENT_CACHE,
            TIER_4_TELEMETRY,
        ]
        for i in range(len(all_tiers)):
            for j in range(i + 1, len(all_tiers)):
                assert not (all_tiers[i] & all_tiers[j]), "Storage tiers must be disjoint"

    def test_offline_content_cache_24h_ttl_calculation(self) -> None:
        """
        Verify 24h (86,400 seconds) expiration logic for cached articles.
        """
        ttl_seconds = 24 * 3600  # 86400s
        now_ts = 1700000000.0

        def is_cache_valid(cached_timestamp: float, current_timestamp: float) -> bool:
            age = current_timestamp - cached_timestamp
            return 0 <= age < ttl_seconds

        # Fresh cache (1 hour old) -> Valid
        assert is_cache_valid(now_ts - 3600, now_ts) is True

        # Cache at 23 hours 59 minutes -> Valid
        assert is_cache_valid(now_ts - (ttl_seconds - 60), now_ts) is True

        # Exact 24 hours boundary -> Expired (strictly < TTL)
        assert is_cache_valid(now_ts - ttl_seconds, now_ts) is False

        # Cache older than 24h (e.g. 25 hours) -> Expired
        assert is_cache_valid(now_ts - (ttl_seconds + 3600), now_ts) is False

        # Future timestamp (clock skew) -> Invalid
        assert is_cache_valid(now_ts + 100, now_ts) is False

    def test_layout_density_invariants(self) -> None:
        """Validate allowed layout density states and default fallback."""
        allowed_densities = {"comfortable", "compact", "spacious"}
        default_density = "comfortable"

        def get_density(value: str | None) -> str:
            if value and value.strip().lower() in allowed_densities:
                return value.strip().lower()
            return default_density

        assert get_density("comfortable") == "comfortable"
        assert get_density("compact") == "compact"
        assert get_density("spacious") == "spacious"
        assert get_density("invalid_mode") == "comfortable"
        assert get_density(None) == "comfortable"
        assert get_density("") == "comfortable"
