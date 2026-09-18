"""Config schema for relay page setup.

Tasks are model chains (order = litellm fallback). Provider key fields are
``derived`` -- the relay widget surfaces them automatically for the providers
the chosen models reference. ``GITHUB_TOKEN`` is a plain (non-derived) key:
it is NOT a model-provider key, just an optional GitHub API rate-limit bump
for library docs discovery.
"""

from __future__ import annotations

from typing import Any

# model-chain tasks (embedding/rerank/chat) carry NO hardcoded suggestions: the
# relay widget's dropdown is fully catalog-driven (live Jina + normalized litellm
# from mcp-core). Only the search-chain below keeps a curated list, since its
# named backends are not litellm models and have no catalog to search.
# Named search backends (no model-prefix inference; resolved via providerKeys).
_SEARCH_BACKENDS = [
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


def _key_field(key: str, label: str, ph: str, url: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "type": "password",
        "placeholder": ph,
        "helpUrl": url,
        "helpText": "Multiple keys: comma-separate for automatic rotation on rate-limit.",
        "derived": True,
        "required": False,
    }


def _api_base_field(key: str, label: str, help_text: str) -> dict[str, Any]:
    # Always-visible (not derived): the renderer only reveals a derived field
    # when a model chip derives that exact provider ENV key, and no model
    # derives *_API_BASE, so a derived endpoint field would stay hidden. The
    # optional badge comes from required:false. Value is SSRF-vetted per-sub in
    # mcp_core.llm dispatch before any request.
    return {
        "key": key,
        "label": label,
        "type": "url",
        "placeholder": "https://gateway.example/…",
        "helpText": help_text,
        "required": False,
    }


RELAY_SCHEMA: dict[str, Any] = {
    "server": "wet-mcp",
    "displayName": "Web Extended Toolkit",
    "description": (
        "Pick models per task (order = fallback). Leave a task empty for "
        "local ONNX (embedding/rerank) — LLM features need at least one model. "
        "Key fields appear automatically for the providers your models use. "
        "Search runs local SearXNG by default in single-user mode; hosted users "
        "configure their own chain. Keyless DuckDuckGo/Startpage are available."
    ),
    "fields": [
        {
            "key": "EMBEDDING_MODELS",
            "label": "Embedding models",
            "type": "model-chain",
            "task": "embedding",
            "hasLocal": True,
            "placeholder": "add embedding model…",
        },
        _api_base_field(
            "EMBEDDING_API_BASE",
            "Embedding endpoint",
            "Custom endpoint / CF AI Gateway. Cohere: {gw}/cohere/v2/embed",
        ),
        {
            "key": "RERANK_MODELS",
            "label": "Rerank models",
            "type": "model-chain",
            "task": "rerank",
            "hasLocal": True,
            "placeholder": "add rerank model…",
        },
        _api_base_field(
            "RERANK_API_BASE",
            "Rerank endpoint",
            "Custom endpoint / CF AI Gateway. Cohere: {gw}/cohere (litellm appends /v1/rerank)",
        ),
        {
            "key": "LLM_MODELS",
            "label": "LLM models",
            "type": "model-chain",
            "task": "chat",
            "hasLocal": False,
            "placeholder": "add LLM model…",
        },
        _api_base_field(
            "LLM_API_BASE",
            "LLM endpoint",
            "Custom endpoint / CF AI Gateway for LLM calls.",
        ),
        {
            "key": "SEARCH_BACKENDS",
            "label": "Search providers",
            "type": "search-chain",
            "task": "search",
            "suggestedModels": _SEARCH_BACKENDS,
            "providerKeys": {
                "searxng": "SEARXNG_URL",
                "tavily": "TAVILY_API_KEY",
                "brave": "BRAVE_API_KEY",
                "exa": "EXA_API_KEY",
                "kagi": "KAGI_API_KEY",
                "openrouter": "OPENROUTER_API_KEY",
                "firecrawl": "FIRECRAWL_API_KEY",
            },
            "hasLocal": True,
            "noun": "providers",
            "localLabel": "local SearXNG",
            "placeholder": "add search provider…",
        },
        _key_field(
            "JINA_AI_API_KEY", "Jina AI API Key", "jina_...", "https://jina.ai/api-key"
        ),
        _key_field(
            "GEMINI_API_KEY",
            "Gemini API Key",
            "AIza...",
            "https://aistudio.google.com/apikey",
        ),
        _key_field(
            "OPENAI_API_KEY",
            "OpenAI API Key",
            "sk-...",
            "https://platform.openai.com/api-keys",
        ),
        _key_field(
            "OPENROUTER_API_KEY",
            "OpenRouter API Key",
            "",
            "https://openrouter.ai/settings/keys",
        ),
        _key_field(
            "COHERE_API_KEY",
            "Cohere API Key",
            "co-...",
            "https://dashboard.cohere.com/api-keys",
        ),
        _key_field(
            "ANTHROPIC_API_KEY",
            "Anthropic API Key",
            "sk-ant-...",
            "https://console.anthropic.com/settings/keys",
        ),
        _key_field("XAI_API_KEY", "xAI API Key", "xai-...", "https://console.x.ai/"),
        _key_field(
            "GOOGLE_VERTEX_EXPRESS_API_KEY",
            "Vertex AI (Express) API Key",
            "AQ...",
            "https://cloud.google.com/vertex-ai/generative-ai/docs/start/express-mode/overview",
        ),
        _key_field(
            "TAVILY_API_KEY",
            "Tavily API Key",
            "tvly-...",
            "https://app.tavily.com/home",
        ),
        _key_field(
            "BRAVE_API_KEY",
            "Brave Search API Key",
            "BSA...",
            "https://api-dashboard.search.brave.com/app/keys",
        ),
        _key_field(
            "EXA_API_KEY", "Exa API Key", "exa_...", "https://dashboard.exa.ai/api-keys"
        ),
        _key_field(
            "KAGI_API_KEY", "Kagi API Key", "", "https://kagi.com/settings?p=api"
        ),
        _key_field(
            "FIRECRAWL_API_KEY",
            "Firecrawl API Key (optional)",
            "",
            "https://www.firecrawl.dev/app/api-keys",
        ),
        {
            # SearXNG is a named backend (not a model-prefix provider): selecting
            # it in the search chain derives this field via providerKeys so the
            # user can point at an external instance. Blank -> auto-started local
            # SearXNG. Optional basic-auth via env SEARXNG_AUTH_USER/PASS.
            "key": "SEARXNG_URL",
            "label": "SearXNG URL (external instance)",
            "type": "url",
            "placeholder": "https://searxng.example.com",
            "helpText": (
                "Point at an external SearXNG. Leave blank to use the local "
                "auto-started instance. Basic-auth (if any): set env "
                "SEARXNG_AUTH_USER / SEARXNG_AUTH_PASS."
            ),
            "derived": True,
            "required": False,
        },
        {
            "key": "GITHUB_TOKEN",
            "label": "GitHub Personal Access Token",
            "type": "password",
            "placeholder": "ghp_...",
            "helpUrl": "https://github.com/settings/tokens",
            "helpText": "Optional. Bumps GitHub API rate limit (60->5000 req/hr) for library docs discovery.",
            "required": False,
        },
        {
            "key": "CAPSOLVER_API_KEY",
            "label": "CapSolver API Key",
            "type": "password",
            "placeholder": "CAP-...",
            "helpUrl": "https://dashboard.capsolver.com/",
            "helpText": "Optional. Solves reCAPTCHA / Cloudflare Turnstile on protected pages during extraction.",
            "required": False,
        },
    ],
    "capabilityInfo": [
        {
            "label": "Search",
            "priority": "configurable",
            "description": (
                "Web search. Public single-user mode supports local SearXNG. "
                "Hosted chains and provider keys are isolated per subject."
            ),
        },
        {
            "label": "Extraction",
            "priority": "Built-in (httpx + readability)",
            "description": "Content extraction from URLs. No API key needed.",
        },
        {
            "label": "Embedding",
            "priority": "configurable",
            "description": "Vector embeddings for docs search. Empty = local fastretrieval ONNX.",
        },
        {
            "label": "Reranking",
            "priority": "configurable",
            "description": "Re-ranks search results for accuracy. Empty = local fastretrieval cross-encoder.",
        },
        {
            "label": "LLM",
            "priority": "configurable",
            "description": "Structured extraction. Empty = these features are limited.",
        },
    ],
}
