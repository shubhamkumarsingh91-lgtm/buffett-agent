#!/usr/bin/env python3
"""
build_site.py — scores both desks and writes the data the website reads.

DISCLAIMER: Independent personal project. Not tied to any employer or agency.
Public market data only (Yahoo Finance via yfinance, SEC EDGAR). No internal or
personal data (no SSNs/PHI). Educational research, not financial advice. Never trades.

Two desks:
  * Company Desk  (watchlist.txt): Buffett & Munger, Graham, Lynch, Fisher, Greenblatt
  * IPO Desk      (ipos.txt):      Jay Ritter (IPO research) + Bill Gurley (revenue quality),
                                   Fisher as a growth-quality check, an IPO checklist and the
                                   SEC prospectus link
Every stock also gets KPIs, a bear/base/bull valuation and a written research memo.

Run locally:  python build_site.py && python -m http.server -d docs 8000
If Yahoo fails for one ticker, the previous good result is kept and marked "stale".
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from data import StockData, fetch_stock_data
from strategies import (buffett_score, graham_score, lynch_score, fisher_score, greenblatt_score,
                        ritter_score, gurley_score, valuation, ipo_checklist, company_verdict, ipo_verdict)
from memo import build_memo

ROOT = Path(__file__).parent
LISTS = {"company": ROOT / "watchlist.txt", "ipo": ROOT / "ipos.txt"}
OUT_DIR = ROOT / "docs" / "data"
SCORES = OUT_DIR / "scores.json"
HISTORY = OUT_DIR / "history.json"
PAUSE_SECONDS = 2.0
SHORT = {"buffett": "Buffett", "graham": "Graham", "lynch": "Lynch", "fisher": "Fisher",
         "greenblatt": "Greenblatt", "ritter": "Ritter", "gurley": "Gurley"}


def read_list(path: Path) -> list[tuple[str, str]]:
    out, seen = [], set()
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
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


def _lens(key, r):
    return {"key": key, "short": SHORT[key], "name": r.strategy, "score": r.score, "verdict": r.verdict,
            "pros": r.pros, "cons": r.cons}


def kpis(d: StockData) -> dict:
    roe = [v for v in d.roe_series if v is not None]
    gb = greenblatt_score(d).metrics
    return {
        # growth
        "revenue_ttm": d.revenue_ttm, "revenue_growth_yoy": _r(d.revenue_growth_yoy), "revenue_cagr": _r(d.revenue_cagr),
        "earnings_growth": _r(d.earnings_growth_estimate), "quarterly_revenue": [round(q) for q in d.quarterly_revenue[-8:] if q],
        # profitability
        "gross_margin": _r(d.gross_margin_ttm), "operating_margin": _r(d.operating_margin_ttm),
        "profit_margin": _r(d.profit_margin_ttm), "roe_avg": _r(sum(roe) / len(roe)) if roe else None,
        "roic": gb.get("roic"), "roa": _r(d.return_on_assets),
        # cash
        "free_cash_flow": d.free_cash_flow, "fcf_margin": _r(d.fcf_margin), "total_cash": d.total_cash,
        "cash_runway_years": _r(d.cash_runway_years, 1),
        "rule_of_40": _r(((d.revenue_growth_yoy or 0) + d.fcf_margin) * 100, 1)
                      if (d.fcf_margin is not None and d.revenue_growth_yoy is not None) else None,
        # valuation
        "market_cap": d.market_cap, "pe": _r(d.pe_ratio, 2), "forward_pe": _r(d.forward_pe, 2), "pb": _r(d.pb_ratio, 2),
        "peg": _r(d.peg_ratio, 2), "price_to_sales": _r(d.price_to_sales, 2), "ev_to_ebitda": _r(d.ev_to_ebitda, 2),
        "earnings_yield": gb.get("earnings_yield"), "graham_number": _r(d.graham_number, 2),
        "dividend_yield": _r(d.dividend_yield), "payout_ratio": _r(d.payout_ratio),
        # balance sheet & ownership
        "debt_to_equity": _r(d.debt_to_equity, 2), "current_ratio": _r(d.current_ratio, 2),
        "insider_pct": _r(d.insider_ownership_pct), "institutional_pct": _r(d.institutional_ownership_pct),
        "short_pct_float": _r(d.short_pct_float), "beta": _r(d.beta, 2),
    }


def score_stock(d: StockData, desk: str, note: str = "", prospectus: dict | None = None) -> dict:
    v = valuation(d)
    if desk == "ipo":
        main = [("ritter", ritter_score(d)), ("gurley", gurley_score(d))]
        overall = ipo_verdict([r for _, r in main], d)
        lenses = [_lens(k, r) for k, r in main] + [_lens("fisher", fisher_score(d))]
        classic = {k: f(d).score for k, f in (("buffett", buffett_score), ("graham", graham_score),
                                                ("lynch", lynch_score), ("greenblatt", greenblatt_score))}
    else:
        res = [("buffett", buffett_score(d)), ("graham", graham_score(d)), ("lynch", lynch_score(d)),
               ("fisher", fisher_score(d)), ("greenblatt", greenblatt_score(d))]
        overall = company_verdict([r for _, r in res])
        lenses, classic = [_lens(k, r) for k, r in res], None
    m = d.months_listed
    entry = {
        "ticker": d.ticker, "desk": desk, "note": note, "name": d.name, "sector": d.sector, "industry": d.industry,
        "price": _r(d.price, 2), "week52_high": _r(d.fifty_two_week_high, 2), "week52_low": _r(d.fifty_two_week_low, 2),
        "overall": {"label": overall["label"], "rationale": overall["rationale"], "score": overall["average_score"]},
        "lenses": lenses, "classic": classic, "kpis": kpis(d), "valuation": v,
        "recent_ipo": m is not None and m < 36,
        "ipo": {"months_listed": _r(m, 1), "first_trade_date": d.first_trade_date,
                "first_day_open": _r(d.first_day_open, 2), "first_day_close": _r(d.first_day_close, 2),
                "prospectus": prospectus, "checklist": ipo_checklist(d, prospectus) if desk == "ipo" else []},
        "news": d.news[:5], "data_notes": d.data_notes, "stale": False,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    entry["memo"] = build_memo(entry)
    return entry


def _load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def default_fetch(ticker: str, desk: str):
    d = fetch_stock_data(ticker, with_history=(desk == "ipo"))
    pro = None
    if desk == "ipo":
        try:
            from edgar import find_prospectus
            pro = find_prospectus(ticker)
        except Exception as e:
            pro = None
            d.data_notes.append(f"SEC prospectus lookup failed ({type(e).__name__}).")
        if pro is None:
            d.data_notes.append("Prospectus link unavailable: ticker not found in SEC's company list.")
    return d, pro


def attach_news(entry: dict) -> None:
    """Adds the "Last 30 days" news paragraph + key headlines (never fails the build)."""
    try:
        from news import build_news
        entry["news30"] = build_news(entry.get("name") or entry["ticker"], entry["ticker"], entry.get("price"))
    except Exception:
        entry["news30"] = None


def promote_listed_ipos() -> list[str]:
    """Upcoming IPOs whose listing date has passed and that have a market symbol move to ipos.txt."""
    path = OUT_DIR / "upcoming.json"
    data = _load(path, {"ipos": []})
    have = {t for t, _ in read_list(LISTS["ipo"])} | {t for t, _ in read_list(LISTS["company"])}
    today, moved = datetime.now(timezone.utc).date().isoformat(), []
    for ipo in data.get("ipos", []):
        sym, ld = (ipo.get("yahoo") or "").upper(), ipo.get("listing_date")
        if sym and ld and ld <= today and not ipo.get("moved_to_ipo_desk"):
            if sym not in have:
                with LISTS["ipo"].open("a") as f:
                    f.write(f"{sym}    # listed {ld}, moved from Upcoming IPOs: {ipo.get('name', '')}\n")
            ipo["moved_to_ipo_desk"] = today
            moved.append(sym)
    if moved:
        path.write_text(json.dumps(data, indent=1, ensure_ascii=False))
        print(f"  Moved to IPO Desk after listing: {', '.join(moved)}")
    return moved


def build(fetch=default_fetch) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    promote_listed_ipos()
    previous = {(s.get("desk", "company"), s["ticker"]): s for s in _load(SCORES, {}).get("stocks", [])}
    history = _load(HISTORY, {})
    today = datetime.now(timezone.utc).date().isoformat()
    stocks, failed = [], []
    jobs = [(desk, t, n) for desk, path in LISTS.items() for t, n in read_list(path)]
    for i, (desk, ticker, note) in enumerate(jobs):
        try:
            d, pro = fetch(ticker, desk)
            # No price and no name means Yahoo doesn't know this symbol (not listed yet, typo,
            # or a non-US listing without its suffix, e.g. RELIANCE.NS). Don't invent a score.
            if d.price is None and not d.name:
                raise SystemExit("no market data for this symbol (not listed yet, or needs an exchange suffix like .NS)")
            entry = score_stock(d, desk, note, pro)
            attach_news(entry)
            print(f"  ok   {desk:7s} {ticker:7s} {entry['overall']['score']:5.1f}  {entry['overall']['label']}")
            key = f"{desk}:{ticker}"
            h = [p for p in history.get(key, []) if p["date"] != today]
            h.append({"date": today, "score": entry["overall"]["score"], "price": entry["price"],
                      **{l["key"]: l["score"] for l in entry["lenses"]}})
            history[key] = h[-400:]
        except BaseException as e:
            if isinstance(e, KeyboardInterrupt):
                raise
            failed.append(f"{desk}:{ticker}")
            print(f"  FAIL {desk:7s} {ticker:7s} {e}")
            prev = previous.get((desk, ticker))
            if not prev or "memo" not in prev:      # skip v1-format leftovers
                continue
            entry = dict(prev, stale=True, note=note or prev.get("note", ""))
        stocks.append(entry)
        if i < len(jobs) - 1:
            time.sleep(PAUSE_SECONDS)

    stocks.sort(key=lambda s: -(s["overall"]["score"] or 0))
    payload = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "version": 2,
               "count": len(stocks), "failed": failed, "stocks": stocks}
    SCORES.write_text(json.dumps(payload, indent=1, default=str))
    keep = {f"{s['desk']}:{s['ticker']}" for s in stocks}
    HISTORY.write_text(json.dumps({k: history[k] for k in sorted(history) if k in keep}, separators=(",", ":")))
    print(f"\nWrote {len(stocks)} stocks ({len(failed)} failed) -> {SCORES.relative_to(ROOT)}")
    return payload


EXCHANGE_SUFFIXES = {"NS", "BO", "L", "TO", "V", "HK", "T", "AX", "DE", "PA", "AS", "SW", "MI", "MC", "SI", "KS", "SS", "SZ", "SA", "MX"}


def normalize_ticker(raw: str) -> str:
    """BRK.B -> BRK-B (Yahoo style) but keep exchange suffixes like RELIANCE.NS or SHOP.TO."""
    t = raw.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-^]{0,14}", t):
        raise SystemExit(f"{raw!r} doesn't look like a ticker")
    base, dot, suf = t.rpartition(".")
    return t if dot and suf in EXCHANGE_SUFFIXES else t.replace(".", "-")


def analyze_one(ticker: str, desk: str, fetch=default_fetch) -> dict:
    """Scores one ticker right away (the site's "Analyze now" button) and merges it into the
    published data, without re-scoring everything else. Adds it to the desk's list so the
    nightly update keeps it fresh. Raises SystemExit with a plain message if there's no data."""
    if desk not in LISTS:
        raise SystemExit(f"unknown desk {desk!r}")
    d, pro = fetch(ticker, desk)
    if d.price is None and not d.name:
        raise SystemExit(f"No market data for {ticker}: not listed yet, a typo, or a non-US listing that needs a suffix like .NS")
    have = {t for t, _ in read_list(LISTS[desk])}
    note = next((n for t, n in read_list(LISTS[desk]) if t == ticker), "")
    entry = score_stock(d, desk, note, pro)
    attach_news(entry)
    data = _load(SCORES, {"stocks": [], "version": 2})
    stocks = [s for s in data.get("stocks", []) if not (s.get("desk", "company") == desk and s["ticker"] == ticker)]
    stocks.append(entry)
    stocks.sort(key=lambda s: -(s["overall"]["score"] or 0))
    data.update({"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "version": 2,
                 "count": len(stocks), "stocks": stocks})
    SCORES.write_text(json.dumps(data, indent=1, default=str))
    history, today = _load(HISTORY, {}), datetime.now(timezone.utc).date().isoformat()
    key = f"{desk}:{ticker}"
    h = [p for p in history.get(key, []) if p["date"] != today]
    h.append({"date": today, "score": entry["overall"]["score"], "price": entry["price"],
              **{l["key"]: l["score"] for l in entry["lenses"]}})
    history[key] = h[-400:]
    HISTORY.write_text(json.dumps({k: history[k] for k in sorted(history)}, separators=(",", ":")))
    if ticker not in have:
        with LISTS[desk].open("a") as f:
            f.write(f"{ticker}    # added from the site's search\n")
    print(f"  ok   {desk:7s} {ticker:7s} {entry['overall']['score']:5.1f}  {entry['overall']['label']}")
    return entry


if __name__ == "__main__":
    # python build_site.py                       -> score everything
    # python build_site.py --only SPCX --desk ipo -> score one ticker now
    if "--only" in sys.argv:
        # one ticker or a comma-separated list (the portfolio's "Analyze my stocks"), max 15
        raw = [x for x in sys.argv[sys.argv.index("--only") + 1].split(",") if x.strip()][:15]
        dk = sys.argv[sys.argv.index("--desk") + 1] if "--desk" in sys.argv else "company"
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        ok, bad = [], []
        for i, x in enumerate(raw):
            try:
                t = normalize_ticker(x)
                analyze_one(t, dk)
                ok.append(t)
            except BaseException as e:
                if isinstance(e, KeyboardInterrupt):
                    raise
                bad.append(x.strip().upper())
                print(f"  FAIL {dk:7s} {x.strip().upper():7s} {e}")
            if i < len(raw) - 1:
                time.sleep(PAUSE_SECONDS)
        print(f"\nAnalyzed {len(ok)}: {', '.join(ok) or '-'}" + (f"  |  no data: {', '.join(bad)}" if bad else ""))
        sys.exit(0 if ok else 1)          # partial success still saves what worked
    result = build()
    sys.exit(0 if result["count"] else 1)
