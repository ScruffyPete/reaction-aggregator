from app.domain.ports.source import RawRow, SourceDescriptor


class FakeSource:
    def __init__(self, data: dict[SourceDescriptor, list[RawRow]]) -> None:
        self._data = data

    def fetch(self, descriptor: SourceDescriptor) -> list[RawRow]:
        if descriptor not in self._data:
            raise KeyError(f"No data seeded for descriptor: {descriptor!r}")
        return list(self._data[descriptor])
