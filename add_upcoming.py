#!/usr/bin/env python3
"""
add_upcoming.py — validates an "Add upcoming IPO" GitHub issue and saves it to
docs/data/upcoming.json (the Upcoming IPOs desk reads that file).

DISCLAIMER: Independent personal project. Not tied to any employer or agency.
Public data only. Not financial advice.

The website builds the issue body for you ("Save for both of us"): a ```json block
with the numbers you typed in. Everything is type-checked and size-limited here,
so nothing unexpected can end up on the site. Same id = update in place.
Usage: python add_upcoming.py issue_body.txt  ->  prints the saved id
"""
from __future__ import annotations

import json
import math
import re
import sys
from datetime import date
from pathlib import Path

OUT = Path(__file__).parent / "docs" / "data" / "upcoming.json"
TEXT = {"name": 80, "symbol": 15, "yahoo": 20, "exchange": 40, "sector": 60, "about": 300, "use_of_proceeds": 400,
        "prospectus_url": 400, "notes": 600, "added_by": 40, "updated": 10, "open_date": 10, "close_date": 10, "listing_date": 10}
NUM = ["price_low", "price_high", "lot_size", "issue_size", "fresh_issue", "ofs", "shares_post", "fresh_shares", "pct_sold",
       "gross_margin", "debt", "cash", "proceeds_debt", "promoter_post_pct", "discount_rate"]
NUM_LISTS = ["revenue", "ebitda", "net_profit"]
CURRENCIES = {"USD", "INR", "EUR", "GBP", "CAD", "AUD", "HKD", "JPY", "CNY", "SGD", "CHF"}
UNITS = {"million", "crore", "billion", "lakh", "thousand"}


def _num(x):
    if isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def clean(raw: dict) -> dict:
    o: dict = {}
    for k, n in TEXT.items():
        if isinstance(raw.get(k), str) and raw[k].strip():
            o[k] = raw[k].strip()[:n]
    for k in ("open_date", "close_date", "listing_date", "updated"):
        if k in o:
            try:
                date.fromisoformat(o[k])
            except ValueError:
                del o[k]
    for k in ("prospectus_url",):
        if k in o and not re.match(r"https?://", o[k]):
            del o[k]
    if "yahoo" in o and not re.fullmatch(r"[A-Za-z0-9.\-^]{1,20}", o["yahoo"]):
        del o["yahoo"]
    for k in NUM:
        v = _num(raw.get(k))
        if v is not None:
            o[k] = v
    for k in NUM_LISTS:
        if isinstance(raw.get(k), list):
            vals = [_num(x) for x in raw[k][:8]]
            if vals and all(v is not None for v in vals):
                o[k] = vals
    if isinstance(raw.get("years"), list):
        o["years"] = [str(y)[:12] for y in raw["years"][:8]]
    if isinstance(raw.get("risks"), list):
        o["risks"] = [str(r)[:200] for r in raw["risks"][:8] if str(r).strip()]
    if isinstance(raw.get("sources"), list):
        o["sources"] = [{"url": s["url"][:400], "title": str(s.get("title", ""))[:120]}
                        for s in raw["sources"][:8] if isinstance(s, dict) and re.match(r"https?://", str(s.get("url", "")))]
    o["currency"] = raw.get("currency") if raw.get("currency") in CURRENCIES else "USD"
    o["unit"] = raw.get("unit") if raw.get("unit") in UNITS else "million"
    if not o.get("name") or not (o.get("price_high") or o.get("price_low")):
        raise ValueError("Name and price band are required.")
    rid = str(raw.get("id") or "")
    o["id"] = rid if re.fullmatch(r"[a-z0-9\-]{3,80}", rid) else re.sub(r"[^a-z0-9]+", "-", o["name"].lower()).strip("-")[:60]
    o["updated"] = date.today().isoformat()
    return o


def main(body_path: str) -> str:
    body = Path(body_path).read_text()
    m = re.search(r"```json\s*(\{.*?\})\s*```", body, re.S) or re.search(r"(\{.*\})", body, re.S)
    if not m:
        raise ValueError("No JSON block found in the issue.")
    ipo = clean(json.loads(m.group(1)))
    data = json.loads(OUT.read_text()) if OUT.exists() else {"ipos": []}
    data["ipos"] = [x for x in data.get("ipos", []) if x.get("id") != ipo["id"]] + [ipo]
    data["updated"] = date.today().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    return ipo["id"]


if __name__ == "__main__":
    try:
        print(main(sys.argv[1]))
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
