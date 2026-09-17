from __future__ import annotations

PRODUCT_NAME = "ListingLens"
VERSION = "0.1.0"


def user_agent(contact: str) -> str:
    """Build the SEC-compliant User-Agent string: '<product>/<version> (<contact>)'."""
    return f"{PRODUCT_NAME}/{VERSION} ({contact})"
