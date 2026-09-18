"""Configuration settings for WET MCP Server."""

import importlib.util
import os
from pathlib import Path

from loguru import logger
from mcp_core.auth import BundledClientSpec, resolve_bundled_client
from mcp_core.chains import resolve_backend
from mcp_core.llm.providers import key_env_for_model
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


def _default_data_dir() -> Path:
    """Get default data directory (~/.wet-mcp/)."""
    return Path.home() / ".wet-mcp"


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
    attempt died inside the lazy ``from fastretrieval import ...``, recorded in
    D1 as ``ModuleNotFoundError: No module named 'fastretrieval'`` with zero
    chunks (#1630) -- a hard failure where a keyword-only degrade was available.

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


# Google Drive OAuth client identity (BYO resolver chain: CLI > env pair >
# bundled default, unless USE_BUNDLED_GOOGLE_CLIENT explicitly disables it).
# The Desktop/Installed OAuth client_secret is public by design per
# https://developers.google.com/identity/protocols/oauth2#installed -- hardcoding
# it here is safe and gives users zero-config sync after relay submit.
_BUNDLED_GOOGLE_CLIENT_ID = (
    "147668446467-olf2cf6e49rshqv9quvhq639110oc6hc.apps.googleusercontent.com"
)
_BUNDLED_GOOGLE_CLIENT_SECRET = "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"  # gitleaks:allow
_GOOGLE_CLIENT_SPEC = BundledClientSpec(
    provider="google-drive",
    env_id="GOOGLE_DRIVE_CLIENT_ID",
    env_secret="GOOGLE_DRIVE_CLIENT_SECRET",
    bundled_id=_BUNDLED_GOOGLE_CLIENT_ID,
    bundled_secret=_BUNDLED_GOOGLE_CLIENT_SECRET,
    use_bundled_env="USE_BUNDLED_GOOGLE_CLIENT",
)


class Settings(BaseSettings):
    """WET MCP Server configuration.

    Environment variables:
    - SEARXNG_URL: SearXNG instance URL (default: http://localhost:8080)
    - API_KEYS: Provider API keys, supports multiple providers
        Format: "ENV_VAR:key,ENV_VAR:key,..."
        Or file path: "@path/to/keys"
        Example: "GOOGLE_API_KEY:AIza...,COHERE_API_KEY:..."
        Embedding providers: Jina, Google, OpenAI, Cohere
        Reranking providers: Jina, Cohere
    - EMBEDDING_MODELS: Embedding model chain "provider/model,..." (order =
        litellm fallback). Empty -> curated default filtered to configured
        keys; no usable key -> local ONNX. Backend inferred from this chain.
        Cloudflare serverless: set EMBEDDING_MODELS and RERANK_MODELS to
        cloud-only chains (e.g. `jina_ai/jina-embeddings-v5-text-small`,
        `jina_ai/jina-reranker-v3`) with JINA_AI_API_KEY so no local ONNX
        model is downloaded.
    - RERANK_MODELS: Rerank model chain (same semantics as EMBEDDING_MODELS).
    - EMBEDDING_DIMS: Embedding dimensions (0 = auto-detect, default 768)
    - RERANK_ENABLED: Enable reranking (default: true)
    - RERANK_TOP_N: Return top N results after reranking (default: 10)
    - RESPECT_ROBOTS_TXT: Enforce robots.txt for extract and crawler actions
        (default: false)
    - EMBEDDING_MODEL / EMBEDDING_BACKEND / RERANK_MODEL / RERANK_BACKEND:
        DEPRECATED (2026-06-11) -- singular model + backend env vars, folded
        into the plural *_MODELS chain (honored one release with a warning).
        Local: GGUF if GPU + llama-cpp-python, else ONNX.
    - SYNC_ENABLED: Enable Google Drive sync (default: true)
    - SYNC_FOLDER: Google Drive folder name (default: "wet-mcp")
    - SYNC_INTERVAL: Auto-sync interval in seconds (default: 300)
    - GOOGLE_DRIVE_CLIENT_ID: OAuth client ID for Google Drive sync

    Provider Mode Detection (resolve_provider_mode):
    - "sdk": API_KEYS set -> direct SDK calls
    - "local": no keys -> local ONNX models only
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
    # "tavily" (cloud adapter for CF where embedded SearXNG cannot run).
    search_backend: str = "searxng"  # env SEARCH_BACKEND: searxng | tavily | brave | exa | kagi | openrouter | firecrawl | duckduckgo | startpage
    tavily_api_key: str = ""  # env TAVILY_API_KEY

    # SEARCH_BACKENDS: CSV provider chain with runtime fallback (try each, on
    # error/empty -> next, return first non-empty). Empty -> falls back to the
    # single SEARCH_BACKEND for back-compat (= a chain of length 1). Providers:
    # searxng (self-host) | tavily | brave | exa | kagi | openrouter (cloud,
    # keyed) | firecrawl (cloud, key optional — keyless attempt) |
    # duckduckgo | startpage (credential-free HTML scrape, uvx-safe).
    search_backends: str = ""  # env SEARCH_BACKENDS
    brave_api_key: str = ""  # env BRAVE_API_KEY
    exa_api_key: str = ""  # env EXA_API_KEY
    firecrawl_api_key: str = ""  # env FIRECRAWL_API_KEY (optional — keyless fallback)
    kagi_api_key: str = ""  # env KAGI_API_KEY
    # OpenRouter web-search backend (keyed). The query runs through a chat
    # completion with the openrouter:web_search server tool; sources come back
    # as url_citation annotations. base_url is overridable for a CF AI Gateway
    # route; engine selects the search provider when OpenRouter supports one.
    openrouter_api_key: str = ""  # env OPENROUTER_API_KEY (CSV for rotation)
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
    # Disable-local toggle for search (cross-cutting, see mcp_core.chains): skip
    # the auto-local SearXNG spawn. An external SEARXNG_URL or cloud backends
    # still work; only the heavy local SearXNG auto-start is suppressed.
    disable_local_search: bool = False  # env DISABLE_LOCAL_SEARCH

    # Crawler
    crawler_headless: bool = True
    crawler_timeout: int = 60
    respect_robots_txt: bool = False  # env RESPECT_ROBOTS_TXT

    # Browser backend chain for the headless (JS-render) leg. BROWSER_BACKENDS
    # CSV (order = agent escalation/fallback): native (in-process chromium) |
    # cf-browser-rendering (Cloudflare REST) | browserless (self-host REST).
    # Empty -> native locally; the deploy sets it explicitly on container
    # transports to offload rendering. DISABLE_LOCAL_BROWSER drops the heavy
    # in-process native chromium (the browser capability's disable-local toggle).
    browser_backends: str = ""  # env BROWSER_BACKENDS
    disable_local_browser: bool = False  # env DISABLE_LOCAL_BROWSER
    cf_account_id: str = ""  # env CF_ACCOUNT_ID
    cf_browser_rendering_token: str = ""  # env CF_BROWSER_RENDERING_TOKEN
    browserless_url: str = ""  # env BROWSERLESS_URL
    browserless_token: str = ""  # env BROWSERLESS_TOKEN

    # Optional, key-gated CAPTCHA escalation tier (CapSolver). Off unless a key
    # is set (user brings their own — per-sub, user-funded). When set, a
    # CaptchaStrategy is appended as the last escalation tier and only acts on a
    # detected reCAPTCHA/Cloudflare Turnstile. Solves the CAPTCHA layer only, not
    # IP reputation.
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
    download_dir: str = "~/.wet-mcp/downloads"

    # Media Analysis (Provider API keys)
    api_keys: SecretStr | None = None  # ENV_VAR:key,ENV_VAR:key (multiple providers)

    llm_models: str = ""  # provider/model fallback chain; empty -> key-gated default
    llm_temperature: float | None = None

    # Cache (web operations)
    wet_cache: bool = True  # Enable/disable web cache
    # Per-provider query budget for the web-search chain (env
    # WET_SEARCH_BUDGET). Counts attempts per provider per process; when a
    # provider reaches the cap the chain advances past it with a structured
    # error naming it. 0 (default) = unlimited.
    wet_search_budget: int = 0
    cache_dir: str = ""  # Cache database directory, default: ~/.wet-mcp

    # Docs storage
    docs_db_path: str = ""  # Default: ~/.wet-mcp/docs.db

    # --- Cloudflare serverless deployment (Phase 2) ---
    # docs_db_backend selects the relational + FTS5 store: "sqlite" (default,
    # local DocsDB) or "cf-d1" (DocsDBCfBackend over Cloudflare D1 + Vectorize).
    public_url: str = ""  # env PUBLIC_URL (Worker custom domain)
    mcp_storage_backend: str = "local"  # env MCP_STORAGE_BACKEND: local | cf-kv
    mcp_kv_base_url: str = ""  # env MCP_KV_BASE_URL (outbound handler)
    mcp_kv_token: str = ""  # env MCP_KV_TOKEN (REST fallback only)
    mcp_dcr_server_secret: str = ""  # env MCP_DCR_SERVER_SECRET (multi-user)
    docs_db_backend: str = "sqlite"  # env DOCS_DB_BACKEND: sqlite | cf-d1
    mcp_d1_base_url: str = ""  # env MCP_D1_BASE_URL
    mcp_d1_token: str = ""  # env MCP_D1_TOKEN (REST fallback only)
    mcp_vectorize_base_url: str = ""  # env MCP_VECTORIZE_BASE_URL
    mcp_vectorize_idx: str = ""  # env MCP_VECTORIZE_IDX (required for cf-d1)
    mcp_vectorize_token: str = ""  # env MCP_VECTORIZE_TOKEN (REST fallback only)

    # Per-task model chains "provider/model,provider/model" (order = litellm
    # fallback). Empty -> local ONNX. Replaces the priority-router auto-detect
    # and the singular EMBEDDING_MODEL/EMBEDDING_BACKEND (deprecated shims).
    embedding_models: str = ""
    rerank_models: str = ""
    # DEPRECATED (2026-06-11): folded into EMBEDDING_MODELS/RERANK_MODELS,
    # honored one release with a warning. Backend now inferred.

    # Per-capability disable-local toggles (cross-cutting; see mcp_core.chains).
    # Turn OFF the heavy local fastretrieval ONNX fallback (~570MB download) WITHOUT
    # pinning a specific cloud model. Toggle on + no cloud chain => the feature
    # is gracefully UNAVAILABLE (clear status), never silently forced to a
    # provider. Independent per task: a user may disable local embed but keep
    # local rerank, or vice versa.
    disable_local_embed: bool = False  # env DISABLE_LOCAL_EMBED
    disable_local_rerank: bool = False  # env DISABLE_LOCAL_RERANK

    # Embedding
    embedding_model: str = ""  # DEPRECATED: folded into EMBEDDING_MODELS
    embedding_dims: int = 0  # 0 = use server default (768)
    embedding_backend: str = ""  # DEPRECATED: inferred from EMBEDDING_MODELS

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
    # Companion var for registering a custom LOCAL reranker (BYO ONNX cross-
    # encoder). Used only when LOCAL_RERANK_MODEL is a non-built-in id. A cross-
    # encoder needs no dim/pooling -- just the ONNX file path within the repo.
    local_rerank_model_file: str = "onnx/model.onnx"  # env LOCAL_RERANK_MODEL_FILE

    # Reranking
    rerank_enabled: bool = (
        True  # Enable reranking (always available via local fallback)
    )
    rerank_backend: str = ""  # DEPRECATED: inferred from RERANK_MODELS
    rerank_model: str = ""  # DEPRECATED: folded into RERANK_MODELS
    rerank_top_n: int = 10  # Return top N after reranking

    # Docs sync (Google Drive API)
    sync_enabled: bool = True
    sync_folder: str = "wet-mcp"  # Google Drive folder name
    sync_interval: int = 300  # seconds, 0 = manual only
    google_drive_client_id: str = Field(
        default_factory=lambda: resolve_bundled_client(_GOOGLE_CLIENT_SPEC).client_id
    )
    google_drive_client_secret: str = Field(
        default_factory=lambda: (
            resolve_bundled_client(_GOOGLE_CLIENT_SPEC).client_secret
        )
    )

    # S3-compatible sync (operator deploy mode).
    # When SYNC_S3_BUCKET is non-empty the active backend resolves to "s3"
    # and the Google Drive OAuth flow is DISABLED. Used in HTTP / Docker
    # deploy mode where the operator pre-provisions a bucket for docs.db
    # backup/restore instead of relying on per-user GDrive OAuth.
    # Mutually exclusive with the GDrive flow at deployment level - the
    # two backends MUST NOT both be active in the same process.
    sync_s3_bucket: str = ""
    sync_s3_region: str = "us-east-1"
    sync_s3_endpoint: str = ""  # custom endpoint for R2 / B2 / MinIO
    sync_s3_access_key_id: str = ""
    sync_s3_secret_access_key: str = ""
    sync_s3_prefix: str = "docs/"

    # Logging
    log_level: str = "INFO"

    # Local file conversion
    convert_max_file_size: int = 104857600  # 100MB
    convert_allowed_dirs: str = ""  # comma-separated absolute paths, empty = allow all

    model_config = {"env_prefix": "", "case_sensitive": False}

    # --- Path helpers (aligned with mnemo-mcp) ---

    def get_data_dir(self) -> Path:
        """Get data directory.

        Uses CACHE_DIR if set, otherwise ~/.wet-mcp/.
        """
        if self.cache_dir:
            return Path(self.cache_dir).expanduser()
        return _default_data_dir()

    def get_db_path(self) -> Path:
        """Get resolved docs database path."""
        if self.docs_db_path:
            return Path(self.docs_db_path).expanduser()
        return self.get_data_dir() / "docs.db"

    def get_cache_db_path(self) -> Path:
        """Get resolved web cache database path."""
        return self.get_data_dir() / "cache.db"

    def auto_searxng_enabled(self) -> bool:
        """Whether to auto-spawn a local SearXNG.

        ``DISABLE_LOCAL_SEARCH`` suppresses the heavy local SearXNG auto-start
        (the search capability's disable-local toggle) regardless of
        ``WET_AUTO_SEARXNG``; an external ``SEARXNG_URL`` or the cloud search
        backends still serve search.
        """
        return self.wet_auto_searxng and not self.disable_local_search

    def browser_backend_chain(self) -> list[str]:
        """Ordered headless backends for the JS-render leg.

        ``BROWSER_BACKENDS`` CSV; empty -> ``['native']`` (in-process chromium).
        ``DISABLE_LOCAL_BROWSER`` drops the ``native`` leg (the browser
        capability's disable-local toggle) so a slim container renders only via
        the cloud/self-host backends.
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

    # --- API key management ---

    # Some providers use different env vars for embeddings vs completions
    _ENV_ALIASES: dict[str, str] = {
        "GOOGLE_API_KEY": "GEMINI_API_KEY",
    }

    def setup_api_keys(self) -> dict[str, list[str]]:
        """Parse API_KEYS and set env vars for provider SDKs.

        Format: "GOOGLE_API_KEY:AIza...,OPENAI_API_KEY:sk-..."
        Or file: "@path/to/keys_file"

        Also sets aliases (e.g., GOOGLE_API_KEY -> GEMINI_API_KEY)
        because Gemini SDK uses GEMINI_API_KEY.

        Returns:
            Dict mapping env var name to list of API keys.
        """
        if not self.api_keys:
            return {}

        keys_by_env: dict[str, list[str]] = {}
        api_keys_str = self.api_keys.get_secret_value()

        # Handle file-based keys
        if api_keys_str.startswith("@"):
            path_str = api_keys_str[1:]
            path = Path(path_str).expanduser()
            if not path.exists():
                raise FileNotFoundError(f"API keys file not found: {path}")

            try:
                # Read content and normalize newlines to commas
                content = path.read_text(encoding="utf-8").strip()
                api_keys_str = content.replace("\n", ",")
            except Exception as e:
                raise ValueError(f"Failed to read API keys file: {e}") from e

        for pair in api_keys_str.split(","):
            pair = pair.strip()
            if ":" not in pair:
                continue

            env_var, key = pair.split(":", 1)
            env_var = env_var.strip()
            key = key.strip()

            if not key:
                continue

            keys_by_env.setdefault(env_var, []).append(key)

        # Set first key of each env var (SDKs read from env)
        for env_var, keys in keys_by_env.items():
            if keys:
                os.environ[env_var] = keys[0]
                # Set alias if defined (e.g., GOOGLE_API_KEY -> GEMINI_API_KEY)
                alias = self._ENV_ALIASES.get(env_var)
                if alias and alias not in os.environ:
                    os.environ[alias] = keys[0]

        return keys_by_env

    # --- Per-task model chains ---

    # Explicit provider prefixes so key-availability filtering + litellm
    # routing are unambiguous (cohere/openai bare names would mis-detect).
    _DEFAULT_EMBEDDING_CHAIN = (
        "jina_ai/jina-embeddings-v5-text-small",
        "gemini/gemini-embedding-001",
        "openai/text-embedding-3-large",
        "cohere/embed-multilingual-v3.0",
    )
    _DEFAULT_RERANK_CHAIN = (
        "jina_ai/jina-reranker-v3",
        "cohere/rerank-v3.5",
    )
    _DEFAULT_LLM_CHAIN = (
        "gemini/gemini-3-flash-preview",
        "openai/gpt-5.4-mini-2026-03-17",
    )

    def _key_available(self, env_var: str) -> bool:
        """Whether a provider key is set (env or GOOGLE->GEMINI alias)."""
        if os.getenv(env_var):
            return True
        # GOOGLE_API_KEY satisfies GEMINI_API_KEY (wet's _ENV_ALIASES)
        aliases = getattr(self, "_ENV_ALIASES", {})
        for alias, canonical in aliases.items():
            if canonical == env_var and os.getenv(alias):
                return True
        return False

    def _key_available_in(self, env_var: str, creds: dict[str, str]) -> bool:
        """Whether a provider key is present in an explicit ``creds`` dict.

        Multi-user analogue of :meth:`_key_available`: instead of reading
        ``os.environ`` (which never holds per-sub keys, and whose mutation
        would bleed one user's key into another's concurrent request), it
        consults the request-scoped per-sub credential bucket. The GOOGLE ->
        GEMINI alias is honored the same way.
        """
        if creds.get(env_var):
            return True
        aliases = getattr(self, "_ENV_ALIASES", {})
        for alias, canonical in aliases.items():
            if canonical == env_var and creds.get(alias):
                return True
        return False

    def _chain_for_creds(
        self,
        explicit: str,
        default: tuple[str, ...],
        creds: dict[str, str],
    ) -> list[str]:
        """Resolve a model chain from an explicit ``<TASK>_MODELS`` value or
        the curated default, key-gated against an explicit ``creds`` dict.

        Mirrors :meth:`_chain` for the per-sub (HTTP multi-user) path: an
        explicit chain submitted by the user is used verbatim; otherwise the
        curated default is filtered to models whose provider key is in the
        sub's bucket (none -> empty -> local ONNX). No ``os.environ`` reads,
        so a second sub never inherits the first sub's chain.
        """
        if explicit:
            return [m.strip() for m in explicit.split(",") if m.strip()]
        return [
            m for m in default if self._key_available_in(key_env_for_model(m), creds)
        ]

    def _chain(self, primary: str, legacy: str, default: tuple[str, ...]) -> list[str]:
        if primary:
            return [m.strip() for m in primary.split(",") if m.strip()]
        if legacy:
            logger.warning(
                "Deprecated singular model env honored; migrate to the plural "
                "<TASK>_MODELS chain (removed next release): {!r}",
                legacy,
            )
            return [legacy.strip()]
        # Curated default, but ONLY models whose provider key is configured;
        # none -> empty -> local ONNX (no priority-router, no keyless cloud).
        return [m for m in default if self._key_available(key_env_for_model(m))]

    def embedding_chain(self) -> list[str]:
        return self._chain(
            self.embedding_models, self.embedding_model, self._DEFAULT_EMBEDDING_CHAIN
        )

    def rerank_chain(self) -> list[str]:
        if not self.rerank_enabled:
            return []
        return self._chain(
            self.rerank_models, self.rerank_model, self._DEFAULT_RERANK_CHAIN
        )

    def embedding_primary(self) -> str | None:
        c = self.embedding_chain()
        return c[0] if c else None

    def rerank_primary(self) -> str | None:
        c = self.rerank_chain()
        return c[0] if c else None

    def llm_chain(self) -> list[str]:
        # Key-gated like embedding/rerank: an explicit LLM_MODELS chain is used
        # verbatim; an empty env falls to the curated default filtered to models
        # whose provider key is configured (none -> [] -> LLM feature off, never
        # a keyless cloud model that 401s at call time).
        return self._chain(self.llm_models, "", self._DEFAULT_LLM_CHAIN)

    # --- Per-sub (HTTP multi-user) chain resolution ---
    #
    # The single-user *_chain() methods above key-gate against ``os.environ``.
    # In remote multi-user mode per-sub keys live in the request's PerPluginStore
    # bucket (never in ``os.environ``), so these *_chain_for_creds variants
    # resolve the chain from that explicit dict. An explicit ``<TASK>_MODELS``
    # submitted by the user takes the chain field; otherwise the curated default
    # is filtered to the providers the sub has a key for.

    def embedding_chain_for_creds(self, creds: dict[str, str]) -> list[str]:
        return self._chain_for_creds(
            creds.get("EMBEDDING_MODELS", ""),
            self._DEFAULT_EMBEDDING_CHAIN,
            creds,
        )

    def rerank_chain_for_creds(self, creds: dict[str, str]) -> list[str]:
        if not self.rerank_enabled:
            return []
        return self._chain_for_creds(
            creds.get("RERANK_MODELS", ""),
            self._DEFAULT_RERANK_CHAIN,
            creds,
        )

    def llm_chain_for_creds(self, creds: dict[str, str]) -> list[str]:
        return self._chain_for_creds(
            creds.get("LLM_MODELS", ""),
            self._DEFAULT_LLM_CHAIN,
            creds,
        )

    # --- Embedding resolution ---

    def resolve_embedding_dims(self) -> int:
        """Return explicit EMBEDDING_DIMS or 0 for auto-detect."""
        return self.embedding_dims

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

        One predicate for both resolution paths (startup and per-request), so
        they cannot drift apart again. ``DISABLE_LOCAL_EMBED`` is the operator's
        answer; :func:`local_onnx_installed` is the image's, and the image gets
        a veto -- a leg the build removed is not available however the config
        reads.
        """
        return not self.disable_local_embed and local_onnx_installed()

    def local_rerank_available(self) -> bool:
        """Whether the local ONNX rerank leg is both allowed AND present."""
        return not self.disable_local_rerank and local_onnx_installed()

    def resolve_embedding_backend(self) -> str:
        """Resolve embedding backend: 'cloud', 'local', or 'unavailable'.

        3-way resolution via the shared mcp-core primitive:
        - 'cloud'       -- a non-empty EMBEDDING_MODELS chain (with keys).
        - 'local'       -- empty chain AND the local leg is enabled and present.
        - 'unavailable' -- empty chain AND no usable local leg, i.e.
          DISABLE_LOCAL_EMBED is set OR the slim image has no ``fastretrieval``
          installed. Embedding is then gracefully unavailable -- NOT forced.

        The deprecated EMBEDDING_BACKEND env var is honored for one release.
        """
        if self.embedding_backend:
            logger.warning(
                "Deprecated EMBEDDING_BACKEND honored; inferred from "
                "EMBEDDING_MODELS now."
            )
            return (
                "cloud"
                if self.embedding_backend in ("cloud", "litellm")
                else self.embedding_backend
            )
        return resolve_backend(
            has_cloud_chain=bool(self.embedding_chain()),
            local_enabled=self.local_embed_available(),
        ).value

    # --- Reranking resolution ---

    def resolve_local_rerank_model(self) -> str:
        """Resolve local rerank model: GGUF if GPU + llama-cpp, else ONNX.

        The ONNX default is the YesNo variant (~598 MB at inference vs ~12 GB
        for the full-vocab build); it is mathematically equivalent and, since
        fastretrieval's local runtime produces batch-invariant scores.

        LOCAL_RERANK_MODEL overrides the bundled default (BYO model).
        """
        if self.local_rerank_model:
            return self.local_rerank_model
        return _resolve_local_model(
            "n24q02m/Qwen3-Reranker-0.6B-ONNX-YesNo",
            "n24q02m/Qwen3-Reranker-0.6B-GGUF",
        )

    def resolve_rerank_backend(self) -> str:
        """Resolve reranking backend: 'cloud', 'local', 'unavailable', or '' (disabled).

        '' when rerank_enabled is False. Otherwise 3-way via the shared
        mcp-core primitive (same semantics as resolve_embedding_backend, keyed
        on RERANK_MODELS + DISABLE_LOCAL_RERANK + whether the slim image kept
        ``fastretrieval``); the deprecated RERANK_BACKEND env var is honored for
        one release.
        """
        if not self.rerank_enabled:
            return ""
        if self.rerank_backend:
            logger.warning(
                "Deprecated RERANK_BACKEND honored; inferred from RERANK_MODELS now."
            )
            return (
                "cloud"
                if self.rerank_backend in ("cloud", "litellm")
                else self.rerank_backend
            )
        return resolve_backend(
            has_cloud_chain=bool(self.rerank_chain()),
            local_enabled=self.local_rerank_available(),
        ).value

    # --- Provider mode resolution ---

    def resolve_provider_mode(self) -> str:
        """Detect provider mode: 'sdk' or 'local'.

        Returns 'sdk' if any API keys are configured, 'local' otherwise.
        """
        from wet_mcp.credential_state import (
            credentials_for_current_request,
            get_current_sub,
        )

        if get_current_sub() is not None or os.getenv("PUBLIC_URL"):
            creds = credentials_for_current_request()
            return (
                "sdk"
                if any(
                    value for key, value in creds.items() if key.endswith("_API_KEY")
                )
                else "local"
            )
        if self.api_keys:
            return "sdk"
        # Check for direct env var keys
        if any(
            os.getenv(k)
            for k in (
                "GEMINI_API_KEY",
                "GOOGLE_API_KEY",
                "OPENAI_API_KEY",
                "OPENROUTER_API_KEY",
                "COHERE_API_KEY",
                "XAI_API_KEY",
                "JINA_AI_API_KEY",
            )
        ):
            return "sdk"
        return "local"

    def setup_providers(self) -> str:
        """One-time provider configuration. Call once during lifespan startup.

        Returns mode string: 'sdk' or 'local'.
        """
        mode = self.resolve_provider_mode()

        if mode == "sdk":
            self.setup_api_keys()
            logger.info("SDK direct mode (litellm passthrough via mcp_core.llm)")
        else:
            logger.info("Local mode (no cloud providers)")

        return mode


settings = Settings()
