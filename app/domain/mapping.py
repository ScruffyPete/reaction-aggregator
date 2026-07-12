from abc import ABC, abstractmethod

from app.domain.ports.source import BaseSource, RawRow
from app.domain.tables import DimensionTable


class Mapping(ABC):
    @abstractmethod
    def extract(self, source: BaseSource) -> list[RawRow]: ...

    @abstractmethod
    def transform(self, rows: list[RawRow]) -> DimensionTable: ...
