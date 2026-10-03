# syntax=docker/dockerfile:1
# wet — single-stage runtime image (CF-era HTTP deployment).
# The bare `python -m wet` module IS the blocking HTTP server: it serves
# WET_HOST:WET_PORT (env below; also overridable per-container at runtime).
# The old multi-stage stdio/http matrix and its MCP_TRANSPORT/MCP_PORT wiring
# are gone — stdio is a local uvx concern, not a container one.

# python:3.13-slim (Debian bookworm) tracks the latest 3.13 patch (currently
# 3.13.13). The astral-sh/uv image still pins an older base that does not
# satisfy requires-python = "==3.13.*" for web-core 1.3.5, so the uv binary is
# copied into this image instead of building FROM it.
FROM python:3.13-slim-bookworm@sha256:2325bb286ec344af3e5898cc224b5844e2707ac6e26b1632516fd3edc84a5e26
COPY --from=ghcr.io/astral-sh/uv:latest@sha256:10787c682e4184e4f290de1171fd4703dc63de99221f10fe1c99002ce7fa9acc /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# git: required by the SearXNG build system (version detection) and by uv's
# git-sourced deps below.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Chromium headless + SearXNG system libraries (harmless when the local
# browser/search legs are disabled; required when they are not).
RUN apt-get update && apt-get install -y --no-install-recommends \
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
    dbus \
    libxshmfence1 \
    libx11-xcb1 \
    libxml2 \
    libxslt1.1 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (cached when deps don't change).
# [tool.uv.sources] stays INTACT: hull-core/hull-web resolve from the git revs
# recorded in uv.lock — do NOT strip them for PyPI.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy application code and install the project.
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# SLIM=1 (CF builds) drops all three LOCAL capability legs (native chromium,
# fastretrieval ONNX embed/rerank, bundled SearXNG) — the CF deploy offloads each
# to a remote/cloud tier via DISABLE_LOCAL_BROWSER/EMBED/SEARCH.
ARG SLIM=0

# SearXNG from GitHub (zip + no-build-isolation for speed); SLIM builds skip it
# and use external SEARXNG_URL + cloud search backends.
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

# SLIM builds also drop the local fastretrieval ONNX embed/rerank deps; both are
# lazy-imported, so the slim image runs fine as long as the cloud chain is set.
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "$SLIM" = "1" ]; then \
    uv pip uninstall fastretrieval onnxruntime || true; \
    echo "SLIM: pruned fastretrieval + onnxruntime"; \
    else echo "full build: keeping local fastretrieval embed/rerank"; fi

ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN mkdir -p /opt/playwright && if [ "$SLIM" != "1" ]; then uv run python -m playwright install chromium; fi

# Non-root runtime. The code reads no WET_HOME-style env (config root is
# Path.home()/.wet), so mount-friendliness comes from pinning HOME and
# pre-creating the config dir with the setup marker (skips first-boot auto-setup
# inside the container).
ENV HOME=/home/appuser
RUN groupadd -r appuser && useradd -r -g appuser -d /home/appuser -m appuser \
    && mkdir -p /data/downloads /home/appuser/.wet \
    && touch /home/appuser/.wet/.setup-complete \
    && chown -R appuser:appuser /app /data /home/appuser /opt/playwright

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    CACHE_DIR=/data \
    DOWNLOAD_DIR=/data/downloads \
    WET_HOST=0.0.0.0 \
    WET_PORT=8000 \
    DBUS_SESSION_BUS_ADDRESS=disabled:

VOLUME /data
EXPOSE 8000
USER appuser

ENTRYPOINT ["python", "-m", "wet"]
