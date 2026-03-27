from __future__ import annotations

import json

from app.core.job_store import JobState, MemoryJobStore, RedisJobStore


class _FakeRedis:
    def __init__(self):
        self.zrem_calls: list[tuple[str, tuple[str, ...]]] = []
        self.zremrangebyscore_calls: list[tuple[str, int, int]] = []

    def zrange(self, key: str, start: int, end: int):
        return [b"job-1", b"job-2"]

    def mget(self, keys: list[str]):
        payload = json.dumps(
            {
                "job_id": "job-1",
                "pair_id": "pair-1",
                "metric": "lpips",
                "model": "alex",
                "normalize": True,
                "img_a_name": "a.png",
                "img_b_name": "b.png",
                "status": "done",
                "has_heatmap": False,
                "created_at_ms": 123,
            }
        )
        return [payload, None]

    def zrem(self, key: str, *members: str):
        self.zrem_calls.append((key, members))
        return 1

    def zremrangebyscore(self, key: str, min_score: int, max_score: int):
        self.zremrangebyscore_calls.append((key, min_score, max_score))
        return 0


def test_redis_list_jobs_prunes_stale_index_entries():
    redis_client = _FakeRedis()
    store = RedisJobStore(
        redis_client,
        prefix="pms-test",
        job_ttl_sec=60,
        heatmap_ttl_sec=60,
        index_gc_interval_sec=1,
    )

    jobs = store.list_jobs()

    assert len(jobs) == 1
    assert jobs[0].job_id == "job-1"
    assert redis_client.zrem_calls == [("pms-test:jobs:index", ("job-2",))]
    assert redis_client.zremrangebyscore_calls


def test_memory_store_prunes_expired_jobs():
    store = MemoryJobStore(job_ttl_sec=1, heatmap_ttl_sec=60)
    store.create_job(
        JobState(
            job_id="expired-job",
            pair_id="pair-1",
            metric="lpips",
            model="alex",
            normalize=True,
            img_a_name="a.png",
            img_b_name="b.png",
            status="done",
            created_at_ms=1,
        )
    )

    assert store.get_job("expired-job") is None


def test_memory_store_prunes_expired_heatmaps():
    store = MemoryJobStore(job_ttl_sec=3600, heatmap_ttl_sec=1)
    store.create_job(
        JobState(
            job_id="job-1",
            pair_id="pair-1",
            metric="lpips",
            model="alex",
            normalize=True,
            img_a_name="a.png",
            img_b_name="b.png",
            status="done",
            created_at_ms=2,
        )
    )
    store.set_heatmap("job-1", b"png")
    store._heatmap_created_at_ms["job-1"] = 1

    assert store.get_heatmap("job-1") is None
    job = store.get_job("job-1")
    assert job is not None
    assert job.has_heatmap is False
