"""Host name normalisation shared by the extract breaker and source exclusion.

Two spellings of one host must compare equal, otherwise a trailing dot, a
Unicode spelling or an uncompressed IPv6 literal slips past an exclusion or
splits one host's failures across several breaker entries.
"""

from __future__ import annotations

import ipaddress

import idna


def normalize_host(host: str) -> str:
    """Canonical form of a URL host name (as ``urlsplit(...).hostname`` gives it).

    IPv6 literals are compressed and bracketed, so a port suffix cannot be
    mistaken for part of the address. Names are mapped the way browsers map
    them (UTS #46: case folding, full-width forms, ideographic dots), the
    trailing dot is dropped and non-ASCII labels are punycode-encoded.
    Labels IDNA cannot encode are kept as they are, lower-cased.
    """
    if not host:
        return ""
    if ":" in host:
        try:
            return f"[{ipaddress.IPv6Address(host).compressed}]"
        except ValueError:
            return f"[{host.lower()}]"
    try:
        mapped = idna.uts46_remap(host, std3_rules=False, transitional=False)
    except idna.IDNAError:
        mapped = host.lower()
    labels = mapped.rstrip(".").split(".")
    return ".".join(_ascii_label(label) for label in labels)


def _ascii_label(label: str) -> str:
    if label.isascii():
        return label
    try:
        return idna.alabel(label).decode("ascii")
    except idna.IDNAError:
        return label
