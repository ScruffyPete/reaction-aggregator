from app.domain.mapping import Mapping
from app.domain.ports.source import BaseSource, SourceDescriptor
from app.domain.ports.warehouse import BaseWarehouse
from app.domain.tables import DimensionTable, FactBuilder


def run_pipeline(
    source: BaseSource,
    warehouse: BaseWarehouse,
    mappings: list[Mapping],
    fact_builder: FactBuilder,
) -> None:
    dimensions: dict[str, DimensionTable] = {}
    for mapping in mappings:
        rows = mapping.extract(source)
        table = mapping.transform(rows)
        warehouse.load(table)
        dimensions[table.name] = table

    raw_reactions = source.fetch(SourceDescriptor.REACTIONS)
    fact = fact_builder(dimensions, raw_reactions)
    warehouse.load(fact)
