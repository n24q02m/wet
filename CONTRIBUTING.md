# Contributing to wet-mcp

Thank you for your interest in contributing to wet-mcp! This guide will help you get started.

## Getting Started

### Prerequisites

- **mise** (recommended) or **Python 3.13+** and **uv**
- Git
- A GitHub account

**Recommended:** Use [mise](https://mise.jdx.dev/) to automatically manage Python and uv versions from `.mise.toml`.

### Setup Development Environment

1. **Fork the repository** and clone your fork

```bash
git clone https://github.com/YOUR_USERNAME/wet-mcp
cd wet-mcp
```

2. **Install tools and dependencies**

If using **mise** (recommended):

```bash
mise run setup
```

Without mise, ensure you have Python 3.13+ and uv installed:

```bash
uv sync --dev
uv run pre-commit install
uv run playwright install chromium
```

3. **Run checks**

```bash
uv run ruff check .
uv run ruff format --check .
```

## Development Workflow

### Running Locally

```bash
# Run the server (SearXNG will auto-start as embedded subprocess)
uv run wet-mcp

# For LLM-based media analysis, set API keys:
export API_KEYS="GOOGLE_API_KEY:your-key"
```

### Making Changes

1. Create a new branch: `git checkout -b feature/your-feature-name`
2. Make your changes
3. Run checks: `uv run ruff check . && uv run ruff format .`
4. Run tests: `uv run pytest`
5. Commit your changes (see [Commit Convention](#commit-convention))
6. Push to your fork: `git push origin feature/your-feature-name`
7. Open a Pull Request

## Commit Convention

We use [Conventional Commits](https://www.conventionalcommits.org/):

```text
<type>[optional scope]: <description>
```

### Types

Only `feat` and `fix` are accepted. The pre-commit commit-message hook
(`scripts/enforce-commit.sh`) rejects any other type (e.g. `docs`,
`chore`, `refactor`, `ci`). Do not use the `!` breaking-change marker.

- `feat`: New feature
- `fix`: Bug fix

### Examples

```text
feat: add support for PDF extraction
fix: handle SearXNG connection timeout
```

## Release Process

Releases are automated using **python-semantic-release (PSR) v10**. We strictly follow the **Conventional Commits** specification to determine version bumps and generate changelogs automatically.

### How to Release

1. Create a Pull Request with your changes.
2. Ensure your commit messages follow the convention above.
3. Merge the PR to `main`.
4. A maintainer triggers the CD workflow manually via **workflow_dispatch**:
   - Choose `beta` or `stable` release type.
   - PSR analyzes commits since the last release.
   - Bumps version, updates `CHANGELOG.md`, creates a tag.
   - Publishes to PyPI.
   - Creates a GitHub Release.
   - Builds and pushes Docker images.

You do **not** need to create manual tags or changelog entries.

## Pull Request Guidelines

- Keep PRs focused on a single feature or fix
- Update documentation if needed
- Add tests for new functionality
- Ensure all checks pass

### PR Checklist

Before submitting your PR, ensure:

- [ ] Code follows Python best practices
- [ ] All tests pass (`uv run pytest`)
- [ ] Linting passes (`uv run ruff check .`)
- [ ] Formatting is correct (`uv run ruff format --check .`)
- [ ] Commit messages follow **Conventional Commits**
- [ ] Documentation updated (if needed)

## Code Style

This project uses **Ruff** for formatting and linting.

```bash
uv run ruff check .       # Check for issues
uv run ruff check --fix . # Auto-fix issues
uv run ruff format .      # Format code
```

## Testing

```bash
uv run pytest              # Run all tests
uv run pytest -v           # Verbose output
uv run pytest --tb=short   # Short tracebacks
```

## Project Structure

```text
wet-mcp/
├── src/
│   └── wet_mcp/
│       ├── __init__.py
│       ├── config.py          # Configuration
│       ├── server.py          # MCP server
│       ├── searxng_runner.py   # Embedded SearXNG subprocess
│       ├── setup.py           # Auto-setup (SearXNG + Playwright)
│       ├── llm.py             # LLM utilities (litellm passthrough via mcp-core[llm])
│       ├── security.py        # URL security validation
│       ├── docs/              # Tool documentation (Markdown)
│       └── sources/
│           ├── crawler.py     # Web crawling (Crawl4AI)
│           └── searxng.py     # Search (SearXNG)
├── tests/
├── pyproject.toml
└── README.md
```

## Questions?

Feel free to open an issue for:

- Bug reports
- Feature requests
- Questions about the codebase
- Discussion about architecture

## License

By contributing, you agree that your contributions will be licensed under the Apache License, Version 2.0.

---

**Thank you for contributing!**
