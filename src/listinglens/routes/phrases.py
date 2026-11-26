from __future__ import annotations

from typing import Final

from listinglens.domain.pathway import Pathway
from listinglens.routes.models import Reason, Role, SettlingPhrase

# The candidates of each reason, why form types cannot separate them, and the fixed phrases that
# would settle them (D78). Every phrase is provisional: step 4 calibrates each on recorded
# documents before it is frozen. Nothing in the route layer searches text for them.
ROUTES: Final[dict[Reason, tuple[Pathway, ...]]] = {
    "offering_forms_alike": (Pathway.TRADITIONAL_IPO, Pathway.DIRECT_LISTING),
    "blank_check_before_listing": (Pathway.SPAC_IPO, Pathway.TRADITIONAL_IPO),
    "merger_partner_unknown": (Pathway.DE_SPAC, Pathway.REVERSE_MERGER),
}
BECAUSE: Final[dict[Reason, str]] = {
    "offering_forms_alike": (
        "A traditional IPO and a direct listing file the same forms (a registration statement "
        "and its amendments, the exchange registration and its certification, the notice of "
        "effectiveness and a final prospectus), so form types cannot tell them apart."
    ),
    "blank_check_before_listing": (
        "A blank-check company's offering files the same forms as any other, and only one whose "
        "class lists on an exchange is a SPAC, so until that listing takes effect form types "
        "cannot tell them apart. No phrase settles it as a traditional IPO: the listing's taking "
        "effect settles it as a SPAC IPO."
    ),
    "merger_partner_unknown": (
        "A merger registration (Form S-4 or F-4) is filed for a merger with a SPAC and for other "
        "mergers alike, and the SEC records read here do not show that the merger partner was a "
        "listed blank-check company, so form types cannot tell them apart."
    ),
}
_OFFERING: Final[tuple[Role, ...]] = ("registration_statement", "final_prospectus")
_MERGER: Final[tuple[Role, ...]] = ("merger_registration", "merger_prospectus")


def _phrase(route: Pathway, phrase: str, roles: tuple[Role, ...]) -> SettlingPhrase:
    return SettlingPhrase(route=route, phrase=phrase, roles=roles, status="provisional")


PHRASES: Final[dict[Reason, tuple[SettlingPhrase, ...]]] = {
    "offering_forms_alike": (
        _phrase(Pathway.DIRECT_LISTING, "direct listing", _OFFERING),
        _phrase(Pathway.TRADITIONAL_IPO, "underwriting discounts and commissions", _OFFERING),
    ),
    "blank_check_before_listing": (
        _phrase(Pathway.SPAC_IPO, "trust account", ("registration_statement",)),
    ),
    "merger_partner_unknown": (
        _phrase(Pathway.DE_SPAC, "special purpose acquisition company", _MERGER),
        _phrase(Pathway.DE_SPAC, "trust account", _MERGER),
        _phrase(Pathway.REVERSE_MERGER, "reverse merger", _MERGER),
    ),
}
