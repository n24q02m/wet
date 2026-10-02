"""Configuration settings for WET MCP Server.

Two config layers (de-host 2026-09):

- **Instance config** (``~/.wet/config.toml``, host-owned): auth mode + bind
  (``[server]``) and per-task provider cells (``[models.embed|rerank|chat|
  jev_score]``, each ``base_url + api_key + model``, OpenAI-spec, OpenRouter
  pre-wired as default). Loaded via :mod:`hull_core.config.settings` — see
  :mod:`wet_mcp.runtime`.
- **Operational knobs** (this module, env-driven): SearXNG, search backends,
  crawler, cache, local ONNX models. Providers are NOT configured here —
  keys are host-only material and live in the instance config / start env.
"""

import importlib.util
import os
from pathlib import Path

from pydantic_settings import BaseSettings


def _default_data_dir() -> Path:
    """Get default data directory (~/.wet/)."""
    return Path.home() / ".wet"


def _detect_gpu() -> bool:
    """Check if GPU is available via onnxruntime providers."""
    try:
        import onnxruntime as ort

        providers = ort.get_available_providers()
        return (
            "CUDAExecutionProvider" in providers or "DmlExecutionProvider" in providers
        )
    except Exception:
        return False


def _has_gguf_support() -> bool:
    """Check if llama-cpp-python is installed for GGUF models."""
    return importlib.util.find_spec("llama_cpp") is not None


def local_onnx_installed() -> bool:
    """Whether both local ONNX extras exist in this image.

    The slim container build uninstalls ``fastretrieval`` and ``onnxruntime``
    (see ``Dockerfile``), so on that image the local embed/rerank leg is simply
    absent. Resolving that leg from ``DISABLE_LOCAL_EMBED`` /
    ``DISABLE_LOCAL_RERANK`` alone made a slim deployment correct only for as
    long as somebody remembered to set those vars; miss one and the first index
    attempt died inside the lazy ``from fastretrieval import ...`` -- a hard
    failure where a keyword-only degrade was available.

    The image is the ground truth, the flag is only a promise about it, so ask
    the image. ``find_spec`` answers without importing: a full install pays a
    path lookup and a slim one never touches the missing package.
    """

    def _package_present(package: str) -> bool:
        try:
            return importlib.util.find_spec(package) is not None
        except (ImportError, ValueError):
            return False

    return all(
        _package_present(package) for package in ("fastretrieval", "onnxruntime")
    )


def _resolve_local_model(onnx_name: str, gguf_name: str) -> str:
    """Choose local model variant: GGUF if GPU + llama-cpp, else ONNX."""
    if _detect_gpu() and _has_gguf_support():
        return gguf_name
    return onnx_name


class Settings(BaseSettings):
    """WET MCP Server operational configuration (env-driven).

    Environment variables:
    - SEARXNG_URL: SearXNG instance URL (default http://localhost:41592)
    - SEARCH_BACKENDS: CSV provider chain (searxng | tavily | brave | exa |
      kagi | openrouter | firecrawl | duckduckgo | startpage)
    - RERANK_ENABLED / RERANK_TOP_N: search-chain rerank toggles
    - RESPECT_ROBOTS_TXT: enforce robots.txt for extract and crawl
    - BROWSER_BACKENDS: CSV (native | browserless); the Cloudflare
      browser-rendering backend was cut in the de-host
    - DISABLE_LOCAL_SEARCH / DISABLE_LOCAL_BROWSER / DISABLE_LOCAL_EMBED /
      DISABLE_LOCAL_RERANK: per-capability disable-local toggles
    - EMBEDDING_DIMS: embedding dimensions (0 = auto-detect, default 768)
    - LOCAL_EMBEDDING_MODEL / LOCAL_RERANK_MODEL: BYO local ONNX overrides
    - WET_CACHE: enable the web cache (default true)
    - CACHE_DIR: data directory override (default ~/.wet)
    - DOCS_DB_PATH: docs database path override (default ~/.wet/docs.db)

    Provider/model configuration lives in ~/.wet/config.toml (host-owned
    per-task cells) — see :mod:`wet_mcp.runtime`, NOT here.
    """

    # SearXNG
    searxng_url: str = "http://localhost:41592"
    searxng_timeout: int = 30
    # Optional HTTP basic-auth for an external SearXNG behind a reverse-proxy
    # auth gate (e.g. Caddy basic-auth). Both must be set to take effect; the
    # auto-local SearXNG needs neither. Avoids embedding credentials in SEARXNG_URL.
    searxng_auth_user: str = ""  # env SEARXNG_AUTH_USER
    searxng_auth_pass: str = ""  # env SEARXNG_AUTH_PASS

    # Pluggable web search backend selector. "searxng" (default, local) or
    # a cloud adapter (tavily/brave/exa/kagi/openrouter/firecrawl/...).
    search_backend: str = "searxng"  # env SEARCH_BACKEND
    tavily_api_key: str = ""  # env TAVILY_API_KEY

    # SEARCH_BACKENDS: CSV provider chain with runtime fallback (try each, on
    # error/empty -> next, return first non-empty). Empty -> falls back to the
    # single SEARCH_BACKEND for back-compat (= a chain of length 1).
    search_backends: str = ""  # env SEARCH_BACKENDS
    brave_api_key: str = ""  # env BRAVE_API_KEY
    exa_api_key: str = ""  # env EXA_API_KEY
    firecrawl_api_key: str = ""  # env FIRECRAWL_API_KEY (optional — keyless fallback)
    kagi_api_key: str = ""  # env KAGI_API_KEY
    # OpenRouter web-search backend (keyed). The query runs through a chat
    # completion with the openrouter:web_search server tool; sources come back
    # as url_citation annotations. Engine selects the search provider when
    # OpenRouter supports one.
    openrouter_api_key: str = ""  # env OPENROUTER_API_KEY
    openrouter_model: str = (
        "meta-llama/llama-3.3-70b-instruct:free"  # env OPENROUTER_MODEL
    )
    openrouter_base_url: str = "https://openrouter.ai/api/v1"  # env OPENROUTER_BASE_URL
    openrouter_search_engine: str = ""  # env OPENROUTER_SEARCH_ENGINE (empty = default)

    # Optional Cohere rerank post-processing for the search chain (PAID API).
    # Double opt-in: WET_SEARCH_RERANK=1 AND COHERE_API_KEY must both be set;
    # without them the chain never calls Cohere and results keep source order.
    cohere_api_key: str = ""  # env COHERE_API_KEY
    cohere_base_url: str = "https://api.cohere.com"  # env COHERE_BASE_URL
    cohere_rerank_model: str = "rerank-v4.0-fast"  # env COHERE_RERANK_MODEL
    wet_search_rerank: bool = False  # env WET_SEARCH_RERANK
    # Disable-local toggle for search: skip the auto-local SearXNG spawn. An
    # external SEARXNG_URL or cloud backends still work; only the heavy local
    # SearXNG auto-start is suppressed.
    disable_local_search: bool = False  # env DISABLE_LOCAL_SEARCH

    # Crawler
    crawler_headless: bool = True
    crawler_timeout: int = 60
    respect_robots_txt: bool = False  # env RESPECT_ROBOTS_TXT

    # Browser backend chain for the headless (JS-render) leg. BROWSER_BACKENDS
    # CSV (order = agent escalation/fallback): native (in-process chromium) |
    # browserless (self-host REST). Empty -> native locally.
    browser_backends: str = ""  # env BROWSER_BACKENDS
    disable_local_browser: bool = False  # env DISABLE_LOCAL_BROWSER
    browserless_url: str = ""  # env BROWSERLESS_URL
    browserless_token: str = ""  # env BROWSERLESS_TOKEN

    # Optional, key-gated CAPTCHA escalation tier (CapSolver). Off unless a key
    # is set (host brings their own). When set, a CaptchaStrategy is appended
    # as the last escalation tier and only acts on a detected
    # reCAPTCHA/Cloudflare Turnstile.
    capsolver_api_key: str = ""  # env CAPSOLVER_API_KEY

    # SearXNG Management
    # web-core runner tries Docker fallback first, then subprocess install.
    # On Windows, Docker path handles lxml/build-tool constraints that would
    # otherwise block the subprocess path -- so auto-start works cross-platform
    # as long as Docker Desktop OR build tools are available.
    wet_auto_searxng: bool = True
    wet_searxng_port: int = 41592

    # Tool execution timeout (seconds, 0 = no timeout)
    tool_timeout: int = 120

    # Media
    download_dir: str = "~/.wet/downloads"

    # Cache (web operations)
    wet_cache: bool = True  # Enable/disable web cache
    # Per-provider query budget for the web-search chain (env
    # WET_SEARCH_BUDGET). Counts attempts per provider per process; when a
    # provider reaches the cap the chain advances past it with a structured
    # error naming it. 0 (default) = unlimited.
    wet_search_budget: int = 0
    cache_dir: str = ""  # Data directory, default: ~/.wet

    # Docs storage
    docs_db_path: str = ""  # Default: ~/.wet/docs.db

    # Embedding width + local ONNX toggles (cloud model = [models.embed] cell
    # in ~/.wet/config.toml)
    embedding_dims: int = 0  # 0 = use server default (768)

    # Per-capability disable-local toggles. Turn OFF the heavy local
    # fastretrieval ONNX fallback (~570MB download) WITHOUT pinning a cloud
    # model. Independent per task.
    disable_local_embed: bool = False  # env DISABLE_LOCAL_EMBED
    disable_local_rerank: bool = False  # env DISABLE_LOCAL_RERANK

    # B2: docs vector-store embedding-model identity guard. When the active
    # embedding model/dims differ from what the store was built with, DocsDB
    # raises EmbeddingModelMismatch by default (safe). Set this to rebuild:
    # the vector table is dropped + re-stamped and the docs-embed pipeline
    # repopulates it on the next pass.
    reindex_on_model_change: bool = False  # env REINDEX_ON_MODEL_CHANGE

    # BYO local model override. When set, the LOCAL embedding/rerank backend
    # loads this model id instead of the bundled Qwen3 default. A non-built-in
    # id is registered with fastretrieval at startup using the companion vars
    # below.
    local_embedding_model: str = ""  # env LOCAL_EMBEDDING_MODEL
    local_rerank_model: str = ""  # env LOCAL_RERANK_MODEL
    # Companion vars for registering a custom LOCAL embedding model (BYO ONNX).
    # Required only when LOCAL_EMBEDDING_MODEL is a non-built-in id.
    local_embedding_pooling: str = "MEAN"  # MEAN | CLS | LAST_TOKEN | DISABLED
    local_embedding_dim: int = 0  # required (>0) for a custom embedding model
    local_embedding_normalize: bool = True
    local_embedding_model_file: str = "onnx/model.onnx"
    # Companion var for registering a custom LOCAL reranker (BYO ONNX
    # cross-encoder). Used only when LOCAL_RERANK_MODEL is a non-built-in id.
    local_rerank_model_file: str = "onnx/model.onnx"  # env LOCAL_RERANK_MODEL_FILE

    # Reranking
    rerank_enabled: bool = True  # Enable reranking (local fallback always available)
    rerank_top_n: int = 10  # Return top N after reranking

    # Logging
    log_level: str = "INFO"

    # Local file conversion
    convert_max_file_size: int = 104857600  # 100MB
    convert_allowed_dirs: str = ""  # comma-separated absolute paths, empty = allow all

    model_config = {"env_prefix": "", "case_sensitive": False}

    # --- Path helpers (aligned with the de-host storage layout) ---

    def get_data_dir(self) -> Path:
        """Get data directory: CACHE_DIR if set, otherwise ~/.wet/."""
        if self.cache_dir:
            return Path(self.cache_dir).expanduser()
        return _default_data_dir()

    def get_db_path(self) -> Path:
        """Get resolved docs database path (default ~/.wet/docs.db)."""
        if self.docs_db_path:
            return Path(self.docs_db_path).expanduser()
        return self.get_data_dir() / "docs.db"

    def auto_searxng_enabled(self) -> bool:
        """Whether to auto-spawn a local SearXNG.

        ``DISABLE_LOCAL_SEARCH`` suppresses the heavy local SearXNG auto-start
        regardless of ``WET_AUTO_SEARXNG``; an external ``SEARXNG_URL`` or the
        cloud search backends still serve search.
        """
        return self.wet_auto_searxng and not self.disable_local_search

    def browser_backend_chain(self) -> list[str]:
        """Ordered headless backends for the JS-render leg.

        ``BROWSER_BACKENDS`` CSV; empty -> ``['native']`` (in-process chromium).
        ``DISABLE_LOCAL_BROWSER`` drops the ``native`` leg so a slim container
        renders only via the self-host browserless backend.
        """
        raw = (os.getenv("BROWSER_BACKENDS", self.browser_backends) or "").strip()
        names: list[str] = (
            [n.strip().lower() for n in raw.split(",") if n.strip()]
            if raw
            else ["native"]
        )
        if self.disable_local_browser:
            names = [n for n in names if n != "native"]
        return names

    # --- Local model resolution ---

    def resolve_local_embedding_model(self) -> str:
        """Resolve local embedding model: GGUF if GPU + llama-cpp, else ONNX.

        LOCAL_EMBEDDING_MODEL overrides the bundled default (BYO model).
        """
        if self.local_embedding_model:
            return self.local_embedding_model
        return _resolve_local_model(
            "n24q02m/Qwen3-Embedding-0.6B-ONNX",
            "n24q02m/Qwen3-Embedding-0.6B-GGUF",
        )

    def local_embed_available(self) -> bool:
        """Whether the local ONNX embedding leg is both allowed AND present.

        ``DISABLE_LOCAL_EMBED`` is the operator's answer;
        :func:`local_onnx_installed` is the image's — a leg the build removed
        is not available however the config reads.
        """
        return not self.disable_local_embed and local_onnx_installed()

    def local_rerank_available(self) -> bool:
        """Whether the local ONNX rerank leg is both allowed AND present."""
        return not self.disable_local_rerank and local_onnx_installed()

    def resolve_local_rerank_model(self) -> str:
        """Resolve local rerank model: GGUF if GPU + llama-cpp, else ONNX."""
        if self.local_rerank_model:
            return self.local_rerank_model
        return _resolve_local_model(
            "n24q02m/Qwen3-Reranker-0.6B-ONNX-YesNo",
            "n24q02m/Qwen3-Reranker-0.6B-GGUF",
        )


settings = Settings()
