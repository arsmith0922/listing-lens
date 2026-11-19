"""Every field of the four tool results and their nested views, and what the memo does with it
(D65, the executable E1). One line per field: `Model.field | disposition`. A disposition starts
with a word: fact (carried as, or in, a fact value, id or rest), citation (carried in a citation),
context (carried in the run context), check (read to check the results agree, then not carried),
nested (a container whose own fields have lines) or dropped (with the reason). The test fails when
a field exists without a line, or a line names a field that does not exist."""

from __future__ import annotations

LINES = """
ResultBase.company | nested
ResultBase.evaluated_on | context in the check result only (the rules date)
ResultBase.scope_note | check against the pinned text; the renderer prints it
CompanyEcho.cik | fact company.cik
CompanyEcho.issuer_name | fact company.name
CompanyEcho.resolved_from | dropped: how the caller named the company, which may be caller text
ResolvedFrom.kind | dropped: how the caller named the company, which may be caller text
ResolvedFrom.value | dropped: how the caller named the company, which may be caller text
ResolveCompanyResult.company | nested
ResolveCompanyResult.evaluated_on | dropped: only the check result date is the rules date
ResolveCompanyResult.scope_note | check against the pinned text
ResolveCompanyResult.tickers | fact company.ticker, one per distinct value
ResolveCompanyResult.exchanges | fact company.exchange, one per distinct value
ResolveCompanyResult.entity_type | fact company.entity_type
ListFilingsResult.company | nested
ListFilingsResult.evaluated_on | dropped: only the check result date is the rules date
ListFilingsResult.scope_note | check against the pinned text
ListFilingsResult.forms_filter | context forms_filter
ListFilingsResult.returned | fact count filings.returned
ListFilingsResult.total_matching | fact count filings.total_matching
ListFilingsResult.omitted | fact count filings.omitted
ListFilingsResult.filings | nested
FilingView.accession_no | fact filing id; citation
FilingView.form_type | fact filing
FilingView.filed_date | fact filing
FilingView.report_date | fact filing
FilingView.acceptance_datetime | dropped: a time of day the memo does not use
FilingView.primary_document | dropped: a filer-supplied file name, which is the reader later
FilingView.index_url | citation of the filing row
ExtractFinancialsResult.company | nested
ExtractFinancialsResult.evaluated_on | dropped: only the check result date is the rules date
ExtractFinancialsResult.scope_note | check against the pinned text
ExtractFinancialsResult.facts_status | fact data_status; check equal to the check result
ExtractFinancialsResult.latest_fiscal_year | nested
ExtractFinancialsResult.figures | nested
ExtractFinancialsResult.gaps | nested
FiscalYearView.end | fact fiscal_year
FiscalYearView.accession_no | citation of the anchor
FiscalYearView.form_type | citation of the anchor
FigureView.concept | fact figure; id
FigureView.value | fact figure amount
FigureView.unit | fact figure
FigureView.period | fact figure; id
FigureView.citation | citation xbrl
FigureView.is_convenience_translation | fact figure translation
FigureView.reported_twins | fact figure twins
FigureView.corroborated_by | fact figure basis
FigureView.diagnostics | fact figure disagreements (kinds only)
PeriodView.kind | fact figure period
PeriodView.instant | fact figure period
PeriodView.start | fact figure period
PeriodView.end | fact figure period
XbrlCitationView.cik | citation xbrl
XbrlCitationView.taxonomy | citation xbrl
XbrlCitationView.concept | citation xbrl
XbrlCitationView.unit | citation xbrl
XbrlCitationView.period | citation xbrl
XbrlCitationView.accession_no | citation xbrl
XbrlCitationView.form_type | citation xbrl
XbrlCitationView.fiscal_year | citation xbrl; count fiscal_years.with_figures
XbrlCitationView.fiscal_period | citation xbrl
XbrlCitationView.source | citation xbrl
TwinView.unit | fact figure twins
TwinView.value | fact figure twins
TwinView.period | dropped: always the figure own period
TwinView.implied_rate | fact figure twins
IdentityEvidenceView.pretax_tag | dropped: a tag name, which is filer data
IdentityEvidenceView.pretax_value | dropped: the pretax income is its own figure
IdentityEvidenceView.tax_tag | dropped: a tag name, which is filer data
IdentityEvidenceView.tax_value | dropped: a detail of how the stand-in was checked
IdentityEvidenceView.witness | dropped: the figure carries only that it stands in by identity
RestatementView.kind | fact figure disagreements
RestatementView.concept | dropped: the figure it sits on carries the concept
RestatementView.tag | dropped: a tag name, which is filer data
RestatementView.unit | dropped: detail of the disagreement, carried as a kind only
RestatementView.period | dropped: detail of the disagreement, carried as a kind only
RestatementView.selected | dropped: no full locator for an observation
RestatementView.others | dropped: no full locator for an observation
ObservationView.value | dropped: no full locator for an observation
ObservationView.accession_no | dropped: no full locator for an observation
ObservationView.form_type | dropped: no full locator for an observation
ObservationView.filed | dropped: no full locator for an observation
CrossTagView.kind | fact figure disagreements
CrossTagView.concept | dropped: the figure it sits on carries the concept
CrossTagView.period | dropped: detail of the disagreement, carried as a kind only
CrossTagView.selected_tag | dropped: a tag name, which is filer data
CrossTagView.selected_value | dropped: detail of the disagreement, carried as a kind only
CrossTagView.other_tag | dropped: a tag name, which is filer data
CrossTagView.other_value | dropped: detail of the disagreement, carried as a kind only
GapView.concept | fact gap
GapView.reason | fact gap
GapView.detail | dropped: it lists tag names, which are filer data
CheckStandardsResult.company | nested
CheckStandardsResult.evaluated_on | context evaluated_on and rules_as_of
CheckStandardsResult.scope_note | check against the pinned text
CheckStandardsResult.listing_type | context
CheckStandardsResult.pathway | context
CheckStandardsResult.requested_tier | context; check the tiers are the tier asked for
CheckStandardsResult.facts_status | check equal to the extract result
CheckStandardsResult.tier_source | nested
CheckStandardsResult.nasdaq_status | nested
CheckStandardsResult.tiers | nested
TierSourceReport.how | context tier_how
TierSourceReport.tickers_tried | dropped: the company tickers are company facts
TierSourceReport.sec_exchanges | dropped: the company exchanges are company facts
TierSourceReport.directory | nested
TierSourceReport.matches | nested
TierSourceReport.test_issues_ignored | context
TierSourceReport.note | dropped: fixed text of the tool
DirectoryOutcomeView.available | context directory
DirectoryOutcomeView.url | dropped: a constant, held by the directory citation
DirectoryOutcomeView.stamp | context directory
DirectoryOutcomeView.file_sha256 | context directory
DirectoryOutcomeView.error | dropped: free text about a failure; the context holds availability
DirectoryStampView.raw | context directory
DirectoryStampView.zone | dropped: a constant, not stated
DirectoryMatchView.ticker | check joined to the status row by symbol
DirectoryMatchView.category_code | dropped: the status row carries it
DirectoryMatchView.tier | dropped: the status row carries it
DirectoryMatchView.etf | fact nasdaq_status etf
NasdaqStatusView.symbol | fact nasdaq_status; id
NasdaqStatusView.category_code | fact nasdaq_status market_category
NasdaqStatusView.category_tier | fact nasdaq_status tier
NasdaqStatusView.status_code | fact nasdaq_status financial_status and status
NasdaqStatusView.status_meaning | dropped: the exchange wording, replaced by the status slug
NasdaqStatusView.meaning_source | dropped: a constant page address
NasdaqStatusView.note | dropped: fixed text of the tool
NasdaqStatusView.citation | citation directory
DirectoryCitationView.kind | citation directory
DirectoryCitationView.url | citation directory
DirectoryCitationView.file_created | citation directory
DirectoryCitationView.file_sha256 | citation directory
DirectoryCitationView.symbol | citation directory
DirectoryCitationView.security_name | citation directory
DirectoryCitationView.market_category | citation directory
DirectoryCitationView.financial_status | citation directory
TierView.tier | fact tier of every rule fact and id of the tier facts
TierView.selected_by_tickers | dropped: how the tier was chosen is in the context
TierView.rules_in_force | context tiers_without_rules; no facts when false
TierView.note | dropped: fixed text of the tool
TierView.reported_financials | fact reported_financials
TierView.reported_financials_caveat | nested
TierView.findings | nested
TierView.common | nested
TierView.standards | nested
TierView.not_measured | nested
TierView.translated_figures | dropped: each entry is a figure fact twin already carried
TierView.verdict | nested
FinancialCaveatView.absent_concepts | fact financial_caveat
FinancialCaveatView.needs_multi_year | fact financial_caveat
FinancialCaveatView.needs_year_end_balance | fact financial_caveat
FinancialCaveatView.stale_concepts | fact financial_caveat
FinancialCaveatView.tests_no_filed_figure | fact financial_caveat
FindingView.rule_id | fact finding; id
FindingView.rule_section | fact finding
FindingView.standard_id | fact finding
FindingView.standard_name | dropped: the standard-level condition carries the name
FindingView.requirement | fact finding
FindingView.branch | fact finding
FindingView.measures_kind | fact finding
FindingView.measures | fact finding
FindingView.measured | fact finding
FindingView.unit | fact finding
FindingView.threshold | fact finding
FindingView.comparison | fact finding
FindingView.window | fact finding
FindingView.state | fact finding
FindingView.headroom | fact finding
FindingView.headroom_ratio | fact finding
FindingView.cushion_ratio | fact finding
FindingView.figure_citation | citation xbrl; fact finding figure link
FindingView.rule_citation | citation rule
FindingView.rule_verified | fact finding
FindingView.translations | fact finding translated flag
WindowView.kind | fact finding and not_measured window
WindowView.n | fact finding and not_measured window
WindowView.m | fact finding and not_measured window
WindowView.years | fact finding and not_measured window
RuleCitationView.section | citation rule
RuleCitationView.url | citation rule
RuleCitationView.quoted_text | citation rule
RuleCitationView.retrieved_on | citation rule
RuleCitationView.sec_release | citation rule
RuleCitationView.sec_release_url | citation rule
TranslationView.unit | dropped: the figure fact carries the twins, the finding a flag
TranslationView.value | dropped: the figure fact carries the twins, the finding a flag
TranslationView.implied_rate | dropped: the figure fact carries the twins, the finding a flag
RequirementView.key | fact condition_status requirement
RequirementView.value | nested
RequirementView.thin | nested
RequirementView.branches | nested
BranchView.name | fact condition_status branch
BranchView.value | fact condition_status
BranchView.thin | fact condition_status
BranchView.rule_ids | fact condition_status rests_on
StandardView.standard_id | fact condition_status; id
StandardView.name | fact condition_status standard_name
StandardView.value | fact condition_status
StandardView.thin | fact condition_status
StandardView.reported_financials | fact condition_status
StandardView.requirements | nested
NotMeasuredView.rule_id | fact not_measured; id
NotMeasuredView.rule_section | fact not_measured
NotMeasuredView.standard_id | fact not_measured
NotMeasuredView.standard_name | dropped: the standard-level condition carries the name
NotMeasuredView.requirement | fact not_measured
NotMeasuredView.branch | fact not_measured
NotMeasuredView.measures_kind | fact not_measured
NotMeasuredView.measures | fact not_measured
NotMeasuredView.threshold | fact not_measured
NotMeasuredView.comparison | fact not_measured
NotMeasuredView.window | fact not_measured
NotMeasuredView.unit | fact not_measured
NotMeasuredView.reasons | nested
NotMeasuredView.primary | fact not_measured
NotMeasuredView.missing_inputs | fact not_measured
NotMeasuredView.rule_citation | citation rule
NotMeasuredView.rule_verified | fact not_measured
ReasonView.kind | fact not_measured reasons; citation companyfacts for concept_absent
ReasonView.detail | dropped: free text that can hold a tag name
ReasonView.gap_reason | fact not_measured reasons
TranslatedFigureView.figure_citation | dropped: each entry is a figure fact twin already carried
TranslatedFigureView.translations | dropped: each entry is a figure fact twin already carried
VerdictView.verdict | fact verdict
VerdictView.value | fact verdict
VerdictView.thin | fact verdict
VerdictView.caveat | nested
CaveatView.missing_inputs | fact verdict_caveat
CaveatView.absent_concepts | fact verdict_caveat
CaveatView.needs_multi_year | fact verdict_caveat
CaveatView.needs_year_end_balance | fact verdict_caveat
CaveatView.stale_concepts | fact verdict_caveat
"""
