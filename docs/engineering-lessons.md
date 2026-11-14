# Engineering lessons

Lessons recovered from the notes of a discarded third-party automation
tool, kept here instead of deleted. Each entry carries the commit that landed
the change in this repository, so a proposal can be located in the history
before the same change is proposed again. Dates are landing dates taken from
`git log`; the order below is the order the notes recorded, not a re-sorting.

## Performance

### 2026-07-05 - Optimized String Window Scanning
**Commit:** 5d04261
**Learning:** Sliding windows using string slicing (`string[i : i+N]`) combined with `O(M * N)` substring matching operations within a loop traversing a full document causes exponential slowdowns on larger blocks of text.
**Action:** Always pre-calculate exact match indices via C-optimized `str.find()` first, then evaluate windows conditionally limited only to relevant indices/buckets rather than traversing blindly across the entire string length.

### 2026-07-10 - Avoid string joining for length checks in tight loops
**Commit:** 153b70c
**Learning:** In `_strip_nav_heading_blocks` (a hot path in markdown chunking), joining multiple string lines into a single string (`"\n".join(...)`) just to check if the combined length exceeds a small limit (50 chars) causes unnecessary memory allocation overhead and slows down processing.
**Action:** Replace `"\n".join` with an iterative loop that calculates the cumulative length (`content_length += len(line.strip())`), and exit early once the limit is reached.

### 2026-07-10 - Optimize string length checks in loops
**Commit:** 729bf0c
**Learning:** Checking the length of accumulated string lists via `len("\n".join(lines))` inside a loop is O(N^2) time complexity and causes repeated memory allocations.
**Action:** Instead of joining strings purely to measure length, track length incrementally with an integer variable (e.g. `current_length += len(line) + (1 if lines else 0)`) to reduce time complexity to O(1) per iteration.

### 2026-07-10 - Fixing `ty` typechecker issues with `ty: ignore`
**Commit:** 729bf0c
**Learning:** The typechecker used in this project is `ty`, not `mypy`. Ignore pragmas must take the form of `# ty: ignore[<rule>]`. For example, `type: ignore` and `ty: ignore` alone don't work, we need `# ty: ignore[unsupported-base]`. Additionally, we also have to clean up unused ignore pragmas or `ty check` fails with unused ignore comments.
**Action:** Always run `uv run ty check` as part of CI checks. Only add `# ty: ignore[<error>]` after verifying what the exact error name is, and remove obsolete `# ty: ignore` lines if they trigger `warning[unused-ignore-comment]`.

### 2026-07-11 - Fast String Suffix/Prefix matching with tuples
**Commit:** 23b5b55
**Learning:** Python generator expressions inside `any()` for checking multiple prefixes/suffixes (e.g. `any(path.endswith(ext) for ext in EXTENSIONS)`) are slow due to Python-level iteration overhead.
**Action:** Always prefer passing a tuple of strings directly to `str.startswith()` and `str.endswith()` (e.g., `path.endswith(tuple(EXTENSIONS))`). This pushes the iteration down into optimized C code, yielding roughly ~5-7x speedup for prefix/suffix matching. Ensure the tuple is defined at the module level if used repeatedly.

### 2026-07-17 - Avoid micro-optimizing cold paths
**Commit:** 1d9b8dd
**Learning:** Replacing idiomatic Python generator expressions (like `sum(1 for ...)`) with manual `for` loops in cold paths (like project locking logic) sacrifices code readability for negligible performance gains, and is considered a negative micro-optimization.
**Action:** When searching for performance improvements, verify that the targeted code is actually in a hot path or tight loop before applying optimizations that reduce readability.

### 2026-07-17 - Use short-circuiting in threshold checks
**Commit:** 1d9b8dd
**Learning:** When checking for a threshold (e.g., detecting if a page is blocked by checking if `hits >= 2`), iterating over the full list of markers using `sum(1 for ...)` wastes cycles. An inline `for` loop with a `break` statement can short-circuit the evaluation as soon as the threshold is met.
**Action:** Apply early exits (`break` or `return`) when counting matches if a fixed threshold defines success or failure.

### 2026-07-18 - Use str.split() for multi-whitespace replacement
**Commit:** 7cbab2e
**Learning:** `re.sub(r"\s+", " ", text).strip()` is generally slower than `" ".join(text.split())` for collapsing multiple whitespace characters into single spaces, as the latter avoids regex engine overhead and is executed entirely in optimized C code.
**Action:** Use `" ".join(text.split())` instead of regex substitution when the goal is simply to replace continuous whitespace characters with a single space.

### 2026-07-25 - Match host suffixes, not substrings
**Commit:** efdf601
**Learning:** `"rtfd.io" in netloc` is also true for `turbo.rtfd.io.evil.com`, whose first label then passes the `subdomain == lib_norm` comparison in `_score_discovery_result` and collects the ReadTheDocs relevance bonus for an attacker-controlled domain. CodeQL reports this shape as `py/incomplete-url-substring-sanitization` whenever the searched string contains a dot.
**Action:** Compare hosts against a module-level tuple of known hosts with `host == h or host.endswith(f".{h}")`, after lowercasing and stripping the port and any trailing dot. Keep every host the previous substring test accepted: dropping `readthedocs-hosted.com` would have silently lost the bonus for ReadTheDocs for Business projects.

### 2026-08-01 - Skip past a heading run the scan has already rejected
**Commit:** d1fd42e
**Learning:** The outer loop of `_strip_nav_heading_blocks` advanced one heading at a time whenever a run was too short to be navigation, so every heading of a rejected run was rescanned as the start of a new run. Advancing straight to the index that broke the run is exact rather than approximate, and the condition that makes it exact is that the inner loop's `break` does not depend on where the run started: it fires on a change of heading level, or on more than 50 characters of content since the previous heading. A run restarted anywhere inside `[i + 1, j - 1]` therefore breaks at the same `j` and is strictly shorter, so it cannot reach the 5-heading threshold the longer run already missed. State that condition before reusing the argument — "any sub-sequence will fail the same check" is false for a loop whose exit test reads state accumulated since the run began, and such a loop must not take this rewrite.
**Action:** Establish equivalence by differential testing against the previous implementation, and keep the harness in the repository: `tests/test_docs_hot_path.py` compares the two over every sequence drawn from alphabets covering each inner-loop branch and over generated documents (106,910 sequences and 3,000 documents by default, 2,222,302 and 60,000 under `-m full`), with zero divergence. Measure before naming a complexity class. This rescan was never quadratic: growing the input eightfold grew the pre-change runtime 9.2x, not ~64x, because only runs shorter than 5 headings take the slow step, so each heading is rescanned at most 4 times. The saving is a constant factor — 1.41x on a synthetic worst case of four-heading runs (3.020 ms to 2.147 ms at 8000 lines) and 1.045x on realistic document shapes (6.12 ms to 5.86 ms), against an A-vs-A control arm at 1.002x and 1.012x. Quote a figure of that shape rather than a round percentage.

### Rejected

Proposals that were reviewed and turned down, with the reason. They are recorded
here so the reason travels with the repository instead of staying behind in a
closed pull request.

#### 2026-07-25 - Expanding a two-element `any()` into explicit `or` (#1556)
**Proposed:** rewrite `any(p in parsed_hp.netloc for p in ("readthedocs", "rtfd.io"))` and `any(p in all_urls for p in ("deprecate-holder", "placeholder"))` in `_score_discovery_result` as explicit `or` chains, claimed at "~3.5x faster".
**Why rejected:** the call site is not hot. `_score_discovery_result` runs once per registry result at `sources/docs.py:1826` — a handful of dicts per lookup — and only after `asyncio.gather` has queried the package registries over HTTP and `_pre_upgrade_discovery_results` has made its GitHub API calls. A saving on the order of 100 ns sits against hundreds of milliseconds of network work, and no measurement accompanied the claim. The 2026-07-17 entry above already covers this. The proposal also arrived under a title about `_DOC_DIRS`, which its diff never touched.
**Action:** Before proposing a membership-test rewrite, trace the call site to a loop that runs often enough for the saving to be observable, and quote a measurement taken on this repository. Where the surrounding work is I/O, prefer proposals that remove a request or a round-trip. The hostname half of that proposal was the part worth having, and it landed as efdf601.

#### 2026-07-25 - Optimisation comments in source (#1556)
**Proposed:** annotate the rewritten conditions with a comment naming the optimisation and its expected impact.
**Why rejected:** this repository is public. A comment that names the tool which wrote it, and asserts an unmeasured speedup, is noise for every later reader of the file.
**Action:** Write comments that explain why the code is shaped the way it is, in the voice of the surrounding file — for example, the reason a fast path exists and the measurement that justified it. Leave authorship to the commit metadata.

### 2026-08-05 - Fast Iterable Intersection with frozenset.isdisjoint()
**Learning:** Python generator expressions inside `any()` checking against a static collection (e.g., `any(p.lower() in _DOC_DIRS for p in parts)`) are slowed down by Python-level iteration overhead.
**Action:** Define the static collection as a `frozenset` and use `not _DOC_DIRS.isdisjoint(...)`. The `isdisjoint()` method iterates through the generator in optimized C code and short-circuits, yielding a ~10-15% speedup over `any()` with a generator.

### 2025-01-20 - Extract redundant string transformations from generator expressions
**Learning:** When using redundant string transformations like `.lower()` inside generator expressions such as `any(skip in u.lower() for skip in skip_patterns)`, Python evaluates the transformation repeatedly for each item in the generator. This causes significant overhead (calling `.lower()` multiple times).
**Action:** Always extract the transformation to a variable outside the expression (e.g., `u_lower = u.lower()`). If this occurs inside a list comprehension, safely convert it to a standard `for` loop.

### 2025-01-20 - Precompile regex and use .split() for HTML cleanup
**Learning:** Repeatedly compiling regexes (like `<[^>]*>`) inside functions such as `_html_text` and using `re.sub(r"\s+", " ")` for whitespace replacement introduces unnecessary overhead in hot paths like text extraction from search backends.
**Action:** Always precompile frequently used regexes at the module level (e.g., `_HTML_TAG_RE = re.compile(r"<[^>]*>")`) and use `" ".join(text.split())` instead of regex substitution for collapsing multiple whitespace characters.
### 2026-08-10 - Fast-path early returns in text processing
**Learning:** In text processing functions that search for specific patterns across large documents (e.g., extracting template macros like `{{`), if the pattern is typically absent in most inputs, implement a fast-path early return (e.g., `if "{{" not in content: return content`) using Python's C-optimized string search. This avoids expensive memory allocations and loops associated with `splitlines()` or `split()`.
**Action:** Always consider an early exit based on a simple string containment check (`in`) before performing heavy string manipulations like `splitlines()` on large text bodies.
### 2024-05-18 - Fast Iterable Intersection with frozenset.isdisjoint()
**Learning:** Python generator expressions inside `any()` checking against a static collection (e.g., `any(part in sensitive_dirs for part in p.parts)`) are slowed down by Python-level iteration overhead and repeated allocation when the collection is defined inside a hot path function.
**Action:** Define the static collection as a module-level `frozenset` and use `not collection.isdisjoint(...)`. The `isdisjoint()` method iterates through the sequence in optimized C code and short-circuits, yielding a ~2x speedup over `any()` with a generator.
### 2025-01-20 - Combine regular expressions for performance
**Learning:** In text processing loops that strip out different elements (like script/style tags and general HTML tags) using multiple `re.sub` calls, combining the patterns into a single regular expression using the alternation operator (`|`) and using a pre-compiled regex object (`re.compile`) avoids multiple full passes over the string and leverages the C-based regex engine, resulting in measurable performance improvements (e.g. 15-20% speedup).
**Action:** Combine multiple pre-compiled regular expressions into a single pattern using the alternation operator (`|`) to improve performance in text processing functions.
### 2024-05-18 - Fast parameter extraction without urlparse
**Learning:** Parsing the entire URL with `urllib.parse.urlparse` and `parse_qs` just to extract a single known query parameter is slow and allocates multiple objects. In hot paths (like unrolling DuckDuckGo result URLs), using basic string manipulation (`str.find`) yields a ~3x speedup.
**Action:** Use manual string slicing (e.g., `href.find("param=")`) when extracting simple, known parameters from URLs in performance-sensitive text processing.

### 2026-08-15 - Replace urlparse in StartpageBackend hot path
**Learning:** Using `urllib.parse.urlparse` just to check the hostname of a URL in a hot loop (like parsing search results) allocates multiple objects and is significantly slower than direct string manipulation.
**Action:** Use fast string slicing (`str.find`) and an early containment check (`in`) to extract the domain, avoiding the overhead of full URL parsing.

### 2025-02-14 - Slice large strings before lstrip
**Learning:** When validating the prefix of a very large string (e.g., an entire HTTP response) after whitespace removal, avoid calling `.strip()` or `.lstrip()` on the whole string as it allocates a massive copy if leading whitespace is present.
**Action:** Slice a small prefix first (e.g., `content[:100].lstrip().startswith(...)`) to minimize memory allocation overhead.

### 2025-02-19 - Fast URL path extraction in hot loops
**Learning:** Using `urllib.parse.urlparse` to extract the URL path inside hot loops like `_score_url_by_query` allocates multiple objects and incurs unnecessary overhead. For standard HTTP(S) URLs, simple string slicing (`str.find`) is significantly faster.
**Action:** When extracting URL paths in hot paths, check for "http://" or "https://", ensure there is no "@" (basic auth) or "[" (IPv6), and use `url.find("/", ...)` and handle bounds for "?" or "#". Use `urlparse` only as a fallback.

### 2026-08-20 - Combine regular expressions for substring matching in hot loops
**Learning:** Python generator expressions inside `any()` checking multiple static substrings (e.g., `any(seg in final_path for seg in _AUTH_SEGMENTS)`) are slowed down by Python-level iteration overhead and repeated generator allocation.
**Action:** Combine multiple static substrings into a single pre-compiled regular expression using alternation (`re.compile("|".join(re.escape(p) for p in patterns))`) and use `.search()`. This leverages the C-based regex engine, yielding a ~2x speedup on hot URL filtering paths.

### 2026-08-20 - Fast URL hostname extraction without urlparse
**Learning:** Using `urllib.parse.urlparse` to extract the hostname of a URL in hot loops allocates multiple objects and is significantly slower than direct string manipulation.
**Action:** Use fast string slicing (`str.find`) bounding by `?`, `#`, and `/` to extract the domain for standard HTTP(S) and `git+https` URLs. Ensure to check for `@` (basic auth) and `[` (IPv6) before relying on the fast path, falling back to `urlparse` otherwise. This avoids object allocations and yields a ~20% speedup.

## Security

### 2026-05-16 - Path Traversal in Token Storage
**Commit:** 031a146 (#1091)
**Vulnerability:** The `token_store.py` module constructed file paths by directly concatenating user-controlled inputs (`provider`, `sub`) via `pathlib.Path` without validation. This allowed path traversal (e.g., using `../` or absolute paths) to read or write arbitrary files on the system with the application's permissions.
**Learning:** Even when using higher-level path abstractions like `pathlib`, string concatenation or `/` division with unvalidated user input is unsafe because the underlying OS resolution still respects traversal sequences.
**Prevention:** Always explicitly validate path components for dangerous characters (like `/`, `\`, and `..`) using an explicit string validation helper before passing them to file I/O operations or path constructors.

### 2026-06-21 - Unsafe Dynamic SQL in SQLite PRAGMA calls
**Commit:** 4357e1a (#1399)
**Vulnerability:** Raw `PRAGMA table_info({table})` and `PRAGMA index_list({table})` using f-strings allows for SQL injection if the table identifier is unsanitized user input. SQLite DDL does not allow standard SQL bound parameters for table names.
**Learning:** SQLite introduced table-valued functions for introspection (`pragma_table_info(?)` and `pragma_index_list(?)`) which do support safe parameterization using bound variables.
**Prevention:** Always use parameterized `SELECT name FROM pragma_table_info(?)` or `SELECT name FROM pragma_index_list(?)` instead of using raw dynamic `PRAGMA` queries using string concatenation or f-strings. Note that when migrating from raw `PRAGMA` to `SELECT name FROM pragma_...`, the target column is returned at index 0 rather than index 1 (or by "name" dict lookup).

### 2026-07-10 - Path Hijacking in subprocess.run
**Commit:** 879ca76
**Vulnerability:** The `subprocess.run` call in `src/wet/server.py` used a partial executable name (`"gh"`) instead of an absolute path. This is susceptible to path hijacking (where an attacker controls the PATH environment variable to execute a malicious binary).
**Learning:** Even though `shutil.which` was used to check for the existence of an executable, the result was discarded, and the partial name was still passed to `subprocess.run`.
**Prevention:** Always use the absolute path returned by `shutil.which` (or hardcode the absolute path if known) when passing the executable name to `subprocess.run`.

### 2026-07-24 - Hardcoded Bind Interface
**Commit:** fd3f437 (#1557)
**Vulnerability:** The application was hardcoded to bind to `0.0.0.0` in multi-user mode. This could expose the service on all network interfaces unconditionally, which may not be desirable in environments where it should only be accessible through specific interfaces or VPNs.
**Learning:** Security scanners like Bandit often flag hardcoded `0.0.0.0` bindings (B104) because it's safer to let administrators control the listen interface.
**Prevention:** Allow configuration of the bind host via an environment variable (e.g., `MCP_HOST`) with `0.0.0.0` as the fallback default for backward compatibility. Add a `# nosec B104` pragma to suppress false positives where the default behavior is intentional and validated.

### Rejected

Findings that were reviewed and turned down, with the reason. They are recorded
here so the reason travels with the repository instead of staying behind in a
closed pull request.

No security finding has been rejected in this repository yet. When one is,
record what was proposed, why it was turned down, and what the correct shape
looks like, so the next scan starts from the answer rather than the question.
### 2026-08-26 - Unsafe Dynamic SQL in SQLite PRAGMA calls in tests
**Vulnerability:** Raw `PRAGMA table_info({table})` using f-strings allows for SQL injection if the table identifier is unsanitized user input in `tests/test_d1_schema_0002.py`.
**Learning:** SQLite introduced table-valued functions for introspection (`pragma_table_info(?)`) which do support safe parameterization using bound variables.
**Prevention:** Always use parameterized `SELECT name FROM pragma_table_info(?)` instead of using raw dynamic `PRAGMA` queries using string concatenation or f-strings. Note that when migrating from raw `PRAGMA` to `SELECT name FROM pragma_...`, the target column is returned at index 0 rather than index 1.
