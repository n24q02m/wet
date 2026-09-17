# CHANGELOG

<!-- version list -->

## v3.14.9 (2026-09-17)

### Bug Fixes

- **deps**: Lock file maintenance ([#1789](https://github.com/n24q02m/wet/pull/1789),
  [`d1041bc`](https://github.com/n24q02m/wet/commit/d1041bc3e8846d79a23a22cd4d41129e04bd257e))

- **deps**: Update dawidd6/action-send-mail action to v22
  ([#1792](https://github.com/n24q02m/wet/pull/1792),
  [`eb6fa4e`](https://github.com/n24q02m/wet/commit/eb6fa4e15b152656a113b5921cb52ac600294189))

- **deps**: Update ghcr.io/astral-sh/uv:latest Docker digest to 62f8c04
  ([#1790](https://github.com/n24q02m/wet/pull/1790),
  [`57ca161`](https://github.com/n24q02m/wet/commit/57ca161851ea82c2c75ade5c088de6a488cd2934))

- **deps**: Update minor dependencies ([#1791](https://github.com/n24q02m/wet/pull/1791),
  [`b62ae69`](https://github.com/n24q02m/wet/commit/b62ae69ba7404782649163ba7caf68874f151ce6))

### Continuous Integration

- Consolidate workflows into ci.yml + cd.yml, drop opencode
  ([`6f073fa`](https://github.com/n24q02m/wet/commit/6f073fa254c582e82dd03e1b2fb8e8318c8fadcc))


## v3.14.8 (2026-09-16)

### Bug Fixes

- **search**: Credential-free default chain for hosted subs without saved SEARCH_BACKENDS
  ([#1793](https://github.com/n24q02m/wet/pull/1793),
  [`3e91eab`](https://github.com/n24q02m/wet/commit/3e91eabaa01210439afb23b51f4bcc5afa6f050b))


## v3.14.7 (2026-09-14)

### Bug Fixes

- Bump mcp-core to 1.24.6 and web-core to 2.7.3 ([#1787](https://github.com/n24q02m/wet/pull/1787),
  [`e31d9df`](https://github.com/n24q02m/wet/commit/e31d9df2e12324f7221e7f1cd83be77250510d64))

- Relax migration guard to fastretrieval floor range
  ([#1781](https://github.com/n24q02m/wet/pull/1781),
  [`95eeb6f`](https://github.com/n24q02m/wet/commit/95eeb6f895096799add9a55f4ebe94afebf6b4fb))

- Sort packaging import for ruff I001 ([#1781](https://github.com/n24q02m/wet/pull/1781),
  [`95eeb6f`](https://github.com/n24q02m/wet/commit/95eeb6f895096799add9a55f4ebe94afebf6b4fb))

- **deps**: Lock file maintenance ([#1781](https://github.com/n24q02m/wet/pull/1781),
  [`95eeb6f`](https://github.com/n24q02m/wet/commit/95eeb6f895096799add9a55f4ebe94afebf6b4fb))


## v3.14.6 (2026-09-14)

### Bug Fixes

- ⚡ bolt: replace urlparse in StartpageBackend to avoid allocations
  ([#1782](https://github.com/n24q02m/wet/pull/1782),
  [`1ab601b`](https://github.com/n24q02m/wet/commit/1ab601b9825bd80645f53f03b0eca73d95fd34ac))

- ⚡ bolt: resolve CodeQL alert in startpage URL fast-path
  ([#1782](https://github.com/n24q02m/wet/pull/1782),
  [`1ab601b`](https://github.com/n24q02m/wet/commit/1ab601b9825bd80645f53f03b0eca73d95fd34ac))


## v3.14.5 (2026-09-13)

### Bug Fixes

- Registry publish tolerates duplicate version on recovery dispatch (mcp registry rejects re-publish
  of an already-published version with 400 cannot publish duplicate version; idempotent recovery
  keeps deploy-cf + PyPI green) ([#1786](https://github.com/n24q02m/wet/pull/1786),
  [`8067f79`](https://github.com/n24q02m/wet/commit/8067f79bf94522df5bd15fe180e315b6d0d56d99))

### Continuous Integration

- Gate deploy-cf behind CF_DEPLOY_ENABLED var (token removed as off-manifest); note paused
  maintained instance in README
  ([`1284504`](https://github.com/n24q02m/wet/commit/12845043ead280bdfc6980e587b7d569f0819bd4))

### Documentation

- **readme**: Lead CLI section with wet script, document wet-mcp legacy alias
  ([`0457258`](https://github.com/n24q02m/wet/commit/04572587dd58fe52613e0018a9adcb1ecea8186a))


## v3.14.4 (2026-09-13)

### Bug Fixes

- Point server.json + plugin metadata at renamed repo wet
  ([`ad2e649`](https://github.com/n24q02m/wet/commit/ad2e649def2c1423c2bc222e849fc2f767f94a11))


## v3.14.3 (2026-09-13)

### Bug Fixes

- Restore legacy wet-mcp command alias so existing uvx wet-mcp configs keep working
  ([`1ae02c0`](https://github.com/n24q02m/wet/commit/1ae02c0cc31e2f79e316ba121119ee0cb35c44b0))


## v3.14.2 (2026-09-13)

### Bug Fixes

- Keep PyPI package wet-mcp (PyPI policy blocks project name wet); repo+CLI stay wet
  ([`b8ecb71`](https://github.com/n24q02m/wet/commit/b8ecb71415f7d889e15f41265f96b7f5ffbddc6c))


## v3.14.1 (2026-09-13)

### Bug Fixes

- **tests**: Metadata lookups + stdio spawn use new package name wet; allowlist fastretrieval 1.4.0
  (verified genuine PyPI stable)
  ([`5c1c715`](https://github.com/n24q02m/wet/commit/5c1c71508d255f9d4b6c493d6f18d0fb1dc6f8e1))

### Code Style

- Ruff format renamed-package test edits
  ([`032ac30`](https://github.com/n24q02m/wet/commit/032ac30759ba9048cf45c950a2d1bf3f9cbb12db))


## v3.14.0 (2026-09-13)

### Bug Fixes

- Update dist metadata lookups to new package name wet (CLI-first rename follow-up)
  ([`0835550`](https://github.com/n24q02m/wet/commit/08355504c9049643ea634fa60ecef6b91e3adaee))

### Documentation

- Correct MCP surface invocation (bare wet = passthrough, no serve-mcp subcommand)
  ([`879d5b8`](https://github.com/n24q02m/wet/commit/879d5b86175882a1e8a3a1cc225706e16db51d43))

### Features

- Add wet skill citizen (SKILL.md) per TOOL-2 L1.5
  ([`7e01124`](https://github.com/n24q02m/wet/commit/7e01124322fc66a1c1d75c465e9af9b466e9bdc9))


## v3.13.0 (2026-09-13)

### Documentation

- Add mode badge, MCP client install matrix, and maintained-instance deployment note
  ([`2632d34`](https://github.com/n24q02m/wet/commit/2632d346e49b10f5d4315cc3b79628c98e79c97a))

### Features

- Rename package wet-mcp -> wet, CLI-first (command: wet, MCP surface: wet serve-mcp)
  ([`00f49c9`](https://github.com/n24q02m/wet/commit/00f49c9af4e968a1741eb70cddc7ca30a9990cbb))


## v3.12.1 (2026-09-13)

### Bug Fixes

- Bump mcp-core to 1.24.1 ([#1778](https://github.com/n24q02m/wet-mcp/pull/1778),
  [`882e070`](https://github.com/n24q02m/wet-mcp/commit/882e0708e9682517725c7afa009a6d5914745c06))


## v3.12.0 (2026-09-12)

### Features

- ⚡ bolt: optimize DuckDuckGo href unwrapping for speed
  ([#1775](https://github.com/n24q02m/wet-mcp/pull/1775),
  [`b541016`](https://github.com/n24q02m/wet-mcp/commit/b54101628cc7ecc75566023ee90f999b1cda964d))


## v3.11.2 (2026-09-12)

### Bug Fixes

- Re-widen sync task attribute and allow fastretrieval 1.3.2 stable
  ([#1774](https://github.com/n24q02m/wet-mcp/pull/1774),
  [`e120652`](https://github.com/n24q02m/wet-mcp/commit/e1206527a465ae5bc44fa4d1040dfa70e4f1bb83))

- **deps**: Lock file maintenance ([#1774](https://github.com/n24q02m/wet-mcp/pull/1774),
  [`e120652`](https://github.com/n24q02m/wet-mcp/commit/e1206527a465ae5bc44fa4d1040dfa70e4f1bb83))

### Chores

- **release**: Fix stale two-branch comment (single-main lane)
  ([`3a259b5`](https://github.com/n24q02m/wet-mcp/commit/3a259b5078e6a3e8af284b339521344b055d03ef))

- **release**: Single-main release lane (staging branch retired)
  ([`09d5650`](https://github.com/n24q02m/wet-mcp/commit/09d5650d258fdaf812a0152ee1f0f979e2f27653))


## v3.11.1 (2026-09-12)

### Bug Fixes

- **deps**: Update dawidd6/action-send-mail action to v21
  ([#1772](https://github.com/n24q02m/wet-mcp/pull/1772),
  [`e90dda3`](https://github.com/n24q02m/wet-mcp/commit/e90dda3842a93bb009e3dafe2afa25a953ba81db))

- **deps**: Update fastmcp to v4 ([#1773](https://github.com/n24q02m/wet-mcp/pull/1773),
  [`8a296c8`](https://github.com/n24q02m/wet-mcp/commit/8a296c8047793494fc404680edc5fba839dc84f6))

- **deps**: Update ghcr.io/astral-sh/uv:latest Docker digest to b485bd6
  ([#1770](https://github.com/n24q02m/wet-mcp/pull/1770),
  [`22a739d`](https://github.com/n24q02m/wet-mcp/commit/22a739d57f8bb23be08d8b4d23088660e5eb1c3d))

- **deps**: Update minor dependencies ([#1771](https://github.com/n24q02m/wet-mcp/pull/1771),
  [`8a1a457`](https://github.com/n24q02m/wet-mcp/commit/8a1a45747d2d0352e7515b5274da644a058ff8ac))

### Chores

- Pin BSR action to v1.6.1 stable (6e688489) ([#1767](https://github.com/n24q02m/wet-mcp/pull/1767),
  [`a906c16`](https://github.com/n24q02m/wet-mcp/commit/a906c16685510c795428fad1d55f062f465eafa3))

- **rulesets**: Align IaC with repo-bootstrap template
  ([`9a86502`](https://github.com/n24q02m/wet-mcp/commit/9a86502919d6ef552285ccc87ad36ee043adb057))


## v3.11.0 (2026-09-11)

### Bug Fixes

- Scope hosted wet routing and sync ([#1765](https://github.com/n24q02m/wet-mcp/pull/1765),
  [`2663a9e`](https://github.com/n24q02m/wet-mcp/commit/2663a9e77c673558dc2fcdd4ef79cff789555f98))

- ⚡ bolt: optimize html stripping via combined regex
  ([#1753](https://github.com/n24q02m/wet-mcp/pull/1753),
  [`a200dc4`](https://github.com/n24q02m/wet-mcp/commit/a200dc47b1c7435a94315e83a1f3118eaee379f6))

- **deps**: Lock file maintenance ([#1758](https://github.com/n24q02m/wet-mcp/pull/1758),
  [`5304de4`](https://github.com/n24q02m/wet-mcp/commit/5304de43e597e962a56cc5d3e5692fe874e70e84))

- **deps**: Update ghcr.io/astral-sh/uv:latest Docker digest to 73d2665
  ([#1760](https://github.com/n24q02m/wet-mcp/pull/1760),
  [`0e63311`](https://github.com/n24q02m/wet-mcp/commit/0e633113882dbaf3fafa4ba71bd71e909d685fe2))

- **deps**: Update mcp to v2 ([#1752](https://github.com/n24q02m/wet-mcp/pull/1752),
  [`212922f`](https://github.com/n24q02m/wet-mcp/commit/212922f1ecbc04d9d6c1f6fc5bca032fab17cdc1))

- **deps**: Update n24q02m/better-semantic-release action to v1.6.0
  ([#1751](https://github.com/n24q02m/wet-mcp/pull/1751),
  [`c9ded6f`](https://github.com/n24q02m/wet-mcp/commit/c9ded6fa42ebe7c98e4e939fb3bfbde78c891994))

- **deps**: Update patch dependencies ([#1750](https://github.com/n24q02m/wet-mcp/pull/1750),
  [`63c3b25`](https://github.com/n24q02m/wet-mcp/commit/63c3b251998f4733ffb1d654fd88f5aa5b5a2795))

- **deps**: Update vitest to v5 ([#1757](https://github.com/n24q02m/wet-mcp/pull/1757),
  [`dba148e`](https://github.com/n24q02m/wet-mcp/commit/dba148e4ee193bbc38e59f7e1a7ca3fd1b4a3ea8))

### Continuous Integration

- Wire unified merge=release ladder (push staging=beta, main=stable)
  ([`01e3afb`](https://github.com/n24q02m/wet-mcp/commit/01e3afb7f8417f66c1f36855f2d975930ad6c5a1))

### Features

- ⚡ bolt: fast path for macro stripping ([#1759](https://github.com/n24q02m/wet-mcp/pull/1759),
  [`4d6829b`](https://github.com/n24q02m/wet-mcp/commit/4d6829b6c18da37c06e28769b508be65da5c2632))

- ⚡ bolt: optimize _html_text with pre-compiled regex and str.split()
  ([#1766](https://github.com/n24q02m/wet-mcp/pull/1766),
  [`637381a`](https://github.com/n24q02m/wet-mcp/commit/637381a578d72bfb4ac7f5dba3e125cc14cf9efd))

- ⚡ bolt: optimize _is_sensitive_path with frozenset.isdisjoint()
  ([#1762](https://github.com/n24q02m/wet-mcp/pull/1762),
  [`a82fd81`](https://github.com/n24q02m/wet-mcp/commit/a82fd81d3cdc23530db0547253543be5b1885083))


## v3.11.0-beta.2 (2026-09-04)

### Bug Fixes

- Add blocked-incident deploy path ([#1756](https://github.com/n24q02m/wet-mcp/pull/1756),
  [`b44e266`](https://github.com/n24q02m/wet-mcp/commit/b44e2666cf2d280690c388b00078ea575b26f9a0))

- Isolate OAuth JWT signing from vault encryption
  ([#1756](https://github.com/n24q02m/wet-mcp/pull/1756),
  [`b44e266`](https://github.com/n24q02m/wet-mcp/commit/b44e2666cf2d280690c388b00078ea575b26f9a0))

- Isolate wet JWT signing secret ([#1756](https://github.com/n24q02m/wet-mcp/pull/1756),
  [`b44e266`](https://github.com/n24q02m/wet-mcp/commit/b44e2666cf2d280690c388b00078ea575b26f9a0))

- Test OAuth rotation contract ([#1756](https://github.com/n24q02m/wet-mcp/pull/1756),
  [`b44e266`](https://github.com/n24q02m/wet-mcp/commit/b44e2666cf2d280690c388b00078ea575b26f9a0))


## v3.11.0-beta.1 (2026-09-04)

### Bug Fixes

- **deploy**: Use Browser Run as sole renderer
  ([#1755](https://github.com/n24q02m/wet-mcp/pull/1755),
  [`34894f7`](https://github.com/n24q02m/wet-mcp/commit/34894f74e96bc139e3dd703fda3880d332c7f04b))

### Features

- **search**: Drop x_search, add kagi/firecrawl backends + credential-free duckduckgo/startpage tier
  ([#1754](https://github.com/n24q02m/wet-mcp/pull/1754),
  [`84956b3`](https://github.com/n24q02m/wet-mcp/commit/84956b3f313df255b3a629b8aec80662e7cd4c73))


## v3.10.0 (2026-09-02)


## v3.10.0-beta.1 (2026-09-02)

### Bug Fixes

- Bump mcp-core to 1.23.2 ([#1732](https://github.com/n24q02m/wet-mcp/pull/1732),
  [`6e59588`](https://github.com/n24q02m/wet-mcp/commit/6e59588b1ae93f13dd6ac32afa4160fefca6f3b3))

- Bump n24q02m-web-core to 2.5.1 ([#1733](https://github.com/n24q02m/wet-mcp/pull/1733),
  [`440b1bf`](https://github.com/n24q02m/wet-mcp/commit/440b1bfcd5dca9af97363d848f88d8492eeee082))

- Remove stale ty suppression comments after uv.lock regeneration
  ([#1743](https://github.com/n24q02m/wet-mcp/pull/1743),
  [`c10b8ae`](https://github.com/n24q02m/wet-mcp/commit/c10b8aefef73a975d4cb813e5ab2eefba42b9826))

- Reuse search chain in agent extraction ([#1736](https://github.com/n24q02m/wet-mcp/pull/1736),
  [`51db4b4`](https://github.com/n24q02m/wet-mcp/commit/51db4b4b4fead96106390ff7cec1def37a1ea144))

- **deps**: Lock file maintenance ([#1734](https://github.com/n24q02m/wet-mcp/pull/1734),
  [`59fa1c6`](https://github.com/n24q02m/wet-mcp/commit/59fa1c6c896a22f2a08f3d8fab806a1087e521fa))

- **deps**: Pin mcp<2 to maintain FastMCP compatibility with MCP v1 SDK
  ([#1748](https://github.com/n24q02m/wet-mcp/pull/1748),
  [`fe9c60f`](https://github.com/n24q02m/wet-mcp/commit/fe9c60feffb6cbd4854cdf11720129ef65c9fa2e))

- **deps**: Pin mcp<2 to maintain FastMCP compatibility with MCP v1 SDK
  ([#1747](https://github.com/n24q02m/wet-mcp/pull/1747),
  [`298eb42`](https://github.com/n24q02m/wet-mcp/commit/298eb424d81ad70e466b2d838fcbc189b6f7bf11))

- **deps**: Pin mcp<2 to maintain FastMCP compatibility with MCP v1 SDK
  ([#1746](https://github.com/n24q02m/wet-mcp/pull/1746),
  [`70fb381`](https://github.com/n24q02m/wet-mcp/commit/70fb3817228777ee41d5d61b016c1abc9fd2cc4f))

- **deps**: Regenerate uv.lock to resolve httpx2 duplicate entry
  ([#1742](https://github.com/n24q02m/wet-mcp/pull/1742),
  [`a5ff80e`](https://github.com/n24q02m/wet-mcp/commit/a5ff80e875d3c3a81605cd53e09083c6a603706e))

- **deps**: Update fastmcp to v4 ([#1735](https://github.com/n24q02m/wet-mcp/pull/1735),
  [`80e905f`](https://github.com/n24q02m/wet-mcp/commit/80e905f28ddfa33865ed2ee884fc8015923acfc4))

- **deps**: Update ghcr.io/astral-sh/uv:latest Docker digest to 8b940d3
  ([#1737](https://github.com/n24q02m/wet-mcp/pull/1737),
  [`3d2db81`](https://github.com/n24q02m/wet-mcp/commit/3d2db81be70f9cb8cb5af0313b157acf9be0a418))

- **tool.ty**: Ignore pydantic-discarded-extra-argument and unused-ignore diagnostics
  ([#1745](https://github.com/n24q02m/wet-mcp/pull/1745),
  [`fa23f08`](https://github.com/n24q02m/wet-mcp/commit/fa23f087b264ad9884ba6efed9d49d15c803ba19))

- **types**: Restore CI-required ty suppressions and fix streamable_http_client types
  ([#1745](https://github.com/n24q02m/wet-mcp/pull/1745),
  [`fa23f08`](https://github.com/n24q02m/wet-mcp/commit/fa23f087b264ad9884ba6efed9d49d15c803ba19))

- **types**: Restore CI-required ty suppressions and fix streamable_http_client types
  ([#1744](https://github.com/n24q02m/wet-mcp/pull/1744),
  [`32f336f`](https://github.com/n24q02m/wet-mcp/commit/32f336f38cdea347a35af6e9e82f7bf96d7a758a))

- **types**: Suppress FastMCP nominal type mismatch in _run_http call
  ([#1748](https://github.com/n24q02m/wet-mcp/pull/1748),
  [`fe9c60f`](https://github.com/n24q02m/wet-mcp/commit/fe9c60feffb6cbd4854cdf11720129ef65c9fa2e))

- **types**: Suppress FastMCP nominal type mismatch in _run_http call
  ([#1747](https://github.com/n24q02m/wet-mcp/pull/1747),
  [`298eb42`](https://github.com/n24q02m/wet-mcp/commit/298eb424d81ad70e466b2d838fcbc189b6f7bf11))

### Features

- Opt-in parallel search fan-out and confidence score exposure
  ([#1741](https://github.com/n24q02m/wet-mcp/pull/1741),
  [`5049736`](https://github.com/n24q02m/wet-mcp/commit/5049736a227e429e09d9f7498216eb9910581629))

- Optional region filter and bounded refine loop for web search
  ([#1739](https://github.com/n24q02m/wet-mcp/pull/1739),
  [`83526e6`](https://github.com/n24q02m/wet-mcp/commit/83526e6cad79310f8b40d5024fa16609a4de6048))

- Stale-while-revalidate cache, per-provider latency EMA, and query budget
  ([#1740](https://github.com/n24q02m/wet-mcp/pull/1740),
  [`ba9eed3`](https://github.com/n24q02m/wet-mcp/commit/ba9eed3e112e7938ee2abbe624ad28cbea33e425))

### Testing

- Align mcp-core pin guards ([#1732](https://github.com/n24q02m/wet-mcp/pull/1732),
  [`6e59588`](https://github.com/n24q02m/wet-mcp/commit/6e59588b1ae93f13dd6ac32afa4160fefca6f3b3))

- **manifest**: Allow fastretrieval 1.2.0 in locked package assertion
  ([#1748](https://github.com/n24q02m/wet-mcp/pull/1748),
  [`fe9c60f`](https://github.com/n24q02m/wet-mcp/commit/fe9c60feffb6cbd4854cdf11720129ef65c9fa2e))


## v3.9.0 (2026-08-31)


## v3.9.0-beta.1 (2026-08-31)

### Bug Fixes

- Avoid repeated URL lowercase transformations
  ([`1cb975e`](https://github.com/n24q02m/wet-mcp/commit/1cb975e8ad8e96eec7989478092fd012a381f447))

- Cover live retrieval metadata ([#1726](https://github.com/n24q02m/wet-mcp/pull/1726),
  [`29cfe96`](https://github.com/n24q02m/wet-mcp/commit/29cfe96921aab62558c9f81240154a7a4ebe2c77))

- Repair registry release and stable retrieval pins
  ([`1ea6a86`](https://github.com/n24q02m/wet-mcp/commit/1ea6a86f00c0504be001166b8977bab7164fb334))

- **deps**: Lock file maintenance ([#1727](https://github.com/n24q02m/wet-mcp/pull/1727),
  [`d772c28`](https://github.com/n24q02m/wet-mcp/commit/d772c287b0e97c13a4253491912f89dda246ebcb))

### Features

- Expose search backend selection metadata ([#1728](https://github.com/n24q02m/wet-mcp/pull/1728),
  [`fc127a9`](https://github.com/n24q02m/wet-mcp/commit/fc127a9588c9a56107341d1531616436308a0ece))

- ⚡ bolt: optimize readthedocs host checking ([#1729](https://github.com/n24q02m/wet-mcp/pull/1729),
  [`2490b0a`](https://github.com/n24q02m/wet-mcp/commit/2490b0ab99a1fb68486a73ddc621e1a336b2544f))


## v3.8.0 (2026-08-29)

### Bug Fixes

- Align wet retrieval contract ([#1711](https://github.com/n24q02m/wet-mcp/pull/1711),
  [`80746d3`](https://github.com/n24q02m/wet-mcp/commit/80746d3ff2edc5daaf641d6f08991ad66784a2f0))

- Align wet retrieval contract ([#1710](https://github.com/n24q02m/wet-mcp/pull/1710),
  [`7257ed2`](https://github.com/n24q02m/wet-mcp/commit/7257ed2ef75cd19e46b958928831648a4b709c85))

- Make benchmark costs evidence-based ([#1711](https://github.com/n24q02m/wet-mcp/pull/1711),
  [`80746d3`](https://github.com/n24q02m/wet-mcp/commit/80746d3ff2edc5daaf641d6f08991ad66784a2f0))

- Make benchmark costs evidence-based ([#1710](https://github.com/n24q02m/wet-mcp/pull/1710),
  [`7257ed2`](https://github.com/n24q02m/wet-mcp/commit/7257ed2ef75cd19e46b958928831648a4b709c85))

- Pin workflow actions ([#1706](https://github.com/n24q02m/wet-mcp/pull/1706),
  [`7b30f24`](https://github.com/n24q02m/wet-mcp/commit/7b30f245ce0eed2b0ba3fa44bcb21b29d2fe8424))

- Refresh fastretrieval slim image comment ([#1693](https://github.com/n24q02m/wet-mcp/pull/1693),
  [`31132b2`](https://github.com/n24q02m/wet-mcp/commit/31132b2ae4f92e0f61a375378a72b8d4985d90aa))

- Use regex doc assertion in oci sunset contract test
  ([#1711](https://github.com/n24q02m/wet-mcp/pull/1711),
  [`80746d3`](https://github.com/n24q02m/wet-mcp/commit/80746d3ff2edc5daaf641d6f08991ad66784a2f0))

- Validate hosted extraction payload ([#1711](https://github.com/n24q02m/wet-mcp/pull/1711),
  [`80746d3`](https://github.com/n24q02m/wet-mcp/commit/80746d3ff2edc5daaf641d6f08991ad66784a2f0))

- Validate hosted extraction payload ([#1710](https://github.com/n24q02m/wet-mcp/pull/1710),
  [`7257ed2`](https://github.com/n24q02m/wet-mcp/commit/7257ed2ef75cd19e46b958928831648a4b709c85))

- ⚡ bolt: optimize _doc_dirs matching with frozenset and isdisjoint
  ([#1720](https://github.com/n24q02m/wet-mcp/pull/1720),
  [`d5751e0`](https://github.com/n24q02m/wet-mcp/commit/d5751e05ac228d205a2c44091d16023ee4c691d1))

- 🛡️ sentinel: [CRITICAL] Fix Unsafe Dynamic SQL in SQLite PRAGMA calls in tests
  ([#1718](https://github.com/n24q02m/wet-mcp/pull/1718),
  [`0aad65a`](https://github.com/n24q02m/wet-mcp/commit/0aad65af69502e7a79b5ea9fdc66d6ec935eea57))

- **deps**: Lock file maintenance ([#1690](https://github.com/n24q02m/wet-mcp/pull/1690),
  [`1a73591`](https://github.com/n24q02m/wet-mcp/commit/1a735911b2232fc83735afafa2c5997231463500))

- **deps**: Update ghcr.io/astral-sh/uv:latest Docker digest to 95f2aa1
  ([#1689](https://github.com/n24q02m/wet-mcp/pull/1689),
  [`580f20a`](https://github.com/n24q02m/wet-mcp/commit/580f20a2b2431ab803e042b00dbbd8ca873c788b))

- **deps**: Update minor dependencies ([#1701](https://github.com/n24q02m/wet-mcp/pull/1701),
  [`c224b8d`](https://github.com/n24q02m/wet-mcp/commit/c224b8d5b64f140e923171496ea8a3974c16630f))

- **deps**: Update patch dependencies ([#1700](https://github.com/n24q02m/wet-mcp/pull/1700),
  [`fdc0c41`](https://github.com/n24q02m/wet-mcp/commit/fdc0c41be070036070c1966f9721eb83fb848779))

- **deps**: Update python:3.13-slim-bookworm Docker digest to c45a22e
  ([#1715](https://github.com/n24q02m/wet-mcp/pull/1715),
  [`bacd235`](https://github.com/n24q02m/wet-mcp/commit/bacd235e27373c862a89cbd9829d5df4ff17d657))

- **deps**: Update step-security/harden-runner action to v2.21.0
  ([#1694](https://github.com/n24q02m/wet-mcp/pull/1694),
  [`7fbfd53`](https://github.com/n24q02m/wet-mcp/commit/7fbfd5323726dd2465f05586d44f08d367900ade))

- **release**: Sunset public OCI publishing ([#1711](https://github.com/n24q02m/wet-mcp/pull/1711),
  [`80746d3`](https://github.com/n24q02m/wet-mcp/commit/80746d3ff2edc5daaf641d6f08991ad66784a2f0))

### Chores

- Bump better-semantic-release to v1.4.0 ([#1714](https://github.com/n24q02m/wet-mcp/pull/1714),
  [`5fdb947`](https://github.com/n24q02m/wet-mcp/commit/5fdb9479468d16498b8e4efb769640938f75a130))

- **release**: Sunset public OCI publishing ([#1711](https://github.com/n24q02m/wet-mcp/pull/1711),
  [`80746d3`](https://github.com/n24q02m/wet-mcp/commit/80746d3ff2edc5daaf641d6f08991ad66784a2f0))

### Features

- Add wet quality benchmark runner ([#1711](https://github.com/n24q02m/wet-mcp/pull/1711),
  [`80746d3`](https://github.com/n24q02m/wet-mcp/commit/80746d3ff2edc5daaf641d6f08991ad66784a2f0))

- Add wet quality benchmark runner ([#1710](https://github.com/n24q02m/wet-mcp/pull/1710),
  [`7257ed2`](https://github.com/n24q02m/wet-mcp/commit/7257ed2ef75cd19e46b958928831648a4b709c85))

- Add Wet runtime quality benchmark ([#1710](https://github.com/n24q02m/wet-mcp/pull/1710),
  [`7257ed2`](https://github.com/n24q02m/wet-mcp/commit/7257ed2ef75cd19e46b958928831648a4b709c85))

- Benchmark wet hosted extraction ([#1711](https://github.com/n24q02m/wet-mcp/pull/1711),
  [`80746d3`](https://github.com/n24q02m/wet-mcp/commit/80746d3ff2edc5daaf641d6f08991ad66784a2f0))

- Benchmark wet hosted extraction ([#1710](https://github.com/n24q02m/wet-mcp/pull/1710),
  [`7257ed2`](https://github.com/n24q02m/wet-mcp/commit/7257ed2ef75cd19e46b958928831648a4b709c85))


## v3.7.4-beta.1 (2026-08-15)

### Bug Fixes

- Migrate wet-mcp to fastretrieval ([#1691](https://github.com/n24q02m/wet-mcp/pull/1691),
  [`7038308`](https://github.com/n24q02m/wet-mcp/commit/703830898ba419312404dbd719713c719e2af6d7))

- Sync wet lock metadata after release merge ([#1691](https://github.com/n24q02m/wet-mcp/pull/1691),
  [`7038308`](https://github.com/n24q02m/wet-mcp/commit/703830898ba419312404dbd719713c719e2af6d7))


## v3.7.3 (2026-08-15)

### Bug Fixes

- Bump wet dependency floors ([#1672](https://github.com/n24q02m/wet-mcp/pull/1672),
  [`fbdcb8a`](https://github.com/n24q02m/wet-mcp/commit/fbdcb8a1b0ee8e81bbf35555dd623ad709dfde69))

- Enforce robots policy in crawler actions ([#1687](https://github.com/n24q02m/wet-mcp/pull/1687),
  [`a839414`](https://github.com/n24q02m/wet-mcp/commit/a83941436b2453d5846dc595a5906f3ca9992c48))

- Isolate search quality harness from legacy drive credentials
  ([#1671](https://github.com/n24q02m/wet-mcp/pull/1671),
  [`13610e9`](https://github.com/n24q02m/wet-mcp/commit/13610e9aaf35fddc26d728dd794d1179381491f0))

- Preserve crawler SSRF transport protection ([#1686](https://github.com/n24q02m/wet-mcp/pull/1686),
  [`6b03aa5`](https://github.com/n24q02m/wet-mcp/commit/6b03aa56f3a0064818ad21aaae7eb3c25c79d866))

- Preserve usable web search results ([#1680](https://github.com/n24q02m/wet-mcp/pull/1680),
  [`dc7f262`](https://github.com/n24q02m/wet-mcp/commit/dc7f26202087471fa9ed94b5aa8c88af624ea5b4))

- Route Jina reranking through Cloudflare gateway
  ([`51529e0`](https://github.com/n24q02m/wet-mcp/commit/51529e09141fdb9347cec48120110cba71515691))

- Separate Renovate range and lock ownership ([#1681](https://github.com/n24q02m/wet-mcp/pull/1681),
  [`3744e36`](https://github.com/n24q02m/wet-mcp/commit/3744e36ae2a241f6f81c6b1b2f8e965b4b86eb86))

- Stabilize s3 auto-sync error test ([#1679](https://github.com/n24q02m/wet-mcp/pull/1679),
  [`5234350`](https://github.com/n24q02m/wet-mcp/commit/52343509b6c2936db1dce5248bdfd989b9300ddb))

- Wait for backend readiness before first request
  ([`2b820b6`](https://github.com/n24q02m/wet-mcp/commit/2b820b6bcc2360e1fbcc388d000455bf929c8906))

- **deps**: Lock file maintenance ([#1683](https://github.com/n24q02m/wet-mcp/pull/1683),
  [`bcff61c`](https://github.com/n24q02m/wet-mcp/commit/bcff61cfbefa364472d28dc3a561b4f2440b1c8f))

- **deps**: Lock file maintenance ([#1677](https://github.com/n24q02m/wet-mcp/pull/1677),
  [`77027da`](https://github.com/n24q02m/wet-mcp/commit/77027da52b1c1a1ee03078991508594e5a4c519f))

- **deps**: Lock file maintenance ([#1668](https://github.com/n24q02m/wet-mcp/pull/1668),
  [`4f3a133`](https://github.com/n24q02m/wet-mcp/commit/4f3a133b102b26b1a3cbe4ab7efaf85612e0ab8a))

- **deps**: Update @cloudflare/workers-types to ^5.20260804.1
  ([#1667](https://github.com/n24q02m/wet-mcp/pull/1667),
  [`818044d`](https://github.com/n24q02m/wet-mcp/commit/818044d4c8cb0ba87abb674814653880c020e6e2))

- **deps**: Update astral-sh/setup-uv action to v10
  ([#1676](https://github.com/n24q02m/wet-mcp/pull/1676),
  [`09a0af2`](https://github.com/n24q02m/wet-mcp/commit/09a0af2b159d31de0c3ce32a8b531358967f3380))

- **deps**: Update greenlet to <3.5.6 ([#1682](https://github.com/n24q02m/wet-mcp/pull/1682),
  [`53ea909`](https://github.com/n24q02m/wet-mcp/commit/53ea9097c115dab1bdea7c286d829503483eadb2))

- **deps**: Update patch dependencies ([#1659](https://github.com/n24q02m/wet-mcp/pull/1659),
  [`013843d`](https://github.com/n24q02m/wet-mcp/commit/013843d40fd03d0179c4ca206cfbea33be2d6579))

- **deps**: Update python:3.13-slim-bookworm Docker digest to 00faa2d
  ([#1666](https://github.com/n24q02m/wet-mcp/pull/1666),
  [`a0628f0`](https://github.com/n24q02m/wet-mcp/commit/a0628f009e99a310757d945bd0d1479bb749adb0))

- **deps**: Update wrangler to ^4.119.0 ([#1675](https://github.com/n24q02m/wet-mcp/pull/1675),
  [`92c3b13`](https://github.com/n24q02m/wet-mcp/commit/92c3b13d89f8091febc36c33741f88319ec90d13))


## v3.7.2 (2026-08-11)


## v3.7.2-beta.1 (2026-08-11)

### Bug Fixes

- Recover unavailable Cloudflare containers ([#1669](https://github.com/n24q02m/wet-mcp/pull/1669),
  [`ebf7b33`](https://github.com/n24q02m/wet-mcp/commit/ebf7b338ed14842b7b56ea4a7e2b43d3f99ad8cd))


## v3.7.1 (2026-08-11)


## v3.7.1-beta.1 (2026-08-11)

### Bug Fixes

- Disable legacy sync on Cloudflare docs backend
  ([#1664](https://github.com/n24q02m/wet-mcp/pull/1664),
  [`45410cd`](https://github.com/n24q02m/wet-mcp/commit/45410cdb6fe6d90fc5f32e6ee2bfb4dc3dff374e))

- **deps**: Update n24q02m/better-semantic-release action to v1.3.0
  ([#1637](https://github.com/n24q02m/wet-mcp/pull/1637),
  [`4aaf51d`](https://github.com/n24q02m/wet-mcp/commit/4aaf51da5ca05ac72afbda04f5d4fc9e3f4d42ac))


## v3.7.0 (2026-08-11)

### Bug Fixes

- **deps**: Lock file maintenance ([#1662](https://github.com/n24q02m/wet-mcp/pull/1662),
  [`d031006`](https://github.com/n24q02m/wet-mcp/commit/d031006161a14d1a549d5048cbe2cbe554a47cbe))

- **deps**: Lock file maintenance ([#1660](https://github.com/n24q02m/wet-mcp/pull/1660),
  [`dc86a97`](https://github.com/n24q02m/wet-mcp/commit/dc86a97eb2d6ba5548cb796cfb49aa4b50168bb1))

- **deps**: Update ghcr.io/astral-sh/uv:latest Docker digest to 2d89062
  ([`217b5c6`](https://github.com/n24q02m/wet-mcp/commit/217b5c60d847152c15b6f564607b26b42771c142))

- **deps**: Update python:3.13-slim-bookworm Docker digest to 67a1e1f
  ([`031a79c`](https://github.com/n24q02m/wet-mcp/commit/031a79c0635c436548d147df1c882080a1b54ce3))

### Features

- Lock wet tool names through protocol
  ([`fc34d36`](https://github.com/n24q02m/wet-mcp/commit/fc34d367e47d4fa08b77ace30510f1042f86f8e3))


## v3.7.0-beta.5 (2026-08-09)

### Bug Fixes

- Clear invalid backend singletons ([#1634](https://github.com/n24q02m/wet-mcp/pull/1634),
  [`b35b100`](https://github.com/n24q02m/wet-mcp/commit/b35b1004afca0edee77bad24e2767297bc028dbf))

- Guard slim image local backend fallback ([#1634](https://github.com/n24q02m/wet-mcp/pull/1634),
  [`b35b100`](https://github.com/n24q02m/wet-mcp/commit/b35b1004afca0edee77bad24e2767297bc028dbf))

- Route docs queries through backend contract
  ([#1634](https://github.com/n24q02m/wet-mcp/pull/1634),
  [`b35b100`](https://github.com/n24q02m/wet-mcp/commit/b35b1004afca0edee77bad24e2767297bc028dbf))

- **deps**: Lock file maintenance ([#1653](https://github.com/n24q02m/wet-mcp/pull/1653),
  [`b90c58f`](https://github.com/n24q02m/wet-mcp/commit/b90c58fa8a5cce81fdbbdf30cb53494661de7669))

- **deps**: Lock file maintenance ([#1647](https://github.com/n24q02m/wet-mcp/pull/1647),
  [`898a03a`](https://github.com/n24q02m/wet-mcp/commit/898a03a9be79d3dc9cfbe12c9d5b3eaf3dee74c2))

- **deps**: Lock file maintenance ([#1645](https://github.com/n24q02m/wet-mcp/pull/1645),
  [`6f0e8fb`](https://github.com/n24q02m/wet-mcp/commit/6f0e8fb742b21b635f41097b203edb2437601e07))

- **deps**: Lock file maintenance ([#1644](https://github.com/n24q02m/wet-mcp/pull/1644),
  [`5f9f781`](https://github.com/n24q02m/wet-mcp/commit/5f9f781f9442301398f935f330b11e09a55e1ec2))

- **deps**: Lock file maintenance ([#1642](https://github.com/n24q02m/wet-mcp/pull/1642),
  [`80d281c`](https://github.com/n24q02m/wet-mcp/commit/80d281c3dc2086c3cf04b18352bc8d6dc8c4ad76))

- **deps**: Lock file maintenance ([#1632](https://github.com/n24q02m/wet-mcp/pull/1632),
  [`de101e9`](https://github.com/n24q02m/wet-mcp/commit/de101e92da77671d42dc2ede48cf97dcec28113b))

- **deps**: Update @cloudflare/workers-types to ^5.20260727.1
  ([#1631](https://github.com/n24q02m/wet-mcp/pull/1631),
  [`25467f1`](https://github.com/n24q02m/wet-mcp/commit/25467f140058e464820832c0694e60d1975b0ecd))

- **deps**: Update @cloudflare/workers-types to ^5.20260729.1
  ([#1641](https://github.com/n24q02m/wet-mcp/pull/1641),
  [`ff7b6b5`](https://github.com/n24q02m/wet-mcp/commit/ff7b6b5807607299cbf73d8737c9919367b01c4f))

- **deps**: Update @cloudflare/workers-types to ^5.20260801.1
  ([#1652](https://github.com/n24q02m/wet-mcp/pull/1652),
  [`c8dd882`](https://github.com/n24q02m/wet-mcp/commit/c8dd8820692f67b4f7ba9c5a9a709ae03dfd8cf6))

- **deps**: Update non-major dev dependencies
  ([#1643](https://github.com/n24q02m/wet-mcp/pull/1643),
  [`f2138ac`](https://github.com/n24q02m/wet-mcp/commit/f2138acdc193551fa621b6af5faa6cce1613f493))

- **deps**: Update non-major dev dependencies
  ([#1636](https://github.com/n24q02m/wet-mcp/pull/1636),
  [`5c82cbf`](https://github.com/n24q02m/wet-mcp/commit/5c82cbf4dd5b70cb26e5b64a87b03f82c002703e))

- **deps**: Update wrangler to ^4.118.0 ([#1646](https://github.com/n24q02m/wet-mcp/pull/1646),
  [`ebfdab5`](https://github.com/n24q02m/wet-mcp/commit/ebfdab509d8d946dedf21340e98e4979053ce1cb))

### Features

- Add search quality baseline harness ([#1655](https://github.com/n24q02m/wet-mcp/pull/1655),
  [`eed318d`](https://github.com/n24q02m/wet-mcp/commit/eed318dc3f0d910ab2643bec2a76530a4af6964c))


## v3.7.0-beta.4 (2026-08-03)

### Bug Fixes

- Align cf-d1 get_best_version with DocsDB and heal un-normalised names
  ([#1629](https://github.com/n24q02m/wet-mcp/pull/1629),
  [`bca9b9b`](https://github.com/n24q02m/wet-mcp/commit/bca9b9be6045355fd6bb23712350210381345e53))

- Apply D1 migrations on every CF deploy path
  ([#1621](https://github.com/n24q02m/wet-mcp/pull/1621),
  [`1b30442`](https://github.com/n24q02m/wet-mcp/commit/1b30442c2b4494f8e5202fc1c181d7596d7b5511))

- Batch D1 neighbour prefetch by parameters, not rows
  ([#1628](https://github.com/n24q02m/wet-mcp/pull/1628),
  [`dce4334`](https://github.com/n24q02m/wet-mcp/commit/dce4334740b63051a03b88b853a16f201911f5cd))

- Copy the DocsDB chunk-column fallbacks into the cf-d1 backend
  ([#1623](https://github.com/n24q02m/wet-mcp/pull/1623),
  [`f5040df`](https://github.com/n24q02m/wet-mcp/commit/f5040df6ab09cf73903256602ae99a2aa0f2c26e))

- Stamp discovery_version and the dropped metadata in cf-d1 upsert_library
  ([#1625](https://github.com/n24q02m/wet-mcp/pull/1625),
  [`5452d29`](https://github.com/n24q02m/wet-mcp/commit/5452d2913a4f160ae93155d7a58bebb049fd7271))


## v3.7.0-beta.3 (2026-08-03)

### Bug Fixes

- Adopt mcp_core.storage d1 and vectorize clients
  ([`5c67267`](https://github.com/n24q02m/wet-mcp/commit/5c67267bccbf049270d07348e4b8e07ae279b5cf))

- Bind single-user http to MCP_HOST/MCP_PORT when set
  ([`70d3409`](https://github.com/n24q02m/wet-mcp/commit/70d34095f52bdb0f73cb82f5eb28d90d6882cd2d))

- Honour disable-local flags in per-request embed/rerank resolution
  ([`1918033`](https://github.com/n24q02m/wet-mcp/commit/1918033c878293cde2d6cd56f601d33a532ebee1))

- Mint cf-d1 chunk ids in the backend instead of reading c["id"]
  ([`a553681`](https://github.com/n24q02m/wet-mcp/commit/a5536813b0cb4d7bccf9c05805020073011c4097))


## v3.7.0-beta.2 (2026-08-03)

### Bug Fixes

- Lowercase Renovate lock-file-maintenance PR subject
  ([#1607](https://github.com/n24q02m/wet-mcp/pull/1607),
  [`30fe6db`](https://github.com/n24q02m/wet-mcp/commit/30fe6db9a1126535938da2aebe51dee95a5c9c4d))

- Make background docs indexing durable and self-reporting
  ([#1610](https://github.com/n24q02m/wet-mcp/pull/1610),
  [`c037bb3`](https://github.com/n24q02m/wet-mcp/commit/c037bb3c53420b9912304d5f3d22437ed81ea37c))

- Quote loguru Record type + lowercase Renovate lock-file-maintenance subject
  ([#1607](https://github.com/n24q02m/wet-mcp/pull/1607),
  [`30fe6db`](https://github.com/n24q02m/wet-mcp/commit/30fe6db9a1126535938da2aebe51dee95a5c9c4d))

- Quote loguru Record TypedDict in test annotation for stricter ty
  ([#1607](https://github.com/n24q02m/wet-mcp/pull/1607),
  [`30fe6db`](https://github.com/n24q02m/wet-mcp/commit/30fe6db9a1126535938da2aebe51dee95a5c9c4d))

- Stamp the server's embedding identity in the Tier 1 ingest script
  ([#1609](https://github.com/n24q02m/wet-mcp/pull/1609),
  [`5a68e9a`](https://github.com/n24q02m/wet-mcp/commit/5a68e9aa2bdf40660b6e0d90621563d24e0f27eb))

- **deps**: Lock file maintenance ([#1604](https://github.com/n24q02m/wet-mcp/pull/1604),
  [`88db575`](https://github.com/n24q02m/wet-mcp/commit/88db575ae16d041ce070e0f4c0479f322b5584b0))

- **deps**: Update cryptography to v50 ([#1603](https://github.com/n24q02m/wet-mcp/pull/1603),
  [`32656d8`](https://github.com/n24q02m/wet-mcp/commit/32656d8145e45a353485cec744c0648dd5452efe))


## v3.7.0-beta.1 (2026-08-02)

### Bug Fixes

- Add bot PR governance workflow ([#1565](https://github.com/n24q02m/wet-mcp/pull/1565),
  [`06a237a`](https://github.com/n24q02m/wet-mcp/commit/06a237abe3fa9416dbce9770bdd8f48b1ee14370))

- Bump mcp-core to 1.21.0 ([#1563](https://github.com/n24q02m/wet-mcp/pull/1563),
  [`fb3a0da`](https://github.com/n24q02m/wet-mcp/commit/fb3a0da033d2dcd47500031e2f40b19f6f935a76))

- Cf-d1 index path drops docs_url and four doc_chunks columns
  ([#1589](https://github.com/n24q02m/wet-mcp/pull/1589),
  [`dc7fcaf`](https://github.com/n24q02m/wet-mcp/commit/dc7fcafc1ec6c9f66c56cb11af1737ceb14ba192))

- Checkpoint sqlite wal into docs.db before sync push
  ([#1587](https://github.com/n24q02m/wet-mcp/pull/1587),
  [`e492351`](https://github.com/n24q02m/wet-mcp/commit/e492351bcff7608f1f14b98937baf8bbf3cb7897))

- Collapse whitespace in normalize_query using split and join
  ([`7cbab2e`](https://github.com/n24q02m/wet-mcp/commit/7cbab2ea5574f9651b1a067bdc5bbdd393536a40))

- Combine markdown noise-filter regexes into one pattern
  ([`32eba3c`](https://github.com/n24q02m/wet-mcp/commit/32eba3c79ed293759767122a1949d24e83537ba9))

- Date the bot ledgers from git history and record rejections
  ([#1562](https://github.com/n24q02m/wet-mcp/pull/1562),
  [`aeafe25`](https://github.com/n24q02m/wet-mcp/commit/aeafe25dfe1eac2bfb5579caaa6d7f3f63b28f89))

- Describe the HTTP mode instead of advertising a personal instance
  ([`fa0d698`](https://github.com/n24q02m/wet-mcp/commit/fa0d69869edf1815ca3eb378eb0547042f76546a))

- Drop rangeStrategy from update-type package rules
  ([#1558](https://github.com/n24q02m/wet-mcp/pull/1558),
  [`9c0ea05`](https://github.com/n24q02m/wet-mcp/commit/9c0ea05020a239b62dfd8a5dfbe16ceda0015640))

- Drop the AI Agent header now that it labels nothing
  ([#1592](https://github.com/n24q02m/wet-mcp/pull/1592),
  [`0c52f92`](https://github.com/n24q02m/wet-mcp/commit/0c52f92180055509af44d01120e4a1f502e43061))

- Drop the code_quality rule from the main ruleset
  ([#1566](https://github.com/n24q02m/wet-mcp/pull/1566),
  [`23e0b08`](https://github.com/n24q02m/wet-mcp/commit/23e0b08a976496676c14ba25180af1ffb8103039))

- Gate bot governance on the branch living in this repository
  ([#1568](https://github.com/n24q02m/wet-mcp/pull/1568),
  [`9eb5fdf`](https://github.com/n24q02m/wet-mcp/commit/9eb5fdff9d00f7efdb3d626065aed5035944555d))

- Implement the 10 missing DocsDBCfBackend methods and a vector delete route
  ([#1605](https://github.com/n24q02m/wet-mcp/pull/1605),
  [`c3aea52`](https://github.com/n24q02m/wet-mcp/commit/c3aea5229bcc0cca55a9c1c9bbe37f4569975409))

- Install a single litellm distribution ([#1560](https://github.com/n24q02m/wet-mcp/pull/1560),
  [`81b7e94`](https://github.com/n24q02m/wet-mcp/commit/81b7e948582d9558d4cb93fd6c79d59285e899fa))

- Isolate test_config Settings() from leaked provider env vars
  ([#1596](https://github.com/n24q02m/wet-mcp/pull/1596),
  [`90ad90b`](https://github.com/n24q02m/wet-mcp/commit/90ad90b9b8acf82227e164db221d4ca02ea92113))

- Match ReadTheDocs hosts by suffix instead of substring
  ([#1559](https://github.com/n24q02m/wet-mcp/pull/1559),
  [`efdf601`](https://github.com/n24q02m/wet-mcp/commit/efdf601a75c2f4c8bfc224f9c798e5ff0c7cf75a))

- Match registry host checks on the host suffix, not a URL substring
  ([#1593](https://github.com/n24q02m/wet-mcp/pull/1593),
  [`dd9ebeb`](https://github.com/n24q02m/wet-mcp/commit/dd9ebebf7cd700a97016f0cd1fa7b044a832dcaf))

- Move this repo to Apache-2.0 ([#1586](https://github.com/n24q02m/wet-mcp/pull/1586),
  [`b63451b`](https://github.com/n24q02m/wet-mcp/commit/b63451bd8a247c1497a9a81f050dea745a9a6c1a))

- Pin config status label to the backend make_docs_db builds
  ([#1606](https://github.com/n24q02m/wet-mcp/pull/1606),
  [`27be3bd`](https://github.com/n24q02m/wet-mcp/commit/27be3bd723fe51d4f0ffb951fc0be443bd5db197))

- Pin GitHub Action references to commit SHAs
  ([#1554](https://github.com/n24q02m/wet-mcp/pull/1554),
  [`9476ade`](https://github.com/n24q02m/wet-mcp/commit/9476adef926360f3acb750b9c7d361c4b449092c))

- Record the heading-run skip in the bolt ledger
  ([#1588](https://github.com/n24q02m/wet-mcp/pull/1588),
  [`49ab24a`](https://github.com/n24q02m/wet-mcp/commit/49ab24afc9edba48464939ebfb8b7fc5b2bc3e58))

- Reduce snippet-scoring generator overhead
  ([`c38e023`](https://github.com/n24q02m/wet-mcp/commit/c38e02385ea3e7f5b45ec7314a616c323fd97b89))

- Remove redundant orphan-tag shell guard (better-semantic-release @v1 has a built-in one)
  ([#1552](https://github.com/n24q02m/wet-mcp/pull/1552),
  [`674e950`](https://github.com/n24q02m/wet-mcp/commit/674e9502dd7b7f943f62873abd220adea89dd92b))

- Report the active docs backend in config status
  ([#1606](https://github.com/n24q02m/wet-mcp/pull/1606),
  [`27be3bd`](https://github.com/n24q02m/wet-mcp/commit/27be3bd723fe51d4f0ffb951fc0be443bd5db197))

- Report weekly canary failures and keep their evidence
  ([#1600](https://github.com/n24q02m/wet-mcp/pull/1600),
  [`91a9cff`](https://github.com/n24q02m/wet-mcp/commit/91a9cff76dd5db029cdb670346aad5b2213b83ef))

- Rewrite optimisation comments in the voice of each file
  ([#1591](https://github.com/n24q02m/wet-mcp/pull/1591),
  [`21ab77c`](https://github.com/n24q02m/wet-mcp/commit/21ab77c1498a4a2306e770f04e8ce59c94c6c30f))

- Run CodeQL on bot pull requests ([#1564](https://github.com/n24q02m/wet-mcp/pull/1564),
  [`b7a8e93`](https://github.com/n24q02m/wet-mcp/commit/b7a8e93044b891242de4db98adb393a31637f620))

- Size D1 INSERT batches by bound parameters, add project_context to D1
  ([#1605](https://github.com/n24q02m/wet-mcp/pull/1605),
  [`c3aea52`](https://github.com/n24q02m/wet-mcp/commit/c3aea5229bcc0cca55a9c1c9bbe37f4569975409))

- Size D1 INSERT batches by bound parameters, add project_context to D1
  ([#1601](https://github.com/n24q02m/wet-mcp/pull/1601),
  [`51dc144`](https://github.com/n24q02m/wet-mcp/commit/51dc14417d08fc0a0d595c350fd0ebea8db2699c))

- Skip bot governance on pull requests from forks
  ([#1567](https://github.com/n24q02m/wet-mcp/pull/1567),
  [`ac0bfec`](https://github.com/n24q02m/wet-mcp/commit/ac0bfece6ae2ed81528208803dc90db95cca99b4))

- Skip the vector-table tests where sqlite-vec cannot load
  ([#1595](https://github.com/n24q02m/wet-mcp/pull/1595),
  [`19ffc51`](https://github.com/n24q02m/wet-mcp/commit/19ffc511eef4afe2ea07fc61cd387cf6c9981f2e))

- Stamp last_indexed_at on the background index path
  ([#1590](https://github.com/n24q02m/wet-mcp/pull/1590),
  [`07f0d42`](https://github.com/n24q02m/wet-mcp/commit/07f0d4286e230d46abe7c8d4b8ebd8f0d835550c))

- Stop .gitignore from silently dropping new .jules bot ledgers
  ([#1592](https://github.com/n24q02m/wet-mcp/pull/1592),
  [`0c52f92`](https://github.com/n24q02m/wet-mcp/commit/0c52f92180055509af44d01120e4a1f502e43061))

- Stop rescanning heading runs and copying whole llms.txt bodies
  ([#1588](https://github.com/n24q02m/wet-mcp/pull/1588),
  [`49ab24a`](https://github.com/n24q02m/wet-mcp/commit/49ab24afc9edba48464939ebfb8b7fc5b2bc3e58))

- Stop tests writing credentials into the developer's real home
  ([#1594](https://github.com/n24q02m/wet-mcp/pull/1594),
  [`3751f7b`](https://github.com/n24q02m/wet-mcp/commit/3751f7b9c8713e847e061b591db5f681352730d5))

- Surface the errors server.py and db.py were swallowing
  ([#1595](https://github.com/n24q02m/wet-mcp/pull/1595),
  [`19ffc51`](https://github.com/n24q02m/wet-mcp/commit/19ffc511eef4afe2ea07fc61cd387cf6c9981f2e))

- Unblock Tier 1 docs indexing (seed stamp, ingest gate, page shape)
  ([#1590](https://github.com/n24q02m/wet-mcp/pull/1590),
  [`07f0d42`](https://github.com/n24q02m/wet-mcp/commit/07f0d4286e230d46abe7c8d4b8ebd8f0d835550c))

- **deps**: Update @cloudflare/workers-types to ^5.20260719.1
  ([#1576](https://github.com/n24q02m/wet-mcp/pull/1576),
  [`51ff329`](https://github.com/n24q02m/wet-mcp/commit/51ff329b0b3beb346761d25487b46d83cea1abc6))

- **deps**: Update actions/checkout action to v7
  ([#1518](https://github.com/n24q02m/wet-mcp/pull/1518),
  [`8ae32c8`](https://github.com/n24q02m/wet-mcp/commit/8ae32c8949c1a8c6625b87427b63e8785ab00705))

- **deps**: Update actions/setup-node action to v7
  ([#1577](https://github.com/n24q02m/wet-mcp/pull/1577),
  [`97c67ee`](https://github.com/n24q02m/wet-mcp/commit/97c67ee11733f2d2bd08014d74a36755fc612396))

- **deps**: Update actions/setup-python action to v7
  ([#1599](https://github.com/n24q02m/wet-mcp/pull/1599),
  [`a589d3f`](https://github.com/n24q02m/wet-mcp/commit/a589d3ffbc4722b93be5a3e49bf47cb243943c81))

- **deps**: Update astral-sh/setup-uv action to v9
  ([#1602](https://github.com/n24q02m/wet-mcp/pull/1602),
  [`af64b29`](https://github.com/n24q02m/wet-mcp/commit/af64b29a2167fe3dd77ee10d33645745a28fa755))

- **deps**: Update dawidd6/action-send-mail action to v18
  ([#1519](https://github.com/n24q02m/wet-mcp/pull/1519),
  [`70694d8`](https://github.com/n24q02m/wet-mcp/commit/70694d8bee0ab1329ebb66d4dd0c20e407d3956d))

- **deps**: Update ghcr.io/astral-sh/uv:latest Docker digest to cf4eedc
  ([#1570](https://github.com/n24q02m/wet-mcp/pull/1570),
  [`14518c4`](https://github.com/n24q02m/wet-mcp/commit/14518c4e9ccaf7b1641e783c9bcce2ba30f1ef2a))

- **deps**: Update minor dependencies ([#1573](https://github.com/n24q02m/wet-mcp/pull/1573),
  [`541d390`](https://github.com/n24q02m/wet-mcp/commit/541d390cf491f22b2b753743bf5cd364fc5f1a3f))

- **deps**: Update n24q02m/better-semantic-release action to v1.2.3
  ([#1597](https://github.com/n24q02m/wet-mcp/pull/1597),
  [`bf60e92`](https://github.com/n24q02m/wet-mcp/commit/bf60e927c8c570cebd01b552c8f0334b73c9ecaf))

- **deps**: Update non-major dev dependencies
  ([#1598](https://github.com/n24q02m/wet-mcp/pull/1598),
  [`9ec0de3`](https://github.com/n24q02m/wet-mcp/commit/9ec0de34a5c418ec11c18ecf200c7269a9f33056))

- **deps**: Update non-major dev dependencies
  ([#1574](https://github.com/n24q02m/wet-mcp/pull/1574),
  [`0bc03fe`](https://github.com/n24q02m/wet-mcp/commit/0bc03fee7863b96fe4f2e38e5bc77d60b84723e2))

- **deps**: Update patch dependencies ([#1572](https://github.com/n24q02m/wet-mcp/pull/1572),
  [`727475f`](https://github.com/n24q02m/wet-mcp/commit/727475fa67d3364c003f1c8ff8062f2a80da631d))

- **deps**: Update python:3.13-slim-bookworm Docker digest to 9d7f287
  ([#1571](https://github.com/n24q02m/wet-mcp/pull/1571),
  [`c840fd1`](https://github.com/n24q02m/wet-mcp/commit/c840fd13fe3c85b5fcb258e42fbc9771dc6ee855))

- **deps**: Update typescript to v7 ([#1520](https://github.com/n24q02m/wet-mcp/pull/1520),
  [`52c99f6`](https://github.com/n24q02m/wet-mcp/commit/52c99f6bea77497693d1ab0f56b330c24368d2e6))

### Features

- Allow configuring bind interface via MCP_HOST in multi-user mode
  ([#1557](https://github.com/n24q02m/wet-mcp/pull/1557),
  [`fd3f437`](https://github.com/n24q02m/wet-mcp/commit/fd3f4378cc8e2ac6f2a08ab1f2b36b8b5b3c26d2))

- Scrape-batch skill for bulk URL extraction ([#1569](https://github.com/n24q02m/wet-mcp/pull/1569),
  [`d9cc762`](https://github.com/n24q02m/wet-mcp/commit/d9cc762aa3f21e2bdd2f28e866a3584663e5c05e))

- Sync cross-promo section ([#1580](https://github.com/n24q02m/wet-mcp/pull/1580),
  [`60888cb`](https://github.com/n24q02m/wet-mcp/commit/60888cb55dc744623287d7453e7565f137de09da))


## v3.6.0 (2026-07-18)


## v3.6.0-beta.3 (2026-07-18)

### Bug Fixes

- Classify embed errors by semantics so dims-rejection recovers
  ([#1550](https://github.com/n24q02m/wet-mcp/pull/1550),
  [`f370f9e`](https://github.com/n24q02m/wet-mcp/commit/f370f9ef0e8db0b38bc92703031cbabcef369d8b))

- Remove dead Modal embed/rerank references from wet test suite
  ([#1549](https://github.com/n24q02m/wet-mcp/pull/1549),
  [`04a867b`](https://github.com/n24q02m/wet-mcp/commit/04a867b237a406f892367fca89e27c444c7c0aa7))


## v3.6.0-beta.2 (2026-07-18)

### Bug Fixes

- Add orphan-tag integrity guard to release CI
  ([#1541](https://github.com/n24q02m/wet-mcp/pull/1541),
  [`45f91cc`](https://github.com/n24q02m/wet-mcp/commit/45f91ccbeb18c915b885bf7a3ccf770f53153b5a))

- Adopt better-semantic-release for built-in release guards
  ([`20eb3c4`](https://github.com/n24q02m/wet-mcp/commit/20eb3c4de88ed5c0705a887b83a3672915431d79))

- Pin rangeStrategy on delayed packageRules to fix renovate artifacts failure
  ([#1542](https://github.com/n24q02m/wet-mcp/pull/1542),
  [`63bcde5`](https://github.com/n24q02m/wet-mcp/commit/63bcde55530587bee37f3377cd573a161cb4ab8a))

- Short-circuit blocked marker check in docs.py
  ([`1d9b8dd`](https://github.com/n24q02m/wet-mcp/commit/1d9b8dd3be1352e920315dd6dd3f3c20c7c6aecd))

### Features

- Add PR-title conventional-commit gate + no-bump release warning
  ([#1544](https://github.com/n24q02m/wet-mcp/pull/1544),
  [`d3a55cf`](https://github.com/n24q02m/wet-mcp/commit/d3a55cfbe65c085c470cc9541f92bdd67bfa024c))

- Add setup_start config action and logout CLI subcommand
  ([#1545](https://github.com/n24q02m/wet-mcp/pull/1545),
  [`583cd96`](https://github.com/n24q02m/wet-mcp/commit/583cd963bc3a79c4d86610fe88ebcf6a9f8da6af))

- Per-sub custom endpoint (api_base) in relay for gateway routing
  ([#1547](https://github.com/n24q02m/wet-mcp/pull/1547),
  [`1dd29a6`](https://github.com/n24q02m/wet-mcp/commit/1dd29a69d09b99630b8b6b1ac59ca0f2c7a9d4ce))


## v3.6.0-beta.1 (2026-07-16)

### Bug Fixes

- Bump mcp-core floor to 1.19.0 stable ([#1538](https://github.com/n24q02m/wet-mcp/pull/1538),
  [`6006e86`](https://github.com/n24q02m/wet-mcp/commit/6006e86f594f021b5b85466daa079e222bbe5137))

- Default LLM chain to OpenRouter MiniMax M3 via CF AI Gateway
  ([#1539](https://github.com/n24q02m/wet-mcp/pull/1539),
  [`e086d01`](https://github.com/n24q02m/wet-mcp/commit/e086d0147d4e202759ce2163a7856aebe76996f7))

- Forward CF AI Gateway litellm envs into container
  ([#1539](https://github.com/n24q02m/wet-mcp/pull/1539),
  [`e086d01`](https://github.com/n24q02m/wet-mcp/commit/e086d0147d4e202759ce2163a7856aebe76996f7))

- Sync self-host wrangler.jsonc example LLM_MODELS with OpenRouter default
  ([#1539](https://github.com/n24q02m/wet-mcp/pull/1539),
  [`e086d01`](https://github.com/n24q02m/wet-mcp/commit/e086d0147d4e202759ce2163a7856aebe76996f7))

### Features

- Document CLI, smithery, and self-host endpoint in README
  ([#1536](https://github.com/n24q02m/wet-mcp/pull/1536),
  [`02d7a61`](https://github.com/n24q02m/wet-mcp/commit/02d7a61dca204e1d076afef80b1a4b876dfe6f4f))


## v3.5.0 (2026-07-14)

### Features

- Add smithery.yaml for stdio deployment ([#1533](https://github.com/n24q02m/wet-mcp/pull/1533),
  [`6fa3803`](https://github.com/n24q02m/wet-mcp/commit/6fa3803b20f15e5d4ed48af10cb018a77946b4a7))


## v3.5.0-beta.8 (2026-07-13)

### Bug Fixes

- Assert XPIA marker on extract diff output ([#1531](https://github.com/n24q02m/wet-mcp/pull/1531),
  [`04834e3`](https://github.com/n24q02m/wet-mcp/commit/04834e39eb97b59ee2eb01123e6e7b1dda2e4d05))

- Correct mention gate expression (balanced parens + precedence)
  ([#1530](https://github.com/n24q02m/wet-mcp/pull/1530),
  [`86e280f`](https://github.com/n24q02m/wet-mcp/commit/86e280f55c879007c6af150d9a547ff7371db2e4))

- Gate oc mention job on comment author write access
  ([#1530](https://github.com/n24q02m/wet-mcp/pull/1530),
  [`86e280f`](https://github.com/n24q02m/wet-mcp/commit/86e280f55c879007c6af150d9a547ff7371db2e4))

- Run opencode bot on hosted runners ([#1528](https://github.com/n24q02m/wet-mcp/pull/1528),
  [`24e4313`](https://github.com/n24q02m/wet-mcp/commit/24e4313aef9564d197b0705e639bee9aef478bf1))

- **deps**: Lock file maintenance ([#1523](https://github.com/n24q02m/wet-mcp/pull/1523),
  [`e10da4e`](https://github.com/n24q02m/wet-mcp/commit/e10da4ef362fe919ea09f18d2c5cfbb4165f6ed3))

### Features

- Track page changes with snapshot retention and extract diff
  ([#1531](https://github.com/n24q02m/wet-mcp/pull/1531),
  [`04834e3`](https://github.com/n24q02m/wet-mcp/commit/04834e39eb97b59ee2eb01123e6e7b1dda2e4d05))


## v3.5.0-beta.7 (2026-07-13)

### Bug Fixes

- Resolve the x-search XAI key per-sub, not from os.environ
  ([#1527](https://github.com/n24q02m/wet-mcp/pull/1527),
  [`2cb3900`](https://github.com/n24q02m/wet-mcp/commit/2cb39002f502185990d69c2a644209cc79316a40))

### Features

- Add X/Twitter search to the search tool (action="x") via xAI
  ([#1527](https://github.com/n24q02m/wet-mcp/pull/1527),
  [`2cb3900`](https://github.com/n24q02m/wet-mcp/commit/2cb39002f502185990d69c2a644209cc79316a40))


## v3.5.0-beta.6 (2026-07-13)

### Bug Fixes

- Make uvx search guard conditional on backend availability
  ([#1526](https://github.com/n24q02m/wet-mcp/pull/1526),
  [`236277f`](https://github.com/n24q02m/wet-mcp/commit/236277f6d8f2d7e64988497787a0192ce52af7b3))


## v3.5.0-beta.5 (2026-07-13)

### Bug Fixes

- Mark untrusted source in structured content of error results
  ([#1525](https://github.com/n24q02m/wet-mcp/pull/1525),
  [`c352fd5`](https://github.com/n24q02m/wet-mcp/commit/c352fd51f06e507e4da9c5b4413ddb0df5bd0775))

- Never open a real browser during tests ([#1522](https://github.com/n24q02m/wet-mcp/pull/1522),
  [`2062eb1`](https://github.com/n24q02m/wet-mcp/commit/2062eb1648d8dcbd20d97aaa050281821ed9d1f3))

### Features

- Return structured content from domain tools
  ([#1525](https://github.com/n24q02m/wet-mcp/pull/1525),
  [`c352fd5`](https://github.com/n24q02m/wet-mcp/commit/c352fd51f06e507e4da9c5b4413ddb0df5bd0775))

- Return structured content from domain tools (S13 W3.1 + XPIA envelope)
  ([#1525](https://github.com/n24q02m/wet-mcp/pull/1525),
  [`c352fd5`](https://github.com/n24q02m/wet-mcp/commit/c352fd51f06e507e4da9c5b4413ddb0df5bd0775))


## v3.5.0-beta.4 (2026-07-11)

### Bug Fixes

- Bump mcp-core floor to 1.19.0b4 ([#1517](https://github.com/n24q02m/wet-mcp/pull/1517),
  [`0dab3d2`](https://github.com/n24q02m/wet-mcp/commit/0dab3d2eca9eb5d7d9073ac1d64508e34acce14f))

- Thread byo client pair explicitly to google auth flow
  ([#1517](https://github.com/n24q02m/wet-mcp/pull/1517),
  [`0dab3d2`](https://github.com/n24q02m/wet-mcp/commit/0dab3d2eca9eb5d7d9073ac1d64508e34acce14f))

### Features

- Mount shared cli builder with auth/warmup/docs subcommands
  ([#1517](https://github.com/n24q02m/wet-mcp/pull/1517),
  [`0dab3d2`](https://github.com/n24q02m/wet-mcp/commit/0dab3d2eca9eb5d7d9073ac1d64508e34acce14f))


## v3.5.0-beta.3 (2026-07-11)

### Bug Fixes

- Bump mcp-core floor to 1.19.0b2 ([#1516](https://github.com/n24q02m/wet-mcp/pull/1516),
  [`b22d5b0`](https://github.com/n24q02m/wet-mcp/commit/b22d5b0bd774d6642112e0cf22a18030a87c8abe))

- Bump n24q02m-mcp-core, qwen3-embed, n24q02m-web-core to tracked versions
  ([#1510](https://github.com/n24q02m/wet-mcp/pull/1510),
  [`b3be771`](https://github.com/n24q02m/wet-mcp/commit/b3be77125eb8ca3e47e992f92777004324d6d49c))

- Clear stored gdrive token when minted by different client
  ([#1516](https://github.com/n24q02m/wet-mcp/pull/1516),
  [`b22d5b0`](https://github.com/n24q02m/wet-mcp/commit/b22d5b0bd774d6642112e0cf22a18030a87c8abe))

- Document public-by-design identifiers for secret scanners
  ([#1508](https://github.com/n24q02m/wet-mcp/pull/1508),
  [`4414993`](https://github.com/n24q02m/wet-mcp/commit/4414993fd9d006f48a857af05d850f10baf34272))

- Enforce fix(deps) semantic commit prefix in renovate config
  ([`3a06a09`](https://github.com/n24q02m/wet-mcp/commit/3a06a099ba5a723a891a33c59f58323595ddec80))

- Make renovate automerge effective (isolated groups, digest+lockfile automerge, 7-day cooldown)
  ([`0521efc`](https://github.com/n24q02m/wet-mcp/commit/0521efc0ea067bab0ec6d1f868bdea335dfc0212))

- Optimize _strip_nav_heading_blocks hot path
  ([`153b70c`](https://github.com/n24q02m/wet-mcp/commit/153b70c4e459d9d1de9e5fb3d9f18d28a3e1770e))

- Optimize whitespace normalization in _smart_chunks
  ([`e9f9110`](https://github.com/n24q02m/wet-mcp/commit/e9f91104b6e82847168bc474869520d2a9324a46))

- Track chunk length incrementally in chunk_markdown
  ([`729bf0c`](https://github.com/n24q02m/wet-mcp/commit/729bf0c57580841079aa2be29c3f7a763f7019af))

- Update stale mcp-core pin comment ([#1516](https://github.com/n24q02m/wet-mcp/pull/1516),
  [`b22d5b0`](https://github.com/n24q02m/wet-mcp/commit/b22d5b0bd774d6642112e0cf22a18030a87c8abe))

- Use resolved gh path in subprocess call (S607)
  ([`879ca76`](https://github.com/n24q02m/wet-mcp/commit/879ca76f6401c6d350470db5ea6b3ffd46634994))

- Use tuple endswith/startswith for document type detection
  ([`23b5b55`](https://github.com/n24q02m/wet-mcp/commit/23b5b55c963d44bdf66aebdf7157aafe1051e9cf))

- **deps**: Update minor dependencies ([#1513](https://github.com/n24q02m/wet-mcp/pull/1513),
  [`82febfe`](https://github.com/n24q02m/wet-mcp/commit/82febfec962aa5106b61d19cc74ff4af556e6d1a))

### Chores

- **deps**: Update dependency @cloudflare/workers-types to v5
  ([#1492](https://github.com/n24q02m/wet-mcp/pull/1492),
  [`8161c6d`](https://github.com/n24q02m/wet-mcp/commit/8161c6d812c0ee038db54e3c4b1be14b7bd6afe8))

- **deps**: Update ghcr.io/astral-sh/uv:latest docker digest to 0f36cb9
  ([#1512](https://github.com/n24q02m/wet-mcp/pull/1512),
  [`ebba49a`](https://github.com/n24q02m/wet-mcp/commit/ebba49a709dd4bcb7d15b61739c8ba381dd99a1e))

### Features

- Adopt bundled client BYO resolution chain for Google Drive
  ([#1516](https://github.com/n24q02m/wet-mcp/pull/1516),
  [`b22d5b0`](https://github.com/n24q02m/wet-mcp/commit/b22d5b0bd774d6642112e0cf22a18030a87c8abe))

- Resolve google client via bundled client BYO chain
  ([#1516](https://github.com/n24q02m/wet-mcp/pull/1516),
  [`b22d5b0`](https://github.com/n24q02m/wet-mcp/commit/b22d5b0bd774d6642112e0cf22a18030a87c8abe))


## v3.5.0-beta.2 (2026-07-10)

### Bug Fixes

- Decline standing GET /mcp SSE stream at the edge
  ([#1507](https://github.com/n24q02m/wet-mcp/pull/1507),
  [`fa3ce66`](https://github.com/n24q02m/wet-mcp/commit/fa3ce6680ea7e160209322bf31e4d4f210d69320))

- Fail the release when the computed version already exists on PyPI
  ([#1506](https://github.com/n24q02m/wet-mcp/pull/1506),
  [`2cd61fa`](https://github.com/n24q02m/wet-mcp/commit/2cd61fafea22333fd75306d82d52ed72271f19a3))


## v3.5.0-beta.1 (2026-07-10)

### Bug Fixes

- Reject unauthenticated /mcp at the Worker edge
  ([#1504](https://github.com/n24q02m/wet-mcp/pull/1504),
  [`2f553d9`](https://github.com/n24q02m/wet-mcp/commit/2f553d91b57704153dc053e0dab88977b29418f4))

- Resolve ty diagnostics blocking the type check
  ([#1505](https://github.com/n24q02m/wet-mcp/pull/1505),
  [`c5a62c4`](https://github.com/n24q02m/wet-mcp/commit/c5a62c4fa0d8cfa57bdb53b1026041b7922fc00c))

### Features

- Add opencode github agent (responds to /oc)
  ([`55f27bc`](https://github.com/n24q02m/wet-mcp/commit/55f27bce46240cde3a45fe4373dd35a5464d15fe))

- Add review-learnings store the automated reviewer must obey
  ([`3ed6d71`](https://github.com/n24q02m/wet-mcp/commit/3ed6d71bd08b0562dd2d03afcef6cd6d124518b9))

- Auto-respond only to issues and PRs opened by outside people
  ([`a5604aa`](https://github.com/n24q02m/wet-mcp/commit/a5604aa0cbbf9d817a43ce999f2c849b1861569a))

- Reviewer must obey .github/review-learnings.md
  ([`3e79220`](https://github.com/n24q02m/wet-mcp/commit/3e79220d889a39794173ae28ae5e2558e7a4a1c3))


## v3.4.2-beta.1 (2026-07-09)

### Bug Fixes

- Set WetContainer pingEndpoint to localhost/ so CF container health passes and it sleeps on idle
  ([#1500](https://github.com/n24q02m/wet-mcp/pull/1500),
  [`dd06178`](https://github.com/n24q02m/wet-mcp/commit/dd0617851a3335a4bb214a2ab991a95233f5ab45))


## v3.4.1 (2026-07-05)


## v3.4.1-beta.1 (2026-07-05)

### Bug Fixes

- Explain Workers Paid plan requirement in README deploy prerequisites
  ([#1479](https://github.com/n24q02m/wet-mcp/pull/1479),
  [`848690f`](https://github.com/n24q02m/wet-mcp/commit/848690f083e3a34ee43060989663727de80344e3))

- Skip heading regex for non-# lines in markdown chunking
  ([`80590bf`](https://github.com/n24q02m/wet-mcp/commit/80590bfff3ee56a72034d33d6707a403f0e6a3c5))

- Substitute PUBLIC_URL and drop routes in cf-deploy.mjs fallback config
  ([#1479](https://github.com/n24q02m/wet-mcp/pull/1479),
  [`848690f`](https://github.com/n24q02m/wet-mcp/commit/848690f083e3a34ee43060989663727de80344e3))

- Substitute YOUR_WORKER_DOMAIN route pattern from PUBLIC_URL host in cf-deploy.mjs
  ([#1479](https://github.com/n24q02m/wet-mcp/pull/1479),
  [`848690f`](https://github.com/n24q02m/wet-mcp/commit/848690f083e3a34ee43060989663727de80344e3))

- Target passage windows near matched query terms
  ([`5d04261`](https://github.com/n24q02m/wet-mcp/commit/5d04261960f8f880971afc95cdd64ab821f446df))

- Use placeholders for PUBLIC_URL and routes in wrangler.jsonc (BYO-generic)
  ([#1479](https://github.com/n24q02m/wet-mcp/pull/1479),
  [`848690f`](https://github.com/n24q02m/wet-mcp/commit/848690f083e3a34ee43060989663727de80344e3))

- **deps**: Lock file maintenance
  ([`99d6e2b`](https://github.com/n24q02m/wet-mcp/commit/99d6e2bb4432222b2dfa1e4343fb0fcf2f4707f6))

- **deps**: Update docker/login-action digest to af1e73f
  ([`b7e1489`](https://github.com/n24q02m/wet-mcp/commit/b7e1489b88b49ccbb853a31a8de3f1e5df880e56))

- **deps**: Update non-major dependencies ([#1472](https://github.com/n24q02m/wet-mcp/pull/1472),
  [`b50cef8`](https://github.com/n24q02m/wet-mcp/commit/b50cef81ffd06b010f359430084e7fa42edd50ba))

### Chores

- **deps**: Update docker/build-push-action digest to 53b7df9
  ([#1471](https://github.com/n24q02m/wet-mcp/pull/1471),
  [`ae2934b`](https://github.com/n24q02m/wet-mcp/commit/ae2934bfd3bdbddecf873709360e713f6cde7a47))

- **deps**: Update docker/setup-buildx-action digest to bb05f3f
  ([#1481](https://github.com/n24q02m/wet-mcp/pull/1481),
  [`3352942`](https://github.com/n24q02m/wet-mcp/commit/335294293812c5f9e688effbddb037ede4b740d3))


## v3.4.0 (2026-07-02)

### Bug Fixes

- Bump mcp-core to 1.18.1 ([#1478](https://github.com/n24q02m/wet-mcp/pull/1478),
  [`0ec45c5`](https://github.com/n24q02m/wet-mcp/commit/0ec45c55152037ff74561240a4e897a73a47f908))

### Features

- Document vertex_express provider option ([#1476](https://github.com/n24q02m/wet-mcp/pull/1476),
  [`be304b1`](https://github.com/n24q02m/wet-mcp/commit/be304b1bd9d208aaaa6f5b9e6e4bc890e309a2cc))


## v3.4.0-beta.2 (2026-07-02)

### Bug Fixes

- Bun install in deploy-cf so wrangler can bundle worker.ts
  ([#1475](https://github.com/n24q02m/wet-mcp/pull/1475),
  [`e6daa20`](https://github.com/n24q02m/wet-mcp/commit/e6daa20d3fbf0c666b3640517ccf45c83b91512c))


## v3.4.0-beta.1 (2026-07-02)

### Bug Fixes

- Assert rendered deploy template via parsed JSON not url substring
  ([#1474](https://github.com/n24q02m/wet-mcp/pull/1474),
  [`1b2e253`](https://github.com/n24q02m/wet-mcp/commit/1b2e253bb80e0059df7a1192d32bf229a31db29d))

- Run deploy-cf on beta releases too so a beta dispatch redeploys CF
  ([#1474](https://github.com/n24q02m/wet-mcp/pull/1474),
  [`1b2e253`](https://github.com/n24q02m/wet-mcp/commit/1b2e253bb80e0059df7a1192d32bf229a31db29d))

### Features

- Deploy CF Worker+Container on stable release from cd.yml
  ([#1474](https://github.com/n24q02m/wet-mcp/pull/1474),
  [`1b2e253`](https://github.com/n24q02m/wet-mcp/commit/1b2e253bb80e0059df7a1192d32bf229a31db29d))


## v3.3.1-beta.1 (2026-07-01)

### Bug Fixes

- Add Vertex AI (Express) API key field to relay schema
  ([#1469](https://github.com/n24q02m/wet-mcp/pull/1469),
  [`0884c18`](https://github.com/n24q02m/wet-mcp/commit/0884c183526db99224aa50023cb693b8fda4eeea))

- Add vertex ai (express) support to the relay credential form
  ([#1469](https://github.com/n24q02m/wet-mcp/pull/1469),
  [`0884c18`](https://github.com/n24q02m/wet-mcp/commit/0884c183526db99224aa50023cb693b8fda4eeea))

- Bump mcp-core to 1.18.1b1 for the vertex relay dropdown fix
  ([#1470](https://github.com/n24q02m/wet-mcp/pull/1470),
  [`c9a818e`](https://github.com/n24q02m/wet-mcp/commit/c9a818e255e551a390b068989cab1b48ab5eea9e))

- Recognize the Vertex Express key as a configured cloud credential
  ([#1469](https://github.com/n24q02m/wet-mcp/pull/1469),
  [`0884c18`](https://github.com/n24q02m/wet-mcp/commit/0884c183526db99224aa50023cb693b8fda4eeea))


## v3.3.0 (2026-07-01)


## v3.3.0-beta.26 (2026-07-01)

### Bug Fixes

- Downgrade wet-mcp CF instance_type to basic now that the slim image fits
  ([#1465](https://github.com/n24q02m/wet-mcp/pull/1465),
  [`52537dc`](https://github.com/n24q02m/wet-mcp/commit/52537dc5dc76691562ea617f34be76f925ed7ad4))


## v3.3.0-beta.25 (2026-07-01)

### Bug Fixes

- Document browserless render backend and BROWSER_BACKENDS config
  ([#1464](https://github.com/n24q02m/wet-mcp/pull/1464),
  [`528ef12`](https://github.com/n24q02m/wet-mcp/commit/528ef12e0089e7ca28f39d433b2d55247b115294))

- **deps**: Update non-major dependencies ([#1461](https://github.com/n24q02m/wet-mcp/pull/1461),
  [`8e0580c`](https://github.com/n24q02m/wet-mcp/commit/8e0580cda208bdb076da3dd325375c7f6c952b4f))

### Chores

- **deps**: Update ghcr.io/astral-sh/uv:latest docker digest to 3d868e5
  ([#1460](https://github.com/n24q02m/wet-mcp/pull/1460),
  [`7b2b34e`](https://github.com/n24q02m/wet-mcp/commit/7b2b34e95865d28cbadefa9124ebd78aa26a73f4))


## v3.3.0-beta.24 (2026-06-30)

### Bug Fixes

- Add test for detect_llm_provider_key ([#1443](https://github.com/n24q02m/wet-mcp/pull/1443),
  [`6fb644c`](https://github.com/n24q02m/wet-mcp/commit/6fb644c800b8cf3b4ef1aa10cf3e7b4ae35dc3c3))

- Add test for except path in embedder ([#1444](https://github.com/n24q02m/wet-mcp/pull/1444),
  [`2c57e7e`](https://github.com/n24q02m/wet-mcp/commit/2c57e7e3c830b5c557311580906f732ab1c059ec))

- Add test for except path in server ([#1441](https://github.com/n24q02m/wet-mcp/pull/1441),
  [`ab5cff1`](https://github.com/n24q02m/wet-mcp/commit/ab5cff110f153456eb3e87edcb63b5f228d304c7))

- Add test for rerank_chain_for_creds ([#1433](https://github.com/n24q02m/wet-mcp/pull/1433),
  [`4f7a3c6`](https://github.com/n24q02m/wet-mcp/commit/4f7a3c6f88ed44828c652c07d7fc71da3c6bcead))

- Batch execute-script loop to avoid N+1 ([#1447](https://github.com/n24q02m/wet-mcp/pull/1447),
  [`faf75a3`](https://github.com/n24q02m/wet-mcp/commit/faf75a36db13003ad8798e74989ce03bffeae312))

- Batch vector search result fetch to avoid N+1
  ([#1435](https://github.com/n24q02m/wet-mcp/pull/1435),
  [`4c5fc64`](https://github.com/n24q02m/wet-mcp/commit/4c5fc641db6ffcf0267997ca4428996140a766e7))

- Canary Gate-A/B settle-retry to avoid false-fail on slow container startup
  ([#1450](https://github.com/n24q02m/wet-mcp/pull/1450),
  [`3b834a5`](https://github.com/n24q02m/wet-mcp/commit/3b834a504501044186294beb71d48160242102b7))

- Collapse OAuth + per-sub routing to one DO (resolve max_instances=1 deadlock)
  ([#1458](https://github.com/n24q02m/wet-mcp/pull/1458),
  [`fb27101`](https://github.com/n24q02m/wet-mcp/commit/fb271016e077bf47afff6fb483592276d6aab042))

- Extract add_chunks helpers for readability ([#1439](https://github.com/n24q02m/wet-mcp/pull/1439),
  [`e925347`](https://github.com/n24q02m/wet-mcp/commit/e9253477d1996d9a76b6533f29b4c6b4e0b196d1))

- Extract import_jsonl per-entity helpers for readability
  ([#1438](https://github.com/n24q02m/wet-mcp/pull/1438),
  [`30e09a0`](https://github.com/n24q02m/wet-mcp/commit/30e09a03d262746251a1b1b6397f66f9c2dbf8bd))

- Extract search FTS/vec/adjacent helpers for readability
  ([#1445](https://github.com/n24q02m/wet-mcp/pull/1445),
  [`50c574c`](https://github.com/n24q02m/wet-mcp/commit/50c574cb6c15cfcca65ae3bb9bd32cf675a6692e))

- Extract upsert_library insert/update helpers for readability
  ([#1437](https://github.com/n24q02m/wet-mcp/pull/1437),
  [`8199114`](https://github.com/n24q02m/wet-mcp/commit/8199114d46798df65c055e38840d302e1b093ad0))

- Pass query_docs optional args via DocsQueryOptions dataclass
  ([#1440](https://github.com/n24q02m/wet-mcp/pull/1440),
  [`58bba73`](https://github.com/n24q02m/wet-mcp/commit/58bba73af98bccc2f16a6b28f8b85537a68c8b6b))

- Prefer self-hosted browserless over CF Browser Rendering in CF deploy
  ([#1459](https://github.com/n24q02m/wet-mcp/pull/1459),
  [`1cb8f92`](https://github.com/n24q02m/wet-mcp/commit/1cb8f927293e144ddb91556e76430c7df0169e89))

- Route OAuth /token refresh to the sub's DO to avoid max_instances=1 deadlock
  ([#1452](https://github.com/n24q02m/wet-mcp/pull/1452),
  [`cd7f169`](https://github.com/n24q02m/wet-mcp/commit/cd7f169fe362ff94e958ad069880572fe0fd6a89))

- SLIM build drops all 3 local capability legs + fix .dockerignore context bloat
  ([#1457](https://github.com/n24q02m/wet-mcp/pull/1457),
  [`665c44d`](https://github.com/n24q02m/wet-mcp/commit/665c44d05bdddabb76614fe5d893a2bd25990aa4))

- Slim CF container by offloading the browser to remote backends
  ([#1451](https://github.com/n24q02m/wet-mcp/pull/1451),
  [`1bd0eb0`](https://github.com/n24q02m/wet-mcp/commit/1bd0eb04d4e6ad12443ecd399471f536b85687ae))

- Split save_credentials into multi-user/single-user helpers
  ([#1449](https://github.com/n24q02m/wet-mcp/pull/1449),
  [`dece6f3`](https://github.com/n24q02m/wet-mcp/commit/dece6f38f4700cf257c1f750d6d7280643f12932))

- Update dependency @cloudflare/workers-types to ^4.20260630.1
  ([`1eea087`](https://github.com/n24q02m/wet-mcp/commit/1eea087eee4b029866b59ab0f16534369bdd482b))

- Use literal ALTER statements in libraries migration (B608)
  ([`8a51032`](https://github.com/n24q02m/wet-mcp/commit/8a51032eb31fc59dd538f2044a1448b1523ec603))


## v3.3.0-beta.23 (2026-06-29)

### Bug Fixes

- Bound concurrency for CPU-bound markdown chunking
  ([`015d6b6`](https://github.com/n24q02m/wet-mcp/commit/015d6b640059824c0a9d849f511a1ff3e5a5072d))

- Cap max_instances=1 for CF container cost (solo dev default)
  ([`f0f3280`](https://github.com/n24q02m/wet-mcp/commit/f0f32803a64aa2d9350be32ae0fa8d43a6e75738))

- Force real litellm to win unclecode-litellm file collision to restore catalog/LLM
  ([`f0f3280`](https://github.com/n24q02m/wet-mcp/commit/f0f32803a64aa2d9350be32ae0fa8d43a6e75738))

- Streamline doc-cleaning pipeline (avoid redundant string allocations)
  ([`dc44815`](https://github.com/n24q02m/wet-mcp/commit/dc448158b9638b5b1c0abe13e558501bb40a6b02))

- Update ghcr.io/astral-sh/uv:latest docker digest
  ([`216e3cf`](https://github.com/n24q02m/wet-mcp/commit/216e3cf5036dcbc3e89b485cff0658792f8b8e8e))

- Update non-major dependencies
  ([`9ef5882`](https://github.com/n24q02m/wet-mcp/commit/9ef5882ece6366f53dc7a90a86ee05fc99f0d97c))

### Chores

- **deps**: Lock file maintenance ([#1415](https://github.com/n24q02m/wet-mcp/pull/1415),
  [`0b93bb5`](https://github.com/n24q02m/wet-mcp/commit/0b93bb555c0b4e4920f00d6c1a4c895ed3081cb1))

- **deps**: Update actions/setup-python digest to ece7cb0
  ([#1421](https://github.com/n24q02m/wet-mcp/pull/1421),
  [`8383b00`](https://github.com/n24q02m/wet-mcp/commit/8383b006c5e0696f90ac7c28669a5392535b4371))

- **deps**: Update python:3.13-slim-bookworm docker digest to fcbd8df
  ([#1422](https://github.com/n24q02m/wet-mcp/pull/1422),
  [`31ee725`](https://github.com/n24q02m/wet-mcp/commit/31ee725e42aa27ed0768a5b76f9654aca0219563))


## v3.3.0-beta.22 (2026-06-23)

### Bug Fixes

- Bump mcp-core to 1.18.0b20 (relay catalog Jina/normalize + keyword)
  ([#1417](https://github.com/n24q02m/wet-mcp/pull/1417),
  [`1e7df27`](https://github.com/n24q02m/wet-mcp/commit/1e7df27b1b75eab35640e56fc77fc60f2cc360a3))

- Bump mcp-core to 1.18.0b20 for relay catalog + drop hardcoded suggestions
  ([#1417](https://github.com/n24q02m/wet-mcp/pull/1417),
  [`1e7df27`](https://github.com/n24q02m/wet-mcp/commit/1e7df27b1b75eab35640e56fc77fc60f2cc360a3))

### Features

- Drop hardcoded model suggestions; relay dropdown is now catalog-driven
  ([#1417](https://github.com/n24q02m/wet-mcp/pull/1417),
  [`1e7df27`](https://github.com/n24q02m/wet-mcp/commit/1e7df27b1b75eab35640e56fc77fc60f2cc360a3))


## v3.3.0-beta.21 (2026-06-22)

### Bug Fixes

- Force real litellm to win unclecode-litellm file collision to restore catalog/LLM
  ([#1413](https://github.com/n24q02m/wet-mcp/pull/1413),
  [`ddca53d`](https://github.com/n24q02m/wet-mcp/commit/ddca53dab0c959c298018f7ac3837d53f61746e1))


## v3.3.0-beta.20 (2026-06-22)

### Bug Fixes

- Bump mcp-core to 1.18.0b19 (relay model-search catalog + OAuth refresh-TTL)
  ([#1412](https://github.com/n24q02m/wet-mcp/pull/1412),
  [`4137709`](https://github.com/n24q02m/wet-mcp/commit/4137709ad8f16fc38042f07c03a866d3f8f7f301))


## v3.3.0-beta.19 (2026-06-22)

### Bug Fixes

- Correct README doc rot from bot-PR + migration churn
  ([#1409](https://github.com/n24q02m/wet-mcp/pull/1409),
  [`e63ad53`](https://github.com/n24q02m/wet-mcp/commit/e63ad5355b65737babf5e078907192d2a4a38e6b))

- Pin CF container max_instances to 3 ([#1411](https://github.com/n24q02m/wet-mcp/pull/1411),
  [`f8a3dec`](https://github.com/n24q02m/wet-mcp/commit/f8a3dec16b79fb41260d3d3730d40a2229dec42f))

### Chores

- **deps**: Lock file maintenance ([#1410](https://github.com/n24q02m/wet-mcp/pull/1410),
  [`5726a74`](https://github.com/n24q02m/wet-mcp/commit/5726a747435dd89fc107c1d69779c4339792349f))


## v3.3.0-beta.18 (2026-06-21)

### Bug Fixes

- Add cf:deploy script for live wrangler deploy
  ([#1407](https://github.com/n24q02m/wet-mcp/pull/1407),
  [`36fd28c`](https://github.com/n24q02m/wet-mcp/commit/36fd28c24d3ec8e4883761241702226c726a5bf4))

- Annotate e2e env dict[str, str] for ty 0.0.51 Popen overload
  ([#1394](https://github.com/n24q02m/wet-mcp/pull/1394),
  [`47dc0c3`](https://github.com/n24q02m/wet-mcp/commit/47dc0c3bb32d17122854fc2bac9d6967ea0d8213))

- Drop env-derived value from cf_deploy log (CodeQL js/clear-text-logging)
  ([#1407](https://github.com/n24q02m/wet-mcp/pull/1407),
  [`36fd28c`](https://github.com/n24q02m/wet-mcp/commit/36fd28c24d3ec8e4883761241702226c726a5bf4))

- Keep wet container on standard-1 (basic 4GB disk too small for crawl4ai image); sleepAfter=5m
  carries the idle-cost win ([#1408](https://github.com/n24q02m/wet-mcp/pull/1408),
  [`4803f97`](https://github.com/n24q02m/wet-mcp/commit/4803f970c5f6751220586c636bf82fa76fd6bc7e))

- Key-gate the wet LLM default chain (no keyless cloud model)
  ([#1402](https://github.com/n24q02m/wet-mcp/pull/1402),
  [`96c7b65`](https://github.com/n24q02m/wet-mcp/commit/96c7b65bcd8160033658a9a5fd0e87d5e441785f))

- Make LLM gate + embed/rerank backend sub-aware in multi-user
  ([#1405](https://github.com/n24q02m/wet-mcp/pull/1405),
  [`d04e075`](https://github.com/n24q02m/wet-mcp/commit/d04e07595bd3687cf7c1bf30307ec41654f6f773))

- Resolve per-sub api_key in dispatch instead of mutating os.environ
  ([#1401](https://github.com/n24q02m/wet-mcp/pull/1401),
  [`e11b1be`](https://github.com/n24q02m/wet-mcp/commit/e11b1be6c6c3337463b5a7e722ed5bc6d7699fbd))

- Rightsize CF container to fit $10 budget ([#1406](https://github.com/n24q02m/wet-mcp/pull/1406),
  [`b96b21f`](https://github.com/n24q02m/wet-mcp/commit/b96b21f4ca1c2104287255902aec84fb22d70d03))

- Surface SearXNG URL field on relay + skip GDrive device-code on Cloudflare
  ([#1403](https://github.com/n24q02m/wet-mcp/pull/1403),
  [`c222069`](https://github.com/n24q02m/wet-mcp/commit/c2220697d431ff69f9926abaa72c8c5eb7d9ed42))

- **deps**: Update non-major dependencies ([#1392](https://github.com/n24q02m/wet-mcp/pull/1392),
  [`9894870`](https://github.com/n24q02m/wet-mcp/commit/9894870d118d5c5e6049bd0ba28d4294fd75ac73))

### Chores

- **deps**: Bump the uv group across 1 directory with 2 updates
  ([#1404](https://github.com/n24q02m/wet-mcp/pull/1404),
  [`236c612`](https://github.com/n24q02m/wet-mcp/commit/236c612dfc40a812e1f2deedcd3e9c53d5bbdea5))

- **deps**: Lock file maintenance ([#1394](https://github.com/n24q02m/wet-mcp/pull/1394),
  [`47dc0c3`](https://github.com/n24q02m/wet-mcp/commit/47dc0c3bb32d17122854fc2bac9d6967ea0d8213))

- **deps**: Update actions/checkout action to v7
  ([#1393](https://github.com/n24q02m/wet-mcp/pull/1393),
  [`602dd24`](https://github.com/n24q02m/wet-mcp/commit/602dd24a1408f9eb800cfe7947a30578ccdd2e91))

- **deps**: Update dependency langsmith to v0.8.18 [security]
  ([#1398](https://github.com/n24q02m/wet-mcp/pull/1398),
  [`4d49575`](https://github.com/n24q02m/wet-mcp/commit/4d495754034aa1349de7d3069f4652500a901b41))

- **deps**: Update ghcr.io/astral-sh/uv:latest docker digest to d0a0a75
  ([#1391](https://github.com/n24q02m/wet-mcp/pull/1391),
  [`11be254`](https://github.com/n24q02m/wet-mcp/commit/11be254635933300601db26b41623c716fa63ba4))


## v3.3.0-beta.17 (2026-06-20)

### Bug Fixes

- Treat reachable SearXNG (401/403) as healthy + stop test_server spawning real SearXNG
  ([`aa87c30`](https://github.com/n24q02m/wet-mcp/commit/aa87c3072895eb34ece2186995d61ba973afc1cc))


## v3.3.0-beta.16 (2026-06-19)

### Bug Fixes

- Read SEARXNG_AUTH_USER/PASS and apply basic-auth to external SearXNG
  ([`450dd1e`](https://github.com/n24q02m/wet-mcp/commit/450dd1e1b0832043c5925fd7e7d40b626c4edb32))


## v3.3.0-beta.15 (2026-06-19)

### Features

- Rotate search-provider API keys on rate-limit (CSV multi-key)
  ([`8cdd1e4`](https://github.com/n24q02m/wet-mcp/commit/8cdd1e47cc20d3b9c0cc627f46077d5b3396f135))


## v3.3.0-beta.14 (2026-06-19)

### Features

- Forward capability-chain env vars into the CF container
  ([#1388](https://github.com/n24q02m/wet-mcp/pull/1388),
  [`1d2ec19`](https://github.com/n24q02m/wet-mcp/commit/1d2ec193a48f0a8c25e1222db28ac93ff2d80164))


## v3.3.0-beta.13 (2026-06-19)

### Bug Fixes

- Make canary gate utf-8-safe (decode+encode) and Cloudflare-UA-aware
  ([`e01dd96`](https://github.com/n24q02m/wet-mcp/commit/e01dd96e7b186053bc190c4aeab16acb91849316))

- Make canary gate utf-8-safe and Cloudflare-UA-aware
  ([`e01dd96`](https://github.com/n24q02m/wet-mcp/commit/e01dd96e7b186053bc190c4aeab16acb91849316))

- Neutral default endpoint + env-first secrets in CF self-host scripts
  ([`67ac018`](https://github.com/n24q02m/wet-mcp/commit/67ac01862ebc4fe3ffef53a7a213cc0b4e69874c))

- Use contextlib.suppress for stdout reconfigure (SIM105)
  ([`e01dd96`](https://github.com/n24q02m/wet-mcp/commit/e01dd96e7b186053bc190c4aeab16acb91849316))

### Features

- Capability provider chains for search + browser + disable-local toggles
  ([#1386](https://github.com/n24q02m/wet-mcp/pull/1386),
  [`58d3204`](https://github.com/n24q02m/wet-mcp/commit/58d3204197cee4d65b63ea22a2434b642f9c3529))

- Enable username-stable-sub workspace bucket
  ([`4fd3e29`](https://github.com/n24q02m/wet-mcp/commit/4fd3e29b99a057752c4e94deca81f1b94fb3c2a6))


## v3.3.0-beta.12 (2026-06-18)

### Bug Fixes

- Add coverage for embedding serialization error paths in db.py
  ([`ff0d656`](https://github.com/n24q02m/wet-mcp/commit/ff0d6562ab0da42466de10783e7ba85854ea49f0))

- Add post-deploy canary gate with auto-rollback to deploy_cf.py
  ([`131da2d`](https://github.com/n24q02m/wet-mcp/commit/131da2d5d01aa47237158e68e397db0afbeed291))

- Add stats() to DocsDBCfBackend so config(status) works on Cloudflare
  ([#1379](https://github.com/n24q02m/wet-mcp/pull/1379),
  [`28e9387`](https://github.com/n24q02m/wet-mcp/commit/28e9387f72f0783d21061a8ff81123b0d19a3de0))

- Coerce non-list locked_libraries to empty list in get_project_context
  ([`fe72946`](https://github.com/n24q02m/wet-mcp/commit/fe729460cdc755fbca5aa7da16223b067756921b))

- Collapse chunk quality scoring into a single content pass
  ([`d1587ca`](https://github.com/n24q02m/wet-mcp/commit/d1587cac23731bb934e80ca14e794ff21004d837))

- Compare mcp-core pin floor as version, not brittle substring
  ([#1374](https://github.com/n24q02m/wet-mcp/pull/1374),
  [`642765f`](https://github.com/n24q02m/wet-mcp/commit/642765f51f969a4b5519e681fe5e6aee0fe615aa))

- Cover searxng patch early-return branches when package dir is missing
  ([`475945b`](https://github.com/n24q02m/wet-mcp/commit/475945b92ffba541e57d8b0f8f654d43f2f4f221))

- Document CF deploy errata (containers delete by ID, relay-password namespace compose)
  ([#1373](https://github.com/n24q02m/wet-mcp/pull/1373),
  [`7ebd7a8`](https://github.com/n24q02m/wet-mcp/commit/7ebd7a835eaebe885c12ee79dfb8fce7ff266a33))

- Prefix unused account var to satisfy RUF059
  ([`131da2d`](https://github.com/n24q02m/wet-mcp/commit/131da2d5d01aa47237158e68e397db0afbeed291))

- Refresh lockfile (renovate maintenance)
  ([`67c8759`](https://github.com/n24q02m/wet-mcp/commit/67c8759b8c44c03b5a8109cd6ec79ffd22781a4c))

- Update non-major dependencies
  ([`0c58478`](https://github.com/n24q02m/wet-mcp/commit/0c58478ca84ec45e920bcc7a43c3cdd11e0d1d4a))

- Update non-major dependencies
  ([`cf05359`](https://github.com/n24q02m/wet-mcp/commit/cf0535906400f37118c13a85e29e0f92b46d511c))

- Update typescript to v6
  ([`1eb4823`](https://github.com/n24q02m/wet-mcp/commit/1eb482346a343e0ad7c562c480bc308421900c24))

### Features

- Add post-deploy canary gate with auto-rollback to deploy_cf.py
  ([`131da2d`](https://github.com/n24q02m/wet-mcp/commit/131da2d5d01aa47237158e68e397db0afbeed291))

### Testing

- **db**: Add coverage for embedding serialization error paths
  ([`ff0d656`](https://github.com/n24q02m/wet-mcp/commit/ff0d6562ab0da42466de10783e7ba85854ea49f0))


## v3.3.0-beta.11 (2026-06-15)

### Bug Fixes

- Correct CF deploy template (managed-registry image push, top-level route, searxng secrets)
  ([#1371](https://github.com/n24q02m/wet-mcp/pull/1371),
  [`109aec0`](https://github.com/n24q02m/wet-mcp/commit/109aec071e7d1e6f11c7d090e484a3398e2f3f6a))

- Correct CF deploy template (managed-registry image, top-level route, searxng secrets)
  ([#1371](https://github.com/n24q02m/wet-mcp/pull/1371),
  [`109aec0`](https://github.com/n24q02m/wet-mcp/commit/109aec071e7d1e6f11c7d090e484a3398e2f3f6a))

- Dispatch worker outbound handlers by internal hostname
  ([#1372](https://github.com/n24q02m/wet-mcp/pull/1372),
  [`78a76b8`](https://github.com/n24q02m/wet-mcp/commit/78a76b8271592a02149c170ff8c860c9a09e7d35))

- Forward container env (storage backends, model chains, secrets) in CF worker
  ([#1371](https://github.com/n24q02m/wet-mcp/pull/1371),
  [`109aec0`](https://github.com/n24q02m/wet-mcp/commit/109aec071e7d1e6f11c7d090e484a3398e2f3f6a))

- Forward container env (storage backends, model chains, secrets) in CF worker
  ([#1370](https://github.com/n24q02m/wet-mcp/pull/1370),
  [`c22f07b`](https://github.com/n24q02m/wet-mcp/commit/c22f07b5970ef3f2b2fb01d626061499769db377))

- Keep outbound handlers off the public fetch entrypoint
  ([#1372](https://github.com/n24q02m/wet-mcp/pull/1372),
  [`78a76b8`](https://github.com/n24q02m/wet-mcp/commit/78a76b8271592a02149c170ff8c860c9a09e7d35))

- Point CF container image at :beta (has CF code + mcp-core b5)
  ([#1371](https://github.com/n24q02m/wet-mcp/pull/1371),
  [`109aec0`](https://github.com/n24q02m/wet-mcp/commit/109aec071e7d1e6f11c7d090e484a3398e2f3f6a))

- Point CF container image at :beta (has CF code + mcp-core b5)
  ([#1370](https://github.com/n24q02m/wet-mcp/pull/1370),
  [`c22f07b`](https://github.com/n24q02m/wet-mcp/commit/c22f07b5970ef3f2b2fb01d626061499769db377))

- Route CF container outbound to Worker bindings
  ([#1371](https://github.com/n24q02m/wet-mcp/pull/1371),
  [`109aec0`](https://github.com/n24q02m/wet-mcp/commit/109aec071e7d1e6f11c7d090e484a3398e2f3f6a))

- Run wet-mcp correctly inside Cloudflare Containers
  ([#1371](https://github.com/n24q02m/wet-mcp/pull/1371),
  [`109aec0`](https://github.com/n24q02m/wet-mcp/commit/109aec071e7d1e6f11c7d090e484a3398e2f3f6a))

- Use searxng search backend for CF wet (reuse self-hosted instance)
  ([#1371](https://github.com/n24q02m/wet-mcp/pull/1371),
  [`109aec0`](https://github.com/n24q02m/wet-mcp/commit/109aec071e7d1e6f11c7d090e484a3398e2f3f6a))

- Use searxng search backend for CF wet (reuse self-hosted instance)
  ([#1370](https://github.com/n24q02m/wet-mcp/pull/1370),
  [`c22f07b`](https://github.com/n24q02m/wet-mcp/commit/c22f07b5970ef3f2b2fb01d626061499769db377))

### Features

- Add kv.internal __ready readiness probe to gate first credential write
  ([#1372](https://github.com/n24q02m/wet-mcp/pull/1372),
  [`78a76b8`](https://github.com/n24q02m/wet-mcp/commit/78a76b8271592a02149c170ff8c860c9a09e7d35))

- Bump mcp-core to 1.18.0b6 for CfKvBackend.ready() probe
  ([#1372](https://github.com/n24q02m/wet-mcp/pull/1372),
  [`78a76b8`](https://github.com/n24q02m/wet-mcp/commit/78a76b8271592a02149c170ff8c860c9a09e7d35))

- Freeze CF worker template + document copy-from-wet contract
  ([#1372](https://github.com/n24q02m/wet-mcp/pull/1372),
  [`78a76b8`](https://github.com/n24q02m/wet-mcp/commit/78a76b8271592a02149c170ff8c860c9a09e7d35))

- Gate first credential PUT on CF KV readiness probe
  ([#1372](https://github.com/n24q02m/wet-mcp/pull/1372),
  [`78a76b8`](https://github.com/n24q02m/wet-mcp/commit/78a76b8271592a02149c170ff8c860c9a09e7d35))

- Harden CF worker template (E.1 readiness probe + E.2 single-user DO/poll)
  ([#1372](https://github.com/n24q02m/wet-mcp/pull/1372),
  [`78a76b8`](https://github.com/n24q02m/wet-mcp/commit/78a76b8271592a02149c170ff8c860c9a09e7d35))

- Lock explicit single-user idFromName(default) DO contract
  ([#1372](https://github.com/n24q02m/wet-mcp/pull/1372),
  [`78a76b8`](https://github.com/n24q02m/wet-mcp/commit/78a76b8271592a02149c170ff8c860c9a09e7d35))

- Poll credential key read-back before reporting setup success
  ([#1372](https://github.com/n24q02m/wet-mcp/pull/1372),
  [`78a76b8`](https://github.com/n24q02m/wet-mcp/commit/78a76b8271592a02149c170ff8c860c9a09e7d35))


## v3.3.0-beta.10 (2026-06-15)

### Bug Fixes

- Bump mcp-core to 1.18.0b5 for vertex_express support
  ([#1369](https://github.com/n24q02m/wet-mcp/pull/1369),
  [`651c286`](https://github.com/n24q02m/wet-mcp/commit/651c286a0f407c1b6c1b703619f14d0a2ac7c9c7))

- Correct credential storage and relay/auth claims in architecture docs
  ([#1369](https://github.com/n24q02m/wet-mcp/pull/1369),
  [`651c286`](https://github.com/n24q02m/wet-mcp/commit/651c286a0f407c1b6c1b703619f14d0a2ac7c9c7))


## v3.3.0-beta.9 (2026-06-15)

### Bug Fixes

- Clarify embedding-model switch requires reindex (B2 guard)
  ([#1341](https://github.com/n24q02m/wet-mcp/pull/1341),
  [`c853ee9`](https://github.com/n24q02m/wet-mcp/commit/c853ee99358c0c3d26e20b2f74d082f3152b7f9a))

- Correct credential storage and relay/auth claims in architecture docs
  ([`b5b876a`](https://github.com/n24q02m/wet-mcp/commit/b5b876a36cbdd767e51310bc8e5802e1b2828abd))

- Optimize _extract_passage sliding window search
  ([#1327](https://github.com/n24q02m/wet-mcp/pull/1327),
  [`1518453`](https://github.com/n24q02m/wet-mcp/commit/1518453c0435771d97b1b9a9db8490b4eeefd28c))

- Optimize whitespace stripping with native string operations
  ([#1339](https://github.com/n24q02m/wet-mcp/pull/1339),
  [`34b5902`](https://github.com/n24q02m/wet-mcp/commit/34b5902cfbe39eb1aa4608f0af967d74ad1b518e))

- **deps**: Update ghcr.io/astral-sh/uv:latest docker digest to ff07b86
  ([#1340](https://github.com/n24q02m/wet-mcp/pull/1340),
  [`244a71a`](https://github.com/n24q02m/wet-mcp/commit/244a71a898f3100a5ba6238f867f4815a97b72c2))

- **deps**: Update non-major dependencies ([#1338](https://github.com/n24q02m/wet-mcp/pull/1338),
  [`76ccbe0`](https://github.com/n24q02m/wet-mcp/commit/76ccbe0c1bdf0b1f47d080f1e06e32b32849a6b8))

- **deps**: Update python:3.13-slim-bookworm docker digest to 05b9539
  ([#1337](https://github.com/n24q02m/wet-mcp/pull/1337),
  [`a2da219`](https://github.com/n24q02m/wet-mcp/commit/a2da2193004f318193a6ec7c39f9ebed4d7824e7))

### Features

- Cloudflare serverless deployment (Phase 2 pilot)
  ([`7d8a194`](https://github.com/n24q02m/wet-mcp/commit/7d8a194509a966fa4a381d993c77d42b28e9e041))


## v3.3.0-beta.8 (2026-06-12)

### Bug Fixes

- Sync README tagline to current capability description
  ([#1333](https://github.com/n24q02m/wet-mcp/pull/1333),
  [`3090464`](https://github.com/n24q02m/wet-mcp/commit/3090464a94c390769ba9999d960d58b931a0b428))

### Features

- Register a BYO local reranker via CustomRerankerSpec
  ([#1335](https://github.com/n24q02m/wet-mcp/pull/1335),
  [`7084531`](https://github.com/n24q02m/wet-mcp/commit/708453118e30b9990a3d93c9f859507790f9c33a))

- Sync cross-promo section ([#1334](https://github.com/n24q02m/wet-mcp/pull/1334),
  [`a04cca8`](https://github.com/n24q02m/wet-mcp/commit/a04cca8d2081b2521353f558556cdbfa1d4866c9))


## v3.3.0-beta.7 (2026-06-12)

### Features

- Guard docs vector store against embedding-model mismatch with opt-in reindex
  ([#1332](https://github.com/n24q02m/wet-mcp/pull/1332),
  [`049ffb1`](https://github.com/n24q02m/wet-mcp/commit/049ffb138a173420769992724e9de406b382b6c0))


## v3.3.0-beta.6 (2026-06-12)

### Bug Fixes

- Decouple wet from web-core private SSRF internals, bump web-core to 2.2.x
  ([#1325](https://github.com/n24q02m/wet-mcp/pull/1325),
  [`61d671d`](https://github.com/n24q02m/wet-mcp/commit/61d671db2d4c92c5ef015ba39516a43d95309ee6))

- Remove orphaned Qodo pr-agent config ([#1326](https://github.com/n24q02m/wet-mcp/pull/1326),
  [`99b8970`](https://github.com/n24q02m/wet-mcp/commit/99b897094f94a58788497675c219877dd8e38b0f))

- Restore PSR changelog generation and backfill version history
  ([#1328](https://github.com/n24q02m/wet-mcp/pull/1328),
  [`8a96c2e`](https://github.com/n24q02m/wet-mcp/commit/8a96c2e23bc7cadcb061ce88bb338903b5d750b1))

- Retrigger CI for web-core decouple ([#1325](https://github.com/n24q02m/wet-mcp/pull/1325),
  [`61d671d`](https://github.com/n24q02m/wet-mcp/commit/61d671db2d4c92c5ef015ba39516a43d95309ee6))

- Sweep priority-router language from docs and plugin manifest
  ([#1329](https://github.com/n24q02m/wet-mcp/pull/1329),
  [`c5887e6`](https://github.com/n24q02m/wet-mcp/commit/c5887e673dc17d28c7d5be42b398ccc1652c7955))

### Features

- Allow overriding the local embed/rerank model via env
  ([#1330](https://github.com/n24q02m/wet-mcp/pull/1330),
  [`5135390`](https://github.com/n24q02m/wet-mcp/commit/5135390e1c3e2188080852bc1aa9021427b26d1f))


## v3.3.0-beta.5 (2026-06-11)

### Bug Fixes

- Default local reranker to YesNo ONNX variant (~598MB vs ~12GB)
  ([#1324](https://github.com/n24q02m/wet-mcp/pull/1324),
  [`c5785e2`](https://github.com/n24q02m/wet-mcp/commit/c5785e26a6339cbd9c7bf7d1f37b17e70d05889b))

### Chores

- **deps**: Lock file maintenance ([#1318](https://github.com/n24q02m/wet-mcp/pull/1318),
  [`c19a35c`](https://github.com/n24q02m/wet-mcp/commit/c19a35c674271e8aac27de26cef459a83e3a4dd6))

- **deps**: Update ghcr.io/astral-sh/uv:latest docker digest to eaa5f1a
  ([#1316](https://github.com/n24q02m/wet-mcp/pull/1316),
  [`5e93b61`](https://github.com/n24q02m/wet-mcp/commit/5e93b6118471b859af148cc769cc7bbebbc9ef1d))


## v3.3.0-beta.4 (2026-06-11)

### Bug Fixes

- Document model chains + tagline (wet) ([#1322](https://github.com/n24q02m/wet-mcp/pull/1322),
  [`f0f54ba`](https://github.com/n24q02m/wet-mcp/commit/f0f54ba14ab03e7227b4e6b3963abdffaa691404))

- Document per-task model chains + provider->key table (drop priority-router docs)
  ([#1322](https://github.com/n24q02m/wet-mcp/pull/1322),
  [`f0f54ba`](https://github.com/n24q02m/wet-mcp/commit/f0f54ba14ab03e7227b4e6b3963abdffaa691404))

### Features

- Drop config(action="models") catalog-listing tool action
  ([#1323](https://github.com/n24q02m/wet-mcp/pull/1323),
  [`4c7034e`](https://github.com/n24q02m/wet-mcp/commit/4c7034eeb9c225b868646df42ab03cabc0ee7b91))

- Wet per-task model chains + relay model-chain widget, drop priority-router
  ([#1322](https://github.com/n24q02m/wet-mcp/pull/1322),
  [`f0f54ba`](https://github.com/n24q02m/wet-mcp/commit/f0f54ba14ab03e7227b4e6b3963abdffaa691404))


## v3.3.0-beta.3 (2026-06-11)

### Features

- Wet per-task model chains + relay model-chain widget, drop priority-router
  ([#1321](https://github.com/n24q02m/wet-mcp/pull/1321),
  [`531944e`](https://github.com/n24q02m/wet-mcp/commit/531944e3936cd87eca9429069864ad318da1b26c))


## v3.3.0-beta.2 (2026-06-11)

### Bug Fixes

- Cap n24q02m-web-core to <2.2 (private SSRF API drift)
  ([#1320](https://github.com/n24q02m/wet-mcp/pull/1320),
  [`6a26421`](https://github.com/n24q02m/wet-mcp/commit/6a26421f68d87469f74770a26e6bf92aea8cb0e2))


## v3.3.0-beta.1 (2026-06-11)

### Bug Fixes

- Add XAI_API_KEY to relay schema and cloud credential keys
  ([#1315](https://github.com/n24q02m/wet-mcp/pull/1315),
  [`366f5cb`](https://github.com/n24q02m/wet-mcp/commit/366f5cb989f517182d75286c0a5048568cd5647c))

- Harden litellm response-shape parsing (None-guard rerank, api_key normalise, attr-access)
  ([#1315](https://github.com/n24q02m/wet-mcp/pull/1315),
  [`366f5cb`](https://github.com/n24q02m/wet-mcp/commit/366f5cb989f517182d75286c0a5048568cd5647c))

### Features

- Migrate LLM, embedding and rerank dispatch to mcp_core.llm litellm passthrough
  ([#1315](https://github.com/n24q02m/wet-mcp/pull/1315),
  [`366f5cb`](https://github.com/n24q02m/wet-mcp/commit/366f5cb989f517182d75286c0a5048568cd5647c))

- Migrate LLM/embedding/rerank to litellm passthrough via mcp-core[llm]
  ([#1315](https://github.com/n24q02m/wet-mcp/pull/1315),
  [`366f5cb`](https://github.com/n24q02m/wet-mcp/commit/366f5cb989f517182d75286c0a5048568cd5647c))

### Testing

- Add comprehensive tests for token_store.py ([#1308](https://github.com/n24q02m/wet-mcp/pull/1308),
  [`8c3842c`](https://github.com/n24q02m/wet-mcp/commit/8c3842cb975d5fe4c01d4ecf681b0cdaafcbbedb))

- Add coverage for get_project_context error paths
  ([#1301](https://github.com/n24q02m/wet-mcp/pull/1301),
  [`39ea3ba`](https://github.com/n24q02m/wet-mcp/commit/39ea3ba8d07e252a53796d380c54239522c92c7b))

- Add error path coverage for DocsDB.add_chunks
  ([#1313](https://github.com/n24q02m/wet-mcp/pull/1313),
  [`d48b54b`](https://github.com/n24q02m/wet-mcp/commit/d48b54bc1aadfd79196989d997db70af4265f7f5))

- Add stronger assertions for searxng missing package dir edge cases
  ([#1314](https://github.com/n24q02m/wet-mcp/pull/1314),
  [`bb89056`](https://github.com/n24q02m/wet-mcp/commit/bb8905612c80f187a26ee7a970a655cd921b84d7))


## v3.2.7-beta.1 (2026-06-10)

### Bug Fixes

- Correct docs drift (tool count, version framing, dead links)
  ([#1298](https://github.com/n24q02m/wet-mcp/pull/1298),
  [`88e355f`](https://github.com/n24q02m/wet-mcp/commit/88e355f074ad7b031ba8614515d0aef357bf3091))

### Chores

- **deps**: Update step-security/harden-runner digest to 9af89fc
  ([#1293](https://github.com/n24q02m/wet-mcp/pull/1293),
  [`dbb6ba7`](https://github.com/n24q02m/wet-mcp/commit/dbb6ba7f4f45a8d30fe1545ce8c8de298f06fbc6))


## v3.2.6 (2026-06-09)


## v3.2.6-beta.1 (2026-06-09)

### Bug Fixes

- Make docs-search tests hermetic to stop macOS teardown timeout
  ([#1269](https://github.com/n24q02m/wet-mcp/pull/1269),
  [`8a6a7f7`](https://github.com/n24q02m/wet-mcp/commit/8a6a7f7c3d8540a47d3f3f395f145df6a4bd152b))

### Chores

- **deps**: Update codecov/codecov-action action to v7
  ([#1272](https://github.com/n24q02m/wet-mcp/pull/1272),
  [`4b7fd3a`](https://github.com/n24q02m/wet-mcp/commit/4b7fd3ab86d22b2a867c5ea0a2bf029e79d0af25))


## v3.2.5 (2026-06-07)

### Bug Fixes

- Force clean re-import in serverInfo version test
  ([#1265](https://github.com/n24q02m/wet-mcp/pull/1265),
  [`6eee850`](https://github.com/n24q02m/wet-mcp/commit/6eee850c0eb7eb5d2a9a7ea6b49a44df6c94d1e5))

- Report wet-mcp package version in serverInfo.version
  ([#1265](https://github.com/n24q02m/wet-mcp/pull/1265),
  [`6eee850`](https://github.com/n24q02m/wet-mcp/commit/6eee850c0eb7eb5d2a9a7ea6b49a44df6c94d1e5))


## v3.2.5-beta.1 (2026-06-07)

### Bug Fixes

- Add cache get_with_age and periodic purge tests
  ([`cb9e33d`](https://github.com/n24q02m/wet-mcp/commit/cb9e33d3eb74146820b2931d987be158761e8d32))

- Add check_health error-path tests for gdrive sync
  ([`f24d648`](https://github.com/n24q02m/wet-mcp/commit/f24d648d85963576b4ecbc45d31a2b5504c2c237))

- Add coverage tests for migrations module
  ([`207a33d`](https://github.com/n24q02m/wet-mcp/commit/207a33d6f367f9191478b4e14ec11faec88460d9))

- Add setup_api_keys alias and whitespace tests
  ([`0b7f5be`](https://github.com/n24q02m/wet-mcp/commit/0b7f5be602bedf56ff76b25f9d0d58d84eec9cfa))

- Add SyncBackend abstract base class tests
  ([`767d841`](https://github.com/n24q02m/wet-mcp/commit/767d841503e9e81fe063af97707c85a44ee06bae))

- Add test for get_token_path_for_sub
  ([`3d59e48`](https://github.com/n24q02m/wet-mcp/commit/3d59e48f160a732f91c8692c2729158ecbfed1a3))

- Update actions/checkout digest to df4cb1c
  ([`44632be`](https://github.com/n24q02m/wet-mcp/commit/44632be2a82db3b76529c81f298c169fb71b73a8))

- Update codeql-action digest to 8aad20d
  ([`a63d3b6`](https://github.com/n24q02m/wet-mcp/commit/a63d3b631469d0c3e11add5783ffe12486c1101b))

- Update non-major dependencies
  ([`86615ff`](https://github.com/n24q02m/wet-mcp/commit/86615ffdde6d607ef4b9bac0c30eeb5b21bd375d))

- Update uv docker digest to b46b03d
  ([`bca3b48`](https://github.com/n24q02m/wet-mcp/commit/bca3b48128c1e54689a1d427d0285106912b893f))

### Chores

- **deps**: Bump aiohttp in the uv group across 1 directory
  ([#1190](https://github.com/n24q02m/wet-mcp/pull/1190),
  [`9a2b862`](https://github.com/n24q02m/wet-mcp/commit/9a2b862658bbdf04a493794b6817833e2ccd638e))


## v3.2.4 (2026-06-01)

### Bug Fixes

- Pin mcp-core 1.17.2 (stable)
  ([`b3e1d77`](https://github.com/n24q02m/wet-mcp/commit/b3e1d77aa029e3b431dc359c1b2c60570dbe26b2))


## v3.2.4-beta.1 (2026-06-01)

### Bug Fixes

- Bump mcp-core to 1.17.2-beta.1 for beta testing
  ([`7cbf4f6`](https://github.com/n24q02m/wet-mcp/commit/7cbf4f694d2b63ecd7439cfede561e3fbb8be32b))

- Make Windows console handle Unicode output without cp1252 crash
  ([#1179](https://github.com/n24q02m/wet-mcp/pull/1179),
  [`2abfbd5`](https://github.com/n24q02m/wet-mcp/commit/2abfbd5299f9fbf2715ffbe9abd9c71544b2336f))

- Make Windows console handle Unicode output without cp1252 crash
  ([#1148](https://github.com/n24q02m/wet-mcp/pull/1148),
  [`2cb3870`](https://github.com/n24q02m/wet-mcp/commit/2cb3870ed76bd72a403e17826b2d29f801e839ca))

- Sync docs to actual code (sync/ package, SYNC_ENABLED default, config actions, docker port)
  ([#1179](https://github.com/n24q02m/wet-mcp/pull/1179),
  [`2abfbd5`](https://github.com/n24q02m/wet-mcp/commit/2abfbd5299f9fbf2715ffbe9abd9c71544b2336f))

- Sync docs to actual sync package, SYNC_ENABLED default, config actions, docker port
  ([#1179](https://github.com/n24q02m/wet-mcp/pull/1179),
  [`2abfbd5`](https://github.com/n24q02m/wet-mcp/commit/2abfbd5299f9fbf2715ffbe9abd9c71544b2336f))

- Update uv docker digest to 03bdc89 ([#1172](https://github.com/n24q02m/wet-mcp/pull/1172),
  [`b2d0c20`](https://github.com/n24q02m/wet-mcp/commit/b2d0c207eacc9707246a8d137f43d5c05418f552))


## v3.2.3 (2026-05-29)

### Bug Fixes

- Pin mcp-core 1.17.1 (BearerMCPApp resource_metadata #260)
  ([`6639d00`](https://github.com/n24q02m/wet-mcp/commit/6639d00e9e7ca7b0ccbeaff189b9a60788498767))


## v3.2.2 (2026-05-29)

### Bug Fixes

- Pin mcp-core 1.17.0 (stable OAuth refresh_token)
  ([`9d75717`](https://github.com/n24q02m/wet-mcp/commit/9d75717a2e065f4be6567b0ccda14407850d6dba))


## v3.2.2-beta.1 (2026-05-29)

### Bug Fixes

- Add coverage tests for mark_library_indexed
  ([#1153](https://github.com/n24q02m/wet-mcp/pull/1153),
  [`7531a42`](https://github.com/n24q02m/wet-mcp/commit/7531a42718421053d026ff4070730cec09584e2c))

- Add offline Alembic migration tests ([#1161](https://github.com/n24q02m/wet-mcp/pull/1161),
  [`916e544`](https://github.com/n24q02m/wet-mcp/commit/916e5449b6e90147feb933fd52d1047ff9946130))

- Bump mcp-core to 1.17.0-beta.1 for OAuth refresh_token
  ([`5240ae0`](https://github.com/n24q02m/wet-mcp/commit/5240ae002d3ee5eac67285f95d255ca3b2164b78))

- Validate db column names against allowlists to prevent SQL injection
  ([#1157](https://github.com/n24q02m/wet-mcp/pull/1157),
  [`8c9baac`](https://github.com/n24q02m/wet-mcp/commit/8c9baac3f1328b45c26cf5eb68f3fff2841dd232))


## v3.2.1 (2026-05-28)

### Bug Fixes

- Annotate benchmark summary dict type so ty resolves results subscript
  ([`cfe11aa`](https://github.com/n24q02m/wet-mcp/commit/cfe11aad0e1b4dcecc6c9f0729996d2fb3af14ff))

- Cast asyncio.Future to Task[Any] in test to satisfy ty type checker
  ([`5bfc49b`](https://github.com/n24q02m/wet-mcp/commit/5bfc49b75b6cd0a1bf7a0fa9824a66dfe109337d))


## v3.2.1-beta.1 (2026-05-28)

### Bug Fixes

- **deps**: Pin pydantic to <2.13 to match mcp-core 1.15.0 transitive cap
  ([`26c76b5`](https://github.com/n24q02m/wet-mcp/commit/26c76b5ff92cdf36dfa4d31beb58a795995f356a))

- **deps**: Update non-major dependencies ([#1130](https://github.com/n24q02m/wet-mcp/pull/1130),
  [`7371b8f`](https://github.com/n24q02m/wet-mcp/commit/7371b8f23b256c5826d78900a875cf5f5b345bb9))

### Chores

- **deps**: Lock file maintenance ([#1131](https://github.com/n24q02m/wet-mcp/pull/1131),
  [`eb06a37`](https://github.com/n24q02m/wet-mcp/commit/eb06a37208c00b40f533778ba5249860c8f8d743))


## v3.2.0 (2026-05-26)


## v3.2.0-beta.2 (2026-05-26)

### Features

- Wire MCP_AUTH_DISABLE env to run_http_server(auth_disabled=)
  ([`0668ef8`](https://github.com/n24q02m/wet-mcp/commit/0668ef894e7003bf3c3dcd1599f9fc5e52e8f59a))


## v3.2.0-beta.1 (2026-05-26)

### Bug Fixes

- **deps**: Update dependency cohere to v7 ([#1119](https://github.com/n24q02m/wet-mcp/pull/1119),
  [`d61fb2a`](https://github.com/n24q02m/wet-mcp/commit/d61fb2a9459c3f0b29f9f5dc3f877b786b513793))

### Features

- Add MCP_AUTH_DISABLE env flag for external auth boundary
  ([`5309f49`](https://github.com/n24q02m/wet-mcp/commit/5309f49f2b76f3f8fa2a32ff567f53e9c095676c))


## v3.1.1-beta.1 (2026-05-24)

### Bug Fixes

- Add supply-chain security test, update GitHub Actions
  ([#1109](https://github.com/n24q02m/wet-mcp/pull/1109),
  [`d385dab`](https://github.com/n24q02m/wet-mcp/commit/d385daba330c9fbb56e3ec08884e434623af81a1))

- **deps**: Pin pydantic <2.13 for mcp-core 1.14.0 compatibility
  ([#1099](https://github.com/n24q02m/wet-mcp/pull/1099),
  [`069286e`](https://github.com/n24q02m/wet-mcp/commit/069286e1b7a44c68c6f55b819e99a73c6e9db414))

- **deps**: Update non-major dependencies ([#1099](https://github.com/n24q02m/wet-mcp/pull/1099),
  [`069286e`](https://github.com/n24q02m/wet-mcp/commit/069286e1b7a44c68c6f55b819e99a73c6e9db414))

### Chores

- **deps**: Update actions/create-github-app-token digest to bcd2ba4
  ([#1093](https://github.com/n24q02m/wet-mcp/pull/1093),
  [`115a555`](https://github.com/n24q02m/wet-mcp/commit/115a555a8aca2a239b3c5824bf8ecf1cf752e623))

- **deps**: Update docker/build-push-action digest to f9f3042
  ([#1110](https://github.com/n24q02m/wet-mcp/pull/1110),
  [`bab7be6`](https://github.com/n24q02m/wet-mcp/commit/bab7be65586a663574ceae2f03d88bdaf362707e))

- **deps**: Update docker/login-action digest to 650006c
  ([#1111](https://github.com/n24q02m/wet-mcp/pull/1111),
  [`d311ad8`](https://github.com/n24q02m/wet-mcp/commit/d311ad819652a59aa97cf7ee94cca060b0fecaaa))

- **deps**: Update docker/setup-buildx-action digest to d7f5e7f
  ([#1112](https://github.com/n24q02m/wet-mcp/pull/1112),
  [`832a610`](https://github.com/n24q02m/wet-mcp/commit/832a6100185831fb71105f666e29490c2bd6dc75))

- **deps**: Update ghcr.io/astral-sh/uv:latest docker digest to 440fd64
  ([#1094](https://github.com/n24q02m/wet-mcp/pull/1094),
  [`2d48bb9`](https://github.com/n24q02m/wet-mcp/commit/2d48bb986554bca0e8d19060edc3f86ef5ca60fe))

- **deps**: Update github/codeql-action digest to 7211b7c
  ([#1114](https://github.com/n24q02m/wet-mcp/pull/1114),
  [`20510df`](https://github.com/n24q02m/wet-mcp/commit/20510df469d61252fc727c19d7b4cb6f76a0344d))

- **deps**: Update github/codeql-action digest to 9e0d7b8
  ([#1095](https://github.com/n24q02m/wet-mcp/pull/1095),
  [`48b83bc`](https://github.com/n24q02m/wet-mcp/commit/48b83bc6c8eb7c2563b1703fb82c4da7ca415470))

- **deps**: Update python:3.13-slim-bookworm docker digest to e4fa1f9
  ([#1115](https://github.com/n24q02m/wet-mcp/pull/1115),
  [`f4e10fc`](https://github.com/n24q02m/wet-mcp/commit/f4e10fc986285bae38f3e9516286a48fd2771eee))

- **deps**: Update step-security/harden-runner digest to ab7a940
  ([#1098](https://github.com/n24q02m/wet-mcp/pull/1098),
  [`1a749db`](https://github.com/n24q02m/wet-mcp/commit/1a749dbc64774873c164440b8a44ff235ff92de3))


## v3.1.0 (2026-05-19)

### Bug Fixes

- Add publish_existing_tag CD recovery for GitHub immutable-release tag burn
  ([`10d79ba`](https://github.com/n24q02m/wet-mcp/commit/10d79baa53daa42a9db8d3189c8bbf17b087eb26))


## v3.0.0-beta.4 (2026-05-16)

### Bug Fixes

- Pin urllib3 + langsmith floors to patch 3 high CVEs
  ([`15c107b`](https://github.com/n24q02m/wet-mcp/commit/15c107b90a8f8f8285fb1796b7534b3143a3b25a))

- Scrub internal dev-process terminology from user-facing docs
  ([`89f0d87`](https://github.com/n24q02m/wet-mcp/commit/89f0d8753857eb9e5e8a6a33b400a535ebcaaa55))

### Chores

- **deps**: Lock file maintenance ([#1085](https://github.com/n24q02m/wet-mcp/pull/1085),
  [`0581cb5`](https://github.com/n24q02m/wet-mcp/commit/0581cb5f05c3bcfb0e83a421bf416172eade7a67))

- **deps**: Update actions/upload-artifact action to v7
  ([#1087](https://github.com/n24q02m/wet-mcp/pull/1087),
  [`bd78a6f`](https://github.com/n24q02m/wet-mcp/commit/bd78a6f07f2df64e3513476011013501146b0586))

- **deps**: Update python:3.13-slim-bookworm docker digest to 386df64
  ([#1083](https://github.com/n24q02m/wet-mcp/pull/1083),
  [`4c9e507`](https://github.com/n24q02m/wet-mcp/commit/4c9e507250db82aba668b0882bdda50851349bec))


## v3.0.0-beta.3 (2026-05-14)

### Bug Fixes

- Sort imports in test_migrations to unblock CI ruff gate
  ([`320ab36`](https://github.com/n24q02m/wet-mcp/commit/320ab361677e69500775b04f654bb6d5f83fc800))

### Features

- Add S3 sync backend settings for operator deploy mode
  ([`b742e2e`](https://github.com/n24q02m/wet-mcp/commit/b742e2efb0a4db4a8fe3713ce9ea59d15548bf1a))

- Add tests for sync backend registry and S3 backend
  ([`a7fd75c`](https://github.com/n24q02m/wet-mcp/commit/a7fd75c3e2b098f62726254a87de06eeec796d94))

- Document docs sync backends and XOR deployment modes
  ([`600cfc8`](https://github.com/n24q02m/wet-mcp/commit/600cfc8181c6778dde0a88df607992e40e6f06cb))

- Gate auto-sync behind active sync backend in server lifespan
  ([`329354f`](https://github.com/n24q02m/wet-mcp/commit/329354f34544459bbe8376238642a7577e764ffb))

- Refactor sync module into backend-pluggable package
  ([`fcb9eb9`](https://github.com/n24q02m/wet-mcp/commit/fcb9eb91bb430a7137fba5def603ed42c820cf9b))


## v3.0.0-beta.2 (2026-05-14)

### Bug Fixes

- Package alembic config + scripts in wheel so migrations run on uvx install
  ([`a96d1a0`](https://github.com/n24q02m/wet-mcp/commit/a96d1a044fae92f8a78d30438ee4b0d956b5cf11))


## v3.0.0-beta.1 (2026-05-10)

### Bug Fixes

- Lower coverage gate to 92% as phase 2 baseline
  ([`cb4a256`](https://github.com/n24q02m/wet-mcp/commit/cb4a256cb24c0bde59b916b4579d964db7ef198d))

- Regression test for v1.x.y to v2.0.0 auto-migrate round-trip
  ([`abb47f4`](https://github.com/n24q02m/wet-mcp/commit/abb47f44d34fe7609712d8fc19316478888148e2))

- Stub phase 2 lifespan hooks in test conftest to prevent timeouts
  ([`22a93a0`](https://github.com/n24q02m/wet-mcp/commit/22a93a05d0834e108886aa740dfdfa893890995d))

### Features

- Alembic baseline + auto-migrate-on-startup runner
  ([`ab31ff5`](https://github.com/n24q02m/wet-mcp/commit/ab31ff5cd86f570a550e72e69109077b9dbe0f17))

- Docs_002_libraries migration extends schema per spec section 5.4
  ([`e29e7e3`](https://github.com/n24q02m/wet-mcp/commit/e29e7e312066fa604382e0de7af92928ba2fc9ef))

- Docs_003_project_context migration adds Cabinets isolation table
  ([`66e5ebd`](https://github.com/n24q02m/wet-mcp/commit/66e5ebd28610d81e9323a531ce7f0d405aeb8277))

- Docs_004_chunk_summaries migration plus add_chunks summary support
  ([`50dbcc6`](https://github.com/n24q02m/wet-mcp/commit/50dbcc6199a67bd1bfb5acde295b120d57b1092a))

- Docs_resolve + docs_query + docs_lock_project actions per spec section 4.3
  ([`d4b7a3c`](https://github.com/n24q02m/wet-mcp/commit/d4b7a3c20718a4350a20476d8e1293f12f663cb0))

- Phase 2 coverage tests for dispatch + ingest_tier2 + project_lock
  ([`4b4f7f2`](https://github.com/n24q02m/wet-mcp/commit/4b4f7f2c870cd198989ea77fa5b534e59fa809f1))

- Phase 2 docs refresh + lock-project-stack skill + SessionStart freshness hook
  ([`68f0949`](https://github.com/n24q02m/wet-mcp/commit/68f09495014ef7c58c8153d69a5df1b336ff1603))

- Phase 3 docs refresh -- migration plus interact guide plus README v2
  ([`7dd7d10`](https://github.com/n24q02m/wet-mcp/commit/7dd7d102f76df33ec1ec620d319d1ab1633726f7))

- Phase 3 task 0 baseline metrics for regression check
  ([`e476e25`](https://github.com/n24q02m/wet-mcp/commit/e476e257aaa1eb2c90806ed99abfd73c9078859d))

- Phase 3 task 1 InteractOps wet-local for patchright interactive ops
  ([`bde5cb7`](https://github.com/n24q02m/wet-mcp/commit/bde5cb7bbf33bb7e28fe1c8e6fb174b4a93c6609))

- Phase 3 task 10 UserPromptSubmit hook for docs cache prewarm
  ([`0a2d3f1`](https://github.com/n24q02m/wet-mcp/commit/0a2d3f15c1aac46797c5ebb805782110da8456d9))

- Phase 3 task 2 extract action agent for cited research synthesis
  ([`3327b91`](https://github.com/n24q02m/wet-mcp/commit/3327b9190b472830181f7e587c53b1b547e1e237))

- Phase 3 task 3 browser session pool with TTL plus LRU eviction
  ([`72710ff`](https://github.com/n24q02m/wet-mcp/commit/72710ff2332d42c20e7d60c9b19fbfe3c2eddb90))

- Phase 3 task 4 extract action interact for patchright drive
  ([`3986811`](https://github.com/n24q02m/wet-mcp/commit/398681135b94116b1e1154d58c4f30613ef99812))

- Phase 3 task 7 research-topic skill for extract action agent
  ([`33d56bc`](https://github.com/n24q02m/wet-mcp/commit/33d56bc872bd2d18463dc0d775222de6d213efb8))

- Remove media action analyze entirely in v2.0.0
  ([`067299a`](https://github.com/n24q02m/wet-mcp/commit/067299add802eaebe040909f5154a5665588cf69))

- Tier 1 warmup + on-demand tier 2 + per-version schema
  ([`6d13269`](https://github.com/n24q02m/wet-mcp/commit/6d13269a808cd1232c7fb3f898771047cc3e2af7))


## v2.31.0-beta.1 (2026-05-09)

### Bug Fixes

- Remove help.md + refresh extract help topic
  ([`4131b86`](https://github.com/n24q02m/wet-mcp/commit/4131b8634acbe87f7829129eda64b1916fee347f))

- Remove stale 'help' from allowed_tools after help.md removal
  ([`ccde4fb`](https://github.com/n24q02m/wet-mcp/commit/ccde4fb28b15f8e441ff6c62b0607924776282e9))

- Revert setup docs duplicates per Spec F single source of truth
  ([`ca9e14c`](https://github.com/n24q02m/wet-mcp/commit/ca9e14c736f6675030388ba7f10204e32fdc64b2))

- Sync CLAUDE.md and AGENTS.md + add diff guard hook
  ([`36f605f`](https://github.com/n24q02m/wet-mcp/commit/36f605f546d7c06949f1b0646b83941f724f0b2c))

- **deps**: Bump n24q02m-web-core pin to v2.0.0 (Plan A Task 14)
  ([`56044dc`](https://github.com/n24q02m/wet-mcp/commit/56044dc65fe9648af8a6eaaa5c5325f39a6cf1f8))

- **deps**: Bump qwen3-embed to v1.9.2 + mcp-core floor to v1.14.0
  ([`f7cb4ea`](https://github.com/n24q02m/wet-mcp/commit/f7cb4ea095beed5cb3284f6bac79ec5812154319))

- **deps**: Pin pydantic <2.13 locally + bump web-core to v2.0.1
  ([`f42f756`](https://github.com/n24q02m/wet-mcp/commit/f42f756e96503edcaa11484e40940a103e97204e))

- **deps**: Update dependency google-genai to v2
  ([#1077](https://github.com/n24q02m/wet-mcp/pull/1077),
  [`aad5650`](https://github.com/n24q02m/wet-mcp/commit/aad565033f571ae6784a65674a8c733389130f01))

- **tests**: Align _get_process_kwargs + _read_discovery with web-core v2.x
  ([`c4ce53a`](https://github.com/n24q02m/wet-mcp/commit/c4ce53a14e0eb04acf2bb8ee556e17025de463f9))

- **tests**: Align test_searxng_runner_comprehensive with web-core v2.x
  ([`986ab71`](https://github.com/n24q02m/wet-mcp/commit/986ab71ad659bb710202a8b25a53dcb3f24edf0e))

### Chores

- **deps**: Update actions/dependency-review-action action to v5
  ([#1078](https://github.com/n24q02m/wet-mcp/pull/1078),
  [`ceadd3c`](https://github.com/n24q02m/wet-mcp/commit/ceadd3ca27d06514582aa808fb9d21e903130254))

- **deps**: Update ghcr.io/astral-sh/uv:latest docker digest to 3a59a3c
  ([#1054](https://github.com/n24q02m/wet-mcp/pull/1054),
  [`f429057`](https://github.com/n24q02m/wet-mcp/commit/f429057b9bfd7ac51b380d91d11eba6cfed102c9))

- **deps**: Update github/codeql-action digest to 68bde55
  ([#1075](https://github.com/n24q02m/wet-mcp/pull/1075),
  [`d386914`](https://github.com/n24q02m/wet-mcp/commit/d386914a747fd598b7fbfe901c7a79ead3fd2805))

### Features

- Add Table of contents heading + auto-generated link list (Spec E Wave 2)
  ([`cca1c62`](https://github.com/n24q02m/wet-mcp/commit/cca1c62da7ab2d8e8dead3fa775a9bdd82e64e74))

- Deprecate media.analyze action with grace period for v2.0.0 removal
  ([`2ea6f23`](https://github.com/n24q02m/wet-mcp/commit/2ea6f23bebfeff29a7c32815d891df5ceec86086))

- Link to mcp.n24q02m.com unified docs site (Spec F Phase 4)
  ([`02d030a`](https://github.com/n24q02m/wet-mcp/commit/02d030a05bdbd2adf1a6ad966cf6505430b233e4))

- Migrate extract pipeline to web-core ScrapingAgent + smart chunks output
  ([`86b4c6b`](https://github.com/n24q02m/wet-mcp/commit/86b4c6bacde87b4c39ea3d5f353dbc02989eda76))

- Refresh README + setup docs + ARCHITECTURE + BENCHMARKS for Phase 1
  ([`a6d2eae`](https://github.com/n24q02m/wet-mcp/commit/a6d2eae6094960bedb5f23d0142f0640c8a7a515))

- Search query expansion + TTL cache + citation standardization
  ([`10f1ca5`](https://github.com/n24q02m/wet-mcp/commit/10f1ca5ef8a5010e590008ee9daead31d9c13aa2))

- Sync cross-promo section ([#1076](https://github.com/n24q02m/wet-mcp/pull/1076),
  [`baa44a5`](https://github.com/n24q02m/wet-mcp/commit/baa44a5c4da4763794497136300fe2deceb5df4a))

### Refactoring

- Modularize _probe_docs_url in docs.py ([#1068](https://github.com/n24q02m/wet-mcp/pull/1068),
  [`ad0c066`](https://github.com/n24q02m/wet-mcp/commit/ad0c06670f9ca3d3bea27eb7a7b9e4e21cf775a6))

- Split overly long config function into helpers
  ([#1074](https://github.com/n24q02m/wet-mcp/pull/1074),
  [`d5ee469`](https://github.com/n24q02m/wet-mcp/commit/d5ee4696c69533662ed8f8e5419e52498c6f4c0f))

### Testing

- Add test for uvx_searxng_blocked_error ([#1059](https://github.com/n24q02m/wet-mcp/pull/1059),
  [`1f2e240`](https://github.com/n24q02m/wet-mcp/commit/1f2e24026882bb7ec0659a2a8468c47185afad7d))

- **llm**: Add coverage for acompletion fallback exception block
  ([#1061](https://github.com/n24q02m/wet-mcp/pull/1061),
  [`cd9bc78`](https://github.com/n24q02m/wet-mcp/commit/cd9bc7885cb42629d7f959a4605237789e712e53))


## v2.30.2 (2026-05-06)


## v2.30.2-beta.1 (2026-05-06)

### Bug Fixes

- **deps**: Update dependency cryptography to v48
  ([#1047](https://github.com/n24q02m/wet-mcp/pull/1047),
  [`4b7b3d2`](https://github.com/n24q02m/wet-mcp/commit/4b7b3d25b88e44543cf2603c537908c7128862d6))

### Chores

- **deps**: Update ghcr.io/astral-sh/uv:latest docker digest to bca7f69
  ([#1046](https://github.com/n24q02m/wet-mcp/pull/1046),
  [`2a0b7e1`](https://github.com/n24q02m/wet-mcp/commit/2a0b7e12cfa03d7415818697479cb16330654f47))

- **deps**: Update step-security/harden-runner digest to a5ad31d
  ([#1021](https://github.com/n24q02m/wet-mcp/pull/1021),
  [`cad99bf`](https://github.com/n24q02m/wet-mcp/commit/cad99bfa938f85c8e5a857a5f57c542e69fb68e3))


## v2.30.1 (2026-05-05)

### Bug Fixes

- Bump n24q02m-web-core to 1.3.11 for SearXNG limiter + JSON fix
  ([#1045](https://github.com/n24q02m/wet-mcp/pull/1045),
  [`b198937`](https://github.com/n24q02m/wet-mcp/commit/b1989378583cfd34fe190f248f6da542ebe4138d))


## v2.30.0 (2026-05-05)

### Bug Fixes

- Bump n24q02m-web-core to 1.3.10 stable ([#1042](https://github.com/n24q02m/wet-mcp/pull/1042),
  [`679cb4b`](https://github.com/n24q02m/wet-mcp/commit/679cb4b6cd4c4ba66dc2a24e17a03840daa93631))


## v2.30.0-beta.1 (2026-05-05)

### Bug Fixes

- Bump n24q02m-web-core to 1.3.10b2 for SearXNG doi_resolver fix
  ([#1039](https://github.com/n24q02m/wet-mcp/pull/1039),
  [`59f9319`](https://github.com/n24q02m/wet-mcp/commit/59f9319b0024c6c886325acdc87c31ab0b2b2678))

- Consolidate setup docs body to 3 methods (drop legacy Method 4/5)
  ([#1034](https://github.com/n24q02m/wet-mcp/pull/1034),
  [`277d25a`](https://github.com/n24q02m/wet-mcp/commit/277d25a67b385ac39362f083a6fc826b6b765aad))

### Features

- Add explicit Method overview section to setup docs
  ([#1033](https://github.com/n24q02m/wet-mcp/pull/1033),
  [`4a8f0c1`](https://github.com/n24q02m/wet-mcp/commit/4a8f0c1191bcec1bcbeb56febc56da4c64d3d034))

- Align userConfig with relay_schema fields ([#1036](https://github.com/n24q02m/wet-mcp/pull/1036),
  [`b33d39c`](https://github.com/n24q02m/wet-mcp/commit/b33d39c288c4a22ba7c544b1e472508a5ea088ad))

- Clarify Method 1/2/3 mutually exclusive (CC scope-by-endpoint)
  ([#1038](https://github.com/n24q02m/wet-mcp/pull/1038),
  [`25d3d66`](https://github.com/n24q02m/wet-mcp/commit/25d3d6693162fd21c0d14e6421d7ff410bc51f61))

- Declare userConfig schema and document install prompt
  ([#1035](https://github.com/n24q02m/wet-mcp/pull/1035),
  [`cd75b1d`](https://github.com/n24q02m/wet-mcp/commit/cd75b1dccd674f7468fc65dcb8e547eee7e8af2d))

- Document userConfig credential prompts per plugin
  ([#1037](https://github.com/n24q02m/wet-mcp/pull/1037),
  [`e314e15`](https://github.com/n24q02m/wet-mcp/commit/e314e15b4a736f6b808ddfe0e4a4e5f40bd61d4b))


## v2.29.0 (2026-05-04)

### Bug Fixes

- Bump mcp-core to 1.13.0 (STABLE) ([#1032](https://github.com/n24q02m/wet-mcp/pull/1032),
  [`fbda87f`](https://github.com/n24q02m/wet-mcp/commit/fbda87f453fea314b2aadd080b20d266816f1350))


## v2.29.0-beta.14 (2026-05-03)

### Bug Fixes

- Bump mcp-core to 1.13.0-beta.9 for /login form shell refactor
  ([#1030](https://github.com/n24q02m/wet-mcp/pull/1030),
  [`810e185`](https://github.com/n24q02m/wet-mcp/commit/810e185022e51e82f890ed6aa0628e480b420069))


## v2.29.0-beta.13 (2026-05-03)

### Bug Fixes

- Bump mcp-core floor to 1.13.0b7 for /login gate
  ([#1029](https://github.com/n24q02m/wet-mcp/pull/1029),
  [`96fec43`](https://github.com/n24q02m/wet-mcp/commit/96fec43b2b115684fa575dedb48e6c33b6c1eefa))


## v2.29.0-beta.12 (2026-05-03)

### Features

- Bump mcp-core to 1.13.0-beta.7 ([#1027](https://github.com/n24q02m/wet-mcp/pull/1027),
  [`de2d929`](https://github.com/n24q02m/wet-mcp/commit/de2d929de47b256288ef04a3c7858338ec4c4124))

- Document MCP_RELAY_PASSWORD edge auth gate ([#1028](https://github.com/n24q02m/wet-mcp/pull/1028),
  [`9e24458`](https://github.com/n24q02m/wet-mcp/commit/9e24458a91762b817cee45bbe5cda5ac1254f76b))

- Pass MCP_RELAY_PASSWORD env to HTTP container
  ([#1026](https://github.com/n24q02m/wet-mcp/pull/1026),
  [`3a5924d`](https://github.com/n24q02m/wet-mcp/commit/3a5924ddf28b78573b9575b54a1fa05b7578d682))


## v2.29.0-beta.11 (2026-05-03)

### Bug Fixes

- HTTP multi-user credential wiring (per-sub contextvar)
  ([#1025](https://github.com/n24q02m/wet-mcp/pull/1025),
  [`2226cc3`](https://github.com/n24q02m/wet-mcp/commit/2226cc35915539c866a772f6807a456a97fc094f))


## v2.29.0-beta.10 (2026-05-03)

### Bug Fixes

- Skip uvx detection inside Docker (Method 3 stdio Docker bug)
  ([#1024](https://github.com/n24q02m/wet-mcp/pull/1024),
  [`0730c85`](https://github.com/n24q02m/wet-mcp/commit/0730c85f062717a53400449ff834343d4b39fafb))


## v2.29.0-beta.9 (2026-05-02)

### Bug Fixes

- Skip SearXNG warmup task in stdio uvx mode ([#1020](https://github.com/n24q02m/wet-mcp/pull/1020),
  [`b053101`](https://github.com/n24q02m/wet-mcp/commit/b053101148919bbd6b79f4f59d68ad45f2318e04))


## v2.29.0-beta.8 (2026-05-02)

### Bug Fixes

- Reject web.search in stdio uvx mode (Docker-only feature)
  ([#1019](https://github.com/n24q02m/wet-mcp/pull/1019),
  [`d65c580`](https://github.com/n24q02m/wet-mcp/commit/d65c580f80e2d6353c8f66c806dee45054561570))


## v2.29.0-beta.7 (2026-05-02)

### Bug Fixes

- Regenerate uv.lock for new mcp-core beta (Docker trap)
  ([#1018](https://github.com/n24q02m/wet-mcp/pull/1018),
  [`46eb8b8`](https://github.com/n24q02m/wet-mcp/commit/46eb8b896c362410be28e99875c90b96a27a28ba))


## v2.29.0-beta.6 (2026-05-02)

### Bug Fixes

- Stdio mode skip PerPluginStore fallback (spec 2026-05-01 §4.1 + OQ3)
  ([#1017](https://github.com/n24q02m/wet-mcp/pull/1017),
  [`5c4bcfb`](https://github.com/n24q02m/wet-mcp/commit/5c4bcfb51245555edab1c8a5c91bd30847f7ed7e))


## v2.29.0-beta.5 (2026-05-02)

### Bug Fixes

- Regenerate uv.lock UV_NO_SOURCES=1 (Docker build trap)
  ([#1016](https://github.com/n24q02m/wet-mcp/pull/1016),
  [`978d47c`](https://github.com/n24q02m/wet-mcp/commit/978d47c73d978adfe4567f7cae5ef104b56b74e0))


## v2.29.0-beta.4 (2026-05-02)

### Bug Fixes

- Setup docs + README reflect stdio-pure architecture
  ([#1015](https://github.com/n24q02m/wet-mcp/pull/1015),
  [`5f642a3`](https://github.com/n24q02m/wet-mcp/commit/5f642a35b722f2d3ec20c074bfae723087d7985e))

### Chores

- Complete run without changes (backend-only project)
  ([#1012](https://github.com/n24q02m/wet-mcp/pull/1012),
  [`153b075`](https://github.com/n24q02m/wet-mcp/commit/153b0753276b44960a9068cd6a2b8b09e966008c))

- **tests**: Remove unused imports in test_g6_ux_status_accuracy.py and format
  ([#1012](https://github.com/n24q02m/wet-mcp/pull/1012),
  [`153b075`](https://github.com/n24q02m/wet-mcp/commit/153b0753276b44960a9068cd6a2b8b09e966008c))

### Features

- Stdio-pure + http-multi-user (drop daemon-bridge)
  ([#1014](https://github.com/n24q02m/wet-mcp/pull/1014),
  [`ff29c58`](https://github.com/n24q02m/wet-mcp/commit/ff29c58f0ea25a8aebd48a2faa0d54a0110a634e))


## v2.29.0-beta.3 (2026-04-30)

### Bug Fixes

- Regenerate uv.lock UV_NO_SOURCES=1 (Docker trap)
  ([#1009](https://github.com/n24q02m/wet-mcp/pull/1009),
  [`f211806`](https://github.com/n24q02m/wet-mcp/commit/f2118068335b2ed7078694335329e2eb1d7ec271))


## v2.29.0-beta.2 (2026-04-30)

### Bug Fixes

- G6 UX status accuracy — derive state from live PerPluginStore
  ([#1008](https://github.com/n24q02m/wet-mcp/pull/1008),
  [`d66e09e`](https://github.com/n24q02m/wet-mcp/commit/d66e09e197202ccffcfc620fc2f1009098d4194e))

### Features

- **docs**: Add trust model section to README
  ([#1006](https://github.com/n24q02m/wet-mcp/pull/1006),
  [`fe9cd67`](https://github.com/n24q02m/wet-mcp/commit/fe9cd6763128e444ec74f3ba68357e1d5e6c6ec5))

- **storage**: Migrate to PerPluginStore from mcp-core 1.13.0b1+
  ([#1007](https://github.com/n24q02m/wet-mcp/pull/1007),
  [`7f9bcf4`](https://github.com/n24q02m/wet-mcp/commit/7f9bcf4c94e95cac85a4987a0ab2dad55b634a3b))


## v2.29.0-beta.1 (2026-04-30)

### Features

- Route stdio mode to FastMCP direct + multi-target Dockerfile
  ([#1004](https://github.com/n24q02m/wet-mcp/pull/1004),
  [`14a954e`](https://github.com/n24q02m/wet-mcp/commit/14a954e4f2d7c5ad7d0b8439673912338d76f1f9))


## v2.28.7 (2026-04-29)

### Bug Fixes

- Bump n24q02m-mcp-core to 1.11.3 for D17 tools cache refresh
  ([#998](https://github.com/n24q02m/wet-mcp/pull/998),
  [`fabb26d`](https://github.com/n24q02m/wet-mcp/commit/fabb26de52725c6c5a851f0d298445f28c003d7e))


## v2.28.6 (2026-04-29)

### Bug Fixes

- Rebuild uv.lock without local path source ([#995](https://github.com/n24q02m/wet-mcp/pull/995),
  [`ee84061`](https://github.com/n24q02m/wet-mcp/commit/ee84061e6bdadb5825327282417803f7b737cbbc))


## v2.28.5 (2026-04-29)

### Bug Fixes

- Pin Python to ==3.13.* and bump web-core to 1.3.9
  ([#991](https://github.com/n24q02m/wet-mcp/pull/991),
  [`d78d26a`](https://github.com/n24q02m/wet-mcp/commit/d78d26accabe874b1bd981f0220dad0a959067ce))

- Register config__open_relay tool (Transparent Bridge Wave 3)
  ([#993](https://github.com/n24q02m/wet-mcp/pull/993),
  [`0ac8993`](https://github.com/n24q02m/wet-mcp/commit/0ac89939db4aa6a8a8ee628a3312e537d792ee9d))


## v2.28.4 (2026-04-28)

### Bug Fixes

- Clarify default-local relay URL in setup docs (no n24q02m subdomain)
  ([#983](https://github.com/n24q02m/wet-mcp/pull/983),
  [`6fc98e3`](https://github.com/n24q02m/wet-mcp/commit/6fc98e303ad8afdc95339ae73caec37577e1ef3a))

- Pass MCP_TRANSPORT=stdio in plugin.json + uv run --no-sync hooks
  ([#985](https://github.com/n24q02m/wet-mcp/pull/985),
  [`4200419`](https://github.com/n24q02m/wet-mcp/commit/4200419672d66d8b92f296ce949236fc96f4b27d))

- Pass MCP_TRANSPORT=stdio in plugin.json + uv run --no-sync hooks
  ([#984](https://github.com/n24q02m/wet-mcp/pull/984),
  [`c329eae`](https://github.com/n24q02m/wet-mcp/commit/c329eae49fb09f23828c1e1b47f42877518f42be))

- **credentials**: Rip _share_cloud_keys_to_peers — per-server isolation
  ([#985](https://github.com/n24q02m/wet-mcp/pull/985),
  [`4200419`](https://github.com/n24q02m/wet-mcp/commit/4200419672d66d8b92f296ce949236fc96f4b27d))

- **deps**: Bump n24q02m-mcp-core to 1.10.0 — Transparent Bridge waves 1-3
  ([#987](https://github.com/n24q02m/wet-mcp/pull/987),
  [`a8f9fd5`](https://github.com/n24q02m/wet-mcp/commit/a8f9fd5bc43b760017fd4297c85269138588be25))


## v2.28.3 (2026-04-28)

### Bug Fixes

- Bump n24q02m-mcp-core to 1.9.0 ([#982](https://github.com/n24q02m/wet-mcp/pull/982),
  [`cfdb90f`](https://github.com/n24q02m/wet-mcp/commit/cfdb90f57c9ca02213ab9ad45e0a6e0409334bb2))

### Chores

- **deps**: Update ghcr.io/astral-sh/uv:latest docker digest to 3b7b60a
  ([#976](https://github.com/n24q02m/wet-mcp/pull/976),
  [`43266c3`](https://github.com/n24q02m/wet-mcp/commit/43266c3611412f16ecbe3003a635d7680847b320))


## v2.28.2 (2026-04-27)

### Bug Fixes

- Regenerate uv.lock with UV_NO_SOURCES=1 (Docker trap)
  ([#975](https://github.com/n24q02m/wet-mcp/pull/975),
  [`7b38f20`](https://github.com/n24q02m/wet-mcp/commit/7b38f2014b36571fb1a1e3dce859163b2a04b445))


## v2.28.1 (2026-04-27)

### Bug Fixes

- Cap greenlet <3.5.0 to unblock Docker arm64 ([#974](https://github.com/n24q02m/wet-mcp/pull/974),
  [`f9c9250`](https://github.com/n24q02m/wet-mcp/commit/f9c925044599ab5c7c6adabd8482a6bc23145705))

- Retrigger CI ([#974](https://github.com/n24q02m/wet-mcp/pull/974),
  [`f9c9250`](https://github.com/n24q02m/wet-mcp/commit/f9c925044599ab5c7c6adabd8482a6bc23145705))


## v2.28.0 (2026-04-27)

### Bug Fixes

- Bump n24q02m-mcp-core to 1.8.1 ([#969](https://github.com/n24q02m/wet-mcp/pull/969),
  [`e116a7a`](https://github.com/n24q02m/wet-mcp/commit/e116a7ab1c0c369658016e182037ea1ae0caf685))

- Ruff format + Windows root dir filter ([#969](https://github.com/n24q02m/wet-mcp/pull/969),
  [`e116a7a`](https://github.com/n24q02m/wet-mcp/commit/e116a7ab1c0c369658016e182037ea1ae0caf685))

### Features

- Add ## E2E section to CLAUDE.md per Task 21 docs rollout
  ([#966](https://github.com/n24q02m/wet-mcp/pull/966),
  [`d2e7f54`](https://github.com/n24q02m/wet-mcp/commit/d2e7f54e540b0d865ebbb8b480fd7c07054afe4a))


## v2.28.0-beta.2 (2026-04-27)

### Bug Fixes

- Trigger per-sub GDrive device-code in multi-user remote mode
  ([`52ec8da`](https://github.com/n24q02m/wet-mcp/commit/52ec8da247a1f489f1c911b7bce2b5fd3a3a1351))


## v2.28.0-beta.1 (2026-04-27)

### Bug Fixes

- Regenerate uv.lock with UV_NO_SOURCES=1 for Docker build compat
  ([`32c1ea9`](https://github.com/n24q02m/wet-mcp/commit/32c1ea9bddb178ed64f27b423dcb6e86f2e0f18c))

- Sweep doppler/infisical refs to skret SSM
  ([`c433fe4`](https://github.com/n24q02m/wet-mcp/commit/c433fe4a5b16bc58d5cba85dfdedc7245dae905c))

### Features

- Wet-mcp multi-user remote mode via PUBLIC_URL + per-sub credential storage
  ([#965](https://github.com/n24q02m/wet-mcp/pull/965),
  [`ac4b9f6`](https://github.com/n24q02m/wet-mcp/commit/ac4b9f6842d07774cadd1c34d0b598da77ffc36a))


## v2.27.1 (2026-04-24)

### Bug Fixes

- Regenerate uv.lock without [tool.uv.sources] for Docker build
  ([#962](https://github.com/n24q02m/wet-mcp/pull/962),
  [`f6cdf5d`](https://github.com/n24q02m/wet-mcp/commit/f6cdf5de3d1635ccf9d6a1e5c142e3e5a290717e))


## v2.27.0 (2026-04-24)

### Bug Fixes

- Bump n24q02m-mcp-core to 1.7.6 ([#961](https://github.com/n24q02m/wet-mcp/pull/961),
  [`c1f4707`](https://github.com/n24q02m/wet-mcp/commit/c1f470705668f6852a2967a3f22ef9cde93fa06f))

- Bump n24q02m-mcp-core to >=1.7.1 ([#952](https://github.com/n24q02m/wet-mcp/pull/952),
  [`c811ca9`](https://github.com/n24q02m/wet-mcp/commit/c811ca995c4ab7aadf9936249c616db4ed715afb))

- Bump n24q02m-web-core to 1.3.6 ([#959](https://github.com/n24q02m/wet-mcp/pull/959),
  [`757d39b`](https://github.com/n24q02m/wet-mcp/commit/757d39bb5149c2ee6a0ef3e936cf08763c027334))

- Update uv.lock
  ([`581580a`](https://github.com/n24q02m/wet-mcp/commit/581580a452bd55fd53e0ade2c8f2c99022bae192))

### Chores

- **deps**: Update python:3.13-slim-bookworm docker digest to bb73517
  ([#948](https://github.com/n24q02m/wet-mcp/pull/948),
  [`db2395c`](https://github.com/n24q02m/wet-mcp/commit/db2395c379f518423956119061c94497c4e2f75b))

### Features

- Use Smart Daemon Manager for stdio transport
  ([`f49331f`](https://github.com/n24q02m/wet-mcp/commit/f49331f318ffbbbc903b371eb8c57a4d54bcebb7))


## v2.26.7 (2026-04-22)

### Bug Fixes

- Bump mcp-core to 1.6.3 ([#947](https://github.com/n24q02m/wet-mcp/pull/947),
  [`a450ea2`](https://github.com/n24q02m/wet-mcp/commit/a450ea28737227c18e49faed17d25e4c4537b012))

- Bump n24q02m-mcp-core to 1.6.3 (relay form follow redirect_url)
  ([#947](https://github.com/n24q02m/wet-mcp/pull/947),
  [`a450ea2`](https://github.com/n24q02m/wet-mcp/commit/a450ea28737227c18e49faed17d25e4c4537b012))

- Switch Dockerfile builder to python:3.13-slim for Python 3.13.13
  ([#947](https://github.com/n24q02m/wet-mcp/pull/947),
  [`a450ea2`](https://github.com/n24q02m/wet-mcp/commit/a450ea28737227c18e49faed17d25e4c4537b012))


## v2.26.6 (2026-04-22)

### Bug Fixes

- Switch Dockerfile builder to python:3.13-slim for Python 3.13.13
  ([#945](https://github.com/n24q02m/wet-mcp/pull/945),
  [`9a27cba`](https://github.com/n24q02m/wet-mcp/commit/9a27cbabafe99a5c452237d8a5d16d0a42da5496))


## v2.26.5 (2026-04-22)

### Bug Fixes

- Enable UV_PYTHON_DOWNLOADS so Docker build gets Python 3.13.13
  ([#944](https://github.com/n24q02m/wet-mcp/pull/944),
  [`0a55d95`](https://github.com/n24q02m/wet-mcp/commit/0a55d95b63282fd9aa36c13c67e4a50cb2ccb667))


## v2.26.4 (2026-04-22)

### Bug Fixes

- Bump mcp-core to 1.6.2 ([#943](https://github.com/n24q02m/wet-mcp/pull/943),
  [`ba9ba9d`](https://github.com/n24q02m/wet-mcp/commit/ba9ba9d753ce5d4d7641ffea478659864c6ac22f))


## v2.26.3 (2026-04-22)

### Bug Fixes

- Add test coverage for run_remote_relay + main() dispatch
  ([#939](https://github.com/n24q02m/wet-mcp/pull/939),
  [`aeaa524`](https://github.com/n24q02m/wet-mcp/commit/aeaa524db989a1df7b297010812f99f87a384540))

- Bump n24q02m-mcp-core to 1.5.1
  ([`1e454f5`](https://github.com/n24q02m/wet-mcp/commit/1e454f577461c882fa969b9c28f4bc0c615624b0))

- Bump n24q02m-mcp-core to 1.6.1 ([#939](https://github.com/n24q02m/wet-mcp/pull/939),
  [`aeaa524`](https://github.com/n24q02m/wet-mcp/commit/aeaa524db989a1df7b297010812f99f87a384540))

- Bump n24q02m-web-core to 1.3.1 for Docker SearXNG JSON fix
  ([`e263bf1`](https://github.com/n24q02m/wet-mcp/commit/e263bf13ff32b988a0d196071a287e5024defa0e))

- Bump web-core 1.3.3 + qwen3-embed 1.9.0 + setup-uv v8
  ([`d186f0d`](https://github.com/n24q02m/wet-mcp/commit/d186f0def23e0bdd46a160a7499714edc811eb2f))

- Bump web-core to 1.3.5 (docker stdin=DEVNULL + fast-path)
  ([`134a66b`](https://github.com/n24q02m/wet-mcp/commit/134a66bfca6674e3380d622f616a72870f673451))

- Enable auto-SearXNG on Windows (Docker fallback handles lxml)
  ([`94ee0a8`](https://github.com/n24q02m/wet-mcp/commit/94ee0a8677ff12780071f1b1e9ac3af585e7ab12))

- Qualify icacls user as DOMAIN\USER to avoid machine-name collision
  ([`1386c2e`](https://github.com/n24q02m/wet-mcp/commit/1386c2ede8c1aee161bff1f3e8eee76c13260f2f))

- Require explicit MCP_RELAY_URL for remote-relay mode
  ([#939](https://github.com/n24q02m/wet-mcp/pull/939),
  [`aeaa524`](https://github.com/n24q02m/wet-mcp/commit/aeaa524db989a1df7b297010812f99f87a384540))

- Require explicit MCP_RELAY_URL for remote-relay mode per matrix 2.5
  ([#939](https://github.com/n24q02m/wet-mcp/pull/939),
  [`aeaa524`](https://github.com/n24q02m/wet-mcp/commit/aeaa524db989a1df7b297010812f99f87a384540))


## v2.26.2 (2026-04-21)

### Bug Fixes

- Bump non-major Python deps incl mcp-core to 1.5.0
  ([`a794a07`](https://github.com/n24q02m/wet-mcp/commit/a794a071f0ac007b9a20eb8cde2e4f6a705eac63))

- Bump step-security/harden-runner digest to 8d3c67d
  ([`6c5b8a0`](https://github.com/n24q02m/wet-mcp/commit/6c5b8a0367a8375c1d8baf967ec90043ae4915b9))


## v2.26.1 (2026-04-21)

### Bug Fixes

- Accept SubjectContext arg on save_credentials
  ([`6f56018`](https://github.com/n24q02m/wet-mcp/commit/6f560180b63803440475d029df002a80eee6e6f8))

- Hoist regex compilations to module-level for string processing performance
  ([`86b0ea6`](https://github.com/n24q02m/wet-mcp/commit/86b0ea65a804e05cb1444c070fb8aeaa8de31352))

- Pin fastmcp>=3.2.3,<4 to prevent Renovate downgrade to CVE-vulnerable 2.x
  ([`424cec5`](https://github.com/n24q02m/wet-mcp/commit/424cec57a6b5c30c2fecdaa155161cb0253197e1))

- Stdio fallback spawns local credential form, not remote relay
  ([`b9ec5a2`](https://github.com/n24q02m/wet-mcp/commit/b9ec5a2d1ba3f940b370774d57db037946f870b6))

- **deps**: Bump mcp-core to 1.4.3
  ([`326641f`](https://github.com/n24q02m/wet-mcp/commit/326641f7d24f191c18427204f5ce88c9c9ccc489))


## v2.26.0 (2026-04-19)

### Bug Fixes

- Bump mcp-core to 1.3.0 ([#899](https://github.com/n24q02m/wet-mcp/pull/899),
  [`4d906c5`](https://github.com/n24q02m/wet-mcp/commit/4d906c5b9a24c88ed01fa5e0dd2ce0340a87997e))

- Bump n24q02m-mcp-core to 1.4.0 ([#909](https://github.com/n24q02m/wet-mcp/pull/909),
  [`5069a4e`](https://github.com/n24q02m/wet-mcp/commit/5069a4ede4eb06fea17b045583d19ecd92bd78a2))

- Propagate GDrive device code failure to browser UI
  ([#907](https://github.com/n24q02m/wet-mcp/pull/907),
  [`1f56b88`](https://github.com/n24q02m/wet-mcp/commit/1f56b88e5d3b0f73a26cb41c8f1db5bc740326e9))

- Restrict Windows token file permissions to current user only
  ([#900](https://github.com/n24q02m/wet-mcp/pull/900),
  [`aed22d3`](https://github.com/n24q02m/wet-mcp/commit/aed22d318f376adff1fe0cdd6eb399d4d2b1a860))

- Use dynamic SearXNG port in test assertions (web-core 1.2.0 parity)
  ([#903](https://github.com/n24q02m/wet-mcp/pull/903),
  [`730bc57`](https://github.com/n24q02m/wet-mcp/commit/730bc573d30791e6182f94a8dc4cb0b96ececcb6))

- **deps**: Update non-major dependencies ([#901](https://github.com/n24q02m/wet-mcp/pull/901),
  [`986d789`](https://github.com/n24q02m/wet-mcp/commit/986d789665d2c28784f3f3756c0d80d8051a840a))

### Chores

- **deps**: Update github/codeql-action digest to 95e58e9
  ([#894](https://github.com/n24q02m/wet-mcp/pull/894),
  [`b8c8ea3`](https://github.com/n24q02m/wet-mcp/commit/b8c8ea3625161dd4ac0f26ffeadc18b6f68e5d6d))

### Features

- Merge setup tool into config with setup_* sub-actions
  ([#898](https://github.com/n24q02m/wet-mcp/pull/898),
  [`3af84a7`](https://github.com/n24q02m/wet-mcp/commit/3af84a752705c191584b614306cc42193798a8db))


## v2.25.2 (2026-04-17)

### Bug Fixes

- Bump n24q02m-mcp-core to 1.2.0 (authlib CVE patch)
  ([`65f404a`](https://github.com/n24q02m/wet-mcp/commit/65f404ab1bc7600699ca0474509be16979f4582f))


## v2.25.1 (2026-04-17)

### Bug Fixes

- Bump n24q02m-mcp-core to 1.1.1 for OAuth issuer fix
  ([`e48f48a`](https://github.com/n24q02m/wet-mcp/commit/e48f48aead602ab12695737d997662e944c98518))


## v2.25.0 (2026-04-17)

### Bug Fixes

- Add composite index to accelerate RAG prefetching
  ([`8b237d6`](https://github.com/n24q02m/wet-mcp/commit/8b237d6350c297b479b126cf37586c590c8aad72))

- Add debug logging for GDrive callback and remove auto-open browser
  ([`297ec46`](https://github.com/n24q02m/wet-mcp/commit/297ec4679d1be504ea4fefdc1bc60e628c406eff))

- Add diacritic preservation pre-commit hook ([#891](https://github.com/n24q02m/wet-mcp/pull/891),
  [`98748e9`](https://github.com/n24q02m/wet-mcp/commit/98748e951d7e1eaf2127114c797cbee6ffee49d1))

- Add tests for chunk_llms_txt in docs ([#826](https://github.com/n24q02m/wet-mcp/pull/826),
  [`b3abebb`](https://github.com/n24q02m/wet-mcp/commit/b3abebbce08507376a72509c51108ae58b3b8d93))

- Add tests for chunk_markdown in docs ([#829](https://github.com/n24q02m/wet-mcp/pull/829),
  [`0ec6d95`](https://github.com/n24q02m/wet-mcp/commit/0ec6d95a0ed11e11f3d79856a01682b37a273e12))

- Add tests for get_model_capabilities in llm ([#836](https://github.com/n24q02m/wet-mcp/pull/836),
  [`2441119`](https://github.com/n24q02m/wet-mcp/commit/24411194ceb45ffb686f07a9feb27ca79b2e3491))

- Add tests for token management in token_store
  ([#827](https://github.com/n24q02m/wet-mcp/pull/827),
  [`bf9ed1a`](https://github.com/n24q02m/wet-mcp/commit/bf9ed1ae94d196ecc6ceef670e0bf88f1c2a6ce0))

- Apply ruff format to db.py and test_docs_coverage.py
  ([`c7172a8`](https://github.com/n24q02m/wet-mcp/commit/c7172a8b15bf78d6c326f19db45bcfbe85e940fe))

- Auto-open default browser at Google device-code URL
  ([`6f6c539`](https://github.com/n24q02m/wet-mcp/commit/6f6c539591cab16911de25f4c37afc4a95acd41b))

- Bump authlib + gdown + langsmith + pytest + python-multipart
  ([`e46a1ca`](https://github.com/n24q02m/wet-mcp/commit/e46a1ca25c432397b438aaf6f55ad3cb1801c591))

- Bump n24q02m-mcp-core to >=1.0.0 stable
  ([`15ed8ce`](https://github.com/n24q02m/wet-mcp/commit/15ed8cec8fb739f1faf8bca22c5daa1fcce7f11f))

- Clean up debug logging for GDrive callback
  ([`c2b67ef`](https://github.com/n24q02m/wet-mcp/commit/c2b67efd465421bb480ab8be6bff5dad454679da))

- Correct README setup tool actions and config tool description
  ([`d265506`](https://github.com/n24q02m/wet-mcp/commit/d265506b9b8c6ee6625cfd900e2af213d4c7b549))

- Correct relay schema capability info for search and extraction
  ([`c552daa`](https://github.com/n24q02m/wet-mcp/commit/c552daae9b6e65d064fdfa3b5485c45389fdd3da))

- Cover _gdrive_token_poll and credential_state edge paths
  ([`dad75ec`](https://github.com/n24q02m/wet-mcp/commit/dad75ecb1f7d6aeb5784377c92377da305525118))

- Cover try_open_browser paths + drop local uv.sources override
  ([`36d2479`](https://github.com/n24q02m/wet-mcp/commit/36d24798266acc7a088a117d33016e959b4f8648))

- Do not auto-open browser from background sync loop
  ([`ee48db9`](https://github.com/n24q02m/wet-mcp/commit/ee48db9861077697443db6f82c11729880e4bb4b))

- Ensure chunk_llms_txt test content forces multi-chunk split
  ([`2b4b80c`](https://github.com/n24q02m/wet-mcp/commit/2b4b80c626b638bcfd1dc94224306ac97c6be93f))

- Ignore coverage.xml and htmlcov artifacts
  ([`0b16f3c`](https://github.com/n24q02m/wet-mcp/commit/0b16f3c0cc29c692585d544d08900a9f3734ad36))

- Linting issues in tests/test_setup_tool_logging.py
  ([#778](https://github.com/n24q02m/wet-mcp/pull/778),
  [`9982527`](https://github.com/n24q02m/wet-mcp/commit/998252769eb0eb7a77eb245ccb062bdb35d643b2))

- MacOS CI test failures (hardcoded /tmp + sqlite-vec extension)
  ([`f43d400`](https://github.com/n24q02m/wet-mcp/commit/f43d40052e62afdbabd13ba12ba05e3fbdb08933))

- N+1 query in document prefetching via row-value IN
  ([`e51b17e`](https://github.com/n24q02m/wet-mcp/commit/e51b17e56be81986d7ec56689000d74582747c32))

- Patch langchain-core CVE-2026-40087 and cryptography CVE-2026-39892
  ([`b3a80a6`](https://github.com/n24q02m/wet-mcp/commit/b3a80a6c62cd3ae7c72376cf44295589453c2502))

- Remove unused _AUDIO_OUTPUT_MODELS import
  ([`b994e23`](https://github.com/n24q02m/wet-mcp/commit/b994e2308df5b33006683fad51eaf02fd0451760))

- Retry GDrive folder search before creating to prevent duplicates
  ([`a034bfb`](https://github.com/n24q02m/wet-mcp/commit/a034bfbbd4a6b7dab5a350e9e1690aa8e6984547))

- Revert GDrive scope to drive.file (drive.appdata incompatible with device code flow)
  ([`134c028`](https://github.com/n24q02m/wet-mcp/commit/134c02844d260e4cfd8ae6b2455a19dfc3154d6a))

- Simplify run_http to use run_local_server with setup_complete_hook
  ([`7093cb9`](https://github.com/n24q02m/wet-mcp/commit/7093cb9704ba29b8714d645c42daf5c58dce03e8))

- Sync local changes from workspace
  ([`3329320`](https://github.com/n24q02m/wet-mcp/commit/3329320c8236c5d4e1d58765e2132115248e11e3))

- Tighten _is_unsupported_param pattern and document reranker sync gap
  ([`9c721db`](https://github.com/n24q02m/wet-mcp/commit/9c721db9c81c5ed2a6b97a8f406e41e625dd7f08))

- Unblock main branch CI (lint+type+test cascade from async embedder migration)
  ([`811e9d1`](https://github.com/n24q02m/wet-mcp/commit/811e9d18bf11f9e12076d87bc84f46af00a6ef41))

- Update docker/build-push-action digest to bcafcac
  ([`8b70385`](https://github.com/n24q02m/wet-mcp/commit/8b703859aaea8c1f330fcaf30dd681c021064e12))

- Update non-major dependencies
  ([`f823d95`](https://github.com/n24q02m/wet-mcp/commit/f823d95c84bbd5dcad96380cfa4d6b40b8d4f6c4))

- Update python:3.13-slim-bookworm docker digest to 061b6e5
  ([`f790a1e`](https://github.com/n24q02m/wet-mcp/commit/f790a1e30c41350eac90bf9afba5dbc1d65d5fbd))

- Use re.finditer with early break in chunk quality score
  ([`61bead5`](https://github.com/n24q02m/wet-mcp/commit/61bead5c387bd5f81f4b35c42c0f55641c370857))

- **deps**: Bump actions/create-github-app-token digest to 1b10c78
  ([#852](https://github.com/n24q02m/wet-mcp/pull/852),
  [`b3f9090`](https://github.com/n24q02m/wet-mcp/commit/b3f9090cbc435e0260a896be3f6b3ec79c3fdb34))

- **deps**: Bump actions/upload-artifact digest to 043fb46
  ([#853](https://github.com/n24q02m/wet-mcp/pull/853),
  [`f95205a`](https://github.com/n24q02m/wet-mcp/commit/f95205aacbab286529c61690c12b779773971b64))

- **deps**: Bump cohere to v6 ([#854](https://github.com/n24q02m/wet-mcp/pull/854),
  [`6fb76c7`](https://github.com/n24q02m/wet-mcp/commit/6fb76c7dd2615e412914c4478c58e9816cc0ffc7))

- **deps**: Bump step-security/harden-runner digest to 6c3c2f2
  ([#842](https://github.com/n24q02m/wet-mcp/pull/842),
  [`869e754`](https://github.com/n24q02m/wet-mcp/commit/869e75442610000f7cd68724532d523aa45adcb7))

### Chores

- Acknowledge PR closure and finalize cleanup task
  ([#776](https://github.com/n24q02m/wet-mcp/pull/776),
  [`b3a1133`](https://github.com/n24q02m/wet-mcp/commit/b3a113335ab6b2212e6205be0d7f0279170b51c9))

- Acknowledge PR closure and stop work ([#775](https://github.com/n24q02m/wet-mcp/pull/775),
  [`1cc7b78`](https://github.com/n24q02m/wet-mcp/commit/1cc7b78408ff98fad93ef6434cbb15be0f1427c9))

- Add logging to broad exception catches in credential_state.py
  ([#776](https://github.com/n24q02m/wet-mcp/pull/776),
  [`b3a1133`](https://github.com/n24q02m/wet-mcp/commit/b3a113335ab6b2212e6205be0d7f0279170b51c9))

- Final state after PR closure acknowledgement ([#778](https://github.com/n24q02m/wet-mcp/pull/778),
  [`9982527`](https://github.com/n24q02m/wet-mcp/commit/998252769eb0eb7a77eb245ccb062bdb35d643b2))

### Features

- Add cross-OS CI matrix (ubuntu/windows/macos)
  ([`d1acd98`](https://github.com/n24q02m/wet-mcp/commit/d1acd98dbd87c41b0d2acf42549a7c44a5f2063d))

- Add GDrive device code flow to local OAuth and fix Jina helpText
  ([`6d591d9`](https://github.com/n24q02m/wet-mcp/commit/6d591d94a814333fd26d3f6876863ab34e81531c))

- Add HTTP transport with local OAuth AS, replace stdio default
  ([`e9b9bed`](https://github.com/n24q02m/wet-mcp/commit/e9b9bed035d455a21cdc880a2fc36f026063285d))

- Add HTTP+OAuth E2E test to unified test file
  ([`e397970`](https://github.com/n24q02m/wet-mcp/commit/e397970e81289ed58e1dc9364ae4d55534ae8663))

- Add tests for set_gdrive_complete_callback registration
  ([`d9f7af4`](https://github.com/n24q02m/wet-mcp/commit/d9f7af488b1a7994d1ccdecce3e73d24472b3b43))

- Hoist auth error patterns tuple to module scope in reranker
  ([`e3f7338`](https://github.com/n24q02m/wet-mcp/commit/e3f7338b329feffa202072f65b939cde52ee11b7))

- Migrate from mcp-relay-core to mcp-core
  ([`2efc8d0`](https://github.com/n24q02m/wet-mcp/commit/2efc8d09a8ad8f1405fb074a3fbff6a41c00cb0f))

- Migrate GDrive sync from drive.file to drive.appdata scope
  ([`1e25f17`](https://github.com/n24q02m/wet-mcp/commit/1e25f17a1e6a6eb65f84bf54ea6477667d5febea))

- Wire GDrive completion callback to form status polling
  ([`eb4980e`](https://github.com/n24q02m/wet-mcp/commit/eb4980ea551e8fd04ad375f27ed411deb5e86270))

### Performance Improvements

- Finalize async embedding backend conversion ([#775](https://github.com/n24q02m/wet-mcp/pull/775),
  [`1cc7b78`](https://github.com/n24q02m/wet-mcp/commit/1cc7b78408ff98fad93ef6434cbb15be0f1427c9))

- Optimize dictionary scoring union in `db.py` ([#815](https://github.com/n24q02m/wet-mcp/pull/815),
  [`2138166`](https://github.com/n24q02m/wet-mcp/commit/21381661e69db828750c54bd22924ee174fc7459))

- Replace blocking time.sleep with asyncio.sleep in embedder
  ([#775](https://github.com/n24q02m/wet-mcp/pull/775),
  [`1cc7b78`](https://github.com/n24q02m/wet-mcp/commit/1cc7b78408ff98fad93ef6434cbb15be0f1427c9))

### Refactoring

- Improve visibility of broad exception catches in credential_state.py
  ([#776](https://github.com/n24q02m/wet-mcp/pull/776),
  [`b3a1133`](https://github.com/n24q02m/wet-mcp/commit/b3a113335ab6b2212e6205be0d7f0279170b51c9))

- Log broad exceptions in _validate_cloud_models
  ([#778](https://github.com/n24q02m/wet-mcp/pull/778),
  [`9982527`](https://github.com/n24q02m/wet-mcp/commit/998252769eb0eb7a77eb245ccb062bdb35d643b2))

- Log broad exceptions in _validate_cloud_models (ready for review)
  ([#778](https://github.com/n24q02m/wet-mcp/pull/778),
  [`9982527`](https://github.com/n24q02m/wet-mcp/commit/998252769eb0eb7a77eb245ccb062bdb35d643b2))

- **server**: Narrow exception handling and add logging in tool JSON formatting
  ([#812](https://github.com/n24q02m/wet-mcp/pull/812),
  [`cfb9799`](https://github.com/n24q02m/wet-mcp/commit/cfb979943d7db10cec88821acfe3bc46ee45bcd0))

- **server**: Narrow exception handling in media.analyze
  ([#812](https://github.com/n24q02m/wet-mcp/pull/812),
  [`cfb9799`](https://github.com/n24q02m/wet-mcp/commit/cfb979943d7db10cec88821acfe3bc46ee45bcd0))


## v2.24.0 (2026-04-07)

### Bug Fixes

- Add tests for credential state relay and structured extraction coverage gaps
  ([`0f39b1f`](https://github.com/n24q02m/wet-mcp/commit/0f39b1f6bcc287468bf751b01be2d5eeb1282e1d))

- Pin web-core >= 1.1.0 for SearXNG brand section fix
  ([`a8932ed`](https://github.com/n24q02m/wet-mcp/commit/a8932ed7c92b36030753f694c20b783bd9e9670d))

- Remove BETA markers and promote relay as primary setup method
  ([`993fc7c`](https://github.com/n24q02m/wet-mcp/commit/993fc7c9fd0f19a2ecee30ef0a6f10c42173fb1a))

- Set UV_NO_SOURCES env for entire CI lint-and-test job
  ([`df8659a`](https://github.com/n24q02m/wet-mcp/commit/df8659ac9a2f7b0ea3d391667094ecd1289c5547))

- Use --no-sources in CI to resolve mcp-relay-core from PyPI
  ([`9ee083b`](https://github.com/n24q02m/wet-mcp/commit/9ee083b7573ad8cb7800fd7cecacf8c697c240ab))

### Features

- Migrate code review from Qodo to CodeRabbit ([#756](https://github.com/n24q02m/wet-mcp/pull/756),
  [`cb1e42f`](https://github.com/n24q02m/wet-mcp/commit/cb1e42f95fd57ddc5e2bd56fe2e8fcdaa375b203))


## v2.23.5-beta.3 (2026-04-07)

### Bug Fixes

- Preserve regenerated uv.lock after COPY in Docker build
  ([`3077ad3`](https://github.com/n24q02m/wet-mcp/commit/3077ad303b2c20dd210b72e41c106caed39d6219))


## v2.23.5-beta.2 (2026-04-07)

### Bug Fixes

- Persist GDrive folder ID to prevent duplicate folder creation
  ([`2ffa4ac`](https://github.com/n24q02m/wet-mcp/commit/2ffa4acdee4a630e1654fd66b5fd946194f6daf8))

- Strip uv sources override in Docker build for PyPI resolution
  ([`7c9e087`](https://github.com/n24q02m/wet-mcp/commit/7c9e087576271903e0ab7e61fea9b701c51e8e76))


## v2.23.5-beta.1 (2026-04-07)

### Bug Fixes

- Use --no-sources in Docker build for PyPI dependency resolution
  ([`44698d6`](https://github.com/n24q02m/wet-mcp/commit/44698d67e8c3177ed032e1957ea6fbd904845b04))


## v2.23.4 (2026-04-07)

### Bug Fixes

- Disable SearXNG auto-start on Windows
  ([`8b7c588`](https://github.com/n24q02m/wet-mcp/commit/8b7c5880fb0e3e84772de61e1034b44ba5009b51))


## v2.23.3 (2026-04-07)

### Bug Fixes

- Re-init embedding and reranker in setup complete action
  ([`42e70e2`](https://github.com/n24q02m/wet-mcp/commit/42e70e27cc2d24037dd732149d4817f05719f63c))


## v2.23.2 (2026-04-06)

### Bug Fixes

- Share cloud keys to peer servers when loading from config on startup
  ([`cb48897`](https://github.com/n24q02m/wet-mcp/commit/cb488971cb7f5d2e671341f40404a83f9110cb16))


## v2.23.1 (2026-04-06)

### Bug Fixes

- Send complete message to browser after relay and trigger GDrive OAuth
  ([`0bcdae9`](https://github.com/n24q02m/wet-mcp/commit/0bcdae9ba651057fffde312abe3d93f73fd91369))


## v2.23.0 (2026-04-06)

### Features

- Remove set_env action and auto-fallback from wet-mcp credential flow
  ([`41f39ff`](https://github.com/n24q02m/wet-mcp/commit/41f39ff2ebc24d7c47946e65e2048032f7148b5b))


## v2.22.0 (2026-04-06)

### Bug Fixes

- Add complete action and lazy setup hints in cloud tools
  ([`bdb6bac`](https://github.com/n24q02m/wet-mcp/commit/bdb6bac85745938f3a4800d2edc20ae01bd457d0))

- Mark relay as BETA, promote env vars as primary setup method
  ([`52d3ff9`](https://github.com/n24q02m/wet-mcp/commit/52d3ff938f96eb7a07bc946e2e74cd92ee49b2c7))

### Features

- Non-blocking relay with state machine and lazy trigger
  ([`f40ee6b`](https://github.com/n24q02m/wet-mcp/commit/f40ee6b2af411ab433d9a85aa90aacab0601ffca))


## v2.21.0 (2026-04-04)

### Bug Fixes

- Remove dead code (research_topic prompt, trigger_relay_setup)
  ([#710](https://github.com/n24q02m/wet-mcp/pull/710),
  [`2b19d52`](https://github.com/n24q02m/wet-mcp/commit/2b19d5228d92aad5a29805ad0d1ceb29969f1bf3))

- Remove exposed model name from setup guide
  ([`18e1ff5`](https://github.com/n24q02m/wet-mcp/commit/18e1ff5e137f36bdd048d1fdb95c4acfaca162eb))

### Features

- Add agent/manual setup guides, simplify README, cleanup root
  ([`51fbaa7`](https://github.com/n24q02m/wet-mcp/commit/51fbaa76d918983391ea83986c6d11ac26847150))


## v2.20.1 (2026-04-03)

### Bug Fixes

- Consolidated Jules PR review -- perf, cleanup, deps, docs
  ([#670](https://github.com/n24q02m/wet-mcp/pull/670),
  [`0d5b9c1`](https://github.com/n24q02m/wet-mcp/commit/0d5b9c1500d223a6b175692c93e54ba8a74dca72))

- Scope marketplace sync token to claude-plugins repo
  ([`4081f16`](https://github.com/n24q02m/wet-mcp/commit/4081f16ef87ce7443729d4f631ba1bc46aed570a))


## v2.20.0 (2026-04-03)

### Features

- Remove deprecated Gemini CLI extension support
  ([`e8d1ba0`](https://github.com/n24q02m/wet-mcp/commit/e8d1ba06061a3234dc5853ef260a6fa6a53efa5c))


## v2.20.0-beta.1 (2026-04-03)

### Bug Fixes

- Also mock ensure_searxng to prevent SearXNG auto-start in tests
  ([#612](https://github.com/n24q02m/wet-mcp/pull/612),
  [`e792441`](https://github.com/n24q02m/wet-mcp/commit/e7924419160e15e243f51f70a09e2bcfa56f175f))

- Mock _background_index_and_search in docs search tests
  ([#612](https://github.com/n24q02m/wet-mcp/pull/612),
  [`e792441`](https://github.com/n24q02m/wet-mcp/commit/e7924419160e15e243f51f70a09e2bcfa56f175f))

- Mock _discover_docs_url to prevent SearXNG startup in tests
  ([#612](https://github.com/n24q02m/wet-mcp/pull/612),
  [`e792441`](https://github.com/n24q02m/wet-mcp/commit/e7924419160e15e243f51f70a09e2bcfa56f175f))

- Relay setup, E2E infrastructure, and Windows test compatibility
  ([#669](https://github.com/n24q02m/wet-mcp/pull/669),
  [`7063289`](https://github.com/n24q02m/wet-mcp/commit/7063289b3ecffe993b3efc41824c30e979f22696))

- Resolve Windows test compatibility issues ([#612](https://github.com/n24q02m/wet-mcp/pull/612),
  [`e792441`](https://github.com/n24q02m/wet-mcp/commit/e7924419160e15e243f51f70a09e2bcfa56f175f))

- Switch mcp-relay-core from git dep to published PyPI package
  ([#669](https://github.com/n24q02m/wet-mcp/pull/669),
  [`7063289`](https://github.com/n24q02m/wet-mcp/commit/7063289b3ecffe993b3efc41824c30e979f22696))

### Features

- Add E2E tests + migrate sync from rclone to GDrive OAuth
  ([#669](https://github.com/n24q02m/wet-mcp/pull/669),
  [`7063289`](https://github.com/n24q02m/wet-mcp/commit/7063289b3ecffe993b3efc41824c30e979f22696))

- Add zero-env-config relay setup via mcp-relay-core
  ([#669](https://github.com/n24q02m/wet-mcp/pull/669),
  [`7063289`](https://github.com/n24q02m/wet-mcp/commit/7063289b3ecffe993b3efc41824c30e979f22696))

- Delegate SearXNG, HTTP security, and search to web-core
  ([#612](https://github.com/n24q02m/wet-mcp/pull/612),
  [`e792441`](https://github.com/n24q02m/wet-mcp/commit/e7924419160e15e243f51f70a09e2bcfa56f175f))

- E2E testing + relay setup + GDrive OAuth migration
  ([#669](https://github.com/n24q02m/wet-mcp/pull/669),
  [`7063289`](https://github.com/n24q02m/wet-mcp/commit/7063289b3ecffe993b3efc41824c30e979f22696))

### Refactoring

- Delegate SearXNG, HTTP security, and search to web-core
  ([#612](https://github.com/n24q02m/wet-mcp/pull/612),
  [`e792441`](https://github.com/n24q02m/wet-mcp/commit/e7924419160e15e243f51f70a09e2bcfa56f175f))


## v2.19.0 (2026-04-01)

### Bug Fixes

- Correct CodeQL action SHA pin
  ([`07fc6eb`](https://github.com/n24q02m/wet-mcp/commit/07fc6eba687956bc27d120b2f1bd63844702e43c))

- Correct test mocking for relay settings and platform-specific tests
  ([`ed98b84`](https://github.com/n24q02m/wet-mcp/commit/ed98b84cd69cdf6c7013de344b121246c0b8b3c6))

- Format relay_setup.py
  ([`df068be`](https://github.com/n24q02m/wet-mcp/commit/df068be4dd282136ae5da3fc59e6a8d0b07c39aa))

- Prevent env var leakage in relay setup tests
  ([`33b73fe`](https://github.com/n24q02m/wet-mcp/commit/33b73fec601b161ea8e3f1e72527e9e14fdebc46))

- Remove GOOGLE_DRIVE_CLIENT_ID from relay form
  ([`94ce50b`](https://github.com/n24q02m/wet-mcp/commit/94ce50bf41e049af080b8a73e0f76dc7ca095fcc))

- Send complete message AFTER GDrive OAuth, not before
  ([`809a417`](https://github.com/n24q02m/wet-mcp/commit/809a4175ecd5649f5685644db628b7d4cb74b34a))

- Trigger GDrive OAuth from default settings, not relay config
  ([`9024faf`](https://github.com/n24q02m/wet-mcp/commit/9024fafa1b3a8f5e17b191e8db6854fa6f2b54a4))

- **ci**: Add coverage threshold fail_under=95
  ([`d59b080`](https://github.com/n24q02m/wet-mcp/commit/d59b080ef7500aa4e1b535821eb8ab3903dd17ce))

- **ci**: Replace Semgrep with CodeQL for public repo SAST compliance
  ([`4a722e0`](https://github.com/n24q02m/wet-mcp/commit/4a722e0420d44b530557d6e5976015e4d9318ac7))

- **test**: Update relay schema tests for flat fields structure
  ([`cabfca0`](https://github.com/n24q02m/wet-mcp/commit/cabfca0ebf8b866bc5e7b9a7f60ebffe6c6a7cf6))

### Chores

- **deps**: Lock file maintenance ([#601](https://github.com/n24q02m/wet-mcp/pull/601),
  [`8966070`](https://github.com/n24q02m/wet-mcp/commit/8966070d066acf540819099f4b583cdc48bf7710))

### Continuous Integration

- Fix Qodo vertex_ai config and VERTEXAI_LOCATION
  ([`824bcb8`](https://github.com/n24q02m/wet-mcp/commit/824bcb81d9e0984f082d13b6869548b0a5b62b4b))

- **cd**: Add plugin marketplace sync on stable release
  ([`e203f86`](https://github.com/n24q02m/wet-mcp/commit/e203f863c76ed9422596238acc1ab1832b58ca41))

### Features

- Add GDrive OAuth client_secret for Device Code token exchange
  ([`9ff4fcc`](https://github.com/n24q02m/wet-mcp/commit/9ff4fcc6d76e86ba43eb7663fabb84e42cdaabcf))

- Boost test coverage to 95%+ with comprehensive unit tests
  ([`5a04b7d`](https://github.com/n24q02m/wet-mcp/commit/5a04b7da41c21020e0d20595c6c338a9e9f3def7))

- Ship default GDrive OAuth Client ID
  ([`a9d9c9b`](https://github.com/n24q02m/wet-mcp/commit/a9d9c9b3b7b533962026f05c88e3be5fc2518455))


## v2.19.0-beta.1 (2026-03-31)

### Bug Fixes

- Correct OpenAI helpText to include LLM capability
  ([`cac4ff1`](https://github.com/n24q02m/wet-mcp/commit/cac4ff1a98de740a69a630966cc588771280f1ec))

- Correct relay timeout message from 30s to actual 120s
  ([`f82afe1`](https://github.com/n24q02m/wet-mcp/commit/f82afe10806b0f231154867e565cf790c1dcf52d))

### Features

- Enable GDrive sync by default
  ([`25b0b53`](https://github.com/n24q02m/wet-mcp/commit/25b0b531d2cbed9c7a627d79c45ffb7d240aa621))

- Redesign relay schema with capability-based layout and priority info
  ([`c298266`](https://github.com/n24q02m/wet-mcp/commit/c298266f5fac5a7eb74503d5ec973d083034616e))

- Trigger GDrive OAuth Device Code after relay config submit
  ([`f53b384`](https://github.com/n24q02m/wet-mcp/commit/f53b384e3d421446d87025ef10d314f8f30d205d))

### Refactoring

- Use google_drive_client_id check instead of sync_enabled guard
  ([`a93d64a`](https://github.com/n24q02m/wet-mcp/commit/a93d64a8e343e559440af0797d96b4e89c159938))


## v2.18.2-beta.2 (2026-03-31)

### Bug Fixes

- Use waitress WSGI server on Windows to prevent SearXNG deadlock
  ([`6de3899`](https://github.com/n24q02m/wet-mcp/commit/6de3899af26385549068601207e7b6c0e65a5b29))


## v2.18.2-beta.1 (2026-03-30)

### Bug Fixes

- Resolve SearXNG search timeout on Windows due to stderr pipe deadlock
  ([`4d404a1`](https://github.com/n24q02m/wet-mcp/commit/4d404a17e7a693428323cae87dfe3e587a8269a9))

- Resolve ty type check errors with proper ty: ignore comments
  ([`34f4313`](https://github.com/n24q02m/wet-mcp/commit/34f43134414e7f6f1d4e7df0aef85c96e6546c5d))

### Refactoring

- Merge setup tool into config tool
  ([`df17ef1`](https://github.com/n24q02m/wet-mcp/commit/df17ef164da325ff841d5cbe53f7a6690ff737b6))

- Merge setup tool into config tool
  ([`b0ea5da`](https://github.com/n24q02m/wet-mcp/commit/b0ea5da079bd5ffbdf3378d59c6ea300828835eb))


## v2.18.1 (2026-03-28)

### Bug Fixes

- Bump mcp-relay-core to >=1.0.5
  ([`ad98179`](https://github.com/n24q02m/wet-mcp/commit/ad98179a4705d0d701290a51daa8e48988915a70))

- Increase relay timeout from 30s to 120s
  ([`57bd389`](https://github.com/n24q02m/wet-mcp/commit/57bd38902e3ad3af33acc4bfd1bc146f2dbf7b74))

- Replace combined API_KEYS with individual provider keys in relay schema
  ([`80049ec`](https://github.com/n24q02m/wet-mcp/commit/80049ec497ecffa1150c2fdf546ef3409e2ca853))

- Use read_config instead of resolve_config for relay config loading
  ([`7d6fb0d`](https://github.com/n24q02m/wet-mcp/commit/7d6fb0d72a057b5472b8aeb4eaaadf489a9a83ff))

- **deps**: Update non-major dependencies ([#595](https://github.com/n24q02m/wet-mcp/pull/595),
  [`064f9a2`](https://github.com/n24q02m/wet-mcp/commit/064f9a215b7194a69797df49030f2383855e8c9e))

### Chores

- **deps**: Lock file maintenance ([#598](https://github.com/n24q02m/wet-mcp/pull/598),
  [`018039a`](https://github.com/n24q02m/wet-mcp/commit/018039a0148e2fe4dd4fc6e7a5f4b0e41cb3827d))

- **deps**: Update actions/create-github-app-token action to v3
  ([#596](https://github.com/n24q02m/wet-mcp/pull/596),
  [`c2694e8`](https://github.com/n24q02m/wet-mcp/commit/c2694e8f4c163c50ed99673178a86aefea9a7f07))

- **deps**: Update google-github-actions/auth action to v3
  ([#597](https://github.com/n24q02m/wet-mcp/pull/597),
  [`6dcf9d8`](https://github.com/n24q02m/wet-mcp/commit/6dcf9d817c80c3e6c5456dade622e88a02b040c2))

### Documentation

- Fix stale addopts, sync lib, and relay schema mode in CLAUDE.md
  ([`ae0dd1a`](https://github.com/n24q02m/wet-mcp/commit/ae0dd1af23e85cde2101771609e22740ea142617))

- Fix stale rclone reference in AGENTS.md
  ([`414e806`](https://github.com/n24q02m/wet-mcp/commit/414e806e478b7edfd55aed5a721246fb93461e17))

- Update CLAUDE.md with missing modules and Google Drive sync
  ([`cb82c65`](https://github.com/n24q02m/wet-mcp/commit/cb82c65e41449c96c84d1710aa13b3231f3f5ed7))

### Testing

- Update relay schema and config tests for cloud mode refactor
  ([`29bdc60`](https://github.com/n24q02m/wet-mcp/commit/29bdc60a5d8b659e824cb205b07fdb1318a60e43))


## v2.18.0 (2026-03-27)

### Bug Fixes

- Resolve ty type check errors in relay_setup
  ([`40095b2`](https://github.com/n24q02m/wet-mcp/commit/40095b2f0706e8b039014b48a9da8651008b5584))

- Send complete message to relay page after config saved
  ([`6fc72ce`](https://github.com/n24q02m/wet-mcp/commit/6fc72ce42fcfcc16170afad261403dacf2e74da8))

- **ci**: Consolidate SMTP_USERNAME and NOTIFY_EMAIL into one secret
  ([`cf38557`](https://github.com/n24q02m/wet-mcp/commit/cf38557ec97c53b7723faf38bd9f1d3f883af898))

- **ci**: Consolidate SMTP_USERNAME+PASSWORD into SMTP_CREDENTIAL
  ([`5a42f50`](https://github.com/n24q02m/wet-mcp/commit/5a42f50e78d8bf9fd0eb6e8fb23cc5c32b59d9e3))

- **tests**: Remove LiteLLM proxy mode from relay schema and fix test mocks
  ([`676529d`](https://github.com/n24q02m/wet-mcp/commit/676529d30d2891e44c0b158d966ee0f57779e9c0))

### Code Style

- Format sync test file
  ([`f859534`](https://github.com/n24q02m/wet-mcp/commit/f85953413c9cd361fbc78974c27223591c6c55e9))

### Features

- Replace rclone with Google Drive API for sync
  ([`50b1bc2`](https://github.com/n24q02m/wet-mcp/commit/50b1bc2d9f98b6866aa42ce083a7920ad24746c7))


## v2.18.0-beta.1 (2026-03-27)

### Bug Fixes

- Credential resolution order -- relay only when no local credentials
  ([`cfbc9c3`](https://github.com/n24q02m/wet-mcp/commit/cfbc9c3de1d9d86e0e3452d5c43c1f802fdc0c60))

- Disable HTTP/2 for embedded SearXNG on Windows
  ([`b304f78`](https://github.com/n24q02m/wet-mcp/commit/b304f78755666786ed6b50bb9497aae17c7caaaa))

- Pin Docker base images to SHA digests
  ([`a60cc96`](https://github.com/n24q02m/wet-mcp/commit/a60cc96687bcbfaca18bcfa31f1f6f24440e95d1))

- Pin pre-commit hooks to commit SHA
  ([`87326a0`](https://github.com/n24q02m/wet-mcp/commit/87326a00e177aa25b06e32d391152aef356f96cb))

- Prevent arbitrary file read in local file conversion tool
  ([#586](https://github.com/n24q02m/wet-mcp/pull/586),
  [`07a521f`](https://github.com/n24q02m/wet-mcp/commit/07a521ffab7d3c7358e2f3c6449b729c700ee01c))

- **cd**: Remove empty env blocks from OIDC migration
  ([`f468cca`](https://github.com/n24q02m/wet-mcp/commit/f468cca450ac8424afc04b41d627f3e2b67fda5f))

- **cd**: Replace GH_PAT with GitHub App installation token
  ([`14223f5`](https://github.com/n24q02m/wet-mcp/commit/14223f59f4b4f12aa7e3342f02ef12fdcc8e6c87))

- **cd**: Use PyPI OIDC trusted publishing instead of PYPI_TOKEN
  ([`f65d77c`](https://github.com/n24q02m/wet-mcp/commit/f65d77c2c7ebe031dfb5bc9dbbfe35c3fc477353))

- **ci**: Remove CODECOV_TOKEN, use tokenless upload
  ([`a543996`](https://github.com/n24q02m/wet-mcp/commit/a5439961ac69b6173b718ffac06d34617c52303e))

- **ci**: Use Vertex AI WIF instead of GEMINI_API_KEY for code review
  ([`f752d11`](https://github.com/n24q02m/wet-mcp/commit/f752d118d4ddd1f55745aa1c098e03913ee03355))

- **deps**: Update dependency openai to >=2.30.0
  ([#591](https://github.com/n24q02m/wet-mcp/pull/591),
  [`f8b75fe`](https://github.com/n24q02m/wet-mcp/commit/f8b75fe81f3893745d28d793afc9cdd68c559602))

- **deps**: Update non-major dependencies ([#588](https://github.com/n24q02m/wet-mcp/pull/588),
  [`4815487`](https://github.com/n24q02m/wet-mcp/commit/481548713ea2a8dfe729136982af58014cc5e709))

### Chores

- **deps**: Lock file maintenance ([#593](https://github.com/n24q02m/wet-mcp/pull/593),
  [`c47866c`](https://github.com/n24q02m/wet-mcp/commit/c47866cfdb1442454c5bd3a184014fc7419be7e1))

- **deps**: Update codecov/codecov-action action to v6
  ([#592](https://github.com/n24q02m/wet-mcp/pull/592),
  [`dc92bc8`](https://github.com/n24q02m/wet-mcp/commit/dc92bc8663c73c718639a586d4e69fa1d57fa312))

### Features

- Relay-first startup — always show relay URL
  ([`27c9bb0`](https://github.com/n24q02m/wet-mcp/commit/27c9bb0b2c506146a6361da3996902dae43b4818))


## v2.17.0 (2026-03-26)

### Chores

- Add server.json to PSR version_variables, sync version
  ([`6b832a4`](https://github.com/n24q02m/wet-mcp/commit/6b832a40f391d305e0f248a0e938109af9ff5332))

- Clean up plugin manifest for best practices
  ([`695c2ef`](https://github.com/n24q02m/wet-mcp/commit/695c2efd29bd2372ebed2c06a8d1e73173a24b1d))

### Documentation

- Fix marketplace references, improve Gemini CLI extension config
  ([`238df6d`](https://github.com/n24q02m/wet-mcp/commit/238df6d47953cd1c47e35a9412e51f31e318bf79))

- Standardize README structure
  ([`6fe9c36`](https://github.com/n24q02m/wet-mcp/commit/6fe9c36734c5f2a1d20bd85ba1f9d0cdfcd07974))


## v2.17.0-beta.1 (2026-03-25)

### Bug Fixes

- Resolve ruff lint errors in relay setup files
  ([#587](https://github.com/n24q02m/wet-mcp/pull/587),
  [`8b16ee8`](https://github.com/n24q02m/wet-mcp/commit/8b16ee8c0af35cdb481dcd65e5e11f19f9183bfb))

- Resolve ty type check errors in relay setup ([#587](https://github.com/n24q02m/wet-mcp/pull/587),
  [`8b16ee8`](https://github.com/n24q02m/wet-mcp/commit/8b16ee8c0af35cdb481dcd65e5e11f19f9183bfb))

- Switch mcp-relay-core from git dep to published PyPI package
  ([#587](https://github.com/n24q02m/wet-mcp/pull/587),
  [`8b16ee8`](https://github.com/n24q02m/wet-mcp/commit/8b16ee8c0af35cdb481dcd65e5e11f19f9183bfb))

### Documentation

- Add relay files to CLAUDE.md file structure
  ([`d9ef8b9`](https://github.com/n24q02m/wet-mcp/commit/d9ef8b93ce51f78f0b98164aa06219463436aab4))

- Add zero-config relay setup section to README
  ([`01afdf7`](https://github.com/n24q02m/wet-mcp/commit/01afdf77293fd511f8d1ce296309f02f653456d0))

### Features

- Add zero-env-config relay setup via mcp-relay-core
  ([#587](https://github.com/n24q02m/wet-mcp/pull/587),
  [`8b16ee8`](https://github.com/n24q02m/wet-mcp/commit/8b16ee8c0af35cdb481dcd65e5e11f19f9183bfb))

- Zero-env-config relay setup via mcp-relay-core
  ([#587](https://github.com/n24q02m/wet-mcp/pull/587),
  [`8b16ee8`](https://github.com/n24q02m/wet-mcp/commit/8b16ee8c0af35cdb481dcd65e5e11f19f9183bfb))


## v2.16.0 (2026-03-25)

### Bug Fixes

- Add 'docs/' to .gitignore
  ([`a687df3`](https://github.com/n24q02m/wet-mcp/commit/a687df30ad51e414165303b5460de7dc2fa62405))

- Add .jules/ and JULES.md to gitignore
  ([`b9fa8eb`](https://github.com/n24q02m/wet-mcp/commit/b9fa8eb0492b6cac636d685584f8796184f090c0))

- Add CI status badge to README
  ([`f462c39`](https://github.com/n24q02m/wet-mcp/commit/f462c39f2d847d69feebc784a76c74ef4b34b532))

- Add difflib-based corrective errors for LLM call pass rate
  ([`c6951c6`](https://github.com/n24q02m/wet-mcp/commit/c6951c6ca97abd08e5208e90493fbc24d1777bb1))

- Add Docker LABEL and re-add OCI package for MCP Registry
  ([`c7ceac3`](https://github.com/n24q02m/wet-mcp/commit/c7ceac30d543298df79f1aa1c63cd9c8f4aa221c))

- Add expanduser() to download_dir path in analyze_media
  ([`827298b`](https://github.com/n24q02m/wet-mcp/commit/827298b5d17295896e68dcde04f535567734a7da))

- Add git installation in Dockerfile for SearXNG build system
  ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- Add gitleaks secret detection to pre-commit hooks
  ([`f01f8ad`](https://github.com/n24q02m/wet-mcp/commit/f01f8ad16a0a2b8180718452711a78732510ab89))

- Add health check to fast path and kill stuck SearXNG processes
  ([`e88833f`](https://github.com/n24q02m/wet-mcp/commit/e88833f617369237953e89a7bda284285240aa1d))

- Add lxml>=6.0 direct dependency for Python 3.14 compatibility
  ([`9660821`](https://github.com/n24q02m/wet-mcp/commit/9660821045524c0c52a347cf319111452fd7cc88))

- Add mcp-name to README for MCP Registry ownership validation
  ([`0d9ae02`](https://github.com/n24q02m/wet-mcp/commit/0d9ae02ea76dc2c5f35e826f022cd0b06e88d3ea))

- Add missing DocsDB.stats() method for config status action
  ([`3be120f`](https://github.com/n24q02m/wet-mcp/commit/3be120fe71083f1252b708aaa5b96bd134896e83))

- Add prerelease versioning strategy to beta config
  ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- Add Semgrep SAST scan to CI pipeline ([#528](https://github.com/n24q02m/wet-mcp/pull/528),
  [`502db68`](https://github.com/n24q02m/wet-mcp/commit/502db68e2fb7a6141f361525c72d7e0aedc32097))

- Add setup tool docs and README entry
  ([`ba3929e`](https://github.com/n24q02m/wet-mcp/commit/ba3929e82ec1e00c8b585395823c0a02cd21561b))

- Add sqlite-vec to local/gguf extras and update Docker tag in docs
  ([`764b059`](https://github.com/n24q02m/wet-mcp/commit/764b05944ace5d63ba35558b421dc8be576bd95a))

- Add sub-timeouts for docs search pipeline, expand benchmark to 300
  ([`59836c8`](https://github.com/n24q02m/wet-mcp/commit/59836c8aae616b05250ee9b95888ad3f67990c70))

- Add well-known docs for cross-ecosystem name collisions
  ([`65281c4`](https://github.com/n24q02m/wet-mcp/commit/65281c4e02b96f21d9dec64d4cdb60637f90d961))

- Align repo with skill audit findings
  ([`54484b7`](https://github.com/n24q02m/wet-mcp/commit/54484b7b9ed654a5a8173d46982cf84ad9728c7c))

- Apply ruff formatting to pass CI
  ([`8ef3897`](https://github.com/n24q02m/wet-mcp/commit/8ef3897a653ed5e8ea8689d775953b10fba7345b))

- Async SSRF hook for httpx 0.28+, improve docs discovery quality
  ([`6d894da`](https://github.com/n24q02m/wet-mcp/commit/6d894da83a56f68d05e56b6c1ab9f27644f1e7f3))

- Auto-sync plugin.json version via PSR
  ([`583449f`](https://github.com/n24q02m/wet-mcp/commit/583449f866178b1fe4aa402850846d50018b6071))

- Correct changelog descriptions for FTS5 search overhaul
  ([`5a3e755`](https://github.com/n24q02m/wet-mcp/commit/5a3e75504a9dd6eab72f3b4e6e6f93e05c0a4776))

- Correct cross-refs and use MCP JSON config format in docs
  ([`0d53b5f`](https://github.com/n24q02m/wet-mcp/commit/0d53b5f704e6bcffe044267d45fc504167b59fe0))

- Correct default embed model to gemini-embedding-001 for public repos
  ([`65566c6`](https://github.com/n24q02m/wet-mcp/commit/65566c63c9258217f97842525a7d767fdb90b508))

- Correct extract map max_pages default in docs and remove orphaned web.md
  ([`1822c92`](https://github.com/n24q02m/wet-mcp/commit/1822c925c5264c37b80a7b6343dd392efb06f843))

- Correct model identifiers to n24q02m/ namespace and bump qwen3-embed to v1.1.3
  ([`59e2d18`](https://github.com/n24q02m/wet-mcp/commit/59e2d180c08be2d21326571d573d66fdff3116e9))

- Correct MRL truncation, use query_embed, fix Docker Chromium
  ([`4a800bc`](https://github.com/n24q02m/wet-mcp/commit/4a800bc642a2af835637425ea535eee5cdee02e0))

- Correct plugin install commands per official docs
  ([`6fe70a5`](https://github.com/n24q02m/wet-mcp/commit/6fe70a572e826426b3514052eeac5804a78ea43c))

- Correct plugin packaging paths and marketplace schema
  ([`6433f5e`](https://github.com/n24q02m/wet-mcp/commit/6433f5e3196e673b2bd43f02ba16d0876f838a72))

- Correct Qodo PR Agent ignore_pr_authors config
  ([`83b81b3`](https://github.com/n24q02m/wet-mcp/commit/83b81b3387e6b5bfa0593eb82ab561b7f2fa7b32))

- Correct README action names and parameter references
  ([`e4e6758`](https://github.com/n24q02m/wet-mcp/commit/e4e6758e1d89bcb7e96d9f27bf8f7b69eda225f6))

- Correct test assertion for gemini-embedding-001 model
  ([`96d7ef9`](https://github.com/n24q02m/wet-mcp/commit/96d7ef9dfae1be29c3670238a9384cb3c6c9543e))

- Correct type annotation in test_stdio.py for ty check
  ([`2b0dbfa`](https://github.com/n24q02m/wet-mcp/commit/2b0dbfa0c1e456365e7386f31c736ccdad0d0a9b))

- Delete .jules directory
  ([`dcff6eb`](https://github.com/n24q02m/wet-mcp/commit/dcff6eb84cddc603baeea10141964de907e85754))

- Delete .vscode directory
  ([`99c529e`](https://github.com/n24q02m/wet-mcp/commit/99c529e974397921bbc32ca51196b114ef5c8850))

- Delete docs/superpowers directory
  ([`3543caa`](https://github.com/n24q02m/wet-mcp/commit/3543caa98071eea324ccd882b52437f26fef4b93))

- Detect zombie SearXNG process and cleanup stale discovery file
  ([`13a68c2`](https://github.com/n24q02m/wet-mcp/commit/13a68c2df4b671df86b09e8aaeafee0ae28e8940))

- Disable mise runtime updates in Renovate
  ([`600b4b9`](https://github.com/n24q02m/wet-mcp/commit/600b4b9baf211ad3383104ce487d3c99fee3f277))

- Disable Python version upgrades in Renovate
  ([`ab73a3e`](https://github.com/n24q02m/wet-mcp/commit/ab73a3e6ec8a17e5e3c4691935cc7d5863a5f3a8))

- Exclude Python 3.7 compat rule from Semgrep scan
  ([`26f284f`](https://github.com/n24q02m/wet-mcp/commit/26f284f76f8c6ebf7f6b15e6bd0d32211dcf416e))

- Fix N+1 query in vector search by leveraging JOIN
  ([#352](https://github.com/n24q02m/wet-mcp/pull/352),
  [`70155d0`](https://github.com/n24q02m/wet-mcp/commit/70155d0f85fc9d94d8a106f0ee1661aac32eba4b))

- Fix nosemgrep comment placement for importlib.resources
  ([`10334e3`](https://github.com/n24q02m/wet-mcp/commit/10334e3c5c1ecbeed70f745d722e13c66d8f7027))

- Format code with ruff ([#187](https://github.com/n24q02m/wet-mcp/pull/187),
  [`3900e01`](https://github.com/n24q02m/wet-mcp/commit/3900e01d8fdc81575c39c7f630f17849158ec1a0))

- Format crawler.py
  ([`0e210a4`](https://github.com/n24q02m/wet-mcp/commit/0e210a4dc618f50b1b0861de7619d252300bf37f))

- Format embedder.py and test_searxng_runner_comprehensive.py
  ([`42803e7`](https://github.com/n24q02m/wet-mcp/commit/42803e753b7bacdc32a15dddc1833a307ab3d128))

- Handle corrupted ONNX model cache in warmup (detect, clear, retry)
  ([`c4ff456`](https://github.com/n24q02m/wet-mcp/commit/c4ff456e607ea8cbaa77803df5d67777f9006af2))

- Handle dict response from LiteLLM proxy rerank
  ([`e087e5d`](https://github.com/n24q02m/wet-mcp/commit/e087e5d857ce1eb219d4fb01c837cf6992f65c02))

- Handle OCI package version in MCP Registry publish
  ([`5d4dfee`](https://github.com/n24q02m/wet-mcp/commit/5d4dfee018b5eef5c5fe668088b88e405c6655fe))

- Ignore unused import in tests to pass ruff
  ([`83e0703`](https://github.com/n24q02m/wet-mcp/commit/83e07037cb6b5f94016cb0fb2912fa01b0553c04))

- Improve docs discovery scoring, crawl scope, and cache validation
  ([`07cb238`](https://github.com/n24q02m/wet-mcp/commit/07cb2389eca7d46729293160592bafb9efe7b204))

- Improve SearXNG shared instance health check reliability
  ([`04c0c9f`](https://github.com/n24q02m/wet-mcp/commit/04c0c9fd6b526a0eca8960ec8d667e3f2c47fac3))

- Include all 5 tools in SessionStart hook message
  ([`96e3b92`](https://github.com/n24q02m/wet-mcp/commit/96e3b92e845623dda78d1265f9723c54fc480b3b))

- Increase SearXNG timeouts and fix browser pool stealth recycle
  ([`ed0cfaa`](https://github.com/n24q02m/wet-mcp/commit/ed0cfaa882e6670c4eba6a2e8f2f3d72a443378e))

- Keep OCI identifier as latest in MCP Registry publish
  ([`4df34c4`](https://github.com/n24q02m/wet-mcp/commit/4df34c4a12d116dff7f5a369be47db7e5d2e8e06))

- Move _EMBEDDING_CANDIDATES to config.py to avoid circular import
  ([`d0adc8d`](https://github.com/n24q02m/wet-mcp/commit/d0adc8de92375010fc2fb006a5a489648921b765))

- Move plugin files back to .claude-plugin/ directory
  ([`1a9b0d1`](https://github.com/n24q02m/wet-mcp/commit/1a9b0d1b9970a3d39cb6143362f8b5fd26174329))

- Optimize Docker build with BuildKit cache and non-root user
  ([`f316a5d`](https://github.com/n24q02m/wet-mcp/commit/f316a5d8306d5c1a91924bcf3384a67995aa8ad7))

- Pass encoding_format='float' in LiteLLM embedding requests
  ([`461246d`](https://github.com/n24q02m/wet-mcp/commit/461246dfc5837deadc218feef59f7e217cf4061f))

- Pin runtime versions with allowedVersions, revert Python to 3.13
  ([`1e6911e`](https://github.com/n24q02m/wet-mcp/commit/1e6911e053035c0fcc89aded5082f6ff13a49d81))

- Properly mock native SDK calls in embedder tests
  ([`ce3b3f3`](https://github.com/n24q02m/wet-mcp/commit/ce3b3f33baaa5627569cd6c2e55ab767749d2f9b))

- Refine discovery scoring with library-name-in-domain bonus
  ([`a1f352b`](https://github.com/n24q02m/wet-mcp/commit/a1f352b5855cefd38659e138f19c844096bebc0f))

- Remaining ruff errors
  ([`dc00055`](https://github.com/n24q02m/wet-mcp/commit/dc000559937559d29de8dcb32911c0f2e8085473))

- Remove .jules/bolt.md
  ([`d14bebb`](https://github.com/n24q02m/wet-mcp/commit/d14bebb3c56fe80c8fe53f5025501f8dd6101965))

- Remove another unused import in tests
  ([`4f09d41`](https://github.com/n24q02m/wet-mcp/commit/4f09d41e42390a28c9a242f5c35baf132a05368c))

- Remove commit-message-check job
  ([`26d5086`](https://github.com/n24q02m/wet-mcp/commit/26d508696cde579e70f9420272b9ebe8eb21cf93))

- Remove empty env vars from plugin configs to prevent empty-string bugs
  ([`4d40515`](https://github.com/n24q02m/wet-mcp/commit/4d405158f10a9ac0a5b26dcb59008c4550e2139d))

- Remove env from README MCP config examples
  ([`d6edf27`](https://github.com/n24q02m/wet-mcp/commit/d6edf2740e4e2f2285fe870b924ae97c3982c747))

- Remove env vars from plugin.json to prevent overwriting user config
  ([`fcb0b66`](https://github.com/n24q02m/wet-mcp/commit/fcb0b66e29149d7aa1b7580bf3d7a8e7b961861a))

- Remove hardcoded secrets from integration tests and pin pr-agent action
  ([`f5ee6d7`](https://github.com/n24q02m/wet-mcp/commit/f5ee6d7e88799a211eaacb212267bf7798a850da))

- Remove hardcoded secrets from integration tests and pin pr-agent action
  ([`e4a8c84`](https://github.com/n24q02m/wet-mcp/commit/e4a8c84319cd2e2e092ea47130c5b73205f8156d))

- Remove leftover temporary scripts
  ([`979a640`](https://github.com/n24q02m/wet-mcp/commit/979a6409827a76b1649f8610217b1aa001392adf))

- Remove mcp-name from README
  ([`4a1bee8`](https://github.com/n24q02m/wet-mcp/commit/4a1bee8aa09fe9808857278dda21cdcb97cf32d8))

- Remove OCI package from server.json until Docker LABEL annotation added
  ([`e1b7a70`](https://github.com/n24q02m/wet-mcp/commit/e1b7a7073b199d90567ac064db51f86290fe97e4))

- Remove pathlib unused import
  ([`347a563`](https://github.com/n24q02m/wet-mcp/commit/347a5632b13d07174c213df46ab3fb5471956384))

- Remove pr-title-check job from CI
  ([`b753da0`](https://github.com/n24q02m/wet-mcp/commit/b753da0b5abf947542eb6fd6567b19bce0287680))

- Remove unused asyncio import, update TODO backlog
  ([`99be77d`](https://github.com/n24q02m/wet-mcp/commit/99be77dfee99225d9690f4673535f996a46e6c4b))

- Remove unused nltk dependency ([#526](https://github.com/n24q02m/wet-mcp/pull/526),
  [`738e04b`](https://github.com/n24q02m/wet-mcp/commit/738e04be6c3d0a600ecf52616d35fa9ae43593fc))

- Replace broken repo-name cache validation with discovery version
  ([`43b9827`](https://github.com/n24q02m/wet-mcp/commit/43b9827ae00ed7be56a38e88c2f3f500cefe1367))

- Replace LiteLLM references with native SDK providers in docs
  ([`47cf14c`](https://github.com/n24q02m/wet-mcp/commit/47cf14c584d8946de4b1bc9ca91da3b6da5d63cc))

- Resolve MCP startup timeouts and stability issues
  ([`64bea1d`](https://github.com/n24q02m/wet-mcp/commit/64bea1d41c325dd3e948321057d82a7feda072cb))

- Resolve ruff C420 lint and f-string format issues in db.py
  ([`035b88a`](https://github.com/n24q02m/wet-mcp/commit/035b88a541b6bbd34159a7bfc79660063fa89e95))

- Resolve ruff lint errors in crawler and docs imports
  ([`4bcc31d`](https://github.com/n24q02m/wet-mcp/commit/4bcc31dfe2734541aea1ca769e1d484f607b8d94))

- Resolve ruff lint errors in full test file
  ([`da31a3f`](https://github.com/n24q02m/wet-mcp/commit/da31a3fff09c447f010a19695f0cf7a93295c014))

- Resolve ty type check errors in native SDK migration
  ([`eb9e4a4`](https://github.com/n24q02m/wet-mcp/commit/eb9e4a4aabd9aa3eaa4f2cb1d25ae147b61e3d56))

- Resolve ty type check errors in tests
  ([`f837986`](https://github.com/n24q02m/wet-mcp/commit/f837986f6f34fabadd87ea0ab7a602fd18315c79))

- Resolve type checking and formatting issues
  ([`92e43ec`](https://github.com/n24q02m/wet-mcp/commit/92e43ec1d2f2fb89c60305141094546673db2936))

- Revert direct lxml>=6.0 dep (conflicts with crawl4ai~=5.3)
  ([`d3015f5`](https://github.com/n24q02m/wet-mcp/commit/d3015f53f0660dfdea06e9fbca5d85f155f0c97a))

- Revert manual version bump, let semantic-release handle it
  ([`7bb5c56`](https://github.com/n24q02m/wet-mcp/commit/7bb5c56c9fae95ab6b918696baab433a6d36aa36))

- Revert Python requirement from 3.14 to 3.13
  ([`d32da45`](https://github.com/n24q02m/wet-mcp/commit/d32da45ad7f67933b12ebf721d33a70dfdc9499e))

- Ruff format
  ([`4bcbb2f`](https://github.com/n24q02m/wet-mcp/commit/4bcbb2f696a339ae7df0bbc7e3953332683de1ea))

- Ruff linting errors
  ([`2d624f2`](https://github.com/n24q02m/wet-mcp/commit/2d624f2eea2a7fd5bfc6b12a635e5b5f3879c438))

- Ruff undefined name crawler error
  ([`85d3d62`](https://github.com/n24q02m/wet-mcp/commit/85d3d62382ef1d9af6028aabe11c7ccb040986c4))

- Run initial sync immediately, document GITHUB_TOKEN auto-detect
  ([`a3c20fe`](https://github.com/n24q02m/wet-mcp/commit/a3c20fece8eb35564ad2c7c109b22da41cb0d028))

- Run ruff format
  ([`0097ef4`](https://github.com/n24q02m/wet-mcp/commit/0097ef49d040aa325ffa41f3e01c5d994c5ef58a))

- SearXNG port contention, docs discovery priority, and llms.txt quality check
  ([`8e0d73e`](https://github.com/n24q02m/wet-mcp/commit/8e0d73ee23f9f7ba630f32cfc9c0465ca0fc66aa))

- Security hardening from code audit
  ([`e8caca1`](https://github.com/n24q02m/wet-mcp/commit/e8caca19e4ccdc031edaaa2e69d7d5727b5b595d))

- Shorten server.json description to comply with MCP Registry 100-char limit
  ([`7d5e536`](https://github.com/n24q02m/wet-mcp/commit/7d5e5368a81336bf8eb6c9583933fc46bcf24c17))

- Split PSR version_toml — move JSON files to version_variables
  ([`069c9e0`](https://github.com/n24q02m/wet-mcp/commit/069c9e0c794ce8aae169f8b38332172064689bdd))

- Standardize CI with PR title check, email notify, and templates
  ([`d6194e5`](https://github.com/n24q02m/wet-mcp/commit/d6194e5fb2142c3df1231c15276c0814f106b055))

- Standardize README structure with plugin-first Quick Start
  ([`48d4cdd`](https://github.com/n24q02m/wet-mcp/commit/48d4cdd972467c286e181c5b224e50103d16fe58))

- Standardize repo structure with enforce-commit hook
  ([`218307d`](https://github.com/n24q02m/wet-mcp/commit/218307d77bb205799163619869464fe2e2967433))

- Support Gemini and Cohere embedding providers
  ([`f8864af`](https://github.com/n24q02m/wet-mcp/commit/f8864af88954b6ab3bdc69c6b5fa0a80a90fc393))

- Suppress Semgrep false positives in db.py and searxng_runner.py
  ([#529](https://github.com/n24q02m/wet-mcp/pull/529),
  [`269708b`](https://github.com/n24q02m/wet-mcp/commit/269708ba325e65649cdd34b2c4c22d01fe41926e))

- Sync CI/CD configs and standardize templates
  ([`e8dfe9b`](https://github.com/n24q02m/wet-mcp/commit/e8dfe9b885b657f3709f905183de8c4d9afa8c58))

- Sync plugin.json and server.json to v2.14.2
  ([`0e7a71c`](https://github.com/n24q02m/wet-mcp/commit/0e7a71c71fc4796aafde615de38dd4ec296834c2))

- Sync plugin.json version and add skills/hooks references
  ([`e3d911f`](https://github.com/n24q02m/wet-mcp/commit/e3d911fcc8d6a0c058bb0a5099b1277b6447b676))

- Sync uv.lock with native provider SDK dependencies
  ([`96043e4`](https://github.com/n24q02m/wet-mcp/commit/96043e4fc5a0c6cdab975065642d09237e57c555))

- Testing improvement] Update patch_searxng_windows mock pattern
  ([#426](https://github.com/n24q02m/wet-mcp/pull/426),
  [`0358ebd`](https://github.com/n24q02m/wet-mcp/commit/0358ebdacfc453a49816179479cfbf6580706717))

- Trigger cd ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- Unify model IDs and remove litellm backward-compat aliases
  ([`fef4099`](https://github.com/n24q02m/wet-mcp/commit/fef40996394776d3e6c66d9e63e8eb83860e30b8))

- Unify Plugin install section with marketplace + individual options
  ([`df44b05`](https://github.com/n24q02m/wet-mcp/commit/df44b05406bac603e05a2d7b8328bc47239c491b))

- Update Codecov badge in README.md
  ([`c0ed733`](https://github.com/n24q02m/wet-mcp/commit/c0ed733526114e2d2de18a3d3f338ca25a778704))

- Update pip commands to use uv for SearXNG and Playwright installation
  ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- Update qwen3-embed version pin and refactor token extraction
  ([`bfcd422`](https://github.com/n24q02m/wet-mcp/commit/bfcd422c38a1db716398b27d00e56cfe4ae0285a))

- Update README badges with Codecov, tech stack, and engineering standards
  ([`ef41cf4`](https://github.com/n24q02m/wet-mcp/commit/ef41cf4f7291b83ef09d0a2b18be47aadd03d042))

- Update ruff pre-commit hook to v0.15.7 and reformat tests
  ([`473be2d`](https://github.com/n24q02m/wet-mcp/commit/473be2dc4652743c102f14867b281bcc6ab09f54))

- Update server.json version dynamically in MCP Registry publish job
  ([`9d7dd78`](https://github.com/n24q02m/wet-mcp/commit/9d7dd78b1df0b10db644062167f71dcd071d1de6))

- Use ctypes OpenProcess for PID liveness check on Windows
  ([`e4bc893`](https://github.com/n24q02m/wet-mcp/commit/e4bc893363b88589519f163e7b9eae46fb559705))

- Use dynamic version from package metadata instead of hardcoded string
  ([`db84775`](https://github.com/n24q02m/wet-mcp/commit/db84775740e4fded73a3be3efb6b85f1f53e1897))

- Use dynamic version from package metadata instead of hardcoded string
  ([`a911c1b`](https://github.com/n24q02m/wet-mcp/commit/a911c1baedcb0653eed491338830f0d27a4aec62))

- ⚡ Bolt: [performance improvement] fix N+1 query in vector search by leveraging JOIN
  ([#352](https://github.com/n24q02m/wet-mcp/pull/352),
  [`70155d0`](https://github.com/n24q02m/wet-mcp/commit/70155d0f85fc9d94d8a106f0ee1661aac32eba4b))

- **cd**: Add git config identity for sync-dev step
  ([`9cb13c1`](https://github.com/n24q02m/wet-mcp/commit/9cb13c1081a191c8c8e5f5fd4f51980e46b7628d))

- **cd**: Add packages:write for GHCR and switch PyPI to uv publish
  ([`54b16e5`](https://github.com/n24q02m/wet-mcp/commit/54b16e5702af0ecee378cbdf3dfa2f8c3cadad20))

- **cd**: Auto-resolve merge conflicts in promote workflow
  ([`4ea92f5`](https://github.com/n24q02m/wet-mcp/commit/4ea92f59609371107f9496ce1364089f685afd19))

- **cd**: Auto-resolve merge conflicts in promote workflow
  ([`c54ac17`](https://github.com/n24q02m/wet-mcp/commit/c54ac177852368d381d99a2accad5449d681f245))

- **cd**: Checkout main branch for PR merge release
  ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- **cd**: Make scripts executable and clean working tree before promote merge
  ([`ddac2e7`](https://github.com/n24q02m/wet-mcp/commit/ddac2e74a2be964f85bf65fe7636d19b829d62b5))

- **cd**: Use dry-run check to prevent workflow failure when no release needed
  ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- **chore**: Trigger cicd ([#76](https://github.com/n24q02m/wet-mcp/pull/76),
  [`683df7a`](https://github.com/n24q02m/wet-mcp/commit/683df7a5889aeae1544f8de251eb3a207841a1c8))

- **ci**: Fix Qodo PR review for external contributors
  ([`c3ec0d6`](https://github.com/n24q02m/wet-mcp/commit/c3ec0d63c03ad9aba2cdd78abce170d8c5f6c3c2))

- **ci**: Fix syntax errors and correctly configure Qodo + Gemini 3 Flash
  ([`0fb2d77`](https://github.com/n24q02m/wet-mcp/commit/0fb2d77c697886d8786ae6c3fba79eb292357a4f))

- **ci**: Integrate qodo merge with gemini 3 flash
  ([`423f7b5`](https://github.com/n24q02m/wet-mcp/commit/423f7b5b91c865abd2241ad9e0d7f96be2b4630e))

- **ci**: Pin PSR v10, Python 3.13, Node 24, Java 21 in Renovate
  ([`7fa6571`](https://github.com/n24q02m/wet-mcp/commit/7fa65715a6e83a518747f99eb12acb6e27373505))

- **ci**: Remove invalid strict field from ty config
  ([`d1e29d4`](https://github.com/n24q02m/wet-mcp/commit/d1e29d4a30ce2fe1588816708adce2c2813fba94))

- **ci**: Remove job-level continue-on-error from dependency-review
  ([`83bc65e`](https://github.com/n24q02m/wet-mcp/commit/83bc65eae95b84101146e7fbd645e3484b52ed7b))

- **ci**: Use pull_request_target for jobs requiring secrets
  ([`3d18dfc`](https://github.com/n24q02m/wet-mcp/commit/3d18dfcc911fd79ad506701c1855406f04f4abdb))

- **crawler**: Correct type hint suppression typo
  ([#176](https://github.com/n24q02m/wet-mcp/pull/176),
  [`d544143`](https://github.com/n24q02m/wet-mcp/commit/d544143e43baa7320d96ab6addd450b4806b455c))

- **deps**: Override lxml>=6.0 for Python 3.14 wheel support
  ([`6d9f73c`](https://github.com/n24q02m/wet-mcp/commit/6d9f73c22134ae2a5bd7708bcbc75331847ccdd7))

- **deps**: Update dependency cryptography to >=46.0.5
  ([#331](https://github.com/n24q02m/wet-mcp/pull/331),
  [`6f9e69d`](https://github.com/n24q02m/wet-mcp/commit/6f9e69d6e832cac5586bc93263dc8b59fca2f948))

- **deps**: Update dependency qwen3-embed to >=1.4.3
  ([#342](https://github.com/n24q02m/wet-mcp/pull/342),
  [`260d3d8`](https://github.com/n24q02m/wet-mcp/commit/260d3d817b9391f5243b181f0a9adafbde9c414a))

- **deps**: Update non-major dependencies ([#532](https://github.com/n24q02m/wet-mcp/pull/532),
  [`e499680`](https://github.com/n24q02m/wet-mcp/commit/e499680eee439b0ac5dade598ba3803bba90c7a0))

- **deps**: Update non-major dependencies ([#464](https://github.com/n24q02m/wet-mcp/pull/464),
  [`0f35c03`](https://github.com/n24q02m/wet-mcp/commit/0f35c0343f8e3b33eab3e1d7bbdac38dab530ae7))

- **deps**: Update non-major dependencies ([#328](https://github.com/n24q02m/wet-mcp/pull/328),
  [`d4fa0f6`](https://github.com/n24q02m/wet-mcp/commit/d4fa0f6a61c56d2826cf3a1fdd8de1e5164b0ab8))

- **deps**: Upgrade pillow to 12.1.1 and cryptography to 46.0.5 for security patches
  ([#166](https://github.com/n24q02m/wet-mcp/pull/166),
  [`3f52d2b`](https://github.com/n24q02m/wet-mcp/commit/3f52d2b4b02ffd6a48828fe8558029b58444cbe3))

- **docs**: V17 filter login URLs, registry listing pages, docs subdomain exclusions
  ([`190b770`](https://github.com/n24q02m/wet-mcp/commit/190b7705dc46d0ec996abadf452672fb2feefb4c))

- **refactor+tests**: Extract helpers from large functions, reuse HTTP clients, add 25 tests
  ([`dce4fed`](https://github.com/n24q02m/wet-mcp/commit/dce4fed052cfdb67ec5570af7969c827cdc3c0ca))

- **release**: Add prerelease false to stable config
  ([#51](https://github.com/n24q02m/wet-mcp/pull/51),
  [`c5bc612`](https://github.com/n24q02m/wet-mcp/commit/c5bc6128cb05bd18747745d82566d773692cc21d))

- **release**: Reset manifest to stable version for proper stable release
  ([`5a19617`](https://github.com/n24q02m/wet-mcp/commit/5a1961746b7e3dbb78fde03ab1689f49147691b3))

- **security**: DNS rebinding protection via pinned getaddrinfo cache
  ([`50fcce8`](https://github.com/n24q02m/wet-mcp/commit/50fcce80d79f40eab3d7b9d62d1db0fc88f1f025))

- **security**: Harden SSRF protection across crawl, extract, and DNS validation
  ([`fed4a75`](https://github.com/n24q02m/wet-mcp/commit/fed4a7568436142afae76d5bff901797cdd6ba0b))

- **security**: Resolve CodeQL alerts and ty check errors
  ([`f604e30`](https://github.com/n24q02m/wet-mcp/commit/f604e303b4b64de26c5d4d90eebaf231de2b4ff2))

- **security+perf**: Harden server against SSRF, path traversal, resource exhaustion and optimize DB
  queries
  ([`50fcce8`](https://github.com/n24q02m/wet-mcp/commit/50fcce80d79f40eab3d7b9d62d1db0fc88f1f025))

- **security+perf**: SSRF protection in docs discovery, path traversal guard in media analyze, batch
  DB queries, remove dead code
  ([`6ae6935`](https://github.com/n24q02m/wet-mcp/commit/6ae6935a40a1049cf3c216bca2fc659875926c0d))

- **test**: Isolate test_server_timeout to prevent side effects
  ([#197](https://github.com/n24q02m/wet-mcp/pull/197),
  [`4d6cda9`](https://github.com/n24q02m/wet-mcp/commit/4d6cda90cae326a48b3d67a764faf8a67d282fbb))

- **test**: Mock _get_crawler directly on unsafe url tests
  ([`92cdff4`](https://github.com/n24q02m/wet-mcp/commit/92cdff485dddcbe96445f49209e6a4b1166d3875))

- **test**: Mock _is_searxng_installed to avoid slow subprocess install timeout during tests
  ([`b7b6506`](https://github.com/n24q02m/wet-mcp/commit/b7b6506a536558217596078047d4d421e5d254f2))

- **test**: Mock playwright to avoid BrowserType.launch error in CI
  ([`993211b`](https://github.com/n24q02m/wet-mcp/commit/993211bf65cf16caf58072906392aeef6907aeb3))

- **test**: Resolve ruff format errors in test_server_timeout.py
  ([#197](https://github.com/n24q02m/wet-mcp/pull/197),
  [`4d6cda9`](https://github.com/n24q02m/wet-mcp/commit/4d6cda90cae326a48b3d67a764faf8a67d282fbb))

- **test**: Resolve ruff linting errors in test_server_timeout.py
  ([#197](https://github.com/n24q02m/wet-mcp/pull/197),
  [`4d6cda9`](https://github.com/n24q02m/wet-mcp/commit/4d6cda90cae326a48b3d67a764faf8a67d282fbb))

- **tests**: Apply strict ruff formatting to test_crawler_download.py
  ([#194](https://github.com/n24q02m/wet-mcp/pull/194),
  [`41d7d41`](https://github.com/n24q02m/wet-mcp/commit/41d7d41bb27c45fc1c94e41a59ed3a7b455976f1))

- **tests**: Format test_api_keys_security.py imports and whitespace
  ([#180](https://github.com/n24q02m/wet-mcp/pull/180),
  [`822b289`](https://github.com/n24q02m/wet-mcp/commit/822b2899a3d1911aa8baae5409050531adc660b0))

- **tests**: Replace URL membership checks with set equality for CodeQL
  ([#76](https://github.com/n24q02m/wet-mcp/pull/76),
  [`683df7a`](https://github.com/n24q02m/wet-mcp/commit/683df7a5889aeae1544f8de251eb3a207841a1c8))

- **tests**: Replace URL membership checks with set equality for CodeQL
  ([#68](https://github.com/n24q02m/wet-mcp/pull/68),
  [`d725213`](https://github.com/n24q02m/wet-mcp/commit/d7252136dc8663979ed2a0c81ae8c72d3e846c8c))

- **tests**: Resolve AsyncClient mocking issue in test_crawler_download.py
  ([#194](https://github.com/n24q02m/wet-mcp/pull/194),
  [`41d7d41`](https://github.com/n24q02m/wet-mcp/commit/41d7d41bb27c45fc1c94e41a59ed3a7b455976f1))

- **tests**: Resolve ruff linting errors in test_crawler_download.py
  ([#194](https://github.com/n24q02m/wet-mcp/pull/194),
  [`41d7d41`](https://github.com/n24q02m/wet-mcp/commit/41d7d41bb27c45fc1c94e41a59ed3a7b455976f1))

- **tests**: Run ruff format on test_api_keys_security.py
  ([#180](https://github.com/n24q02m/wet-mcp/pull/180),
  [`822b289`](https://github.com/n24q02m/wet-mcp/commit/822b2899a3d1911aa8baae5409050531adc660b0))

- **tests**: Update tests to use SecretStr for api_keys
  ([#180](https://github.com/n24q02m/wet-mcp/pull/180),
  [`822b289`](https://github.com/n24q02m/wet-mcp/commit/822b2899a3d1911aa8baae5409050531adc660b0))

- **tests**: Update version test to validate semantic versioning format
  ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

### Build System

- Set project Python version to 3.13 and update `wet-mcp` package in `uv.lock`.
  ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

### Chores

- Add .code-review-graph/ to .gitignore
  ([`1988c1c`](https://github.com/n24q02m/wet-mcp/commit/1988c1cae8a37333d38fd7d2792a472a13e2b50f))

- Add Gemini Code Assist style guide
  ([`7b68fd0`](https://github.com/n24q02m/wet-mcp/commit/7b68fd05ad857303a75fb0a456002724ba82075c))

- Add glama.json for Glama directory listing
  ([`323fa47`](https://github.com/n24q02m/wet-mcp/commit/323fa4791f3a0f4b3785021a7aab0915b60bc698))

- Add jsonschema dependency for structured extraction
  ([`1dfa1e0`](https://github.com/n24q02m/wet-mcp/commit/1dfa1e0a6fbf563c901857ad28132418d3c2df5b))

- Align CI/CD action versions
  ([`67390f1`](https://github.com/n24q02m/wet-mcp/commit/67390f161b19b4140852ab1a2175201699c879fd))

- Change Renovate schedule to daily 5am
  ([`364da48`](https://github.com/n24q02m/wet-mcp/commit/364da48f6f828ce342ba2b6050c66e4a59bd65fb))

- Disable dependency dashboard to keep issues clean
  ([`55ea63b`](https://github.com/n24q02m/wet-mcp/commit/55ea63b32c269476681600c8c26e3a47f07ce61f))

- Fix manifest and version to last stable (2.1.3)
  ([`e41621d`](https://github.com/n24q02m/wet-mcp/commit/e41621d33a4356ee75b236a1cdbb6b9df59af8d0))

- Fix ruff formatting
  ([`8297036`](https://github.com/n24q02m/wet-mcp/commit/82970362ea90c729d683dc3d3b0a755a271769b2))

- Fix type hint suppression typo in crawler.py ([#171](https://github.com/n24q02m/wet-mcp/pull/171),
  [`2e854c3`](https://github.com/n24q02m/wet-mcp/commit/2e854c3fa89375717e0ed55ea5855b99c4b975b7))

- Ignore PLR0913 for search tool to preserve MCP API schema
  ([#454](https://github.com/n24q02m/wet-mcp/pull/454),
  [`4ad2a0b`](https://github.com/n24q02m/wet-mcp/commit/4ad2a0b2ff38d5c614192e80fcadf06be36afc90))

- Implement dual manifest strategy for release pipeline
  ([#76](https://github.com/n24q02m/wet-mcp/pull/76),
  [`683df7a`](https://github.com/n24q02m/wet-mcp/commit/683df7a5889aeae1544f8de251eb3a207841a1c8))

- Implement dual manifest strategy for release pipeline
  ([`3d4ac86`](https://github.com/n24q02m/wet-mcp/commit/3d4ac860630da1ee2739dd2803bb6387b6ee63ff))

- Migrate to 2025-2026 tech stack (uv/ty)
  ([`04222d6`](https://github.com/n24q02m/wet-mcp/commit/04222d6760d22525b3841ee0daf1ef8a7aedccfc))

- Remove .jules directory (bot artifact)
  ([`6bd71a8`](https://github.com/n24q02m/wet-mcp/commit/6bd71a859919a233ce0328eb69fc1da24a14d7d0))

- Remove auto-generated .jules/bolt.md
  ([`45f5079`](https://github.com/n24q02m/wet-mcp/commit/45f50792afdf29208b98425bfd7f27042acf933c))

- Remove CodeRabbit config, migrating to Gemini Code Assist
  ([`dce5217`](https://github.com/n24q02m/wet-mcp/commit/dce5217c7b75d90701011a6867c6c65595ca6a64))

- Remove debug script
  ([`0fd7b74`](https://github.com/n24q02m/wet-mcp/commit/0fd7b74c31676207348f4231f80650a760f7c8dc))

- Remove dependabot.yml in favor of Renovate
  ([`a3f71c5`](https://github.com/n24q02m/wet-mcp/commit/a3f71c5f0db05052fe514857f48e59549d1dcc5e))

- Remove unstable hacky setup tests
  ([`d4300bf`](https://github.com/n24q02m/wet-mcp/commit/d4300bfce952b113028d81fb8dbdb717720d6dec))

- Standardize repo files across MCP server portfolio
  ([`2d614fa`](https://github.com/n24q02m/wet-mcp/commit/2d614fad64ef3157531a5d833ea14f14b46aa533))

- Sync beta manifest from stable [skip ci]
  ([`4e10a4c`](https://github.com/n24q02m/wet-mcp/commit/4e10a4c1fa535d24c5a961538f5afd9cd73ea349))

- Trigger release-please
  ([`b792204`](https://github.com/n24q02m/wet-mcp/commit/b792204be2e260ff3f6dea7cdd15ff52be5d054f))

- Trigger release-please on main
  ([`3207386`](https://github.com/n24q02m/wet-mcp/commit/3207386ce8bacf8d39ed730e24fb8f35dcd0fe93))

- Update uv.lock for markitdown[xlsx] dependency
  ([`5567d9a`](https://github.com/n24q02m/wet-mcp/commit/5567d9a34f5b8626633c37f83a803a7ed0ebdae9))

- **config**: Migrate config renovate.json ([#232](https://github.com/n24q02m/wet-mcp/pull/232),
  [`570eeb3`](https://github.com/n24q02m/wet-mcp/commit/570eeb3ae8e877ffdbba61a55b65396a687ef017))

- **crawler**: Fix `ty: ignore` typo in type suppression comments
  ([#174](https://github.com/n24q02m/wet-mcp/pull/174),
  [`bb9fad9`](https://github.com/n24q02m/wet-mcp/commit/bb9fad9f77b65d9ac17ccf72dbf5f918c14e92cc))

- **crawler**: Fix type suppression typo ty: ignore -> type: ignore
  ([#168](https://github.com/n24q02m/wet-mcp/pull/168),
  [`c4221a6`](https://github.com/n24q02m/wet-mcp/commit/c4221a6a11a8e8b114557d46049a40fdeb819963))

- **deps**: Bump pyopenssl in the uv group across 1 directory
  ([#461](https://github.com/n24q02m/wet-mcp/pull/461),
  [`83d85be`](https://github.com/n24q02m/wet-mcp/commit/83d85beef9ad9f98b26d27ef4c9de4a6cdd861e9))

- **deps**: Fix vulnerabilities in nltk, pillow, diskcache, cryptography
  ([`cc95fa7`](https://github.com/n24q02m/wet-mcp/commit/cc95fa7a29fbe7da31e5a57c180699931852dc3e))

- **deps**: Lock file maintenance ([#533](https://github.com/n24q02m/wet-mcp/pull/533),
  [`f8f3e23`](https://github.com/n24q02m/wet-mcp/commit/f8f3e230ba78909d653c87c17bb095564a43ced9))

- **deps**: Lock file maintenance ([#465](https://github.com/n24q02m/wet-mcp/pull/465),
  [`02230ba`](https://github.com/n24q02m/wet-mcp/commit/02230ba8bbb26c0a3f267505a4888d2f63055fc4))

- **deps**: Lock file maintenance ([#382](https://github.com/n24q02m/wet-mcp/pull/382),
  [`5c267e9`](https://github.com/n24q02m/wet-mcp/commit/5c267e998baef9c389b18f579d0eae5d3a6b3350))

- **deps**: Lock file maintenance ([#343](https://github.com/n24q02m/wet-mcp/pull/343),
  [`766efa8`](https://github.com/n24q02m/wet-mcp/commit/766efa8831f9638422b0901cba23087b0b02f8d8))

- **deps**: Pin dependencies ([#346](https://github.com/n24q02m/wet-mcp/pull/346),
  [`ca9f82b`](https://github.com/n24q02m/wet-mcp/commit/ca9f82b07cc0c7df8e7dc87011144c81ebbd96aa))

- **deps**: Pin dependencies ([#327](https://github.com/n24q02m/wet-mcp/pull/327),
  [`d1394a7`](https://github.com/n24q02m/wet-mcp/commit/d1394a736e77e03a82cd74eb4d5089b01bb5b9ec))

- **deps**: Update actions/dependency-review-action digest to 3c4e3dc
  ([#351](https://github.com/n24q02m/wet-mcp/pull/351),
  [`44b641d`](https://github.com/n24q02m/wet-mcp/commit/44b641d1592143d0701eeb4f339f3c5ee15aa92e))

- **deps**: Update actions/download-artifact digest to 3e5f45b
  ([#379](https://github.com/n24q02m/wet-mcp/pull/379),
  [`762e4a5`](https://github.com/n24q02m/wet-mcp/commit/762e4a59adcd26ff67935597dc4bd3859ebbe1e5))

- **deps**: Update astral-sh/setup-uv digest to 37802ad
  ([#380](https://github.com/n24q02m/wet-mcp/pull/380),
  [`99f53dd`](https://github.com/n24q02m/wet-mcp/commit/99f53dd48c2120fc29ca621af086badcdc9acf31))

- **deps**: Update codecov/codecov-action digest to 1af5884
  ([#467](https://github.com/n24q02m/wet-mcp/pull/467),
  [`ee62f15`](https://github.com/n24q02m/wet-mcp/commit/ee62f15e77fb06817a17f3ac1b300dd6822f681f))

- **deps**: Update dawidd6/action-send-mail action to v11
  ([#348](https://github.com/n24q02m/wet-mcp/pull/348),
  [`d49d100`](https://github.com/n24q02m/wet-mcp/commit/d49d10040760d62f00291fe3dc3790c87c0bd331))

- **deps**: Update dawidd6/action-send-mail action to v15
  ([#386](https://github.com/n24q02m/wet-mcp/pull/386),
  [`8fa186d`](https://github.com/n24q02m/wet-mcp/commit/8fa186dc2237db6b19fcc8ad06684b2b741ded4d))

- **deps**: Update dawidd6/action-send-mail action to v16
  ([#466](https://github.com/n24q02m/wet-mcp/pull/466),
  [`d33fb08`](https://github.com/n24q02m/wet-mcp/commit/d33fb080fc7a77f18e0d2e081d743635c6334656))

- **deps**: Update docker/build-push-action action to v7
  ([#337](https://github.com/n24q02m/wet-mcp/pull/337),
  [`b00f1fd`](https://github.com/n24q02m/wet-mcp/commit/b00f1fd040ea466a09a213114530812656ebdefe))

- **deps**: Update docker/login-action to v4
  ([`12e3f36`](https://github.com/n24q02m/wet-mcp/commit/12e3f3682634c91a7ce24f4933fdf04709145b05))

- **deps**: Update docker/setup-buildx-action action to v4
  ([#332](https://github.com/n24q02m/wet-mcp/pull/332),
  [`aef7acc`](https://github.com/n24q02m/wet-mcp/commit/aef7acc5e7f2f27ec0a9bbfde04cbd066675a61a))

- **deps**: Update github artifact actions ([#333](https://github.com/n24q02m/wet-mcp/pull/333),
  [`c5bc5a5`](https://github.com/n24q02m/wet-mcp/commit/c5bc5a54ad904d44b009ce7f2f29a69667e56240))

- **deps**: Update step-security/harden-runner digest to 58077d3
  ([#335](https://github.com/n24q02m/wet-mcp/pull/335),
  [`d8bc883`](https://github.com/n24q02m/wet-mcp/commit/d8bc883e74e4f81d15641941503e07ff80ec2402))

- **dev**: Release 2.3.0-beta ([#51](https://github.com/n24q02m/wet-mcp/pull/51),
  [`c5bc612`](https://github.com/n24q02m/wet-mcp/commit/c5bc6128cb05bd18747745d82566d773692cc21d))

- **dev**: Release 2.3.0-beta ([#48](https://github.com/n24q02m/wet-mcp/pull/48),
  [`44a45ac`](https://github.com/n24q02m/wet-mcp/commit/44a45acf4f4e534facde1b3c64858edf477294fe))

- **dev**: Release 2.4.0-beta ([#76](https://github.com/n24q02m/wet-mcp/pull/76),
  [`683df7a`](https://github.com/n24q02m/wet-mcp/commit/683df7a5889aeae1544f8de251eb3a207841a1c8))

- **dev**: Release 2.4.0-beta ([#68](https://github.com/n24q02m/wet-mcp/pull/68),
  [`d725213`](https://github.com/n24q02m/wet-mcp/commit/d7252136dc8663979ed2a0c81ae8c72d3e846c8c))

- **dev**: Release 2.4.0-beta.1 ([#76](https://github.com/n24q02m/wet-mcp/pull/76),
  [`683df7a`](https://github.com/n24q02m/wet-mcp/commit/683df7a5889aeae1544f8de251eb3a207841a1c8))

- **dev**: Release 2.4.0-beta.1 ([#68](https://github.com/n24q02m/wet-mcp/pull/68),
  [`d725213`](https://github.com/n24q02m/wet-mcp/commit/d7252136dc8663979ed2a0c81ae8c72d3e846c8c))

- **dev**: Release 2.4.0-beta.2 ([#76](https://github.com/n24q02m/wet-mcp/pull/76),
  [`683df7a`](https://github.com/n24q02m/wet-mcp/commit/683df7a5889aeae1544f8de251eb3a207841a1c8))

- **dev**: Release 2.4.0-beta.2 ([#68](https://github.com/n24q02m/wet-mcp/pull/68),
  [`d725213`](https://github.com/n24q02m/wet-mcp/commit/d7252136dc8663979ed2a0c81ae8c72d3e846c8c))

- **dev**: Release 2.4.0-beta.3 ([#76](https://github.com/n24q02m/wet-mcp/pull/76),
  [`683df7a`](https://github.com/n24q02m/wet-mcp/commit/683df7a5889aeae1544f8de251eb3a207841a1c8))

- **dev**: Release 2.4.0-beta.3 ([#68](https://github.com/n24q02m/wet-mcp/pull/68),
  [`d725213`](https://github.com/n24q02m/wet-mcp/commit/d7252136dc8663979ed2a0c81ae8c72d3e846c8c))

- **dev**: Release 2.4.0-beta.4 ([#76](https://github.com/n24q02m/wet-mcp/pull/76),
  [`683df7a`](https://github.com/n24q02m/wet-mcp/commit/683df7a5889aeae1544f8de251eb3a207841a1c8))

- **dev**: Release 2.5.0-beta ([#85](https://github.com/n24q02m/wet-mcp/pull/85),
  [`fe87474`](https://github.com/n24q02m/wet-mcp/commit/fe87474933c2a8c24e6aee68a18d622152a56382))

- **dev**: Release 2.5.0-beta.1 ([#86](https://github.com/n24q02m/wet-mcp/pull/86),
  [`bd09c9a`](https://github.com/n24q02m/wet-mcp/commit/bd09c9ab141dcdc89735d71425076609555199f0))

- **dev**: Release 2.5.0-beta.2 ([#102](https://github.com/n24q02m/wet-mcp/pull/102),
  [`d7b628f`](https://github.com/n24q02m/wet-mcp/commit/d7b628fa5c832d937418b736af717570e35a19d1))

- **dev**: Release 2.5.0-beta.3 ([#140](https://github.com/n24q02m/wet-mcp/pull/140),
  [`a1119ae`](https://github.com/n24q02m/wet-mcp/commit/a1119ae16e19df963119038b9df8a1db39ae3afd))

- **dev**: Release 2.5.0-beta.4 ([#141](https://github.com/n24q02m/wet-mcp/pull/141),
  [`32ae9a2`](https://github.com/n24q02m/wet-mcp/commit/32ae9a28f6b8c68d11bebef0303cf5d7675d40de))

- **dev**: Release 2.5.0-beta.5 ([#142](https://github.com/n24q02m/wet-mcp/pull/142),
  [`6988608`](https://github.com/n24q02m/wet-mcp/commit/69886080a37b6d18a2516caf30839877fe3b5b63))

- **dev**: Release 2.5.0-beta.6 ([#146](https://github.com/n24q02m/wet-mcp/pull/146),
  [`8633cf2`](https://github.com/n24q02m/wet-mcp/commit/8633cf2d35afe21f879af457d151bbff20963bb4))

- **dev**: Release 2.5.0-beta.7 ([#147](https://github.com/n24q02m/wet-mcp/pull/147),
  [`219455d`](https://github.com/n24q02m/wet-mcp/commit/219455ded3959103a5ffc1fb04301a02f216be5e))

- **dev**: Release 2.5.0-beta.8 ([#148](https://github.com/n24q02m/wet-mcp/pull/148),
  [`08df4f2`](https://github.com/n24q02m/wet-mcp/commit/08df4f2a41c657d6138e6875ac23134d7fb5baf7))

- **dev**: Release 3.0.0 ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- **dev**: Release 3.0.1-beta ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- **dev**: Release 3.1.0-beta ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- **dev**: Release 3.1.0-beta.1 ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- **dev**: Release 3.1.0-beta.2 ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- **dev**: Release 3.1.0-beta.3 ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- **dev**: Release 3.1.0-beta.4 ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- **main**: Release 2.2.0 ([#19](https://github.com/n24q02m/wet-mcp/pull/19),
  [`9a2b1fd`](https://github.com/n24q02m/wet-mcp/commit/9a2b1fd5b2a406731d7661bbe8a85780ea0db0b5))

- **main**: Release 2.3.0 ([#54](https://github.com/n24q02m/wet-mcp/pull/54),
  [`6614e62`](https://github.com/n24q02m/wet-mcp/commit/6614e62da6b075afd6f745bb569d103d2180730c))

- **main**: Release 2.4.0 ([#77](https://github.com/n24q02m/wet-mcp/pull/77),
  [`3f88dd9`](https://github.com/n24q02m/wet-mcp/commit/3f88dd9256c9df2d31f453cadc3825be873f5b0f))

- **main**: Release 2.4.1 ([#79](https://github.com/n24q02m/wet-mcp/pull/79),
  [`f1c83c0`](https://github.com/n24q02m/wet-mcp/commit/f1c83c02b9c094953a4f7ee5dd0ddd20779cf8e1))

- **release**: 2.1.4-beta.1 [skip ci] ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- **release**: 2.1.4-beta.2 [skip ci] ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- **release**: 2.1.4-beta.3 [skip ci] ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- **release**: 2.1.4-beta.4 [skip ci] ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- **workspace**: Update project paths in VSCode workspace configuration
  ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

### Code Style

- Auto-format server.py
  ([`5f973c5`](https://github.com/n24q02m/wet-mcp/commit/5f973c564a5b9decbb1f293076b5bb3e548d5d62))

- Fix ruff format failure in test_crawler_media.py
  ([#177](https://github.com/n24q02m/wet-mcp/pull/177),
  [`31df357`](https://github.com/n24q02m/wet-mcp/commit/31df357b010b2ace0117d632a7a0159910850c16))

- Fix ruff format on docs.py
  ([`ba162f2`](https://github.com/n24q02m/wet-mcp/commit/ba162f258e9b37d71f8e30eeabc832222c860178))

- Format docs.py for ruff compliance
  ([`4eba1bf`](https://github.com/n24q02m/wet-mcp/commit/4eba1bfe875a9d75b4fedaef8ea2ef097414d475))

- Format test_real_comprehensive.py for ruff compliance
  ([`c635304`](https://github.com/n24q02m/wet-mcp/commit/c635304f1c4d5a4be86c029cd58b20cd706a94e2))

- Format test_server_coverage.py
  ([`57baa8c`](https://github.com/n24q02m/wet-mcp/commit/57baa8c3b0ea27b4fb5be8ea44be523c849548e3))

### Continuous Integration

- Disable CD for PSR migration [skip ci]
  ([`48964e2`](https://github.com/n24q02m/wet-mcp/commit/48964e26e7a385a14af2b17eaac56b7e8d5ae7dd))

- Fix formatting in searxng.py to pass CI checks
  ([#191](https://github.com/n24q02m/wet-mcp/pull/191),
  [`9234fa2`](https://github.com/n24q02m/wet-mcp/commit/9234fa21ac18cf4568a75db694c4c4d7973221af))

- Fix release-please prerelease config (use beta config file)
  ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- Improve PR checks and Qodo filtering ([#350](https://github.com/n24q02m/wet-mcp/pull/350),
  [`8015eb9`](https://github.com/n24q02m/wet-mcp/commit/8015eb973d94a2d0feb6be7152c2a2995eb84f19))

- Migrate from release-please to python-semantic-release v10
  ([`886b67d`](https://github.com/n24q02m/wet-mcp/commit/886b67de5025c6200e4d96f17c5b4a80a1c6277a))

- Remove dependency-review job (private repo) ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- Remove temporary repro_issue.py script to fix linting errors
  ([#191](https://github.com/n24q02m/wet-mcp/pull/191),
  [`9234fa2`](https://github.com/n24q02m/wet-mcp/commit/9234fa21ac18cf4568a75db694c4c4d7973221af))

- Skip Qodo AI review for bot-created PRs
  ([`55edd8d`](https://github.com/n24q02m/wet-mcp/commit/55edd8d18a3531c20c270aabe83a5e4500b940b8))

- **cd**: Fix release workflow token usage ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- **cd**: Improve release workflow ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- **cd**: Promote creates PR instead of direct merge
  ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- **cd**: Trigger release on PR merge ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- **cd**: Use feat: prefix for promote PR to trigger release
  ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

### Documentation

- Add AGENTS.md for AI coding agents
  ([`3008931`](https://github.com/n24q02m/wet-mcp/commit/300893160356e972ca8dfdf7c4fc39150def3502))

- Add CODEOWNERS and update README description
  ([`9b726cc`](https://github.com/n24q02m/wet-mcp/commit/9b726cc8b445dbac301c4818cd2586eb44551a29))

- Add CODEOWNERS and update README description
  ([`d64cdf0`](https://github.com/n24q02m/wet-mcp/commit/d64cdf0df06100f4c476950cbcb10432c40d218f))

- Add compatible-with badges and cross-links to sibling MCP servers
  ([`18bb889`](https://github.com/n24q02m/wet-mcp/commit/18bb8890fd8c58ce411d063d7b3db2d9036f7a79))

- Add config tool to help docs, gguf support, docker-compose
  ([`0b197f7`](https://github.com/n24q02m/wet-mcp/commit/0b197f7990fe888194f53890d3920949ff8ac211))

- Add config tool to tools table and architecture diagram
  ([`92d1e67`](https://github.com/n24q02m/wet-mcp/commit/92d1e67a983a9afed65d70300b3c5ba9342a8acf))

- Add MCP client keywords to pyproject.toml for PyPI discoverability
  ([`afd6443`](https://github.com/n24q02m/wet-mcp/commit/afd64432e459dfb0b5865412c80c5148b39472fa))

- Add Pre-Phase + Phase 1 implementation plan
  ([`29e78cc`](https://github.com/n24q02m/wet-mcp/commit/29e78ccfcd23c6490c65f97691c0d92c57c5bb2f))

- Add related projects cross-references
  ([`af4a818`](https://github.com/n24q02m/wet-mcp/commit/af4a818bda5db6b810806177f314ff5b687b29d1))

- Add server.json and MCP Registry publish step to CD workflow
  ([`73aa581`](https://github.com/n24q02m/wet-mcp/commit/73aa5817d62494f53d21ed44728406fc8e0bfb5e))

- Add TODO backlog — markitdown integration for PDF/DOCX extraction
  ([`0ac5777`](https://github.com/n24q02m/wet-mcp/commit/0ac5777fda349a8aaa8edde1ddd8e65d398f8891))

- Add v2.14-v2.16 design spec
  ([`8e0b0ea`](https://github.com/n24q02m/wet-mcp/commit/8e0b0ea2eaa7cf1d1774b13a34a9035f7375bb1b))

- Chuẩn hóa repo cho public opensource ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- Document 3-mode LLM and 2-mode SearXNG architecture
  ([`ff73f38`](https://github.com/n24q02m/wet-mcp/commit/ff73f38a7916293e97db4211dfdf5868a7875809))

- Fix 3 blockers + warnings in design spec
  ([`4122794`](https://github.com/n24q02m/wet-mcp/commit/4122794cc0f8b86444930e20391fd3bcb342a160))

- Fix Docker volume persistence and config documentation
  ([`13c2901`](https://github.com/n24q02m/wet-mcp/commit/13c2901224e3e3f5bca183dbdfddf0e503fcedf3))

- Move 3-mode env vars into Quick Start config blocks
  ([`26593c8`](https://github.com/n24q02m/wet-mcp/commit/26593c8b9bdb4a21649f9412451b66bcdfddf1d7))

- Restructure Quick Start with 4 config options
  ([`17d8623`](https://github.com/n24q02m/wet-mcp/commit/17d86230dcd0965280df29239e9130f36a61aca1))

- Revert Docker tag to :latest and add --name to Docker examples
  ([`82f3358`](https://github.com/n24q02m/wet-mcp/commit/82f33583627ecc057823f19d753345d8e714e64e))

- Simplify quick start to uvx and docker options with full config
  ([`274a6d0`](https://github.com/n24q02m/wet-mcp/commit/274a6d0b1d8c4d57fb67e6e7efafc92ae3d0957d))

- Standardize README sections and sync Also by table
  ([`7f09e90`](https://github.com/n24q02m/wet-mcp/commit/7f09e90cae0a9c3c4e419d6c7925e835477f2ae9))

- Update compatible-with badges - add Antigravity, Gemini CLI, Codex, OpenCode
  ([`2f8b228`](https://github.com/n24q02m/wet-mcp/commit/2f8b2284efb7daef0f0d6b0e124050081995daca))

- Update help docs for Phase 2 features and add plan
  ([`71715eb`](https://github.com/n24q02m/wet-mcp/commit/71715eb7361eaa7c56b3d5a87c1e98212f61ad84))

- Update help docs for Phase 3 features (batch, HyDE, Jina)
  ([`7f5e99f`](https://github.com/n24q02m/wet-mcp/commit/7f5e99fb0939689e4186a7c7a2f47cf8632a2ebc))

- Update help docs for search filters and convert action
  ([`9e85780`](https://github.com/n24q02m/wet-mcp/commit/9e857808574c93f83a7ad78479517a4f65e29ab6))

- Update README for auto-token management
  ([`9d07a00`](https://github.com/n24q02m/wet-mcp/commit/9d07a00e58dfd50785be0901a3bd47fc9f9add07))

- Update README for v2.14.0 features and Jina AI priority
  ([`f1f872c`](https://github.com/n24q02m/wet-mcp/commit/f1f872c9f9137c622259499b5975bf4541cbafbf))

- **readme**: Require Python 3.13 and show uvx arg
  ([#76](https://github.com/n24q02m/wet-mcp/pull/76),
  [`683df7a`](https://github.com/n24q02m/wet-mcp/commit/683df7a5889aeae1544f8de251eb3a207841a1c8))

- **readme**: Require Python 3.13 and show uvx arg
  ([#68](https://github.com/n24q02m/wet-mcp/pull/68),
  [`d725213`](https://github.com/n24q02m/wet-mcp/commit/d7252136dc8663979ed2a0c81ae8c72d3e846c8c))

### Features

- Add automated cleanup for stale release-please PRs
  ([`a48fb56`](https://github.com/n24q02m/wet-mcp/commit/a48fb5620a126fb2eb884c31b5cb607c5d15dee3))

- Add batch extract with per-domain rate limiting
  ([`0c1d39b`](https://github.com/n24q02m/wet-mcp/commit/0c1d39bdb2cee0fdcf2e5e440d797ba1b05ffff2))

- Add batch splitting and retry with exponential backoff to embedder
  ([`c27e637`](https://github.com/n24q02m/wet-mcp/commit/c27e637227b8eee46b5af587794d1e17cbcf26d1))

- Add better-telegram-mcp to Also by section and mcp-name
  ([`378906a`](https://github.com/n24q02m/wet-mcp/commit/378906a5951b93a1d3eb37b844037832dd63809a))

- Add Codecov coverage upload and CodeRabbit config
  ([`7ccd57d`](https://github.com/n24q02m/wet-mcp/commit/7ccd57d9a7fcb7a6ce94a2f920cbf489e888bad1))

- Add data encapsulation against indirect prompt injection (XPIA)
  ([`da31567`](https://github.com/n24q02m/wet-mcp/commit/da315670f41995633cb0a338db34f2b51efd83b1))

- Add development and production rulesets, update CI/CD workflows, and enhance project dependencies
  ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- Add docs indexing, research tools, and caching
  ([`76bc595`](https://github.com/n24q02m/wet-mcp/commit/76bc59596fa3c303621fa9ba9fe95279f1c9b3e0))

- Add embedding/rerank model config env vars to plugin
  ([`fa00759`](https://github.com/n24q02m/wet-mcp/commit/fa007598aea5c3d329fe3c093717187ae0620b4d))

- Add Gemini CLI extension config with PSR version sync
  ([`ace6f5a`](https://github.com/n24q02m/wet-mcp/commit/ace6f5a1f5e36093da21a27d00a2463b0f4412b3))

- Add GITHUB_TOKEN, SYNC_ENABLED and sync config to plugin
  ([`51901b6`](https://github.com/n24q02m/wet-mcp/commit/51901b6588e7a087157fc422e615893ae00eb27e))

- Add Glama.ai badge to README
  ([`96afa3b`](https://github.com/n24q02m/wet-mcp/commit/96afa3bc8ffb1e0c8f73f01e7dc72c07a1a7c3bb))

- Add HyDE for docs search and version-specific docs discovery
  ([`df94edd`](https://github.com/n24q02m/wet-mcp/commit/df94eddd76e80ade213e07558f73adec60e3845d))

- Add is_safe_local_path for local file validation
  ([`4e36e2b`](https://github.com/n24q02m/wet-mcp/commit/4e36e2bd489176f2eba736355b0fcb5db03a1615))

- Add Jina AI as priority #1 for embedding and reranking
  ([`6e78233`](https://github.com/n24q02m/wet-mcp/commit/6e78233f510a39ea5417ea0b4b9e9d2946bc2856))

- Add LLM-powered structured data extraction
  ([`36dae73`](https://github.com/n24q02m/wet-mcp/commit/36dae73e2c7f2c989161ca7769e77813d0d3ce26))

- Add local file convert action with security validation
  ([`4b3cd49`](https://github.com/n24q02m/wet-mcp/commit/4b3cd498b89c8769ea232544b14651ac41f2d54a))

- Add markitdown PDF/DOCX extraction and fix docs discovery
  ([`acc442c`](https://github.com/n24q02m/wet-mcp/commit/acc442c9ea9314ee463de90a818216c3ba6e7e57))

- Add media analysis action and enhance SearXNG installation robustness.
  ([#51](https://github.com/n24q02m/wet-mcp/pull/51),
  [`c5bc612`](https://github.com/n24q02m/wet-mcp/commit/c5bc6128cb05bd18747745d82566d773692cc21d))

- Add media analysis action and enhance SearXNG installation robustness.
  ([#48](https://github.com/n24q02m/wet-mcp/pull/48),
  [`44a45ac`](https://github.com/n24q02m/wet-mcp/commit/44a45acf4f4e534facde1b3c64858edf477294fe))

- Add plugin packaging (skills, hooks, plugin manifest)
  ([`06fffb7`](https://github.com/n24q02m/wet-mcp/commit/06fffb7ff7b6074b64922633e433b514b87c6ced))

- Add search filters (time_range, language, include/exclude domains)
  ([`c7b2bec`](https://github.com/n24q02m/wet-mcp/commit/c7b2bec7f01bfed4eee63f12fba786739a18a3b0))

- Add search strategies (query expansion, find similar, snippet enrichment)
  ([`fe6d3d6`](https://github.com/n24q02m/wet-mcp/commit/fe6d3d6818718c9dad0373784164691fb22f2b2d))

- Add semantic reranking to web search results
  ([`151e357`](https://github.com/n24q02m/wet-mcp/commit/151e3578010e76ff071ed652d843f4759b6a864a))

- Add tests for LiteLLMReranker and Qwen3Reranker; update dependencies in uv.lock
  ([`39b2d28`](https://github.com/n24q02m/wet-mcp/commit/39b2d284b49728eb1adfc150a99ec433841502ec))

- Add tool timeout setting and improve SearXNG compatibility on Windows
  ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- Add URL normalization and per-domain result cap to search
  ([`8168fbb`](https://github.com/n24q02m/wet-mcp/commit/8168fbb951220f888b7a2e7dea243a748094d5a6))

- Add warmup subcommand and improve embedding/reranker startup
  ([`35975be`](https://github.com/n24q02m/wet-mcp/commit/35975bed306c85220e118ee6e8e653378b36849e))

- Async Cache Retrieval ([#457](https://github.com/n24q02m/wet-mcp/pull/457),
  [`54982e0`](https://github.com/n24q02m/wet-mcp/commit/54982e0a50206b0b6fcb47ced4d0a1c0cfeb291b))

- Auto-token management, security hardening, coverage improvements
  ([`1c50a21`](https://github.com/n24q02m/wet-mcp/commit/1c50a214a265d0d9cc763e6bdfe4cfeadb4e6f35))

- Consolidate Jules AI PRs (#20-#56) ([#76](https://github.com/n24q02m/wet-mcp/pull/76),
  [`683df7a`](https://github.com/n24q02m/wet-mcp/commit/683df7a5889aeae1544f8de251eb3a207841a1c8))

- Consolidate Jules AI PRs (#20-#56) ([#68](https://github.com/n24q02m/wet-mcp/pull/68),
  [`d725213`](https://github.com/n24q02m/wet-mcp/commit/d7252136dc8663979ed2a0c81ae8c72d3e846c8c))

- Enhance documentation search with GitHub raw markdown support and content cleaning
  ([`91bfe0f`](https://github.com/n24q02m/wet-mcp/commit/91bfe0fc7a2e99b632066e4d58779f9bbf992a1e))

- Fully automatic sync - no setup-sync or RCLONE_CONFIG vars needed
  ([`e6108cc`](https://github.com/n24q02m/wet-mcp/commit/e6108cc44c160d3f7c0792a5dc974cb09580cd24))

- Implement 3-mode LLM architecture (proxy/sdk/local)
  ([`b1225db`](https://github.com/n24q02m/wet-mcp/commit/b1225db20065b4407391d9856c803aa9c037e7a8))

- Implement version patching for SearXNG installation from zip archive
  ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- Improve tool descriptions for better LLM pass rate
  ([`0cf5acd`](https://github.com/n24q02m/wet-mcp/commit/0cf5acd74ffe60839d25bf6c7d8ba902800213d4))

- Migrate warmup/setup-sync CLI to MCP setup tool
  ([`a9aacd6`](https://github.com/n24q02m/wet-mcp/commit/a9aacd68c2bc4dd2645794f7bdd521bd357fd079))

- Multi-mode plugin config (stdio + docker + http)
  ([`f7933c0`](https://github.com/n24q02m/wet-mcp/commit/f7933c038beed96ab839f7cc2c7e9d510fe49d31))

- Promote dev to main (v2.3.0-beta) ([#51](https://github.com/n24q02m/wet-mcp/pull/51),
  [`c5bc612`](https://github.com/n24q02m/wet-mcp/commit/c5bc6128cb05bd18747745d82566d773692cc21d))

- Promote dev to main (v2.3.0-beta) ([#48](https://github.com/n24q02m/wet-mcp/pull/48),
  [`44a45ac`](https://github.com/n24q02m/wet-mcp/commit/44a45acf4f4e534facde1b3c64858edf477294fe))

- Promote dev to main (v2.4.0-beta.2) ([#68](https://github.com/n24q02m/wet-mcp/pull/68),
  [`d725213`](https://github.com/n24q02m/wet-mcp/commit/d7252136dc8663979ed2a0c81ae8c72d3e846c8c))

- Promote dev to main (v2.4.0-beta.4) ([#76](https://github.com/n24q02m/wet-mcp/pull/76),
  [`683df7a`](https://github.com/n24q02m/wet-mcp/commit/683df7a5889aeae1544f8de251eb3a207841a1c8))

- Promote dev to main (v3.1.0-beta.4) ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- Reuse httpx.AsyncClient in SearXNG retry loop
  ([#187](https://github.com/n24q02m/wet-mcp/pull/187),
  [`3900e01`](https://github.com/n24q02m/wet-mcp/commit/3900e01d8fdc81575c39c7f630f17849158ec1a0))

- Standardize README with MCP Resources, Security, collapsible clients
  ([`90125ef`](https://github.com/n24q02m/wet-mcp/commit/90125eff2dbb197ec146b0094c8bc20d3694d528))

- Testing Improvement] Add tests for start_auto_sync and stop_auto_sync
  ([#422](https://github.com/n24q02m/wet-mcp/pull/422),
  [`b2670bf`](https://github.com/n24q02m/wet-mcp/commit/b2670bf5c361fbc47951355a74a688bb00189a4b))

- Transition from Docker-based SearXNG to embedded subprocess management
  ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- Tune SearXNG engine weights and default language to auto
  ([`f74ff13`](https://github.com/n24q02m/wet-mcp/commit/f74ff134b0836fa11e23ff80f6c318f32db29c2a))

- Update CI configuration and add pytest hook to pre-commit
  ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- Wire Phase 2 actions (structured, similar, expand, enrich)
  ([`e53612b`](https://github.com/n24q02m/wet-mcp/commit/e53612b2e9a05930fbaad42abcf08f608c18244e))

- ⚡ Bolt: [performance improvement] fix N+1 query in vector search by leveraging JOIN
  ([#352](https://github.com/n24q02m/wet-mcp/pull/352),
  [`70155d0`](https://github.com/n24q02m/wet-mcp/commit/70155d0f85fc9d94d8a106f0ee1661aac32eba4b))

- **ci**: Add Renovate config for automated dependency updates
  ([`8c94c3f`](https://github.com/n24q02m/wet-mcp/commit/8c94c3fe3e941bbb16f5a05715d220eadbb998c0))

- **ci**: Add StepSecurity Harden-Runner to all workflow jobs (audit mode)
  ([`088a71a`](https://github.com/n24q02m/wet-mcp/commit/088a71a3879de90c0a56cc79a0e6774cc58db614))

- **config**: Support file-based API keys via @path syntax
  ([#180](https://github.com/n24q02m/wet-mcp/pull/180),
  [`822b289`](https://github.com/n24q02m/wet-mcp/commit/822b2899a3d1911aa8baae5409050531adc660b0))

- **discovery**: Star-count scoring + expand benchmark to 100 libs
  ([`07be846`](https://github.com/n24q02m/wet-mcp/commit/07be8464e99a6946cbff4c14e22d10ce5692264b))

- **docs**: Improve library discovery with Go modules, GitHub homepage upgrade, and scoring fixes
  ([`04e2d4a`](https://github.com/n24q02m/wet-mcp/commit/04e2d4a36ab44e9cd07471dc45438b8f72c45e25))

- **docs**: V14 discovery scoring - crates.io downloads, docs.rs fix, 120-lib benchmark
  ([`e73ef59`](https://github.com/n24q02m/wet-mcp/commit/e73ef59fae6a1eeefacbf907e1d5019e1f50abc4))

- **docs**: V15 sphinx objects.inv discovery for url enumeration
  ([`63c1329`](https://github.com/n24q02m/wet-mcp/commit/63c132941b8e5a342372c827a43f2b7084500da6))

- **docs**: V16 _probe_docs_url, RTD validation, benchmark 200
  ([`8e13a0a`](https://github.com/n24q02m/wet-mcp/commit/8e13a0ab2a645211b9f75923fe4e39523abd461f))

- **docs**: V18 detect Cloudflare blocked pages, add RST support
  ([`37acc4b`](https://github.com/n24q02m/wet-mcp/commit/37acc4b8d50bc49dac858d21c9c35e355e7b9d42))

- **docs**: V19 enhanced discovery, adaptive quality gate, language hints
  ([`63aa113`](https://github.com/n24q02m/wet-mcp/commit/63aa1130af3bb18d4b09d3f02fd083ae9a37dd3e))

- **docs**: V20 README fallback, language hints, 500 benchmark cases
  ([`b0e013b`](https://github.com/n24q02m/wet-mcp/commit/b0e013bc05b2d1facf9dda57b8a352a8e7c1fa37))

- **docs**: V21 two-pass GitHub search, language accept groups, 800 diverse benchmark cases
  ([`a2100e2`](https://github.com/n24q02m/wet-mcp/commit/a2100e27340e9b353cc42c2651f6ec998ea9887e))

- **docs**: V23 well-known docs, SearXNG crash fix, 1200 benchmark cases
  ([`3e8dbf1`](https://github.com/n24q02m/wet-mcp/commit/3e8dbf1fc34077797106e43d8ae4737d9d0854aa))

- **docs**: V24 add 6 registries, config tool, reduce well-known
  ([`b0fcbf7`](https://github.com/n24q02m/wet-mcp/commit/b0fcbf77515d6c6b88e3b60b0e676cb3dcbd9f1f))

- **search**: Add language param for docs disambiguation, change SearXNG port
  ([`96cc99b`](https://github.com/n24q02m/wet-mcp/commit/96cc99b94a17d2ca4709e37f77268f1adac15636))

- **searxng**: Add auto-restart and health checks
  ([#76](https://github.com/n24q02m/wet-mcp/pull/76),
  [`683df7a`](https://github.com/n24q02m/wet-mcp/commit/683df7a5889aeae1544f8de251eb3a207841a1c8))

- **searxng**: Add auto-restart and health checks
  ([#68](https://github.com/n24q02m/wet-mcp/pull/68),
  [`d725213`](https://github.com/n24q02m/wet-mcp/commit/d7252136dc8663979ed2a0c81ae8c72d3e846c8c))

- **searxng**: Shared instance discovery + eager startup
  ([`e18891b`](https://github.com/n24q02m/wet-mcp/commit/e18891b63513591295d9ff2287b795c35a1a78d2))

### Performance Improvements

- Apply async optimizations from merged PRs ([#17](https://github.com/n24q02m/wet-mcp/pull/17),
  [`52dfc44`](https://github.com/n24q02m/wet-mcp/commit/52dfc44f70cf3346d0f4967077b7fe733f13af10))

- Optimize GitHub raw docs fetch with concurrent requests
  ([#535](https://github.com/n24q02m/wet-mcp/pull/535),
  [`2fba5b6`](https://github.com/n24q02m/wet-mcp/commit/2fba5b61be166162088330ed8990ca715e1ec91b))

- Reuse httpx.AsyncClient in SearXNG retry loop
  ([#191](https://github.com/n24q02m/wet-mcp/pull/191),
  [`9234fa2`](https://github.com/n24q02m/wet-mcp/commit/9234fa21ac18cf4568a75db694c4c4d7973221af))

- Use deque for O(1) queue operations in crawler
  ([#201](https://github.com/n24q02m/wet-mcp/pull/201),
  [`ad008f6`](https://github.com/n24q02m/wet-mcp/commit/ad008f6919763c7ed8b005e5277d5c2f0d7865a8))

- **db**: Optimize chunk retrieval with composite index IN clause
  ([#530](https://github.com/n24q02m/wet-mcp/pull/530),
  [`41720c2`](https://github.com/n24q02m/wet-mcp/commit/41720c2efad4945fd1730fcf7b119b70fd131aa2))

- **db**: Optimize rrf score combination speed ([#468](https://github.com/n24q02m/wet-mcp/pull/468),
  [`d057290`](https://github.com/n24q02m/wet-mcp/commit/d057290ad73c926d0a2ebc790335a4b14f939f14))

### Refactoring

- Extract hardcoded crawler timeout to settings
  ([#189](https://github.com/n24q02m/wet-mcp/pull/189),
  [`e32e4a1`](https://github.com/n24q02m/wet-mcp/commit/e32e4a1d7eb6fae68d12ee303eb8d092ce1f2804))

- Make qwen3-embed core dep, cloud-first embedding and reranking
  ([`ebb0388`](https://github.com/n24q02m/wet-mcp/commit/ebb0388c627e30f719878d0bb7f4c27475b420a8))

- Redesign skills/hooks per approved spec
  ([`5dabcb9`](https://github.com/n24q02m/wet-mcp/commit/5dabcb9980c7b0484adc2dbc9f26b25d077396ae))

- Remove custom endpoint support (EMBEDDING_API_BASE, RERANK_API_BASE, LLM_API_BASE)
  ([`e407319`](https://github.com/n24q02m/wet-mcp/commit/e4073198995e54b7da85855564eb2eb8522726e9))

- Remove litellm entirely from wet-mcp, use native provider SDKs
  ([`a2cdd55`](https://github.com/n24q02m/wet-mcp/commit/a2cdd5550e5b41dcd9138753d0092a5561ad6817))

- Remove stop words filtering from FTS queries and update related comments
  ([`b87036e`](https://github.com/n24q02m/wet-mcp/commit/b87036e6eb6754d26c249a2733883e3aa0215b28))

- Replace LiteLLM reranker with Cohere SDK (rerank-v4.0-pro)
  ([`0f2e3d9`](https://github.com/n24q02m/wet-mcp/commit/0f2e3d9e433b3d6304a4625c8f968e2d47e37dab))

- Update crawl4ai setup process and remove Playwright installation
  ([#76](https://github.com/n24q02m/wet-mcp/pull/76),
  [`683df7a`](https://github.com/n24q02m/wet-mcp/commit/683df7a5889aeae1544f8de251eb3a207841a1c8))

- Use settings.crawler_timeout in download_media
  ([#195](https://github.com/n24q02m/wet-mcp/pull/195),
  [`2fd7958`](https://github.com/n24q02m/wet-mcp/commit/2fd7958d82b57b8c72228a86f684b37170634f12))

- **llm**: Avoid redundant calls to get_llm_config in analyze_media
  ([#196](https://github.com/n24q02m/wet-mcp/pull/196),
  [`e423df4`](https://github.com/n24q02m/wet-mcp/commit/e423df4d711d78554fd4b19a8055b5854646b69a))

### Testing

- Add cloud embedding mode tests with API_KEYS
  ([`d4dea4e`](https://github.com/n24q02m/wet-mcp/commit/d4dea4e155a58cfd017156e9e7c7ca6253a8def6))

- Add comprehensive real-world integration tests
  ([`3676ad3`](https://github.com/n24q02m/wet-mcp/commit/3676ad370db45da5a07e1229985184508494d71e))

- Add comprehensive test suites to achieve 80% coverage
  ([`88584d1`](https://github.com/n24q02m/wet-mcp/commit/88584d162796c608b8c905c33bfa248c8d2543cb))

- Add comprehensive tests for ensure_searxng orchestration
  ([#184](https://github.com/n24q02m/wet-mcp/pull/184),
  [`2d24dac`](https://github.com/n24q02m/wet-mcp/commit/2d24dac64749bd9fa8c5a0d48038cb95fbdd1ea6))

- Add coverage gap tests for setup and sync modules
  ([`584ebdd`](https://github.com/n24q02m/wet-mcp/commit/584ebdd329c241f93c82efd2fb1db45761bb33b3))

- Add full/real live tests for all tools and modes
  ([`dad7f15`](https://github.com/n24q02m/wet-mcp/commit/dad7f15a05f13b013d6262e3aa03d6ecdcf9197d))

- Add Modal.com AI workers integration tests
  ([`fcdb887`](https://github.com/n24q02m/wet-mcp/commit/fcdb88729f12ccd47138878642821b728e04c7ab))

- Add pytest-based live MCP protocol tests
  ([`2d61b75`](https://github.com/n24q02m/wet-mcp/commit/2d61b75000a4d6312e40b53f083819c84df1a466))

- Add test_analyze_media_large_text_file to verify truncation
  ([#190](https://github.com/n24q02m/wet-mcp/pull/190),
  [`c8d76d6`](https://github.com/n24q02m/wet-mcp/commit/c8d76d6903cd486629cc722910c56884536412a4))

- Add unit tests for list_media in crawler ([#177](https://github.com/n24q02m/wet-mcp/pull/177),
  [`31df357`](https://github.com/n24q02m/wet-mcp/commit/31df357b010b2ace0117d632a7a0159910850c16))

- Comprehensive unit tests for 97% coverage
  ([`072ac8b`](https://github.com/n24q02m/wet-mcp/commit/072ac8b442a3a0ca2d7cbfed943dab1e1aa723c2))

- **benchmark**: Expand to 2000 cases and add comparison report
  ([`03fd3eb`](https://github.com/n24q02m/wet-mcp/commit/03fd3eb9de972cc6c6a4e88722a5d4d84fa71eb4))

- **crawler**: Add unit tests for download_media success path
  ([#194](https://github.com/n24q02m/wet-mcp/pull/194),
  [`41d7d41`](https://github.com/n24q02m/wet-mcp/commit/41d7d41bb27c45fc1c94e41a59ed3a7b455976f1))

- **server**: Add comprehensive tests for _with_timeout helper
  ([#197](https://github.com/n24q02m/wet-mcp/pull/197),
  [`4d6cda9`](https://github.com/n24q02m/wet-mcp/commit/4d6cda90cae326a48b3d67a764faf8a67d282fbb))


## v2.1.3 (2026-02-04)

### Bug Fixes

- **server**: Remove url cache to ensure auto-restart
  ([`36f44d2`](https://github.com/n24q02m/wet-mcp/commit/36f44d23b624a2422ef18597b4d855aea07de7b5))

### Chores

- **release**: 2.1.3 [skip ci]
  ([`ec2beb8`](https://github.com/n24q02m/wet-mcp/commit/ec2beb833259ccef65f6c4096097764e26c3f5a7))


## v2.1.2 (2026-02-04)

### Bug Fixes

- **searxng**: Robust connection fix
  ([`140eecb`](https://github.com/n24q02m/wet-mcp/commit/140eecb5ee064033df30b6ad62da708b990c4427))

### Chores

- **release**: 2.1.2 [skip ci]
  ([`76553b5`](https://github.com/n24q02m/wet-mcp/commit/76553b5d93fcc66af1c379863ecacc1d5fdbe6bc))


## v2.1.1 (2026-02-04)

### Bug Fixes

- Update tests and formatting
  ([`17906f3`](https://github.com/n24q02m/wet-mcp/commit/17906f3641b80ae2fa267923cadd9b0169e411fa))

### Chores

- **release**: 2.1.1 [skip ci]
  ([`d28a5a7`](https://github.com/n24q02m/wet-mcp/commit/d28a5a77088973009baae334b70e0ff04ed2093d))


## v2.1.0 (2026-02-04)

### Chores

- **release**: 2.1.0 [skip ci]
  ([`0ccf15a`](https://github.com/n24q02m/wet-mcp/commit/0ccf15a3fdea44acfed7bab68778de59e626f5e4))

### Features

- Enable LLM analysis for text files and enhance SearXNG container startup with port readiness
  checks.
  ([`4fb3f4e`](https://github.com/n24q02m/wet-mcp/commit/4fb3f4eb1dc6ed7fd47c29da7e824fc03b8eb146))


## v2.0.0 (2026-02-04)

### Chores

- **release**: 2.0.0 [skip ci]
  ([`52eb67c`](https://github.com/n24q02m/wet-mcp/commit/52eb67c52ac106a72005c0e11e2452b23b9ef68d))

### Features

- Refactor API_KEYS format and add auto-detect capabilities
  ([`77e277b`](https://github.com/n24q02m/wet-mcp/commit/77e277b8989a692cd3ede287ba25f83f949d3f4b))

### Breaking Changes

- API_KEYS now expects ENV_VAR:key format e.g. GOOGLE_API_KEY:abc instead of gemini:abc


## v1.3.0 (2026-02-03)

### Chores

- **release**: 1.3.0 [skip ci]
  ([`618a86c`](https://github.com/n24q02m/wet-mcp/commit/618a86ccf015dba768dcd65f0494937ec6f64e25))

### Features

- Enhance crawler with retries, user-agent, redirect following, and protocol-relative URL handling.
  ([`ab1ecea`](https://github.com/n24q02m/wet-mcp/commit/ab1ecead5ae0fbbd4e7f33cd6d82e0a6e2215ea2))


## v1.2.1 (2026-02-03)

### Chores

- **release**: 1.2.1 [skip ci]
  ([`df3d238`](https://github.com/n24q02m/wet-mcp/commit/df3d238e685e675d0d9ec5faebf82df96190ac9f))


## v1.2.0 (2026-02-03)

### Bug Fixes

- Silence Crawl4AI verbose output to prevent JSON parse errors
  ([`62d5f92`](https://github.com/n24q02m/wet-mcp/commit/62d5f92a1a398fef7e4c1c9bd88cb52e2c63a2e0))

### Chores

- **release**: 1.2.0 [skip ci]
  ([`737e7f7`](https://github.com/n24q02m/wet-mcp/commit/737e7f7def5b6782e2be34f851d61f7fa1660d04))

### Features

- Integrate LiteLLM for media analysis (analyze tool)
  ([`77003ce`](https://github.com/n24q02m/wet-mcp/commit/77003ce43c3641a1d755398a03806826720a343c))


## v1.1.0 (2026-02-03)

### Chores

- **release**: 1.1.0 [skip ci]
  ([`43fcb0f`](https://github.com/n24q02m/wet-mcp/commit/43fcb0f448d855edb33c6356837de79217dfe249))

### Features

- Integrate LiteLLM for media analysis (analyze tool)
  ([`fe4d365`](https://github.com/n24q02m/wet-mcp/commit/fe4d36571f6d2104f989e60178aac0e01d225002))


## v1.0.0 (2026-02-03)

- Initial Release
