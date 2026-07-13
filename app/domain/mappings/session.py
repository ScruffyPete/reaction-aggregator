from app.domain.mapping import Mapping
from app.domain.models import DIM_SESSION, Session
from app.domain.ports.source import BaseSource, RawRow, SourceDescriptor
from app.domain.tables import DimensionTable


class SessionMapping(Mapping):
    def extract(self, source: BaseSource) -> list[RawRow]:
        return source.fetch(SourceDescriptor.SESSION)

    def transform(self, rows: list[RawRow]) -> DimensionTable:
        if not rows:
            raise ValueError("no session rows in source")
        seen: dict[str, Session] = {}
        for row in rows:
            raw_id = row.get("id")
            if raw_id is None:
                raise ValueError("session row missing required 'id'")

            viewer_id = row.get("viewer_id")
            if viewer_id is None:
                raise ValueError("session row missing required 'viewer_id'")

            creative_id = row.get("creative_id")
            if creative_id is None:
                raise ValueError("session row missing required 'creative_id'")

            if raw_id in seen:
                continue

            started_at = row.get("started_at") or "unknown"
            seen[raw_id] = Session(
                session_id=raw_id,
                viewer_id=viewer_id,
                creative_id=creative_id,
                started_at=started_at,
            )

        return DimensionTable(
            name=DIM_SESSION,
            key="session_id",
            rows=tuple(seen.values()),
        )
