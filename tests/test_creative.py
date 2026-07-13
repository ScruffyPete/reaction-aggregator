import pytest
from collections.abc import Callable

from app.domain.mappings.creative import CreativeMapping
from app.domain.models import DIM_CREATIVE
from app.domain.ports.source import RawRow, SourceDescriptor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def creative_mapping() -> CreativeMapping:
    return CreativeMapping()


# ---------------------------------------------------------------------------
# Transform tests
# ---------------------------------------------------------------------------

def test_happy_path(creative_mapping: CreativeMapping) -> None:
    rows = [{"id": "c1", "title": "Ad One", "brand": "Acme", "duration_ms": 3000}]
    result = creative_mapping.transform(rows)
    creative = result.rows[0]
    assert creative.creative_id == "c1"
    assert creative.title == "Ad One"
    assert creative.brand == "Acme"
    assert creative.duration_ms == 3000


def test_missing_title_brand_become_unknown(creative_mapping: CreativeMapping) -> None:
    rows = [{"id": "c2"}]
    result = creative_mapping.transform(rows)
    creative = result.rows[0]
    assert creative.title == "unknown"
    assert creative.brand == "unknown"


def test_none_title_brand_become_unknown(creative_mapping: CreativeMapping) -> None:
    rows = [{"id": "c3", "title": None, "brand": None}]
    result = creative_mapping.transform(rows)
    creative = result.rows[0]
    assert creative.title == "unknown"
    assert creative.brand == "unknown"


def test_missing_duration_ms_is_none(creative_mapping: CreativeMapping) -> None:
    rows = [{"id": "c4", "title": "T", "brand": "B"}]
    result = creative_mapping.transform(rows)
    assert result.rows[0].duration_ms is None


def test_none_duration_ms_is_none(creative_mapping: CreativeMapping) -> None:
    rows = [{"id": "c5", "title": "T", "brand": "B", "duration_ms": None}]
    result = creative_mapping.transform(rows)
    assert result.rows[0].duration_ms is None


def test_missing_id_raises(creative_mapping: CreativeMapping) -> None:
    with pytest.raises(ValueError):
        creative_mapping.transform([{"title": "T"}])


def test_none_id_raises(creative_mapping: CreativeMapping) -> None:
    with pytest.raises(ValueError):
        creative_mapping.transform([{"id": None, "title": "T"}])


def test_dedup_keeps_first_occurrence(creative_mapping: CreativeMapping) -> None:
    rows = [
        {"id": "c6", "title": "First", "brand": "B1", "duration_ms": 1000},
        {"id": "c6", "title": "Second", "brand": "B2", "duration_ms": 2000},
    ]
    result = creative_mapping.transform(rows)
    assert len(result.rows) == 1
    assert result.rows[0].title == "First"
    assert result.rows[0].brand == "B1"
    assert result.rows[0].duration_ms == 1000


def test_dedup_output_order_stable(creative_mapping: CreativeMapping) -> None:
    rows = [
        {"id": "c7", "title": "Seven"},
        {"id": "c8", "title": "Eight"},
        {"id": "c7", "title": "Seven Again"},
        {"id": "c9", "title": "Nine"},
    ]
    result = creative_mapping.transform(rows)
    ids = [c.creative_id for c in result.rows]
    assert ids == ["c7", "c8", "c9"]


def test_key_stability(creative_mapping: CreativeMapping) -> None:
    rows = [{"id": "c10", "title": "Stable", "brand": "S", "duration_ms": 500}]
    result1 = creative_mapping.transform(rows)
    result2 = creative_mapping.transform(rows)
    assert result1.name == result2.name
    assert result1.key == result2.key
    assert len(result1.rows) == len(result2.rows)
    c1, c2 = result1.rows[0], result2.rows[0]
    assert c1.creative_id == c2.creative_id
    assert c1.title == c2.title
    assert c1.brand == c2.brand
    assert c1.duration_ms == c2.duration_ms


def test_result_metadata(creative_mapping: CreativeMapping) -> None:
    rows = [{"id": "c11"}]
    result = creative_mapping.transform(rows)
    assert result.name == DIM_CREATIVE
    assert result.key == "creative_id"


def test_empty_input_raises(creative_mapping: CreativeMapping) -> None:
    with pytest.raises(ValueError):
        creative_mapping.transform([])


# ---------------------------------------------------------------------------
# Extract test
# ---------------------------------------------------------------------------

def test_extract_fetches_creative_descriptor_rows(
    creative_mapping: CreativeMapping,
    make_mock_source: Callable,
) -> None:
    # Seed two descriptors with distinct rows; extract must return exactly the
    # CREATIVE rows — proving the mapping fetched the CREATIVE descriptor, not VIEWER.
    creative_rows: list[RawRow] = [{"id": "c12", "title": "Canned"}]
    viewer_rows: list[RawRow] = [{"id": "v1", "country_code": "US"}]
    source = make_mock_source({
        SourceDescriptor.CREATIVE: creative_rows,
        SourceDescriptor.VIEWER: viewer_rows,
    })
    result = creative_mapping.extract(source)
    assert result == creative_rows
