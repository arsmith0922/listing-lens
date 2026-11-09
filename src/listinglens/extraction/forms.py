from __future__ import annotations

# Which filing forms a fact may come from (D51, refining D31). The forms are SEC identifiers, never
# free text, and the lists are checked against the facts of 51 sampled companies.

# The annual, quarterly and transition reports, with their amendments (restatements arrive as
# amendments: D31 pins a 10-Q/A that restates a 10-Q). A figure is cited to one of these whenever
# one carries the value. The forms are the SEC's: 10-KT and 10-QT are transition reports under
# Rule 13a-10 or 15d-10, 20-F is the foreign private issuer's annual and transition report, and
# 40-F the certain Canadian issuers' annual report (https://sec-edgar.github.io/sec-edgar/
# filingtypes.html, from EDGAR's form-type list). 6-K is not here: it is a current report. The
# forms found in the six recorded fixtures are 10-K, 10-Q, 10-Q/A, 20-F and 20-F/A.
PERIODIC_FORMS = frozenset(
    {
        "10-K",
        "10-K/A",
        "10-KT",
        "10-KT/A",
        "10-Q",
        "10-Q/A",
        "10-QT",
        "10-QT/A",
        "20-F",
        "20-F/A",
        "40-F",
        "40-F/A",
    }
)

# Proxy, information-statement and going-private filings: they excerpt the financial statements
# (the pay-versus-performance table of a DEF 14A repeats net income rounded, in the wrong scale, or
# as another measure) and are never a source of a figure. Evidence, 51 sampled companies, facts
# with a periodic counterpart at the identical period: DEF 14A 399 facts, 49.1 percent differ
# (MacroGenics -74,620 against its 10-K's -74,620,000); PRE 14A 60 facts, 28.6 percent differ;
# registration statements and 8-Ks repeat the audited numbers (S-1 1.6, POS AM 1.9, F-1 0, 8-K 0
# percent differ), so they stay eligible, and so does S-8, a registration statement like them
# with no evidence of its own. The family is EDGAR's: DEF 14A, PRE 14A, DEFR14A and PRER14A
# (revised), DEFA14A (additional), DEFM14A and PREM14A (merger), DEF 14C, PRE 14C, DEFR14C and
# PRER14C (information statements) and SC 13E3 (going private), as listed at
# https://sec-edgar.github.io/sec-edgar/filingtypes.html. The contested and non-management
# solicitation forms and the exempt-solicitation notices are left out: no evidence, and the
# list fails open to today's behavior.
EXCERPT_FORMS = frozenset(
    {
        "DEF 14A",
        "PRE 14A",
        "DEFR14A",
        "PRER14A",
        "DEFA14A",
        "DEFM14A",
        "PREM14A",
        "DEF 14C",
        "PRE 14C",
        "DEFR14C",
        "PRER14C",
        "SC 13E3",
    }
)


def is_periodic(form: str) -> bool:
    return form in PERIODIC_FORMS
