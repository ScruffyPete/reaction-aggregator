from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from app.domain.ports.source import RawRow


@dataclass(frozen=True)
class DimensionTable:
    name: str
    key: str
    rows: tuple[BaseModel, ...]


@dataclass(frozen=True)
class FactTable:
    name: str
    grain: tuple[str, ...]
    rows: tuple[BaseModel, ...]


FactBuilder = Callable[[dict[str, DimensionTable], list[RawRow]], FactTable]
