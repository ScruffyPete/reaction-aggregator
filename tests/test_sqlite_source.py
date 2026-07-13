"""Tests for app.adapters.sqlite_source.SQLiteSource — session scoping, parsed scores, raw shape, and error cases."""
from __future__ import annotations

import sqlite3

import pytest

import app.seed as seed_module
from app.adapters.sqlite_source import SQLiteSource
from app.domain.ports.source import SourceDescriptor
from app.seed import CREATIVES, EXPRESSION_NAMES


# ---------------------------------------------------------------------------
# Module-local fixtures — used only within this module
# ---------------------------------------------------------------------------

@pytest.fixture()
def make_seeded_source_path(tmp_path):
    """Factory fixture: call _make(session_ids, duration_ms) to get a seeded source db path."""

    def _make(session_ids: list[str], duration_ms: int = 1000) -> str:
        path = str(tmp_path / "source.db")
        for session_id in session_ids:
            seed_module.seed_source(path, session_id, duration_ms=duration_ms)
        return path

    return _make


@pytest.fixture()
def seeded_source_path(make_seeded_source_path) -> str:
    """Plain fixture: a source db seeded with session id 's1'."""
    return make_seeded_source_path(["s1"])


# ---------------------------------------------------------------------------
# Session scoping
# ---------------------------------------------------------------------------

def test_session_fetch_returns_only_the_requested_session(make_seeded_source_path) -> None:
    path = make_seeded_source_path(["s1", "s2"])
    source = SQLiteSource(path, "s1")

    rows = source.fetch(SourceDescriptor.SESSION)

    assert len(rows) == 1
    assert rows[0]["id"] == "s1"


def test_viewer_fetch_returns_only_the_viewer_for_the_requested_session(make_seeded_source_path) -> None:
    path = make_seeded_source_path(["s1", "s2"])
    source = SQLiteSource(path, "s1")

    rows = source.fetch(SourceDescriptor.VIEWER)

    assert len(rows) == 1
    assert rows[0]["id"] == "viewer-s1"


def test_reactions_fetch_returns_only_rows_for_the_requested_session(make_seeded_source_path) -> None:
    path = make_seeded_source_path(["s1", "s2"])
    source = SQLiteSource(path, "s1")

    rows = source.fetch(SourceDescriptor.REACTIONS)

    assert len(rows) > 0
    for row in rows:
        assert row["session_id"] == "s1"


# ---------------------------------------------------------------------------
# REACTIONS scores parsed to dict
# ---------------------------------------------------------------------------

def test_reactions_scores_are_parsed_to_dict_of_floats(seeded_source_path) -> None:
    source = SQLiteSource(seeded_source_path, "s1")

    rows = source.fetch(SourceDescriptor.REACTIONS)

    assert len(rows) > 0
    for row in rows:
        scores = row["scores"]
        assert isinstance(scores, dict), "scores must be a dict, not a string"
        assert len(scores) == 48
        assert set(scores.keys()) == set(EXPRESSION_NAMES)
        for value in scores.values():
            assert isinstance(value, float)


# ---------------------------------------------------------------------------
# Raw row shape (dict keys match source columns)
# ---------------------------------------------------------------------------

def test_viewer_rows_have_source_column_keys(seeded_source_path) -> None:
    source = SQLiteSource(seeded_source_path, "s1")

    rows = source.fetch(SourceDescriptor.VIEWER)

    assert len(rows) == 1
    assert set(rows[0].keys()) == {"id", "age_bracket", "gender", "country_code"}


def test_fetch_for_session_never_seeded_returns_empty_lists(make_seeded_source_path) -> None:
    path = make_seeded_source_path(["s1"])
    source = SQLiteSource(path, "unknown-session")

    assert source.fetch(SourceDescriptor.SESSION) == []
    assert source.fetch(SourceDescriptor.VIEWER) == []
    assert source.fetch(SourceDescriptor.REACTIONS) == []


# ---------------------------------------------------------------------------
# Missing source file raises at construction or first fetch
# ---------------------------------------------------------------------------

def test_missing_source_file_raises_operational_error(tmp_path) -> None:
    missing_path = str(tmp_path / "missing.db")

    with pytest.raises(sqlite3.OperationalError):
        source = SQLiteSource(missing_path, "s1")
        source.fetch(SourceDescriptor.SESSION)


# ---------------------------------------------------------------------------
# Creative scoping
# ---------------------------------------------------------------------------

def test_creative_fetch_returns_only_the_creative_for_the_requested_session(make_seeded_source_path) -> None:
    path = make_seeded_source_path(["s1", "s2"])
    source = SQLiteSource(path, "s1")

    rows = source.fetch(SourceDescriptor.CREATIVE)

    with sqlite3.connect(path) as connection:
        creative_id_for_s1 = connection.execute(
            "SELECT creative_id FROM sessions WHERE id = ?", ("s1",)
        ).fetchone()[0]

    assert len(rows) == 1
    assert rows[0]["id"] == creative_id_for_s1
    assert rows[0]["id"] in {creative_id for creative_id, _, _ in CREATIVES}


# ---------------------------------------------------------------------------
# Score range invariant
# ---------------------------------------------------------------------------

def test_reactions_scores_are_within_zero_and_one(seeded_source_path) -> None:
    source = SQLiteSource(seeded_source_path, "s1")

    rows = source.fetch(SourceDescriptor.REACTIONS)

    assert len(rows) > 0
    for row in rows:
        for value in row["scores"].values():
            assert 0.0 <= value <= 1.0
