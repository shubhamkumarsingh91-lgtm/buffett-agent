"""
edgar.py — finds a company's IPO prospectus on SEC EDGAR (free, no API key).

DISCLAIMER: Independent personal project. Not tied to any employer or agency.
Public data only. Not financial advice.

For a recent IPO the most useful document is the final prospectus (form 424B4,
or the S-1 / F-1 registration statement for foreign issuers). It contains the
business description, risk factors, use of proceeds, share classes, lock-up
terms and audited financials. We link it so you can read it yourself, and we
record its date, which is a reliable IPO date.

SEC asks automated clients to identify themselves in the User-Agent and to stay
under 10 requests per second; we make at most 2 requests per IPO.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Optional

UA = "Long-Term Lab research site (github.com/shubhamkumarsingh91-lgtm/buffett-agent)"
_TICKER_MAP: Optional[dict] = None
PROSPECTUS_FORMS = ("424B4", "424B1", "S-1", "F-1", "S-1/A", "F-1/A")


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def cik_for(ticker: str) -> Optional[int]:
    global _TICKER_MAP
    if _TICKER_MAP is None:
        try:
            raw = _get_json("https://www.sec.gov/files/company_tickers.json")
            _TICKER_MAP = {v["ticker"].upper(): int(v["cik_str"]) for v in raw.values()}
        except Exception:
            _TICKER_MAP = {}
    t = ticker.upper()
    return _TICKER_MAP.get(t) or _TICKER_MAP.get(t.replace("-", ".")) or _TICKER_MAP.get(t.replace(".", "-"))


def find_prospectus(ticker: str) -> Optional[dict]:
    """Returns {"form", "date", "url", "company_url"} for the IPO prospectus, or None."""
    cik = cik_for(ticker)
    if not cik:
        return None
    try:
        sub = _get_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    except Exception:
        return None
    recent = sub.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    company_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=424B&dateb=&owner=include&count=40"
    # Prefer the final prospectus (424B4); otherwise the earliest registration statement.
    for wanted in PROSPECTUS_FORMS:
        idx = [i for i, f in enumerate(forms) if f == wanted]
        if not idx:
            continue
        i = idx[-1]                       # oldest of that form = the IPO one
        acc = recent["accessionNumber"][i].replace("-", "")
        doc = recent["primaryDocument"][i]
        return {
            "form": wanted,
            "date": recent["filingDate"][i],
            "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}",
            "company_url": company_url,
        }
    return {"form": None, "date": None, "url": None, "company_url": company_url}
