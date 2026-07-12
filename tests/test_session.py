from collections.abc import Callable

import pytest

from app.domain.mappings.session import SessionMapping
from app.domain.models import DIM_SESSION, Session
from app.domain.ports.source import RawRow, SourceDescriptor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_ROW: RawRow = {
    "id": "s1",
    "viewer_id": "v1",
    "creative_id": "c1",
    "started_at": "2024-01-01T00:00:00Z",
}


@pytest.fixture()
def session_mapping() -> SessionMapping:
    return SessionMapping()


# ---------------------------------------------------------------------------
# Transform tests
# ---------------------------------------------------------------------------

def test_happy_path_fields_land_correctly(session_mapping: SessionMapping) -> None:
    table = session_mapping.transform([_VALID_ROW])
    assert len(table.rows) == 1
    session = table.rows[0]
    assert isinstance(session, Session)
    assert session.session_id == "s1"
    assert session.viewer_id == "v1"
    assert session.creative_id == "c1"
    assert session.started_at == "2024-01-01T00:00:00Z"


def test_viewer_id_and_creative_id_survive_intact(session_mapping: SessionMapping) -> None:
    row: RawRow = {
        "id": "s99",
        "viewer_id": "viewer-xyz",
        "creative_id": "creative-abc",
        "started_at": "2025-06-15T12:00:00Z",
    }
    table = session_mapping.transform([row])
    session = table.rows[0]
    assert session.viewer_id == "viewer-xyz"
    assert session.creative_id == "creative-abc"


def test_missing_started_at_defaults_to_unknown(session_mapping: SessionMapping) -> None:
    row: RawRow = {"id": "s2", "viewer_id": "v1", "creative_id": "c1"}
    table = session_mapping.transform([row])
    assert table.rows[0].started_at == "unknown"  # type: ignore[union-attr]


def test_none_started_at_defaults_to_unknown(session_mapping: SessionMapping) -> None:
    row: RawRow = {"id": "s3", "viewer_id": "v1", "creative_id": "c1", "started_at": None}
    table = session_mapping.transform([row])
    assert table.rows[0].started_at == "unknown"  # type: ignore[union-attr]


def test_missing_id_raises_value_error(session_mapping: SessionMapping) -> None:
    row: RawRow = {"viewer_id": "v1", "creative_id": "c1"}
    with pytest.raises(ValueError):
        session_mapping.transform([row])


def test_none_id_raises_value_error(session_mapping: SessionMapping) -> None:
    row: RawRow = {"id": None, "viewer_id": "v1", "creative_id": "c1"}
    with pytest.raises(ValueError):
        session_mapping.transform([row])


def test_missing_viewer_id_raises_value_error(session_mapping: SessionMapping) -> None:
    row: RawRow = {"id": "s1", "creative_id": "c1"}
    with pytest.raises(ValueError):
        session_mapping.transform([row])


def test_none_viewer_id_raises_value_error(session_mapping: SessionMapping) -> None:
    row: RawRow = {"id": "s1", "viewer_id": None, "creative_id": "c1"}
    with pytest.raises(ValueError):
        session_mapping.transform([row])


def test_missing_creative_id_raises_value_error(session_mapping: SessionMapping) -> None:
    row: RawRow = {"id": "s1", "viewer_id": "v1"}
    with pytest.raises(ValueError):
        session_mapping.transform([row])


def test_none_creative_id_raises_value_error(session_mapping: SessionMapping) -> None:
    row: RawRow = {"id": "s1", "viewer_id": "v1", "creative_id": None}
    with pytest.raises(ValueError):
        session_mapping.transform([row])


def test_dedup_first_occurrence_wins(session_mapping: SessionMapping) -> None:
    rows: list[RawRow] = [
        {"id": "s1", "viewer_id": "v1", "creative_id": "c1", "started_at": "2024-01-01T00:00:00Z"},
        {"id": "s1", "viewer_id": "v2", "creative_id": "c2", "started_at": "2024-06-01T00:00:00Z"},
    ]
    table = session_mapping.transform(rows)
    assert len(table.rows) == 1
    session = table.rows[0]
    assert session.viewer_id == "v1"
    assert session.creative_id == "c1"
    assert session.started_at == "2024-01-01T00:00:00Z"


def test_dedup_output_order_is_first_seen(session_mapping: SessionMapping) -> None:
    rows: list[RawRow] = [
        {"id": "s1", "viewer_id": "v1", "creative_id": "c1"},
        {"id": "s2", "viewer_id": "v2", "creative_id": "c2"},
        {"id": "s1", "viewer_id": "v3", "creative_id": "c3"},
        {"id": "s3", "viewer_id": "v4", "creative_id": "c4"},
    ]
    table = session_mapping.transform(rows)
    assert len(table.rows) == 3
    ids = [r.session_id for r in table.rows]  # type: ignore[union-attr]
    assert ids == ["s1", "s2", "s3"]


def test_key_stability_same_input_yields_identical_content(session_mapping: SessionMapping) -> None:
    rows: list[RawRow] = [
        {"id": "s1", "viewer_id": "v1", "creative_id": "c1", "started_at": "2024-01-01T00:00:00Z"},
        {"id": "s2", "viewer_id": "v2", "creative_id": "c2"},
    ]
    t1 = session_mapping.transform(rows)
    t2 = session_mapping.transform(rows)
    assert t1.name == t2.name
    assert t1.key == t2.key
    assert len(t1.rows) == len(t2.rows)
    for r1, r2 in zip(t1.rows, t2.rows):
        assert r1 == r2


def test_result_metadata(session_mapping: SessionMapping) -> None:
    table = session_mapping.transform([_VALID_ROW])
    assert table.name == DIM_SESSION
    assert table.key == "session_id"


def test_empty_input_returns_empty_rows(session_mapping: SessionMapping) -> None:
    table = session_mapping.transform([])
    assert table.rows == ()
    assert table.name == DIM_SESSION
    assert table.key == "session_id"


# ---------------------------------------------------------------------------
# Extract test
# ---------------------------------------------------------------------------

def test_extract_fetches_session_descriptor_rows(
    session_mapping: SessionMapping,
    make_fake_source: Callable,
) -> None:
    # Seed two descriptors with distinct rows; extract must return exactly the
    # SESSION rows — proving the mapping fetched the SESSION descriptor, not VIEWER.
    session_rows: list[RawRow] = [
        {"id": "s1", "viewer_id": "v1", "creative_id": "c1", "started_at": "2024-01-01T00:00:00Z"},
    ]
    viewer_rows: list[RawRow] = [{"id": "v1", "country_code": "US"}]
    source = make_fake_source({
        SourceDescriptor.SESSION: session_rows,
        SourceDescriptor.VIEWER: viewer_rows,
    })
    result = session_mapping.extract(source)
    assert result == session_rows
