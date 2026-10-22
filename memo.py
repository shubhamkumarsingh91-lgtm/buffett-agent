"""
memo.py — writes a plain-English research memo for each stock from its numbers.

DISCLAIMER: Independent personal project. Not tied to any employer or agency.
Public data only. Educational research, not financial advice.

No API key needed: the memo is assembled by rules from the scores, KPIs,
valuation range and checklist. If a GEMINI_API_KEY secret exists, the nightly
job also asks Gemini (free tier) for an extra "analyst's take" paragraph; if the
key is missing or the call fails, nothing breaks and the rule-based memo stands.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional


def _m(x):
    if x is None:
        return "n/a"
    return f"${x/1e12:,.2f}T" if x >= 1e12 else f"${x/1e9:,.1f}B" if x >= 1e9 else f"${x/1e6:,.0f}M"


def _pick(lenses: list, kind: str, n: int) -> list:
    """Strongest points first: pros from the highest-scoring lenses, cons from the lowest."""
    ordered = sorted(lenses, key=lambda l: -l["score"] if kind == "pros" else l["score"])
    out, seen = [], set()
    for l in ordered:
        for p in l[kind]:
            key = p[:40]
            if key not in seen and "need the prospectus" not in p:
                seen.add(key)
                out.append(f"{p} ({l['short']})")
            if len(out) >= n:
                return out
    return out


def build_memo(e: dict) -> dict:
    """e = one stock entry as written by build_site.score_stock (before the memo is attached)."""
    k, v, ipo = e["kpis"], e["valuation"], e["desk"] == "ipo"
    verdict = e["overall"]["label"]
    name = e.get("name") or e["ticker"]

    # The business in one paragraph
    kind = (e.get('industry') or e.get('sector') or 'public').lower()
    bits = [f"{name} ({e['ticker']}) is {'an' if kind[:1] in 'aeiou' else 'a'} {kind} company"]
    if k.get("market_cap"):
        bits.append(f"worth about {_m(k['market_cap'])}")
    s = " ".join(bits) + "."
    if k.get("revenue_ttm"):
        s += f" It brought in {_m(k['revenue_ttm'])} of revenue over the last year"
        if k.get("revenue_growth_yoy") is not None:
            s += f", {'up' if k['revenue_growth_yoy'] >= 0 else 'down'} {abs(k['revenue_growth_yoy']):.0%} from a year earlier"
        s += "."
    if k.get("operating_margin") is not None:
        s += (f" It keeps {k['operating_margin']:.0%} of sales as operating profit."
              if k["operating_margin"] > 0 else " It is not yet profitable at the operating level.")
    if ipo and e.get("ipo", {}).get("months_listed") is not None:
        s += f" It has traded publicly for about {e['ipo']['months_listed']:.0f} months."

    # Valuation sentence
    if v.get("base"):
        mos = v.get("margin_of_safety")
        val = (f"Using a simple two-stage cash-flow model ({v['method']}, {v['growth']:.0%} growth fading to 3%, "
               f"{v.get('discount_rate', 0.09):.0%} discount rate), fair value is roughly ${v['base']:,.2f} a share "
               f"(bear ${v['bear']:,.2f}, bull ${v['bull']:,.2f}) against a price of ${e['price']:,.2f}. ")
        if v.get("confidence") == "low":
            val += "Low confidence: cash flow and earnings disagree a lot here, so treat this range loosely. "
        if mos is not None:
            val += (f"That's a {mos:.0%} margin of safety: Buffett and Graham wanted 25%+." if mos >= 0.25 else
                    f"That's a thin {mos:.0%} margin of safety." if mos >= 0 else
                    (f"The price is more than {(e['price'] / v['base']):.0f}x the base-case value: the market expects far more growth than this model assumes." if mos <= -1 else
                     f"The price is {abs(mos):.0%} above the base-case value, so you're paying for growth that hasn't happened yet."))
    else:
        val = (v.get("note") or "Can't value it on cash flow yet.")
        if k.get("price_to_sales"):
            val += f" The market prices it at {k['price_to_sales']:.1f}x sales."

    # What to watch
    watch = []
    if ipo:
        for it in e.get("ipo", {}).get("checklist", []):
            if it["status"] in ("fail", "warn"):
                watch.append(f"{it['label']}: {it['detail']}")
    if k.get("revenue_growth_yoy") is not None:
        watch.append(f"Revenue growth stays near or above {max(k['revenue_growth_yoy'], 0):.0%} (last reading).")
    if k.get("operating_margin") is not None:
        watch.append(f"Operating margin ({k['operating_margin']:.0%}) keeps rising as the company grows.")
    if k.get("fcf_margin") is not None and k["fcf_margin"] < 0:
        watch.append("Free cash flow turns positive. Until then it may need to raise money.")
    if k.get("debt_to_equity") is not None and k["debt_to_equity"] > 1:
        watch.append(f"Debt (debt/equity {k['debt_to_equity']:.1f}) comes down.")
    if k.get("short_pct_float") is not None and k["short_pct_float"] >= 0.1:
        watch.append(f"Short interest ({k['short_pct_float']:.0%} of float): find out what the bears are betting on.")
    watch = watch[:6]

    # If you act on it
    if verdict.startswith("BUY"):
        plan = ("Read the latest annual report (or prospectus) first. If it still holds up, start with a partial "
                "position, about a third of what you'd eventually want, and add after the next two quarterly reports confirm the story.")
    elif verdict.startswith(("WATCH", "WORTH")):
        plan = "Put it on watch."
        if v.get("base"):
            plan += f" A price around ${v['base'] * 0.75:,.2f} would give the 25% margin of safety value investors look for."
        plan += " Re-check after the next earnings report."
    elif verdict.startswith("WAIT"):
        plan = "Don't buy yet. Revisit once the open items in the checklist are resolved."
    else:
        plan = "Pass for now. Revisit only if the business or the price changes materially."

    buffett = ("Buffett almost never buys IPOs: the seller picks the time and the price, so the odds favor them. "
               "He prefers businesses with years of public results." if ipo else
               f"On Buffett's own tests this scores {next(l['score'] for l in e['lenses'] if l['key']=='buffett'):.0f}/100.")

    memo = {
        "headline": f"{verdict}. {e['overall']['rationale']}",
        "business": s,
        "bull": _pick(e["lenses"], "pros", 4),
        "bear": _pick(e["lenses"], "cons", 4),
        "valuation": val,
        "watch": watch,
        "plan": plan,
        "buffett_view": buffett,
        "ai": None,
    }
    memo["ai"] = _gemini_take(e, memo)
    return memo


def _gemini_take(e: dict, memo: dict) -> Optional[str]:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    prompt = (
        "You are a long-term value investor writing in the style of a Berkshire Hathaway letter: plain words, "
        "no hype, honest about risks. In 120-170 words, give your take on whether a patient investor should "
        "own this stock for 5+ years, what would have to be true, and the single biggest risk. Do not invent "
        "numbers; use only the data below. End with: 'Not financial advice.'\n\n"
        + json.dumps({"ticker": e["ticker"], "name": e.get("name"), "desk": e["desk"], "verdict": e["overall"],
                      "kpis": e["kpis"], "valuation": e["valuation"], "memo": {k: memo[k] for k in ("bull", "bear", "watch")}},
                     default=str)[:9000])
    return gemini_text(prompt)


def gemini_text(prompt: str, timeout: int = 40) -> Optional[str]:
    """Free-tier Gemini call; None if there's no GEMINI_API_KEY secret or anything fails."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    url = ("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + key)
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode())
        return out["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return None
