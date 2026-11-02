1. Edit `src/wet/sources/docs.py` to extract `_is_github_url(url)` to slice the URL manually inside `_url_host`.
2. Wait, the previous benchmark for URL slicing in `_url_host` yielded a measurable ~20% speedup, avoiding `urlparse` allocations for the vast majority of URLs (HTTP(S) and git+https). This is a purely CPU-bound hot path in `discover_library` loops. I will implement this manual string slicing optimization in `_url_host`.
3. Complete pre-commit steps.
4. Submit.
