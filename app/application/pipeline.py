from app.domain.mapping import Mapping
from app.domain.ports.source import BaseSource, RawRow, SourceDescriptor
from app.domain.ports.warehouse import BaseWarehouse
from app.domain.tables import DimensionTable, FactBuilder, FactTable


def run_pipeline(
    source: BaseSource,
    warehouse: BaseWarehouse,
    mappings: list[Mapping],
    fact_builder: FactBuilder,
) -> None:
    extracted, raw_reactions = _extract(source, mappings)
    tables = _transform(extracted, raw_reactions, fact_builder)
    _load(warehouse, tables)


def _extract(
    source: BaseSource, mappings: list[Mapping]
) -> tuple[list[tuple[Mapping, list[RawRow]]], list[RawRow]]:
    extracted = [(mapping, mapping.extract(source)) for mapping in mappings]
    raw_reactions = source.fetch(SourceDescriptor.REACTIONS)
    return extracted, raw_reactions


def _transform(
    extracted: list[tuple[Mapping, list[RawRow]]],
    raw_reactions: list[RawRow],
    fact_builder: FactBuilder,
) -> tuple[DimensionTable | FactTable, ...]:
    dimensions: dict[str, DimensionTable] = {}
    for mapping, rows in extracted:
        table = mapping.transform(rows)
        dimensions[table.name] = table
    fact = fact_builder(dimensions, raw_reactions)
    return (*dimensions.values(), fact)


def _load(
    warehouse: BaseWarehouse, tables: tuple[DimensionTable | FactTable, ...]
) -> None:
    warehouse.load(tables)
