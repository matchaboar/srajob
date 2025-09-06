from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import types
import pytest

# Target module
import os, sys
sys.path.insert(0, os.path.abspath('.'))
from job_scrape_application.workflows import activities as acts


class FakeResponse:
    def __init__(self, json_data: Any, status_code: int = 200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> Any:
        return self._json


class FakeAsyncClient:
    def __init__(self, timeout: int | float | None = None):
        # Sites state
        self.sites: Dict[str, Dict[str, Any]] = {}
        self._id_counter = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def _insert_site(self, name: str) -> str:
        self._id_counter += 1
        sid = f"site_{self._id_counter}"
        self.sites[sid] = {
            "_id": sid,
            "name": name,
            "url": f"https://example.com/{name}",
            "enabled": True,
            "completed": False,
            "lockExpiresAt": None,
            "lockedBy": None,
            "lastRunAt": None,
        }
        return sid

    # Minimal POST router for the endpoints we use
    async def post(self, url: str, json: Optional[Dict[str, Any]] = None):
        if url.endswith("/api/sites"):
            # Create site
            sid = self._insert_site(json.get("name") or "site")
            return FakeResponse({"success": True, "id": sid})
        if url.endswith("/api/sites/lease"):
            # Lease first unlocked + not completed
            now = 0
            for s in self.sites.values():
                if s.get("completed"):
                    continue
                if s.get("lockExpiresAt") and s["lockExpiresAt"] > now:
                    continue
                s["lockedBy"] = json.get("workerId")
                s["lockExpiresAt"] = now + int(json.get("lockSeconds") or 300) * 1000
                return FakeResponse(s)
            return FakeResponse(None)
        if url.endswith("/api/sites/complete"):
            sid = json.get("id")
            s = self.sites.get(sid)
            assert s, f"unknown site id {sid}"
            s["completed"] = True
            s["lockedBy"] = None
            s["lockExpiresAt"] = None
            return FakeResponse({"success": True})
        return FakeResponse({"error": "not found"}, status_code=404)


@pytest.mark.asyncio
async def test_lease_complete_sequence(monkeypatch):
    # Monkeypatch httpx.AsyncClient used inside activities
    fake_client = FakeAsyncClient()

    class _Factory:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return fake_client

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(acts.httpx, "AsyncClient", _Factory)

    # Seed two sites via the HTTP route used by activities.store/lease/complete
    base = (acts.settings.convex_http_url or "http://local").rstrip("/")
    async with fake_client as c:
        # Create two
        r1 = await c.post(base + "/api/sites", json={"name": "A", "url": "u", "enabled": True})
        r1.raise_for_status(); sid1 = r1.json()["id"]
        r2 = await c.post(base + "/api/sites", json={"name": "B", "url": "u", "enabled": True})
        r2.raise_for_status(); sid2 = r2.json()["id"]

    # Lease one
    leased1 = await acts.lease_site("worker-x", 60)
    assert leased1 is not None
    first_id = leased1["_id"]
    assert first_id in (sid1, sid2)

    # Complete it
    await acts.complete_site(first_id)

    # Lease again => different id
    leased2 = await acts.lease_site("worker-x", 60)
    assert leased2 is not None
    second_id = leased2["_id"]
    assert second_id != first_id
