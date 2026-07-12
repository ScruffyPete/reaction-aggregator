from app.domain.mapping import Mapping
from app.domain.models import DIM_VIEWER, Viewer
from app.domain.ports.source import BaseSource, RawRow, SourceDescriptor
from app.domain.tables import DimensionTable


class ViewerMapping(Mapping):
    def extract(self, source: BaseSource) -> list[RawRow]:
        return source.fetch(SourceDescriptor.VIEWER)

    def transform(self, rows: list[RawRow]) -> DimensionTable:
        seen: dict[str, Viewer] = {}
        for row in rows:
            raw_id = row.get("id")
            if raw_id is None:
                raise ValueError("viewer row missing required 'id'")
            if raw_id in seen:
                continue
            seen[raw_id] = Viewer(
                viewer_id=raw_id,
                age_bracket=row.get("age_bracket") or "unknown",
                gender=row.get("gender") or "unknown",
                country=row.get("country_code") or "unknown",
            )
        return DimensionTable(name=DIM_VIEWER, key="viewer_id", rows=tuple(seen.values()))
