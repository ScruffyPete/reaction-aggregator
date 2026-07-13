from app.domain.mapping import Mapping
from app.domain.models import DIM_CREATIVE, Creative
from app.domain.ports.source import BaseSource, RawRow, SourceDescriptor
from app.domain.tables import DimensionTable


class CreativeMapping(Mapping):
    def extract(self, source: BaseSource) -> list[RawRow]:
        return source.fetch(SourceDescriptor.CREATIVE)

    def transform(self, rows: list[RawRow]) -> DimensionTable:
        if not rows:
            raise ValueError("no creative rows in source")
        seen: dict[str, Creative] = {}
        for row in rows:
            raw_id = row.get("id")
            if raw_id is None:
                raise ValueError("creative row missing required 'id'")

            if raw_id in seen:
                continue

            title = row.get("title") or "unknown"
            brand = row.get("brand") or "unknown"
            duration_ms = row.get("duration_ms")

            seen[raw_id] = Creative(
                creative_id=raw_id,
                title=title,
                brand=brand,
                duration_ms=duration_ms,
            )

        return DimensionTable(
            name=DIM_CREATIVE,
            key="creative_id",
            rows=tuple(seen.values()),
        )
