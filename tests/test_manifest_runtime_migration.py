"""Release manifest and local-runtime migration contracts."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import numpy as np
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _job_block(workflow: str, job: str) -> str:
    lines = workflow.splitlines()
    start = lines.index(f"  {job}:")
    for offset, line in enumerate(lines[start + 1 :], start=start + 1):
        if line.startswith("  ") and line.endswith(":") and not line.startswith("    "):
            return "\n".join(lines[start:offset])
    return "\n".join(lines[start:])


def _project_metadata() -> dict:
    return tomllib.loads(_read("pyproject.toml"))


def _locked_package(name: str) -> dict:
    lock = tomllib.loads(_read("uv.lock"))
    return next(package for package in lock["package"] if package["name"] == name)


def test_registry_description_matches_project_and_is_at_most_100_characters():
    manifest = json.loads(_read("server.json"))
    project = _project_metadata()["project"]

    assert manifest["description"] == project["description"]
    assert 0 < len(manifest["description"]) <= 100


def test_mcp_registry_validates_manifest_before_login_and_publish():
    registry_job = _job_block(_read(".github/workflows/cd.yml"), "publish-mcp-registry")

    validate_at = registry_job.index("./mcp-publisher validate server.json")
    login_at = registry_job.index("./mcp-publisher login github-oidc")
    publish_at = registry_job.index("./mcp-publisher publish")

    assert validate_at < login_at
    assert validate_at < publish_at


def test_dependency_specs_and_lock_use_stable_fastretrieval():
    project = _project_metadata()["project"]
    dependencies = project["dependencies"]

    assert "fastretrieval>=1.1.0,<2" in dependencies
    locked_fr = Version(_locked_package("fastretrieval")["version"])
    assert locked_fr >= Version("1.1.0"), locked_fr
    assert locked_fr < Version("2"), locked_fr


async def test_local_embedding_uses_fastretrieval_output_contract(monkeypatch):
    from wet_mcp.embedder import LocalEmbeddingBackend

    calls: dict[str, object] = {}

    class FakeEmbedding:
        def embed(self, texts, **kwargs):
            calls["texts"] = texts
            calls["kwargs"] = kwargs
            return iter([np.array([0.1, 0.2])])

    backend = LocalEmbeddingBackend("stable-model")
    monkeypatch.setattr(backend, "_get_model", lambda: FakeEmbedding())

    vectors = await backend.embed_texts(["document"], dimensions=2)

    assert vectors == [[0.1, 0.2]]
    assert calls == {"texts": ["document"], "kwargs": {"dim": 2}}


def test_local_reranker_uses_fastretrieval_score_contract(monkeypatch):
    from wet_mcp.reranker import LocalReranker

    class FakeCrossEncoder:
        def rerank(self, query, documents):
            assert query == "query"
            assert documents == ["low", "high"]
            return iter([0.1, 0.9])

    reranker = LocalReranker("stable-model")
    monkeypatch.setattr(reranker, "_get_model", lambda: FakeCrossEncoder())

    assert reranker.rerank("query", ["low", "high"], top_n=2) == [
        (1, 0.9),
        (0, 0.1),
    ]


def test_legacy_qwen_cache_variable_does_not_select_cache(tmp_path, monkeypatch):
    from wet_mcp.setup_tool import clear_model_cache

    legacy_dir = tmp_path / "legacy"
    active_dir = tmp_path / "xdg" / "fastretrieval"
    legacy_model = legacy_dir / "models--org--model"
    active_model = active_dir / "models--org--model"
    legacy_model.mkdir(parents=True)
    active_model.mkdir(parents=True)

    monkeypatch.delenv("FASTRETRIEVAL_CACHE_PATH", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("QWEN3_EMBED_CACHE_PATH", str(legacy_dir))

    result = clear_model_cache("org/model")

    assert result == str(active_model)
    assert not active_model.exists()
    assert legacy_model.exists()
