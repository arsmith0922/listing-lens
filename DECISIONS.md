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

### D25: IngestionService facade, open_ingestion_service wiring, and recorded Phase 1 limitations
- Date: 2026-10-07
- Decision: `ingestion/service.py`'s `IngestionService(client: EdgarClient)` builds `EdgarRepository` and `FullTextSearchRepository` on one injected client and delegates 1:1: `resolve_company`, `list_filings`, `fetch_document`, `search`, with the repositories' own signatures and return types and no composition conveniences. Because both repositories sit on the one client, a resolve followed by a list fetches submissions once (the cache absorbs the second read). `ingestion/wiring.py`'s `open_ingestion_service(settings=None, *, cache_dir=Path("data"), http_transport=None, clock=None)` is the first real settings-to-stack wiring: a `@contextmanager` that builds `Settings()` (a blank or placeholder `SEC_EDGAR_CONTACT` raises `MissingUserAgent` before anything is created), makes `cache_dir`, builds `EdgarTransport(contact)` (the User-Agent is composed inside the transport by `branding.user_agent`, D19) and `CachedEdgarClient(transport, cache_dir/"http_cache.db", cache_dir)`, yields the service, and closes the client in `finally`. A context manager rather than a `from_settings()` classmethod because the SQLite connection needs an owner that closes it. `http_transport` and `clock` are test seams only; the tests build the real stack over a fake transport and never touch the network. `data/*.db*` and `plans/` are gitignored. `scripts/smoke_edgar.py` is the one live-tested step, gated like `record_fixtures.py` (`LISTINGLENS_ALLOW_NETWORK=1`, outside `testpaths`, never in CI). Run once against Apple before this commit: resolve by ticker (cik 320193), list 2,264 filings across recent plus the overflow page (newest first, pinned accession present), fetch the pinned 10-K's primary document (1.56 MB), and a narrowed full-text search (88 hits, not truncated). Its search total is a plausibility range, not an exact assertion.
- Limitation, subdirectory primaryDocument: 669 of Apple's 1,000 recent rows carry a `primaryDocument` containing a slash (for example `xslF345X06/form4.xml`, a rendered Form 4 path). `filing_document_url` rejects `/` and those names are not in the Archives index, so `fetch_document` raises `FilingNotFound` for them even though `FilingRef.primary_document` reports them. The 10-K path used by the smoke script is a plain name and works. Forward note: this needs addressing in Phase 2, when primary documents are fetched for extraction.
- Limitation, unbounded search paging: `FullTextSearchRepository.search` pages until a short page or the result window, so one broad query can issue up to about 100 sequential requests (roughly 11 MB). The smoke search is narrowed (form filter plus a one-year range) to stay at one page. Forward note: add a page or hit bound once search is agent-callable in Phase 3/4.
- D22 "revisit if" clause, third real-data null: the live smoke surfaced `core_type = null` on one 1994 row (SC 13G/A, row 1260 of 1264) of Apple's overflow page, after `isXBRLNumeric` and `file_description` (both D22). Fixed in `07e5e77` as `core_type: list[str | None]`, with a regression test that parses a synthetic null row and maps it through `page_to_filing_refs`. Same lesson as D22: nulls appear only in live data, so confirm against the live page, loosen only the observed field, and add a regression test. A full null scan of Apple's recent and overflow pages found no other new null; that row's empty-string `primaryDocument` already parses as a plain `str`.
- Options considered: A `from_settings()` classmethod that returns a service (rejected: nothing would own the SQLite connection); having the service accept the two repositories instead of a client (rejected: the shared single client is the point, and tests would have to wire two repositories by hand); a page or hit bound on search now (rejected for this chunk: the design was settled as 1:1 delegation, and no caller can run an unbounded query before Phase 3).
- Why: Phase 1 needed a single entry point over the four ingestion operations and one proof that the whole stack works against the real SEC endpoints, without making the suite depend on the network.
- Revisit if: A caller needs the Form 4 style primary documents or a bounded search before Phase 2 and Phase 3/4 respectively, or the service needs to compose operations (resolve then list) rather than delegate.

### D24: FullTextSearchRepository pages EFTS by arithmetic, signals truncation, and guards pre-2001 coverage
- Date: 2026-10-06
- Decision: `ingestion/search_repository.py`'s `FullTextSearchRepository(client: EdgarClient, *, page_size=100, result_window=10000)` exposes `search(query, *, forms, start_date, end_date) -> FullTextSearchResult`. It reuses the D23 `EdgarClient` Protocol, so it runs over either `EdgarTransport` or `CachedEdgarClient`. A coverage guard runs before any fetch: a `start_date` earlier than 2001-01-01 raises the new `OutsideFullTextCoverage(start_date, coverage_start)` leaf under `IngestionError`. The 2001-01-01 constant lives in the repository, not in `endpoints.full_text_search_url`, which stays a pure builder with no policy. Results are projected to frozen domain models in `domain/search.py`: `FullTextHit` (`AccessionNumber`, `tuple[Cik, ...]`, and straight copies of `form`, `file_date`, `file_type`, `file_description`) and `FullTextSearchResult` (`hits`, `truncated`, `total`, `total_is_estimate`). They take already-validated input, so they have a strict constructor and no `parse()`. `ingestion/search_hits.py` does the pure projection; it dedupes by accession first (`dedupe_by_accession`, first occurrence wins) and then projects, and a malformed `adsh` or cik raises its typed parse error rather than being caught. `file_date` stays a string, as in D22; date parsing is a later concern.
- Paging and the cap: offsets start at 0 and advance by `page_size`. The loop stops when a page returns fewer than `page_size` hits (natural end, `truncated=False`), or when a full page lands at `offset >= result_window - page_size`, at which point `truncated=True`. So with the defaults it fetches `from=0` through `from=9900` and never requests `from=9901` or beyond; it never issues a request past the cap to discover it, and never reads `MalformedPayload.detail`. This is the chunk 8 obligation recorded in D22. `SearchResponse.parse()`'s error-envelope handling stays a defensive backstop only. `total` and `total_is_estimate` come from the first page only; `total_is_estimate` is true when a total is reported with `relation != "eq"`.
- Coupling: `full_text_search_url` emits no `size`, and the recorded fixtures were made against EFTS's server default of 100, so `page_size` must equal that default for offsets to tile contiguously. Both `page_size` and `result_window` are injectable (default 100 and 10000) so tests can exercise the cap with tiny windows; changing `page_size` in production without adding a `size` parameter to the builder would skip or repeat hits.
- Accepted over-signal: `truncated` is inferred from a full page at the last in-window offset, not from the total. A result set that has exactly `result_window` hits therefore reports `truncated=True` although nothing was lost. This errs toward the safe direction (a caller is told the result may be incomplete) and costs one spurious flag at an exact boundary.
- Unexpected statuses: any non-2xx the transport did not retry raises `UpstreamError(attempts=1, detail="unexpected status, not retried")`, the same shape as D23; a non-JSON body raises `MalformedPayload`.
- Options considered: Putting the 2001 guard in `full_text_search_url` (rejected: the URL builder is pure and shared, and coverage is a repository policy); adding a `size` parameter to the builder (rejected for this chunk: the fixtures were recorded against the no-size default, so the cap constant stays in the repository); detecting the cap by requesting past it and catching `MalformedPayload` (rejected: it spends a request to learn what arithmetic already knows, and string-sniffing `detail` is fragile); deriving `truncated` from `total` (rejected: `total` is a `gte` floor of 10000 once results exceed the window, so it cannot say whether the window was reached).
- Why: Verified live during the Phase 1 investigation (D15) that pre-2001 queries return HTTP 200 with zero hits, a silent wrong answer, so they need a typed refusal rather than an empty result; verified live in chunk 6 (D22) that the window boundary is exact at `from + size <= 10000`. The deep-pagination known-failing entry (D15) stays chunk 9's: beyond the window the repository now reports `truncated`, but a `search_after` style continuation is not built.
- Revisit if: A caller needs more than the first 10,000 hits per query (narrow by date range, or build the continuation), or a `size` parameter is added to the URL builder, at which point `page_size` should be passed through to it.

### D23: EdgarRepository over an EdgarClient Protocol; exact-match resolution; per-filing records; untrusted names validated before they become URLs
- Date: 2026-10-03
- Decision: `ingestion/repository.py`'s `EdgarRepository(client: EdgarClient)` holds only IO orchestration (`resolve_company`, `list_filings`, `fetch_document`); the pure logic lives in `ingestion/company_index.py` and `ingestion/filing_rows.py` so it is testable with no client. `ingestion/client.py` adds `EdgarClient`, a one-method `Protocol` (`get(url) -> httpx.Response`) that `EdgarTransport` and `CachedEdgarClient` satisfy structurally with no edits; this settles the D21 deferral. Resolution takes the first field present in the order cik, ticker, name, with no cross-check when a ref carries several. Ticker and name go through `CompanyIndex` (ticker uppercased by `Ticker`; name matched by casefold plus whitespace collapse only, never fuzzy or substring). Every path then fetches the CIK's submissions, including the cik path, to validate the CIK exists and to canonicalize `issuer_name`; the second fetch is a cache hit. Two new `IngestionError` leaves: `CompanyNotFound(identifier, identifier_kind)` for a miss and `AmbiguousCompany(query, query_kind, candidates)` when a ticker or name maps to more than one distinct CIK (several tickers or titles of one CIK are not ambiguous). `FilingNotFound` is reused for a missing accession directory or a document absent from the Archives index. `list_filings` returns `list[FilingRef]`, one per filing, newest first: `filings.recent`, then each `filings.files` page in listed order, with no sort and no dedupe. `FilingRef` gained optional `report_date`, `acceptance_datetime`, and `primary_document` (the last is what lets a caller pick a filing's main document for `fetch_document`). `page_to_filing_refs` builds rows by explicit index, never `zip`, and is self-guarding: it re-checks every column length against `accession_number` and raises `MalformedPayload` on the first mismatch, so a page that bypassed the chunk 6 validator (for example via `model_construct`) fails typed rather than with an `IndexError` or a silent truncation.
- Untrusted names: overflow file names (`filings.files[].name`) and document names (Archives index) are upstream data. `endpoints.submissions_overflow_url` accepts only `CIK{this company's padded cik}-submissions-NNN.json`; `endpoints.filing_document_url` accepts only a plain file name matching `[A-Za-z0-9][A-Za-z0-9._-]*` (all 99 names in the recorded Apple index match). Both end in `assert_allowed`. A document name must also be an exact member of the parsed index before any URL is built, so a hostile or odd name never reaches the transport. A rejected name from upstream surfaces as `MalformedPayload`.
- Non-UTF-8 documents: `fetch_document` decodes strictly as UTF-8. A body that arrives whole but does not decode raises `UndecodableDocument(url, detail)`, a distinct `IngestionError` leaf, not `MalformedPayload`, because the bytes were retrieved intact and the limitation is decoding, not a malformed payload. This scope cut blocks nothing in chunks 7, 8, or 9: listing reads UTF-8 submissions JSON, resolution reads the UTF-8 ticker map and submissions JSON, search reads UTF-8 EFTS JSON, and only a raw document fetch of a legacy-encoded filing is affected. It is recorded by name as the chunk 9 known-failing entry "legacy non-UTF-8 document decoding" (D15): the xfail test asserts that a latin-1 document decodes, and today that raises `UndecodableDocument`.
- Unexpected statuses: a 404 maps to the caller's typed not-found; any other non-2xx that the transport did not retry raises `UpstreamError(attempts=1, detail="unexpected status, not retried")`, so it cannot be read as the retry-exhaustion report D20 designed `UpstreamError` for.
- Still deferred, stated explicitly: real `If-Modified-Since`/304 revalidation of the ticker map (the `CONDITIONAL` cache class). Chunk 7 reintroduces the map but the 24-hour TTL stopgap still suffices. The cost is that a ticker the SEC published within the last 24 hours can read as a miss until the cached copy expires; real revalidation would only narrow that cache-added staleness, not the SEC's own publication lag. Build it if an eval or demo case misses a freshly listed ticker; the `etag` and `last_modified` columns are already stored, so it is additive.
- Options considered: Union or concrete `CachedEdgarClient` instead of a Protocol (rejected: a Union is a closed set every new client must edit, and the concrete type forces every repository test onto real SQLite); resolving `issuer_name` from the ticker-map title (rejected: unavailable for issuers with no ticker, and gives two name sources); column-wise filings (rejected: pushes index alignment onto every caller and recreates the ragged-array hazard the chunk 6 guard removes); enforcing `filingCount == rows` (rejected: it matches live, 2010/2010 and 1764/1764 for GE, but the committed trimmed GE fixtures cannot satisfy it, and the real truncation modes are already caught by JSON parsing and the length guard); reusing `FilingNotFound` for company misses (rejected: its message reads "Filing not found for ticker=...").
- Why: Live probes this chunk: the ticker map has 10,434 entries, 1,453 CIKs with several tickers, and no ticker or title shared across CIKs; GE's recent plus two overflow pages are contiguous, newest first, and share no accession; every missing resource (CIK, accession directory, document) is a 404 with a varying content type, so status alone is the signal. Exact matching keeps resolution deterministic; the name-to-CIK gap for issuers absent from the map stays the chunk 9 known-failing item.
- Revisit if: A caller needs fuzzy name resolution, a cross-check between several `CompanyRef` fields, or a freshly listed ticker is missed (see the deferral above).

### D22: Typed EDGAR payload models; MalformedPayload leaf; EFTS pagination cap corrected and pushed to chunk 8
- Date: 2026-09-22
- Decision: `ingestion/payloads/` holds five small modules (`submissions.py`, `tickers.py`, `archives.py`, `search.py`, `common.py`) parsing the raw JSON `EdgarTransport`/`CachedEdgarClient` return into validated typed models, with no interpretation. Every payload model follows D18's `parse(raw: object, url: str) -> Self` convention, extended with a required `url` parameter (these models have no natural scalar "value" to carry source context the way `Cik`/`AccessionNumber` do). `common.py`'s `parse_or_raise[M: BaseModel](model_cls, raw, url)` centralizes the `pydantic.ValidationError`-to-`MalformedPayload` wrapping used by every module, calling `model_cls.model_validate(raw, context={"url": url})`; the `context` parameter is how a `url`-aware validator deep in a model tree (`FilingIndexPage`'s ragged-array guard) gets the real `url` without it being threaded manually through every nested model. `MalformedPayload(url, field, detail)` is a new leaf under `IngestionError` (not `ExtractionError`; `payloads/` still parses raw shape, it does not interpret filing content). `FilingIndexPage` (the bare 16-parallel-array shape shared by `filings.recent` and every overflow file) has a `model_validator(mode="after")` that compares every field's list length against `accession_number`'s and raises `MalformedPayload` naming the first mismatched field; it never `zip()`s the arrays, so a shortened column is caught explicitly rather than silently truncating. `SubmissionsDocument` deliberately models only 7 of 23 confirmed top-level fields (`cik`, `entityType`, `name`, `tickers`, `exchanges`, `formerNames`, `filings`); the rest fall to `extra="allow"` since none have a consumer yet. `SearchResponse.parse()` detects the real EFTS deep-pagination shape (`errorType`/`errorMessage`/`trace`, HTTP 200, no `hits` key at all) and raises `MalformedPayload(field="hits", ...)` directly, as a defensive backstop; it does not itself decide when to stop paging.
- Real-data findings that changed the field types from the plan's first draft (each confirmed against a fixture recorded live via `scripts/record_fixtures.py`, gated on `LISTINGLENS_ALLOW_NETWORK=1`, never run in CI or by pytest): `filings.recent.isXBRLNumeric` is JSON `null` for 46 of 48 rows for one real domestic filer (Trans American Aquaculture), so `is_xbrl_numeric` is typed `list[int | None]`, not `list[int]`; EFTS `_source.file_description` is JSON `null` for 11 of 100 real hits, so `HitSource.file_description` is typed `str | None`, not `str`. Both are genuine JSON `null`, not the empty-string convention `EmptyStrAsNone` exists for, so both use a plain `X | None` field rather than the `Annotated[X | None, EmptyStrAsNone]` pattern. `file_date` and `period_ending` stay `str` (never `date`), matching how `_source` fields are kept close to the wire in this chunk; date parsing is chunk 7's job. `Archives` items' `size` legitimately observed as `""` for a few real rows (index-header meta entries, not files); kept as plain `str`, no validator needed. `EFTS` `_source.sequence` was observed as a numeric JSON string (`"4"`) for 3 of 100 real hits, alongside `int` for the rest; left as `sequence: int` since pydantic's default lax int coercion already absorbs a numeric string correctly, verified against the real fixture.
- Corrected finding: the EFTS pagination cap does not return an "empty `hits.total`" near `from=10000` as informally noted before this chunk's live verification. The real boundary is exact at `from + size <= 10000`: `from=9900` (with the default `size=100`) succeeds normally; `from=9901` returns HTTP 200 with an entirely different, `hits`-less error-envelope body. Both states are captured as fixtures (`efts_search_normal.json`, `efts_search_boundary_error.json`).
- Explicit guidance for chunk 8: the search repository must cap pagination by computing `from + size <= 10000` and stopping at `from=9900`, surfacing an explicit truncated signal to its caller. It must never page to `from=9901` to discover the cap by hitting it, and must never string-sniff `MalformedPayload.detail` to detect truncation; `SearchResponse.parse()`'s error-envelope handling in this chunk is a defensive backstop against an unexpected upstream response, not the mechanism chunk 8 should rely on to know when to stop.
- Fixture strategy: `scripts/record_fixtures.py` fetches real bodies and writes them under `tests/fixtures/edgar/`, gated on `LISTINGLENS_ALLOW_NETWORK=1`, outside `testpaths` and never run in CI. Trans American (domestic S-1), Luckin (FPI F-1), and both EFTS boundary fixtures are committed full, since they are small and their full shape (especially Luckin's empty-string distribution) is what the tests exercise. Only GE's main submissions doc and its two overflow files are trimmed, and trimmed deterministically: the same row-index list is selected across all 16 parallel arrays at once, so lengths stay equal by construction rather than by hand-editing arrays separately; `filings.files` is kept intact so the multi-overflow case still has both refs. `manifest.json` records `{file, url, fetched_at, sha256}` per fixture, with `trimmed: true` plus a note on the four trimmed entries, marking that the recorded `sha256` verifies the committed (trimmed) file, not a fresh fetch of `url`.
- Options considered: Model every confirmed top-level `SubmissionsDocument` field now versus only the 7 with a real consumer (narrow scope chosen, matching the project's repeated minimal-over-engineering discipline); apply `EmptyStrAsNone` to `isXBRLNumeric` and `file_description` versus a plain `X | None` (plain chosen: both fields carry genuine JSON `null` in real data, never an observed empty string, so the empty-string validator would be solving a problem that does not occur here and would mask a future genuine empty-string case if one appears); hand-trim fixtures field by field versus a single index-aligned transform applied identically everywhere it is needed (index-aligned transform chosen, makes a ragged or lopsided fixture impossible to create by accident).
- Why: `isXBRLNumeric` and `file_description`'s real-world nulls were not visible during the planning investigation's earlier empty-string sampling (which checked `v == ""`, not `v is None`) and only surfaced once the actual recorded fixtures were parsed end to end; this is the reason fixtures are recorded from live data before the models are finalized, not assumed from the brief. The EFTS pagination correction exists for the same reason: a precise `curl`-based re-check overturned an imprecise earlier paraphrase of the same real behavior.
- Revisit if: A future EDGAR filer or hit surfaces a null or type variant on a field currently typed as required/non-null; treat it the same way, confirm against a fixture before loosening the type, never loosen speculatively.

### D21: SQLite HTTP cache wraps EdgarTransport; wall-clock TTLs, fail-open on both read and write
- Date: 2026-09-22
- Decision: `ingestion/cache.py`'s `CachedEdgarClient` wraps an already-constructed `EdgarTransport`, exposing the same `get(url) -> httpx.Response` shape; `EdgarTransport` gets no new parameter and stays unaware caching exists. `classify_ttl(url)` is a pure function over `urlsplit(url).hostname.lower()` and `.path` (lowercased to match `assert_allowed`'s canonical form), returning `IMMUTABLE` for anything under `www.sec.gov/Archives/edgar/data/`, `CONDITIONAL` for the ticker map, and `SHORT` (a safe default) for everything else, including endpoints not built yet. The `Clock` protocol (`ingestion/throttle.py`) gained a `time() -> float` method, implemented as `time.time()` in `RealClock`; the cache uses only `.time()`, never `.monotonic()`, for `fetched_at` and freshness comparisons. Both `_read` and `_write` fail open: a `sqlite3.Error` or a corrupt stored row is treated as a cache miss and never propagates, and a failed write (disk full, locked, permissions) is swallowed so the already-fetched response is still returned. Only `2xx` responses are persisted. Response headers are serialized via `dict(headers.items())`, which keeps only the last value of any repeated header name; an accepted, deliberate limitation, since EDGAR GET responses have not been observed to repeat a header name.
- Options considered: Store `fetched_at` via the throttle's existing `Clock.monotonic()` (rejected: verified `time.monotonic()`'s reference point is undefined across process runs, and the cache DB persists across runs by design, so a monotonic comparison would silently corrupt every TTL check after the first restart); inject the cache into `EdgarTransport` itself versus wrap it in a separate client (wrap chosen, keeps the transport onion-pure); build real `If-Modified-Since`/304 handling for the ticker map now versus defer it (defer chosen: nothing fetches the ticker map yet, that lands with chunk 7's name/ticker resolution, so building it now would have no caller); raise from a failed cache write versus swallow it (swallow chosen, extending the same fail-open principle already applied to reads, since a write happening only after a successful fetch means an uncaught write error would turn a successful request into a failed one, which the cache exists to never do).
- Why: The cache is explicitly disposable, best-effort local infrastructure (per D4's original framing); it must never be able to turn a working request into a failure, in either direction (read or write). `classify_ttl`'s safe default and host/path-only matching keep it forward-compatible with endpoints not yet built (companyfacts) without needing to be touched again, and keep it honest against the ingestion-layer constraint test (no form-name literals, no `domain.pathway` import).
- Revisit if: Chunk 7 actually needs the ticker map, at which point real conditional revalidation (an optional `extra_headers` parameter on `EdgarTransport.get`, a 304-aware branch in `CachedEdgarClient.get`) replaces the `CONDITIONAL` class's current plain-TTL stopgap. Note: chunk 5 does not provide a shared static type across `EdgarTransport`/`CachedEdgarClient` (no Protocol or Union); if a caller ever needs to hold either interchangeably under strict mypy, that is chunk 7's job to add when it actually needs it, not something this chunk delivers.

### D20: Ingestion failure errors carry url and enough last-observed evidence to diagnose the cause
- Date: 2026-09-17
- Decision: Three new leaves under `IngestionError` in `core/errors.py`: `ResponseTooLarge(host, url, limit_bytes)`, `TooManyRedirects(host, url, max_redirects)`, `UpstreamError(host, url, status_code: int | None, attempts, detail: str | None)`. `UpstreamError.status_code` is `None` for a transport-level failure (connect timeout, connection refused, no HTTP status exists) with `detail=str(exc)`; it carries the last HTTP status with `detail=None` on 5xx exhaustion. `RateLimited` is enriched in place rather than replaced: it now also carries `url`, `attempts`, the last `content_type`, `undeclared_tool_fingerprint` (whether the response body matched the "Undeclared Automated Tool" signature), and `retry_after_seen` (whether the header was present at all, independent of whether it parsed), alongside the existing `retry_after_seconds`. Its message states plainly that this response shape can also indicate a rejected User-Agent rather than true rate limiting. No fourth `RetriesExhausted` leaf: the transport retries every retryable condition itself, so `RateLimited` and `UpstreamError` are only ever raised at exhaustion in this layer, and enriching those two in place is the complete diagnosable-exhaustion surface.
- Options considered: A single generic `RetriesExhausted(host, status_code)` leaf for every exhaustion case (rejected: collapses a genuine 5xx, a transport-level failure with no status, and a rate-limit-or-rejected-UA ambiguity into one shape, losing exactly the evidence needed to tell them apart); enrich the two leaves that already exist for these cases, plus one clearly-scoped new leaf per genuinely new failure mode (chosen).
- Why: A persistent failure must be diagnosable from the exception alone, without re-running the request. The guiding principle going forward: every ingestion failure error carries `url` like the others already do, plus enough last-observed evidence (status code or its absence, content type, a matched body fingerprint, whether an expected header was present) to diagnose the real cause, and it never asserts a cause the response does not actually prove, which is exactly why the HTML-shaped 403 is raised as `RateLimited` with evidence attached rather than as a confident `MissingUserAgent` the transport cannot actually verify at that point.
- Revisit if: A future failure mode needs evidence that doesn't fit any existing leaf's fields; extend that leaf rather than adding a new one unless the cause is genuinely distinct.

### D19: Product name and version live in branding; environment supplies contact only
- Date: 2026-09-17
- Decision: `core/branding.py` holds `PRODUCT_NAME`, `VERSION`, and `user_agent(contact)`, the single source for the outgoing SEC User-Agent string. The environment supplies only a contact address, via `SEC_EDGAR_CONTACT` (`core/config.py`'s `Settings.sec_edgar_contact`), not the full User-Agent. Chunk 4's transport calls `branding.user_agent(settings.sec_edgar_contact)` to build the real header.
- Options considered: Keep the full composed User-Agent string in the environment (`SEC_EDGAR_USER_AGENT`), with `core/config.py` validating it against a full placeholder (the shape built in the branding refactor's first draft); supply contact only and compose the header from branding (chosen).
- Why: Carrying the full UA string in the env var would make `branding.user_agent()` dead code with no real caller, source the product name in every outgoing request from user-typed `.env` text rather than from the one authoritative constant, and reintroduce a product/version string in `.env.example` that can silently drift from `core/branding.py`. Supplying contact only means the operator can never mistype or go stale on the product identity half of the header; only `core/branding.py` can change it.
- Revisit if: A future deployment needs the operator to override the full User-Agent string outright (unlikely under SEC's fair-access policy, which asks for identifying contact info, not a specific product string).

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
