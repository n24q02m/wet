from wet_mcp.relay_schema import RELAY_SCHEMA


def test_has_model_chain_tasks():
    tasks = {
        f.get("task") for f in RELAY_SCHEMA["fields"] if f.get("type") == "model-chain"
    }
    assert tasks == {"embedding", "rerank", "chat"}


def test_key_fields_are_derived():
    derived = {f["key"] for f in RELAY_SCHEMA["fields"] if f.get("derived")}
    assert "GEMINI_API_KEY" in derived and "JINA_AI_API_KEY" in derived


def test_github_token_not_derived_not_chain():
    # GITHUB_TOKEN is a plain rate-limit key, not a model-provider key.
    gh = next(f for f in RELAY_SCHEMA["fields"] if f["key"] == "GITHUB_TOKEN")
    assert gh["type"] == "password"
    assert not gh.get("derived")
    assert gh.get("task") is None


def test_no_hardcoded_priority_strings():
    for cap in RELAY_SCHEMA.get("capabilityInfo", []):
        assert ">" not in cap.get("priority", "")


def test_model_chain_fields_have_no_hardcoded_suggestions():
    # model-chain dropdowns are fully catalog-driven (live Jina + normalized
    # litellm from mcp-core); they must carry no hand-curated suggestion list.
    by_key = {f["key"]: f for f in RELAY_SCHEMA["fields"]}
    for key in ("EMBEDDING_MODELS", "RERANK_MODELS", "LLM_MODELS"):
        assert not by_key[key].get("suggestedModels"), (
            f"{key} must be catalog-driven, no hardcode"
        )
    # search-chain keeps its named backends (no litellm catalog backs them).
    assert by_key["SEARCH_BACKENDS"]["suggestedModels"] == [
        "searxng",
        "tavily",
        "brave",
        "exa",
        "kagi",
        "openrouter",
        "firecrawl",
        "duckduckgo",
        "startpage",
    ]


def test_vertex_express_key_field_present_and_derived():
    # Selecting a vertex_express/gemini model must surface a credential box, so
    # the schema declares GOOGLE_VERTEX_EXPRESS_API_KEY as a derived field. The
    # unsupported vertex_ai/ variant (SA-only) is never offered nor declared.
    by_key = {f["key"]: f for f in RELAY_SCHEMA["fields"]}
    assert "GOOGLE_VERTEX_EXPRESS_API_KEY" in by_key
    f = by_key["GOOGLE_VERTEX_EXPRESS_API_KEY"]
    assert f.get("derived") is True
    assert f.get("type") == "password"
    assert "VERTEX_AI_API_KEY" not in by_key  # no dead-end field
