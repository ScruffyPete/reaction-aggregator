import copy
import pytest
from collections.abc import Callable
from pydantic import ValidationError

from app.domain.fact import build_expression_fact
from app.domain.models import DIM_SESSION, FACT_EXPRESSION, Expression
from app.domain.tables import FactTable


# ---------------------------------------------------------------------------
# Fan-out cardinality
# ---------------------------------------------------------------------------

def test_fanout_n_raw_reactions_k_expressions(
    session_dimensions: dict,
    make_raw_reaction: Callable,
) -> None:
    """N raw reactions × K expressions → N*K rows."""
    k = 5
    scores = {f"expr_{i}": 0.1 * i for i in range(k)}
    raw_reactions = [
        make_raw_reaction(timestamp_ms=t, scores=scores)
        for t in range(3)
    ]
    dimensions = session_dimensions
    result = build_expression_fact(dimensions, raw_reactions)

    assert len(result.rows) == 3 * k


def test_all_rows_of_one_raw_reaction_share_metadata(
    session_dimensions: dict,
    make_raw_reaction: Callable,
) -> None:
    """All rows produced from a single raw reaction share timestamp, channel, session_id."""
    scores = {"expr_a": 0.1, "expr_b": 0.2, "expr_c": 0.3}
    dimensions = session_dimensions
    result = build_expression_fact(dimensions, [make_raw_reaction(timestamp_ms=42, channel="voice", scores=scores)])

    assert len(result.rows) == 3
    for row in result.rows:
        assert isinstance(row, Expression)
        assert row.timestamp == 42
        assert row.channel == "voice"
        assert row.session_id == "s1"


def test_full_48_expression_vector(
    session_dimensions: dict,
    make_raw_reaction: Callable,
) -> None:
    """Spot-check a full ~48-expression vector on one raw reaction."""
    n = 48
    scores = {f"expression_{i:02d}": round(i / n, 4) for i in range(n)}
    dimensions = session_dimensions
    result = build_expression_fact(dimensions, [make_raw_reaction(scores=scores)])

    assert len(result.rows) == n
    expression_names = {row.expression for row in result.rows}
    assert expression_names == set(scores.keys())


# ---------------------------------------------------------------------------
# Denormalization
# ---------------------------------------------------------------------------

def test_denormalization_viewer_and_creative_from_dim(
    make_session: Callable,
    make_session_dimensions: Callable,
    make_raw_reaction: Callable,
) -> None:
    """viewer_id and creative_id are pulled from dim_session, not raw input."""
    dimensions = make_session_dimensions([
        make_session(session_id="s1", viewer_id="viewer-xyz", creative_id="creative-abc"),
    ])
    raw = [make_raw_reaction(session_id="s1", scores={"expr": 0.5})]
    result = build_expression_fact(dimensions, raw)

    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.viewer_id == "viewer-xyz"
    assert row.creative_id == "creative-abc"


# ---------------------------------------------------------------------------
# Timestamp passthrough
# ---------------------------------------------------------------------------

def test_timestamp_passthrough(
    session_dimensions: dict,
    make_raw_reaction: Callable,
) -> None:
    """Entity timestamp equals raw timestamp_ms, unchanged."""
    dimensions = session_dimensions
    raw = [make_raw_reaction(timestamp_ms=99999, scores={"expr": 0.0})]
    result = build_expression_fact(dimensions, raw)

    assert result.rows[0].timestamp == 99999


# ---------------------------------------------------------------------------
# Both channels
# ---------------------------------------------------------------------------

def test_both_channels_behave_identically(
    session_dimensions: dict,
    make_raw_reaction: Callable,
) -> None:
    """face and voice channels both produce rows following the same rules."""
    scores = {"expr_x": 0.7}
    dimensions = session_dimensions
    face_result = build_expression_fact(dimensions, [make_raw_reaction(channel="face", scores=scores)])
    voice_result = build_expression_fact(dimensions, [make_raw_reaction(channel="voice", scores=scores)])

    assert len(face_result.rows) == 1
    assert face_result.rows[0].channel == "face"

    assert len(voice_result.rows) == 1
    assert voice_result.rows[0].channel == "voice"


# ---------------------------------------------------------------------------
# Missing dim_session → ValueError
# ---------------------------------------------------------------------------

def test_missing_dim_session_raises(make_raw_reaction: Callable) -> None:
    with pytest.raises(ValueError, match="dim_session"):
        build_expression_fact({}, [make_raw_reaction(scores={"e": 0.5})])


# ---------------------------------------------------------------------------
# Unknown session_id in raw → ValueError
# ---------------------------------------------------------------------------

def test_unknown_session_id_raises(
    session_dimensions: dict,
    make_raw_reaction: Callable,
) -> None:
    dimensions = session_dimensions  # only has session_id "s1"
    with pytest.raises(ValueError, match="session_id"):
        build_expression_fact(dimensions, [make_raw_reaction(session_id="unknown-session", scores={"e": 0.5})])


# ---------------------------------------------------------------------------
# Missing/None required fields → ValueError
# ---------------------------------------------------------------------------

def test_missing_timestamp_ms_raises(session_dimensions: dict) -> None:
    dimensions = session_dimensions
    raw = [{"session_id": "s1", "channel": "face", "scores": {"e": 0.5}}]
    with pytest.raises(ValueError, match="timestamp_ms"):
        build_expression_fact(dimensions, raw)


def test_none_timestamp_ms_raises(session_dimensions: dict) -> None:
    dimensions = session_dimensions
    raw = [{"session_id": "s1", "timestamp_ms": None, "channel": "face", "scores": {"e": 0.5}}]
    with pytest.raises(ValueError, match="timestamp_ms"):
        build_expression_fact(dimensions, raw)


def test_missing_session_id_raises(session_dimensions: dict) -> None:
    dimensions = session_dimensions
    raw = [{"timestamp_ms": 100, "channel": "face", "scores": {"e": 0.5}}]
    with pytest.raises(ValueError, match="session_id"):
        build_expression_fact(dimensions, raw)


def test_none_session_id_raises(session_dimensions: dict) -> None:
    dimensions = session_dimensions
    raw = [{"session_id": None, "timestamp_ms": 100, "channel": "face", "scores": {"e": 0.5}}]
    with pytest.raises(ValueError, match="session_id"):
        build_expression_fact(dimensions, raw)


def test_missing_channel_raises(session_dimensions: dict) -> None:
    dimensions = session_dimensions
    raw = [{"session_id": "s1", "timestamp_ms": 100, "scores": {"e": 0.5}}]
    with pytest.raises(ValueError, match="channel"):
        build_expression_fact(dimensions, raw)


def test_none_channel_raises(session_dimensions: dict) -> None:
    dimensions = session_dimensions
    raw = [{"session_id": "s1", "timestamp_ms": 100, "channel": None, "scores": {"e": 0.5}}]
    with pytest.raises(ValueError, match="channel"):
        build_expression_fact(dimensions, raw)


# ---------------------------------------------------------------------------
# Empty/absent scores → zero rows for that raw reaction, others unaffected
# ---------------------------------------------------------------------------

def test_empty_scores_yields_zero_rows(
    session_dimensions: dict,
    make_raw_reaction: Callable,
) -> None:
    dimensions = session_dimensions
    raw = [make_raw_reaction(scores={})]
    result = build_expression_fact(dimensions, raw)
    assert len(result.rows) == 0


def test_absent_scores_yields_zero_rows(session_dimensions: dict) -> None:
    dimensions = session_dimensions
    raw = [{"session_id": "s1", "timestamp_ms": 100, "channel": "face"}]
    result = build_expression_fact(dimensions, raw)
    assert len(result.rows) == 0


def test_absent_scores_does_not_affect_other_raw_reactions(
    session_dimensions: dict,
    make_raw_reaction: Callable,
) -> None:
    dimensions = session_dimensions
    raw = [
        {"session_id": "s1", "timestamp_ms": 100, "channel": "face"},  # no scores
        make_raw_reaction(timestamp_ms=200, scores={"expr": 0.5}),
    ]
    result = build_expression_fact(dimensions, raw)
    assert len(result.rows) == 1
    assert result.rows[0].timestamp == 200


def test_none_scores_yields_zero_rows(
    session_dimensions: dict,
    make_raw_reaction: Callable,
) -> None:
    dimensions = session_dimensions
    raw = [make_raw_reaction(scores=None)]
    result = build_expression_fact(dimensions, raw)
    assert len(result.rows) == 0


# ---------------------------------------------------------------------------
# Grain dedup: first occurrence wins
# ---------------------------------------------------------------------------

def test_grain_dedup_first_score_wins(
    session_dimensions: dict,
    make_raw_reaction: Callable,
) -> None:
    """Two raw reactions with same (session_id, timestamp, channel) and overlapping expression → first score wins."""
    dimensions = session_dimensions
    raw = [
        make_raw_reaction(timestamp_ms=500, channel="face", scores={"expr_a": 0.3, "expr_b": 0.4}),
        make_raw_reaction(timestamp_ms=500, channel="face", scores={"expr_a": 0.9, "expr_c": 0.1}),
    ]
    result = build_expression_fact(dimensions, raw)

    rows_by_expr = {row.expression: row.score for row in result.rows}
    # expr_a: first occurrence wins → 0.3
    assert rows_by_expr["expr_a"] == pytest.approx(0.3)
    # expr_b: only in first → survives
    assert rows_by_expr["expr_b"] == pytest.approx(0.4)
    # expr_c: only in second → survives
    assert rows_by_expr["expr_c"] == pytest.approx(0.1)
    assert len(result.rows) == 3


def test_grain_dedup_different_timestamps_no_dedup(
    session_dimensions: dict,
    make_raw_reaction: Callable,
) -> None:
    """Same session and channel but different timestamps → no dedup, all rows kept."""
    dimensions = session_dimensions
    raw = [
        make_raw_reaction(timestamp_ms=100, channel="face", scores={"expr": 0.2}),
        make_raw_reaction(timestamp_ms=200, channel="face", scores={"expr": 0.8}),
    ]
    result = build_expression_fact(dimensions, raw)
    assert len(result.rows) == 2


def test_grain_dedup_different_channels_no_dedup(
    session_dimensions: dict,
    make_raw_reaction: Callable,
) -> None:
    """Same session, timestamp, expression but different channels → no dedup."""
    dimensions = session_dimensions
    raw = [
        make_raw_reaction(timestamp_ms=100, channel="face", scores={"expr": 0.2}),
        make_raw_reaction(timestamp_ms=100, channel="voice", scores={"expr": 0.8}),
    ]
    result = build_expression_fact(dimensions, raw)
    assert len(result.rows) == 2


# ---------------------------------------------------------------------------
# Score out of bounds → validation error
# ---------------------------------------------------------------------------

def test_score_out_of_bounds_raises(
    session_dimensions: dict,
    make_raw_reaction: Callable,
) -> None:
    dimensions = session_dimensions
    raw = [make_raw_reaction(scores={"expr": 1.5})]
    with pytest.raises(ValidationError, match="less than or equal"):
        build_expression_fact(dimensions, raw)


def test_score_below_zero_raises(
    session_dimensions: dict,
    make_raw_reaction: Callable,
) -> None:
    dimensions = session_dimensions
    raw = [make_raw_reaction(scores={"expr": -0.1})]
    with pytest.raises(ValidationError, match="greater than or equal"):
        build_expression_fact(dimensions, raw)


# ---------------------------------------------------------------------------
# Invalid channel → validation error (Literal["face", "voice"])
# ---------------------------------------------------------------------------

def test_invalid_channel_raises(
    session_dimensions: dict,
    make_raw_reaction: Callable,
) -> None:
    dimensions = session_dimensions
    raw = [make_raw_reaction(channel="wink", scores={"expr": 0.5})]
    with pytest.raises(ValidationError):
        build_expression_fact(dimensions, raw)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_determinism_same_input_same_output(
    session_dimensions: dict,
    make_raw_reaction: Callable,
) -> None:
    """Same input twice → identical FactTable content."""
    dimensions = session_dimensions
    scores = {f"expr_{i}": 0.01 * i for i in range(10)}
    raw = [make_raw_reaction(scores=scores)]

    result1 = build_expression_fact(dimensions, raw)
    result2 = build_expression_fact(dimensions, raw)

    assert len(result1.rows) == len(result2.rows)
    for r1, r2 in zip(result1.rows, result2.rows):
        assert r1 == r2


# ---------------------------------------------------------------------------
# Empty raw_reactions
# ---------------------------------------------------------------------------

def test_empty_raw_reactions_returns_empty_fact_table(
    session_dimensions: dict,
) -> None:
    dimensions = session_dimensions
    result = build_expression_fact(dimensions, [])

    assert isinstance(result, FactTable)
    assert result.name == FACT_EXPRESSION
    assert result.grain == ("session_id", "timestamp", "channel", "expression")
    assert result.rows == ()


# ---------------------------------------------------------------------------
# Metadata correctness
# ---------------------------------------------------------------------------

def test_fact_table_metadata(
    session_dimensions: dict,
    make_raw_reaction: Callable,
) -> None:
    dimensions = session_dimensions
    result = build_expression_fact(dimensions, [make_raw_reaction(scores={"e": 0.5})])

    assert result.name == FACT_EXPRESSION
    assert result.grain == ("session_id", "timestamp", "channel", "expression")


# ---------------------------------------------------------------------------
# Purity: build_expression_fact does not mutate inputs
# ---------------------------------------------------------------------------

def test_purity_inputs_not_mutated(
    session_dimensions: dict,
    make_raw_reaction: Callable,
) -> None:
    dimensions = session_dimensions
    scores = {"expr_a": 0.1, "expr_b": 0.2}
    raw = [make_raw_reaction(scores=scores)]

    original_dimensions = copy.deepcopy(dimensions)
    original_raw = copy.deepcopy(raw)

    build_expression_fact(dimensions, raw)

    # dimensions unchanged
    assert len(dimensions) == len(original_dimensions)
    assert (
        dimensions[DIM_SESSION].rows[0].session_id
        == original_dimensions[DIM_SESSION].rows[0].session_id
    )

    # raw unchanged
    assert raw[0] == original_raw[0]


# ---------------------------------------------------------------------------
# Multiple sessions / viewer denormalization correctness across sessions
# ---------------------------------------------------------------------------

def test_multiple_sessions_correct_denormalization(
    make_session: Callable,
    make_session_dimensions: Callable,
    make_raw_reaction: Callable,
) -> None:
    dimensions = make_session_dimensions([
        make_session(session_id="s1", viewer_id="v1", creative_id="c1"),
        make_session(session_id="s2", viewer_id="v2", creative_id="c2"),
    ])
    raw = [
        make_raw_reaction(session_id="s1", timestamp_ms=100, scores={"e": 0.1}),
        make_raw_reaction(session_id="s2", timestamp_ms=100, scores={"e": 0.2}),
    ]
    result = build_expression_fact(dimensions, raw)

    assert len(result.rows) == 2
    by_session = {row.session_id: row for row in result.rows}
    assert by_session["s1"].viewer_id == "v1"
    assert by_session["s1"].creative_id == "c1"
    assert by_session["s2"].viewer_id == "v2"
    assert by_session["s2"].creative_id == "c2"
