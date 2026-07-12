from typing import Protocol

from app.domain.tables import DimensionTable, FactTable


class BaseWarehouse(Protocol):
    def load(self, table: DimensionTable | FactTable) -> None: ...
