from __future__ import annotations

import copy
from collections.abc import Callable

from listinglens.ingestion.payloads.archives import ArchivesIndex

FixtureLoader = Callable[[str], object]


def test_parses_archives_directory_index(load_edgar_fixture: FixtureLoader) -> None:
    raw = load_edgar_fixture("archives_index_aapl.json")
    index = ArchivesIndex.parse(raw, "https://x/archives")
    assert len(index.directory.item) > 0
    first = index.directory.item[0]
    assert first.name
    assert first.type
    assert first.last_modified


def test_size_field_stays_a_raw_string_including_empty_on_real_data(
    load_edgar_fixture: FixtureLoader,
) -> None:
    """A few real Archives rows (index-header meta entries, not real files) carry
    size="" rather than a byte count. size is kept as a plain str, so this parses
    cleanly with no validator needed; this pins that real behavior."""
    raw = load_edgar_fixture("archives_index_aapl.json")
    index = ArchivesIndex.parse(raw, "https://x/archives")
    sizes = [item.size for item in index.directory.item]
    assert any(size == "" for size in sizes)
    assert any(size != "" for size in sizes)


def test_unknown_key_is_visible_but_not_blocking(load_edgar_fixture: FixtureLoader) -> None:
    raw = load_edgar_fixture("archives_index_aapl.json")
    assert isinstance(raw, dict)
    mutated = copy.deepcopy(raw)
    mutated["directory"]["futureField"] = "x"

    index = ArchivesIndex.parse(mutated, "https://x/archives")
    assert index.directory.model_extra is not None
    assert index.directory.model_extra["futureField"] == "x"
