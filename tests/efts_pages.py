from __future__ import annotations

import json


def hit(n: int, *, description: str | None = "10-K") -> dict[str, object]:
    """A synthetic EFTS hit with a distinct, valid accession number per n."""
    adsh = f"0000320193-23-{n:06d}"
    source: dict[str, object] = {
        "adsh": adsh,
        "ciks": ["0000320193"],
        "display_names": ["Apple Inc."],
        "form": "10-K",
        "root_forms": ["10-K"],
        "file_date": "2023-11-03",
        "period_ending": "2023-09-30",
        "file_type": "10-K",
        "file_description": description,
        "file_num": ["001-36743"],
        "film_num": ["231373000"],
        "biz_states": ["CA"],
        "biz_locations": ["Cupertino, CA"],
        "inc_states": ["CA"],
        "sics": ["3571"],
        "items": [],
        "sequence": 1,
        "xsl": None,
    }
    return {"_id": f"{adsh}:doc.htm", "_source": source}


def page(hits: list[dict[str, object]], *, total: int = 0, relation: str = "eq") -> bytes:
    """A synthetic EFTS response body in the real envelope shape."""
    body = {
        "took": 1,
        "hits": {"total": {"value": total, "relation": relation}, "hits": hits},
        "aggregations": {},
    }
    return json.dumps(body).encode()
