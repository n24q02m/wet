"""Multi-key rotation in the search backends: a CSV of keys for one provider
rotates on a key-specific failure (429/401/403) and is byte-identical to today
for a single key."""

import json
from unittest import mock

from wet_mcp.sources.search_backends import TavilyBackend


class _RL(Exception):
    def __init__(self):
        self.status_code = 429


async def test_tavily_rotates_key_on_429():
    used = []

    async def fake_post(self, url, **kw):
        key = kw["json"]["api_key"]
        used.append(key)
        if key == "bad":
            raise _RL()
        resp = mock.Mock(status_code=200)
        resp.json = lambda: {
            "results": [{"url": "https://e", "title": "t", "content": "c"}]
        }
        return resp

    with mock.patch("httpx.AsyncClient.post", new=fake_post):
        out = await TavilyBackend(["bad", "good"]).search("q", max_results=1)
    assert "https://e" in out
    assert used == ["bad", "good"]


async def test_tavily_single_key_unchanged():
    async def fake_post(self, url, **kw):
        resp = mock.Mock(status_code=200)
        resp.json = lambda: {"results": []}
        return resp

    with mock.patch("httpx.AsyncClient.post", new=fake_post):
        out = await TavilyBackend(["solo"]).search("q")
    assert "results" in json.loads(out)
