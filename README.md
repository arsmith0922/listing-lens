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
Uses only free, public data: SEC EDGAR (submissions, XBRL company facts) and Nasdaq's public symbol directory. No proprietary or paid data.

## Run it
You need [uv](https://docs.astral.sh/uv/) 0.13.4 or later (an older uv refuses this project), which installs Python 3.12 for you; a real email address, because the SEC asks every client to identify itself and ListingLens sends yours to SEC hosts only; and a directory where it can keep its cache. The server needs no API key and never reads a `.env` file.

```
git clone https://github.com/arsmith0922/listing-lens
cd listing-lens
uv sync
```

The server takes its settings only from the environment your MCP host gives it:

| Variable | Meaning |
|---|---|
| `SEC_EDGAR_CONTACT` | required: your real email address |
| `LISTINGLENS_CACHE_DIR` | required: an absolute path to a writable directory |
| `LISTINGLENS_LOG_LEVEL` | optional: DEBUG, INFO, WARNING (the default), ERROR or CRITICAL; logs go to stderr |

Add the server to your MCP host's configuration with an `env` block that sets both required variables. The shape is the same for any host that takes a command, arguments and an environment; check your host's documentation for where the file lives.

Windows, using the installed script:

```json
{
  "mcpServers": {
    "listinglens": {
      "command": "C:\\Users\\you\\listing-lens\\.venv\\Scripts\\listinglens-server.exe",
      "args": [],
      "env": {
        "SEC_EDGAR_CONTACT": "you@example.com",
        "LISTINGLENS_CACHE_DIR": "C:\\Users\\you\\.listinglens"
      }
    }
  }
}
```

macOS or Linux, using the module form:

```json
{
  "mcpServers": {
    "listinglens": {
      "command": "/home/you/listing-lens/.venv/bin/python",
      "args": ["-m", "listinglens.server"],
      "env": {
        "SEC_EDGAR_CONTACT": "you@example.com",
        "LISTINGLENS_CACHE_DIR": "/home/you/.listinglens"
      }
    }
  }
}
```

The two forms are interchangeable on either system: `listinglens-server` is a console script for `python -m listinglens.server`. If a variable is missing or wrong, the server exits with status 2 and says which one on stderr. Ask for `resolve_company` first, then pass the CIK it returns to the other tools.

`.env.example` is a template for the planned agent, whose `ANTHROPIC_API_KEY` line the server does not use. To smoke-test the real server against the live services (manual, never run in CI):

```
LISTINGLENS_ALLOW_NETWORK=1 uv run python scripts/smoke_mcp.py
```

The smoke script reads `SEC_EDGAR_CONTACT` from your environment or `.env`, hands it to the server it starts, and never prints it.

## Disclaimer
This is an educational and research tool. It is not investment advice, not a recommendation to buy or sell any security, and it does not predict fraud. It surfaces risk signals from public filings, with accuracy reported in the evaluation harness.

## License
MIT. See LICENSE.
