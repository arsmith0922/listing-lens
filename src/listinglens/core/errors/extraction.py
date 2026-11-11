from __future__ import annotations

from listinglens.core.errors.base import ListingLensError


class ExtractionError(ListingLensError):
    """Base class for errors raised by the extraction layer."""


class ConceptNotFound(ExtractionError):
    """No candidate tag for the target is present in the company's facts at all."""

    def __init__(self, target: str, cik: str, tried: tuple[str, ...]) -> None:
        self.target = target
        self.cik = cik
        self.tried = tried
        super().__init__(
            f"No candidate tag for {target!r} is present for CIK {cik} (tried {', '.join(tried)})"
        )


class UnitUnavailable(ExtractionError):
    """The tag is present, but not in the unit this target needs. Never converted."""

    def __init__(
        self,
        target: str,
        cik: str,
        tag: str,
        expected_unit: str,
        available_units: tuple[str, ...],
    ) -> None:
        self.target = target
        self.cik = cik
        self.tag = tag
        self.expected_unit = expected_unit
        self.available_units = available_units
        super().__init__(
            f"{tag!r} for {target!r} (CIK {cik}) has no {expected_unit} facts; "
            f"it is reported in {', '.join(available_units)}"
        )


class PeriodUnavailable(ExtractionError):
    """The tag has the unit, but no fact fits the period kind (for example only quarterly flows)."""

    def __init__(
        self, target: str, cik: str, tag: str, expected_unit: str, period_kind: str
    ) -> None:
        self.target = target
        self.cik = cik
        self.tag = tag
        self.expected_unit = expected_unit
        self.period_kind = period_kind
        super().__init__(
            f"{tag!r} for {target!r} (CIK {cik}) has {expected_unit} facts but none that are "
            f"a usable {period_kind} period"
        )


class SectionNotFound(ExtractionError):
    def __init__(self, section_label: str, accession_no: str) -> None:
        self.section_label = section_label
        self.accession_no = accession_no
        super().__init__(f"Section {section_label!r} not found in filing {accession_no}")
