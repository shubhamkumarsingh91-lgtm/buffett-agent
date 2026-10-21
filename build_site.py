#!/usr/bin/env python3
"""
build_site.py — scores every ticker in watchlist.txt and writes the data the
website reads (docs/data/scores.json and docs/data/history.json).

DISCLAIMER: Independent personal project. Not tied to any employer or agency.
Public market data only (Yahoo Finance via yfinance). No internal or personal
data (no SSNs/PHI). Educational research, not financial advice. Never trades.

How it runs:
  * GitHub Actions runs it every weekday evening and whenever watchlist.txt
    changes (see .github/workflows/update.yml).
  * You can also run it on your laptop:  python build_site.py
    then open docs/index.html through a tiny local server:
        python -m http.server -d docs 8000   ->  http://localhost:8000

If Yahoo fails for one ticker, the previous good result is kept and marked
"stale" so the site never loses a stock because of one bad night.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from data import StockData, fetch_stock_data
from strategies import buffett_score, graham_score, lynch_score, overall_verdict

ROOT = Path(__file__).parent
WATCHLIST = ROOT / "watchlist.txt"
OUT_DIR = ROOT / "docs" / "data"
SCORES = OUT_DIR / "scores.json"
HISTORY = OUT_DIR / "history.json"
PAUSE_SECONDS = 2.0          # be gentle with Yahoo's rate limits


def read_watchlist() -> list[tuple[str, str]]:
    """Lines like 'KO  # Coca-Cola, dividend compounder'. Returns [(ticker, note)]."""
    out, seen = [], set()
    for line in WATCHLIST.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        ticker, _, note = line.partition("#")
        ticker = ticker.strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            out.append((ticker, note.strip()))
    return out


def _r(x, n=4):
    return None if x is None else round(float(x), n)


def score_stock(d: StockData, note: str = "") -> dict:
    """Run the three lenses and flatten everything the website shows."""
    b, g, l = buffett_score(d), graham_score(d), lynch_score(d)
    overall = overall_verdict([b, g, l])
    iv = d.intrinsic_value_per_share()
    mos = (iv - d.price) / iv if (iv and iv > 0 and d.price) else None
    roe = [v for v in d.roe_series if v is not None]
    gm = [v for v in d.gross_margin_series if v is not None]
    return {
        "ticker": d.ticker,
        "note": note,
        "name": d.name,
        "sector": d.sector,
        "industry": d.industry,
        "price": _r(d.price, 2),
        "market_cap": d.market_cap,
        "week52_high": _r(d.fifty_two_week_high, 2),
        "week52_low": _r(d.fifty_two_week_low, 2),
        "overall": {
            "label": overall["label"],
            "rationale": overall["rationale"],
            "score": overall["average_score"],
        },
        "lenses": [
            {"key": key, "name": r.strategy, "score": r.score, "verdict": r.verdict,
             "pros": r.pros, "cons": r.cons}
            for key, r in (("buffett", b), ("graham", g), ("lynch", l))
        ],
        "metrics": {
            "pe": _r(d.pe_ratio, 2),
            "forward_pe": _r(d.forward_pe, 2),
            "pb": _r(d.pb_ratio, 2),
            "peg": _r(d.peg_ratio, 2),
            "dividend_yield": _r(d.dividend_yield),
            "payout_ratio": _r(d.payout_ratio),
            "roe_avg": _r(sum(roe) / len(roe)) if roe else None,
            "gross_margin_avg": _r(sum(gm) / len(gm)) if gm else None,
            "debt_to_equity": _r(d.debt_to_equity, 2),
            "current_ratio": _r(d.current_ratio, 2),
            "graham_number": _r(d.graham_number, 2),
            "intrinsic_value": _r(iv, 2),
            "margin_of_safety": _r(mos),
            "earnings_growth": _r(d.earnings_growth_estimate),
            "beta": _r(d.beta, 2),
        },
        "news": d.news[:5],
        "data_notes": d.data_notes,
        "stale": False,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def build(fetch=fetch_stock_data) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    previous = {s["ticker"]: s for s in _load(SCORES, {}).get("stocks", [])}
    history = _load(HISTORY, {})
    today = datetime.now(timezone.utc).date().isoformat()

    stocks, failed = [], []
    watch = read_watchlist()
    for i, (ticker, note) in enumerate(watch):
        try:
            entry = score_stock(fetch(ticker), note)
            print(f"  ok   {ticker:7s} {entry['overall']['score']:5.1f}  {entry['overall']['label']}")
            h = [p for p in history.get(ticker, []) if p["date"] != today]
            h.append({"date": today, "score": entry["overall"]["score"], "price": entry["price"],
                      "b": entry["lenses"][0]["score"], "g": entry["lenses"][1]["score"],
                      "l": entry["lenses"][2]["score"]})
            history[ticker] = h[-400:]
        except BaseException as e:            # SystemExit from data.py on fetch failure
            if isinstance(e, KeyboardInterrupt):
                raise
            failed.append(ticker)
            print(f"  FAIL {ticker:7s} {e}")
            if ticker in previous:
                entry = dict(previous[ticker], stale=True, note=note or previous[ticker].get("note", ""))
            else:
                continue
        stocks.append(entry)
        if i < len(watch) - 1:
            time.sleep(PAUSE_SECONDS)

    stocks.sort(key=lambda s: -(s["overall"]["score"] or 0))
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(stocks),
        "failed": failed,
        "stocks": stocks,
    }
    SCORES.write_text(json.dumps(payload, indent=1, default=str))
    HISTORY.write_text(json.dumps({t: history[t] for t in sorted(history) if t in {s['ticker'] for s in stocks}},
                                  separators=(",", ":")))
    print(f"\nWrote {len(stocks)} stocks ({len(failed)} failed) -> {SCORES.relative_to(ROOT)}")
    return payload


if __name__ == "__main__":
    result = build()
    # Fail the job only if nothing at all could be scored (e.g. Yahoo fully blocked).
    sys.exit(0 if result["count"] else 1)
