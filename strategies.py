"""
strategies.py — three independent scoring lenses over a StockData object:

  * buffett_score   — Buffett/Munger quality compounding: moat (margins),
                       balance-sheet strength, earnings consistency,
                       capital allocation, margin-of-safety on owner earnings.
  * graham_score     — Ben Graham deep value: Graham Number, P/E & P/B caps,
                       current ratio, debt vs working capital, earnings
                       stability, dividend record.
  * lynch_score      — Peter Lynch GARP: PEG ratio, growth-category
                       classification, debt load, institutional ownership,
                       buyback/dilution trend.

Each returns a StrategyResult: 0-100 score, verdict, and explicit pros/cons
so you can see *why*, not just a number. None of this is financial advice —
these are quantitative proxies for qualitative judgments Buffett, Graham and
Lynch each made mostly by hand.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Optional

from data import StockData


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class StrategyResult:
    strategy: str
    score: float
    verdict: str
    pros: list = field(default_factory=list)
    cons: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _verdict_from_score(score: float) -> str:
    if score >= 75:
        return "Strong fit"
    if score >= 55:
        return "Partial fit"
    if score >= 35:
        return "Weak fit"
    return "Poor fit"


# --------------------------------------------------------------------------
# Buffett / Munger — quality compounding
# --------------------------------------------------------------------------

def buffett_score(d: StockData, discount_rate: float = 0.09, growth_rate: float = 0.04) -> StrategyResult:
    pros, cons, metrics = [], [], {}
    scores, weights = [], []

    # Moat proxy: margins, level + stability
    gm = [v for v in d.gross_margin_series if v is not None]
    om = [v for v in d.operating_margin_series if v is not None]
    if gm or om:
        avg_gm = statistics.mean(gm) if gm else None
        avg_om = statistics.mean(om) if om else None
        vol_penalty = statistics.pstdev(gm) * 100 if len(gm) >= 2 else 0.0
        level = 0.0
        if avg_gm is not None:
            level += _clamp((avg_gm - 0.20) / 0.50 * 100) * 0.6
        if avg_om is not None:
            level += _clamp((avg_om - 0.10) / 0.25 * 100) * (0.4 if avg_gm is not None else 1.0)
        moat = _clamp(level - vol_penalty * 2)
        scores.append(moat); weights.append(0.20)
        metrics["moat_score"] = round(moat, 1)
        if avg_gm is not None and avg_gm >= 0.45:
            pros.append(f"High gross margin ({avg_gm:.0%}) suggests real pricing power / a moat.")
        elif avg_gm is not None and avg_gm < 0.25:
            cons.append(f"Thin gross margin ({avg_gm:.0%}) — little evidence of a durable moat.")
        if vol_penalty > 2:
            cons.append("Margins are unstable year to year — less predictable than Buffett prefers.")
    else:
        scores.append(50.0); weights.append(0.20)
        cons.append("No margin data available to assess moat strength.")

    # Balance sheet strength
    de = d.debt_to_equity
    if de is not None:
        de_score = _clamp(100 - (de / 1.5) * 100)
        cr = d.current_ratio
        bonus = 5 if (cr and cr >= 1.5) else (-10 if (cr and cr < 1.0) else 0)
        bs_score = _clamp(de_score + bonus)
        scores.append(bs_score); weights.append(0.20)
        metrics["debt_to_equity"] = round(de, 2)
        if de < 0.5:
            pros.append(f"Debt/Equity of {de:.2f} is comfortably below Buffett's 0.5 ceiling.")
        else:
            cons.append(f"Debt/Equity of {de:.2f} exceeds Buffett's usual 0.5 comfort zone.")
    else:
        scores.append(50.0); weights.append(0.20)
        cons.append("Debt/equity data unavailable.")

    # Earnings consistency + ROE
    eps = [v for v in d.eps_series if v is not None]
    roe = [v for v in d.roe_series if v is not None]
    cons_score = 50.0
    if len(eps) >= 2:
        growth_periods = sum(1 for a, b in zip(eps, eps[1:]) if b > a)
        total = len(eps) - 1
        no_losses = all(v > 0 for v in eps)
        cons_score = _clamp((growth_periods / total) * 70 + (20 if no_losses else -20))
        if no_losses and growth_periods == total:
            pros.append("Earnings grew in every available period with no loss years.")
        elif not no_losses:
            cons.append("At least one loss-making year in the available window.")
    if roe:
        avg_roe = statistics.mean(roe)
        min_roe = min(roe)
        metrics["avg_roe"] = round(avg_roe, 3)
        bonus = 20 if avg_roe >= 0.20 else (10 if avg_roe >= 0.15 else 0)
        if min_roe < 0.15:
            bonus -= 10
        cons_score = _clamp(cons_score * 0.6 + _clamp(50 + bonus) * 0.4)
        if avg_roe >= 0.20:
            pros.append(f"Average ROE of {avg_roe:.0%} clears Buffett's 20% bar for elite businesses.")
        elif avg_roe < 0.15:
            cons.append(f"Average ROE of {avg_roe:.0%} falls short of Buffett's 15% minimum.")
    scores.append(cons_score); weights.append(0.20)

    # Management / capital allocation
    shares = [v for v in d.shares_series if v is not None]
    if len(shares) >= 2:
        change_pct = (shares[-1] - shares[0]) / shares[0]
        mgmt_score = _clamp(65 - change_pct * 450)
        scores.append(mgmt_score); weights.append(0.15)
        metrics["share_count_change"] = round(change_pct, 3)
        if change_pct < -0.01:
            pros.append(f"Share count shrank {abs(change_pct):.1%} — management is buying back stock, not diluting.")
        elif change_pct > 0.02:
            cons.append(f"Share count grew {change_pct:.1%} — dilution works against per-share owner value.")
    else:
        scores.append(50.0); weights.append(0.15)

    # Simplicity proxy
    if d.rnd_to_revenue is not None:
        simp_score = _clamp(90 - (d.rnd_to_revenue / 0.20) * 70)
        scores.append(simp_score); weights.append(0.10)
        if d.rnd_to_revenue < 0.03:
            pros.append("Low R&D intensity — a simpler, more predictable business model to underwrite.")
        elif d.rnd_to_revenue > 0.15:
            cons.append(f"High R&D intensity ({d.rnd_to_revenue:.0%} of revenue) — fast-moving, harder to "
                        f"forecast 10-20 years out, arguably outside a conservative circle of competence.")
    else:
        scores.append(60.0); weights.append(0.10)

    # Margin of safety
    iv = d.intrinsic_value_per_share(discount_rate, growth_rate)
    if iv is not None and d.price:
        if iv <= 0:
            scores.append(0.0); weights.append(0.15)
            cons.append("Owner earnings are too weak/negative to support a going-concern valuation.")
        else:
            mos = (iv - d.price) / iv
            val_score = _clamp(50 + mos * 100)
            scores.append(val_score); weights.append(0.15)
            metrics["intrinsic_value_per_share"] = round(iv, 2)
            metrics["margin_of_safety_pct"] = round(mos, 3)
            if mos >= 0.25:
                pros.append(f"Trading ~{mos:.0%} below estimated intrinsic value — a real margin of safety.")
            elif mos <= -0.15:
                cons.append(f"Trading ~{abs(mos):.0%} above estimated intrinsic value — little to no margin of safety.")
    else:
        scores.append(50.0); weights.append(0.15)
        cons.append("Insufficient cash-flow data to estimate intrinsic value / margin of safety.")

    total_w = sum(weights)
    composite = sum(s * w for s, w in zip(scores, weights)) / total_w if total_w else 50.0
    return StrategyResult("Buffett & Munger (Quality Compounding)", round(composite, 1),
                           _verdict_from_score(composite), pros, cons, metrics)


# --------------------------------------------------------------------------
# Benjamin Graham — deep value
# --------------------------------------------------------------------------

def graham_score(d: StockData) -> StrategyResult:
    pros, cons, metrics = [], [], {}
    scores, weights = [], []

    # Graham Number / P/E / P/B
    gn = d.graham_number
    if gn is not None and d.price:
        discount = (gn - d.price) / gn
        score = _clamp(50 + discount * 100)
        scores.append(score); weights.append(0.30)
        metrics["graham_number"] = round(gn, 2)
        metrics["graham_discount_pct"] = round(discount, 3)
        if d.price < gn:
            pros.append(f"Price (${d.price:,.2f}) is below the Graham Number (${gn:,.2f}) — "
                        f"attractively priced by Graham's classic test.")
        else:
            cons.append(f"Price (${d.price:,.2f}) exceeds the Graham Number (${gn:,.2f}) — "
                        f"fails Graham's defensive-investor price test.")
    else:
        scores.append(50.0); weights.append(0.30)
        cons.append("Not enough data (EPS/book value) to compute a Graham Number.")

    if d.pe_ratio is not None and d.pb_ratio is not None:
        combo = d.pe_ratio * d.pb_ratio
        combo_score = _clamp(100 - (combo / 22.5) * 60)
        scores.append(combo_score); weights.append(0.15)
        metrics["pe_x_pb"] = round(combo, 1)
        if combo <= 22.5:
            pros.append(f"P/E × P/B = {combo:.1f}, at or under Graham's 22.5 ceiling.")
        else:
            cons.append(f"P/E × P/B = {combo:.1f}, above Graham's 22.5 ceiling — pricey on a combined basis.")
    elif d.pe_ratio is not None:
        pe_score = _clamp(100 - (d.pe_ratio / 15) * 60)
        scores.append(pe_score); weights.append(0.15)
        metrics["pe_ratio"] = round(d.pe_ratio, 1)
        if d.pe_ratio <= 15:
            pros.append(f"P/E of {d.pe_ratio:.1f} is at or under Graham's max of 15.")
        else:
            cons.append(f"P/E of {d.pe_ratio:.1f} exceeds Graham's max of 15.")

    # Current ratio (liquidity)
    cr = d.current_ratio
    if cr is not None:
        cr_score = _clamp((cr / 2.0) * 100)
        scores.append(cr_score); weights.append(0.15)
        metrics["current_ratio"] = round(cr, 2)
        if cr >= 2.0:
            pros.append(f"Current ratio of {cr:.2f} clears Graham's 2.0 liquidity bar.")
        else:
            cons.append(f"Current ratio of {cr:.2f} is below Graham's 2.0 liquidity bar.")
    else:
        scores.append(50.0); weights.append(0.15)
        cons.append("Current ratio unavailable — can't verify Graham's liquidity requirement.")

    # Long-term debt vs working capital
    wc = d.working_capital
    if d.long_term_debt is not None and wc is not None:
        debt_ok = d.long_term_debt <= wc if wc > 0 else False
        scores.append(85.0 if debt_ok else 20.0); weights.append(0.15)
        metrics["long_term_debt_vs_working_capital_ok"] = debt_ok
        if debt_ok:
            pros.append("Long-term debt is fully covered by net working capital — Graham's conservative debt test.")
        else:
            cons.append("Long-term debt exceeds net working capital — fails Graham's conservative debt test.")
    else:
        scores.append(50.0); weights.append(0.15)

    # Earnings stability (positive earnings across available window)
    eps = [v for v in d.eps_series if v is not None]
    if eps:
        no_losses = all(v > 0 for v in eps)
        scores.append(80.0 if no_losses else 15.0); weights.append(0.15)
        metrics["years_checked_for_losses"] = len(eps)
        if no_losses:
            pros.append(f"No loss-making years across the {len(eps)} most recent periods available.")
        else:
            cons.append("At least one loss-making year in the available window — "
                        "Graham requires positive earnings every year (traditionally over 10 years).")
    else:
        scores.append(50.0); weights.append(0.15)

    # Dividend record (best-effort; free data can't verify Graham's true 20-year requirement)
    if d.dividend_yield is not None and d.dividend_yield > 0:
        scores.append(70.0); weights.append(0.10)
        pros.append(f"Currently pays a dividend (yield ~{d.dividend_yield:.1%}) — "
                    f"though a true Graham screen wants 20 uninterrupted years, which free data can't confirm.")
    else:
        scores.append(35.0); weights.append(0.10)
        cons.append("No current dividend — fails Graham's income requirement for the defensive investor.")

    total_w = sum(weights)
    composite = sum(s * w for s, w in zip(scores, weights)) / total_w if total_w else 50.0
    return StrategyResult("Benjamin Graham (Deep Value)", round(composite, 1),
                           _verdict_from_score(composite), pros, cons, metrics)


# --------------------------------------------------------------------------
# Peter Lynch — growth at a reasonable price (GARP)
# --------------------------------------------------------------------------

_CYCLICAL_SECTORS = {"energy", "industrials", "basic materials", "materials",
                     "consumer cyclical", "financial services", "financials"}


def _lynch_category(growth: Optional[float], sector: Optional[str]) -> str:
    sector_l = (sector or "").lower()
    if growth is None:
        return "Unclassified (insufficient growth data)"
    if growth < 0:
        return "Turnaround (negative recent earnings growth)"
    if sector_l in _CYCLICAL_SECTORS and 0 <= growth < 0.20:
        return "Cyclical"
    if growth >= 0.25:
        return "Fast Grower"
    if growth >= 0.10:
        return "Stalwart"
    if growth >= 0.0:
        return "Slow Grower"
    return "Unclassified"


def lynch_score(d: StockData) -> StrategyResult:
    pros, cons, metrics = [], [], {}
    scores, weights = [], []

    growth = d.earnings_growth_estimate
    category = _lynch_category(growth, d.sector)
    metrics["lynch_category"] = category
    if growth is not None:
        metrics["earnings_growth_estimate"] = round(growth, 3)

    # PEG ratio — Lynch's central metric
    peg = d.peg_ratio
    if peg is not None and peg > 0:
        peg_score = _clamp(100 - (peg - 0.5) / 1.5 * 100) if peg >= 0.5 else 100.0
        scores.append(peg_score); weights.append(0.35)
        metrics["peg_ratio"] = round(peg, 2)
        if peg < 1.0:
            pros.append(f"PEG ratio of {peg:.2f} is under 1.0 — Lynch's rule of thumb for a reasonably priced grower.")
        else:
            cons.append(f"PEG ratio of {peg:.2f} is at/above 1.0 — pricey relative to its growth rate by Lynch's rule.")
    else:
        scores.append(50.0); weights.append(0.35)
        cons.append("PEG ratio unavailable (need both a P/E and a growth estimate).")

    # Growth category context
    if "Fast Grower" in category:
        scores.append(85.0); weights.append(0.15)
        pros.append("Classified as a Fast Grower (>25% earnings growth) — Lynch's favorite hunting ground, "
                    "though these also carry the most execution/valuation risk.")
    elif "Stalwart" in category:
        scores.append(65.0); weights.append(0.15)
        pros.append("Classified as a Stalwart (10-25% growth) — steady compounding, good downside protection.")
    elif "Slow Grower" in category:
        scores.append(35.0); weights.append(0.15)
        cons.append("Classified as a Slow Grower (<10% growth) — Lynch generally passed on these unless "
                    "the dividend/value case was compelling.")
    elif "Turnaround" in category:
        scores.append(40.0); weights.append(0.15)
        cons.append("Negative recent earnings growth — a Lynch 'turnaround' candidate: high risk, "
                    "requires real evidence the business is being fixed.")
    elif "Cyclical" in category:
        scores.append(50.0); weights.append(0.15)
        cons.append("Sits in a cyclical sector — Lynch warns timing matters enormously here; "
                    "cheap-looking multiples near a cycle peak can be a trap.")
    else:
        scores.append(50.0); weights.append(0.15)

    # Debt load
    de = d.debt_to_equity
    if de is not None:
        de_score = _clamp(100 - (de / 1.0) * 60)
        scores.append(de_score); weights.append(0.15)
        if de < 0.5:
            pros.append(f"Manageable Debt/Equity of {de:.2f} — Lynch was wary of highly leveraged growth stories.")
        elif de > 1.0:
            cons.append(f"Debt/Equity of {de:.2f} is elevated — leverage adds fragility to a growth thesis.")
    else:
        scores.append(50.0); weights.append(0.15)

    # Institutional ownership (Lynch's contrarian angle: low institutional ownership = more room to run)
    inst = d.institutional_ownership_pct
    if inst is not None:
        inst_score = _clamp(100 - inst * 100)
        scores.append(inst_score); weights.append(0.15)
        metrics["institutional_ownership_pct"] = round(inst, 3)
        if inst < 0.5:
            pros.append(f"Institutional ownership is relatively low ({inst:.0%}) — "
                        f"by Lynch's logic, more room for the stock to be 'discovered'.")
        elif inst > 0.85:
            cons.append(f"Institutional ownership is very high ({inst:.0%}) — the easy discovery phase is "
                        f"likely already behind it.")
    else:
        scores.append(50.0); weights.append(0.15)

    # Buyback/dilution trend, reused as a secondary signal
    shares = [v for v in d.shares_series if v is not None]
    if len(shares) >= 2:
        change_pct = (shares[-1] - shares[0]) / shares[0]
        score = _clamp(60 - change_pct * 400)
        scores.append(score); weights.append(0.05)
        if change_pct < -0.01:
            pros.append("Company is buying back shares alongside its growth story.")
    else:
        scores.append(50.0); weights.append(0.05)

    total_w = sum(weights)
    composite = sum(s * w for s, w in zip(scores, weights)) / total_w if total_w else 50.0
    return StrategyResult(f"Peter Lynch (GARP — {category})", round(composite, 1),
                           _verdict_from_score(composite), pros, cons, metrics)


# --------------------------------------------------------------------------
# Combine all three lenses into one overall read
# --------------------------------------------------------------------------

def overall_verdict(results: list) -> dict:
    avg = sum(r.score for r in results) / len(results) if results else 0.0
    strong = sum(1 for r in results if r.score >= 65)
    weak = sum(1 for r in results if r.score < 40)

    if avg >= 70 and strong >= 2:
        label = "BUY candidate"
        rationale = "Multiple independent value/quality/growth lenses agree this deserves real research time."
    elif avg >= 55:
        label = "WORTH RESEARCHING"
        rationale = "Some lenses like it, others don't — a mixed picture that calls for deeper individual due diligence."
    elif weak >= 2:
        label = "LIKELY PASS"
        rationale = "Most lenses see meaningful gaps versus their criteria on the available data."
    else:
        label = "HOLD / NEUTRAL"
        rationale = "No strong signal in either direction from the metrics available."

    all_pros = [(r.strategy, p) for r in results for p in r.pros]
    all_cons = [(r.strategy, c) for r in results for c in r.cons]

    return {
        "average_score": round(avg, 1),
        "label": label,
        "rationale": rationale,
        "pros": all_pros,
        "cons": all_cons,
    }
