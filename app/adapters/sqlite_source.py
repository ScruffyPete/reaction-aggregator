import json
import sqlite3

from app.domain.ports.source import RawRow, SourceDescriptor


class SQLiteSource:
    def __init__(self, database_path: str, session_id: str) -> None:
        self._connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
        self._connection.row_factory = sqlite3.Row
        self._session_id = session_id

    def fetch(self, descriptor: SourceDescriptor) -> list[RawRow]:
        if descriptor not in _QUERIES:
            raise KeyError(f"No query for descriptor: {descriptor!r}")

        cursor = self._connection.execute(_QUERIES[descriptor], (self._session_id,))
        rows: list[RawRow] = [dict(row) for row in cursor.fetchall()]

        if descriptor is SourceDescriptor.REACTIONS:
            for row in rows:
                row["scores"] = json.loads(row["scores"])

        return rows


_QUERIES: dict[SourceDescriptor, str] = {
    SourceDescriptor.SESSION: (
        "SELECT id, viewer_id, creative_id, started_at FROM sessions WHERE id = ?"
    ),
    SourceDescriptor.VIEWER: (
        "SELECT v.id, v.age_bracket, v.gender, v.country_code"
        " FROM viewers v JOIN sessions s ON s.viewer_id = v.id WHERE s.id = ?"
    ),
    SourceDescriptor.CREATIVE: (
        "SELECT c.id, c.title, c.brand, c.duration_ms"
        " FROM creatives c JOIN sessions s ON s.creative_id = c.id WHERE s.id = ?"
    ),
    SourceDescriptor.REACTIONS: (
        "SELECT session_id, timestamp_ms, channel, scores FROM reactions WHERE session_id = ?"
    ),
}
