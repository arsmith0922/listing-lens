from __future__ import annotations

from datetime import date

from listinglens.memo import vocab
from listinglens.memo.citations import RuleCite, SecRecordCite, XbrlCite
from listinglens.tools.models_financials import XbrlCitationView
from listinglens.tools.models_rule import RuleCitationView

# The citations of the memo, made from the tools' views (D65). Nothing is added or guessed: a
# view's fields are copied, and the record citations are made from the company's CIK and the
# parts of a filing row the result holds.


def xbrl_cite(view: XbrlCitationView) -> XbrlCite:
    return XbrlCite.model_validate(view.model_dump())


def rule_cite(view: RuleCitationView) -> RuleCite:
    return RuleCite(
        section=view.section,
        url=view.url,
        quoted_text=view.quoted_text,
        retrieved_on=view.retrieved_on,
        sec_release=view.sec_release,
        sec_release_url=view.sec_release_url,
    )


def record_cite(
    cik: str,
    record: vocab.SecRecord,
    field: vocab.SecField,
    *,
    accession_no: str | None = None,
    form_type: str | None = None,
    filed_date: date | None = None,
    index_url: str | None = None,
) -> SecRecordCite:
    return SecRecordCite(
        cik=cik,
        record=record,
        field=field,
        accession_no=accession_no,
        form_type=form_type,
        filed_date=filed_date,
        index_url=index_url,
    )
