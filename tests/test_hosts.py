"""Host name normalisation shared by the extract breaker and source exclusion."""

from __future__ import annotations

import pytest

from wet.sources.hosts import normalize_host


@pytest.mark.parametrize(
    "host,expected",
    [
        ("Example.COM", "example.com"),
        ("example.com.", "example.com"),
        ("example.com..", "example.com"),
        # IPv6 literals: compressed and bracketed, so a port suffix is unambiguous.
        ("::1", "[::1]"),
        ("0:0::1", "[::1]"),
        ("::1:8080", "[::1:8080]"),
        ("FE80::A", "[fe80::a]"),
        # An IP-literal that is not IPv6 (IPvFuture) is still bracketed.
        ("v1.Fe:80", "[v1.fe:80]"),
        # IDN and punycode spellings of one host collapse to the punycode form.
        ("bücher.example", "xn--bcher-kva.example"),
        ("BÜCHER.example.", "xn--bcher-kva.example"),
        ("XN--BCHER-KVA.example", "xn--bcher-kva.example"),
        ("faß.de", "xn--fa-hia.de"),
        ("xn--fa-hia.de", "xn--fa-hia.de"),
        # Full-width forms and ideographic dots map the way browsers map them.
        ("ｂａｄ.example", "bad.example"),
        ("bad。example", "bad.example"),
        # ASCII labels IDNA would reject are kept, not dropped.
        ("my_host.example", "my_host.example"),
        ("127.0.0.1", "127.0.0.1"),
        ("", ""),
        (".", ""),
    ],
)
def test_normalize_host(host, expected):
    assert normalize_host(host) == expected


def test_normalize_host_keeps_names_idna_cannot_encode():
    # U+FFFD is not a valid IDNA code point; the name is kept lower-cased.
    assert normalize_host("X�Y.Example") == "x�y.example"
    # A non-ASCII label that cannot be encoded stays as it is.
    assert normalize_host("bü_x.example") == "bü_x.example"


def test_normalize_host_is_idempotent():
    for host in ("BÜCHER.example.", "0:0::1", "bad。example"):
        once = normalize_host(host)
        assert normalize_host(once.strip("[]")) == once
