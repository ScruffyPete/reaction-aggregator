from enum import StrEnum
from typing import Any, Protocol

RawRow = dict[str, Any]


class SourceDescriptor(StrEnum):
    VIEWER = "viewer"
    CREATIVE = "creative"
    SESSION = "session"
    REACTIONS = "reactions"


class BaseSource(Protocol):
    def fetch(self, descriptor: SourceDescriptor) -> list[RawRow]: ...
