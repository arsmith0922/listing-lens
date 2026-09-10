# Decisions

A running log of architecture and design decisions: what was chosen, why, and what to revisit. Newest first.

## Template
- Date:
- Decision:
- Options considered:
- Why:
- Revisit if:

---

## Phase 1 decisions

Decided during the Phase 1 ingestion-client investigation, after probing the live SEC EDGAR APIs rather than trusting the Phase 0 brief's literal wording.

### D18: pydantic mypy plugin adopted; typed models expose a strict constructor plus a parse() classmethod for untrusted input
- Date: 2026-09-10
- Decision: The pydantic mypy plugin is enabled project-wide (plugins = ["pydantic.mypy"]) with init_typed = true and init_forbid_extra = true. Typed value models (the identifiers) therefore expose two entry points: the plain field constructor for already-clean typed values, and a parse(raw: object) -> Self classmethod that validates arbitrary external input and raises a typed InputValidationError. Untrusted or external input goes through parse(); internal typed code uses the constructor.
- Options considered: Widen field types (for example Cik.value: int | str) or scatter per-call type ignores to keep one flexible constructor (rejected: reintroduces the coercion and the untyped surface the plugin exists to remove); adopt the plugin and split the API (chosen).
- Why: disallow_any_explicit flags every BaseModel subclass because pydantic's own BaseModel.__init__ is typed with an explicit Any; the plugin's synthesized per-model __init__ removes that. init_typed then makes the constructor reject loose input at type-check time, which is the reject-not-coerce rule enforced statically. The parse() split gives untrusted input one explicit validating doorway. Chunks 6 and 7 must follow this convention for any new typed model that ingests external data.
- Revisit if: A model needs a genuinely open or polymorphic input shape that the two-entry-point pattern cannot express cleanly.

### D17: No FastAPI dependency in Phase 1
- Date: 2026-09-06
- Decision: Phase 1 adds no FastAPI application or HTTP framework, even though FastAPI is listed in the project stack.
- Options considered: Scaffold a FastAPI app now so it exists when needed later; add it only when a transport actually needs it.
- Why: The approved MCP transport is local stdio (D2), and nothing before a remote deployment needs an HTTP app. Adding FastAPI now would be dead code with no caller.
- Revisit if: Remote MCP transport (see D2) is scheduled and needs an HTTP entry point.

### D16: Citation model deferred to Phase 2
- Date: 2026-09-06
- Decision: `domain/citation.py` and the `Citation` discriminated union (D5) are not implemented in Phase 1, despite being listed in the Phase 0 MCP tool contracts.
- Options considered: Define the citation shape now from the brief's description; wait until the first real extraction service exists.
- Why: Nothing in Phase 1 emits a citation. `Pathway` is defined now (D14 note below) because the enum is fixed and reused unchanged everywhere; `Citation`'s exact shape should instead be driven by the first real `XbrlLocator`/`TextLocator` use in Phase 2's extraction layer, not guessed in advance.
- Revisit if: Phase 2 extraction work begins.

### D15: Known-failing baseline is a session hook over real unhandled edge cases, not a test-observed comparison
- Date: 2026-09-06
- Decision: The CLAUDE.md-required "recorded known-failing baseline" for Phase 1 is `xfail_strict = true` plus a small git-tracked `tests/known_failing.txt`, compared in a `pytest_sessionfinish` hook gated to full-suite runs. It lists exactly three genuinely unimplemented items: legacy non-UTF-8 document decoding, name-to-CIK resolution for issuers absent from `company_tickers.json`, and EFTS `search_after` deep pagination beyond the roughly 9,900-result cap.
- Options considered: A pytest test that compares the baseline file to the live xfail set (rejected: a test cannot observe the outcomes of tests that have not yet run, so this is not implementable as a test); a broader baseline that also xfails `filings.files` pagination overflow, pre-2001 full-text-search coverage, and ambiguous ticker resolution (rejected: verified live that overflow must be implemented in Phase 1 since it is the common case for the target long-history dataset, that pre-2001 EFTS queries return HTTP 200 with zero hits, a silent wrong answer that needs a typed `OutsideFullTextCoverage` guard rather than an xfail, and that ambiguous ticker resolution should be a passing test asserting a typed ambiguous result); an empty baseline (rejected: proves nothing until populated, and the three items above are real known gaps worth recording now).
- Why: `xfail_strict` already delivers the requirement that matters, an XPASS fails the run, so drift toward silently regressing is caught. The baseline file's only added value is documenting genuinely unbuilt capability, so it should contain only that.
- Revisit if: The baseline grows past about five items, at which point the mechanism itself should be reconsidered.

### D14: Form-agnostic ingestion
- Date: 2026-09-06
- Decision: The ingestion layer accepts filing form types (`forms: frozenset[str]`) as a caller parameter and hardcodes no IPO form set. Foreign-issuer forms (the F-series: `F-1`, `F-1/A`, `F-1MEF`, plus `DRS`, `DRSLTR`, `CORRESP`, `UPLOAD`, `20-F`, `6-K`) are supported from Phase 1, not deferred to Phase 7 as the Phase 0 brief's literal "S-1 or 424B" scoping implied.
- Options considered: Hardcode an `IPO_FORMS` constant (`S-1`, `424B`) inside the ingestion layer per the brief's literal wording; accept forms as a caller-supplied parameter with no hardcoded set (chosen).
- Why: Three reasons, in order of weight.
  1. Ingestion stays interpretation-free. Deciding that `F-1` and `424B4` constitute "the IPO path" while `424B2` usually does not (it is typically a shelf takedown, not an IPO prospectus) is a classification judgment. It belongs in the analysis layer's `PathwayClassifier`, not in a transport client. A hardcoded form set would be exactly the kind of interpretation leak the onion architecture (see project-level architecture notes) is meant to prevent.
  2. The foreign-private-issuer population needs the F-series now, not in Phase 7. Verified live against Luckin Coffee (CIK 1767582), the canonical China fraud and delisting case and the deepest part of the project's stated moat: its complete filing history contains zero `S-1` filings. It filed `F-1`, `F-1/A`, `F-1MEF`, `DRS`, `DRS/A`, `DRSLTR`, `EFFECT`, `UPLOAD`, `CORRESP`, `20-F`, `6-K`, `CERT`, and `25-NSE`. An `S-1`-only ingestion client returns nothing for the exact population this project exists to analyze.
  3. Phase 7 never has to touch this layer. De-SPAC (`S-4`, `F-4`, `DEFM14A`), reverse merger (Super `8-K`), and the bilingual foreign-issuer work (O5) all become caller-supplied form sets against an unchanged ingestion client. The high-signal artifacts already visible in Luckin's own history, `UPLOAD` (SEC comment letters) and `CORRESP` (issuer responses), stay reachable from Phase 1 rather than being designed out by a narrow form allowlist.
- Revisit if: A future phase needs ingestion itself to filter or rank by form type rather than simply fetching what the caller asks for; that would be a sign the boundary needs to move.

---

## Phase 0 decisions

Recorded here as a permanent log; approved in the Phase 0 architecture sign-off prior to this session. Rationale is summarized from the approved brief, not re-litigated.

### D13: Peer selection is deterministic, versioned config
- Date: 2026-09-06
- Decision: `compare_to_peers` selects peers by pathway, size band, recency, and sector, as versioned config rather than an ad hoc model judgment.
- Options considered: Let the agent or a model call select comparable peers at run time; select peers via deterministic, versioned selection criteria (chosen).
- Why: Peer comparison needs to be reproducible and explainable like the standards checks and the red-flag weights, not a one-off LLM judgment that could vary run to run.
- Revisit if: The eval shows the deterministic criteria produce poor peer sets for a pathway or sector.

### D12: Demo UI deferred to Phase 6, video plus run-it-yourself preferred over hosting
- Date: 2026-09-06
- Decision: The optional Next.js/React demo UI is deferred to Phase 6. A recorded two-minute video plus a run-it-yourself-with-your-own-key path is preferred over a live public host; if hosted later, it sits behind rate limiting and a hard per-day cost cap.
- Options considered: Build the demo UI early alongside the core agent; defer it and lead with a recorded video and self-hosting instructions (chosen).
- Why: Avoids taking on hosting cost and abuse surface before the core agent and eval harness, which are the actual moat, are proven.
- Revisit if: A live demo becomes necessary for a specific audience (for example, an interview) before Phase 6.

### D11: Deterministic eval metrics maximized; LLM-as-judge scoped to memo prose only
- Date: 2026-09-06
- Decision: Eval metrics are maximized as deterministic (precision/recall/F1 against real outcomes, extraction numeric fidelity, citation faithfulness, injection resistance). LLM-as-judge is used only for memo prose quality, at temperature 0 against a fixed rubric on a cheap model, with a human-audited sample and cached judgments.
- Options considered: Use an LLM judge broadly across metrics; restrict LLM-as-judge to the one genuinely subjective metric and keep everything else deterministic (chosen).
- Why: Deterministic metrics are cheap, reproducible, and safe to gate a release on. LLM-as-judge is reserved for prose quality, the one dimension that is not otherwise measurable, and constrained to stay reproducible and cheap.
- Revisit if: A deterministic proxy for prose quality is found, or judge cost/variance becomes a problem even at the constrained scope.

### D10: First pathway and ruleset is traditional_ipo on Nasdaq
- Date: 2026-09-06
- Decision: The first implemented pathway and listing-standard ruleset is `traditional_ipo` against Nasdaq initial and continued listing standards. NYSE and foreign-issuer standards land in Phase 7.
- Options considered: Build multiple pathways or exchanges in parallel from the start; sequence a single well-documented pathway and exchange first (chosen).
- Why: Bounds Phases 1 through 6 to the best-documented pathway and exchange before tackling multi-route pathway detection and foreign-issuer complexity in Phase 7.
- Revisit if: Early eval cases turn out to concentrate on NYSE or a non-IPO pathway, making this sequencing a poor fit.

### D9: Typed CompanyRef resolved to CIK and echoed everywhere
- Date: 2026-09-06
- Decision: `CompanyRef` (cik, ticker, or name) is resolved to a CIK and echoed back in every tool output.
- Options considered: Let each tool re-resolve or silently assume the company; resolve once to CIK and echo it in every output (chosen).
- Why: CIK is the one stable EDGAR identifier; tickers and names are ambiguous and change over time, so every output must state unambiguously which company it resolved to.
- Revisit if: Multi-entity outputs (for example, a SPAC and its de-SPAC target) need more than one CIK echoed at once.

### D8: Deterministic weighted red-flag scoring in v1
- Date: 2026-09-06
- Decision: `RedFlagScorer` uses deterministic weighted scoring in v1, with versioned weights in `risk/weights.yaml`. A learned component is added only if the eval harness justifies it.
- Options considered: Train a learned scoring model from the start; start with deterministic weighted rules and only add learning if evaluated performance demands it (chosen).
- Why: Matches the minimal-over-engineering constraint and keeps the model auditable and explainable before a labeled set large enough to justify learned weights exists.
- Revisit if: The Phase 5 eval shows deterministic weights plateau below an acceptable precision/recall bar.

### D7: Standards are versioned YAML, one rule per record
- Date: 2026-09-06
- Decision: Listing standards live in `standards/<exchange>/*.yaml`, one rule per record, each with a primary-source citation and an `effective_from` date. All numeric thresholds are flagged to-verify rather than asserted.
- Options considered: Hardcode thresholds in code; store them as versioned, git-diffable YAML with citations (chosen).
- Why: Listing standards change over time and must be auditable to their primary source; YAML keeps them reviewable and out of code, consistent with the "structured, schema-validated, never free-text" constraint.
- Revisit if: A rule needs conditional logic that outgrows a flat YAML record.

### D6: Qualitative extraction locates sections deterministically, then structures with a bounded LLM call
- Date: 2026-09-06
- Decision: `QualitativeExtractionService` first locates sections (risk factors, related-party, ownership/VIE) deterministically, then performs schema-constrained LLM structuring inside a bounded, sanitized envelope.
- Options considered: Let the LLM find and structure sections in one open-ended pass; separate deterministic location from constrained structuring (chosen).
- Why: Matches the security stance that filing text is untrusted data, never instructions. Deterministic section location keeps the LLM's job narrow, bounded, and auditable rather than open-ended.
- Revisit if: Deterministic section location proves too brittle across filing formats and needs a fallback.

### D5: Citation is a discriminated union of XbrlLocator and TextLocator
- Date: 2026-09-06
- Decision: `Citation` is a discriminated union: `XbrlLocator {concept, context_ref, unit, period, accession_no, source_url}` for financial values, `TextLocator {accession_no, form_type, filed_date, section_label, verbatim_anchor, char_span?, source_url}` for qualitative claims.
- Options considered: One generic citation shape for both financial and qualitative claims; a discriminated union with a distinct shape per source kind (chosen).
- Why: Financial values and qualitative claims resolve to structurally different locations (an XBRL concept/context versus a text span), and citation faithfulness is a graded eval metric targeting 100%, so each kind needs to be independently and precisely resolvable.
- Revisit if: A third citation kind (for example, a tabular non-XBRL figure) is needed.

### D4: HTTP-layer cache, disposable, separate from the eval store
- Date: 2026-09-06
- Decision: Caching happens at the HTTP layer, keyed by URL, in a disposable cache DB that is a separate SQLite file from the eval store.
- Options considered: Cache at a higher layer (for example, per extracted value); cache raw HTTP responses only, kept structurally separate from eval data (chosen).
- Why: Keeps the cache purely a performance and SEC-politeness layer that can be deleted and rebuilt at any time, and keeps it structurally isolated so eval results are never contaminated by cache eviction or rebuild.
- Revisit if: A higher-layer cache (for example, extracted `FinancialFacts`) becomes necessary for cost reasons.

### D3: Golden-set labels are git-tracked fixtures; results and baseline are gitignored SQLite
- Date: 2026-09-06
- Decision: Golden-set case labels are git-tracked JSON fixtures (`eval/cases/*.json`) loaded into SQLite at run time. Eval results (`eval_result`) and the recorded baseline (`eval_baseline`) live in gitignored SQLite, keyed by `git_sha`.
- Options considered: Track everything (labels, results, baseline) in git; track only the curated labels in git and keep run-generated data out of history (chosen).
- Why: Labels are curated, reviewable data that should be diffable in git. Run results and the baseline are regenerated by running the harness and would bloat history if tracked, while still needing to be keyed to a specific `git_sha` for the release-gate comparison.
- Revisit if: Reproducing a specific historical eval run without re-running it becomes a real need.

### D2: Local stdio transport by default, remote HTTP later behind auth
- Date: 2026-09-06
- Decision: The MCP server uses local stdio transport by default. Remote HTTP transport is later work, and only behind authentication.
- Options considered: Build remote HTTP transport from the start; start local-only and add remote later behind auth (chosen).
- Why: Avoids exposing a network-facing service before authentication exists. Consistent with D12's deferred-hosting stance for the demo.
- Revisit if: A remote MCP consumer (for example, a hosted demo backend) is scheduled.

### D1: MCP tools are thin wrappers over an in-process ToolService
- Date: 2026-09-06
- Decision: MCP tools are thin wrappers over a single in-process `ToolService` facade. The agent dogfoods the server over a stdio MCP client. The eval harness calls `ToolService` directly, in-process.
- Options considered: Put tool logic directly in the MCP server handlers; centralize all logic in one `ToolService` facade and make the MCP layer a thin schema-validating adapter over it (chosen).
- Why: Keeps one source of truth for logic. The MCP layer stays a thin, typed, schema-validating adapter, and the eval harness can exercise the same logic the agent uses without needing a live MCP round trip for every eval run.
- Revisit if: `ToolService` methods start needing MCP-specific behavior that does not belong in the eval or agent paths.

---

## Resolved open decisions (Phase 0)

### O5: Bilingual China layer lands in Phase 7
- Date: 2026-09-06
- Decision: Phase 7 covers foreign-issuer filings (`20-F`, `F-1`) plus a first bilingual slice. Deeper CSRC and exchange enforcement terminology is a later stretch goal, not part of Phase 7.
- Options considered: Build bilingual/foreign-issuer depth early, since it is the core differentiator; sequence it after the domestic pipeline is proven end to end (chosen).
- Why: Bilingual and foreign-issuer depth is the differentiator but also the hardest and riskiest work, so it is sequenced after the core pipeline (ingestion through eval) is proven on the simpler domestic case.
- Revisit if: A specific China case becomes available early and is worth pulling forward as a spike.

### O4: Demo UI deferred but stays in the plan
- Date: 2026-09-06
- Decision: The demo UI is deferred to Phase 6 per D12, but is not dropped from the plan.
- Options considered: Drop the UI entirely and rely only on MCP/CLI access; keep it in the plan, deferred (chosen).
- Why: Same reasoning as D12: the UI has value for the resume-headline and demo goal, but is not the moat, so it is sequenced late rather than removed.
- Revisit if: See D12.

### O3: Golden set size, composition, and label sources
- Date: 2026-09-06
- Decision: Golden set of about 30 to 40 cases to start, drawn from the recent China small-cap wave plus a domestic control group, labeled from Form 25 and delisting notices, halt and enforcement records, and post-listing price history. The survived-versus-delisted label horizon N is confirmed when the set is built.
- Options considered: A larger set built later once tooling matures; a smaller set (30-40) built early to start driving the eval loop, with a domestic control group added so metrics are not confounded by one population (chosen).
- Why: Needs enough cases to be statistically meaningful while staying buildable solo. The China small-cap wave is the moat's core validation population; the domestic control group keeps metrics honest against a base rate.
- Revisit if: Early metrics are too noisy at this sample size to be actionable.

### O2: Traditional IPO plus Nasdaq standards first
- Date: 2026-09-06
- Decision: Confirms D10: traditional IPO pathway plus Nasdaq listing standards are the first implemented slice.
- Options considered: See D10.
- Why: See D10.
- Revisit if: See D10.

### O1: Keep the ListingLens name for now; centralize it against a future rename
- Date: 2026-09-06
- Decision: Keep the product name ListingLens and the repo `arsmith0922/listing-lens` for now. A rename is planned later. The product name is centralized in code (see D14 and Phase 1's `core/branding.py`) rather than hardcoded ad hoc, so a future rename stays low-cost.
- Options considered: Rename now before writing code; keep the current name and centralize it so a later rename is mechanical (chosen).
- Why: No strong reason to block on renaming now; centralizing the name costs little today and de-risks a future rename.
- Revisit if: A specific new name is chosen.
