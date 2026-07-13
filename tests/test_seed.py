"""Tests for app.seed — determinism, idempotency, count formula, and multi-session coexistence."""
from __future__ import annotations

import json
import sqlite3

import pytest

from app.seed import (
    CREATIVES,
    EXPRESSION_NAMES,
    FACE_FRAME_INTERVAL_MS,
    VOICE_INTERVAL_MS,
    seed_source,
)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_same_session_id_produces_identical_reaction_rows(tmp_path) -> None:
    path_a = str(tmp_path / "db_a.db")
    path_b = str(tmp_path / "db_b.db")

    seed_source(path_a, "determinism-session", duration_ms=1000)
    seed_source(path_b, "determinism-session", duration_ms=1000)

    with sqlite3.connect(path_a) as conn_a, sqlite3.connect(path_b) as conn_b:
        rows_a = conn_a.execute(
            "SELECT session_id, timestamp_ms, channel, scores FROM reactions ORDER BY channel, timestamp_ms"
        ).fetchall()
        rows_b = conn_b.execute(
            "SELECT session_id, timestamp_ms, channel, scores FROM reactions ORDER BY channel, timestamp_ms"
        ).fetchall()

    assert rows_a == rows_b


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_reseeding_same_session_does_not_duplicate_rows(tmp_path) -> None:
    path = str(tmp_path / "idempotent.db")

    seed_source(path, "idem-session", duration_ms=1000)
    seed_source(path, "idem-session", duration_ms=1000)

    with sqlite3.connect(path) as connection:
        viewer_count = connection.execute("SELECT COUNT(*) FROM viewers").fetchone()[0]
        creative_count = connection.execute("SELECT COUNT(*) FROM creatives").fetchone()[0]
        session_count = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        reaction_count = connection.execute("SELECT COUNT(*) FROM reactions").fetchone()[0]

    expected_reactions = (
        len(range(0, 1000, FACE_FRAME_INTERVAL_MS))
        + len(range(0, 1000, VOICE_INTERVAL_MS))
    )
    assert viewer_count == 1
    assert creative_count == 1
    assert session_count == 1
    assert reaction_count == expected_reactions


# ---------------------------------------------------------------------------
# Count formula and score shape
# ---------------------------------------------------------------------------

def test_reaction_count_matches_formula_for_duration_1000(tmp_path) -> None:
    path = str(tmp_path / "count.db")
    duration_ms = 1000

    seed_source(path, "count-session", duration_ms=duration_ms)

    expected_count = (
        len(range(0, duration_ms, FACE_FRAME_INTERVAL_MS))
        + len(range(0, duration_ms, VOICE_INTERVAL_MS))
    )
    assert expected_count == 35

    with sqlite3.connect(path) as connection:
        actual_count = connection.execute("SELECT COUNT(*) FROM reactions").fetchone()[0]
        assert actual_count == 35


def test_every_reaction_scores_json_has_all_48_expression_names(tmp_path) -> None:
    path = str(tmp_path / "scores.db")

    seed_source(path, "scores-session", duration_ms=1000)

    with sqlite3.connect(path) as connection:
        raw_scores_rows = connection.execute("SELECT scores FROM reactions").fetchall()

    assert len(raw_scores_rows) == 35
    for (scores_text,) in raw_scores_rows:
        scores = json.loads(scores_text)
        assert set(scores.keys()) == set(EXPRESSION_NAMES)
        assert len(scores) == 48
        for value in scores.values():
            assert isinstance(value, float)
            assert 0.0 <= value <= 1.0


# ---------------------------------------------------------------------------
# Multi-session coexistence
# ---------------------------------------------------------------------------

def test_two_different_sessions_coexist_without_overlap(tmp_path) -> None:
    path = str(tmp_path / "multi.db")

    seed_source(path, "alpha", duration_ms=1000)
    seed_source(path, "beta", duration_ms=1000)

    with sqlite3.connect(path) as connection:
        session_count = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        viewer_count = connection.execute("SELECT COUNT(*) FROM viewers").fetchone()[0]

        alpha_reactions = connection.execute(
            "SELECT COUNT(*) FROM reactions WHERE session_id = ?", ("alpha",)
        ).fetchone()[0]
        beta_reactions = connection.execute(
            "SELECT COUNT(*) FROM reactions WHERE session_id = ?", ("beta",)
        ).fetchone()[0]

    expected_reactions_per_session = (
        len(range(0, 1000, FACE_FRAME_INTERVAL_MS))
        + len(range(0, 1000, VOICE_INTERVAL_MS))
    )
    assert session_count == 2
    assert viewer_count == 2
    assert alpha_reactions == expected_reactions_per_session
    assert beta_reactions == expected_reactions_per_session


def test_five_sessions_draw_creatives_from_the_fixed_pool(tmp_path) -> None:
    path = str(tmp_path / "shared_creatives.db")

    for session_id in ("s1", "s2", "s3", "s4", "s5"):
        seed_source(path, session_id, duration_ms=1000)

    with sqlite3.connect(path) as connection:
        session_count = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        creative_ids = {
            row[0] for row in connection.execute("SELECT id FROM creatives").fetchall()
        }

    assert session_count == 5
    assert len(creative_ids) <= len(CREATIVES)
    assert creative_ids <= {creative_id for creative_id, _, _ in CREATIVES}
