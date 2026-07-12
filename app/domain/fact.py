from app.domain.models import DIM_SESSION, FACT_EXPRESSION, Expression
from app.domain.ports.source import RawRow
from app.domain.tables import DimensionTable, FactTable


def build_expression_fact(dimensions: dict[str, DimensionTable], raw_reactions: list[RawRow]) -> FactTable:
    session_lookup = _session_lookup(dimensions)

    seen_grain_keys: set[tuple[str, int, str, str]] = set()
    expression_rows: list[Expression] = []

    for raw_reaction in raw_reactions:
        timestamp_ms, session_id, channel = _validate_raw_reaction(raw_reaction, session_lookup)

        scores = raw_reaction.get("scores")
        if not scores:
            continue

        viewer_id, creative_id = session_lookup[session_id]

        for expression, score in scores.items():
            grain_key = (session_id, timestamp_ms, channel, expression)
            if grain_key in seen_grain_keys:
                continue
            seen_grain_keys.add(grain_key)

            expression_rows.append(Expression(
                session_id=session_id,
                viewer_id=viewer_id,
                creative_id=creative_id,
                timestamp=timestamp_ms,
                channel=channel,
                expression=expression,
                score=score,
            ))

    return FactTable(
        name=FACT_EXPRESSION,
        grain=("session_id", "timestamp", "channel", "expression"),
        rows=tuple(expression_rows),
    )


def _session_lookup(dimensions: dict[str, DimensionTable]) -> dict[str, tuple[str, str]]:
    if DIM_SESSION not in dimensions:
        raise ValueError(f"dimensions must contain '{DIM_SESSION}'")

    session_lookup: dict[str, tuple[str, str]] = {}
    for row in dimensions[DIM_SESSION].rows:
        session_lookup[row.session_id] = (row.viewer_id, row.creative_id)

    return session_lookup


def _validate_raw_reaction(
    raw_reaction: RawRow,
    session_lookup: dict[str, tuple[str, str]],
) -> tuple[int, str, str]:
    timestamp_ms = raw_reaction.get("timestamp_ms")
    if timestamp_ms is None:
        raise ValueError("raw reaction missing required 'timestamp_ms'")

    session_id = raw_reaction.get("session_id")
    if session_id is None:
        raise ValueError("raw reaction missing required 'session_id'")

    if session_id not in session_lookup:
        raise ValueError(
            f"raw reaction references unknown session_id '{session_id}'"
        )

    channel = raw_reaction.get("channel")
    if channel is None:
        raise ValueError("raw reaction missing required 'channel'")

    return timestamp_ms, session_id, channel
