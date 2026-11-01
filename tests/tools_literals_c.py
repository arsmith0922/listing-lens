from __future__ import annotations

from tests.tools_literals import Want

# C. Xiao-I Corp (AIXI), continued listing, no tier named (tier-table row 6): the directory row
# `AIXI|XIAO-I Corporation - American Depositary Shares|G|N|D|100|N|N` of the file stamped
# 1030202618:01 says Global Market, status D. Three measured rules, all breached, worked by hand
# from the raw companyfacts JSON (USD as reported; equal in the FY2025 20-F filed 2026-05-15,
# accession 0001213900-26-057986, and the 20-F/A filed 2026-05-22, accession 0001213900-26-060270;
# within a period the most recently filed fact wins, D31, so the 20-F/A is the one cited). The
# headroom is measured minus threshold and the ratio is headroom over the threshold, exact.
C_ACCESSION = "0001213900-26-060270"
C_EARLIER_ACCESSION = "0001213900-26-057986"
C_TREE_ORDER = [
    "nasdaq-5450b3-g-assets-latest",
    "nasdaq-5450b3-g-revenue-latest",
    "nasdaq-5450b1-g-equity",
]
_ASSETS_REVENUE = ("nasdaq-5450b3-g", "Total Assets/Total Revenue Standard")
_PERIOD = "nasdaq-5450b3-g-assets-revenue-period"
C_FINDINGS: dict[str, Want] = {
    "nasdaq-5450b3-g-assets-latest": Want(
        "nasdaq-5450b3-g-assets-latest", "Rule 5450(b)(3)", *_ASSETS_REVENUE, _PERIOD,
        "latest_fiscal_year", "total_assets", "15901131", "50000000", "-34098869",
        "-0.68197738",  # 34,098,869 / 50,000,000
        "breached", "Assets", ("instant", "2025-12-31"), "20-F/A", "FY", 2025, C_ACCESSION,
        window=("latest_fiscal_year",),
    ),
    "nasdaq-5450b3-g-revenue-latest": Want(
        "nasdaq-5450b3-g-revenue-latest", "Rule 5450(b)(3)", *_ASSETS_REVENUE, _PERIOD,
        "latest_fiscal_year", "revenue", "12327684", "50000000", "-37672316",
        "-0.75344632",  # 37,672,316 / 50,000,000
        "breached", "RevenueFromContractWithCustomerIncludingAssessedTax",
        ("duration", "2025-01-01", "2025-12-31"), "20-F/A", "FY", 2025, C_ACCESSION,
        window=("latest_fiscal_year",),
    ),
    "nasdaq-5450b1-g-equity": Want(
        "nasdaq-5450b1-g-equity", "Rule 5450(b)(1)", "nasdaq-5450b1-g", "Equity Standard",
        "nasdaq-5450b1-g-equity", "main", "stockholders_equity", "-100554759", "10000000",
        "-110554759", "-11.0554759",  # 110,554,759 / 10,000,000
        "breached", "StockholdersEquity", ("instant", "2025-12-31"), "20-F/A", "FY", 2025,
        C_ACCESSION, window=("instant",),
    ),
}  # fmt: skip
# (name, value, reported_financials): the two-of-three branch of the assets/revenue standard
# cannot be measured on one year, and the market value standard needs market inputs.
C_STANDARDS = [
    ("Total Assets/Total Revenue Standard", "unknown", "undetermined"),
    ("Equity Standard", "false", "breached"),
    ("Market Value Standard", "unknown", "undetermined"),
]
C_NOT_MEASURED = 14
C_MISSING_INPUTS = (
    "market_price",
    "publicly_held_shares",
    "total_holders",
    "market_maker_count",
)

# The directory side of the same call.
DIRECTORY_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
DIRECTORY_STAMP = "1030202618:01"
DIRECTORY_SHA256 = "b160a2f2814e5df68d7e414fba70f808f7ad3d20cbbdd167a8a2e38a10044168"
AIXI_NAME = "XIAO-I Corporation - American Depositary Shares"
STATUS_D = "Deficient: Issuer Failed to Meet Nasdaq Continued Listing Requirements"
