"""Regression tests for the silent semantic-degrade bug.

When a cloud provider rejects the requested output ``dimensions`` (e.g.
``cohere/embed-v4.0`` at wet's default 768; cohere-v4 supports only
{256, 512, 1024, 1536}), the hull OpenAI-spec client wraps the provider's
HTTP 422 in a :class:`~hull_core.providers.openai_spec.ProviderError` whose
text embeds the status and body verbatim. A naive retryability check that
matched on "connection" or a 5xx status would misclassify that shape, so the
dimensions-fallback would be bypassed, the call retried 3x with the SAME
rejected dims, then give up -> ``_embed`` returned None -> semantic search
silently degraded to keyword search with no error surfaced.

These tests reproduce that exact shape (ProviderError, dims-aware client
stub) and lock in the fix: unsupported-dimensions recover via
retry-without-dims + local truncate, and permanent client errors are never
retried.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hull_core.providers.openai_spec import ProviderError

from wet_mcp.embedder import MAX_RETRIES, CloudEmbeddingBackend, _is_retryable

# The exact provider body cohere returns for an unsupported output_dimension,
# as the hull client surfaces it inside ProviderError.
_COHERE_422_BODY = (
    '{"message": "768 is not a valid output_dimension, '
    'use one of 256, 512, 1024, 1536"}'
)


def _wrapped_422() -> ProviderError:
    """A ProviderError wrapping cohere's 422 dims rejection."""
    return ProviderError(status=422, detail=_COHERE_422_BODY)


def _stub_client(model: str = "cohere/embed-v4.0") -> MagicMock:
    """A stub OpenAI-spec client: ``embeddings`` async, ``cell.model`` reads."""
    client = MagicMock()
    client.cell.model = model
    client.embeddings = AsyncMock()
    return client


class TestIsRetryableClassification:
    """`_is_retryable` must classify on error semantics, not class name."""

    def test_422_unsupported_dimension_is_not_retryable(self):
        exc = _wrapped_422()
        # Guard: this really is the tricky shape — the provider body names
        # "output_dimension" while the status reads as a generic 4xx, and the
        # wrapping class name ("ProviderError") must not decide alone.
        assert "output_dimension" in str(exc).lower()
        assert exc.status == 422

        assert _is_retryable(exc) is False

    def test_genuine_connection_error_is_retryable(self):
        exc = ProviderError(
            status=502, detail="connection error while contacting provider"
        )
        assert _is_retryable(exc) is True

    def test_timeout_is_retryable(self):
        exc = ProviderError(status=504, detail="request timed out")
        assert _is_retryable(exc) is True

    def test_rate_limit_is_retryable(self):
        exc = ProviderError(
            status=429,
            detail='{"message": "rate limit exceeded"}',
        )
        assert _is_retryable(exc) is True

    def test_invalid_api_key_is_not_retryable(self):
        exc = ProviderError(
            status=401,
            detail='{"message": "invalid api key: authentication failed"}',
        )
        assert _is_retryable(exc) is False


class TestWrappedDimsRejectionRecovery:
    """The wrapped 422 must trigger the retry-without-dims fallback."""

    async def test_wrapped_422_triggers_dims_fallback_and_truncates(self):
        # Dims-aware fake: the provider REJECTS every dims-bearing call (as
        # cohere-v4 does at 768) and only succeeds when dims are dropped.
        # A non-dims-aware mock would let the buggy retry "recover" by luck and
        # hide the defect.
        native_dim = 1536
        client = _stub_client()

        async def fake_embeddings(texts, dimensions=None, **extra):
            if dimensions is not None:
                raise _wrapped_422()
            return [[0.1] * native_dim for _ in texts]

        client.embeddings = AsyncMock(side_effect=fake_embeddings)
        backend = CloudEmbeddingBackend(client)
        with patch.object(
            backend, "_client", client
        ):
            result = await backend._embed_batch_inner(["hello"], dimensions=768)

        # Recovered: valid vector truncated locally to the requested 768.
        assert len(result[0]) == 768
        assert result[0] == [0.1] * 768
        # Exactly two provider calls: dims=768 (rejected) then dims=None (ok).
        assert client.embeddings.call_count == 2
        assert client.embeddings.call_args_list[0].kwargs["dimensions"] == 768
        assert client.embeddings.call_args_list[1].kwargs["dimensions"] is None

    async def test_wrapped_422_is_not_retried_with_same_dims(self):
        # If the fallback did NOT fire, the buggy code would retry MAX_RETRIES
        # times with the same rejected dims. Assert it does NOT.
        client = _stub_client()

        async def always_reject(texts, dimensions=None, **extra):
            raise _wrapped_422()

        client.embeddings = AsyncMock(side_effect=always_reject)
        backend = CloudEmbeddingBackend(client)

        with pytest.raises(ProviderError):
            await backend._embed_batch_inner(["hello"], dimensions=768)

        # 1 dims=768 attempt (rejected) + 1 dims=None fallback attempt (also
        # rejected) = 2. NOT MAX_RETRIES retries of the same bad dims.
        assert client.embeddings.call_count == 2
        assert client.embeddings.call_count < MAX_RETRIES + 1
        assert client.embeddings.call_args_list[0].kwargs["dimensions"] == 768
        assert client.embeddings.call_args_list[1].kwargs["dimensions"] is None
