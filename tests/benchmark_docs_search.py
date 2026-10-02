"""Benchmark test suite for docs search quality (2000 libraries).

Run manually or via CI to validate docs search quality after changes.
Each test case specifies a library, query, and expected quality signals.

Usage:
    uv run pytest tests/benchmark_docs_search.py -v --timeout=120 -k "test_docs_benchmark"

NOTE: These are live integration tests that hit external APIs.
      Mark with @pytest.mark.benchmark to skip in regular CI.
"""

# fmt: off
# ruff: noqa: E501

BENCHMARK_CASES = [
    # =====================================================================
    # Category A: Popular libraries (10) — stress core pipeline
    # =====================================================================
    {
        "id": "fastapi",
        "library": "fastapi",
        "query": "CORS middleware configuration",
        "tests_aspect": "i18n GitHub raw filtering (de/ja/zh translations)",
        "expect_lang": "en",
        "expect_no_patterns": ["/de/", "/ja/", "/zh/", "/ko/"],
    },
    {
        "id": "react",
        "library": "react",
        "query": "useState useEffect hooks",
        "tests_aspect": "internal docs skip -> Tier 2 crawl (react.dev)",
        "expect_url_contains": "react.dev",
    },
    {
        "id": "django",
        "library": "django",
        "query": "database models and migrations",
        "tests_aspect": "crawl i18n URL filtering + depth-2 crawling",
        "expect_lang": "en",
        "expect_no_patterns": ["/ja/", "/el/", "/fr/", "/es/"],
    },
    {
        "id": "polars",
        "library": "polars",
        "query": "lazy frame filter group_by",
        "tests_aspect": "macro-heavy fallthrough to Tier 2 crawl",
        "expect_no_patterns": ["{{", "code_block("],
    },
    {
        "id": "pydantic",
        "library": "pydantic",
        "query": "field_validator custom validation",
        "tests_aspect": "FTS heading weight balance (content vs heading)",
        "expect_top_relevant": True,
    },
    {
        "id": "nextjs",
        "library": "next",
        "query": "server components data fetching",
        "tests_aspect": "large docs site with many pages",
    },
    {
        "id": "vue",
        "library": "vue",
        "query": "composition API reactive refs",
        "tests_aspect": "i18n (vuejs.org has translations)",
        "expect_lang": "en",
    },
    {
        "id": "sqlalchemy",
        "library": "sqlalchemy",
        "query": "ORM relationships one-to-many",
        "tests_aspect": "version prefix crawl restriction",
    },
    {
        "id": "tailwindcss",
        "library": "tailwindcss",
        "query": "flexbox grid layout utilities",
        "tests_aspect": "nav heading block stripping",
        "expect_no_nav_titles": True,
    },
    {
        "id": "langchain",
        "library": "langchain",
        "query": "retrieval chain vector store",
        "tests_aspect": "quality gate <20 chunks -> Tier 2 fallthrough",
    },
    # =====================================================================
    # Category B: Medium popularity (10) — diverse ecosystems
    # =====================================================================
    {
        "id": "hono",
        "library": "hono",
        "query": "middleware routing context",
        "tests_aspect": "TypeScript web framework (npm, llms.txt)",
    },
    {
        "id": "effect",
        "library": "effect",
        "query": "error handling pipe effect",
        "language": "typescript",
        "tests_aspect": "TypeScript functional (llms.txt)",
    },
    {
        "id": "ruff",
        "library": "ruff",
        "query": "configuration rules select ignore",
        "tests_aspect": "Rust-based Python tool (PyPI, GitHub raw)",
    },
    {
        "id": "duckdb",
        "library": "duckdb",
        "query": "SQL queries parquet files",
        "tests_aspect": "multi-language bindings docs (landing page fix)",
    },
    {
        "id": "meilisearch",
        "library": "meilisearch",
        "query": "search index settings filters",
        "tests_aspect": "SearXNG fallback (SDK vs server docs)",
    },
    {
        "id": "prisma",
        "library": "prisma",
        "query": "schema models client queries relations",
        "tests_aspect": "npm ORM with prisma.io docs",
    },
    {
        "id": "fastify",
        "library": "fastify",
        "query": "plugins hooks decorators routes",
        "tests_aspect": "npm, fastify.dev",
    },
    {
        "id": "angular",
        "library": "@angular/core",
        "query": "components services dependency injection",
        "tests_aspect": "scoped npm, angular.dev",
    },
    {
        "id": "svelte",
        "library": "svelte",
        "query": "reactivity stores components",
        "tests_aspect": "npm, svelte.dev",
    },
    {
        "id": "astro",
        "library": "astro",
        "query": "content collections islands architecture",
        "tests_aspect": "npm, astro.build, llms.txt expected",
    },
    # =====================================================================
    # Category C: Python ecosystem (10) — PyPI discovery
    # =====================================================================
    {
        "id": "flask",
        "library": "flask",
        "query": "blueprints application factory routing",
        "tests_aspect": "PyPI, ReadTheDocs",
    },
    {
        "id": "pytorch",
        "library": "torch",
        "query": "tensor operations autograd backward",
        "tests_aspect": "PyPI vs npm name collision",
    },
    {
        "id": "pytest",
        "library": "pytest",
        "query": "fixtures parametrize marks conftest",
        "tests_aspect": "PyPI, pytest.org docs",
    },
    {
        "id": "numpy",
        "library": "numpy",
        "query": "array operations broadcasting reshape",
        "tests_aspect": "PyPI, numpy.org large docs",
    },
    {
        "id": "pandas",
        "library": "pandas",
        "query": "dataframe groupby merge pivot",
        "tests_aspect": "PyPI, pandas.pydata.org",
    },
    {
        "id": "scikit-learn",
        "library": "scikit-learn",
        "query": "classification random forest fit predict",
        "tests_aspect": "hyphenated PyPI name",
    },
    {
        "id": "requests",
        "library": "requests",
        "query": "session authentication headers timeout",
        "tests_aspect": "PyPI, very popular, ReadTheDocs",
    },
    {
        "id": "celery",
        "library": "celery",
        "query": "task queue workers beat schedule",
        "tests_aspect": "PyPI, celeryproject.org docs",
    },
    {
        "id": "httpx",
        "library": "httpx",
        "query": "async client streaming timeout",
        "tests_aspect": "PyPI, modern async HTTP",
    },
    {
        "id": "typer",
        "library": "typer",
        "query": "CLI commands options arguments callback",
        "tests_aspect": "PyPI, tiangolo ecosystem",
    },
    # =====================================================================
    # Category D: Lesser-known / niche (10) — edge cases
    # =====================================================================
    {
        "id": "instructor",
        "library": "instructor",
        "query": "structured output pydantic model",
        "tests_aspect": "npm deprecated detection (PyPI is correct)",
    },
    {
        "id": "litestar",
        "library": "litestar",
        "query": "route handlers dependency injection",
        "tests_aspect": "Python ASGI framework (less popular)",
    },
    {
        "id": "drizzle-orm",
        "library": "drizzle-orm",
        "query": "schema definition queries select",
        "tests_aspect": "TypeScript ORM (npm, llms.txt)",
    },
    {
        "id": "tanstack-query",
        "library": "@tanstack/react-query",
        "query": "useQuery mutations invalidation",
        "tests_aspect": "framework path filtering (react vs angular)",
    },
    {
        "id": "crawl4ai",
        "library": "crawl4ai",
        "query": "async web crawler extraction config",
        "tests_aspect": "npm wrapper vs PyPI original",
    },
    {
        "id": "zod",
        "library": "zod",
        "query": "schema validation parse safeParse",
        "tests_aspect": "npm small TS validation lib",
    },
    {
        "id": "htmx",
        "library": "htmx.org",
        "query": "hx-get hx-post hx-swap attributes",
        "tests_aspect": "htmx.org (CDN-based, no npm install)",
    },
    {
        "id": "elysia",
        "library": "elysia",
        "query": "routes plugins lifecycle hooks",
        "tests_aspect": "Bun web framework (newer npm)",
    },
    {
        "id": "playwright",
        "library": "playwright",
        "query": "page locator click assertions",
        "tests_aspect": "npm, playwright.dev, cross-language",
    },
    {
        "id": "remix",
        "library": "@remix-run/react",
        "query": "loaders actions routes outlet",
        "tests_aspect": "scoped npm, remix.run docs",
    },
    # =====================================================================
    # Category E: Rust & Go (10) — crates.io / Go discovery
    # =====================================================================
    {
        "id": "tokio",
        "library": "tokio",
        "query": "async runtime spawn tasks select",
        "tests_aspect": "crates.io, tokio.rs docs",
    },
    {
        "id": "axum",
        "library": "axum",
        "query": "router extractors handlers middleware",
        "tests_aspect": "crates.io, small Rust web",
    },
    {
        "id": "serde",
        "library": "serde",
        "query": "serialize deserialize derive attributes",
        "tests_aspect": "crates.io, serde.rs",
    },
    {
        "id": "gin",
        "library": "gin",
        "query": "router middleware groups context JSON",
        "tests_aspect": "Go web framework (npm collision likely)",
    },
    {
        "id": "echo-go",
        "library": "echo",
        "query": "routes middleware context request response",
        "tests_aspect": "Go web framework (npm/pypi collision, star-count disambiguation)",
    },
    {
        "id": "trpc",
        "library": "@trpc/server",
        "query": "router procedures middleware context",
        "tests_aspect": "scoped npm, tRPC monorepo",
    },
    {
        "id": "sveltekit",
        "library": "@sveltejs/kit",
        "query": "load functions form actions hooks",
        "tests_aspect": "scoped npm, kit.svelte.dev",
    },
    {
        "id": "uvicorn",
        "library": "uvicorn",
        "query": "ASGI server configuration workers reload",
        "tests_aspect": "PyPI, ASGI server docs",
    },
    {
        "id": "shadcn-ui",
        "library": "shadcn-ui",
        "query": "button dialog components installation",
        "tests_aspect": "not a real npm package (copy-paste CLI)",
    },
    {
        "id": "playwright-python",
        "library": "playwright",
        "query": "page locator click assertions browser",
        "tests_aspect": "PyPI playwright, cross-lang (same name as npm)",
    },
    # =====================================================================
    # Category F: Frontend frameworks & UI (10) — npm scoped + UI libs
    # =====================================================================
    {
        "id": "solidjs",
        "library": "solid-js",
        "query": "createSignal createEffect reactivity",
        "tests_aspect": "npm, solidjs.com (hyphenated name)",
    },
    {
        "id": "qwik",
        "library": "@builder.io/qwik",
        "query": "component$ useSignal routing",
        "tests_aspect": "deeply scoped npm, qwik.dev",
    },
    {
        "id": "nuxt",
        "library": "nuxt",
        "query": "pages routing composables useFetch",
        "tests_aspect": "npm, nuxt.com (Vue meta-framework)",
    },
    {
        "id": "preact",
        "library": "preact",
        "query": "hooks useState component rendering",
        "tests_aspect": "npm, preactjs.com (lightweight React alternative)",
    },
    {
        "id": "alpinejs",
        "library": "alpinejs",
        "query": "x-data x-on x-bind directives",
        "tests_aspect": "npm, alpinejs.dev (minimal JS framework)",
    },
    {
        "id": "lit",
        "library": "lit",
        "query": "LitElement html css reactive properties",
        "tests_aspect": "npm, lit.dev (Web Components)",
    },
    {
        "id": "mui-material",
        "library": "@mui/material",
        "query": "Button TextField theme customization",
        "tests_aspect": "scoped npm, mui.com (large component lib)",
    },
    {
        "id": "mantine",
        "library": "@mantine/core",
        "query": "Button Input Modal hooks theme",
        "tests_aspect": "scoped npm, mantine.dev",
    },
    {
        "id": "chakra-ui",
        "library": "@chakra-ui/react",
        "query": "Box Flex theme provider responsive",
        "tests_aspect": "scoped npm, chakra-ui.com",
    },
    {
        "id": "threejs",
        "library": "three",
        "query": "scene camera renderer mesh geometry",
        "tests_aspect": "npm, threejs.org (WebGL, name != pkg)",
    },
    # =====================================================================
    # Category G: Backend & API (10) — diverse server frameworks
    # =====================================================================
    {
        "id": "express",
        "library": "express",
        "query": "middleware routing error handling",
        "tests_aspect": "npm, expressjs.com (most popular Node.js)",
    },
    {
        "id": "koa",
        "library": "koa",
        "query": "context middleware cascade error",
        "tests_aspect": "npm, koajs.com (lightweight Node.js)",
    },
    {
        "id": "nestjs",
        "library": "@nestjs/core",
        "query": "controllers providers modules guards",
        "tests_aspect": "scoped npm, docs.nestjs.com",
    },
    {
        "id": "starlette",
        "library": "starlette",
        "query": "routes middleware WebSocket responses",
        "tests_aspect": "PyPI, ASGI framework (fastapi base)",
    },
    {
        "id": "sanic",
        "library": "sanic",
        "query": "handlers blueprints middleware streaming",
        "tests_aspect": "PyPI, sanicframework.org (async Python)",
    },
    {
        "id": "aiohttp",
        "library": "aiohttp",
        "query": "client session server routes WebSocket",
        "tests_aspect": "PyPI, aiohttp.readthedocs.io",
    },
    {
        "id": "drf",
        "library": "djangorestframework",
        "query": "serializers viewsets routers permissions",
        "tests_aspect": "PyPI, django-rest-framework.org (name != import)",
    },
    {
        "id": "graphql-js",
        "library": "graphql",
        "query": "schema types resolvers queries mutations",
        "tests_aspect": "npm graphql, graphql.org (generic name)",
    },
    {
        "id": "socketio",
        "library": "socket.io",
        "query": "emit rooms namespaces events broadcast",
        "tests_aspect": "npm, socket.io (dotted package name)",
    },
    {
        "id": "actix-web",
        "library": "actix-web",
        "query": "handlers extractors middleware state",
        "tests_aspect": "crates.io, actix.rs (Rust web framework)",
    },
    # =====================================================================
    # Category H: Data & ML (10) — Python scientific ecosystem
    # =====================================================================
    {
        "id": "transformers",
        "library": "transformers",
        "query": "pipeline AutoModel tokenizer training",
        "tests_aspect": "PyPI, huggingface.co (large docs)",
    },
    {
        "id": "tensorflow",
        "library": "tensorflow",
        "query": "keras model layers training compile",
        "tests_aspect": "PyPI, tensorflow.org (massive docs)",
    },
    {
        "id": "scipy",
        "library": "scipy",
        "query": "optimize interpolate integrate stats",
        "tests_aspect": "PyPI, scipy.org (scientific computing)",
    },
    {
        "id": "matplotlib",
        "library": "matplotlib",
        "query": "plot figure axes subplot legend",
        "tests_aspect": "PyPI, matplotlib.org (visualization)",
    },
    {
        "id": "seaborn",
        "library": "seaborn",
        "query": "heatmap scatter violin distribution",
        "tests_aspect": "PyPI, seaborn.pydata.org (stats viz)",
    },
    {
        "id": "spacy",
        "library": "spacy",
        "query": "nlp pipeline ner tokenization models",
        "tests_aspect": "PyPI, spacy.io (NLP library)",
    },
    {
        "id": "opencv",
        "library": "opencv-python",
        "query": "image processing video capture contours",
        "tests_aspect": "PyPI, opencv.org (name != import)",
    },
    {
        "id": "pillow",
        "library": "pillow",
        "query": "Image open resize filter save",
        "tests_aspect": "PyPI, pillow.readthedocs.io (PIL fork)",
    },
    {
        "id": "sympy",
        "library": "sympy",
        "query": "symbols solve integrate simplify",
        "tests_aspect": "PyPI, sympy.org (symbolic math)",
    },
    {
        "id": "nltk",
        "library": "nltk",
        "query": "tokenize corpus pos_tag sentiment",
        "tests_aspect": "PyPI, nltk.org (classic NLP toolkit)",
    },
    # =====================================================================
    # Category I: DevTools & Build (10) — JavaScript tooling
    # =====================================================================
    {
        "id": "webpack",
        "library": "webpack",
        "query": "loaders plugins entry output config",
        "tests_aspect": "npm, webpack.js.org (bundler)",
    },
    {
        "id": "esbuild",
        "library": "esbuild",
        "query": "build transform bundle plugins",
        "tests_aspect": "npm, esbuild.github.io (Go-based bundler)",
    },
    {
        "id": "vite",
        "library": "vite",
        "query": "dev server plugins HMR config build",
        "tests_aspect": "npm, vite.dev (modern build tool)",
    },
    {
        "id": "jest",
        "library": "jest",
        "query": "matchers mocks describe expect beforeEach",
        "tests_aspect": "npm, jestjs.io (testing framework)",
    },
    {
        "id": "cypress",
        "library": "cypress",
        "query": "commands visit click intercept assertions",
        "tests_aspect": "npm, docs.cypress.io (E2E testing)",
    },
    {
        "id": "prettier",
        "library": "prettier",
        "query": "options plugins configuration ignore",
        "tests_aspect": "npm, prettier.io (code formatter)",
    },
    {
        "id": "biome",
        "library": "@biomejs/biome",
        "query": "lint format rules configuration",
        "tests_aspect": "scoped npm, biomejs.dev (linter+formatter)",
    },
    {
        "id": "turbo",
        "library": "turbo",
        "query": "pipeline tasks caching remote cache",
        "tests_aspect": "npm, turbo.build (monorepo build)",
    },
    {
        "id": "rollup",
        "library": "rollup",
        "query": "plugins input output format treeshaking",
        "tests_aspect": "npm, rollupjs.org (ES module bundler)",
    },
    {
        "id": "vitest",
        "library": "vitest",
        "query": "describe it expect mock coverage",
        "tests_aspect": "npm, vitest.dev (Vite test runner)",
    },
    # =====================================================================
    # Category J: Rust & Go ecosystem (10) — crates.io / Go edge cases
    # =====================================================================
    {
        "id": "fiber",
        "library": "fiber",
        "query": "router middleware handlers context JSON",
        "tests_aspect": "Go, gofiber.io (generic name like echo)",
    },
    {
        "id": "chi",
        "library": "chi",
        "query": "router middleware mux handlers subrouter",
        "tests_aspect": "Go, go-chi.io (very generic name)",
    },
    {
        "id": "bevy",
        "library": "bevy",
        "query": "ECS components systems queries plugins",
        "tests_aspect": "crates.io, bevyengine.org (game engine)",
    },
    {
        "id": "clap",
        "library": "clap",
        "query": "derive arguments subcommand parser",
        "tests_aspect": "crates.io, clap.rs (CLI arg parser)",
    },
    {
        "id": "reqwest",
        "library": "reqwest",
        "query": "client get post async request",
        "tests_aspect": "crates.io (similar to requests, unique name)",
    },
    {
        "id": "diesel",
        "library": "diesel",
        "query": "query schema migrations insert select",
        "tests_aspect": "crates.io, diesel.rs (Rust ORM)",
    },
    {
        "id": "rocket",
        "library": "rocket",
        "query": "routes handlers guards state fairings",
        "tests_aspect": "crates.io, rocket.rs (Rust web, generic name)",
    },
    {
        "id": "warp",
        "library": "warp",
        "query": "filters routes rejection handlers",
        "language": "rust",
        "tests_aspect": "crates.io (Rust web, very generic name)",
    },
    {
        "id": "iced",
        "library": "iced",
        "query": "Application widget view update message",
        "tests_aspect": "crates.io (Rust GUI, generic name)",
    },
    {
        "id": "tauri-rs",
        "library": "tauri",
        "query": "commands events window IPC plugins",
        "tests_aspect": "npm + crates.io cross-ecosystem, tauri.app",
    },
    # =====================================================================
    # Category K: Cloud & Infrastructure (10) — SDKs, CLIs, cloud tools
    # =====================================================================
    {
        "id": "terraform-cdk",
        "library": "cdktf",
        "query": "providers stacks constructs synth deploy",
        "tests_aspect": "npm, Terraform CDK for TypeScript",
    },
    {
        "id": "pulumi",
        "library": "pulumi",
        "query": "stack resource output config provider",
        "tests_aspect": "npm/pypi, pulumi.com (IaC tool)",
    },
    {
        "id": "boto3",
        "library": "boto3",
        "query": "s3 client resource session ec2",
        "tests_aspect": "PyPI, AWS SDK for Python",
    },
    {
        "id": "supabase-js",
        "library": "supabase",
        "query": "auth database storage realtime edge functions",
        "tests_aspect": "npm, supabase.com (BaaS)",
    },
    {
        "id": "firebase-admin",
        "library": "firebase-admin",
        "query": "auth firestore messaging cloud functions",
        "tests_aspect": "npm/pypi, Firebase Admin SDK",
    },
    {
        "id": "redis-py",
        "library": "redis",
        "query": "connection pool pipeline pub sub cluster",
        "language": "python",
        "tests_aspect": "PyPI, redis.io (generic name collision npm vs pypi)",
    },
    {
        "id": "celery-beat",
        "library": "django-celery-beat",
        "query": "periodic tasks schedule crontab interval",
        "tests_aspect": "PyPI, django-celery-beat (long name, unique)",
    },
    {
        "id": "docker-py",
        "library": "docker",
        "query": "containers images volumes networks build",
        "tests_aspect": "PyPI docker SDK (generic name)",
    },
    {
        "id": "kubernetes-client",
        "library": "kubernetes",
        "query": "pods deployments services config client",
        "tests_aspect": "PyPI, kubernetes.io (generic name)",
    },
    {
        "id": "httpie",
        "library": "httpie",
        "query": "request headers auth plugins sessions",
        "tests_aspect": "PyPI, httpie.io (CLI HTTP client)",
    },
    # =====================================================================
    # Category L: Emerging & Niche (10) — newer/niche libraries
    # =====================================================================
    {
        "id": "pnpm",
        "library": "pnpm",
        "query": "workspace install link peer dependencies",
        "tests_aspect": "npm, pnpm.io (package manager, unique name)",
    },
    {
        "id": "deno",
        "library": "deno",
        "query": "permissions runtime deploy fresh",
        "tests_aspect": "npm, deno.land (JS runtime)",
    },
    {
        "id": "lodash",
        "library": "lodash",
        "query": "debounce throttle merge cloneDeep",
        "tests_aspect": "npm, lodash.com (JS utility, well-known)",
    },
    {
        "id": "motion",
        "library": "motion",
        "query": "animate transition gesture spring keyframes",
        "tests_aspect": "npm, motion.dev (animation library, ex-framer-motion)",
    },
    {
        "id": "cheerio",
        "library": "cheerio",
        "query": "selector parse html load find",
        "tests_aspect": "npm, cheerio.js.org (HTML parser)",
    },
    {
        "id": "sqlx",
        "library": "sqlx",
        "query": "query pool connection migrate transaction",
        "tests_aspect": "crates.io, github.com/launchbadge/sqlx (Rust async SQL)",
    },
    {
        "id": "salvo",
        "library": "salvo",
        "query": "router handler depot request response",
        "tests_aspect": "crates.io, salvo.rs (Rust web framework)",
    },
    {
        "id": "sea-orm",
        "library": "sea-orm",
        "query": "entity model migration query builder",
        "tests_aspect": "crates.io, sea-ql.org (Rust ORM, unique name)",
    },
    {
        "id": "dayjs",
        "library": "dayjs",
        "query": "format parse timezone locale plugin",
        "tests_aspect": "npm, day.js.org (date library, unique name)",
    },
    {
        "id": "ultralytics",
        "library": "ultralytics",
        "query": "yolo detect train predict export model",
        "tests_aspect": "PyPI, ultralytics.com (YOLO object detection)",
    },
    # =====================================================================
    # Category M: Auth & Security (10) — authentication/authorization libs
    # =====================================================================
    {
        "id": "passportjs",
        "library": "passport",
        "query": "strategy authenticate session serialize",
        "tests_aspect": "npm, passportjs.org (Node.js auth middleware)",
    },
    {
        "id": "nextauth",
        "library": "next-auth",
        "query": "providers session callbacks credentials JWT",
        "tests_aspect": "npm, authjs.dev (Next.js auth, renamed)",
    },
    {
        "id": "jose",
        "library": "jose",
        "query": "JWT sign verify encrypt JWK JWS",
        "tests_aspect": "npm, JOSE/JWT library (short generic name)",
    },
    {
        "id": "bcrypt",
        "library": "bcrypt",
        "query": "hash compare salt rounds password",
        "tests_aspect": "npm, bcrypt (password hashing, generic name)",
    },
    {
        "id": "authlib",
        "library": "authlib",
        "query": "OAuth2 client OIDC JWT bearer token",
        "tests_aspect": "PyPI, authlib.org (Python OAuth library)",
    },
    {
        "id": "python-jose",
        "library": "python-jose",
        "query": "JWT encode decode claims algorithms",
        "tests_aspect": "PyPI, python-jose (Python JWT, hyphenated name)",
    },
    {
        "id": "helmet",
        "library": "helmet",
        "query": "CSP headers security HSTS frameguard",
        "tests_aspect": "npm, helmetjs.github.io (HTTP security headers)",
    },
    {
        "id": "cors",
        "library": "cors",
        "query": "origin methods headers credentials preflight",
        "tests_aspect": "npm, expressjs/cors (very short generic name)",
    },
    {
        "id": "cryptography",
        "library": "cryptography",
        "query": "Fernet symmetric asymmetric certificates X509",
        "tests_aspect": "PyPI, cryptography.io (Python crypto library)",
    },
    {
        "id": "argon2",
        "library": "argon2-cffi",
        "query": "hash verify password PasswordHasher",
        "tests_aspect": "PyPI, argon2-cffi (Argon2 bindings, hyphenated)",
    },
    # =====================================================================
    # Category N: Database & ORM (10) — database drivers and ORMs
    # =====================================================================
    {
        "id": "typeorm",
        "library": "typeorm",
        "query": "entity repository migration query builder",
        "tests_aspect": "npm, typeorm.io (TypeScript ORM)",
    },
    {
        "id": "sequelize",
        "library": "sequelize",
        "query": "model define associations migration findAll",
        "tests_aspect": "npm, sequelize.org (Node.js ORM)",
    },
    {
        "id": "mongoose",
        "library": "mongoose",
        "query": "schema model query populate middleware",
        "tests_aspect": "npm, mongoosejs.com (MongoDB ODM)",
    },
    {
        "id": "sqlmodel",
        "library": "sqlmodel",
        "query": "table model select session relationship",
        "tests_aspect": "PyPI, sqlmodel.tiangolo.com (Pydantic + SQLAlchemy)",
    },
    {
        "id": "peewee",
        "library": "peewee",
        "query": "model fields query select create",
        "tests_aspect": "PyPI, docs.peewee-orm.com (lightweight Python ORM)",
    },
    {
        "id": "knex",
        "library": "knex",
        "query": "query builder migration schema join where",
        "tests_aspect": "npm, knexjs.org (SQL query builder)",
    },
    {
        "id": "kysely",
        "library": "kysely",
        "query": "query builder type-safe select insert migration",
        "tests_aspect": "npm, kysely.dev (type-safe TS SQL builder)",
    },
    {
        "id": "alembic",
        "library": "alembic",
        "query": "migration revision upgrade downgrade autogenerate",
        "tests_aspect": "PyPI, alembic.sqlalchemy.org (SQLAlchemy migrations)",
    },
    {
        "id": "motor",
        "library": "motor",
        "query": "async MongoDB client collection find insert",
        "tests_aspect": "PyPI, motor.readthedocs.io (async MongoDB driver)",
    },
    {
        "id": "ioredis",
        "library": "ioredis",
        "query": "client cluster pipeline subscribe pub",
        "tests_aspect": "npm, ioredis (Redis client for Node.js)",
    },
    # =====================================================================
    # Category O: CLI & Terminal (10) — command line tools & TUI libs
    # =====================================================================
    {
        "id": "click",
        "library": "click",
        "query": "command group option argument callback",
        "tests_aspect": "PyPI, click.palletsprojects.com (Python CLI, very popular)",
    },
    {
        "id": "rich",
        "library": "rich",
        "query": "console table progress panel syntax",
        "tests_aspect": "PyPI, rich.readthedocs.io (terminal formatting)",
    },
    {
        "id": "inquirer",
        "library": "@inquirer/prompts",
        "query": "input select confirm checkbox password",
        "tests_aspect": "scoped npm, inquirer (interactive CLI prompts)",
    },
    {
        "id": "commander",
        "library": "commander",
        "query": "program command option argument action",
        "tests_aspect": "npm, commander.js (Node.js CLI framework)",
    },
    {
        "id": "yargs",
        "library": "yargs",
        "query": "command options positional middleware help",
        "tests_aspect": "npm, yargs.js.org (CLI parser)",
    },
    {
        "id": "textual",
        "library": "textual",
        "query": "App Widget Screen compose mount",
        "tests_aspect": "PyPI, textual.textualize.io (Python TUI framework)",
    },
    {
        "id": "tqdm",
        "library": "tqdm",
        "query": "progress bar iterator wrap notebook",
        "tests_aspect": "PyPI, tqdm.github.io (progress bar, short name)",
    },
    {
        "id": "chalk",
        "library": "chalk",
        "query": "color red green bold underline hex",
        "tests_aspect": "npm, chalk (terminal colors, generic name)",
    },
    {
        "id": "argparse",
        "library": "argparse",
        "query": "parser argument add subparser",
        "tests_aspect": "PyPI/stdlib, very generic name",
    },
    {
        "id": "blessed",
        "library": "blessed",
        "query": "screen box terminal cursor input",
        "tests_aspect": "npm, blessed (terminal UI, generic name)",
    },
    # =====================================================================
    # Category P: Testing & QA (10) — test frameworks and tools
    # =====================================================================
    {
        "id": "mocha",
        "library": "mocha",
        "query": "describe it before after hooks reporter",
        "tests_aspect": "npm, mochajs.org (Node.js test framework)",
    },
    {
        "id": "chai",
        "library": "chai",
        "query": "expect should assert deep equal include",
        "tests_aspect": "npm, chaijs.com (assertion library, short name)",
    },
    {
        "id": "supertest",
        "library": "supertest",
        "query": "request app get post expect status",
        "tests_aspect": "npm, supertest (HTTP assertions)",
    },
    {
        "id": "nock",
        "library": "nock",
        "query": "intercept mock HTTP scope reply",
        "tests_aspect": "npm, nock (HTTP mocking, short name)",
    },
    {
        "id": "faker",
        "library": "@faker-js/faker",
        "query": "name email address phone random seed",
        "tests_aspect": "scoped npm, fakerjs.dev (data generation)",
    },
    {
        "id": "hypothesis",
        "library": "hypothesis",
        "query": "given strategies example settings assume",
        "tests_aspect": "PyPI, hypothesis.readthedocs.io (property-based testing)",
    },
    {
        "id": "factory-boy",
        "library": "factory-boy",
        "query": "Factory SubFactory Sequence LazyAttribute",
        "tests_aspect": "PyPI, factory-boy (test fixtures, hyphenated)",
    },
    {
        "id": "responses",
        "library": "responses",
        "query": "mock activate add callback passthrough",
        "tests_aspect": "PyPI, responses (HTTP mocking for requests)",
    },
    {
        "id": "coverage",
        "library": "coverage",
        "query": "run report html combine source branch",
        "tests_aspect": "PyPI, coverage.readthedocs.io (code coverage)",
    },
    {
        "id": "storybook",
        "library": "storybook",
        "query": "stories args decorators addon controls",
        "tests_aspect": "npm, storybook.js.org (UI component testing)",
    },
    # =====================================================================
    # Category Q: State Management & Data Flow (10) — state, stores, events
    # =====================================================================
    {
        "id": "zustand",
        "library": "zustand",
        "query": "create store set get subscribe middleware",
        "tests_aspect": "npm, zustand (React state, unique name)",
    },
    {
        "id": "redux-toolkit",
        "library": "@reduxjs/toolkit",
        "query": "createSlice configureStore createAsyncThunk",
        "tests_aspect": "scoped npm, redux-toolkit.js.org",
    },
    {
        "id": "jotai",
        "library": "jotai",
        "query": "atom useAtom Provider atomWithStorage",
        "tests_aspect": "npm, jotai.org (atomic state, unique name)",
    },
    {
        "id": "pinia",
        "library": "pinia",
        "query": "defineStore state getters actions plugins",
        "tests_aspect": "npm, pinia.vuejs.org (Vue state management)",
    },
    {
        "id": "mobx",
        "library": "mobx",
        "query": "observable action computed reaction autorun",
        "tests_aspect": "npm, mobx.js.org (reactive state)",
    },
    {
        "id": "rxjs",
        "library": "rxjs",
        "query": "Observable pipe map filter switchMap Subject",
        "tests_aspect": "npm, rxjs.dev (reactive extensions)",
    },
    {
        "id": "recoil",
        "library": "recoil",
        "query": "atom selector useRecoilState RecoilRoot",
        "tests_aspect": "npm, recoiljs.org (React state by Meta)",
    },
    {
        "id": "valtio",
        "library": "valtio",
        "query": "proxy useSnapshot subscribe ref",
        "tests_aspect": "npm, valtio (proxy-based state, unique name)",
    },
    {
        "id": "ngrx-store",
        "library": "@ngrx/store",
        "query": "reducer action selector effects createFeature",
        "tests_aspect": "scoped npm, ngrx.io (Angular state management)",
    },
    {
        "id": "xstate",
        "library": "xstate",
        "query": "machine state transition context actions guards",
        "tests_aspect": "npm, xstate.js.org (state machines)",
    },
    # =====================================================================
    # Category R: Networking & HTTP (10) — HTTP clients, WebSocket, gRPC
    # =====================================================================
    {
        "id": "axios",
        "library": "axios",
        "query": "get post interceptors config instance",
        "tests_aspect": "npm, axios-http.com (HTTP client)",
    },
    {
        "id": "got",
        "library": "got",
        "query": "request retry hooks pagination stream",
        "tests_aspect": "npm, got (HTTP client, very short name)",
    },
    {
        "id": "undici",
        "library": "undici",
        "query": "fetch request client pool dispatcher",
        "tests_aspect": "npm, undici (Node.js HTTP/1.1 client)",
    },
    {
        "id": "ws",
        "library": "ws",
        "query": "WebSocket server client send message",
        "tests_aspect": "npm, ws (WebSocket, ultra-short 2-char name)",
    },
    {
        "id": "grpcio",
        "library": "grpcio",
        "query": "server channel stub service interceptor",
        "tests_aspect": "PyPI, grpc.io (gRPC Python bindings)",
    },
    {
        "id": "urllib3",
        "library": "urllib3",
        "query": "pool manager request retry timeout",
        "tests_aspect": "PyPI, urllib3.readthedocs.io (HTTP library)",
    },
    {
        "id": "node-fetch",
        "library": "node-fetch",
        "query": "fetch response headers body stream",
        "tests_aspect": "npm, node-fetch (polyfill, hyphenated name)",
    },
    {
        "id": "twisted",
        "library": "twisted",
        "query": "reactor protocol factory deferred endpoint",
        "tests_aspect": "PyPI, twisted.org (async networking)",
    },
    {
        "id": "httptools",
        "library": "httptools",
        "query": "parser HttpRequestParser protocol",
        "tests_aspect": "PyPI, httptools (HTTP parser, generic name)",
    },
    {
        "id": "ky",
        "library": "ky",
        "query": "get post hooks retry timeout prefixUrl",
        "tests_aspect": "npm, ky (HTTP client, ultra-short 2-char name)",
    },
    # =====================================================================
    # Category S: Validation & Serialization (10) — schemas, parsing, codegen
    # =====================================================================
    {
        "id": "joi",
        "library": "joi",
        "query": "schema object string number validate alternatives",
        "tests_aspect": "npm, joi.dev (validation, very short name)",
    },
    {
        "id": "yup",
        "library": "yup",
        "query": "schema object string required validate cast",
        "tests_aspect": "npm, yup (validation, very short name)",
    },
    {
        "id": "ajv",
        "library": "ajv",
        "query": "schema validate compile error format",
        "tests_aspect": "npm, ajv.js.org (JSON Schema validator, short name)",
    },
    {
        "id": "marshmallow",
        "library": "marshmallow",
        "query": "Schema fields dump load validate nested",
        "tests_aspect": "PyPI, marshmallow.readthedocs.io (serialization)",
    },
    {
        "id": "msgpack",
        "library": "msgpack",
        "query": "pack unpack Packer Unpacker raw",
        "tests_aspect": "PyPI/npm, msgpack.org (binary serialization)",
    },
    {
        "id": "protobuf",
        "library": "protobuf",
        "query": "message field service enum compile",
        "tests_aspect": "PyPI/npm, protobuf.dev (Protocol Buffers)",
    },
    {
        "id": "valibot",
        "library": "valibot",
        "query": "schema object string parse safeParse pipe",
        "tests_aspect": "npm, valibot.dev (TS schema validation, unique name)",
    },
    {
        "id": "typebox",
        "library": "@sinclair/typebox",
        "query": "Type Object String Number Static Value",
        "tests_aspect": "scoped npm, typebox (JSON Schema type builder)",
    },
    {
        "id": "cattrs",
        "library": "cattrs",
        "query": "structure unstructure converter hook",
        "tests_aspect": "PyPI, cattrs.readthedocs.io (attrs serialization)",
    },
    {
        "id": "orjson",
        "library": "orjson",
        "query": "dumps loads OPT_INDENT OPT_SORT_KEYS",
        "tests_aspect": "PyPI, orjson (fast JSON, unique name)",
    },
    # =====================================================================
    # Category T: Logging, Config & Utilities (10) — cross-cutting concerns
    # =====================================================================
    {
        "id": "winston",
        "library": "winston",
        "query": "logger transport format level createLogger",
        "language": "javascript",
        "tests_aspect": "npm, winston (Node.js logging, unique name)",
    },
    {
        "id": "pino",
        "library": "pino",
        "query": "logger child transport destination level",
        "tests_aspect": "npm, getpino.io (fast Node.js logging)",
    },
    {
        "id": "loguru",
        "library": "loguru",
        "query": "logger add sink format level filter",
        "tests_aspect": "PyPI, loguru.readthedocs.io (Python logging)",
    },
    {
        "id": "dotenv",
        "library": "dotenv",
        "query": "config parse load env process.env",
        "tests_aspect": "npm, dotenv (env vars, generic name collision)",
    },
    {
        "id": "pydantic-settings",
        "library": "pydantic-settings",
        "query": "BaseSettings env_prefix env_file dotenv",
        "tests_aspect": "PyPI, pydantic-settings (settings management)",
    },
    {
        "id": "python-dotenv",
        "library": "python-dotenv",
        "query": "load_dotenv find_dotenv set_key dotenv_values",
        "tests_aspect": "PyPI, python-dotenv (env file loading)",
    },
    {
        "id": "date-fns",
        "library": "date-fns",
        "query": "format parse add differenceIn isValid",
        "tests_aspect": "npm, date-fns.org (date utility, hyphenated)",
    },
    {
        "id": "nanoid",
        "library": "nanoid",
        "query": "nanoid customAlphabet urlAlphabet random",
        "tests_aspect": "npm, nanoid (ID generator, unique name)",
    },
    {
        "id": "structlog",
        "library": "structlog",
        "query": "get_logger configure processors bind event",
        "tests_aspect": "PyPI, structlog.readthedocs.io (structured logging)",
    },
    {
        "id": "uuid",
        "library": "uuid",
        "query": "v4 v5 v7 parse validate NIL",
        "language": "javascript",
        "tests_aspect": "npm, uuid (UUID generator, ultra-generic name)",
    },
    # =====================================================================
    # Category U: Graphics & Media (10) — canvas, image processing, charting
    # =====================================================================
    {
        "id": "pixijs",
        "library": "pixi.js",
        "query": "Application Sprite Container Texture renderer",
        "tests_aspect": "npm, pixijs.com (2D WebGL engine, dotted name)",
    },
    {
        "id": "phaser",
        "library": "phaser",
        "query": "Scene Sprite Physics Arcade Tilemap",
        "language": "javascript",
        "tests_aspect": "npm, phaser.io (HTML5 game framework)",
    },
    {
        "id": "konva",
        "library": "konva",
        "query": "Stage Layer Shape Rect Circle drag",
        "language": "javascript",
        "tests_aspect": "npm, konvajs.org (canvas 2D library)",
    },
    {
        "id": "fabricjs",
        "library": "fabric",
        "query": "Canvas Object Rect Circle path event",
        "tests_aspect": "npm, fabricjs.com (canvas library, generic name)",
    },
    {
        "id": "sharp",
        "library": "sharp",
        "query": "resize rotate crop composite format metadata",
        "tests_aspect": "npm, sharp.pixelplumbing.com (image processing)",
    },
    {
        "id": "jimp",
        "library": "jimp",
        "query": "read resize crop blur composite write",
        "tests_aspect": "npm, jimp (JS image manipulation, unique name)",
    },
    {
        "id": "p5js",
        "library": "p5",
        "query": "setup draw createCanvas ellipse rect fill",
        "tests_aspect": "npm, p5js.org (creative coding, short name)",
    },
    {
        "id": "d3",
        "library": "d3",
        "query": "select scale axis transition svg path",
        "tests_aspect": "npm, d3js.org (data viz, ultra-short 2-char name)",
    },
    {
        "id": "chartjs",
        "library": "chart.js",
        "query": "Chart config data options plugins scales",
        "tests_aspect": "npm, chartjs.org (charting library, dotted name)",
    },
    {
        "id": "plotly",
        "library": "plotly",
        "query": "scatter bar heatmap layout figure subplot",
        "tests_aspect": "PyPI, plotly.com (interactive plots, multi-lang)",
    },
    # =====================================================================
    # Category V: Documentation & Static Site Generators (10)
    # =====================================================================
    {
        "id": "docusaurus",
        "library": "@docusaurus/core",
        "query": "docs blog sidebar plugin theme config",
        "tests_aspect": "scoped npm, docusaurus.io (Meta docs framework)",
    },
    {
        "id": "mkdocs",
        "library": "mkdocs",
        "query": "nav theme plugins markdown extensions",
        "tests_aspect": "PyPI, mkdocs.org (Python docs generator)",
    },
    {
        "id": "sphinx",
        "library": "sphinx",
        "query": "toctree directive extension conf.py autodoc",
        "tests_aspect": "PyPI, sphinx-doc.org (Python docs, objects.inv)",
    },
    {
        "id": "vuepress",
        "library": "vuepress",
        "query": "theme plugins config markdown frontmatter",
        "tests_aspect": "npm, vuepress.vuejs.org (Vue docs generator)",
    },
    {
        "id": "nextra",
        "library": "nextra",
        "query": "pages _meta.json callout steps tabs",
        "tests_aspect": "npm, nextra.site (Next.js docs framework)",
    },
    {
        "id": "typedoc",
        "library": "typedoc",
        "query": "entry points plugin theme options reflection",
        "tests_aspect": "npm, typedoc.org (TypeScript documentation)",
    },
    {
        "id": "starlight",
        "library": "@astrojs/starlight",
        "query": "sidebar navigation i18n components config",
        "tests_aspect": "scoped npm, starlight.astro.build (Astro docs)",
    },
    {
        "id": "redoc",
        "library": "redoc",
        "query": "OpenAPI schema theme config scrollYOffset",
        "tests_aspect": "npm, redocly.com (API docs from OpenAPI)",
    },
    {
        "id": "mintlify",
        "library": "mintlify",
        "query": "navigation api components mint.json groups",
        "tests_aspect": "npm, mintlify.com (docs platform, SaaS)",
    },
    {
        "id": "fumadocs",
        "library": "fumadocs-core",
        "query": "source loader MDX search config page",
        "tests_aspect": "npm, fumadocs.vercel.app (Next.js docs framework)",
    },
    # =====================================================================
    # Category W: Monorepo & Build Tools (10) — workspace management
    # =====================================================================
    {
        "id": "nx",
        "library": "nx",
        "query": "workspace generators executors project.json cache",
        "tests_aspect": "npm, nx.dev (monorepo build system)",
    },
    {
        "id": "lerna",
        "library": "lerna",
        "query": "publish version bootstrap link workspace",
        "tests_aspect": "npm, lerna.js.org (monorepo manager, Nrwl)",
    },
    {
        "id": "changesets",
        "library": "@changesets/cli",
        "query": "changeset version publish status init",
        "tests_aspect": "scoped npm, changesets (versioning tool)",
    },
    {
        "id": "tsup",
        "library": "tsup",
        "query": "entry format dts splitting config",
        "tests_aspect": "npm, tsup.egoist.dev (TypeScript bundler)",
    },
    {
        "id": "unbuild",
        "library": "unbuild",
        "query": "build.config entries rollup mkdist stub",
        "tests_aspect": "npm, unbuild (unified build system)",
    },
    {
        "id": "concurrently",
        "library": "concurrently",
        "query": "run parallel prefix kill-others names",
        "tests_aspect": "npm, concurrently (run parallel commands)",
    },
    {
        "id": "cross-env",
        "library": "cross-env",
        "query": "NODE_ENV set environment variable script",
        "tests_aspect": "npm, cross-env (cross-platform env vars)",
    },
    {
        "id": "syncpack",
        "library": "syncpack",
        "query": "list-mismatches fix-mismatches format semver",
        "tests_aspect": "npm, syncpack (monorepo dependency sync)",
    },
    {
        "id": "patch-package",
        "library": "patch-package",
        "query": "patch postinstall diff apply exclude",
        "tests_aspect": "npm, patch-package (patch node_modules)",
    },
    {
        "id": "pkgroll",
        "library": "pkgroll",
        "query": "exports types bin conditions build",
        "tests_aspect": "npm, pkgroll (package bundler)",
    },
    # =====================================================================
    # Category X: DevOps & Automation (10) — infra tools & task automation
    # =====================================================================
    {
        "id": "ansible",
        "library": "ansible",
        "query": "playbook inventory module task role",
        "tests_aspect": "PyPI, docs.ansible.com (IaC tool, massive docs)",
    },
    {
        "id": "paramiko",
        "library": "paramiko",
        "query": "SSHClient connect SFTPClient channel transport",
        "tests_aspect": "PyPI, paramiko.org (SSH library)",
    },
    {
        "id": "watchdog",
        "library": "watchdog",
        "query": "Observer FileSystemEventHandler events patterns",
        "tests_aspect": "PyPI, watchdog (filesystem monitoring)",
    },
    {
        "id": "schedule",
        "library": "schedule",
        "query": "every day hour minute job do run_pending",
        "tests_aspect": "PyPI, schedule (job scheduler, generic name)",
    },
    {
        "id": "apscheduler",
        "library": "apscheduler",
        "query": "scheduler trigger cron interval job store",
        "tests_aspect": "PyPI, apscheduler (advanced scheduler)",
    },
    {
        "id": "invoke",
        "library": "invoke",
        "query": "task context run collection namespace",
        "tests_aspect": "PyPI, pyinvoke.org (task runner, generic name)",
    },
    {
        "id": "fabric-py",
        "library": "fabric",
        "query": "Connection run sudo put group task",
        "tests_aspect": "PyPI, fabfile.org (SSH deployment, generic name collision)",
    },
    {
        "id": "psutil",
        "library": "psutil",
        "query": "cpu_percent virtual_memory disk_usage process",
        "tests_aspect": "PyPI, psutil (system monitoring, unique name)",
    },
    {
        "id": "sh",
        "library": "sh",
        "query": "Command bake piping redirection background",
        "tests_aspect": "PyPI, sh (subprocess wrapper, ultra-short 2-char name)",
    },
    {
        "id": "plumbum",
        "library": "plumbum",
        "query": "local path command pipeline ProcessExecutionError",
        "tests_aspect": "PyPI, plumbum (shell combinators, unique name)",
    },
    # =====================================================================
    # Category Y: Message Queues & Real-time (10) — async messaging
    # =====================================================================
    {
        "id": "bullmq",
        "library": "bullmq",
        "query": "Queue Worker FlowProducer Job connection",
        "tests_aspect": "npm, bullmq (Redis-based queue)",
    },
    {
        "id": "amqplib",
        "library": "amqplib",
        "query": "connect channel assertQueue sendToQueue consume",
        "tests_aspect": "npm, amqplib (AMQP 0-9-1 client)",
    },
    {
        "id": "kafka-python",
        "library": "kafka-python",
        "query": "KafkaProducer KafkaConsumer topic partition commit",
        "tests_aspect": "PyPI, kafka-python (Kafka client, hyphenated)",
    },
    {
        "id": "pika",
        "library": "pika",
        "query": "BlockingConnection channel basic_publish basic_consume",
        "tests_aspect": "PyPI, pika (RabbitMQ client, short name)",
    },
    {
        "id": "kombu",
        "library": "kombu",
        "query": "Connection Exchange Queue Consumer Producer",
        "tests_aspect": "PyPI, kombu (messaging library, Celery dep)",
    },
    {
        "id": "dramatiq",
        "library": "dramatiq",
        "query": "actor broker middleware message result",
        "tests_aspect": "PyPI, dramatiq.io (task processing, unique name)",
    },
    {
        "id": "rq",
        "library": "rq",
        "query": "Queue Worker job enqueue result timeout",
        "tests_aspect": "PyPI, python-rq.org (Redis queue, ultra-short name)",
    },
    {
        "id": "huey",
        "library": "huey",
        "query": "task periodic crontab RedisHuey storage",
        "tests_aspect": "PyPI, huey (lightweight task queue, unique name)",
    },
    {
        "id": "nats-py",
        "library": "nats-py",
        "query": "connect publish subscribe JetStream KeyValue",
        "tests_aspect": "PyPI, nats-py (NATS client, hyphenated)",
    },
    {
        "id": "aio-pika",
        "library": "aio-pika",
        "query": "connect_robust Queue Exchange Message channel",
        "tests_aspect": "PyPI, aio-pika (async RabbitMQ, hyphenated)",
    },
    # =====================================================================
    # Category Z: TypeScript Advanced (10) — TS utilities & patterns
    # =====================================================================
    {
        "id": "ts-pattern",
        "library": "ts-pattern",
        "query": "match with when exhaustive select P",
        "tests_aspect": "npm, ts-pattern (pattern matching, hyphenated)",
    },
    {
        "id": "type-fest",
        "library": "type-fest",
        "query": "PartialDeep RequiredDeep SetRequired Simplify",
        "tests_aspect": "npm, type-fest (TS type helpers, hyphenated)",
    },
    {
        "id": "zx",
        "library": "zx",
        "query": "$ cd fetch echo question within",
        "tests_aspect": "npm, zx (Google shell scripts, ultra-short name)",
    },
    {
        "id": "oclif",
        "library": "oclif",
        "query": "Command Flags Args Plugin Hook run",
        "tests_aspect": "npm, oclif.io (CLI framework by Salesforce)",
    },
    {
        "id": "tsyringe",
        "library": "tsyringe",
        "query": "container injectable inject singleton scoped",
        "tests_aspect": "npm, tsyringe (DI container, unique name)",
    },
    {
        "id": "inversify",
        "library": "inversify",
        "query": "Container bind injectable inject kernel",
        "tests_aspect": "npm, inversify.io (IoC container)",
    },
    {
        "id": "ts-morph",
        "library": "ts-morph",
        "query": "Project SourceFile Node Type ClassDeclaration",
        "tests_aspect": "npm, ts-morph (TypeScript AST manipulation)",
    },
    {
        "id": "type-graphql",
        "library": "type-graphql",
        "query": "Resolver Query Mutation Field ObjectType",
        "tests_aspect": "npm, typegraphql.com (GraphQL with TS decorators)",
    },
    {
        "id": "neverthrow",
        "library": "neverthrow",
        "query": "ok err Result ResultAsync fromPromise",
        "tests_aspect": "npm, neverthrow (Result type for TS)",
    },
    {
        "id": "arktype",
        "library": "arktype",
        "query": "type scope morph narrow infer union",
        "tests_aspect": "npm, arktype.io (runtime TS validation)",
    },
    # =====================================================================
    # Category AA: Python Data & Workflow (10) — data processing, caching
    # =====================================================================
    {
        "id": "tenacity",
        "library": "tenacity",
        "query": "retry stop wait before after retry_if",
        "tests_aspect": "PyPI, tenacity (retry library, unique name)",
    },
    {
        "id": "diskcache",
        "library": "diskcache",
        "query": "Cache FanoutCache DiskCache memoize Deque",
        "tests_aspect": "PyPI, grantjenks.com/docs/diskcache (disk-based cache)",
    },
    {
        "id": "cachetools",
        "library": "cachetools",
        "query": "LRUCache TTLCache cached cachedmethod",
        "tests_aspect": "PyPI, cachetools (extensible cache, unique name)",
    },
    {
        "id": "joblib",
        "library": "joblib",
        "query": "Parallel delayed Memory dump load hash",
        "tests_aspect": "PyPI, joblib.readthedocs.io (lightweight pipelining)",
    },
    {
        "id": "dask",
        "library": "dask",
        "query": "dataframe array delayed compute scheduler",
        "tests_aspect": "PyPI, dask.org (parallel computing)",
    },
    {
        "id": "ray",
        "library": "ray",
        "query": "remote init get put task actor serve",
        "tests_aspect": "PyPI, ray.io (distributed computing, generic name)",
    },
    {
        "id": "prefect",
        "library": "prefect",
        "query": "flow task deployment schedule parameter",
        "tests_aspect": "PyPI, prefect.io (workflow orchestration)",
    },
    {
        "id": "airflow",
        "library": "apache-airflow",
        "query": "DAG operator task sensor trigger schedule",
        "tests_aspect": "PyPI, airflow.apache.org (workflow scheduler)",
    },
    {
        "id": "dagster",
        "library": "dagster",
        "query": "asset op job schedule sensor io_manager",
        "tests_aspect": "PyPI, dagster.io (data orchestration, unique name)",
    },
    {
        "id": "luigi",
        "library": "luigi",
        "query": "Task Target requires output run Parameter",
        "tests_aspect": "PyPI, luigi (Spotify workflow, unique name)",
    },
    # =====================================================================
    # Category AB: Rust Ecosystem (10) — error handling, async, parsing
    # =====================================================================
    {
        "id": "anyhow",
        "library": "anyhow",
        "query": "Result Context Error bail ensure anyhow!",
        "language": "rust",
        "tests_aspect": "crates.io, anyhow (error handling, unique name)",
    },
    {
        "id": "thiserror",
        "library": "thiserror",
        "query": "Error derive from source transparent display",
        "tests_aspect": "crates.io, thiserror (derive Error, unique name)",
    },
    {
        "id": "tracing-rs",
        "library": "tracing",
        "query": "span event instrument subscriber Layer",
        "tests_aspect": "crates.io, tracing-rs (instrumentation, generic name collision npm)",
    },
    {
        "id": "rayon",
        "library": "rayon",
        "query": "par_iter into_par_iter join scope ThreadPool",
        "language": "rust",
        "tests_aspect": "crates.io, rayon (data parallelism, unique name)",
    },
    {
        "id": "regex-rust",
        "library": "regex",
        "query": "Regex captures find replace is_match",
        "tests_aspect": "crates.io, regex (ultra-generic name, npm collision)",
    },
    {
        "id": "hyper-rs",
        "library": "hyper",
        "query": "Client Server Request Response Body service",
        "tests_aspect": "crates.io, hyper.rs (HTTP library, npm collision)",
    },
    {
        "id": "tonic",
        "library": "tonic",
        "query": "Server Request Response Channel transport codec",
        "tests_aspect": "crates.io, tonic (gRPC framework, generic name)",
    },
    {
        "id": "prost",
        "library": "prost",
        "query": "Message encode decode prost_build Service",
        "tests_aspect": "crates.io, prost (Protocol Buffers, unique name)",
    },
    {
        "id": "tower",
        "library": "tower",
        "query": "Service Layer ServiceBuilder timeout retry",
        "tests_aspect": "crates.io, tower-rs (middleware abstractions, generic name)",
    },
    {
        "id": "nom",
        "library": "nom",
        "query": "tag take_while separated_list IResult many0",
        "tests_aspect": "crates.io, nom (parser combinators, ultra-short name)",
    },
    # =====================================================================
    # Category AC: Go Packages (10) — popular Go ecosystem tools
    # =====================================================================
    {
        "id": "cobra",
        "library": "cobra",
        "query": "Command Args Flags PersistentFlags RunE",
        "language": "go",
        "tests_aspect": "Go, cobra.dev (CLI framework, generic name)",
    },
    {
        "id": "viper",
        "library": "viper",
        "query": "SetConfigFile ReadInConfig Get Set BindPFlag",
        "tests_aspect": "Go, viper (config management, generic name collision npm)",
    },
    {
        "id": "zap",
        "library": "zap",
        "query": "Logger Sugar NewProduction Field Info Error",
        "language": "go",
        "tests_aspect": "Go, uber-go/zap (structured logging, generic name)",
    },
    {
        "id": "gorm",
        "library": "gorm",
        "query": "Model Create Find Where Preload AutoMigrate",
        "tests_aspect": "Go, gorm.io (ORM, unique name)",
    },
    {
        "id": "fx",
        "library": "fx",
        "query": "Provide Invoke Module New Supply Lifecycle",
        "tests_aspect": "Go, uber-go/fx (DI framework, ultra-short name collision npm)",
    },
    {
        "id": "wire",
        "library": "wire",
        "query": "Injector Provider Set Bind Value NewSet",
        "tests_aspect": "Go, google/wire (compile-time DI, generic name)",
    },
    {
        "id": "testify",
        "library": "testify",
        "query": "assert require suite mock Equal NotNil",
        "tests_aspect": "Go, testify (test toolkit, generic name)",
    },
    {
        "id": "mockery-go",
        "library": "mockery",
        "query": "mock generate interface expectations Return",
        "tests_aspect": "Go, mockery (mock generator, generic name collision npm)",
    },
    {
        "id": "air",
        "library": "air",
        "query": "live reload .air.toml build cmd tmp",
        "tests_aspect": "Go, air (hot reload, ultra-generic name collision)",
    },
    {
        "id": "gorilla-mux",
        "library": "gorilla/mux",
        "query": "Router HandleFunc PathPrefix Vars Subrouter",
        "language": "go",
        "tests_aspect": "Go, gorilla/mux (HTTP router, slash in name)",
    },
    # =====================================================================
    # Category AD: Mobile & Desktop (10) — cross-platform frameworks
    # =====================================================================
    {
        "id": "react-native",
        "library": "react-native",
        "query": "View Text StyleSheet FlatList navigation",
        "language": "javascript",
        "tests_aspect": "npm, reactnative.dev (mobile framework, hyphenated)",
    },
    {
        "id": "expo",
        "library": "expo",
        "query": "router config plugins assets SDK modules",
        "tests_aspect": "npm, docs.expo.dev (React Native platform)",
    },
    {
        "id": "capacitor",
        "library": "@capacitor/core",
        "query": "Plugins registerPlugin WebPlugin Capacitor bridge",
        "tests_aspect": "scoped npm, capacitorjs.com (mobile runtime)",
    },
    {
        "id": "electron",
        "library": "electron",
        "query": "BrowserWindow ipcMain ipcRenderer app menu",
        "tests_aspect": "npm, electronjs.org (desktop framework)",
    },
    {
        "id": "neutralinojs",
        "library": "@neutralinojs/lib",
        "query": "app os filesystem window events computer",
        "language": "javascript",
        "tests_aspect": "npm, neutralino.js.org (lightweight desktop alt)",
    },
    {
        "id": "wails-go",
        "library": "wails",
        "query": "Application Window Bind Events menu dialog",
        "tests_aspect": "Go, wails.io (Go desktop framework)",
    },
    {
        "id": "fyne-go",
        "library": "fyne",
        "query": "App Window Canvas Widget Container Entry",
        "tests_aspect": "Go, fyne.io (Go GUI toolkit)",
    },
    {
        "id": "kivy",
        "library": "kivy",
        "query": "App Widget Builder BoxLayout Button Label",
        "tests_aspect": "PyPI, kivy.org (Python GUI framework)",
    },
    {
        "id": "dearpygui",
        "library": "dearpygui",
        "query": "create_viewport add_window add_button callback",
        "tests_aspect": "PyPI, dearpygui.readthedocs.io (Python GUI, unique name)",
    },
    {
        "id": "toga",
        "library": "toga",
        "query": "App MainWindow Box Button TextInput handler",
        "language": "python",
        "tests_aspect": "PyPI, toga.readthedocs.io (Python native UI, BeeWare)",
    },
    # =====================================================================
    # Category AE: Python Web Extensions (10) — Flask/Django plugins, ASGI tools
    # =====================================================================
    {
        "id": "flask-cors",
        "library": "flask-cors",
        "query": "CORS cross_origin origins headers methods",
        "tests_aspect": "PyPI, flask-cors (Flask extension, hyphenated)",
    },
    {
        "id": "flask-sqlalchemy",
        "library": "flask-sqlalchemy",
        "query": "db Model init_app session query relationship",
        "tests_aspect": "PyPI, flask-sqlalchemy.readthedocs.io (Flask ORM integration)",
    },
    {
        "id": "django-ninja",
        "library": "django-ninja",
        "query": "api router Schema path query body",
        "tests_aspect": "PyPI, django-ninja.dev (Django REST alternative)",
    },
    {
        "id": "django-filter",
        "library": "django-filter",
        "query": "FilterSet CharFilter NumberFilter filterset_fields",
        "tests_aspect": "PyPI, django-filter (queryset filtering, hyphenated)",
    },
    {
        "id": "gunicorn",
        "library": "gunicorn",
        "query": "workers bind timeout config worker_class",
        "tests_aspect": "PyPI, gunicorn.org (WSGI HTTP server)",
    },
    {
        "id": "whitenoise",
        "library": "whitenoise",
        "query": "static files middleware compression immutable",
        "tests_aspect": "PyPI, whitenoise (static file serving, unique name)",
    },
    {
        "id": "flask-login",
        "library": "flask-login",
        "query": "login_user current_user LoginManager user_loader",
        "tests_aspect": "PyPI, flask-login (auth extension, hyphenated)",
    },
    {
        "id": "django-debug-toolbar",
        "library": "django-debug-toolbar",
        "query": "panels configuration middleware SQL queries",
        "tests_aspect": "PyPI, django-debug-toolbar (debug tool, long hyphenated name)",
    },
    {
        "id": "flask-restx",
        "library": "flask-restx",
        "query": "Namespace Resource fields marshal api.model",
        "tests_aspect": "PyPI, flask-restx (REST API builder, hyphenated)",
    },
    {
        "id": "django-extensions",
        "library": "django-extensions",
        "query": "shell_plus TimeStampedModel runserver_plus graph_models",
        "tests_aspect": "PyPI, django-extensions (utilities collection, hyphenated)",
    },
    # =====================================================================
    # Category AF: Python Scientific & Numerical (10) — more science libs
    # =====================================================================
    {
        "id": "statsmodels",
        "library": "statsmodels",
        "query": "OLS regression ARIMA time series summary",
        "tests_aspect": "PyPI, statsmodels.org (statistical modeling)",
    },
    {
        "id": "xarray",
        "library": "xarray",
        "query": "DataArray Dataset sel isel open_dataset",
        "tests_aspect": "PyPI, xarray.dev (labeled multi-dim arrays)",
    },
    {
        "id": "networkx",
        "library": "networkx",
        "query": "Graph add_edge shortest_path neighbors draw",
        "tests_aspect": "PyPI, networkx.org (graph algorithms)",
    },
    {
        "id": "astropy",
        "library": "astropy",
        "query": "units coordinates FITS Table SkyCoord",
        "tests_aspect": "PyPI, astropy.org (astronomy library, large docs)",
    },
    {
        "id": "biopython",
        "library": "biopython",
        "query": "SeqIO Seq BLAST Entrez PDB alignment",
        "tests_aspect": "PyPI, biopython.org (bioinformatics toolkit)",
    },
    {
        "id": "shapely",
        "library": "shapely",
        "query": "Point Polygon LineString buffer intersection union",
        "tests_aspect": "PyPI, shapely.readthedocs.io (geometric operations)",
    },
    {
        "id": "numba",
        "library": "numba",
        "query": "jit njit vectorize cuda prange parallel",
        "tests_aspect": "PyPI, numba.readthedocs.io (JIT compiler)",
    },
    {
        "id": "h5py",
        "library": "h5py",
        "query": "File create_dataset group attrs dtype",
        "tests_aspect": "PyPI, h5py.org (HDF5 interface, short name)",
    },
    {
        "id": "pyarrow",
        "library": "pyarrow",
        "query": "Table RecordBatch parquet read_table schema",
        "tests_aspect": "PyPI, arrow.apache.org (Apache Arrow bindings)",
    },
    {
        "id": "scikit-image",
        "library": "scikit-image",
        "query": "filters threshold edge detection segmentation",
        "tests_aspect": "PyPI, scikit-image.org (image processing, hyphenated)",
    },
    # =====================================================================
    # Category AG: JavaScript Animation & Visuals (10) — animation, canvas, WebGL
    # =====================================================================
    {
        "id": "gsap",
        "library": "gsap",
        "query": "timeline tween ScrollTrigger fromTo stagger",
        "tests_aspect": "npm, gsap.com (animation platform, unique name)",
    },
    {
        "id": "animejs",
        "library": "animejs",
        "query": "animate targets duration easing keyframes",
        "tests_aspect": "npm, animejs.com (lightweight animation, unique name)",
    },
    {
        "id": "react-spring",
        "library": "@react-spring/web",
        "query": "useSpring animated useTransition config",
        "tests_aspect": "scoped npm, react-spring.dev (React animation)",
    },
    {
        "id": "lottie-web",
        "library": "lottie-web",
        "query": "loadAnimation play stop setSpeed goToAndStop",
        "tests_aspect": "npm, lottie-web (After Effects animations, hyphenated)",
    },
    {
        "id": "matter-js",
        "library": "matter-js",
        "query": "Engine World Bodies Constraint Composite",
        "tests_aspect": "npm, brm.io/matter-js (2D physics engine, hyphenated)",
    },
    {
        "id": "cytoscape",
        "library": "cytoscape",
        "query": "elements nodes edges layout style selector",
        "tests_aspect": "npm, js.cytoscape.org (graph visualization)",
    },
    {
        "id": "paperjs",
        "library": "paper",
        "query": "Path Point Shape Tool Layer PaperScope",
        "tests_aspect": "npm, paperjs.org (vector graphics, name != pkg)",
    },
    {
        "id": "theatre",
        "library": "@theatre/core",
        "query": "project sheet object sequence animation",
        "tests_aspect": "scoped npm, theatrejs.com (motion design tool)",
    },
    {
        "id": "rive",
        "library": "@rive-app/canvas",
        "query": "Rive src stateMachines artboard layout",
        "tests_aspect": "scoped npm, rive.app (interactive animations)",
    },
    {
        "id": "spline",
        "library": "@splinetool/react-spline",
        "query": "Application load canvas events mouse",
        "language": "javascript",
        "tests_aspect": "scoped npm, spline.design (3D web experiences via react-spline).",
    },
    # =====================================================================
    # Category AH: CSS & Styling Tools (10) — PostCSS, CSS-in-JS, design tokens
    # =====================================================================
    {
        "id": "postcss",
        "library": "postcss",
        "query": "plugin process transform AtRule Declaration",
        "tests_aspect": "npm, postcss.org (CSS transformer, unique name)",
    },
    {
        "id": "autoprefixer",
        "library": "autoprefixer",
        "query": "browsers grid flexbox prefixes config",
        "tests_aspect": "npm, autoprefixer (vendor prefix, unique name)",
    },
    {
        "id": "sass",
        "library": "sass",
        "query": "compile variables mixins nesting modules @use",
        "tests_aspect": "npm, sass-lang.com (CSS preprocessor, generic name)",
    },
    {
        "id": "less",
        "library": "less",
        "query": "variables mixins functions import nesting",
        "tests_aspect": "npm, lesscss.org (CSS preprocessor, generic name)",
    },
    {
        "id": "styled-components",
        "library": "styled-components",
        "query": "styled css ThemeProvider createGlobalStyle attrs",
        "tests_aspect": "npm, styled-components.com (CSS-in-JS, hyphenated)",
    },
    {
        "id": "emotion",
        "library": "@emotion/react",
        "query": "css styled ThemeProvider keyframes Global",
        "tests_aspect": "scoped npm, emotion.sh (CSS-in-JS framework)",
    },
    {
        "id": "vanilla-extract",
        "library": "@vanilla-extract/css",
        "query": "style globalStyle createTheme sprinkles recipe",
        "tests_aspect": "scoped npm, vanilla-extract.style (zero-runtime CSS-in-TS)",
    },
    {
        "id": "stylelint",
        "library": "stylelint",
        "query": "rules config plugins extends fix customSyntax",
        "tests_aspect": "npm, stylelint.io (CSS linter, unique name)",
    },
    {
        "id": "cssnano",
        "library": "cssnano",
        "query": "preset plugins minify optimise advanced",
        "tests_aspect": "npm, cssnano.github.io (CSS minifier, unique name)",
    },
    {
        "id": "lightningcss",
        "library": "lightningcss",
        "query": "transform bundle minify targets features nesting",
        "tests_aspect": "npm, lightningcss.dev (fast CSS tool, Rust-based)",
    },
    # =====================================================================
    # Category AI: Rust Systems Programming (10) — OS, filesystem, crypto
    # =====================================================================
    {
        "id": "sled",
        "library": "sled",
        "query": "Db Tree insert get remove flush open",
        "tests_aspect": "crates.io, sled (embedded database, unique name)",
    },
    {
        "id": "ring",
        "library": "ring",
        "query": "digest signature agreement aead pbkdf2",
        "language": "rust",
        "tests_aspect": "crates.io, ring (crypto primitives, generic name)",
    },
    {
        "id": "rustls",
        "library": "rustls",
        "query": "ServerConfig ClientConfig Certificate TLS stream",
        "tests_aspect": "crates.io, rustls (TLS library, unique name)",
    },
    {
        "id": "libc",
        "library": "libc",
        "query": "c_int c_char size_t pid_t stat ioctl",
        "language": "rust",
        "tests_aspect": "crates.io, libc (FFI bindings, generic name)",
    },
    {
        "id": "nix-rs",
        "library": "nix",
        "query": "unistd sys signal mount socket poll",
        "language": "rust",
        "tests_aspect": "crates.io, nix (Unix API bindings, name collision with Nix pkg mgr)",
    },
    {
        "id": "memmap2",
        "library": "memmap2",
        "query": "MmapOptions Mmap MmapMut map map_mut",
        "tests_aspect": "crates.io, memmap2 (memory-mapped files, unique name)",
    },
    {
        "id": "notify-rs",
        "library": "notify",
        "query": "Watcher RecommendedWatcher Event EventKind RecursiveMode",
        "language": "rust",
        "tests_aspect": "crates.io, notify (filesystem watcher, generic name)",
    },
    {
        "id": "walkdir",
        "library": "walkdir",
        "query": "WalkDir DirEntry into_iter min_depth max_depth",
        "language": "rust",
        "tests_aspect": "crates.io, walkdir (directory traversal, unique name)",
    },
    {
        "id": "tempfile",
        "library": "tempfile",
        "query": "NamedTempFile TempDir tempdir Builder persist",
        "language": "rust",
        "tests_aspect": "crates.io, tempfile (temp files, generic name)",
    },
    {
        "id": "rand-rs",
        "library": "rand",
        "query": "Rng thread_rng gen_range random distributions",
        "language": "rust",
        "tests_aspect": "crates.io, rand (random numbers, ultra-generic name)",
    },
    # =====================================================================
    # Category AJ: Go Infrastructure (10) — monitoring, tracing, caching
    # =====================================================================
    {
        "id": "logrus",
        "library": "logrus",
        "query": "WithFields Info Warn Error Entry Formatter",
        "language": "go",
        "tests_aspect": "Go, sirupsen/logrus (structured logging, generic name)",
    },
    {
        "id": "zerolog",
        "library": "zerolog",
        "query": "Logger Str Int Msg Err With Timestamp",
        "tests_aspect": "Go, rs/zerolog (zero-alloc logging, unique name)",
    },
    {
        "id": "caddy",
        "library": "caddy",
        "query": "Caddyfile reverse_proxy tls auto_https handle",
        "tests_aspect": "Go, caddyserver.com (web server, unique name)",
    },
    {
        "id": "colly",
        "library": "colly",
        "query": "Collector OnHTML OnRequest Visit Scrape",
        "tests_aspect": "Go, go-colly.org (web scraper, unique name)",
    },
    {
        "id": "goquery",
        "library": "goquery",
        "query": "Document Selection Find Each Attr Text Html",
        "tests_aspect": "Go, goquery (jQuery-like HTML parser, unique name)",
    },
    {
        "id": "casbin",
        "library": "casbin",
        "query": "Enforcer Model Policy AddPolicy Enforce RBAC",
        "tests_aspect": "Go, casbin.org (authorization library, unique name)",
    },
    {
        "id": "watermill",
        "library": "watermill",
        "query": "Publisher Subscriber Router Handler Message",
        "language": "go",
        "tests_aspect": "Go, watermill.io (event-driven, generic name)",
    },
    {
        "id": "sarama",
        "library": "sarama",
        "query": "Producer Consumer Client Partition Topic Offset",
        "language": "go",
        "tests_aspect": "Go, IBM/sarama (Kafka client, unique name)",
    },
    {
        "id": "go-kit",
        "library": "go-kit/kit",
        "query": "endpoint transport middleware service logging",
        "language": "go",
        "tests_aspect": "Go, gokit.io (microservices toolkit, hyphenated)",
    },
    {
        "id": "afero",
        "library": "afero",
        "query": "Fs MemMapFs OsFs NewOsFs Open ReadFile",
        "tests_aspect": "Go, spf13/afero (filesystem abstraction, unique name)",
    },
    # =====================================================================
    # Category AK: Node.js Streams & Files (10) — file handling, streams
    # =====================================================================
    {
        "id": "fs-extra",
        "library": "fs-extra",
        "query": "copy move remove ensureDir readJson outputFile",
        "tests_aspect": "npm, fs-extra (filesystem utilities, hyphenated)",
    },
    {
        "id": "glob",
        "library": "glob",
        "query": "pattern match sync stream ignore cwd",
        "tests_aspect": "npm, glob (file matching, ultra-generic name)",
    },
    {
        "id": "chokidar",
        "library": "chokidar",
        "query": "watch on add change unlink ready persistent",
        "language": "javascript",
        "tests_aspect": "npm, chokidar (file watcher, unique name)",
    },
    {
        "id": "archiver",
        "library": "archiver",
        "query": "create pipe append directory finalize zip tar",
        "language": "javascript",
        "tests_aspect": "npm, archiver (archive streaming, unique name)",
    },
    {
        "id": "multer",
        "library": "multer",
        "query": "upload single array fields storage diskStorage",
        "language": "javascript",
        "tests_aspect": "npm, multer (file upload middleware, unique name)",
    },
    {
        "id": "formidable",
        "library": "formidable",
        "query": "parse fields files IncomingForm options maxFileSize",
        "language": "javascript",
        "tests_aspect": "npm, formidable (form data parsing, unique name)",
    },
    {
        "id": "tmp",
        "library": "tmp",
        "query": "tmpName file dir setGracefulCleanup template",
        "language": "javascript",
        "tests_aspect": "npm, tmp (temp files, ultra-short generic name)",
    },
    {
        "id": "rimraf",
        "library": "rimraf",
        "query": "rimraf sync glob options force recursive",
        "language": "javascript",
        "tests_aspect": "npm, rimraf (rm -rf for Node.js, unique name)",
    },
    {
        "id": "mkdirp",
        "library": "mkdirp",
        "query": "mkdirp sync mode manual native",
        "language": "javascript",
        "tests_aspect": "npm, mkdirp (mkdir -p for Node.js, unique name)",
    },
    {
        "id": "fast-glob",
        "library": "fast-glob",
        "query": "pattern ignore cwd dot onlyFiles stats",
        "language": "javascript",
        "tests_aspect": "npm, fast-glob (high-perf glob, hyphenated)",
    },
    # =====================================================================
    # Category AL: Python Formatting & Linting (10) — code quality tools
    # =====================================================================
    {
        "id": "black",
        "library": "black",
        "query": "format line_length target_version config check diff",
        "language": "python",
        "tests_aspect": "PyPI, black.readthedocs.io (code formatter, generic name)",
    },
    {
        "id": "isort",
        "library": "isort",
        "query": "profile sections known_third_party multi_line skip",
        "language": "python",
        "tests_aspect": "PyPI, pycqa.github.io/isort (import sorter, unique name)",
    },
    {
        "id": "mypy",
        "library": "mypy",
        "query": "type checking config strict ignore_errors reveal_type",
        "language": "python",
        "tests_aspect": "PyPI, mypy.readthedocs.io (static type checker)",
    },
    {
        "id": "pyright",
        "library": "pyright",
        "query": "type checking reportMissingImports config strict diagnostic",
        "language": "python",
        "tests_aspect": "PyPI/npm, pyright (MS type checker, cross-ecosystem)",
    },
    {
        "id": "pylint",
        "library": "pylint",
        "query": "rcfile disable enable message convention refactor",
        "language": "python",
        "tests_aspect": "PyPI, pylint.readthedocs.io (code analyzer)",
    },
    {
        "id": "flake8",
        "library": "flake8",
        "query": "select ignore max-line-length extend plugins",
        "language": "python",
        "tests_aspect": "PyPI, flake8.pycqa.org (style checker, unique name)",
    },
    {
        "id": "bandit",
        "library": "bandit",
        "query": "security scan severity confidence skip tests",
        "language": "python",
        "tests_aspect": "PyPI, bandit.readthedocs.io (security linter, generic name)",
    },
    {
        "id": "autopep8",
        "library": "autopep8",
        "query": "fix_code aggressive max_line_length in_place",
        "language": "python",
        "tests_aspect": "PyPI, autopep8 (PEP8 formatter, unique name)",
    },
    {
        "id": "pre-commit",
        "library": "pre-commit",
        "query": "hooks repos rev install run autoupdate",
        "language": "python",
        "tests_aspect": "PyPI, pre-commit.com (git hook manager, hyphenated)",
    },
    {
        "id": "pycodestyle",
        "library": "pycodestyle",
        "query": "check max_line_length ignore select statistics",
        "tests_aspect": "PyPI, pycodestyle (PEP8 checker, formerly pep8)",
    },
    # =====================================================================
    # Category AM: Email & Notifications (10) — email, push, SMS libs
    # =====================================================================
    {
        "id": "nodemailer",
        "library": "nodemailer",
        "query": "createTransport sendMail SMTP attachments html",
        "tests_aspect": "npm, nodemailer.com (email sending, unique name)",
    },
    {
        "id": "sendgrid",
        "library": "@sendgrid/mail",
        "query": "send setApiKey MailService personalizations",
        "tests_aspect": "scoped npm, sendgrid.com (email API service)",
    },
    {
        "id": "email-validator",
        "library": "email-validator",
        "query": "validate_email check_deliverability normalize EmailNotValidError",
        "tests_aspect": "PyPI, email-validator (validation, hyphenated)",
    },
    {
        "id": "yagmail",
        "library": "yagmail",
        "query": "SMTP send to subject contents attachments",
        "tests_aspect": "PyPI, yagmail (simple Gmail sender, unique name)",
    },
    {
        "id": "web-push",
        "library": "web-push",
        "query": "sendNotification setVapidDetails generateVAPIDKeys",
        "tests_aspect": "npm, web-push (push notifications, hyphenated)",
    },
    {
        "id": "postmark",
        "library": "postmark",
        "query": "ServerClient sendEmail template batch bounce",
        "tests_aspect": "npm, postmarkapp.com (transactional email, unique name)",
    },
    {
        "id": "resend",
        "library": "resend",
        "query": "emails send from to subject html react",
        "tests_aspect": "npm, resend.com (developer email API, unique name)",
    },
    {
        "id": "mailparser",
        "library": "mailparser",
        "query": "simpleParser MailParser headers attachments html text",
        "tests_aspect": "npm, mailparser (email parser, unique name)",
    },
    {
        "id": "aiosmtpd",
        "library": "aiosmtpd",
        "query": "Controller handler SMTP AUTH STARTTLS",
        "tests_aspect": "PyPI, aiosmtpd.readthedocs.io (async SMTP server)",
    },
    {
        "id": "notifiers",
        "library": "notifiers",
        "query": "notify provider slack email telegram pushover",
        "tests_aspect": "PyPI, notifiers (multi-channel notifications, unique name)",
    },
    # =====================================================================
    # Category AN: Template Engines & Rendering (10) — EJS, Handlebars, Jinja
    # =====================================================================
    {
        "id": "ejs",
        "library": "ejs",
        "query": "render template include locals compile data",
        "tests_aspect": "npm, ejs.co (embedded JavaScript templates, short name)",
    },
    {
        "id": "handlebars",
        "library": "handlebars",
        "query": "compile template helper partial registerHelper",
        "language": "javascript",
        "tests_aspect": "npm, handlebarsjs.com (template engine, unique name)",
    },
    {
        "id": "nunjucks",
        "library": "nunjucks",
        "query": "render Environment configure filter macro extends",
        "tests_aspect": "npm, mozilla.github.io/nunjucks (Jinja2-inspired, unique name)",
    },
    {
        "id": "pug",
        "library": "pug",
        "query": "render compile template mixin include extends",
        "tests_aspect": "npm, pugjs.org (indent-based HTML, short name)",
    },
    {
        "id": "mustache",
        "library": "mustache",
        "query": "render template tags partials sections lambdas",
        "language": "javascript",
        "tests_aspect": "npm, mustache.github.io (logic-less templates, unique name)",
    },
    {
        "id": "eta",
        "library": "eta",
        "query": "render renderAsync configure partial layout include",
        "tests_aspect": "npm, eta.js.org (lightweight template engine, short name)",
    },
    {
        "id": "jinja2",
        "library": "jinja2",
        "query": "Environment render template filter extends macro",
        "tests_aspect": "PyPI, jinja.palletsprojects.com (Python templates)",
    },
    {
        "id": "mako",
        "library": "mako",
        "query": "Template render_unicode TemplateLookup def include",
        "tests_aspect": "PyPI, makotemplates.org (Python templates, unique name)",
    },
    {
        "id": "liquidjs",
        "library": "liquidjs",
        "query": "Liquid parse render tag filter plugin",
        "tests_aspect": "npm, liquidjs.com (Shopify Liquid in JS, unique name)",
    },
    {
        "id": "react-email",
        "library": "@react-email/components",
        "query": "Html Head Body Container Section Button",
        "tests_aspect": "scoped npm, react.email (email components with React)",
    },
    # =====================================================================
    # Category AO: Reactive & Event Systems (10) — event emitters, signals
    # =====================================================================
    {
        "id": "eventemitter3",
        "library": "eventemitter3",
        "query": "on emit once removeListener listeners eventNames",
        "tests_aspect": "npm, eventemitter3 (high-perf event emitter, unique name)",
    },
    {
        "id": "mitt",
        "library": "mitt",
        "query": "on off emit all handler type",
        "tests_aspect": "npm, mitt (tiny 200B event emitter, short name)",
    },
    {
        "id": "immer",
        "library": "immer",
        "query": "produce draft enableMapSet original freeze",
        "tests_aspect": "npm, immerjs.github.io (immutable state, unique name)",
    },
    {
        "id": "effector",
        "library": "effector",
        "query": "createStore createEvent createEffect sample combine",
        "tests_aspect": "npm, effector.dev (reactive state manager, unique name)",
    },
    {
        "id": "preact-signals",
        "library": "@preact/signals-core",
        "query": "signal computed effect batch untracked",
        "tests_aspect": "scoped npm, preactjs.com/signals (fine-grained reactivity)",
    },
    {
        "id": "nanostores",
        "library": "nanostores",
        "query": "atom map computed action onMount listen",
        "tests_aspect": "npm, nanostores (tiny state, framework-agnostic, unique name)",
    },
    {
        "id": "emittery",
        "library": "emittery",
        "query": "on emit once onAny clearListeners events",
        "tests_aspect": "npm, emittery (async event emitter, unique name)",
    },
    {
        "id": "p-queue",
        "library": "p-queue",
        "query": "PQueue add concurrency priority onIdle size",
        "tests_aspect": "npm, p-queue (promise queue, hyphenated, short name)",
    },
    {
        "id": "rxdb",
        "library": "rxdb",
        "query": "createRxDatabase addCollections find insert subscribe",
        "tests_aspect": "npm, rxdb.info (reactive database, unique name)",
    },
    {
        "id": "tinybase",
        "library": "tinybase",
        "query": "createStore setCell getCell addRow Queries",
        "tests_aspect": "npm, tinybase.org (reactive data store, unique name)",
    },
    # =====================================================================
    # Category AP: Machine Learning Extras (10) — more ML libs
    # =====================================================================
    {
        "id": "xgboost",
        "library": "xgboost",
        "query": "XGBClassifier train DMatrix feature_importance cv",
        "tests_aspect": "PyPI, xgboost.readthedocs.io (gradient boosting)",
    },
    {
        "id": "lightgbm",
        "library": "lightgbm",
        "query": "LGBMClassifier train Dataset feature_importance cv",
        "tests_aspect": "PyPI, lightgbm.readthedocs.io (gradient boosting, unique name)",
    },
    {
        "id": "catboost",
        "library": "catboost",
        "query": "CatBoostClassifier Pool fit predict feature_importance",
        "tests_aspect": "PyPI, catboost.ai (gradient boosting, unique name)",
    },
    {
        "id": "optuna",
        "library": "optuna",
        "query": "create_study trial suggest_float optimize pruner",
        "tests_aspect": "PyPI, optuna.org (hyperparameter optimization, unique name)",
    },
    {
        "id": "mlflow",
        "library": "mlflow",
        "query": "log_metric log_param start_run autolog register_model",
        "tests_aspect": "PyPI, mlflow.org (experiment tracking, unique name)",
    },
    {
        "id": "wandb",
        "library": "wandb",
        "query": "init log watch config sweep artifact",
        "tests_aspect": "PyPI, wandb.ai (experiment tracking, unique name)",
    },
    {
        "id": "onnxruntime",
        "library": "onnxruntime",
        "query": "InferenceSession run get_inputs SessionOptions providers",
        "tests_aspect": "PyPI, onnxruntime.ai (ONNX inference, unique name)",
    },
    {
        "id": "gradio",
        "library": "gradio",
        "query": "Interface launch Blocks Textbox Image Button",
        "tests_aspect": "PyPI, gradio.app (ML demos, unique name)",
    },
    {
        "id": "streamlit",
        "library": "streamlit",
        "query": "write title sidebar dataframe chart button",
        "tests_aspect": "PyPI, streamlit.io (data apps, unique name)",
    },
    {
        "id": "sentence-transformers",
        "library": "sentence-transformers",
        "query": "SentenceTransformer encode similarity models util",
        "tests_aspect": "PyPI, sbert.net (embeddings, long hyphenated name)",
    },
    # =====================================================================
    # Category AQ: API Clients & SDKs (10) — stripe, OpenAI, etc.
    # =====================================================================
    {
        "id": "stripe",
        "library": "stripe",
        "query": "Checkout Session PaymentIntent Customer Subscription",
        "tests_aspect": "npm, docs.stripe.com (payment API, short name)",
    },
    {
        "id": "openai",
        "library": "openai",
        "query": "ChatCompletion create messages model stream",
        "language": "python",
        "tests_aspect": "PyPI, platform.openai.com (AI API SDK, npm collision)",
    },
    {
        "id": "octokit",
        "library": "@octokit/rest",
        "query": "repos issues pulls actions createRelease",
        "tests_aspect": "scoped npm, octokit.github.io (GitHub API client)",
    },
    {
        "id": "twilio",
        "library": "twilio",
        "query": "messages create send verify voice client",
        "tests_aspect": "npm, twilio.com (communication API, unique name)",
    },
    {
        "id": "slack-sdk",
        "library": "slack-sdk",
        "query": "WebClient chat_postMessage events socket_mode",
        "tests_aspect": "PyPI, slack.dev (Slack API SDK, hyphenated)",
    },
    {
        "id": "anthropic",
        "library": "anthropic",
        "query": "messages create model max_tokens stream",
        "tests_aspect": "PyPI, docs.anthropic.com (AI API SDK, unique name)",
    },
    {
        "id": "sentry-sdk",
        "library": "sentry-sdk",
        "query": "init capture_exception set_user traces_sample_rate",
        "tests_aspect": "PyPI, docs.sentry.io (error tracking, hyphenated)",
    },
    {
        "id": "replicate",
        "library": "replicate",
        "query": "run predictions create model version stream",
        "tests_aspect": "PyPI, replicate.com (ML API client, unique name)",
    },
    {
        "id": "cohere",
        "library": "cohere",
        "query": "chat embed rerank classify generate",
        "language": "python",
        "tests_aspect": "PyPI, docs.cohere.com (AI API SDK, unique name)",
    },
    {
        "id": "mistralai",
        "library": "mistralai",
        "query": "chat complete models agents embeddings",
        "tests_aspect": "PyPI, docs.mistral.ai (AI API SDK, unique name)",
    },
    # =====================================================================
    # Category AR: Rust Async & Concurrency (10) — async runtime, channels
    # =====================================================================
    {
        "id": "crossbeam",
        "library": "crossbeam",
        "query": "channel select scope epoch queue deque",
        "tests_aspect": "crates.io, crossbeam-rs (concurrency tools, unique name)",
    },
    {
        "id": "parking-lot",
        "library": "parking_lot",
        "query": "Mutex RwLock Condvar Once ReentrantMutex",
        "tests_aspect": "crates.io, parking_lot (sync primitives, underscore name)",
    },
    {
        "id": "async-trait",
        "library": "async-trait",
        "query": "async_trait trait impl async fn Send",
        "tests_aspect": "crates.io, async-trait (async in traits, hyphenated)",
    },
    {
        "id": "futures-rs",
        "library": "futures",
        "query": "Stream Future join select pin_mut executor",
        "language": "rust",
        "tests_aspect": "crates.io, futures (async abstractions, ultra-generic name)",
    },
    {
        "id": "mio",
        "library": "mio",
        "query": "Poll Token Events Interest TcpListener Registry",
        "language": "rust",
        "tests_aspect": "crates.io, mio (low-level async I/O, unique name)",
    },
    {
        "id": "bytes-rs",
        "library": "bytes",
        "query": "Bytes BytesMut Buf BufMut put get slice",
        "language": "rust",
        "tests_aspect": "crates.io, bytes (byte buffer, ultra-generic name)",
    },
    {
        "id": "dashmap",
        "library": "dashmap",
        "query": "DashMap DashSet insert get entry iter",
        "tests_aspect": "crates.io, dashmap (concurrent HashMap, unique name)",
    },
    {
        "id": "flume",
        "library": "flume",
        "query": "unbounded bounded Sender Receiver select recv",
        "tests_aspect": "crates.io, flume (MPMC channel, unique name)",
    },
    {
        "id": "smol",
        "library": "smol",
        "query": "block_on spawn Executor Timer Async Unblock",
        "tests_aspect": "crates.io, smol (small async runtime, unique name)",
    },
    {
        "id": "async-std",
        "library": "async-std",
        "query": "task spawn block_on File TcpListener stream",
        "tests_aspect": "crates.io, async-std (async stdlib, hyphenated)",
    },
    # =====================================================================
    # Category AS: Go Database & Storage (10) — Go DB drivers, caches
    # =====================================================================
    {
        "id": "pgx",
        "library": "pgx",
        "query": "Connect Query QueryRow Exec Pool Scan Rows",
        "language": "go",
        "tests_aspect": "Go, jackc/pgx (PostgreSQL driver, short name)",
    },
    {
        "id": "ent",
        "library": "ent",
        "query": "Schema Fields Edges Mixin Client Create Query",
        "language": "go",
        "tests_aspect": "Go, entgo.io (entity framework, ultra-short name)",
    },
    {
        "id": "bbolt",
        "library": "bbolt",
        "query": "DB Open Bucket Put Get Cursor Tx",
        "tests_aspect": "Go, bbolt (embedded KV store, unique name)",
    },
    {
        "id": "badger-go",
        "library": "badger",
        "query": "DB Open Set Get Delete Txn Iterator",
        "language": "go",
        "tests_aspect": "Go, dgraph-io/badger (embedded KV, generic name)",
    },
    {
        "id": "go-redis",
        "library": "go-redis",
        "query": "Client Set Get Pipeline Subscribe Cluster",
        "tests_aspect": "Go, redis/go-redis (Redis client, prefixed name)",
    },
    {
        "id": "sqlboiler",
        "library": "sqlboiler",
        "query": "model query relationship eager loading Bind",
        "tests_aspect": "Go, sqlboiler (ORM from DB schema, unique name)",
    },
    {
        "id": "migrate-go",
        "library": "migrate",
        "query": "Up Down Steps Version Force source database",
        "language": "go",
        "tests_aspect": "Go, golang-migrate (DB migrations, ultra-generic name)",
    },
    {
        "id": "groupcache",
        "library": "groupcache",
        "query": "Group Get Sink ByteView Getter peer",
        "tests_aspect": "Go, golang/groupcache (distributed cache, unique name)",
    },
    {
        "id": "rqlite",
        "library": "rqlite",
        "query": "Execute Query node cluster Raft consensus",
        "tests_aspect": "Go, rqlite.io (distributed SQLite, unique name)",
    },
    {
        "id": "xorm",
        "library": "xorm",
        "query": "Engine Find Insert Update Delete Session",
        "tests_aspect": "Go, xorm.io (ORM engine, unique name)",
    },
    # =====================================================================
    # Category AT: Python Async & Concurrency (10) — async libs
    # =====================================================================
    {
        "id": "anyio",
        "library": "anyio",
        "query": "create_task_group run sleep open_file Event",
        "tests_aspect": "PyPI, anyio.readthedocs.io (async compatibility, unique name)",
    },
    {
        "id": "trio",
        "library": "trio",
        "query": "open_nursery sleep run open_tcp_stream Event",
        "tests_aspect": "PyPI, trio.readthedocs.io (structured concurrency, unique name)",
    },
    {
        "id": "asyncpg",
        "library": "asyncpg",
        "query": "connect fetch fetchrow execute create_pool",
        "tests_aspect": "PyPI, asyncpg (async PostgreSQL, unique name)",
    },
    {
        "id": "aiofiles",
        "library": "aiofiles",
        "query": "open read write tempfile os wrap",
        "tests_aspect": "PyPI, aiofiles (async file I/O, unique name)",
    },
    {
        "id": "uvloop",
        "library": "uvloop",
        "query": "install EventLoopPolicy run loop libuv",
        "tests_aspect": "PyPI, uvloop (fast event loop, unique name)",
    },
    {
        "id": "asyncssh",
        "library": "asyncssh",
        "query": "connect create_server SSHClient run SFTP keys",
        "language": "python",
        "tests_aspect": "PyPI, asyncssh.readthedocs.io (async SSH, unique name)",
    },
    {
        "id": "aiocache",
        "library": "aiocache",
        "query": "cached Cache RedisCache SimpleMemoryCache serializer",
        "tests_aspect": "PyPI, aiocache (async caching, unique name)",
    },
    {
        "id": "aiomysql",
        "library": "aiomysql",
        "query": "connect create_pool cursor execute fetchone",
        "tests_aspect": "PyPI, aiomysql (async MySQL driver, unique name)",
    },
    {
        "id": "granian",
        "library": "granian",
        "query": "Granian serve workers threads interface ASGI RSGI",
        "tests_aspect": "PyPI, granian (Rust ASGI server, unique name)",
    },
    {
        "id": "greenlet",
        "library": "greenlet",
        "query": "greenlet switch getcurrent GreenletExit parent",
        "tests_aspect": "PyPI, greenlet (lightweight coroutines, unique name)",
    },
    # =====================================================================
    # Category AU: JavaScript Forms & Validation (10) — form libs, validation
    # =====================================================================
    {
        "id": "react-hook-form",
        "library": "react-hook-form",
        "query": "useForm register handleSubmit watch errors Controller",
        "tests_aspect": "npm, react-hook-form.com (React form lib, hyphenated)",
    },
    {
        "id": "formik",
        "library": "formik",
        "query": "Formik Form Field useFormik validationSchema",
        "tests_aspect": "npm, formik.org (React form management, unique name)",
    },
    {
        "id": "tanstack-form",
        "library": "@tanstack/react-form",
        "query": "useForm form.Field validators onChange onBlur",
        "tests_aspect": "scoped npm, tanstack.com/form (headless form lib)",
    },
    {
        "id": "final-form",
        "library": "final-form",
        "query": "createForm subscribe reset submit Field Form",
        "tests_aspect": "npm, final-form.org (framework-agnostic forms, hyphenated)",
    },
    {
        "id": "superstruct",
        "library": "superstruct",
        "query": "object string number validate assert create",
        "tests_aspect": "npm, superstruct (struct validation, unique name)",
    },
    {
        "id": "class-validator",
        "library": "class-validator",
        "query": "IsEmail IsString MinLength validate ValidateNested",
        "tests_aspect": "npm, class-validator (decorator validation, hyphenated)",
    },
    {
        "id": "io-ts",
        "library": "io-ts",
        "query": "type string number decode encode intersection",
        "tests_aspect": "npm, io-ts (runtime type system, hyphenated)",
    },
    {
        "id": "class-transformer",
        "library": "class-transformer",
        "query": "plainToInstance Expose Exclude Type Transform",
        "tests_aspect": "npm, class-transformer (object transform, hyphenated)",
    },
    {
        "id": "conform",
        "library": "@conform-to/react",
        "query": "useForm getFormProps getInputProps submission",
        "tests_aspect": "scoped npm, conform.guide (progressive form validation)",
    },
    {
        "id": "vest",
        "library": "vest",
        "query": "create test enforce only skip warn",
        "tests_aspect": "npm, vestjs.dev (validation framework, unique name)",
    },
    # =====================================================================
    # Category AV: Container & Cloud SDKs (10) — Docker, K8s, cloud SDKs
    # =====================================================================
    {
        "id": "aws-sdk-s3",
        "library": "@aws-sdk/client-s3",
        "query": "S3Client PutObjectCommand GetObjectCommand Bucket",
        "tests_aspect": "scoped npm, AWS SDK v3 (deeply scoped modular SDK)",
    },
    {
        "id": "gcs-python",
        "library": "google-cloud-storage",
        "query": "Client Bucket Blob upload_from_string download",
        "tests_aspect": "PyPI, cloud.google.com (GCS Python SDK, long name)",
    },
    {
        "id": "azure-id-node",
        "library": "@azure/identity",
        "query": "DefaultAzureCredential ClientSecretCredential token",
        "tests_aspect": "scoped npm, azure.github.io (Azure auth SDK)",
    },
    {
        "id": "gcs-node",
        "library": "@google-cloud/storage",
        "query": "Storage Bucket File upload download createReadStream",
        "tests_aspect": "scoped npm, cloud.google.com (GCS Node.js SDK)",
    },
    {
        "id": "azure-id-python",
        "library": "azure-identity",
        "query": "DefaultAzureCredential ClientSecretCredential token",
        "tests_aspect": "PyPI, azure-identity (Azure auth Python SDK, hyphenated)",
    },
    {
        "id": "minio-client",
        "library": "minio",
        "query": "Minio put_object get_object make_bucket fput_object",
        "language": "python",
        "tests_aspect": "PyPI, min.io (S3-compatible client, generic name collision npm)",
    },
    {
        "id": "pulumi-aws",
        "library": "@pulumi/aws",
        "query": "s3 ec2 lambda iam Bucket Function",
        "tests_aspect": "scoped npm, pulumi.com/registry (AWS provider)",
    },
    {
        "id": "aws-cdk",
        "library": "aws-cdk-lib",
        "query": "Stack App Construct s3 lambda ec2 CfnOutput",
        "tests_aspect": "npm, docs.aws.amazon.com/cdk (AWS CDK v2, long name)",
    },
    {
        "id": "google-api-python",
        "library": "google-api-python-client",
        "query": "build discovery service execute credentials",
        "tests_aspect": "PyPI, google-api-python-client (Google API, very long name)",
    },
    {
        "id": "cdk8s",
        "library": "cdk8s",
        "query": "App Chart ApiObject Helm include synth",
        "tests_aspect": "npm, cdk8s.io (Kubernetes CDK, unique name)",
    },
    # =====================================================================
    # Category AW: Markdown & Content (10) — markdown parsers, content tools
    # =====================================================================
    {
        "id": "remark",
        "library": "remark",
        "query": "remark process use plugin remarkParse stringify",
        "tests_aspect": "npm, remark.js.org (markdown processor, unified ecosystem)",
    },
    {
        "id": "rehype",
        "library": "rehype",
        "query": "rehype process use plugin rehypeParse stringify",
        "tests_aspect": "npm, rehype (HTML processor, unified ecosystem, unique name)",
    },
    {
        "id": "unified",
        "library": "unified",
        "query": "unified use process parse stringify run plugin",
        "tests_aspect": "npm, unifiedjs.com (content processing, unique name)",
    },
    {
        "id": "markdown-it",
        "library": "markdown-it",
        "query": "render renderInline use plugin enable disable",
        "tests_aspect": "npm, markdown-it (markdown parser, hyphenated)",
    },
    {
        "id": "marked",
        "library": "marked",
        "query": "parse Renderer Tokenizer use extensions",
        "tests_aspect": "npm, marked.js.org (markdown compiler, unique name)",
    },
    {
        "id": "mdx",
        "library": "@mdx-js/mdx",
        "query": "compile evaluate run createProcessor MDXProvider",
        "tests_aspect": "scoped npm, mdxjs.com (Markdown + JSX)",
    },
    {
        "id": "turndown",
        "library": "turndown",
        "query": "TurndownService turndown addRule keep remove",
        "tests_aspect": "npm, turndown (HTML to Markdown, unique name)",
    },
    {
        "id": "gray-matter",
        "library": "gray-matter",
        "query": "matter data content excerpt engines stringify",
        "tests_aspect": "npm, gray-matter (frontmatter parser, hyphenated)",
    },
    {
        "id": "mistune",
        "library": "mistune",
        "query": "create_markdown html renderer plugins BlockParser",
        "tests_aspect": "PyPI, mistune (fast markdown parser, unique name)",
    },
    {
        "id": "python-docx",
        "library": "python-docx",
        "query": "Document add_paragraph add_table add_heading style",
        "tests_aspect": "PyPI, python-docx (Word documents, hyphenated)",
    },
    # =====================================================================
    # Category AX: Miscellaneous Popular (10) — remaining popular libs
    # =====================================================================
    {
        "id": "tanstack-table",
        "library": "@tanstack/react-table",
        "query": "useReactTable getCoreRowModel columnHelper flexRender",
        "tests_aspect": "scoped npm, tanstack.com/table (headless table)",
    },
    {
        "id": "tanstack-router",
        "library": "@tanstack/react-router",
        "query": "createRouter createRoute Outlet Link useParams",
        "tests_aspect": "scoped npm, tanstack.com/router (type-safe routing)",
    },
    {
        "id": "i18next",
        "library": "i18next",
        "query": "init t use changeLanguage namespace interpolation",
        "tests_aspect": "npm, i18next.com (internationalization, unique name)",
    },
    {
        "id": "headlessui",
        "library": "@headlessui/react",
        "query": "Dialog Menu Listbox Combobox Transition Tab",
        "tests_aspect": "scoped npm, headlessui.com (unstyled UI components)",
    },
    {
        "id": "radix-themes",
        "library": "@radix-ui/themes",
        "query": "Theme Button Card Flex Text Select Dialog",
        "tests_aspect": "scoped npm, radix-ui.com (design system components)",
    },
    {
        "id": "clsx",
        "library": "clsx",
        "query": "clsx classnames conditional string object array",
        "tests_aspect": "npm, clsx (className utility, ultra-short name)",
    },
    {
        "id": "tailwind-merge",
        "library": "tailwind-merge",
        "query": "twMerge extendTailwindMerge config override",
        "tests_aspect": "npm, tailwind-merge (class merging, hyphenated)",
    },
    {
        "id": "cva",
        "library": "class-variance-authority",
        "query": "cva variants compoundVariants defaultVariants cx",
        "tests_aspect": "npm, cva.style (variant utilities, id != pkg name)",
    },
    {
        "id": "cmdk",
        "library": "cmdk",
        "query": "Command Input List Item Group Dialog Empty",
        "tests_aspect": "npm, cmdk.paco.me (command palette, short name)",
    },
    {
        "id": "sonner",
        "library": "sonner",
        "query": "toast Toaster success error promise loading",
        "tests_aspect": "npm, sonner.emilkowal.ski (toast notifications, unique name)",
    },
    # =====================================================================
    # Category AY: Java — Spring ecosystem (10)
    # =====================================================================
    {
        "id": "spring-boot",
        "library": "spring-boot",
        "query": "auto-configuration properties starter dependencies",
        "tests_aspect": "Java, GitHub search (spring.io docs)",
        "language": "java",
    },
    {
        "id": "spring-framework",
        "library": "spring-framework",
        "query": "dependency injection bean lifecycle scope",
        "tests_aspect": "Java, GitHub search (spring.io docs)",
        "language": "java",
    },
    {
        "id": "hibernate-orm",
        "library": "hibernate-orm",
        "query": "entity mapping one-to-many lazy loading",
        "tests_aspect": "Java, GitHub search (hibernate.org docs)",
        "language": "java",
    },
    {
        "id": "junit5",
        "library": "junit-framework",
        "query": "assertions parameterized test lifecycle extensions",
        "tests_aspect": "Java, GitHub search (junit.org docs, renamed repo)",
        "language": "java",
    },
    {
        "id": "jackson-databind",
        "library": "jackson-databind",
        "query": "ObjectMapper deserialization annotations JsonProperty",
        "tests_aspect": "Java, GitHub search (JSON processing)",
        "language": "java",
    },
    {
        "id": "guava",
        "library": "guava",
        "query": "ImmutableList cache builder multimap",
        "tests_aspect": "Java, GitHub search (Google Guava)",
        "language": "java",
    },
    {
        "id": "lombok",
        "library": "lombok",
        "query": "Getter Setter Builder Data annotation",
        "tests_aspect": "Java, GitHub search (projectlombok.org)",
        "language": "java",
    },
    {
        "id": "mockito",
        "library": "mockito",
        "query": "when thenReturn verify mock spy",
        "tests_aspect": "Java, GitHub search (mocking framework)",
        "language": "java",
    },
    {
        "id": "netty",
        "library": "netty",
        "query": "channel handler pipeline bootstrap event loop",
        "tests_aspect": "Java, GitHub search (netty.io)",
        "language": "java",
    },
    {
        "id": "quarkus",
        "library": "quarkus",
        "query": "native image CDI rest client reactive",
        "tests_aspect": "Java, GitHub search (quarkus.io docs)",
        "language": "java",
    },
    # =====================================================================
    # Category AZ: Java — More libraries (10)
    # =====================================================================
    {
        "id": "micronaut-core",
        "library": "micronaut-core",
        "query": "dependency injection HTTP client server filter",
        "tests_aspect": "Java, GitHub search (micronaut.io)",
        "language": "java",
    },
    {
        "id": "vertx",
        "library": "vert.x",
        "query": "verticle event bus HTTP server router",
        "tests_aspect": "Java, GitHub search (vertx.io)",
        "language": "java",
    },
    {
        "id": "mapstruct",
        "library": "mapstruct",
        "query": "Mapper Mapping source target expression",
        "tests_aspect": "Java, GitHub search (code generation mapper)",
        "language": "java",
    },
    {
        "id": "flyway",
        "library": "flyway",
        "query": "migration versioned repeatable baseline callback",
        "tests_aspect": "Java, GitHub search (flywaydb.org)",
        "language": "java",
    },
    {
        "id": "jooq",
        "library": "jOOQ",
        "query": "DSL select join where group by type-safe SQL",
        "tests_aspect": "Java, GitHub search (jooq.org)",
        "language": "java",
    },
    {
        "id": "reactor-core",
        "library": "reactor-core",
        "query": "Mono Flux subscribe map flatMap backpressure",
        "tests_aspect": "Java, GitHub search (Project Reactor)",
        "language": "java",
    },
    {
        "id": "okhttp",
        "library": "okhttp",
        "query": "OkHttpClient Request Response interceptor",
        "tests_aspect": "Java, GitHub search (square.github.io/okhttp)",
        "language": "java",
    },
    {
        "id": "retrofit",
        "library": "retrofit",
        "query": "interface annotation GET POST Call converter",
        "tests_aspect": "Java, GitHub search (square.github.io/retrofit)",
        "language": "java",
    },
    {
        "id": "log4j",
        "library": "logging-log4j2",
        "query": "Logger appender layout configuration pattern",
        "tests_aspect": "Java, GitHub search (Apache Log4j)",
        "language": "java",
    },
    {
        "id": "apache-kafka-java",
        "library": "kafka",
        "query": "producer consumer topic partition offset",
        "tests_aspect": "Java, GitHub search (Apache Kafka clients)",
        "language": "java",
    },
    # =====================================================================
    # Category BA: PHP — Laravel and frameworks (10)
    # =====================================================================
    {
        "id": "laravel-framework",
        "library": "framework",
        "query": "Eloquent model migration route middleware",
        "tests_aspect": "PHP, GitHub search (laravel.com docs)",
        "language": "php",
    },
    {
        "id": "symfony",
        "library": "symfony",
        "query": "controller routing service container dependency injection",
        "tests_aspect": "PHP, GitHub search (symfony.com docs)",
        "language": "php",
    },
    {
        "id": "composer",
        "library": "composer",
        "query": "require install autoload vendor lock",
        "tests_aspect": "PHP, GitHub search (getcomposer.org)",
        "language": "php",
    },
    {
        "id": "guzzle",
        "library": "guzzle",
        "query": "HTTP client request response middleware promise",
        "tests_aspect": "PHP, GitHub search (guzzlephp.org)",
        "language": "php",
    },
    {
        "id": "phpunit",
        "library": "phpunit",
        "query": "test case assertion mock data provider",
        "tests_aspect": "PHP, GitHub search (phpunit.de)",
        "language": "php",
    },
    {
        "id": "doctrine-orm",
        "library": "orm",
        "query": "entity manager repository query builder mapping",
        "tests_aspect": "PHP, GitHub search (doctrine-project.org)",
        "language": "php",
    },
    {
        "id": "monolog",
        "library": "monolog",
        "query": "logger handler formatter processor channel",
        "tests_aspect": "PHP, GitHub search (Seldaek/monolog)",
        "language": "php",
    },
    {
        "id": "slim-php",
        "library": "Slim",
        "query": "route middleware request response PSR-7",
        "tests_aspect": "PHP, GitHub search (slimframework.com)",
        "language": "php",
    },
    {
        "id": "pest-php",
        "library": "pest",
        "query": "test it expect toEqual beforeEach describe",
        "tests_aspect": "PHP, GitHub search (pestphp.com testing)",
        "language": "php",
    },
    {
        "id": "livewire",
        "library": "livewire",
        "query": "component wire:model wire:click mount render",
        "tests_aspect": "PHP, GitHub search (livewire.laravel.com)",
        "language": "php",
    },
    # =====================================================================
    # Category BB: PHP — More libraries (10)
    # =====================================================================
    {
        "id": "filament",
        "library": "filament",
        "query": "resource table form action panel builder",
        "tests_aspect": "PHP, GitHub search (filamentphp.com)",
        "language": "php",
    },
    {
        "id": "phpstan",
        "library": "phpstan",
        "query": "rule level type analysis baseline extension",
        "tests_aspect": "PHP, GitHub search (phpstan.org)",
        "language": "php",
    },
    {
        "id": "rector",
        "library": "rector",
        "query": "rule set upgrade refactor PHP version",
        "tests_aspect": "PHP, GitHub search (getrector.com)",
        "language": "php",
    },
    {
        "id": "twig",
        "library": "Twig",
        "query": "template extends block include filter macro",
        "tests_aspect": "PHP, GitHub search (twig.symfony.com)",
        "language": "php",
    },
    {
        "id": "swoole",
        "library": "swoole-src",
        "query": "coroutine server websocket process channel",
        "tests_aspect": "PHP, GitHub search (swoole.co.uk async)",
        "language": "php",
    },
    {
        "id": "yii2",
        "library": "yii2",
        "query": "ActiveRecord widget module migration RBAC",
        "tests_aspect": "PHP, GitHub search (yiiframework.com)",
        "language": "php",
    },
    {
        "id": "cakephp",
        "library": "cakephp",
        "query": "bake ORM controller plugin middleware",
        "tests_aspect": "PHP, GitHub search (cakephp.org)",
        "language": "php",
    },
    {
        "id": "inertia-laravel",
        "library": "inertia-laravel",
        "query": "Inertia render shared data lazy loading",
        "tests_aspect": "PHP, GitHub search (inertiajs.com)",
        "language": "php",
    },
    {
        "id": "spatie-permission",
        "library": "laravel-permission",
        "query": "role permission guard middleware hasRole",
        "tests_aspect": "PHP, GitHub search (spatie.be/docs)",
        "language": "php",
    },
    {
        "id": "predis",
        "library": "predis",
        "query": "client connection pipeline pub/sub cluster",
        "tests_aspect": "PHP, GitHub search (predis/predis Redis)",
        "language": "php",
    },
    # =====================================================================
    # Category BC: Ruby — Rails and ecosystem (10)
    # =====================================================================
    {
        "id": "rails",
        "library": "rails",
        "query": "ActiveRecord controller migration route model",
        "tests_aspect": "Ruby, GitHub search (rubyonrails.org)",
        "language": "ruby",
    },
    {
        "id": "sinatra",
        "library": "sinatra",
        "query": "get post route params template helper",
        "tests_aspect": "Ruby, GitHub search (sinatrarb.com)",
        "language": "ruby",
    },
    {
        "id": "rspec",
        "library": "rspec",
        "query": "describe it expect to subject let before",
        "tests_aspect": "Ruby, GitHub search (rspec.info)",
        "language": "ruby",
    },
    {
        "id": "devise",
        "library": "devise",
        "query": "authentication token confirmable recoverable lockable",
        "tests_aspect": "Ruby, GitHub search (auth gem)",
        "language": "ruby",
    },
    {
        "id": "sidekiq",
        "library": "sidekiq",
        "query": "worker perform_async queue retry concurrency",
        "tests_aspect": "Ruby, GitHub search (sidekiq.org background jobs)",
        "language": "ruby",
    },
    {
        "id": "nokogiri",
        "library": "nokogiri",
        "query": "parse HTML XML CSS selector xpath",
        "tests_aspect": "Ruby, GitHub search (nokogiri.org)",
        "language": "ruby",
    },
    {
        "id": "rubocop",
        "library": "rubocop",
        "query": "cop rule offense disable enable configuration",
        "tests_aspect": "Ruby, GitHub search (rubocop.org linter)",
        "language": "ruby",
    },
    {
        "id": "puma",
        "library": "puma",
        "query": "server threads workers bind configuration",
        "tests_aspect": "Ruby, GitHub search (puma.io web server)",
        "language": "ruby",
    },
    {
        "id": "faraday",
        "library": "faraday",
        "query": "connection request response middleware adapter",
        "tests_aspect": "Ruby, GitHub search (HTTP client)",
        "language": "ruby",
    },
    {
        "id": "hanami",
        "library": "hanami",
        "query": "action view slice ROM repository",
        "tests_aspect": "Ruby, GitHub search (hanamirb.org)",
        "language": "ruby",
    },
    # =====================================================================
    # Category BD: C# / .NET (10)
    # =====================================================================
    {
        "id": "aspnet-core",
        "library": "aspnetcore",
        "query": "middleware controller routing dependency injection",
        "tests_aspect": "C#, GitHub search (learn.microsoft.com)",
        "language": "csharp",
    },
    {
        "id": "efcore",
        "library": "efcore",
        "query": "DbContext migration entity relationship LINQ",
        "tests_aspect": "C#, GitHub search (Entity Framework Core)",
        "language": "csharp",
    },
    {
        "id": "xunit",
        "library": "xunit",
        "query": "Fact Theory InlineData Assert collection fixture",
        "tests_aspect": "C#, GitHub search (xunit.net)",
        "language": "csharp",
    },
    {
        "id": "serilog",
        "library": "serilog",
        "query": "Log sink enricher structured logging template",
        "tests_aspect": "C#, GitHub search (serilog.net)",
        "language": "csharp",
    },
    {
        "id": "dapper",
        "library": "Dapper",
        "query": "Query Execute SqlMapper multi mapping parameterized",
        "tests_aspect": "C#, GitHub search (micro-ORM)",
        "language": "csharp",
    },
    {
        "id": "automapper",
        "library": "AutoMapper",
        "query": "CreateMap ForMember Profile configuration mapping",
        "tests_aspect": "C#, GitHub search (automapper.org)",
        "language": "csharp",
    },
    {
        "id": "mediatr",
        "library": "MediatR",
        "query": "IRequest IRequestHandler Send notification pipeline",
        "tests_aspect": "C#, GitHub search (mediator pattern CQRS)",
        "language": "csharp",
    },
    {
        "id": "fluentvalidation",
        "library": "FluentValidation",
        "query": "RuleFor Must NotEmpty validator AbstractValidator",
        "tests_aspect": "C#, GitHub search (fluentvalidation.net)",
        "language": "csharp",
    },
    {
        "id": "polly-dotnet",
        "library": "Polly",
        "query": "retry circuit breaker timeout policy resilience",
        "tests_aspect": "C#, GitHub search (thepollyproject.org)",
        "language": "csharp",
    },
    {
        "id": "signalr",
        "library": "SignalR",
        "query": "hub connection group send client invoke",
        "tests_aspect": "C#, GitHub search (real-time comm)",
        "language": "csharp",
    },
    # =====================================================================
    # Category BE: C# / .NET — More libraries (10)
    # =====================================================================
    {
        "id": "avalonia",
        "library": "Avalonia",
        "query": "Window control XAML binding style ViewModel",
        "tests_aspect": "C#, GitHub search (avaloniaui.net)",
        "language": "csharp",
    },
    {
        "id": "blazor",
        "library": "aspnetcore",
        "query": "Blazor component render StateHasChanged parameter",
        "tests_aspect": "C#, GitHub search (Blazor framework)",
        "language": "csharp",
    },
    {
        "id": "hangfire",
        "library": "Hangfire",
        "query": "BackgroundJob Enqueue Schedule Recurring dashboard",
        "tests_aspect": "C#, GitHub search (hangfire.io job scheduler)",
        "language": "csharp",
    },
    {
        "id": "masstransit",
        "library": "MassTransit",
        "query": "consumer producer bus endpoint saga",
        "tests_aspect": "C#, GitHub search (masstransit.io messaging)",
        "language": "csharp",
    },
    {
        "id": "spectre-console",
        "library": "spectre.console",
        "query": "AnsiConsole Table Prompt Markup Status Progress",
        "tests_aspect": "C#, GitHub search (spectreconsole.net)",
        "language": "csharp",
    },
    {
        "id": "benchmark-dotnet",
        "library": "BenchmarkDotNet",
        "query": "Benchmark GlobalSetup IterationSetup Job column",
        "tests_aspect": "C#, GitHub search (benchmarkdotnet.org)",
        "language": "csharp",
    },
    {
        "id": "refit-dotnet",
        "library": "refit",
        "query": "interface Get Post Body Headers RestService",
        "tests_aspect": "C#, GitHub search (reactiveui.github.io/refit)",
        "language": "csharp",
    },
    {
        "id": "fast-endpoints",
        "library": "FastEndpoints",
        "query": "Endpoint HandleAsync Validator Configure Response",
        "tests_aspect": "C#, GitHub search (fast-endpoints.com)",
        "language": "csharp",
    },
    {
        "id": "nunit",
        "library": "nunit",
        "query": "TestFixture Test Assert That Is Constraint",
        "tests_aspect": "C#, GitHub search (nunit.org testing)",
        "language": "csharp",
    },
    {
        "id": "orleans",
        "library": "orleans",
        "query": "grain silo client cluster persistence timer",
        "tests_aspect": "C#, GitHub search (learn.microsoft.com/dotnet/orleans)",
        "language": "csharp",
    },
    # =====================================================================
    # Category BF: Swift / iOS (10)
    # =====================================================================
    {
        "id": "alamofire",
        "library": "Alamofire",
        "query": "Session request response upload download interceptor",
        "tests_aspect": "Swift, GitHub search (alamofire.github.io)",
        "language": "swift",
    },
    {
        "id": "vapor",
        "library": "vapor",
        "query": "route controller middleware Fluent model migration",
        "tests_aspect": "Swift, GitHub search (vapor.codes server)",
        "language": "swift",
    },
    {
        "id": "snapkit",
        "library": "SnapKit",
        "query": "makeConstraints equalTo offset multipliedBy snp",
        "tests_aspect": "Swift, GitHub search (Auto Layout DSL)",
        "language": "swift",
    },
    {
        "id": "kingfisher",
        "library": "Kingfisher",
        "query": "image download cache placeholder processor",
        "tests_aspect": "Swift, GitHub search (image downloading)",
        "language": "swift",
    },
    {
        "id": "rxswift",
        "library": "RxSwift",
        "query": "Observable subscribe DisposeBag map flatMap",
        "tests_aspect": "Swift, GitHub search (ReactiveX)",
        "language": "swift",
    },
    {
        "id": "moya",
        "library": "Moya",
        "query": "TargetType provider endpoint MoyaProvider",
        "tests_aspect": "Swift, GitHub search (networking abstraction)",
        "language": "swift",
    },
    {
        "id": "realm-swift",
        "library": "realm-swift",
        "query": "Object Realm write delete observe Results",
        "tests_aspect": "Swift, GitHub search (realm.io mobile DB)",
        "language": "swift",
    },
    {
        "id": "swiftyjson",
        "library": "SwiftyJSON",
        "query": "JSON parse subscript rawValue stringValue array",
        "tests_aspect": "Swift, GitHub search (JSON parsing)",
        "language": "swift",
    },
    {
        "id": "combine-swift",
        "library": "OpenCombine",
        "query": "Publisher Subscriber sink receive completion Combine",
        "tests_aspect": "Swift, GitHub search (OpenCombine open-source reimplementation)",
        "language": "swift",
    },
    {
        "id": "swift-composable",
        "library": "swift-composable-architecture",
        "query": "Reducer Store Effect Action State Environment",
        "tests_aspect": "Swift, GitHub search (TCA by pointfreeco)",
        "language": "swift",
    },
    # =====================================================================
    # Category BG: Kotlin (10)
    # =====================================================================
    {
        "id": "ktor",
        "library": "ktor",
        "query": "routing install plugin client server engine",
        "tests_aspect": "Kotlin, GitHub search (ktor.io)",
        "language": "kotlin",
    },
    {
        "id": "exposed",
        "library": "Exposed",
        "query": "Table Column transaction select insert update",
        "tests_aspect": "Kotlin, GitHub search (JetBrains SQL)",
        "language": "kotlin",
    },
    {
        "id": "koin",
        "library": "koin",
        "query": "module single factory viewModel inject",
        "tests_aspect": "Kotlin, GitHub search (insert-koin.io DI)",
        "language": "kotlin",
    },
    {
        "id": "coroutines",
        "library": "kotlinx.coroutines",
        "query": "launch async await flow suspend scope",
        "tests_aspect": "Kotlin, GitHub search (KotlinX Coroutines)",
        "language": "kotlin",
    },
    {
        "id": "compose-multiplatform",
        "library": "compose-multiplatform",
        "query": "Composable remember mutableStateOf Column Row",
        "tests_aspect": "Kotlin, GitHub search (compose-multiplatform)",
        "language": "kotlin",
    },
    {
        "id": "arrow-kt",
        "library": "arrow",
        "query": "Either Option raise typed errors effect",
        "tests_aspect": "Kotlin, GitHub search (arrow-kt.io FP)",
        "language": "kotlin",
    },
    {
        "id": "kotest",
        "library": "kotest",
        "query": "StringSpec shouldBe property test forAll describe",
        "tests_aspect": "Kotlin, GitHub search (kotest.io testing)",
        "language": "kotlin",
    },
    {
        "id": "mockk",
        "library": "mockk",
        "query": "every returns verify slot capture coEvery",
        "tests_aspect": "Kotlin, GitHub search (mockk.io mocking)",
        "language": "kotlin",
    },
    {
        "id": "serialization",
        "library": "kotlinx.serialization",
        "query": "Serializable Json encode decode SerialName",
        "tests_aspect": "Kotlin, GitHub search (KotlinX Serialization)",
        "language": "kotlin",
    },
    {
        "id": "detekt",
        "library": "detekt",
        "query": "rule configuration report static analysis custom",
        "tests_aspect": "Kotlin, GitHub search (detekt.dev linter)",
        "language": "kotlin",
    },
    # =====================================================================
    # Category BH: Dart / Flutter (10)
    # =====================================================================
    {
        "id": "flutter",
        "library": "flutter",
        "query": "Widget StatefulWidget build setState MaterialApp",
        "tests_aspect": "Dart, GitHub search (flutter.dev)",
        "language": "dart",
    },
    {
        "id": "dio-dart",
        "library": "dio",
        "query": "Dio get post options interceptor FormData",
        "tests_aspect": "Dart, GitHub search (HTTP client)",
        "language": "dart",
    },
    {
        "id": "riverpod",
        "library": "riverpod",
        "query": "Provider ref watch read notifier state",
        "tests_aspect": "Dart, GitHub search (riverpod.dev)",
        "language": "dart",
    },
    {
        "id": "bloc-dart",
        "library": "bloc",
        "query": "Bloc Cubit emit state BlocProvider BlocBuilder",
        "tests_aspect": "Dart, GitHub search (bloclibrary.dev)",
        "language": "dart",
    },
    {
        "id": "getx",
        "library": "getx",
        "query": "GetMaterialApp controller binding route Obx",
        "tests_aspect": "Dart, GitHub search (GetX state management)",
        "language": "dart",
    },
    {
        "id": "hive-dart",
        "library": "hive",
        "query": "box put get delete adapter TypeAdapter",
        "tests_aspect": "Dart, GitHub search (lightweight KV store)",
        "language": "dart",
    },
    {
        "id": "go-router",
        "library": "go_router",
        "query": "GoRouter GoRoute redirect guard ShellRoute",
        "tests_aspect": "Dart, GitHub search (Flutter routing)",
        "language": "dart",
    },
    {
        "id": "freezed",
        "library": "freezed",
        "query": "Freezed union sealed class copyWith fromJson",
        "tests_aspect": "Dart, GitHub search (code gen immutable)",
        "language": "dart",
    },
    {
        "id": "provider-dart",
        "library": "provider",
        "query": "ChangeNotifierProvider Consumer watch read create",
        "tests_aspect": "Dart, GitHub search (simple state mgmt)",
        "language": "dart",
    },
    {
        "id": "flame",
        "library": "flame",
        "query": "FlameGame Component SpriteComponent GameWidget",
        "tests_aspect": "Dart, GitHub search (flame-engine.org game)",
        "language": "dart",
    },
    # =====================================================================
    # Category BI: Elixir (10)
    # =====================================================================
    {
        "id": "phoenix",
        "library": "phoenix",
        "query": "router controller channel endpoint plug",
        "tests_aspect": "Elixir, GitHub search (phoenixframework.org)",
        "language": "elixir",
    },
    {
        "id": "ecto",
        "library": "ecto",
        "query": "Repo schema changeset query migration",
        "tests_aspect": "Elixir, GitHub search (hexdocs.pm/ecto)",
        "language": "elixir",
    },
    {
        "id": "phoenix-liveview",
        "library": "phoenix_live_view",
        "query": "mount handle_event render assign socket",
        "tests_aspect": "Elixir, GitHub search (Phoenix LiveView)",
        "language": "elixir",
    },
    {
        "id": "absinthe",
        "library": "absinthe",
        "query": "query mutation field resolve object type",
        "tests_aspect": "Elixir, GitHub search (GraphQL toolkit)",
        "language": "elixir",
    },
    {
        "id": "oban",
        "library": "oban",
        "query": "worker perform queue schedule cron plugin",
        "tests_aspect": "Elixir, GitHub search (getoban.pro jobs)",
        "language": "elixir",
    },
    {
        "id": "broadway",
        "library": "broadway",
        "query": "producer processor batcher handle_message",
        "tests_aspect": "Elixir, GitHub search (data pipeline)",
        "language": "elixir",
    },
    {
        "id": "nx-elixir",
        "library": "nx",
        "query": "tensor defn grad backend serving",
        "tests_aspect": "Elixir, GitHub search (numerical Elixir)",
        "language": "elixir",
    },
    {
        "id": "plug",
        "library": "plug",
        "query": "conn Router call init pipeline",
        "tests_aspect": "Elixir, GitHub search (elixir-plug adapter)",
        "language": "elixir",
    },
    {
        "id": "ex-unit",
        "library": "elixir",
        "query": "ExUnit test assert describe setup callback",
        "tests_aspect": "Elixir, GitHub search (elixir testing)",
        "language": "elixir",
    },
    {
        "id": "nerves",
        "library": "nerves",
        "query": "firmware target mix deploy build system",
        "tests_aspect": "Elixir, GitHub search (nerves-project.org IoT)",
        "language": "elixir",
    },
    # =====================================================================
    # Category BJ: Scala (10)
    # =====================================================================
    {
        "id": "akka",
        "library": "akka",
        "query": "Actor ActorSystem message receive behavior",
        "tests_aspect": "Scala, GitHub search (akka.io actor model)",
        "language": "scala",
    },
    {
        "id": "play-framework",
        "library": "playframework",
        "query": "Controller Action route template Form async",
        "tests_aspect": "Scala, GitHub search (playframework.com)",
        "language": "scala",
    },
    {
        "id": "zio",
        "library": "zio",
        "query": "ZIO Effect Layer fiber Runtime provide",
        "tests_aspect": "Scala, GitHub search (zio.dev)",
        "language": "scala",
    },
    {
        "id": "cats-effect",
        "library": "cats-effect",
        "query": "IO Resource Fiber Ref Deferred Async",
        "tests_aspect": "Scala, GitHub search (typelevel.org/cats-effect)",
        "language": "scala",
    },
    {
        "id": "http4s",
        "library": "http4s",
        "query": "HttpRoutes HttpApp client server middleware ember",
        "tests_aspect": "Scala, GitHub search (http4s.org)",
        "language": "scala",
    },
    {
        "id": "circe",
        "library": "circe",
        "query": "Decoder Encoder Json parse auto derive cursor",
        "tests_aspect": "Scala, GitHub search (circe.github.io JSON)",
        "language": "scala",
    },
    {
        "id": "slick",
        "library": "slick",
        "query": "Table TableQuery filter map result DBIO run",
        "tests_aspect": "Scala, GitHub search (scala-slick.org DB)",
        "language": "scala",
    },
    {
        "id": "scalatest",
        "library": "scalatest",
        "query": "FlatSpec should matchers assert eventually",
        "tests_aspect": "Scala, GitHub search (scalatest.org)",
        "language": "scala",
    },
    {
        "id": "sbt",
        "library": "sbt",
        "query": "build.sbt settings task libraryDependencies plugin",
        "tests_aspect": "Scala, GitHub search (scala-sbt.org build tool)",
        "language": "scala",
    },
    {
        "id": "spark-scala",
        "library": "spark",
        "query": "DataFrame SparkSession RDD transformation action",
        "tests_aspect": "Scala, GitHub search (Apache Spark)",
        "language": "scala",
    },
    # =====================================================================
    # Category BK: C / C++ (10)
    # =====================================================================
    {
        "id": "opencv-cpp",
        "library": "opencv",
        "query": "Mat imread imshow VideoCapture filter threshold",
        "tests_aspect": "C++, GitHub search (opencv.org docs)",
        "language": "cpp",
    },
    {
        "id": "qt",
        "library": "qtbase",
        "query": "QWidget signal slot layout event QApplication",
        "tests_aspect": "C++, GitHub search (doc.qt.io)",
        "language": "cpp",
    },
    {
        "id": "boost",
        "library": "boost",
        "query": "asio beast filesystem smart_ptr spirit",
        "tests_aspect": "C++, GitHub search (boost.org)",
        "language": "cpp",
    },
    {
        "id": "catch2",
        "library": "Catch2",
        "query": "TEST_CASE SECTION REQUIRE CHECK Matchers",
        "tests_aspect": "C++, GitHub search (Catch2 testing)",
        "language": "cpp",
    },
    {
        "id": "googletest",
        "library": "googletest",
        "query": "TEST TEST_F EXPECT_EQ ASSERT_TRUE mock fixture",
        "tests_aspect": "C++, GitHub search (Google Test gtest)",
        "language": "cpp",
    },
    {
        "id": "nlohmann-json",
        "library": "json",
        "query": "parse dump operator[] at get type_error",
        "tests_aspect": "C++, GitHub search (nlohmann/json)",
        "language": "cpp",
    },
    {
        "id": "fmt-lib",
        "library": "fmt",
        "query": "format print arg join compile_string",
        "tests_aspect": "C++, GitHub search (fmt.dev formatting)",
        "language": "cpp",
    },
    {
        "id": "spdlog",
        "library": "spdlog",
        "query": "logger info debug warn sink async",
        "tests_aspect": "C++, GitHub search (fast logging)",
        "language": "cpp",
    },
    {
        "id": "eigen",
        "library": "eigen",
        "query": "Matrix Vector3d transpose inverse decomposition",
        "tests_aspect": "C++, GitHub search (eigen.tuxfamily.org)",
        "language": "cpp",
    },
    {
        "id": "sfml",
        "library": "SFML",
        "query": "RenderWindow Sprite Texture Event draw",
        "tests_aspect": "C++, GitHub search (sfml-dev.org multimedia)",
        "language": "cpp",
    },
    # =====================================================================
    # Category BL: Haskell (5) + Lua (5)
    # =====================================================================
    {
        "id": "yesod",
        "library": "yesod",
        "query": "handler widget route template foundation",
        "tests_aspect": "Haskell, GitHub search (yesodweb.com)",
        "language": "haskell",
    },
    {
        "id": "servant",
        "library": "servant",
        "query": "API type Server Client handler endpoint",
        "tests_aspect": "Haskell, GitHub search (docs.servant.dev)",
        "language": "haskell",
    },
    {
        "id": "aeson",
        "library": "aeson",
        "query": "FromJSON ToJSON Value encode decode parseJSON",
        "tests_aspect": "Haskell, GitHub search (JSON parsing)",
        "language": "haskell",
    },
    {
        "id": "stack-haskell",
        "library": "stack",
        "query": "build resolver package extra-deps ghc",
        "tests_aspect": "Haskell, GitHub search (haskellstack.org)",
        "language": "haskell",
    },
    {
        "id": "lens-haskell",
        "library": "lens",
        "query": "view set over makeLenses traversal prism",
        "tests_aspect": "Haskell, GitHub search (lens library optics)",
        "language": "haskell",
    },
    {
        "id": "love2d",
        "library": "love",
        "query": "draw update load keypressed graphics audio",
        "tests_aspect": "Lua, GitHub search (love2d.org game engine)",
        "language": "lua",
    },
    {
        "id": "openresty",
        "library": "openresty",
        "query": "ngx_lua content_by_lua access cosocket timer",
        "tests_aspect": "Lua, GitHub search (openresty.org)",
        "language": "lua",
    },
    {
        "id": "luarocks",
        "library": "luarocks",
        "query": "install rockspec search config path",
        "tests_aspect": "Lua, GitHub search (luarocks.org package mgr)",
        "language": "lua",
    },
    {
        "id": "lapis-lua",
        "library": "lapis",
        "query": "action route model migration respond_to",
        "tests_aspect": "Lua, GitHub search (leafo.net/lapis web)",
        "language": "lua",
    },
    {
        "id": "hammerspoon",
        "library": "hammerspoon",
        "query": "hotkey window layout application watcher hs",
        "tests_aspect": "Lua, GitHub search (hammerspoon.org macOS)",
        "language": "lua",
    },
    # =====================================================================
    # Category BM: R (5) + Julia (5)
    # =====================================================================
    {
        "id": "ggplot2",
        "library": "ggplot2",
        "query": "aes geom_point geom_bar facet_wrap theme",
        "tests_aspect": "R, GitHub search (ggplot2.tidyverse.org)",
        "language": "r",
    },
    {
        "id": "dplyr",
        "library": "dplyr",
        "query": "filter select mutate group_by summarise pipe",
        "tests_aspect": "R, GitHub search (dplyr.tidyverse.org)",
        "language": "r",
    },
    {
        "id": "shiny-r",
        "library": "shiny",
        "query": "server ui renderPlot reactive observe input",
        "tests_aspect": "R, GitHub search (shiny.posit.co web apps)",
        "language": "r",
    },
    {
        "id": "tidyverse",
        "library": "tidyverse",
        "query": "tibble pipe tidy data readr purrr",
        "tests_aspect": "R, GitHub search (tidyverse.org)",
        "language": "r",
    },
    {
        "id": "data-table-r",
        "library": "data.table",
        "query": "DT fread fwrite setkey merge .SD .N",
        "tests_aspect": "R, GitHub search (rdatatable.gitlab.io)",
        "language": "r",
    },
    {
        "id": "flux-jl",
        "library": "Flux.jl",
        "query": "Chain Dense train! gradient params loss",
        "tests_aspect": "Julia, GitHub search (fluxml.ai ML)",
        "language": "julia",
    },
    {
        "id": "differentialequations-jl",
        "library": "DifferentialEquations.jl",
        "query": "ODEProblem solve Tsit5 callback plot",
        "tests_aspect": "Julia, GitHub search (diffeq.sciml.ai)",
        "language": "julia",
    },
    {
        "id": "makie-jl",
        "library": "Makie.jl",
        "query": "Figure Axis scatter lines heatmap theme",
        "tests_aspect": "Julia, GitHub search (docs.makie.org plotting)",
        "language": "julia",
    },
    {
        "id": "dataframes-jl",
        "library": "DataFrames.jl",
        "query": "DataFrame select filter transform groupby combine",
        "tests_aspect": "Julia, GitHub search (dataframes.juliadata.org)",
        "language": "julia",
    },
    {
        "id": "pluto-jl",
        "library": "Pluto.jl",
        "query": "notebook cell reactive bind slider PlutoUI",
        "tests_aspect": "Julia, GitHub search (plutojl.org)",
        "language": "julia",
    },
    # =====================================================================
    # Category BN: Zig (5) + Nim (5)
    # =====================================================================
    {
        "id": "zig-std",
        "library": "zig",
        "query": "allocator ArrayList HashMap comptime error",
        "tests_aspect": "Zig, GitHub search (ziglang.org/documentation)",
        "language": "zig",
    },
    {
        "id": "zls",
        "library": "zls",
        "query": "language server completion diagnostics format",
        "tests_aspect": "Zig, GitHub search (Zig Language Server)",
        "language": "zig",
    },
    {
        "id": "mach-zig",
        "library": "mach",
        "query": "engine platform app module gpu graphics",
        "tests_aspect": "Zig, GitHub search (machengine.org)",
        "language": "zig",
    },
    {
        "id": "capy-zig",
        "library": "capy",
        "query": "window widget button label layout event",
        "tests_aspect": "Zig, GitHub search (capy cross-platform GUI)",
        "language": "zig",
    },
    {
        "id": "httpz-zig",
        "library": "http.zig",
        "query": "server request response router handler header",
        "tests_aspect": "Zig, GitHub search (HTTP server lib)",
        "language": "zig",
    },
    {
        "id": "nim-lang",
        "library": "Nim",
        "query": "proc type template macro iterator gc",
        "tests_aspect": "Nim, GitHub search (nim-lang.org)",
        "language": "nim",
    },
    {
        "id": "prologue-nim",
        "library": "prologue",
        "query": "server route middleware context response",
        "tests_aspect": "Nim, GitHub search (web framework)",
        "language": "nim",
    },
    {
        "id": "nimble",
        "library": "nimble",
        "query": "install package task requires config",
        "tests_aspect": "Nim, GitHub search (package manager)",
        "language": "nim",
    },
    {
        "id": "karax",
        "library": "karax",
        "query": "buildHtml tdiv span button router VNode",
        "tests_aspect": "Nim, GitHub search (SPA framework)",
        "language": "nim",
    },
    {
        "id": "norm-nim",
        "library": "norm",
        "query": "Model createTables insert select update delete",
        "tests_aspect": "Nim, GitHub search (ORM for Nim)",
        "language": "nim",
    },
    # =====================================================================
    # Category BO: Clojure (5) + Perl (5)
    # =====================================================================
    {
        "id": "ring-clj",
        "library": "ring",
        "query": "handler middleware request response wrap",
        "tests_aspect": "Clojure, GitHub search (ring-clojure HTTP)",
        "language": "clojure",
    },
    {
        "id": "compojure",
        "library": "compojure",
        "query": "defroutes GET POST route context wrap",
        "tests_aspect": "Clojure, GitHub search (routing library)",
        "language": "clojure",
    },
    {
        "id": "reagent",
        "library": "reagent",
        "query": "atom render component hiccup ratom cursor",
        "tests_aspect": "Clojure, GitHub search (ClojureScript React)",
        "language": "clojure",
    },
    {
        "id": "re-frame",
        "library": "re-frame",
        "query": "reg-event-db reg-sub dispatch subscribe fx",
        "tests_aspect": "Clojure, GitHub search (re-frame SPA)",
        "language": "clojure",
    },
    {
        "id": "leiningen",
        "library": "leiningen",
        "query": "project.clj dependencies plugin profile uberjar",
        "tests_aspect": "Clojure, GitHub search (leiningen.org build)",
        "language": "clojure",
    },
    {
        "id": "mojolicious",
        "library": "mojo",
        "query": "route controller template helper websocket",
        "tests_aspect": "Perl, GitHub search (mojolicious.org)",
        "language": "perl",
    },
    {
        "id": "dancer2",
        "library": "Dancer2",
        "query": "get post route template session hook",
        "tests_aspect": "Perl, GitHub search (perldancer.org)",
        "language": "perl",
    },
    {
        "id": "moose",
        "library": "Moose",
        "query": "has accessor attribute role extends method",
        "tests_aspect": "Perl, GitHub search (metacpan OOP)",
        "language": "perl",
    },
    {
        "id": "dbi-perl",
        "library": "DBI",
        "query": "connect prepare execute fetch selectall bind",
        "tests_aspect": "Perl, GitHub search (database interface)",
        "language": "perl",
    },
    {
        "id": "plack",
        "library": "Plack",
        "query": "PSGI app builder middleware handler response",
        "tests_aspect": "Perl, GitHub search (plackperl.org)",
        "language": "perl",
    },
    # =====================================================================
    # Category BP: Erlang (5) + OCaml (5)
    # =====================================================================
    {
        "id": "cowboy",
        "library": "cowboy",
        "query": "handler route dispatch websocket stream",
        "tests_aspect": "Erlang, GitHub search (ninenines.eu/cowboy)",
        "language": "erlang",
    },
    {
        "id": "rebar3",
        "library": "rebar3",
        "query": "compile release plugin provider deps app",
        "tests_aspect": "Erlang, GitHub search (rebar3.org build)",
        "language": "erlang",
    },
    {
        "id": "gen-server",
        "library": "otp",
        "query": "gen_server handle_call handle_cast supervisor",
        "tests_aspect": "Erlang, GitHub search (erlang.org/doc OTP)",
        "language": "erlang",
    },
    {
        "id": "rabbitmq-erlang",
        "library": "rabbitmq-server",
        "query": "queue exchange binding consumer publish channel",
        "tests_aspect": "Erlang, GitHub search (rabbitmq.com)",
        "language": "erlang",
    },
    {
        "id": "ejabberd",
        "library": "ejabberd",
        "query": "module hook XMPP config acl user",
        "tests_aspect": "Erlang, GitHub search (ejabberd.im XMPP)",
        "language": "erlang",
    },
    {
        "id": "ocaml-base",
        "library": "base",
        "query": "List Map Set Option Result String sexp",
        "tests_aspect": "OCaml, GitHub search (Jane Street Base)",
        "language": "ocaml",
    },
    {
        "id": "dream",
        "library": "dream",
        "query": "handler route middleware form session html",
        "tests_aspect": "OCaml, GitHub search (aantron.github.io/dream)",
        "language": "ocaml",
    },
    {
        "id": "dune",
        "library": "dune",
        "query": "build library executable rule stanza config",
        "tests_aspect": "OCaml, GitHub search (dune.build tool)",
        "language": "ocaml",
    },
    {
        "id": "lwt-ocaml",
        "library": "lwt",
        "query": "bind return Lwt_main.run promise callback",
        "tests_aspect": "OCaml, GitHub search (concurrent programming)",
        "language": "ocaml",
    },
    {
        "id": "opam",
        "library": "opam",
        "query": "install switch pin repository package formula",
        "tests_aspect": "OCaml, GitHub search (opam.ocaml.org pkg mgr)",
        "language": "ocaml",
    },
    # =====================================================================
    # Category BQ: DevOps / Infrastructure tools (10)
    # =====================================================================
    {
        "id": "terraform",
        "library": "terraform",
        "query": "provider resource module variable output plan",
        "tests_aspect": "Go, GitHub search (terraform.io)",
        "language": "go",
    },
    {
        "id": "ansible-devops",
        "library": "ansible",
        "query": "playbook task module role handler inventory",
        "tests_aspect": "Python, GitHub search (docs.ansible.com)",
        "language": "python",
    },
    {
        "id": "vault",
        "library": "vault",
        "query": "secret engine policy auth token mount",
        "tests_aspect": "Go, GitHub search (vaultproject.io)",
        "language": "go",
    },
    {
        "id": "consul",
        "library": "consul",
        "query": "service discovery catalog health KV agent",
        "tests_aspect": "Go, GitHub search (consul.io)",
        "language": "go",
    },
    {
        "id": "prometheus-go",
        "library": "prometheus",
        "query": "Counter Gauge Histogram Summary Registry",
        "tests_aspect": "Go, GitHub search (prometheus.io)",
        "language": "go",
    },
    {
        "id": "traefik",
        "library": "traefik",
        "query": "router entrypoint middleware provider service",
        "tests_aspect": "Go, GitHub search (traefik.io proxy)",
        "language": "go",
    },
    {
        "id": "caddy-go",
        "library": "caddy",
        "query": "Caddyfile reverse_proxy tls file_server handle",
        "tests_aspect": "Go, GitHub search (caddyserver.com)",
        "language": "go",
    },
    {
        "id": "envoy-proxy",
        "library": "envoy",
        "query": "listener filter cluster route upstream",
        "tests_aspect": "C++, GitHub search (envoyproxy.io)",
        "language": "cpp",
    },
    {
        "id": "pulumi-go",
        "library": "pulumi",
        "query": "resource stack config output provider Component",
        "tests_aspect": "Go, GitHub search (pulumi.com IaC)",
        "language": "go",
    },
    {
        "id": "grafana",
        "library": "grafana",
        "query": "dashboard panel query datasource alert plugin",
        "tests_aspect": "Go, GitHub search (grafana.com/docs)",
        "language": "go",
    },
    # =====================================================================
    # Category BR: Cross-platform CLI / Build tools (10)
    # =====================================================================
    {
        "id": "cmake",
        "library": "cmake",
        "query": "add_executable target_link_libraries find_package",
        "tests_aspect": "C++, GitHub search (cmake.org docs)",
        "language": "cpp",
    },
    {
        "id": "meson",
        "library": "meson",
        "query": "project executable dependency install subdir",
        "tests_aspect": "Python, GitHub search (mesonbuild.com)",
        "language": "python",
    },
    {
        "id": "bazel",
        "library": "bazel",
        "query": "BUILD rule target label workspace load",
        "tests_aspect": "Java, GitHub search (bazel.build)",
        "language": "java",
    },
    {
        "id": "gradle",
        "library": "gradle",
        "query": "build.gradle plugin task dependency configuration",
        "tests_aspect": "Java, GitHub search (docs.gradle.org)",
        "language": "java",
    },
    {
        "id": "maven",
        "library": "maven",
        "query": "pom.xml dependency plugin lifecycle phase",
        "tests_aspect": "Java, GitHub search (maven.apache.org)",
        "language": "java",
    },
    {
        "id": "just-runner",
        "library": "just",
        "query": "recipe variable setting alias default shebang",
        "tests_aspect": "Rust, GitHub search (just.systems)",
        "language": "rust",
    },
    {
        "id": "taskfile",
        "library": "task",
        "query": "Taskfile task command deps vars sources",
        "tests_aspect": "Go, GitHub search (taskfile.dev)",
        "language": "go",
    },
    {
        "id": "mise-runner",
        "library": "mise",
        "query": "tool install plugin task environment version",
        "tests_aspect": "Rust, GitHub search (mise.jdx.dev)",
        "language": "rust",
    },
    {
        "id": "nix-pkg",
        "library": "nix",
        "query": "derivation flake shell overlay package",
        "tests_aspect": "C++, GitHub search (nixos.org/manual/nix)",
        "language": "cpp",
    },
    {
        "id": "pixi",
        "library": "pixi",
        "query": "install add task project platform feature run",
        "tests_aspect": "Rust, GitHub search (pixi.sh conda tool)",
        "language": "rust",
    },
    # =====================================================================
    # Category BS: Web3 / Blockchain (10)
    # =====================================================================
    {
        "id": "ethers-js",
        "library": "ethers",
        "query": "Provider Signer Contract Wallet Transaction",
        "tests_aspect": "npm, ethers (Ethereum interaction)",
    },
    {
        "id": "web3-js",
        "library": "web3",
        "query": "eth Contract sendTransaction accounts ABI",
        "tests_aspect": "npm, web3 (Ethereum JavaScript API)",
    },
    {
        "id": "hardhat",
        "library": "hardhat",
        "query": "task compile deploy test network config",
        "tests_aspect": "npm, hardhat (Ethereum dev environment)",
    },
    {
        "id": "foundry",
        "library": "foundry",
        "query": "forge test script anvil cast deploy",
        "tests_aspect": "Rust, GitHub search (getfoundry.sh)",
        "language": "rust",
    },
    {
        "id": "anchor-solana",
        "library": "anchor",
        "query": "program instruction account context derive",
        "tests_aspect": "Rust, GitHub search (anchor-lang.com Solana)",
        "language": "rust",
    },
    {
        "id": "wagmi",
        "library": "wagmi",
        "query": "useAccount useConnect useBalance hook config",
        "tests_aspect": "npm, wagmi (React hooks Ethereum)",
    },
    {
        "id": "viem",
        "library": "viem",
        "query": "createPublicClient readContract writeContract chain",
        "tests_aspect": "npm, viem (TypeScript Ethereum interface)",
    },
    {
        "id": "openzeppelin",
        "library": "@openzeppelin/contracts",
        "query": "ERC20 ERC721 Ownable AccessControl SafeMath",
        "tests_aspect": "npm, OpenZeppelin (Solidity contracts)",
    },
    {
        "id": "thirdweb",
        "library": "thirdweb",
        "query": "ThirdwebProvider useContract useNFTs SDK deploy",
        "tests_aspect": "npm, thirdweb (web3 dev platform)",
    },
    {
        "id": "rainbowkit",
        "library": "@rainbow-me/rainbowkit",
        "query": "ConnectButton getDefaultConfig WalletList chain",
        "tests_aspect": "npm, RainbowKit (wallet UI)",
    },
    # =====================================================================
    # Category BT: Data science / ML libraries — non-Python (10)
    # =====================================================================
    {
        "id": "deedle",
        "library": "Deedle",
        "query": "Frame Series key value groupBy aggregate",
        "tests_aspect": "C#/F#, GitHub search (F#/C# data analysis)",
        "language": "csharp",
    },
    {
        "id": "gonum",
        "library": "gonum",
        "query": "mat Dense vector stat plot optimize",
        "tests_aspect": "Go, GitHub search (gonum.org numerical)",
        "language": "go",
    },
    {
        "id": "dplyr-ruby",
        "library": "rover",
        "query": "DataFrame read_csv filter sort head types",
        "tests_aspect": "Ruby, GitHub search (ankane/rover DataFrame)",
        "language": "ruby",
    },
    {
        "id": "smile-java",
        "library": "smile",
        "query": "classification regression clustering DataFrame",
        "tests_aspect": "Java, GitHub search (haifengl.github.io/smile)",
        "language": "java",
    },
    {
        "id": "tensorflow-swift",
        "library": "swift-numerics",
        "query": "Complex Real ElementaryFunctions log exp sqrt",
        "tests_aspect": "Swift, GitHub search (apple/swift-numerics)",
        "language": "swift",
    },
    {
        "id": "kmath",
        "library": "kmath",
        "query": "algebra structure ND buffer space operation",
        "tests_aspect": "Kotlin, GitHub search (KMath multiplatform)",
        "language": "kotlin",
    },
    {
        "id": "tablecloth",
        "library": "tablecloth",
        "query": "dataset column filter group-by aggregate",
        "tests_aspect": "Clojure, GitHub search (scicloj data science)",
        "language": "clojure",
    },
    {
        "id": "halide",
        "library": "Halide",
        "query": "Func Var Buffer schedule vectorize parallel",
        "tests_aspect": "C++, GitHub search (halide-lang.org imaging)",
        "language": "cpp",
    },
    {
        "id": "shark-ml",
        "library": "shark",
        "query": "SVM neural network RBF optimization trainer",
        "tests_aspect": "C++, GitHub search (Shark-ML library)",
        "language": "cpp",
    },
    {
        "id": "scikit-learn-go",
        "library": "gorgonia",
        "query": "tensor graph node ExprGraph Let Must",
        "tests_aspect": "Go, GitHub search (gorgonia.org ML)",
        "language": "go",
    },
    # =====================================================================
    # Category BU: Mobile — React Native / KMP / misc (10)
    # =====================================================================
    {
        "id": "react-navigation",
        "library": "@react-navigation/native",
        "query": "NavigationContainer Stack Screen navigate Tab",
        "tests_aspect": "npm, React Navigation (RN routing)",
    },
    {
        "id": "expo-mobile",
        "library": "expo",
        "query": "router config plugin prebuild eas build",
        "tests_aspect": "npm, expo (React Native DX platform)",
    },
    {
        "id": "react-native-reanimated",
        "library": "react-native-reanimated",
        "query": "useSharedValue useAnimatedStyle withSpring worklet",
        "tests_aspect": "npm, Reanimated (RN animation)",
    },
    {
        "id": "kotlin-multiplatform",
        "library": "compose-multiplatform-core",
        "query": "expect actual commonMain iosMain androidMain",
        "tests_aspect": "Kotlin, GitHub search (JetBrains compose-multiplatform-core)",
        "language": "kotlin",
    },
    {
        "id": "swift-package",
        "library": "swift-package-manager",
        "query": "Package dependencies target product executable",
        "tests_aspect": "Swift, GitHub search (Swift PM)",
        "language": "swift",
    },
    {
        "id": "nativewind",
        "library": "nativewind",
        "query": "className styled tailwind.config StyledComponent",
        "tests_aspect": "npm, NativeWind (TailwindCSS for RN)",
    },
    {
        "id": "mmkv",
        "library": "react-native-mmkv",
        "query": "MMKV useMMKVStorage getString setString",
        "tests_aspect": "npm, MMKV (fast KV storage for RN)",
    },
    {
        "id": "gluestack-ui",
        "library": "@gluestack-ui/themed",
        "query": "Button Text Box HStack VStack Provider",
        "tests_aspect": "npm, Gluestack UI (universal UI kit)",
    },
    {
        "id": "tamagui",
        "library": "tamagui",
        "query": "TamaguiProvider YStack XStack styled theme tokens",
        "tests_aspect": "npm, Tamagui (universal UI framework)",
    },
    {
        "id": "react-native-svg",
        "library": "react-native-svg",
        "query": "Svg Circle Rect Path G Text SvgUri",
        "tests_aspect": "npm, RN SVG (vector graphics)",
    },
    # =====================================================================
    # Category BV: Database clients — multi-language (10)
    # =====================================================================
    {
        "id": "jedis",
        "library": "jedis",
        "query": "JedisPool get set hset lpush subscribe",
        "tests_aspect": "Java, GitHub search (Redis Java client)",
        "language": "java",
    },
    {
        "id": "go-redis-client",
        "library": "go-redis",
        "query": "Client Set Get Pipeline Tx Pub Subscribe",
        "tests_aspect": "Go, GitHub search (redis.uptrace.dev)",
        "language": "go",
    },
    {
        "id": "pg-go",
        "library": "pgx",
        "query": "conn Query Exec Pool Row Scan CopyFrom",
        "tests_aspect": "Go, GitHub search (PostgreSQL driver Go)",
        "language": "go",
    },
    {
        "id": "gorm-go",
        "library": "gorm",
        "query": "Model AutoMigrate Create Find Where Preload",
        "tests_aspect": "Go, GitHub search (gorm.io ORM)",
        "language": "go",
    },
    {
        "id": "sequel-ruby",
        "library": "sequel",
        "query": "DB dataset where insert update delete migration",
        "tests_aspect": "Ruby, GitHub search (sequel.jeremyevans.net)",
        "language": "ruby",
    },
    {
        "id": "postgrex",
        "library": "postgrex",
        "query": "start_link query execute prepare_execute",
        "tests_aspect": "Elixir, GitHub search (PostgreSQL driver)",
        "language": "elixir",
    },
    {
        "id": "mybatis",
        "library": "mybatis-3",
        "query": "mapper select insert update SqlSessionFactory",
        "tests_aspect": "Java, GitHub search (mybatis.org persistence)",
        "language": "java",
    },
    {
        "id": "npgsql",
        "library": "npgsql",
        "query": "NpgsqlConnection Open ExecuteNonQuery DataReader",
        "tests_aspect": "C#, GitHub search (npgsql.org PostgreSQL)",
        "language": "csharp",
    },
    {
        "id": "rusqlite",
        "library": "rusqlite",
        "query": "Connection open execute query_row params",
        "tests_aspect": "crates.io, rusqlite (SQLite for Rust)",
    },
    {
        "id": "ent-go",
        "library": "ent",
        "query": "Schema Field Edge Create Query entc codegen",
        "tests_aspect": "Go, GitHub search (entgo.io ORM)",
        "language": "go",
    },
    # =====================================================================
    # Category BW: API / Serialization — multi-language (10)
    # =====================================================================
    {
        "id": "grpc-java",
        "library": "grpc-java",
        "query": "stub channel Server Service ManagedChannel",
        "tests_aspect": "Java, GitHub search (grpc.io Java)",
        "language": "java",
    },
    {
        "id": "grpc-go",
        "library": "grpc-go",
        "query": "Server Dial ClientConn DialOption Unary Stream",
        "tests_aspect": "Go, GitHub search (grpc.io Go)",
        "language": "go",
    },
    {
        "id": "protobuf-go",
        "library": "protobuf-go",
        "query": "proto Message Marshal Unmarshal FileOptions",
        "tests_aspect": "Go, GitHub search (protobuf for Go)",
        "language": "go",
    },
    {
        "id": "avro-java",
        "library": "avro",
        "query": "Schema Record GenericRecord DatumReader Writer",
        "tests_aspect": "Java, GitHub search (Apache Avro)",
        "language": "java",
    },
    {
        "id": "msgpack-ruby",
        "library": "msgpack-ruby",
        "query": "pack unpack Packer Unpacker factory extension",
        "tests_aspect": "Ruby, GitHub search (MessagePack for Ruby)",
        "language": "ruby",
    },
    {
        "id": "jason",
        "library": "jason",
        "query": "encode! decode! Encoder Decoder fragment sigil",
        "tests_aspect": "Elixir, GitHub search (JSON codec Elixir)",
        "language": "elixir",
    },
    {
        "id": "gson",
        "library": "gson",
        "query": "Gson toJson fromJson TypeAdapter JsonObject",
        "tests_aspect": "Java, GitHub search (Google Gson)",
        "language": "java",
    },
    {
        "id": "kotlinx-datetime",
        "library": "kotlinx-datetime",
        "query": "Instant LocalDate TimeZone Clock DateTimePeriod",
        "tests_aspect": "Kotlin, GitHub search (KotlinX datetime)",
        "language": "kotlin",
    },
    {
        "id": "cedar-swift",
        "library": "cedar",
        "query": "describe it expect equal beforeEach context",
        "tests_aspect": "C++, GitHub search (Cedar BDD testing, Obj-C++)",
        "language": "cpp",
    },
    {
        "id": "poison-elixir",
        "library": "poison",
        "query": "encode decode Encoder Decoder Parser",
        "tests_aspect": "Elixir, GitHub search (JSON parsing Elixir)",
        "language": "elixir",
    },
    # =====================================================================
    # Category BX: Emerging / niche libraries (10)
    # =====================================================================
    {
        "id": "gleam",
        "library": "gleam",
        "query": "fn type Result module import let pub use",
        "tests_aspect": "GitHub search (gleam.run language, written in Rust)",
        "language": "rust",
    },
    {
        "id": "roc-lang",
        "library": "roc",
        "query": "Task platform app expect dbg module",
        "tests_aspect": "GitHub search (roc-lang.org, written in Zig)",
        "language": "zig",
    },
    {
        "id": "grain",
        "library": "grain",
        "query": "module let match enum import export wasm",
        "tests_aspect": "GitHub search (grain-lang.org WASM, written in Reason)",
        "language": "ocaml",
    },
    {
        "id": "crystal-lang",
        "library": "crystal",
        "query": "class struct macro fiber channel spawn",
        "tests_aspect": "Ruby, GitHub search (crystal-lang.org)",
        "language": "ruby",
    },
    {
        "id": "vlang",
        "library": "v",
        "query": "fn struct module import or_block defer",
        "tests_aspect": "C, GitHub search (vlang.io)",
        "language": "c",
    },
    {
        "id": "bun",
        "library": "bun",
        "query": "Bun.serve fetch file test install create run",
        "tests_aspect": "npm, bun (fast JS runtime)",
    },
    {
        "id": "deno-runtime",
        "library": "deno",
        "query": "Deno.serve fetch test deploy lsp permissions",
        "tests_aspect": "Rust, GitHub search (deno.com)",
        "language": "rust",
    },
    {
        "id": "htmx-web",
        "library": "htmx.org",
        "query": "hx-get hx-post hx-swap hx-target hx-trigger",
        "tests_aspect": "npm, htmx (hypermedia-driven)",
    },
    {
        "id": "leptos",
        "library": "leptos",
        "query": "component view create_signal create_effect server",
        "tests_aspect": "crates.io, leptos (Rust full-stack web)",
    },
    {
        "id": "templ-go",
        "library": "templ",
        "query": "templ component render handler generate",
        "tests_aspect": "Go, GitHub search (templ.guide HTML)",
        "language": "go",
    },
    # =====================================================================
    # Category BY: More Java / JVM ecosystem (10)
    # =====================================================================
    {
        "id": "spring-security",
        "library": "spring-security",
        "query": "SecurityFilterChain authentication authorization CSRF",
        "tests_aspect": "Java, GitHub search (Spring Security)",
        "language": "java",
    },
    {
        "id": "thymeleaf",
        "library": "thymeleaf",
        "query": "th:text th:each th:if template expression",
        "tests_aspect": "Java, GitHub search (thymeleaf.org template)",
        "language": "java",
    },
    {
        "id": "liquibase",
        "library": "liquibase",
        "query": "changeset changelog rollback tag context",
        "tests_aspect": "Java, GitHub search (liquibase.org migration)",
        "language": "java",
    },
    {
        "id": "apache-commons-lang",
        "library": "commons-lang",
        "query": "StringUtils NumberUtils Pair Triple RandomStringUtils",
        "tests_aspect": "Java, GitHub search (Apache Commons Lang)",
        "language": "java",
    },
    {
        "id": "vaadin",
        "library": "flow",
        "query": "Button Grid TextField Layout Router Component",
        "tests_aspect": "Java, GitHub search (Vaadin Flow web UI)",
        "language": "java",
    },
    {
        "id": "assertj",
        "library": "assertj",
        "query": "assertThat isEqualTo containsExactly hasSize",
        "tests_aspect": "Java, GitHub search (assertj.github.io)",
        "language": "java",
    },
    {
        "id": "testcontainers-java",
        "library": "testcontainers-java",
        "query": "GenericContainer PostgreSQLContainer Docker wait",
        "tests_aspect": "Java, GitHub search (testcontainers.org)",
        "language": "java",
    },
    {
        "id": "resilience4j",
        "library": "resilience4j",
        "query": "CircuitBreaker Retry RateLimiter Bulkhead TimeLimiter",
        "tests_aspect": "Java, GitHub search (resilience4j.readme.io)",
        "language": "java",
    },
    {
        "id": "micrometer",
        "library": "micrometer",
        "query": "Counter Timer Gauge MeterRegistry registry",
        "tests_aspect": "Java, GitHub search (micrometer.io metrics)",
        "language": "java",
    },
    {
        "id": "archunit",
        "library": "ArchUnit",
        "query": "classes that resideIn noClasses should access",
        "tests_aspect": "Java, GitHub search (archunit.org tests)",
        "language": "java",
    },
    # =====================================================================
    # Category BZ: More C# / Swift / Kotlin (10)
    # =====================================================================
    {
        "id": "maui-dotnet",
        "library": "maui",
        "query": "ContentPage XAML Shell Entry Button Navigation",
        "tests_aspect": "C#, GitHub search (MAUI cross-platform)",
        "language": "csharp",
    },
    {
        "id": "wolverine-dotnet",
        "library": "wolverine",
        "query": "handler message endpoint saga outbox middleware",
        "tests_aspect": "C#, GitHub search (wolverine.netlify messaging)",
        "language": "csharp",
    },
    {
        "id": "carter-dotnet",
        "library": "Carter",
        "query": "CarterModule Get Post Route Bind Negotiate",
        "tests_aspect": "C#, GitHub search (minimal API framework)",
        "language": "csharp",
    },
    {
        "id": "otel-dotnet",
        "library": "opentelemetry-dotnet",
        "query": "TracerProvider MeterProvider Activity Span Export",
        "tests_aspect": "C#, GitHub search (OTel .NET SDK)",
        "language": "csharp",
    },
    {
        "id": "swiftlint",
        "library": "SwiftLint",
        "query": "rule violation configuration disable enable opt_in",
        "tests_aspect": "Swift, GitHub search (realm.github.io/SwiftLint)",
        "language": "swift",
    },
    {
        "id": "tuist",
        "library": "tuist",
        "query": "Project Target generate manifest workspace edit",
        "tests_aspect": "Swift, GitHub search (tuist.dev Xcode tool)",
        "language": "swift",
    },
    {
        "id": "hilt",
        "library": "dagger",
        "query": "Module Inject Provides Singleton Component Hilt",
        "tests_aspect": "Java, GitHub search (dagger.dev DI)",
        "language": "java",
    },
    {
        "id": "room-android",
        "library": "androidx",
        "query": "Room Dao Entity Database Query Insert migration",
        "tests_aspect": "Kotlin, GitHub search (Android Room persistence)",
        "language": "kotlin",
    },
    {
        "id": "swift-argument-parser",
        "library": "swift-argument-parser",
        "query": "ParsableCommand Argument Option Flag help",
        "tests_aspect": "Swift, GitHub search (Apple CLI args)",
        "language": "swift",
    },
    {
        "id": "amperfy-swift",
        "library": "swift-collections",
        "query": "Deque OrderedSet OrderedDictionary TreeDictionary",
        "tests_aspect": "Swift, GitHub search (Apple data structures)",
        "language": "swift",
    },
    # =====================================================================
    # Category CA: Testing frameworks — cross-language (10)
    # =====================================================================
    {
        "id": "testcontainers-go",
        "library": "testcontainers-go",
        "query": "GenericContainer ContainerRequest Started Terminate",
        "tests_aspect": "Go, GitHub search (golang.testcontainers.org)",
        "language": "go",
    },
    {
        "id": "cypress-e2e",
        "library": "cypress",
        "query": "cy get visit click intercept fixture should",
        "tests_aspect": "npm, cypress (E2E testing)",
    },
    {
        "id": "playwright-test",
        "library": "@playwright/test",
        "query": "test expect page locator fill click toHaveText",
        "tests_aspect": "npm, Playwright (E2E browser testing)",
    },
    {
        "id": "wallaby-elixir",
        "library": "wallaby",
        "query": "visit fill_in click_button assert_has Browser",
        "tests_aspect": "Elixir, GitHub search (browser testing)",
        "language": "elixir",
    },
    {
        "id": "junit-pioneer",
        "library": "junit-pioneer",
        "query": "CartesianTest RetryingTest DefaultTimeZone",
        "tests_aspect": "Java, GitHub search (junit-pioneer.org)",
        "language": "java",
    },
    {
        "id": "hspec-haskell",
        "library": "hspec",
        "query": "describe it shouldBe shouldReturn before",
        "tests_aspect": "Haskell, GitHub search (hspec.github.io)",
        "language": "haskell",
    },
    {
        "id": "busted-lua",
        "library": "busted",
        "query": "describe it assert spy mock pending setup",
        "tests_aspect": "Lua, GitHub search (lunarmodules testing)",
        "language": "lua",
    },
    {
        "id": "scalacheck",
        "library": "scalacheck",
        "query": "Gen Prop forAll Arbitrary choose frequency",
        "tests_aspect": "Scala, GitHub search (property-based testing)",
        "language": "scala",
    },
    {
        "id": "pest-rust",
        "library": "pest",
        "query": "Grammar Rule Pair Pairs inner parse",
        "tests_aspect": "crates.io, pest (PEG parser)",
    },
    {
        "id": "storybook-testing",
        "library": "storybook",
        "query": "Story Meta args decorators controls play",
        "tests_aspect": "npm, storybook (UI component dev)",
    },
    # =====================================================================
    # Category CB: Logging / Observability — cross-language (10)
    # =====================================================================
    {
        "id": "loguru-py",
        "library": "loguru",
        "query": "logger add bind catch format rotation",
        "tests_aspect": "PyPI, loguru (Python logging)",
        "language": "python",
    },
    {
        "id": "zerolog-go",
        "library": "zerolog",
        "query": "Logger Info Warn Error Str Int Msg With",
        "tests_aspect": "Go, GitHub search (rs/zerolog JSON logging)",
        "language": "go",
    },
    {
        "id": "timber-android",
        "library": "timber",
        "query": "Timber.d plant Tree tag format DebugTree",
        "tests_aspect": "Kotlin, GitHub search (JakeWharton/timber)",
        "language": "kotlin",
    },
    {
        "id": "otel-java",
        "library": "opentelemetry-java",
        "query": "Tracer Span Meter exporter SDK autoconfigure",
        "tests_aspect": "Java, GitHub search (OTel Java SDK)",
        "language": "java",
    },
    {
        "id": "cocoalumberjack",
        "library": "CocoaLumberjack",
        "query": "DDLog DDLogLevel DDFileLogger DDOSLogger",
        "tests_aspect": "Swift, GitHub search (iOS/macOS logging)",
        "language": "swift",
    },
    {
        "id": "ruby-logger",
        "library": "semantic_logger",
        "query": "Logger info warn error debug formatter appender",
        "tests_aspect": "Ruby, GitHub search (semantic logging)",
        "language": "ruby",
    },
    {
        "id": "telemetry-elixir",
        "library": "telemetry",
        "query": "execute attach span measurement metadata",
        "tests_aspect": "Elixir, GitHub search (beam-telemetry)",
        "language": "elixir",
    },
    {
        "id": "log-rs",
        "library": "tracing",
        "query": "span event instrument subscriber Layer filter",
        "tests_aspect": "crates.io, tracing (Rust diagnostics)",
    },
    {
        "id": "winston-logging",
        "library": "winston",
        "query": "createLogger transports format level info error",
        "tests_aspect": "npm, winston (Node.js logging)",
    },
    {
        "id": "structlog-py",
        "library": "structlog",
        "query": "get_logger bind configure processor renderer",
        "tests_aspect": "PyPI, structlog (Python structured logging)",
        "language": "python",
    },
]


def get_benchmark_ids() -> list[str]:
    """Return all benchmark case IDs."""
    return [str(c["id"]) for c in BENCHMARK_CASES]


def get_case(case_id: str) -> dict:
    """Get a benchmark case by ID."""
    for c in BENCHMARK_CASES:
        if c["id"] == case_id:
            return c
    raise ValueError(f"Unknown benchmark case: {case_id}")


# ---------------------------------------------------------------------------
# Merge 400 new cases (Categories CC-DP) from benchmark_cases_cc_dp.py
# ---------------------------------------------------------------------------
from benchmark_cases_cc_dp import NEW_BENCHMARK_CASES  # noqa: E402

BENCHMARK_CASES.extend(NEW_BENCHMARK_CASES)

# ---------------------------------------------------------------------------
# Merge 400 new cases (Categories DQ-EZ) from benchmark_cases_dq_ez.py
# ---------------------------------------------------------------------------
from benchmark_cases_dq_ez import NEW_BENCHMARK_CASES_DQ_EZ  # noqa: E402

BENCHMARK_CASES.extend(NEW_BENCHMARK_CASES_DQ_EZ)

# ---------------------------------------------------------------------------
# Merge 400 new cases (Categories FA-GJ) from benchmark_cases_fa_gj.py
# ---------------------------------------------------------------------------
from benchmark_cases_fa_gj import NEW_BENCHMARK_CASES_FA_GJ  # noqa: E402

BENCHMARK_CASES.extend(NEW_BENCHMARK_CASES_FA_GJ)
