from pydantic import BaseModel

from app.domain.tables import DimensionTable, FactTable


class MockWarehouse:
    def __init__(self) -> None:
        self.loads: list[DimensionTable | FactTable] = []

    def load(self, tables: tuple[DimensionTable | FactTable, ...]) -> None:
        self.loads.extend(tables)

    def rows_for(self, name: str) -> list[BaseModel]:
        result: list[BaseModel] = []
        for table in self.loads:
            if table.name == name:
                result.extend(table.rows)
        return result
