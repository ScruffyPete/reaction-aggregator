from collections.abc import Callable

import pytest

from app.adapters.fake_source import FakeSource
from app.domain.mappings.viewer import ViewerMapping
from app.domain.models import DIM_VIEWER, Viewer
from app.domain.ports.source import RawRow, SourceDescriptor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def viewer_mapping() -> ViewerMapping:
    return ViewerMapping()


# ---------------------------------------------------------------------------
# Transform tests
# ---------------------------------------------------------------------------

def test_happy_path(viewer_mapping: ViewerMapping) -> None:
    rows = [{"id": "v1", "age_bracket": "25-34", "gender": "female", "country_code": "DE"}]
    table = viewer_mapping.transform(rows)
    assert len(table.rows) == 1
    viewer = table.rows[0]
    assert isinstance(viewer, Viewer)
    assert viewer.viewer_id == "v1"
    assert viewer.age_bracket == "25-34"
    assert viewer.gender == "female"
    assert viewer.country == "DE"


def test_missing_optional_fields_default_to_unknown(viewer_mapping: ViewerMapping) -> None:
    rows = [{"id": "v2"}]
    table = viewer_mapping.transform(rows)
    viewer = table.rows[0]
    assert viewer.age_bracket == "unknown"
    assert viewer.gender == "unknown"
    assert viewer.country == "unknown"


def test_none_optional_fields_default_to_unknown(viewer_mapping: ViewerMapping) -> None:
    rows = [{"id": "v3", "age_bracket": None, "gender": None, "country_code": None}]
    table = viewer_mapping.transform(rows)
    viewer = table.rows[0]
    assert viewer.age_bracket == "unknown"
    assert viewer.gender == "unknown"
    assert viewer.country == "unknown"


def test_missing_id_raises_value_error(viewer_mapping: ViewerMapping) -> None:
    rows = [{"age_bracket": "18-24"}]
    with pytest.raises(ValueError):
        viewer_mapping.transform(rows)


def test_none_id_raises_value_error(viewer_mapping: ViewerMapping) -> None:
    rows = [{"id": None, "age_bracket": "18-24"}]
    with pytest.raises(ValueError):
        viewer_mapping.transform(rows)


def test_dedup_first_occurrence_wins(viewer_mapping: ViewerMapping) -> None:
    rows = [
        {"id": "v1", "age_bracket": "25-34", "gender": "male", "country_code": "US"},
        {"id": "v1", "age_bracket": "35-44", "gender": "female", "country_code": "GB"},
    ]
    table = viewer_mapping.transform(rows)
    assert len(table.rows) == 1
    viewer = table.rows[0]
    assert viewer.age_bracket == "25-34"
    assert viewer.gender == "male"
    assert viewer.country == "US"


def test_dedup_output_length_and_order_stable(viewer_mapping: ViewerMapping) -> None:
    rows = [
        {"id": "a", "country_code": "US"},
        {"id": "b", "country_code": "FR"},
        {"id": "a", "country_code": "DE"},
        {"id": "c", "country_code": "JP"},
    ]
    table = viewer_mapping.transform(rows)
    assert len(table.rows) == 3
    ids = [v.viewer_id for v in table.rows]
    assert ids == ["a", "b", "c"]


def test_key_stability(viewer_mapping: ViewerMapping) -> None:
    rows = [{"id": "v1", "age_bracket": "25-34", "gender": "male", "country_code": "US"}]
    table1 = viewer_mapping.transform(rows)
    table2 = viewer_mapping.transform(rows)
    assert table1.rows[0].model_dump() == table2.rows[0].model_dump()


def test_result_metadata(viewer_mapping: ViewerMapping) -> None:
    table = viewer_mapping.transform([{"id": "v1"}])
    assert table.name == DIM_VIEWER
    assert table.key == "viewer_id"


def test_empty_input(viewer_mapping: ViewerMapping) -> None:
    table = viewer_mapping.transform([])
    assert table.rows == ()
    assert table.name == DIM_VIEWER
    assert table.key == "viewer_id"


def test_country_code_renamed_to_country(viewer_mapping: ViewerMapping) -> None:
    rows = [{"id": "v1", "country_code": "JP"}]
    table = viewer_mapping.transform(rows)
    viewer = table.rows[0]
    assert viewer.country == "JP"


# ---------------------------------------------------------------------------
# Extract test
# ---------------------------------------------------------------------------

def test_extract_fetches_viewer_descriptor_rows(
    viewer_mapping: ViewerMapping,
    make_fake_source: Callable,
) -> None:
    # Seed two descriptors with distinct rows; extract must return exactly the
    # VIEWER rows — proving the mapping fetched the VIEWER descriptor, not SESSION.
    viewer_rows: list[RawRow] = [{"id": "v1", "country_code": "US"}]
    session_rows: list[RawRow] = [{"id": "s1", "viewer_id": "v1", "creative_id": "c1"}]
    source = make_fake_source({
        SourceDescriptor.VIEWER: viewer_rows,
        SourceDescriptor.SESSION: session_rows,
    })
    result = viewer_mapping.extract(source)
    assert result == viewer_rows
