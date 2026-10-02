Dates below are the dates the fix landed on `main`, taken from `git log`. Each
entry carries the commit holding it, so an entry can be located in the
repository history before the same finding is raised again.

## 2026-05-16 - Path Traversal in Token Storage
**Commit:** 031a146 (#1091)
**Vulnerability:** The `token_store.py` module constructed file paths by directly concatenating user-controlled inputs (`provider`, `sub`) via `pathlib.Path` without validation. This allowed path traversal (e.g., using `../` or absolute paths) to read or write arbitrary files on the system with the application's permissions.
**Learning:** Even when using higher-level path abstractions like `pathlib`, string concatenation or `/` division with unvalidated user input is unsafe because the underlying OS resolution still respects traversal sequences.
**Prevention:** Always explicitly validate path components for dangerous characters (like `/`, `\`, and `..`) using an explicit string validation helper before passing them to file I/O operations or path constructors.

## 2026-06-21 - Unsafe Dynamic SQL in SQLite PRAGMA calls
**Commit:** 4357e1a (#1399)
**Vulnerability:** Raw `PRAGMA table_info({table})` and `PRAGMA index_list({table})` using f-strings allows for SQL injection if the table identifier is unsanitized user input. SQLite DDL does not allow standard SQL bound parameters for table names.
**Learning:** SQLite introduced table-valued functions for introspection (`pragma_table_info(?)` and `pragma_index_list(?)`) which do support safe parameterization using bound variables.
**Prevention:** Always use parameterized `SELECT name FROM pragma_table_info(?)` or `SELECT name FROM pragma_index_list(?)` instead of using raw dynamic `PRAGMA` queries using string concatenation or f-strings. Note that when migrating from raw `PRAGMA` to `SELECT name FROM pragma_...`, the target column is returned at index 0 rather than index 1 (or by "name" dict lookup).

## 2026-07-10 - Path Hijacking in subprocess.run
**Commit:** 879ca76
**Vulnerability:** The `subprocess.run` call in `src/wet_mcp/server.py` used a partial executable name (`"gh"`) instead of an absolute path. This is susceptible to path hijacking (where an attacker controls the PATH environment variable to execute a malicious binary).
**Learning:** Even though `shutil.which` was used to check for the existence of an executable, the result was discarded, and the partial name was still passed to `subprocess.run`.
**Prevention:** Always use the absolute path returned by `shutil.which` (or hardcode the absolute path if known) when passing the executable name to `subprocess.run`.

## 2026-07-24 - Hardcoded Bind Interface
**Commit:** fd3f437 (#1557)
**Vulnerability:** The application was hardcoded to bind to `0.0.0.0` in multi-user mode. This could expose the service on all network interfaces unconditionally, which may not be desirable in environments where it should only be accessible through specific interfaces or VPNs.
**Learning:** Security scanners like Bandit often flag hardcoded `0.0.0.0` bindings (B104) because it's safer to let administrators control the listen interface.
**Prevention:** Allow configuration of the bind host via an environment variable (e.g., `MCP_HOST`) with `0.0.0.0` as the fallback default for backward compatibility. Add a `# nosec B104` pragma to suppress false positives where the default behavior is intentional and validated.

## Rejected

Findings that were reviewed and turned down, with the reason. They are recorded
here so the reason travels with the repository instead of staying behind in a
closed pull request.

No security finding has been rejected in this repository yet. When one is,
record what was proposed, why it was turned down, and what the correct shape
looks like, so the next scan starts from the answer rather than the question.
## 2026-08-26 - Unsafe Dynamic SQL in SQLite PRAGMA calls in tests
**Vulnerability:** Raw `PRAGMA table_info({table})` using f-strings allows for SQL injection if the table identifier is unsanitized user input in `tests/test_d1_schema_0002.py`.
**Learning:** SQLite introduced table-valued functions for introspection (`pragma_table_info(?)`) which do support safe parameterization using bound variables.
**Prevention:** Always use parameterized `SELECT name FROM pragma_table_info(?)` instead of using raw dynamic `PRAGMA` queries using string concatenation or f-strings. Note that when migrating from raw `PRAGMA` to `SELECT name FROM pragma_...`, the target column is returned at index 0 rather than index 1.
