from __future__ import annotations

PRODUCT_NAME = "ListingLens"
VERSION = "0.1.0"


def public_user_agent() -> str:
    """The User-Agent for hosts that are not the SEC: product and version, never the contact."""
    return f"{PRODUCT_NAME}/{VERSION}"


def user_agent(contact: str) -> str:
    """Build the SEC-compliant User-Agent string: '<product>/<version> (<contact>)'."""
    return f"{PRODUCT_NAME}/{VERSION} ({contact})"
