"""
hq_events.py — the Buffett agent's plain-English event list for Agent HQ (docs/data/events.json).

DISCLAIMER: Independent personal project. Not tied to any employer or agency. Public market data
only. No internal or personal data (no SSNs/PHI). Educational research, not financial advice.
Every event describes something the agent actually did in this run.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

FILE = Path(__file__).parent / "docs" / "data" / "events.json"
KEEP = 200


def add(text: str, place: str, kind: str, t: str | None = None, **kw) -> None:
    try:
        data = json.loads(FILE.read_text()) if FILE.exists() else {"bot": "buffett", "events": []}
    except Exception:
        data = {"bot": "buffett", "events": []}
    data["events"].append({"t": t or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                           "bot": "buffett", "place": place, "kind": kind, "text": text, **kw})
    data["events"] = sorted(data["events"], key=lambda e: e["t"])[-KEEP:]
    data["generated"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    FILE.write_text(json.dumps(data, ensure_ascii=False, indent=0))


def describe_stock(e: dict) -> str:
    n = (e.get("news30") or {}).get("count")
    v = e.get("valuation") or {}
    s = f"{e['ticker']} ({e.get('name') or e['ticker']}): {e['overall']['label']}, {e['overall']['score']:.0f}/100"
    if v.get("base") and e.get("price"):
        s += f"; fair value about ${v['base']:,.0f} vs a ${e['price']:,.2f} price"
    if n:
        s += f"; read {n} news stories from the past month"
    return s


def after_build(previous: dict, stocks: list) -> None:
    """One summary event for a full re-score, plus any verdict changes."""
    ipo = sum(1 for s in stocks if s["desk"] == "ipo")
    top = max(stocks, key=lambda s: s["overall"]["score"]) if stocks else None
    add(f"Re-scored all {len(stocks)} stocks ({ipo} IPOs, {len(stocks) - ipo} established companies) with every investor’s rules and "
        f"a month of news for each." + (f" Top score: {top['ticker']} ({top['overall']['label']}, {top['overall']['score']:.0f})." if top else ""),
        "research", "rescore")
    changes = []
    for s in stocks:
        p = previous.get((s["desk"], s["ticker"]))
        if p and p.get("overall", {}).get("label") != s["overall"]["label"]:
            changes.append(f"{s['ticker']} {p['overall']['label']} → {s['overall']['label']}")
    if changes:
        add("Changed its mind on " + "; ".join(changes[:5]) + ("…" if len(changes) > 5 else "") + ".", "research", "verdicts")
