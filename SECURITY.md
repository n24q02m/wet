# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 3.x.x   | :white_check_mark: |
| < 3.0   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability, please **DO NOT** create a public issue.

Instead, please email: **quangminh2402.dev@gmail.com**

Include:

1. Detailed description of the vulnerability
2. Steps to reproduce
3. Potential impact
4. Suggested fix (if any)

You will receive acknowledgment within 48 hours.

## Security Best Practices

When using wet:

- **Never commit API keys** to version control
- Use environment variables or secure secret management
- Keep dependencies updated
- Be cautious with URL inputs (SSRF protection is built-in)
- Review extracted content before processing sensitive data

## Trust Model & Threat Boundaries

- **Untrusted external data**: All search, extract, crawl, and docs content originating from the web is treated strictly as untrusted data. Responses are wrapped in `<untrusted_<tool>_content>` XML boundary tags on text channels, carry `_untrusted_source` / `_untrusted_warning` markers in `structuredContent`, strip hidden DOM/zero-width obfuscation characters, and surface `_injection_warnings` when indirect prompt-injection patterns are matched.
- **SSRF defense**: Outbound HTTP fetches validate resolved IPs via `hull-web`'s `is_safe_url` / DNS-pinned `safe_httpx_client`, blocking loopback, private, link-local, metadata (`169.254.169.254`), and non-HTTP schemes across redirects.
- **SERP scraping opt-in**: Direct HTML SERP scrapers (`duckduckgo`, `startpage`) are disabled by default (`WET_ALLOW_SERP_SCRAPE=false`) so zero-config defaults prefer official/keyless APIs (`tavily`, `keenable`, `firecrawl`). Operators explicitly accept ToS/rate-limit responsibility when enabling `WET_ALLOW_SERP_SCRAPE=true`.
- **BYO credentials & local state**: Provider API keys and local SQLite caches (`~/.wet/`) stay under operator control; keys are never returned in tool payloads or status responses.
