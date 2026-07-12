from typing import Protocol

from app.domain.tables import DimensionTable, FactTable


class BaseWarehouse(Protocol):
    def load(self, tables: tuple[DimensionTable | FactTable, ...]) -> None: ...
