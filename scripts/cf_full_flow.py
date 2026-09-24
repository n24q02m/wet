"""CF wet-mcp live OAuth full-flow self-test harness.

Drives the deployed wet-mcp Cloudflare Worker (Worker + per-sub Container + KV +
D1 + Vectorize) end-to-end against a named public endpoint. Gate A uses the
MCP-owned relay password; supply approved credentials before running and do not
bypass any additional provider/account interaction required by the target.

Flow (authorization_code + PKCE, DCR public client; ported verbatim from the
mnemo/imagine/email CF harnesses):
  1. DCR register   -- POST /register (RFC 7591) -> client_id
  2. password-grant -- GET /authorize -> POST /login (Gate A relay password) -> form
  3. save config    -- POST /authorize?nonce=... with an explicit subject search
                       chain and optional model/API-base/key groups. Keyless
                       search needs no provider secret. Operator defaults are
                       never copied into the new subject implicitly.
  4. token          -- POST /token (code + verifier) -> bearer JWT
  5. tool call      -- config(status) + search(action="search"); assert the search
                       path resolves real results (URLs) over the CF deployment.

Gate A uses MCP_RELAY_PASSWORD from the MCP-owned /mcp-stack/prod namespace;
there is no alternate namespace or password fallback. Search/model credentials
come from the approved MCP-owned subject configuration. This script never
fetches secrets. Cohere retrieval or Browser Run calls require the campaign's
explicit capped Provider Spend Gate before execution.

Run modes:
  (default)            full flow: config(status) + search, assert real results.
  --save-only          configure one sub + save the token locally
                       (recreate-gate setup half of the state-survives-recreate test).
  --auth-only          replay the SAME token (same sub) and search again WITHOUT
                       re-saving (recreate-gate verify: the sub vault survived KV).
  --two-sub-isolation  two authorization flows; fails as inconclusive if the
                       current stable-sub policy resolves both to one identity.

Example (keyless search; omit model/key env groups to avoid retrieval spend):
  SEARCH_BACKENDS=duckduckgo,startpage python scripts/cf_full_flow.py --endpoint <approved-endpoint>
The selected endpoint and Gate A credential must already be approved/injected.
Do not treat distinct token issuance as proof of distinct subject isolation.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json as _json
import os
import re
import secrets
import sys
import time
import urllib.parse
from pathlib import Path

# No hardcoded host: set CF_ENDPOINT or pass --endpoint https://<your-worker-domain>.
# This self-tests YOUR deployed CF server; creds come from env (MCP_RELAY_PASSWORD +
# provider keys) -- the maintainer injects them via skret, but any export works.
DEFAULT_ENDPOINT = os.environ.get("CF_ENDPOINT", "")

SEARCH_QUERY = "cloudflare workers durable objects"
EXTRACT_URL = "https://example.com"


def _password() -> str:
    pw = os.environ.get("MCP_RELAY_PASSWORD")
    if not pw:
        raise SystemExit(
            "MCP_RELAY_PASSWORD from the MCP-owned /mcp-stack/prod namespace "
            "is required for Gate A; no fallback namespace is permitted."
        )
    return pw


def _creds() -> dict[str, str]:
    """Collect only the explicitly selected personal subject configuration."""
    chain = os.environ.get("SEARCH_BACKENDS", "").strip()
    backends = [name.strip().lower() for name in chain.split(",") if name.strip()]
    if not backends or "searxng" in backends:
        raise SystemExit(
            "Set an explicit SEARCH_BACKENDS chain without personal SearXNG."
        )
    creds = {"SEARCH_BACKENDS": ",".join(backends)}
    search_keys = {
        "tavily": "TAVILY_API_KEY",
        "brave": "BRAVE_API_KEY",
        "exa": "EXA_API_KEY",
        "kagi": "KAGI_API_KEY",
        "firecrawl": "FIRECRAWL_API_KEY",
    }
    for backend in backends:
        key = search_keys.get(backend)
        if key and (value := os.environ.get(key)):
            creds[key] = value

    retrieval_fields = ("EMBEDDING_MODELS", "RERANK_MODELS")
    if any(os.environ.get(field) for field in retrieval_fields) and not all(
        os.environ.get(field) for field in retrieval_fields
    ):
        raise SystemExit("Configure both accepted Cohere retrieval chains explicitly.")
    for field, expected, key, api_base in (
        (
            "LLM_MODELS",
            "openrouter/minimax/minimax-m3:free",
            "OPENROUTER_API_KEY",
            "LLM_API_BASE",
        ),
        (
            "EMBEDDING_MODELS",
            "cohere/embed-v4.0",
            "COHERE_API_KEY",
            "EMBEDDING_API_BASE",
        ),
        (
            "RERANK_MODELS",
            "cohere/rerank-v4.0-fast",
            "COHERE_API_KEY",
            "RERANK_API_BASE",
        ),
    ):
        selected = os.environ.get(field, "").strip()
        if not selected:
            continue
        if selected != expected:
            raise SystemExit(
                f"{field} must be exactly {expected}; no alternate fallback."
            )
        for name in (field, key, api_base):
            value = os.environ.get(name, "").strip()
            if not value:
                raise SystemExit(f"{name} is required for the selected model route.")
            creds[name] = value
    return creds


class _SaveRetry(Exception):
    pass


def get_token(endpoint: str, creds: dict[str, str], *, save_retries: int = 8) -> str:
    """Run the full OAuth flow, retrying on a transient 500 at the credential save
    step (CF Containers outbound-interception race on cold-started instances; E.1).
    Each retry restarts from DCR so the nonce is fresh. ``creds`` is the /authorize
    form payload (EMPTY for wet: search/extract + embed are server-side)."""
    import httpx  # lazy: keep --help importable without httpx installed

    last: Exception | None = None
    for attempt in range(save_retries):
        try:
            return _get_token_once(httpx, endpoint, creds)
        except _SaveRetry as e:
            last = e
            print(
                f"get_token: save 500 (interception race), retry {attempt + 1}/{save_retries}"
            )
            time.sleep(3)
    raise RuntimeError(f"get_token failed after {save_retries} retries: {last}")


def _get_token_once(httpx, endpoint: str, creds: dict[str, str]) -> str:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    ru = "http://localhost:9999/cb"
    pw = _password()
    with httpx.Client(timeout=120, follow_redirects=False) as c:
        cid = c.post(
            f"{endpoint}/register",
            json={
                "client_name": "cf-verify",
                "redirect_uris": [ru],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
                "scope": "offline_access",
            },
        ).json()["client_id"]
        az = c.get(
            f"{endpoint}/authorize",
            params={
                "response_type": "code",
                "client_id": cid,
                "redirect_uri": ru,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "st",
                "scope": "offline_access",
            },
        )
        nxt = urllib.parse.parse_qs(
            urllib.parse.urlparse(az.headers["location"]).query
        )["next"][0]
        lg = c.post(f"{endpoint}/login", data={"next": nxt, "password": pw})
        url = lg.headers["location"]
        url = url if url.startswith("http") else endpoint + url
        form_html = c.get(url).text
        m = re.search(r"/authorize\?nonce=([A-Za-z0-9_\-]+)", form_html)
        assert m, "nonce not found in form"
        nonce = m.group(1)
        sub = c.post(f"{endpoint}/authorize", params={"nonce": nonce}, json=creds)
        if sub.status_code == 500 and "save credentials" in sub.text:
            raise _SaveRetry(sub.text[:120])
        assert sub.status_code == 200, (sub.status_code, sub.text[:300])
        data = sub.json()
        assert data.get("ok"), data
        code = urllib.parse.parse_qs(urllib.parse.urlparse(data["redirect_url"]).query)[
            "code"
        ][0]
        tok = c.post(
            f"{endpoint}/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": ru,
                "client_id": cid,
                "code_verifier": verifier,
            },
        )
        assert tok.status_code == 200, (tok.status_code, tok.text[:300])
        return tok.json()["access_token"]


def _sub_of(token: str) -> str:
    payload = _json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
    return payload.get("sub", "?")


async def _call(s, label, tool, args, *, retries=20, delay=8):
    """Call a tool, retrying while the sub is still propagating (KV cross-colo
    eventual consistency after the setup write; E.2). Returns the concatenated
    text payload, or None on give-up."""
    for i in range(retries):
        try:
            res = await s.call_tool(tool, args)
            txt = "".join(getattr(b, "text", "") for b in res.content)
            if "awaiting_setup" in txt or "Credentials not configured" in txt:
                print(f"{label}: awaiting_setup (KV propagating) try {i + 1}/{retries}")
                await asyncio.sleep(delay)
                continue
            print(f"{label} OK:", txt[:320].replace("\n", " "))
            return txt
        except Exception as e:
            print(f"{label} ERR:", repr(e)[:300])
            return None
    print(f"{label}: gave up after {retries} tries")
    return None


def _assert_search_resolved(txt: str | None) -> None:
    """A real search result is a JSON listing with at least one http(s) URL and no
    hard error. A backend-misconfig (SearXNG vs Tavily) surfaces as an error string
    here -- that is a genuine CF-deployment finding, not a test bug."""
    assert txt is not None, "search returned no payload (gave up while not ready)"
    low = txt.lower()
    assert not low.startswith("error"), f"search returned an error: {txt[:300]}"
    assert "http" in low, f"search did not return any URL result: {txt[:300]}"
    print("ASSERT OK: search resolved real web results over the CF deployment.")


async def _session(endpoint: str, token: str):
    from mcp import ClientSession  # lazy: keep --help importable without mcp installed
    from mcp.client.streamable_http import streamablehttp_client

    return streamablehttp_client(
        f"{endpoint}/mcp", headers={"Authorization": f"Bearer {token}"}
    ), ClientSession


async def _run_search(s) -> str | None:
    return await _call(
        s,
        "SEARCH",
        "search",
        {"action": "search", "query": SEARCH_QUERY, "max_results": 3},
    )


async def _run_extract(s) -> str | None:
    return await _call(
        s,
        "EXTRACT",
        "extract",
        {"action": "extract", "urls": [EXTRACT_URL]},
    )


def _assert_extract_resolved(txt: str | None) -> None:
    """Assert that extract returned non-empty structured content from a real URL."""
    assert txt is not None, "extract returned no payload (gave up while not ready)"
    json_text = txt.strip()
    opening = "<untrusted_extract_content>"
    closing = "</untrusted_extract_content>"
    if json_text.startswith(opening):
        json_text, separator, _warning = json_text[len(opening) :].partition(closing)
        assert separator, "extract wrapper is missing its closing boundary"
        json_text = json_text.strip()
    try:
        payload = _json.loads(json_text)
    except (TypeError, _json.JSONDecodeError) as error:
        raise AssertionError(f"extract returned invalid JSON: {txt[:300]}") from error

    results = payload.get("results") if isinstance(payload, dict) else None
    assert isinstance(results, list) and results, (
        f"extract returned no result records: {txt[:300]}"
    )
    resolved = any(
        isinstance(result, dict)
        and isinstance(result.get("url"), str)
        and result["url"].startswith(("http://", "https://"))
        and any(
            isinstance(result.get(field), str) and result[field].strip()
            for field in ("markdown", "clean_text")
        )
        for result in results
    )
    assert resolved, f"extract returned no resolved page content: {txt[:300]}"
    print("ASSERT OK: extract resolved real page content over the CF deployment.")


def _token_file() -> Path:
    # Keep the dumped JWT OUT of the repo: prefer WET_CF_TOKEN_FILE env override,
    # else the OS temp dir. Writing into scripts/ previously left live tokens
    # inside the checkout (not gitignored).
    import os

    override = os.environ.get("WET_CF_TOKEN_FILE")
    if override:
        return Path(override)
    import tempfile

    return Path(tempfile.gettempdir()) / ".wet_cf_token"


async def run_full(endpoint: str) -> None:
    token = get_token(endpoint, _creds())
    print("TOKEN OK len=", len(token), "sub=", _sub_of(token))
    transport, ClientSession = await _session(endpoint, token)
    async with transport as (r, w, _), ClientSession(r, w) as s:
        await s.initialize()
        tools = await s.list_tools()
        print("TOOLS:", [t.name for t in tools.tools])
        await _call(s, "CONFIG_STATUS", "config", {"action": "status"})
        txt = await _run_search(s)
        _assert_search_resolved(txt)
        extract_txt = await _run_extract(s)
        _assert_extract_resolved(extract_txt)
    print("FULL FLOW PASS.")


async def run_save_only(endpoint: str) -> None:
    token = get_token(endpoint, _creds())
    transport, ClientSession = await _session(endpoint, token)
    async with transport as (r, w, _), ClientSession(r, w) as s:
        await s.initialize()
        await _call(s, "CONFIG_STATUS", "config", {"action": "status"})
    # Dump the EXACT token so --auth-only replays the SAME JWT sub (relay-login mints
    # a fresh random sub per /authorize).
    _token_file().write_text(token)
    print(
        "SAVE-ONLY OK: sub configured=",
        _sub_of(token),
        "(token dumped for --auth-only)",
    )


async def run_auth_only(endpoint: str) -> None:
    tok_path = _token_file()
    if not tok_path.exists():
        raise SystemExit("No dumped token -- run --save-only first.")
    token = tok_path.read_text().strip()
    print("AUTH-ONLY: replaying saved token for sub=", _sub_of(token))
    transport, ClientSession = await _session(endpoint, token)
    async with transport as (r, w, _), ClientSession(r, w) as s:
        await s.initialize()
        txt = await _run_search(s)
        _assert_search_resolved(txt)
        extract_txt = await _run_extract(s)
        _assert_extract_resolved(extract_txt)
    print("AUTH-ONLY PASS: sub survived recreate (KV vault resolved, no re-save).")


async def run_two_sub_isolation(endpoint: str) -> None:
    token_a = get_token(endpoint, _creds())
    sub_a = _sub_of(token_a)
    token_b = get_token(endpoint, _creds())
    sub_b = _sub_of(token_b)
    print(f"sub A={sub_a}  sub B={sub_b}")
    if sub_a == sub_b:
        raise SystemExit(
            f"ISOLATION INCONCLUSIVE: both flows share sub {sub_a} (cannot test bleed)."
        )
    transport, ClientSession = await _session(endpoint, token_b)
    async with transport as (r, w, _), ClientSession(r, w) as s:
        await s.initialize()
        txt = await _run_search(s)
        _assert_search_resolved(txt)
    print(
        "TWO-SUB AUTH/SEARCH OBSERVED: distinct subjects and sub-B search succeeded; "
        "credential-isolation verification remains separate."
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="CF wet-mcp live OAuth full-flow self-test harness.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        required=not DEFAULT_ENDPOINT,
        help=f"Deployed wet endpoint (default: {DEFAULT_ENDPOINT})",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--save-only",
        action="store_true",
        help="Configure one sub with the explicit env-selected chain and save its token locally.",
    )
    mode.add_argument(
        "--auth-only",
        action="store_true",
        help="Replay the SAME token + search WITHOUT re-saving (recreate verify).",
    )
    mode.add_argument(
        "--two-sub-isolation",
        action="store_true",
        help="Check distinct subjects and sub-B search; not a credential-bleed proof.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.save_only:
        asyncio.run(run_save_only(args.endpoint))
    elif args.auth_only:
        asyncio.run(run_auth_only(args.endpoint))
    elif args.two_sub_isolation:
        asyncio.run(run_two_sub_isolation(args.endpoint))
    else:
        asyncio.run(run_full(args.endpoint))
    return 0


if __name__ == "__main__":
    sys.exit(main())
