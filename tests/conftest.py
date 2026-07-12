"""Shared fixtures for the reaction-aggregator test suite."""
from __future__ import annotations

import pytest
from collections.abc import Callable

from app.adapters.fake_source import FakeSource
from app.adapters.fake_warehouse import FakeWarehouse
from app.domain.models import DIM_SESSION, Session
from app.domain.ports.source import RawRow, SourceDescriptor
from app.domain.tables import DimensionTable


# ---------------------------------------------------------------------------
# Fake source — factory fixture wrapping the shipped FakeSource adapter
# ---------------------------------------------------------------------------

@pytest.fixture()
def make_fake_source() -> Callable[[dict[SourceDescriptor, list[RawRow]]], FakeSource]:
    """Factory fixture: call _make(data) to get a fresh FakeSource."""

    def _make(data: dict[SourceDescriptor, list[RawRow]]) -> FakeSource:
        return FakeSource(data)

    return _make


# ---------------------------------------------------------------------------
# Fake warehouse — plain fixture returning the shipped FakeWarehouse adapter
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_warehouse() -> FakeWarehouse:
    """Return a fresh FakeWarehouse."""
    return FakeWarehouse()


# ---------------------------------------------------------------------------
# Session entities and the session dimension — rows are real Session entities,
# as in production
# ---------------------------------------------------------------------------

@pytest.fixture()
def make_session() -> Callable[..., Session]:
    """Factory fixture: call _make(...) when specific attributes matter."""

    def _make(
        session_id: str = "s1",
        viewer_id: str = "v1",
        creative_id: str = "c1",
    ) -> Session:
        return Session(session_id=session_id, viewer_id=viewer_id, creative_id=creative_id)

    return _make


@pytest.fixture()
def session(make_session: Callable[..., Session]) -> Session:
    """Plain fixture: a default Session for when the attributes don't matter."""
    return make_session()


@pytest.fixture()
def make_session_dimensions() -> Callable[..., dict[str, DimensionTable]]:
    """Factory fixture: call _make(sessions) to build a dim_session dict."""

    def _make(sessions: list[Session]) -> dict[str, DimensionTable]:
        return {DIM_SESSION: DimensionTable(DIM_SESSION, "session_id", tuple(sessions))}

    return _make


@pytest.fixture()
def session_dimensions(
    session: Session,
    make_session_dimensions: Callable[..., dict[str, DimensionTable]],
) -> dict[str, DimensionTable]:
    """Plain fixture: default dim_session dict with the default session."""
    return make_session_dimensions([session])


# ---------------------------------------------------------------------------
# Raw reaction builder
# ---------------------------------------------------------------------------

@pytest.fixture()
def make_raw_reaction() -> Callable[..., dict]:
    """Factory fixture: call _make(...) to build a raw reaction dict."""

    def _make(
        session_id: str = "s1",
        timestamp_ms: int = 1000,
        channel: str = "face",
        scores: dict[str, float] | None = None,
    ) -> dict:
        result: dict = {
            "session_id": session_id,
            "timestamp_ms": timestamp_ms,
            "channel": channel,
        }
        if scores is not None:
            result["scores"] = scores
        return result

    return _make
