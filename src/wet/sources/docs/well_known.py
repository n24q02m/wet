"""Curated well-known documentation URLs."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Well-known docs — ONLY for genuinely ambiguous names, monorepo
# sub-frameworks, and non-library tools/platforms that no registry can
# discover correctly.  Entries should be minimal — add a new registry
# instead of adding entries here.
# ---------------------------------------------------------------------------
_WELL_KNOWN_DOCS: dict[str, dict[str, str]] = {
    # --- Ambiguous names (multi-language collision) ---
    "boost": {
        "homepage": "https://www.boost.org/doc/libs/",
        "repository": "https://github.com/boostorg/boost",
        "description": "Boost C++ Libraries — portable, peer-reviewed",
    },
    "cmake": {
        "homepage": "https://cmake.org/cmake/help/latest/",
        "repository": "https://github.com/Kitware/CMake",
        "description": "CMake cross-platform build system",
    },
    "protobuf": {
        "homepage": "https://protobuf.dev/",
        "repository": "https://github.com/protocolbuffers/protobuf",
        "description": "Protocol Buffers — Google's data interchange format",
    },
    "flux": {
        "homepage": "https://fluxcd.io/flux/",
        "repository": "https://github.com/fluxcd/flux2",
        "description": "Flux — GitOps toolkit for Kubernetes",
    },
    # --- Java/Spring monorepo sub-frameworks ---
    "spring-webflux": {
        "homepage": "https://docs.spring.io/spring-framework/reference/web/webflux.html",
        "repository": "https://github.com/spring-projects/spring-framework",
        "description": "Spring WebFlux — reactive web framework for Java",
    },
    "kafka-streams": {
        "homepage": "https://kafka.apache.org/documentation/streams/",
        "repository": "https://github.com/apache/kafka",
        "description": "Apache Kafka Streams — stream processing library",
    },
    "reactor-test": {
        "homepage": "https://projectreactor.io/docs/core/release/reference/#testing",
        "repository": "https://github.com/reactor/reactor-core",
        "description": "Project Reactor test utilities — StepVerifier",
    },
    # --- Android Jetpack monorepo ---
    "navigation-compose": {
        "homepage": "https://developer.android.com/develop/ui/compose/navigation",
        "repository": "https://github.com/androidx/androidx",
        "description": "Jetpack Navigation for Compose",
    },
    "work-manager": {
        "homepage": "https://developer.android.com/develop/background-work/background-tasks/persistent/getting-started",
        "repository": "https://github.com/androidx/androidx",
        "description": "Android WorkManager — background task scheduling",
    },
    "datastore": {
        "homepage": "https://developer.android.com/topic/libraries/architecture/datastore",
        "repository": "https://github.com/androidx/androidx",
        "description": "Android Jetpack DataStore — data storage solution",
    },
    # --- Non-library tools/platforms ---
    "gitlab-ci": {
        "homepage": "https://docs.gitlab.com/ci/yaml/",
        "repository": "https://github.com/gitlabhq/gitlabhq",
        "description": "GitLab CI/CD pipeline configuration",
    },
    "linkerd": {
        "homepage": "https://linkerd.io/2/reference/",
        "repository": "https://github.com/linkerd/linkerd2",
        "description": "Linkerd — ultra-light service mesh for Kubernetes",
    },
    "apisix": {
        "homepage": "https://apisix.apache.org/docs/apisix/getting-started/",
        "repository": "https://github.com/apache/apisix",
        "description": "Apache APISIX — cloud-native API gateway",
    },
    "krakend": {
        "homepage": "https://www.krakend.io/docs/overview/",
        "repository": "https://github.com/krakend/krakend-ce",
        "description": "KrakenD — high-performance API gateway",
    },
    "defold": {
        "homepage": "https://defold.com/manuals/introduction/",
        "repository": "https://github.com/defold/defold",
        "description": "Defold — cross-platform game engine",
    },
    "sqitch": {
        "homepage": "https://sqitch.org/docs/",
        "repository": "https://github.com/sqitchers/sqitch",
        "description": "Sqitch — database change management",
    },
    "tekton": {
        "homepage": "https://tekton.dev/docs/",
        "repository": "https://github.com/tektoncd/pipeline",
        "description": "Tekton — Kubernetes-native CI/CD pipelines",
    },
    "spline": {
        "homepage": "https://docs.spline.design/",
        "repository": "",
        "description": "Spline — 3D design tool for the web",
    },
    "dhall": {
        "homepage": "https://dhall-lang.org/",
        "repository": "https://github.com/dhall-lang/dhall-haskell",
        "description": "Dhall — programmable configuration language",
    },
    "@enhance/ssr": {
        "homepage": "https://enhance.dev/docs/",
        "repository": "https://github.com/enhance-dev/enhance",
        "description": "Enhance — HTML-first web framework",
    },
    # --- Go tools (binaries, not importable packages) ---
    "staticcheck": {
        "homepage": "https://staticcheck.dev/docs/",
        "repository": "https://github.com/dominikh/go-tools",
        "description": "Staticcheck — Go static analysis tool",
    },
    "mockgen": {
        "homepage": "https://pkg.go.dev/go.uber.org/mock/mockgen",
        "repository": "https://github.com/uber-go/mock",
        "description": "MockGen — Go mock code generator",
    },
    "govulncheck": {
        "homepage": "https://pkg.go.dev/golang.org/x/vuln/cmd/govulncheck",
        "repository": "https://github.com/golang/vuln",
        "description": "govulncheck — Go vulnerability scanner",
    },
    # --- Popular libraries with wrong/missing npm/PyPI homepage ---
    "chakra-ui": {
        "homepage": "https://www.chakra-ui.com/docs",
        "repository": "https://github.com/chakra-ui/chakra-ui",
        "description": "Chakra UI — accessible React component library",
    },
    "@chakra-ui/react": {
        "homepage": "https://www.chakra-ui.com/docs",
        "repository": "https://github.com/chakra-ui/chakra-ui",
        "description": "Chakra UI — accessible React component library",
    },
    "clerk": {
        "homepage": "https://clerk.com/docs",
        "repository": "https://github.com/clerk/javascript",
        "description": "Clerk — authentication and user management",
    },
    "@clerk/nextjs": {
        "homepage": "https://clerk.com/docs",
        "repository": "https://github.com/clerk/javascript",
        "description": "Clerk — authentication and user management for Next.js",
    },
    "supabase": {
        "homepage": "https://supabase.com/docs",
        "repository": "https://github.com/supabase/supabase",
        "description": "Supabase — open-source Firebase alternative",
    },
    "@supabase/supabase-js": {
        "homepage": "https://supabase.com/docs/reference/javascript/",
        "repository": "https://github.com/supabase/supabase-js",
        "description": "Supabase JavaScript client library",
    },
    # --- Scoped / monorepo sub-packages with missing homepage ---
    "@vue/router": {
        "homepage": "https://router.vuejs.org/",
        "repository": "https://github.com/vuejs/router",
        "description": "Vue Router — official router for Vue.js",
    },
    "vue-router": {
        "homepage": "https://router.vuejs.org/",
        "repository": "https://github.com/vuejs/router",
        "description": "Vue Router — official router for Vue.js",
    },
    "@vue/pinia": {
        "homepage": "https://pinia.vuejs.org/",
        "repository": "https://github.com/vuejs/pinia",
        "description": "Pinia — intuitive store for Vue.js",
    },
    "pinia": {
        "homepage": "https://pinia.vuejs.org/",
        "repository": "https://github.com/vuejs/pinia",
        "description": "Pinia — intuitive store for Vue.js",
    },
    # --- Ambiguous short names (deprecated/squatted on npm) ---
    "nest": {
        "homepage": "https://docs.nestjs.com/",
        "repository": "https://github.com/nestjs/nest",
        "description": "NestJS — progressive Node.js framework",
    },
    "nestjs": {
        "homepage": "https://docs.nestjs.com/",
        "repository": "https://github.com/nestjs/nest",
        "description": "NestJS — progressive Node.js framework",
    },
    # --- Name aliasing (common name != package name) ---
    "nextjs": {
        "homepage": "https://nextjs.org/docs",
        "repository": "https://github.com/vercel/next.js",
        "description": "Next.js — the React framework for the web",
    },
    "next.js": {
        "homepage": "https://nextjs.org/docs",
        "repository": "https://github.com/vercel/next.js",
        "description": "Next.js — the React framework for the web",
    },
    "vuejs": {
        "homepage": "https://vuejs.org/",
        "repository": "https://github.com/vuejs/core",
        "description": "Vue.js — progressive JavaScript framework",
    },
    "angular": {
        "homepage": "https://angular.dev/",
        "repository": "https://github.com/angular/angular",
        "description": "Angular — web application framework by Google",
    },
    "trpc": {
        "homepage": "https://trpc.io/docs",
        "repository": "https://github.com/trpc/trpc",
        "description": "tRPC — end-to-end typesafe APIs",
    },
    "@trpc/server": {
        "homepage": "https://trpc.io/docs",
        "repository": "https://github.com/trpc/trpc",
        "description": "tRPC — end-to-end typesafe APIs",
    },
    "tanstack-query": {
        "homepage": "https://tanstack.com/query/latest",
        "repository": "https://github.com/TanStack/query",
        "description": "TanStack Query — async state management",
    },
    "react-query": {
        "homepage": "https://tanstack.com/query/latest",
        "repository": "https://github.com/TanStack/query",
        "description": "TanStack Query — async state management",
    },
    "turborepo": {
        "homepage": "https://turbo.build/repo/docs",
        "repository": "https://github.com/vercel/turborepo",
        "description": "Turborepo — high-performance build system for JS/TS monorepos",
    },
    # --- Wrong/missing registry metadata (real package, bad discovery) ---
    "vinejs": {
        "homepage": "https://vinejs.dev/docs/introduction",
        "repository": "https://github.com/vinejs/vine",
        "description": "VineJS — form data validation library for Node.js",
    },
    "@vinejs/vine": {
        "homepage": "https://vinejs.dev/docs/introduction",
        "repository": "https://github.com/vinejs/vine",
        "description": "VineJS — form data validation library for Node.js",
    },
    "inertia": {
        "homepage": "https://inertiajs.com/",
        "repository": "https://github.com/inertiajs/inertia",
        "description": "Inertia.js — modern monolith SPA framework",
    },
    "inertiajs": {
        "homepage": "https://inertiajs.com/",
        "repository": "https://github.com/inertiajs/inertia",
        "description": "Inertia.js — modern monolith SPA framework",
    },
    "@inertiajs/react": {
        "homepage": "https://inertiajs.com/",
        "repository": "https://github.com/inertiajs/inertia",
        "description": "Inertia.js React adapter — modern monolith SPA framework",
    },
    "@inertiajs/vue3": {
        "homepage": "https://inertiajs.com/",
        "repository": "https://github.com/inertiajs/inertia",
        "description": "Inertia.js Vue 3 adapter — modern monolith SPA framework",
    },
    # --- Umbrella orgs / meta-packages not on registries ---
    "dry-rb": {
        "homepage": "https://dry-rb.org/",
        "repository": "https://github.com/dry-rb",
        "description": "dry-rb — Ruby gems for common programming patterns",
    },
    "dry-validation": {
        "homepage": "https://dry-rb.org/gems/dry-validation/",
        "repository": "https://github.com/dry-rb/dry-validation",
        "description": "dry-validation — data validation for Ruby",
    },
    "dry-types": {
        "homepage": "https://dry-rb.org/gems/dry-types/",
        "repository": "https://github.com/dry-rb/dry-types",
        "description": "dry-types — flexible type system for Ruby",
    },
    # --- Cross-ecosystem collisions (name exists on wrong registry) ---
    "rails": {
        "homepage": "https://guides.rubyonrails.org/",
        "repository": "https://github.com/rails/rails",
        "description": "Ruby on Rails — full-stack web application framework",
    },
    "laravel": {
        "homepage": "https://laravel.com/docs",
        "repository": "https://github.com/laravel/laravel",
        "description": "Laravel — PHP web application framework",
    },
    "symfony": {
        "homepage": "https://symfony.com/doc/current/",
        "repository": "https://github.com/symfony/symfony",
        "description": "Symfony — PHP web application framework",
    },
    "echo": {
        "homepage": "https://echo.labstack.com/",
        "repository": "https://github.com/labstack/echo",
        "description": "Echo — high-performance Go web framework",
    },
    "flutter": {
        "homepage": "https://docs.flutter.dev/",
        "repository": "https://github.com/flutter/flutter",
        "description": "Flutter — UI toolkit for multi-platform apps by Google",
    },
    "swift": {
        "homepage": "https://www.swift.org/documentation/",
        "repository": "https://github.com/swiftlang/swift",
        "description": "Swift — programming language by Apple",
    },
    "nginx": {
        "homepage": "https://nginx.org/en/docs/",
        "repository": "https://github.com/nginx/nginx",
        "description": "nginx — high-performance HTTP and reverse proxy server",
    },
    "beautiful-soup": {
        "homepage": "https://www.crummy.com/software/BeautifulSoup/bs4/doc/",
        "repository": "https://code.launchpad.net/beautifulsoup",
        "description": "Beautiful Soup — HTML/XML parser for Python",
    },
    "beautifulsoup": {
        "homepage": "https://www.crummy.com/software/BeautifulSoup/bs4/doc/",
        "repository": "https://code.launchpad.net/beautifulsoup",
        "description": "Beautiful Soup — HTML/XML parser for Python",
    },
    "bs4": {
        "homepage": "https://www.crummy.com/software/BeautifulSoup/bs4/doc/",
        "repository": "https://code.launchpad.net/beautifulsoup",
        "description": "Beautiful Soup — HTML/XML parser for Python",
    },
    "pytorch": {
        "homepage": "https://pytorch.org/docs/stable/",
        "repository": "https://github.com/pytorch/pytorch",
        "description": "PyTorch — open-source deep learning framework",
    },
    "torch": {
        "homepage": "https://pytorch.org/docs/stable/",
        "repository": "https://github.com/pytorch/pytorch",
        "description": "PyTorch — open-source deep learning framework",
    },
    "tensorflow": {
        "homepage": "https://www.tensorflow.org/api_docs",
        "repository": "https://github.com/tensorflow/tensorflow",
        "description": "TensorFlow — end-to-end ML platform",
    },
    "sklearn": {
        "homepage": "https://scikit-learn.org/stable/",
        "repository": "https://github.com/scikit-learn/scikit-learn",
        "description": "scikit-learn — machine learning in Python",
    },
    # --- Generic names (multi-language/ecosystem collision) ---
    "graphql": {
        "homepage": "https://graphql.org/learn/",
        "repository": "https://github.com/graphql/graphql-spec",
        "description": "GraphQL — query language for APIs",
    },
    "redis": {
        "homepage": "https://redis.io/docs/",
        "repository": "https://github.com/redis/redis",
        "description": "Redis — in-memory data store",
    },
    "kafka": {
        "homepage": "https://kafka.apache.org/documentation/",
        "repository": "https://github.com/apache/kafka",
        "description": "Apache Kafka — distributed event streaming platform",
    },
    "grpc": {
        "homepage": "https://grpc.io/docs/",
        "repository": "https://github.com/grpc/grpc",
        "description": "gRPC — high-performance RPC framework",
    },
    "htmx": {
        "homepage": "https://htmx.org/docs/",
        "repository": "https://github.com/bigskysoftware/htmx",
        "description": "htmx — high power tools for HTML",
    },
    # --- Java/Spring ecosystem ---
    "spring-boot": {
        "homepage": "https://docs.spring.io/spring-boot/reference/",
        "repository": "https://github.com/spring-projects/spring-boot",
        "description": "Spring Boot — Java application framework",
    },
    "spring": {
        "homepage": "https://docs.spring.io/spring-framework/reference/",
        "repository": "https://github.com/spring-projects/spring-framework",
        "description": "Spring Framework — comprehensive Java application framework",
    },
    "spring-security": {
        "homepage": "https://docs.spring.io/spring-security/reference/",
        "repository": "https://github.com/spring-projects/spring-security",
        "description": "Spring Security — authentication and authorization for Java",
    },
    # --- Rust crates with no custom homepage ---
    "axum": {
        "homepage": "https://docs.rs/axum/latest/axum/",
        "repository": "https://github.com/tokio-rs/axum",
        "description": "axum — ergonomic and modular web framework for Rust",
    },
    "reqwest": {
        "homepage": "https://docs.rs/reqwest/latest/reqwest/",
        "repository": "https://github.com/seanmonstar/reqwest",
        "description": "reqwest — HTTP client for Rust",
    },
    "sqlx": {
        "homepage": "https://docs.rs/sqlx/latest/sqlx/",
        "repository": "https://github.com/launchbadge/sqlx",
        "description": "SQLx — async SQL toolkit for Rust",
    },
    # --- Python popular but ambiguous ---
    "celery": {
        "homepage": "https://docs.celeryq.dev/en/stable/",
        "repository": "https://github.com/celery/celery",
        "description": "Celery — distributed task queue for Python",
    },
    "numpy": {
        "homepage": "https://numpy.org/doc/stable/",
        "repository": "https://github.com/numpy/numpy",
        "description": "NumPy — numerical computing with Python",
    },
    "pandas": {
        "homepage": "https://pandas.pydata.org/docs/",
        "repository": "https://github.com/pandas-dev/pandas",
        "description": "pandas — data analysis and manipulation for Python",
    },
}
