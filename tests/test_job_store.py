from __future__ import annotations

import json

from app.core.job_store import RedisJobStore


class _FakeRedis:
    def __init__(self):
        self.zrem_calls: list[tuple[str, tuple[str, ...]]] = []

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


def test_redis_list_jobs_prunes_stale_index_entries():
    redis_client = _FakeRedis()
    store = RedisJobStore(
        redis_client,
        prefix="pms-test",
        job_ttl_sec=60,
        heatmap_ttl_sec=60,
    )

    jobs = store.list_jobs()

    assert len(jobs) == 1
    assert jobs[0].job_id == "job-1"
    assert redis_client.zrem_calls == [("pms-test:jobs:index", ("job-2",))]
