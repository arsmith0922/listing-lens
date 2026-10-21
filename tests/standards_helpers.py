from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

SYNTHETIC_DIR = Path(__file__).parent / "fixtures" / "standards" / "synthetic"

POLICY_YAML = """\
translation:
  value: allow_flagged
  basis: Synthetic policy for tests.
proxy:
  value: "off"
  basis: Synthetic policy for tests.
cushion:
  default_ratio: 0.10
  basis: Synthetic policy for tests.
"""


def record(**overrides: object) -> dict[str, object]:
    """A valid synthetic rule record as the loader would see it; override any field."""
    base: dict[str, object] = {
        "rule_id": "SYN-T-1",
        "exchange": "nasdaq",
        "tier": "capital",
        "listing_type": "continued",
        "pathways": ["traditional_ipo"],
        "metric": {"kind": "concept", "concept": "stockholders_equity"},
        "window": {"kind": "instant"},
        "comparison": "gte",
        "threshold": 1,
        "threshold_unit": "usd",
        "effective_from": "2020-01-01",
        "citation": {
            "rule_section": "SYN section",
            "rule_url": "https://example.invalid/synthetic",
            "quoted_text": "Synthetic quotation, not rule text.",
            "retrieved_on": "2026-01-02",
        },
        "verification": {"verified": False},
    }
    return {**base, **overrides}


def write_ruleset(
    directory: Path,
    rule_files: Mapping[str, Sequence[Mapping[str, object]] | str],
    *,
    policy: str | None = POLICY_YAML,
) -> Path:
    """Write rule files (JSON is valid YAML) and a policy file into a directory."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in rule_files.items():
        text = content if isinstance(content, str) else json.dumps(list(content))
        (directory / name).write_text(text, encoding="utf-8", newline="\n")
    if policy is not None:
        (directory / "policy.yaml").write_text(policy, encoding="utf-8", newline="\n")
    return directory
