from __future__ import annotations

from listinglens.core.branding import PRODUCT_NAME, VERSION, user_agent


def test_product_name_is_listinglens() -> None:
    assert PRODUCT_NAME == "ListingLens"


def test_user_agent_composes_product_name_version_and_contact() -> None:
    assert user_agent("test@example.com") == f"{PRODUCT_NAME}/{VERSION} (test@example.com)"


def test_user_agent_contains_contact_and_starts_with_product_name() -> None:
    result = user_agent("a@b.com")
    assert result.startswith(PRODUCT_NAME)
    assert "a@b.com" in result
