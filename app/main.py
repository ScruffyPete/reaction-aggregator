import sys

from app.adapters.fake_source import FakeSource
from app.adapters.fake_warehouse import FakeWarehouse
from app.application.pipeline import run_pipeline
from app.application.registry import REGISTRY
from app.domain.fact import build_expression_fact
from app.domain.ports.source import SourceDescriptor


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: reaction-aggregator <session_id>", file=sys.stderr)
        sys.exit(2)

    session_id = sys.argv[1]
    source, warehouse = build_adapters(session_id)
    run_pipeline(source, warehouse, REGISTRY, build_expression_fact)

    for table in warehouse.loads:
        print(f"{table.name}: {len(table.rows)} rows")


def build_adapters(session_id: str) -> tuple[FakeSource, FakeWarehouse]:
    source = FakeSource(
        data={
            SourceDescriptor.VIEWER: [
                {"id": "v1", "age_bracket": "25-34", "gender": "f", "country_code": "PL"}
            ],
            SourceDescriptor.CREATIVE: [
                {"id": "c1", "title": "Spring Launch", "brand": "Acme", "duration_ms": 30000}
            ],
            SourceDescriptor.SESSION: [
                {
                    "id": session_id,
                    "viewer_id": "v1",
                    "creative_id": "c1",
                    "started_at": "2026-07-12T10:00:00Z",
                }
            ],
            SourceDescriptor.REACTIONS: [
                {
                    "session_id": session_id,
                    "timestamp_ms": 0,
                    "channel": "face",
                    "scores": {"joy": 0.81, "surprise": 0.4, "anger": 0.02},
                },
                {
                    "session_id": session_id,
                    "timestamp_ms": 33,
                    "channel": "face",
                    "scores": {"joy": 0.79, "surprise": 0.35, "anger": 0.03},
                },
                {
                    "session_id": session_id,
                    "timestamp_ms": 2400,
                    "channel": "voice",
                    "scores": {"joy": 0.77, "calmness": 0.6},
                },
            ],
        }
    )
    warehouse = FakeWarehouse()
    return source, warehouse


if __name__ == "__main__":
    main()
