from __future__ import annotations

from collections.abc import Sequence

from listinglens.domain.pathway import Pathway
from listinglens.routes.models import CandidateSet, Settlement

# How step 4 settles a candidate set (D78): only with a cited match. The route layer never reads
# filing text; this is the rule step 4's phrase search must pass.


def _accepted(candidates: CandidateSet, settlement: Settlement) -> bool:
    """The settlement names one of its route's phrases in this set, the match's anchor text is
    that phrase (ignoring case), and the match lies in the primary document of a filing of a role
    the phrase is looked for in. An exhibit can carry either route's phrase, so it never counts."""
    match = settlement.match
    for phrase in candidates.settle_by:
        if (phrase.route, phrase.phrase) != (settlement.route, settlement.phrase):
            continue
        if match.anchor_text.casefold() != phrase.phrase.casefold():
            return False
        return any(
            document.role in phrase.roles
            and document.filing.accession_no == match.accession_no
            and document.filing.cik == match.cik
            and document.primary_document is not None
            and document.primary_document == match.document_name
            for document in candidates.documents
        )
    return False


def settle(candidates: CandidateSet, settlements: Sequence[Settlement]) -> Pathway | None:
    """The one route every accepted settlement names, or None: settlements for two routes, or
    none accepted, leave the candidates as they are."""
    accepted = {s.route for s in settlements if _accepted(candidates, s)}
    if len(accepted) != 1:
        return None
    return next(iter(accepted))
