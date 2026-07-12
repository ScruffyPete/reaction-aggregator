from pydantic import BaseModel

from app.domain.tables import DimensionTable, FactTable


class FakeWarehouse:
    def __init__(self) -> None:
        self.loads: list[DimensionTable | FactTable] = []

    def load(self, table: DimensionTable | FactTable) -> None:
        self.loads.append(table)

    def rows_for(self, name: str) -> list[BaseModel]:
        result: list[BaseModel] = []
        for table in self.loads:
            if table.name == name:
                result.extend(table.rows)
        return result
