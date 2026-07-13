"""Mocks-only end-to-end smoke tests through run_pipeline(); real-adapter main() path tests."""
import sys

import pytest

from app.adapters.mock_source import MockSource
from app.adapters.mock_warehouse import MockWarehouse
from app.application.pipeline import run_pipeline
from app.application.registry import REGISTRY
from app.domain.fact import build_expression_fact
from app.domain.models import DIM_CREATIVE, DIM_SESSION, DIM_VIEWER, FACT_EXPRESSION
from app.domain.ports.source import SourceDescriptor
from app.seed import seed_source


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SESSION_ID = "demo-session-1"


@pytest.fixture()
def seeded_adapters() -> tuple[MockSource, MockWarehouse]:
    source = MockSource(
        data={
            SourceDescriptor.VIEWER: [
                {"id": "v1", "age_bracket": "25-34", "gender": "f", "country_code": "PL"}
            ],
            SourceDescriptor.CREATIVE: [
                {"id": "c1", "title": "Spring Launch", "brand": "Acme", "duration_ms": 30000}
            ],
            SourceDescriptor.SESSION: [
                {
                    "id": SESSION_ID,
                    "viewer_id": "v1",
                    "creative_id": "c1",
                    "started_at": "2026-07-12T10:00:00Z",
                }
            ],
            SourceDescriptor.REACTIONS: [
                {
                    "session_id": SESSION_ID,
                    "timestamp_ms": 0,
                    "channel": "face",
                    "scores": {"joy": 0.81, "surprise": 0.4, "anger": 0.02},
                },
                {
                    "session_id": SESSION_ID,
                    "timestamp_ms": 33,
                    "channel": "face",
                    "scores": {"joy": 0.79, "surprise": 0.35, "anger": 0.03},
                },
                {
                    "session_id": SESSION_ID,
                    "timestamp_ms": 2400,
                    "channel": "voice",
                    "scores": {"joy": 0.77, "calmness": 0.6},
                },
            ],
        }
    )
    warehouse = MockWarehouse()
    return source, warehouse


# ---------------------------------------------------------------------------
# End-to-end smoke
# ---------------------------------------------------------------------------

def test_exactly_four_loads_in_correct_order(seeded_adapters) -> None:
    source, warehouse = seeded_adapters
    run_pipeline(source, warehouse, REGISTRY, build_expression_fact)

    names = [t.name for t in warehouse.loads]
    assert names == [DIM_VIEWER, DIM_CREATIVE, DIM_SESSION, FACT_EXPRESSION]


def test_dim_row_counts(seeded_adapters) -> None:
    source, warehouse = seeded_adapters
    run_pipeline(source, warehouse, REGISTRY, build_expression_fact)

    assert len(warehouse.rows_for(DIM_VIEWER)) == 1
    assert len(warehouse.rows_for(DIM_CREATIVE)) == 1
    assert len(warehouse.rows_for(DIM_SESSION)) == 1


def test_fact_row_count(seeded_adapters) -> None:
    source, warehouse = seeded_adapters
    run_pipeline(source, warehouse, REGISTRY, build_expression_fact)

    # 3 scores from the raw reaction at 0ms + 3 at 33ms + 2 at 2400ms = 8
    assert len(warehouse.rows_for(FACT_EXPRESSION)) == 8


def test_fact_rows_denormalized_viewer_and_creative(seeded_adapters) -> None:
    source, warehouse = seeded_adapters
    run_pipeline(source, warehouse, REGISTRY, build_expression_fact)

    fact_rows = warehouse.rows_for(FACT_EXPRESSION)
    for row in fact_rows:
        assert row.viewer_id == "v1"
        assert row.creative_id == "c1"
        assert row.session_id == SESSION_ID


def test_fact_grain_sanity(seeded_adapters) -> None:
    source, warehouse = seeded_adapters
    run_pipeline(source, warehouse, REGISTRY, build_expression_fact)

    fact_rows = warehouse.rows_for(FACT_EXPRESSION)
    grains = {(r.session_id, r.timestamp, r.channel, r.expression) for r in fact_rows}
    assert len(grains) == 8  # no grain duplicates


def test_fact_timestamps(seeded_adapters) -> None:
    source, warehouse = seeded_adapters
    run_pipeline(source, warehouse, REGISTRY, build_expression_fact)

    fact_rows = warehouse.rows_for(FACT_EXPRESSION)
    timestamps = {r.timestamp for r in fact_rows}
    assert timestamps == {0, 33, 2400}


def test_fact_table_grain_metadata(seeded_adapters) -> None:
    source, warehouse = seeded_adapters
    run_pipeline(source, warehouse, REGISTRY, build_expression_fact)

    # The last load is the fact table
    fact_table = warehouse.loads[-1]
    assert fact_table.grain == ("session_id", "timestamp", "channel", "expression")


# ---------------------------------------------------------------------------
# main() argv handling
# ---------------------------------------------------------------------------

def test_main_missing_arg_exits_with_code_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["reaction-aggregator"])
    from app.main import main
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 2


def test_main_happy_path_aggregates_session(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path,
) -> None:
    import duckdb

    source_path = str(tmp_path / "source.db")
    warehouse_path = str(tmp_path / "warehouse.duckdb")

    seed_source(source_path, SESSION_ID, duration_ms=1000)

    monkeypatch.setenv("SOURCE_DATABASE_PATH", source_path)
    monkeypatch.setenv("WAREHOUSE_DATABASE_PATH", warehouse_path)
    monkeypatch.setattr(sys, "argv", ["reaction-aggregator", SESSION_ID])

    from app.main import main
    main()

    assert capsys.readouterr().out == (
        f"aggregating session {SESSION_ID}: {source_path} -> {warehouse_path}\n"
        f"aggregated session {SESSION_ID}\n"
    )

    connection = duckdb.connect(warehouse_path, read_only=True)
    try:
        fact_count = connection.execute("SELECT COUNT(*) FROM fact_expression").fetchone()[0]
        dim_viewer_count = connection.execute("SELECT COUNT(*) FROM dim_viewer").fetchone()[0]
        dim_creative_count = connection.execute("SELECT COUNT(*) FROM dim_creative").fetchone()[0]
        dim_session_count = connection.execute("SELECT COUNT(*) FROM dim_session").fetchone()[0]
    finally:
        connection.close()

    assert fact_count == 1680
    assert dim_viewer_count == 1
    assert dim_creative_count == 1
    assert dim_session_count == 1


def test_main_unknown_session_id_fails_loudly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    source_path = str(tmp_path / "source.db")
    warehouse_path = str(tmp_path / "warehouse.duckdb")

    seed_source(source_path, SESSION_ID, duration_ms=1000)

    monkeypatch.setenv("SOURCE_DATABASE_PATH", source_path)
    monkeypatch.setenv("WAREHOUSE_DATABASE_PATH", warehouse_path)
    monkeypatch.setattr(sys, "argv", ["reaction-aggregator", "session-never-seeded"])

    from app.main import main
    with pytest.raises(ValueError):
        main()
