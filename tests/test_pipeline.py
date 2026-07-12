from collections.abc import Callable

import pytest

from app.adapters.mock_source import MockSource
from app.adapters.mock_warehouse import MockWarehouse
from app.application.pipeline import run_pipeline
from app.domain.mapping import Mapping
from app.domain.ports.source import BaseSource, RawRow, SourceDescriptor
from app.domain.tables import DimensionTable, FactTable


# ---------------------------------------------------------------------------
# Seeded data used across pipeline tests
# ---------------------------------------------------------------------------

_SEEDED: dict[SourceDescriptor, list[RawRow]] = {
    SourceDescriptor.VIEWER: [{"id": "v1"}],
    SourceDescriptor.CREATIVE: [{"id": "c1"}],
    SourceDescriptor.SESSION: [{"id": "s1"}],
    SourceDescriptor.REACTIONS: [{"reaction": "like"}],
}


# ---------------------------------------------------------------------------
# Fetch-counting MockSource subclass — used only where data-based assertions
# cannot prove "fetched exactly once" (a wiring property, not a data property).
# ---------------------------------------------------------------------------

class _CountingMockSource(MockSource):
    """Thin wiring recorder: counts fetch calls per descriptor, delegates via super()."""

    def __init__(self, data: dict[SourceDescriptor, list[RawRow]]) -> None:
        super().__init__(data)
        self.fetch_counts: dict[SourceDescriptor, int] = {}

    def fetch(self, descriptor: SourceDescriptor) -> list[RawRow]:
        self.fetch_counts[descriptor] = self.fetch_counts.get(descriptor, 0) + 1
        return super().fetch(descriptor)


# ---------------------------------------------------------------------------
# Local dummies (no mock library) — stay local; they record wiring specifics
# ---------------------------------------------------------------------------

class DummyMapping(Mapping):
    """Calls source.fetch(VIEWER) in extract; records invocation details."""

    def __init__(self, table_name: str) -> None:
        self._table_name = table_name
        self.extract_call_count = 0
        self.transform_call_count = 0
        self.last_transform_rows: list[RawRow] | None = None

    def extract(self, source: BaseSource) -> list[RawRow]:
        self.extract_call_count += 1
        return source.fetch(SourceDescriptor.VIEWER)

    def transform(self, rows: list[RawRow]) -> DimensionTable:
        self.transform_call_count += 1
        self.last_transform_rows = rows
        return DimensionTable(name=self._table_name, key="id", rows=())


class DummyFactBuilder:
    """Records arguments and returns a fixed FactTable."""

    def __init__(self) -> None:
        self.call_count = 0
        self.last_dimensions: dict[str, DimensionTable] | None = None
        self.last_raw_reactions: list[RawRow] | None = None

    def __call__(
        self,
        dimensions: dict[str, DimensionTable],
        raw_reactions: list[RawRow],
    ) -> FactTable:
        self.call_count += 1
        self.last_dimensions = dimensions
        self.last_raw_reactions = raw_reactions
        return FactTable("fact_dummy", ("id",), ())


# ---------------------------------------------------------------------------
# Core behaviour tests
# ---------------------------------------------------------------------------

def test_each_mapping_extracted_transformed_loaded_exactly_once(
    mock_warehouse: MockWarehouse,
) -> None:
    mappings = [DummyMapping("dim_a"), DummyMapping("dim_b")]
    source = MockSource(_SEEDED)
    fact_builder = DummyFactBuilder()
    run_pipeline(source, mock_warehouse, mappings, fact_builder)

    for m in mappings:
        assert m.extract_call_count == 1
        assert m.transform_call_count == 1

    # first two loads are dim tables
    dim_names = [t.name for t in mock_warehouse.loads[:2]]
    assert dim_names == ["dim_a", "dim_b"]


def test_warehouse_receives_dimensions_then_fact_last(
    mock_warehouse: MockWarehouse,
) -> None:
    mappings = [DummyMapping("dim_a"), DummyMapping("dim_b")]
    source = MockSource(_SEEDED)
    fact_builder = DummyFactBuilder()
    run_pipeline(source, mock_warehouse, mappings, fact_builder)

    assert len(mock_warehouse.loads) == 3  # 2 dimensions + 1 fact
    assert isinstance(mock_warehouse.loads[0], DimensionTable)
    assert isinstance(mock_warehouse.loads[1], DimensionTable)
    assert isinstance(mock_warehouse.loads[2], FactTable)


def test_fact_builder_called_exactly_once_with_all_dimensions_and_reactions(
    mock_warehouse: MockWarehouse,
) -> None:
    mappings = [DummyMapping("dim_a"), DummyMapping("dim_b")]
    source = MockSource(_SEEDED)
    fact_builder = DummyFactBuilder()
    run_pipeline(source, mock_warehouse, mappings, fact_builder)

    assert fact_builder.call_count == 1
    assert set(fact_builder.last_dimensions.keys()) == {"dim_a", "dim_b"}
    expected_reactions = _SEEDED[SourceDescriptor.REACTIONS]
    assert fact_builder.last_raw_reactions == expected_reactions


def test_reactions_fetched_exactly_once(mock_warehouse: MockWarehouse) -> None:
    mappings = [DummyMapping("dim_a"), DummyMapping("dim_b")]
    source = _CountingMockSource(_SEEDED)
    fact_builder = DummyFactBuilder()
    run_pipeline(source, mock_warehouse, mappings, fact_builder)

    assert source.fetch_counts.get(SourceDescriptor.REACTIONS, 0) == 1


def test_mappings_processed_in_registry_list_order(
    mock_warehouse: MockWarehouse,
) -> None:
    mappings = [DummyMapping(f"dim_{i}") for i in range(3)]
    source = MockSource(_SEEDED)
    fact_builder = DummyFactBuilder()
    run_pipeline(source, mock_warehouse, mappings, fact_builder)

    loaded_dim_names = [t.name for t in mock_warehouse.loads if isinstance(t, DimensionTable)]
    assert loaded_dim_names == ["dim_0", "dim_1", "dim_2"]


# ---------------------------------------------------------------------------
# Zero-mapping edge case
# ---------------------------------------------------------------------------

def test_zero_mappings_still_builds_and_loads_fact(
    mock_warehouse: MockWarehouse,
) -> None:
    source = _CountingMockSource(_SEEDED)
    fact_builder = DummyFactBuilder()
    run_pipeline(source, mock_warehouse, [], fact_builder)

    # reactions must still be fetched
    assert source.fetch_counts.get(SourceDescriptor.REACTIONS, 0) >= 1
    # only one load: the fact
    assert len(mock_warehouse.loads) == 1
    assert isinstance(mock_warehouse.loads[0], FactTable)
    # fact builder called with empty dimensions
    assert fact_builder.call_count == 1
    assert fact_builder.last_dimensions == {}


# ---------------------------------------------------------------------------
# Extensibility property: adding a mapping scales loads and dimensions dict
# without changing Pipeline code — parametrized over k
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("k", [0, 1, 2, 5])
def test_extensibility_property(k: int) -> None:
    """k mappings → k dim loads + 1 fact load; dimensions dict has k entries."""
    mappings_k = [DummyMapping(f"dim_{i}") for i in range(k)]
    source_k = MockSource(_SEEDED)
    warehouse_k = MockWarehouse()
    fact_builder_k = DummyFactBuilder()
    run_pipeline(source_k, warehouse_k, mappings_k, fact_builder_k)

    assert len(warehouse_k.loads) == k + 1
    assert isinstance(warehouse_k.loads[-1], FactTable)
    assert len(fact_builder_k.last_dimensions) == k

    # k+1 version
    mappings_k1 = [DummyMapping(f"dim_{i}") for i in range(k + 1)]
    source_k1 = MockSource(_SEEDED)
    warehouse_k1 = MockWarehouse()
    fact_builder_k1 = DummyFactBuilder()
    run_pipeline(source_k1, warehouse_k1, mappings_k1, fact_builder_k1)

    assert len(warehouse_k1.loads) == (k + 1) + 1
    assert isinstance(warehouse_k1.loads[-1], FactTable)
    assert len(fact_builder_k1.last_dimensions) == k + 1


# ---------------------------------------------------------------------------
# transform receives extract's rows (pass-through honesty check)
# ---------------------------------------------------------------------------

def test_transform_receives_rows_from_extract(mock_warehouse: MockWarehouse) -> None:
    mapping = DummyMapping("dim_a")
    source = MockSource(_SEEDED)
    fact_builder = DummyFactBuilder()
    run_pipeline(source, mock_warehouse, [mapping], fact_builder)

    expected = _SEEDED[SourceDescriptor.VIEWER]
    assert mapping.last_transform_rows == expected


# ---------------------------------------------------------------------------
# dimensions dict uses table.name as key (not mapping order or class name)
# ---------------------------------------------------------------------------

def test_dimensions_dict_keyed_by_table_name(mock_warehouse: MockWarehouse) -> None:
    mappings = [DummyMapping("alpha"), DummyMapping("beta")]
    source = MockSource(_SEEDED)
    fact_builder = DummyFactBuilder()
    run_pipeline(source, mock_warehouse, mappings, fact_builder)

    assert "alpha" in fact_builder.last_dimensions
    assert "beta" in fact_builder.last_dimensions
    assert fact_builder.last_dimensions["alpha"].name == "alpha"
    assert fact_builder.last_dimensions["beta"].name == "beta"


# ---------------------------------------------------------------------------
# Duplicate table name: the dict collapses duplicates before the single batch
# load, so only the last mapping's table reaches the warehouse. The registry
# is the real guard against collisions; this test documents the corner
# behaviour.
# ---------------------------------------------------------------------------

class _KeyedDummyMapping(Mapping):
    """Emits a fixed table name but a distinguishing key so the two mappings' tables are not equal."""

    def __init__(self, table_name: str, key: str) -> None:
        self._table_name = table_name
        self._key = key

    def extract(self, source: BaseSource) -> list[RawRow]:
        return source.fetch(SourceDescriptor.VIEWER)

    def transform(self, rows: list[RawRow]) -> DimensionTable:
        return DimensionTable(name=self._table_name, key=self._key, rows=())


def test_duplicate_table_name_last_writer_wins(
    mock_warehouse: MockWarehouse,
) -> None:
    first = _KeyedDummyMapping("dim_dup", key="first_key")
    last = _KeyedDummyMapping("dim_dup", key="last_key")
    source = MockSource(_SEEDED)
    fact_builder = DummyFactBuilder()
    run_pipeline(source, mock_warehouse, [first, last], fact_builder)

    # Duplicates collapse in the dict before the single batch load: warehouse
    # receives 2 tables total — one dim_dup (last mapping's) plus the fact.
    assert len(mock_warehouse.loads) == 2
    assert isinstance(mock_warehouse.loads[0], DimensionTable)
    assert mock_warehouse.loads[0].name == "dim_dup"
    assert mock_warehouse.loads[0].key == "last_key"
    assert isinstance(mock_warehouse.loads[1], FactTable)

    # The dimensions dict keyed by name collapses to a single entry holding the
    # LAST mapping's table (last-writer-wins).
    assert set(fact_builder.last_dimensions.keys()) == {"dim_dup"}
    assert fact_builder.last_dimensions["dim_dup"].key == "last_key"


# ---------------------------------------------------------------------------
# Atomicity and ETL phasing — a failed run writes nothing; the load is a
# single call
# ---------------------------------------------------------------------------

class _FailingTransformMapping(DummyMapping):
    """Extracts normally (recorded via DummyMapping) but always fails in transform."""

    def transform(self, rows: list[RawRow]) -> DimensionTable:
        raise RuntimeError("transform failure")


class _FailingFactBuilder:
    """Always fails when called."""

    def __call__(
        self,
        dimensions: dict[str, DimensionTable],
        raw_reactions: list[RawRow],
    ) -> FactTable:
        raise RuntimeError("fact builder failure")


class _CountingMockWarehouse(MockWarehouse):
    """Thin wiring recorder: counts load calls, delegates via super()."""

    def __init__(self) -> None:
        super().__init__()
        self.load_call_count = 0

    def load(self, tables: tuple[DimensionTable | FactTable, ...]) -> None:
        self.load_call_count += 1
        super().load(tables)


def test_fact_builder_failure_writes_nothing(mock_warehouse: MockWarehouse) -> None:
    mappings = [DummyMapping("dim_a"), DummyMapping("dim_b")]
    source = MockSource(_SEEDED)
    fact_builder = _FailingFactBuilder()

    with pytest.raises(RuntimeError):
        run_pipeline(source, mock_warehouse, mappings, fact_builder)

    assert mock_warehouse.loads == []


def test_mapping_transform_failure_writes_nothing(mock_warehouse: MockWarehouse) -> None:
    mappings = [DummyMapping("dim_a"), _FailingTransformMapping("dim_b")]
    source = MockSource(_SEEDED)
    fact_builder = DummyFactBuilder()

    with pytest.raises(RuntimeError):
        run_pipeline(source, mock_warehouse, mappings, fact_builder)

    assert mock_warehouse.loads == []


def test_warehouse_load_called_exactly_once_per_run() -> None:
    warehouse = _CountingMockWarehouse()
    mappings = [DummyMapping("dim_a"), DummyMapping("dim_b")]
    source = MockSource(_SEEDED)
    fact_builder = DummyFactBuilder()
    run_pipeline(source, warehouse, mappings, fact_builder)

    assert warehouse.load_call_count == 1
    assert len(warehouse.loads) == 3


def test_all_extracts_complete_before_any_transform_failure(
    mock_warehouse: MockWarehouse,
) -> None:
    mapping_a = DummyMapping("dim_a")
    mapping_b = _FailingTransformMapping("dim_b")
    mappings = [mapping_a, mapping_b]
    source = MockSource(_SEEDED)
    fact_builder = DummyFactBuilder()

    with pytest.raises(RuntimeError):
        run_pipeline(source, mock_warehouse, mappings, fact_builder)

    # Both extracts completed before any transform ran.
    assert mapping_a.extract_call_count == 1
    assert mapping_b.extract_call_count == 1
    # The transform phase began (first mapping's transform ran) before failing.
    assert mapping_a.transform_call_count == 1
