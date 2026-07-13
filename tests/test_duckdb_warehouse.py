"""Tests for app.adapters.duckdb_warehouse.DuckDBWarehouse — table creation, upsert, replace, and atomic rollback."""
from __future__ import annotations

import duckdb
import pytest

from app.adapters.duckdb_warehouse import DuckDBWarehouse
from app.domain.models import (
    DIM_CREATIVE,
    DIM_SESSION,
    DIM_VIEWER,
    FACT_EXPRESSION,
    Creative,
    Expression,
    Session,
    Viewer,
)
from app.domain.tables import DimensionTable, FactTable


# ---------------------------------------------------------------------------
# Module-local fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def warehouse_path(tmp_path) -> str:
    """Plain fixture: path to a not-yet-created DuckDB warehouse file."""
    return str(tmp_path / "warehouse.duckdb")


@pytest.fixture()
def make_viewer_dimension():
    """Factory fixture: call _make(viewers) to build a dim_viewer DimensionTable."""

    def _make(viewers: list[Viewer]) -> DimensionTable:
        return DimensionTable(name=DIM_VIEWER, key="viewer_id", rows=tuple(viewers))

    return _make


@pytest.fixture()
def make_creative_dimension():
    """Factory fixture: call _make(creatives) to build a dim_creative DimensionTable."""

    def _make(creatives: list[Creative]) -> DimensionTable:
        return DimensionTable(name=DIM_CREATIVE, key="creative_id", rows=tuple(creatives))

    return _make


@pytest.fixture()
def make_session_dimension():
    """Factory fixture: call _make(sessions) to build a dim_session DimensionTable."""

    def _make(sessions: list[Session]) -> DimensionTable:
        return DimensionTable(name=DIM_SESSION, key="session_id", rows=tuple(sessions))

    return _make


@pytest.fixture()
def make_expression_fact():
    """Factory fixture: call _make(expressions) to build a fact_expression FactTable."""

    def _make(expressions: list[Expression]) -> FactTable:
        return FactTable(
            name=FACT_EXPRESSION,
            grain=("session_id", "timestamp", "channel", "expression"),
            rows=tuple(expressions),
        )

    return _make


@pytest.fixture()
def make_expressions():
    """Factory fixture: call _make(session_id, viewer_id, creative_id) to get a small expression list."""

    def _make(session_id: str, viewer_id: str, creative_id: str) -> list[Expression]:
        return [
            Expression(
                session_id=session_id,
                viewer_id=viewer_id,
                creative_id=creative_id,
                timestamp=0,
                channel="face",
                expression="joy",
                score=0.8,
            ),
            Expression(
                session_id=session_id,
                viewer_id=viewer_id,
                creative_id=creative_id,
                timestamp=0,
                channel="face",
                expression="anger",
                score=0.1,
            ),
            Expression(
                session_id=session_id,
                viewer_id=viewer_id,
                creative_id=creative_id,
                timestamp=33,
                channel="voice",
                expression="calmness",
                score=0.6,
            ),
        ]

    return _make


@pytest.fixture()
def first_session_batch(
    make_viewer_dimension,
    make_creative_dimension,
    make_session_dimension,
    make_expression_fact,
    make_expressions,
) -> tuple[DimensionTable | FactTable, ...]:
    """Plain fixture: a complete first-session batch for session s1/v1/c1."""
    viewer = Viewer(viewer_id="v1", age_bracket="25-34", gender="f", country="PL")
    creative = Creative(creative_id="c1", title="Spring Launch", brand="Acme", duration_ms=30000)
    session = Session(session_id="s1", viewer_id="v1", creative_id="c1")
    expressions = make_expressions("s1", "v1", "c1")
    return (
        make_viewer_dimension([viewer]),
        make_creative_dimension([creative]),
        make_session_dimension([session]),
        make_expression_fact(expressions),
    )


# ---------------------------------------------------------------------------
# Batch load creates all four tables with correct row counts
# ---------------------------------------------------------------------------

def test_load_creates_all_four_tables_with_expected_counts(warehouse_path, first_session_batch) -> None:
    warehouse = DuckDBWarehouse(warehouse_path)

    warehouse.load(first_session_batch)

    connection = duckdb.connect(warehouse_path, read_only=True)
    try:
        assert connection.execute(f"SELECT COUNT(*) FROM {DIM_CREATIVE}").fetchone()[0] == 1
        assert connection.execute(f"SELECT COUNT(*) FROM {DIM_SESSION}").fetchone()[0] == 1
        assert connection.execute(f"SELECT COUNT(*) FROM {DIM_VIEWER}").fetchone()[0] == 1
        assert connection.execute(f"SELECT COUNT(*) FROM {FACT_EXPRESSION}").fetchone()[0] == 3
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Same-session reload leaves counts unchanged
# ---------------------------------------------------------------------------

def test_same_session_reload_does_not_change_row_counts(warehouse_path, first_session_batch) -> None:
    warehouse = DuckDBWarehouse(warehouse_path)

    warehouse.load(first_session_batch)
    warehouse.load(first_session_batch)

    connection = duckdb.connect(warehouse_path, read_only=True)
    try:
        assert connection.execute(f"SELECT COUNT(*) FROM {DIM_VIEWER}").fetchone()[0] == 1
        assert connection.execute(f"SELECT COUNT(*) FROM {DIM_CREATIVE}").fetchone()[0] == 1
        assert connection.execute(f"SELECT COUNT(*) FROM {DIM_SESSION}").fetchone()[0] == 1
        assert connection.execute(f"SELECT COUNT(*) FROM {FACT_EXPRESSION}").fetchone()[0] == 3
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Second session appends — fact count is the sum, dimension counts grow by one
# ---------------------------------------------------------------------------

def test_second_session_appends_to_fact_and_grows_dimensions(
    warehouse_path,
    first_session_batch,
    make_viewer_dimension,
    make_creative_dimension,
    make_session_dimension,
    make_expression_fact,
    make_expressions,
) -> None:
    warehouse = DuckDBWarehouse(warehouse_path)

    warehouse.load(first_session_batch)

    viewer2 = Viewer(viewer_id="v2", age_bracket="35-44", gender="m", country="US")
    creative2 = Creative(creative_id="c2", title="Summer Splash", brand="Globex", duration_ms=15000)
    session2 = Session(session_id="s2", viewer_id="v2", creative_id="c2")
    expressions2 = make_expressions("s2", "v2", "c2")
    second_batch = (
        make_viewer_dimension([viewer2]),
        make_creative_dimension([creative2]),
        make_session_dimension([session2]),
        make_expression_fact(expressions2),
    )

    warehouse.load(second_batch)

    connection = duckdb.connect(warehouse_path, read_only=True)
    try:
        assert connection.execute(f"SELECT COUNT(*) FROM {DIM_VIEWER}").fetchone()[0] == 2
        assert connection.execute(f"SELECT COUNT(*) FROM {DIM_CREATIVE}").fetchone()[0] == 2
        assert connection.execute(f"SELECT COUNT(*) FROM {DIM_SESSION}").fetchone()[0] == 2
        assert connection.execute(f"SELECT COUNT(*) FROM {FACT_EXPRESSION}").fetchone()[0] == 6  # 3 from s1 + 3 from s2
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Dimension upsert by key — updated attribute, count stays 1
# ---------------------------------------------------------------------------

def test_dimension_upsert_updates_attribute_without_adding_rows(
    warehouse_path,
    make_viewer_dimension,
) -> None:
    warehouse = DuckDBWarehouse(warehouse_path)

    original_viewer = Viewer(viewer_id="v1", age_bracket="25-34", gender="f", country="PL")
    warehouse.load((make_viewer_dimension([original_viewer]),))

    updated_viewer = Viewer(viewer_id="v1", age_bracket="45-54", gender="f", country="PL")
    warehouse.load((make_viewer_dimension([updated_viewer]),))

    connection = duckdb.connect(warehouse_path, read_only=True)
    try:
        assert connection.execute(f"SELECT COUNT(*) FROM {DIM_VIEWER}").fetchone()[0] == 1
        row = connection.execute("SELECT age_bracket FROM dim_viewer WHERE viewer_id = 'v1'").fetchone()
    finally:
        connection.close()

    assert row is not None
    assert row[0] == "45-54"


# ---------------------------------------------------------------------------
# Atomic rollback — failed batch leaves no partial state
# ---------------------------------------------------------------------------

def test_failed_batch_rolls_back_and_leaves_prior_state_intact(
    warehouse_path,
    first_session_batch,
    make_viewer_dimension,
) -> None:
    warehouse = DuckDBWarehouse(warehouse_path)

    # Establish a clean baseline
    warehouse.load(first_session_batch)

    def _read_counts(path: str) -> dict[str, int]:
        conn = duckdb.connect(path, read_only=True)
        try:
            return {
                name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                for name in [DIM_VIEWER, DIM_CREATIVE, DIM_SESSION, FACT_EXPRESSION]
            }
        finally:
            conn.close()

    counts_before = _read_counts(warehouse_path)

    # Build a batch where one table has a key that does not exist as a column on Viewer,
    # which causes CREATE TABLE / schema resolution to fail mid-transaction.
    valid_new_viewer = Viewer(viewer_id="v2", age_bracket="18-24", gender="m", country="DE")
    broken_table = DimensionTable(
        name="dim_broken",
        key="missing_key",
        rows=(Viewer(viewer_id="v-broken"),),
    )
    broken_batch = (
        make_viewer_dimension([valid_new_viewer]),
        broken_table,
    )

    with pytest.raises(Exception):
        warehouse.load(broken_batch)

    counts_after = _read_counts(warehouse_path)

    # The valid new viewer must NOT have landed; the pre-failure counts are preserved exactly.
    assert counts_after.get(DIM_VIEWER) == counts_before.get(DIM_VIEWER)
    assert counts_after.get(DIM_CREATIVE) == counts_before.get(DIM_CREATIVE)
    assert counts_after.get(DIM_SESSION) == counts_before.get(DIM_SESSION)
    assert counts_after.get(FACT_EXPRESSION) == counts_before.get(FACT_EXPRESSION)
    # The broken table itself must not exist at all
    conn = duckdb.connect(warehouse_path, read_only=True)
    try:
        table_names = [
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        ]
    finally:
        conn.close()
    assert "dim_broken" not in table_names


# ---------------------------------------------------------------------------
# Reload with changed fact rows replaces — not appends
# ---------------------------------------------------------------------------

def test_reloading_session_with_changed_fact_rows_replaces_not_appends(
    warehouse_path,
    make_viewer_dimension,
    make_creative_dimension,
    make_session_dimension,
    make_expression_fact,
) -> None:
    warehouse = DuckDBWarehouse(warehouse_path)

    viewer = Viewer(viewer_id="v1", age_bracket="25-34", gender="f", country="PL")
    creative = Creative(creative_id="c1", title="Spring Launch", brand="Acme", duration_ms=30000)
    session = Session(session_id="s1", viewer_id="v1", creative_id="c1")

    # First load: 3 expression rows for s1
    first_expressions = [
        Expression(session_id="s1", viewer_id="v1", creative_id="c1", timestamp=0, channel="face", expression="joy", score=0.8),
        Expression(session_id="s1", viewer_id="v1", creative_id="c1", timestamp=0, channel="face", expression="anger", score=0.1),
        Expression(session_id="s1", viewer_id="v1", creative_id="c1", timestamp=33, channel="voice", expression="calmness", score=0.6),
    ]
    first_batch = (
        make_viewer_dimension([viewer]),
        make_creative_dimension([creative]),
        make_session_dimension([session]),
        make_expression_fact(first_expressions),
    )
    warehouse.load(first_batch)

    # Second load: only 2 rows for the SAME session — different timestamps and expressions
    second_expressions = [
        Expression(session_id="s1", viewer_id="v1", creative_id="c1", timestamp=100, channel="face", expression="sadness", score=0.3),
        Expression(session_id="s1", viewer_id="v1", creative_id="c1", timestamp=200, channel="voice", expression="excitement", score=0.7),
    ]
    second_batch = (
        make_viewer_dimension([viewer]),
        make_creative_dimension([creative]),
        make_session_dimension([session]),
        make_expression_fact(second_expressions),
    )
    warehouse.load(second_batch)

    connection = duckdb.connect(warehouse_path, read_only=True)
    try:
        fact_count = connection.execute(f"SELECT COUNT(*) FROM {FACT_EXPRESSION}").fetchone()[0]
        gone = connection.execute(
            "SELECT COUNT(*) FROM fact_expression WHERE session_id = 's1' AND timestamp = 33 AND expression = 'calmness'"
        ).fetchone()
    finally:
        connection.close()

    assert fact_count == 2
    assert gone is not None
    assert gone[0] == 0
