import types
import typing

import duckdb

from app.domain.tables import DimensionTable, FactTable


class DuckDBWarehouse:
    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    def load(self, tables: tuple[DimensionTable | FactTable, ...]) -> None:
        connection = duckdb.connect(self._database_path)
        try:
            connection.execute("BEGIN TRANSACTION")
            for table in tables:
                if not table.rows:
                    continue
                _load_table(connection, table)
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()


def _load_table(connection: duckdb.DuckDBPyConnection, table: DimensionTable | FactTable) -> None:
    _create_table(connection, table)
    if isinstance(table, DimensionTable):
        _upsert_dimension_rows(connection, table)
    else:
        _replace_fact_rows(connection, table)


def _create_table(connection: duckdb.DuckDBPyConnection, table: DimensionTable | FactTable) -> None:
    columns = _column_definitions(type(table.rows[0]))
    if isinstance(table, DimensionTable):
        ddl = _CREATE_DIMENSION_TABLE.format(table=table.name, columns=columns, key=table.key)
    else:
        ddl = _CREATE_FACT_TABLE.format(table=table.name, columns=columns)
    connection.execute(ddl)


def _upsert_dimension_rows(connection: duckdb.DuckDBPyConnection, table: DimensionTable) -> None:
    field_count = len(type(table.rows[0]).model_fields)
    placeholders = ", ".join("?" * field_count)
    row_values = [list(row.model_dump().values()) for row in table.rows]
    connection.executemany(
        _UPSERT_ROWS.format(table=table.name, placeholders=placeholders), row_values
    )


def _replace_fact_rows(connection: duckdb.DuckDBPyConnection, table: FactTable) -> None:
    first_session_id = table.rows[0].model_dump()["session_id"]
    connection.execute(_DELETE_SESSION_ROWS.format(table=table.name), [first_session_id])
    field_count = len(type(table.rows[0]).model_fields)
    placeholders = ", ".join("?" * field_count)
    row_values = [list(row.model_dump().values()) for row in table.rows]
    connection.executemany(
        _INSERT_ROWS.format(table=table.name, placeholders=placeholders), row_values
    )


def _column_definitions(model_class: type) -> str:
    return ", ".join(
        f"{name} {_column_type(field.annotation)}"
        for name, field in model_class.model_fields.items()
    )


def _column_type(annotation: object) -> str:
    origin = typing.get_origin(annotation)

    if origin is typing.Union or isinstance(annotation, types.UnionType):
        non_none_args = [argument for argument in typing.get_args(annotation) if argument is not type(None)]
        if len(non_none_args) == 1:
            return _column_type(non_none_args[0])

    if origin is typing.Literal:
        return "VARCHAR"

    if annotation in _COLUMN_TYPE_MAP:
        return _COLUMN_TYPE_MAP[annotation]  # type: ignore[index]

    raise ValueError(f"No SQL type mapping for annotation: {annotation!r}")


_COLUMN_TYPE_MAP: dict[type, str] = {
    str: "VARCHAR",
    int: "BIGINT",
    float: "DOUBLE",
    bool: "BOOLEAN",
}

_CREATE_DIMENSION_TABLE = "CREATE TABLE IF NOT EXISTS {table} ({columns}, PRIMARY KEY ({key}))"
_CREATE_FACT_TABLE = "CREATE TABLE IF NOT EXISTS {table} ({columns})"
_UPSERT_ROWS = "INSERT OR REPLACE INTO {table} VALUES ({placeholders})"
_INSERT_ROWS = "INSERT INTO {table} VALUES ({placeholders})"
_DELETE_SESSION_ROWS = "DELETE FROM {table} WHERE session_id = ?"
