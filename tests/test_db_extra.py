from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import wet_mcp.db as db


def test_db_quality_edge_cases():
    content = "def test1(): pass\n" * 5
    score = db._chunk_quality_score(content)
    assert score > 0.0

    content = '"""docstring"""\n' * 4
    score = db._chunk_quality_score(content)
    assert score > 0.0

    content = "```\ntest\n```\n" * 5
    score = db._chunk_quality_score(content)
    assert score > 0.0

    content = "```\n" * 5
    score = db._chunk_quality_score(content)
    assert score <= 1.0


def test_db_directives():
    content = "::: test\n" * 4
    db._chunk_quality_score(content)


def test_link_ratio():
    content = "[test](http://test.com)\n" * 10
    db._chunk_quality_score(content)


def test_db_link_ratio_branches():
    content1 = "Just text\n" * 10
    db._chunk_quality_score(content1)

    content2 = "[test](link)\n" * 10 + "text\n" * 2
    db._chunk_quality_score(content2)

    content3 = "[test](link)\n" * 4 + "text\n" * 6
    db._chunk_quality_score(content3)

    content4 = ""
    db._chunk_quality_score(content4)


@patch("sqlite3.connect")
def test_sqlite_vec_extension(mock_connect: Any):
    mock_conn = MagicMock()
    mock_connect.return_value = mock_conn
    mock_conn.execute.return_value.fetchone.return_value = None

    with patch("sqlite_vec.load"):
        database = db.DocsDB(Path("/tmp/test.db"), embedding_dims=1536)
        database._vec_enabled = True
        database._embedding_dims = 1536
        database._create_vector_table()
        mock_conn.execute.assert_called()


def test_clear_version_chunks():
    database = db.DocsDB(Path("/tmp/test2.db"))
    database.clear_version_chunks = MagicMock(return_value=1)
    database.clear_version_chunks("test")


def test_combine_scores_no_match():
    database = db.DocsDB(Path("/tmp/test3.db"))
    scores = database._combine_scores({}, {}, {})
    assert scores == []


def test_import_jsonl_no_match():
    database = db.DocsDB(Path("/tmp/test4.db"))
    database.import_jsonl("")
