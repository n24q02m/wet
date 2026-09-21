# syntax=docker/dockerfile:1
# Multi-stage build for wet-mcp
# Python 3.13 + SearXNG + Playwright chromium
# All-in-one: no external Docker or services needed

# ========================
# Stage 1: Builder
# ========================
# Use python:3.13-slim (Debian bookworm) which tracks the latest 3.13 patch
# (currently 3.13.13). The astral-sh/uv Docker image still pins an older
# build with uv 0.9.30 + Python 3.13.11, which does not satisfy
# requires-python = ">=3.13.13" from web-core 1.3.5.
# Copy the uv binary from the standalone uv image (always latest).
FROM python:3.13-slim-bookworm@sha256:c45a22ea000adfd9cda29364bbe7edd23001ce5cc2ad15857cfbf7766943b9ca AS builder
COPY --from=ghcr.io/astral-sh/uv:latest@sha256:10787c682e4184e4f290de1171fd4703dc63de99221f10fe1c99002ce7fa9acc /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install git (required by SearXNG build system for version detection)
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (cached when deps don't change)
# Strip [tool.uv.sources] local path overrides so uv resolves from PyPI
COPY pyproject.toml uv.lock ./
RUN sed -i '/^\[tool\.uv\.sources\]/,/^$/d' pyproject.toml && \
    cp uv.lock /tmp/uv.lock.docker
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy application code and install the project
COPY . /app
RUN sed -i '/^\[tool\.uv\.sources\]/,/^$/d' pyproject.toml && \
    cp /tmp/uv.lock.docker uv.lock
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# crawl4ai pulls `unclecode-litellm` (a hard fork that ships files under the same
# top-level `litellm/` package as real `litellm`). The two distributions collide
# on `litellm/constants.py`; install order decides which wins, and when the fork's
# older constants.py (no REDIS_CIRCUIT_BREAKER_FAILURE_THRESHOLD) lands last the
# real litellm 1.89.x redis_cache.py fails to import -> mcp_core.llm.catalog dies.
# Reinstall real litellm LAST so its files are authoritative, then a build-time
# smoke test fails the build loud rather than ever shipping a broken litellm.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --reinstall-package litellm "litellm==$(uv pip show litellm | awk '/^Version:/ {print $2}')" \
    && uv run python -c "import litellm; from litellm.constants import REDIS_CIRCUIT_BREAKER_FAILURE_THRESHOLD; from mcp_core.llm.catalog import list_models; n=len(list_models(modes=('chat',), configured_only=False, limit=5000)); assert n > 100, f'catalog too small: {n}'; print(f'litellm import OK, catalog chat models={n}')"

# SLIM=1 (CF builds) drops all three LOCAL capability legs (native chromium,
# fastretrieval ONNX embed/rerank, bundled SearXNG) — the CF deploy offloads each to a
# remote/cloud tier via DISABLE_LOCAL_BROWSER/EMBED/SEARCH. Declared HERE (after
# uv sync) so it does not bust the apt + uv-sync layer cache above.
ARG SLIM=0

# Install SearXNG from GitHub (zip archive + no-build-isolation for speed).
# SLIM (CF) builds skip it — the search-local leg is offloaded to external
# SearXNG (SEARXNG_URL) + cloud backends (Tavily/Brave/Exa); DISABLE_LOCAL_SEARCH.
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "$SLIM" != "1" ]; then \
    uv pip install --quiet msgspec setuptools wheel pyyaml \
    && uv pip install --quiet --no-build-isolation \
    https://github.com/searxng/searxng/archive/refs/heads/master.zip \
    && uv run python -c "\
import importlib.util; from pathlib import Path; \
spec = importlib.util.find_spec('searx'); \
vf = Path(spec.submodule_search_locations[0]) / 'version_frozen.py'; \
vf.write_text('VERSION_STRING = \"0.0.0\"\nVERSION_TAG = \"v0.0.0\"\nDOCKER_TAG = \"\"\nGIT_URL = \"https://github.com/searxng/searxng\"\nGIT_BRANCH = \"master\"\n'); \
print(f'Created {vf}')"; \
    else echo "SLIM: skipping local SearXNG (external SEARXNG_URL used)"; fi

# SLIM builds also drop the local fastretrieval ONNX embed/rerank deps (CF uses
# cloud Jina via EMBEDDING_MODELS; DISABLE_LOCAL_EMBED/RERANK). fastretrieval is
# lazy-imported, so the slim image runs fine as long as the cloud chain is set.
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "$SLIM" = "1" ]; then \
    uv pip uninstall fastretrieval onnxruntime || true; \
    echo "SLIM: pruned fastretrieval + onnxruntime"; \
    else echo "full build: keeping local fastretrieval embed/rerank"; fi

# Install Playwright chromium browser (skipped in SLIM CF builds — the browser
# leg is offloaded to remote backends: CF Browser Rendering + OCI browserless,
# selected via BROWSER_BACKENDS + DISABLE_LOCAL_BROWSER. Dropping the ~640MB
# chromium binary slims the CF container image.)
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN mkdir -p /opt/playwright && if [ "$SLIM" != "1" ]; then uv run python -m playwright install chromium; fi

# ========================
# Stage 2: Runtime base (shared by stdio + http targets)
# ========================
# Multi-target Dockerfile per spec
# `~/projects/.superpower/mcp-core/specs/2026-04-30-multi-mode-stdio-http-architecture.md`
# section D6. Build stdio: `docker buildx build --target stdio -t <repo>:stdio .`
# Build http:  `docker buildx build --target http  -t <repo>:http .`
# Build latest (= http): `docker buildx build --target http -t <repo>:latest .`
FROM python:3.13-slim-bookworm@sha256:c45a22ea000adfd9cda29364bbe7edd23001ce5cc2ad15857cfbf7766943b9ca AS runtime

LABEL org.opencontainers.image.source="https://github.com/n24q02m/wet-mcp"
LABEL io.modelcontextprotocol.server.name="io.github.n24q02m/wet-mcp"

WORKDIR /app

# Install Playwright runtime dependencies (system libs for chromium)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Playwright chromium dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libwayland-client0 \
    # D-Bus daemon (required by Chromium headless)
    dbus \
    # Additional Chromium dependencies
    libxshmfence1 \
    libx11-xcb1 \
    # SearXNG dependencies
    libxml2 \
    libxslt1.1 \
    # General
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment and Playwright browsers from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /opt/playwright /opt/playwright

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    CACHE_DIR=/data \
    DOWNLOAD_DIR=/data/downloads \
    DBUS_SESSION_BUS_ADDRESS=disabled:

# Create non-root user and set permissions
RUN groupadd -r appuser && useradd -r -g appuser -d /home/appuser -m appuser \
    && mkdir -p /data/downloads /home/appuser/.wet-mcp \
    && touch /home/appuser/.wet-mcp/.setup-complete \
    && chown -R appuser:appuser /app /data /home/appuser /opt/playwright

VOLUME /data
USER appuser

# ========================
# Stage 3a: stdio target (default for plugin marketplace & uvx-style usage)
# ========================
FROM runtime AS stdio
ENV MCP_TRANSPORT=stdio
ENTRYPOINT ["python", "-m", "wet_mcp"]

# ========================
# Stage 3b: http target (multi-user remote daemon)
# ========================
FROM runtime AS http
ENV MCP_TRANSPORT=http \
    MCP_PORT=8080
EXPOSE 8080
ENTRYPOINT ["python", "-m", "wet_mcp"]
