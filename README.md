# ListingLens

An MCP server and evaluated AI agent that assess companies entering the US public markets for integrity and delisting risk. Given a company or deal, it classifies the listing pathway (IPO, SPAC or de-SPAC, reverse merger, direct listing) and the issuer's structure, then flags the red flags in its SEC filings that historically precede failed listings, early delistings, or fraud, with every claim cited to a source filing. Deepest on cross-border and China-based issuers.

Status: in development. See DECISIONS.md for the running design log.

## What it does
- Classifies the listing pathway and issuer structure from SEC filings.
- Flags integrity and delisting risk factors, each cited to its source filing.
- Measures how much margin a company has against initial and continued listing standards (a risk signal, not a pass or fail gate).
- Exposes all of the above as typed tools via an MCP server.
- Ships with an evaluation harness that grades the risk flags against companies with known real outcomes.

## Data
Uses only free, public SEC EDGAR data (filings, full-text search, XBRL financials). No proprietary or paid data.

## Run it yourself
Bring your own Anthropic API key. Copy `.env.example` to `.env`, add your key, and follow the setup steps (coming soon).

## Disclaimer
This is an educational and research tool. It is not investment advice, not a recommendation to buy or sell any security, and it does not predict fraud. It surfaces risk signals from public filings, with accuracy reported in the evaluation harness.

## License
MIT. See LICENSE.