import os
import sys

from app.adapters.sqlite_source import SQLiteSource
from app.adapters.duckdb_warehouse import DuckDBWarehouse
from app.application.pipeline import run_pipeline
from app.application.registry import REGISTRY
from app.domain.fact import build_expression_fact


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: reaction-aggregator <session_id>", file=sys.stderr)
        sys.exit(2)

    session_id = sys.argv[1]
    source_path = os.environ.get("SOURCE_DATABASE_PATH", "data/source.db")
    warehouse_path = os.environ.get("WAREHOUSE_DATABASE_PATH", "data/warehouse.duckdb")
    source, warehouse = build_adapters(session_id, source_path, warehouse_path)

    print(f"aggregating session {session_id}: {source_path} -> {warehouse_path}")
    run_pipeline(source, warehouse, REGISTRY, build_expression_fact)

    print(f"aggregated session {session_id}")


def build_adapters(
    session_id: str, source_path: str, warehouse_path: str
) -> tuple[SQLiteSource, DuckDBWarehouse]:
    return SQLiteSource(source_path, session_id), DuckDBWarehouse(warehouse_path)


if __name__ == "__main__":
    main()
