"""The registry is consistent with itself and with the source modules."""

from pipeline.registry import SERIES, SOURCES
from pipeline.sources import SOURCE_IDS


def test_every_source_has_series_and_a_description():
    assert tuple(SOURCES) == SOURCE_IDS
    assert {s.source for s in SERIES.values()} == set(SOURCE_IDS)


def test_series_fields_are_valid():
    for sid, s in SERIES.items():
        assert s.id == sid and sid == sid.lower() and " " not in sid
        assert s.freq in ("D", "M", "A", "E"), sid
        assert s.revision.kind in ("relative", "absolute", "exact", "accept"), sid
        assert s.bounds[0] < s.bounds[1], sid
        assert s.label and s.units, sid


def test_only_bom_data_is_kept_off_the_download_page():
    private = {sid for sid, s in SERIES.items() if not s.redistribute}
    assert private == {sid for sid, s in SERIES.items() if s.source == "bom"}
