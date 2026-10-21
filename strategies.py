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
    # v2: use the bear/base/bull DCF (company's own growth rate) instead of a flat 20x owner earnings,
    # which made almost every quality business look 100%+ overpriced.
    iv = valuation(d)["base"]
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
        cons.append("No positive free cash flow yet, so there's no intrinsic value / margin of safety to estimate.")

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


# ══════════════════════════════════════════════════════════════════════════
# v2 (Oct 2026): valuation range, two more company lenses, two IPO lenses,
# IPO checklist and desk-level verdicts.
# ══════════════════════════════════════════════════════════════════════════

def _band(x, steps):
    """steps: list of (threshold, score) checked top-down with x >= threshold; last item is the floor score."""
    for th, sc in steps[:-1]:
        if x >= th:
            return sc
    return steps[-1][1]


def growth_estimate(d: StockData) -> Optional[float]:
    """Middle of the growth signals we have, clamped to a sane long-run range."""
    cands = [g for g in (d.earnings_growth_estimate, d.revenue_cagr, d.revenue_growth_yoy) if g is not None]
    if not cands:
        return None
    return max(-0.05, min(0.25, statistics.median(cands)))


def _dcf_per_share(base: float, g: float, r: float = 0.09, tg: float = 0.03, years: int = 10) -> float:
    """Two-stage DCF: growth g for 5 years, fading linearly to tg by year 10, then a terminal value."""
    pv, cf = 0.0, base
    for y in range(1, years + 1):
        gy = g if y <= 5 else g + (tg - g) * (y - 5) / (years - 5)
        cf *= 1 + gy
        pv += cf / (1 + r) ** y
    terminal = cf * (1 + tg) / (r - tg)
    return pv + terminal / (1 + r) ** years


def valuation(d: StockData) -> dict:
    """Bear / base / bull value per share from free cash flow (or owner earnings)."""
    out = {"bear": None, "base": None, "bull": None, "growth": None, "method": None, "note": None,
           "margin_of_safety": None}
    shares = d.shares_outstanding
    if not shares:
        out["note"] = "Share count unavailable."
        return out
    if d.free_cash_flow is not None and d.free_cash_flow > 0:
        base_cf, out["method"] = d.free_cash_flow / shares, "free cash flow"
    elif (d.owner_earnings() or 0) > 0:
        base_cf, out["method"] = d.owner_earnings() / shares, "owner earnings"
    else:
        out["note"] = "Not meaningful: the company doesn't generate positive free cash flow yet."
        return out
    g = growth_estimate(d)
    g = 0.04 if g is None else g
    out["growth"] = round(g, 4)
    bear_g = g * 0.5 if g > 0 else g - 0.03
    bull_g = min(g * 1.5 + 0.02, 0.35)
    out["bear"] = round(_dcf_per_share(base_cf, bear_g), 2)
    out["base"] = round(_dcf_per_share(base_cf, g), 2)
    out["bull"] = round(_dcf_per_share(base_cf, bull_g), 2)
    if d.price and out["base"] > 0:
        out["margin_of_safety"] = round((out["base"] - d.price) / out["base"], 4)
    return out


# ── Philip Fisher — growth quality (Common Stocks and Uncommon Profits, 1958) ──
def fisher_score(d: StockData) -> StrategyResult:
    pros, cons, parts = [], [], []
    cagr = d.revenue_cagr
    if cagr is not None:
        parts.append((_band(cagr, [(0.15, 90), (0.10, 75), (0.05, 55), (0.0, 40), (None, 20)]), 0.25))
        (pros if cagr >= 0.10 else cons).append(
            f"Revenue grew {cagr:.0%} a year over the available history. Fisher's point #1 wants products "
            f"with room for sales to keep growing for years." if cagr >= 0.10 else
            f"Revenue grew only {cagr:.0%} a year, weak on Fisher's point #1 (sales growth potential).")
    else:
        parts.append((50, 0.25))
    if d.rnd_to_revenue is not None:
        r = d.rnd_to_revenue
        parts.append((75 if 0.03 <= r <= 0.15 else 65 if r > 0.15 else 45, 0.10))
        if r >= 0.03:
            pros.append(f"Spends {r:.0%} of revenue on R&D. Fisher (#2, #3) wants management investing in future products.")
    else:
        parts.append((50, 0.10))
    om = d.operating_margin_ttm
    if om is not None:
        parts.append((_band(om, [(0.20, 85), (0.10, 65), (0.0, 45), (None, 20)]), 0.20))
        (pros if om >= 0.15 else cons).append(
            f"Operating margin {om:.0%}. Fisher #5: worthwhile profit margins." if om >= 0.15 else
            f"Operating margin {om:.0%}, below what Fisher called a worthwhile margin (#5).")
    else:
        parts.append((50, 0.20))
    oms = [v for v in d.operating_margin_series if v is not None]
    if len(oms) >= 2:
        delta = oms[-1] - oms[0]
        parts.append((85 if delta >= 0.02 else 60 if delta > -0.02 else 30, 0.15))
        if delta >= 0.02:
            pros.append(f"Margins widened by {delta*100:.1f} points. Fisher #6: improving margins.")
        elif delta <= -0.02:
            cons.append(f"Margins shrank by {abs(delta)*100:.1f} points. Fisher #6 looks for improvement.")
    else:
        parts.append((55, 0.15))
    sh = [v for v in d.shares_series if v]
    if len(sh) >= 2:
        ch = (sh[-1] - sh[0]) / sh[0]
        parts.append((80 if ch <= 0 else 60 if ch <= 0.03 else 30, 0.15))
        if ch > 0.03:
            cons.append(f"Share count up {ch:.0%}. Fisher #13 warns against growth funded by diluting owners.")
    else:
        parts.append((50, 0.15))
    ins = d.insider_ownership_pct
    if ins is not None:
        parts.append((85 if ins >= 0.10 else 60 if ins >= 0.02 else 45, 0.15))
        if ins >= 0.10:
            pros.append(f"Insiders own {ins:.0%}. Management has real skin in the game (Fisher #14–15).")
    else:
        parts.append((50, 0.15))
    sc = sum(s * w for s, w in parts) / sum(w for _, w in parts)
    return StrategyResult("Philip Fisher (Growth Quality)", round(sc, 1), _verdict_from_score(sc), pros, cons)


# ── Joel Greenblatt — Magic Formula (The Little Book That Beats the Market, 2005) ──
_GB_EXCLUDED = {"financial services", "financials", "utilities"}


def greenblatt_score(d: StockData) -> StrategyResult:
    pros, cons, metrics = [], [], {}
    if (d.sector or "").lower() in _GB_EXCLUDED:
        return StrategyResult("Joel Greenblatt (Magic Formula)", 50.0, "Not applicable",
                              [], [f"Greenblatt excludes {d.sector} companies; their balance sheets don't fit the formula."])
    ic, ev, ebit = d.invested_capital, d.enterprise_value, d.ebit
    parts = []
    if ebit is not None and ic and ic > 0:
        roic = ebit / ic
        metrics["roic"] = round(roic, 4)
        parts.append(_band(roic, [(0.25, 90), (0.15, 70), (0.08, 50), (None, 25)]))
        (pros if roic >= 0.15 else cons).append(
            f"Return on capital ~{roic:.0%}: a good business by Greenblatt's first test." if roic >= 0.15 else
            f"Return on capital ~{roic:.0%}: below what the Magic Formula looks for.")
    else:
        parts.append(50)
    if ebit is not None and ev and ev > 0:
        ey = ebit / ev
        metrics["earnings_yield"] = round(ey, 4)
        parts.append(_band(ey, [(0.10, 90), (0.07, 70), (0.04, 45), (None, 20)]))
        (pros if ey >= 0.07 else cons).append(
            f"Earnings yield (EBIT ÷ EV) {ey:.1%}: a cheap price by Greenblatt's second test." if ey >= 0.07 else
            f"Earnings yield (EBIT ÷ EV) {ey:.1%}: not cheap by the Magic Formula.")
    else:
        parts.append(50)
    sc = sum(parts) / len(parts)
    return StrategyResult("Joel Greenblatt (Magic Formula)", round(sc, 1), _verdict_from_score(sc), pros, cons, metrics)


# ── Jay Ritter — what decades of IPO research says predicts long-run returns ──
def ritter_score(d: StockData) -> StrategyResult:
    pros, cons, parts = [], [], []
    rev = d.revenue_ttm
    if rev:
        parts.append((_band(rev, [(1e9, 80), (2.5e8, 65), (5e7, 45), (None, 25)]), 0.25))
        if rev < 2.5e8:
            cons.append(f"Small company (${rev/1e6:,.0f}M revenue). Ritter's data shows the smallest IPOs drive "
                        f"the long-run underperformance.")
        else:
            pros.append(f"Revenue of ${rev/1e9:,.2f}B. Ritter finds larger IPOs roughly match the market over time.")
    else:
        parts.append((40, 0.25))
    ps = d.price_to_sales
    if ps:
        parts.append((_band(-ps, [(-6, 85), (-12, 60), (-24, 35), (None, 15)]), 0.30))
        if ps <= 6:
            pros.append(f"Price/sales {ps:.1f}, near the historical tech-IPO norm of ~6.")
        else:
            cons.append(f"Price/sales {ps:.1f}. Ritter: at high multiples 'the upside potential is more limited and "
                        f"the downside potential is greater' (historical tech-IPO norm ~6).")
    else:
        parts.append((50, 0.30))
    pm = d.profit_margin_ttm
    if pm is not None:
        parts.append((70 if pm > 0 else 45, 0.10))
        (pros if pm > 0 else cons).append("Already profitable." if pm > 0 else
            "Not yet profitable. For tech IPOs Ritter sees only a weak link to later returns, but it raises the stakes on growth.")
    else:
        parts.append((50, 0.10))
    m = d.months_listed
    if m is not None:
        parts.append((30 if m < 6 else 55 if m < 12 else 75, 0.15))
        if m < 6:
            cons.append(f"Listed {m:.0f} months ago. Studies find prices tend to drop when the ~180-day lock-up ends, "
                        f"especially for VC-backed IPOs.")
    else:
        parts.append((50, 0.15))
    rg = d.revenue_growth_yoy
    if rg is not None:
        parts.append((_band(rg, [(0.20, 80), (0.0, 60), (None, 25)]), 0.20))
        if rg < 0:
            cons.append(f"Revenue shrinking {rg:.0%} year over year. Weak post-IPO operating performance is one of "
                        f"the clearest predictors of poor IPO returns.")
        elif rg >= 0.20:
            pros.append(f"Revenue up {rg:.0%} year over year since listing: operating performance is holding up.")
    else:
        parts.append((50, 0.20))
    sc = sum(s * w for s, w in parts) / sum(w for _, w in parts)
    return StrategyResult("Jay Ritter (IPO Research)", round(sc, 1), _verdict_from_score(sc), pros, cons)


# ── Bill Gurley — revenue quality ("All Revenue Is Not Created Equal", 2011) ──
def gurley_score(d: StockData) -> StrategyResult:
    pros, cons, parts = [], [], []
    gm = d.gross_margin_ttm
    if gm is not None:
        parts.append((_band(gm, [(0.70, 90), (0.50, 70), (0.30, 45), (None, 20)]), 0.25))
        (pros if gm >= 0.50 else cons).append(
            f"Gross margin {gm:.0%}: high-quality revenue (Gurley factor #5)." if gm >= 0.50 else
            f"Gross margin {gm:.0%}: Gurley notes low-margin businesses deserve lower multiples (#5).")
    else:
        parts.append((50, 0.25))
    rg = d.revenue_growth_yoy
    if rg is not None:
        parts.append((_band(rg, [(0.40, 90), (0.25, 75), (0.10, 55), (None, 30)]), 0.20))
        if rg >= 0.25:
            pros.append(f"Revenue growing {rg:.0%} a year (#10). Gurley adds that growth only counts if it ends in cash flow.")
    else:
        parts.append((50, 0.20))
    oms = [v for v in d.operating_margin_series if v is not None]
    if len(oms) >= 2:
        delta = oms[-1] - oms[0]
        parts.append((90 if delta >= 0.05 else 70 if delta >= 0.01 else 55 if delta > -0.01 else 25, 0.20))
        (pros if delta >= 0.01 else cons).append(
            f"Margins up {delta*100:.1f} points as it grows: it scales efficiently (#6 marginal profitability)." if delta >= 0.01 else
            f"Margins not improving with scale ({delta*100:+.1f} points). Gurley's #6 warning sign.")
    else:
        parts.append((50, 0.20))
    q = [v for v in d.quarterly_revenue if v]
    if len(q) >= 3:
        ups = sum(1 for a, b in zip(q, q[1:]) if b > a) / (len(q) - 1)
        parts.append((85 if ups >= 0.99 else 65 if ups >= 0.66 else 35, 0.15))
        if ups >= 0.99:
            pros.append("Revenue rose every recent quarter: visible, predictable revenue (#3).")
        elif ups < 0.66:
            cons.append("Quarterly revenue is bumpy: low visibility (#3).")
    else:
        parts.append((50, 0.15))
    if rg is not None and d.fcf_margin is not None:
        r40 = (rg + d.fcf_margin) * 100
        parts.append((85 if r40 >= 40 else 60 if r40 >= 25 else 30, 0.20))
        (pros if r40 >= 40 else cons).append(
            f"Rule of 40 score {r40:.0f} (growth % + free-cash-flow margin %): healthy balance of growth and cash." if r40 >= 40 else
            f"Rule of 40 score {r40:.0f}: growth plus cash margin falls short of 40.")
    else:
        parts.append((50, 0.20))
    cons.append("Gurley's moat, network-effect, lock-in, customer-concentration, partner-dependency and "
                "organic-demand factors need the prospectus: see the checklist.")
    sc = sum(s * w for s, w in parts) / sum(w for _, w in parts)
    return StrategyResult("Bill Gurley (Revenue Quality)", round(sc, 1), _verdict_from_score(sc), pros, cons)


def ipo_checklist(d: StockData, prospectus: Optional[dict] = None) -> list:
    """The things to check before buying a recent IPO. status: pass | warn | fail | info."""
    from datetime import date, timedelta
    items = []
    m = d.months_listed
    if d.first_trade_date and m is not None:
        lock = date.fromisoformat(d.first_trade_date[:10]) + timedelta(days=180)
        if lock > date.today():
            items.append({"label": "Lock-up expiry", "status": "fail",
                          "detail": f"Estimated {lock:%b %d, %Y} (~180 days after listing). Insiders can sell after this; prices often dip."})
        else:
            items.append({"label": "Lock-up expiry", "status": "pass", "detail": f"Passed around {lock:%b %Y} (estimated)."})
        items.append({"label": "Track record as a public company", "status": "pass" if m >= 9 else "warn",
                      "detail": f"{m:.0f} months listed (~{int(m // 3)} quarterly reports). Graham warned against buying new issues; a few public quarters give real evidence."})
    else:
        items.append({"label": "Listing date", "status": "info", "detail": "Not available from free data."})
    if d.first_day_open and d.price:
        vs = d.price / d.first_day_open - 1
        items.append({"label": "Price vs first-day open", "status": "warn" if vs > 1.0 else "info",
                      "detail": f"{vs:+.0%} vs ${d.first_day_open:,.2f} on day one" +
                                (". It has more than doubled, so check that the hype matches the numbers." if vs > 1 else ".")})
    if d.first_day_open and d.first_day_close:
        pop = d.first_day_close / d.first_day_open - 1
        items.append({"label": "First-day move", "status": "info",
                      "detail": f"{pop:+.0%} open-to-close. Research finds the first-day move doesn't predict long-run returns."})
    if d.profit_margin_ttm is not None:
        items.append({"label": "Profitable", "status": "pass" if d.profit_margin_ttm > 0 else "warn",
                      "detail": f"Net margin {d.profit_margin_ttm:.0%}."})
    run = d.cash_runway_years
    if d.free_cash_flow is not None:
        if d.free_cash_flow >= 0:
            items.append({"label": "Cash runway", "status": "pass", "detail": "Generates its own cash; no funding risk."})
        elif run is not None:
            items.append({"label": "Cash runway", "status": "fail" if run < 2 else "warn",
                          "detail": f"About {run:.1f} years of cash at the current burn rate."})
    if d.insider_ownership_pct is not None:
        items.append({"label": "Insider ownership", "status": "pass" if d.insider_ownership_pct >= 0.10 else "warn",
                      "detail": f"{d.insider_ownership_pct:.0%} owned by insiders. Check the prospectus for dual-class voting."})
    if d.short_pct_float is not None:
        items.append({"label": "Short interest", "status": "warn" if d.short_pct_float >= 0.10 else "pass",
                      "detail": f"{d.short_pct_float:.0%} of the float is sold short."})
    if d.price_to_sales:
        items.append({"label": "Valuation (price/sales)", "status": "pass" if d.price_to_sales <= 6 else "warn" if d.price_to_sales <= 15 else "fail",
                      "detail": f"{d.price_to_sales:.1f}x sales (historical tech-IPO norm ~6x)."})
    if prospectus and prospectus.get("url"):
        items.append({"label": "Read the prospectus", "status": "info",
                      "detail": f"{prospectus['form']} filed {prospectus['date']}: business, risk factors, use of proceeds, share classes, lock-up terms.",
                      "link": prospectus["url"]})
    elif prospectus and prospectus.get("company_url"):
        items.append({"label": "Read the prospectus", "status": "info",
                      "detail": "Find the S-1 / 424B4 in the company's SEC filings.", "link": prospectus["company_url"]})
    return items


def company_verdict(results: list) -> dict:
    """Company desk: average of all five lenses."""
    scored = [r for r in results if r.verdict != "Not applicable"]
    avg = sum(r.score for r in scored) / len(scored) if scored else 0.0
    strong = sum(1 for r in scored if r.score >= 65)
    weak = sum(1 for r in scored if r.score < 40)
    if avg >= 65 and strong >= 3:
        label, why = "BUY candidate", "Most of the great investors' tests agree. This deserves serious research time."
    elif avg >= 55:
        label, why = "WORTH RESEARCHING", "Several lenses like it, others don't. Dig into the cons before buying."
    elif weak >= 3:
        label, why = "LIKELY PASS", "Most lenses see meaningful gaps versus their criteria."
    else:
        label, why = "HOLD / NEUTRAL", "No strong signal either way on the available data."
    return {"label": label, "rationale": why, "average_score": round(avg, 1)}


def ipo_verdict(results: list, d: StockData) -> dict:
    """IPO desk: Ritter + Gurley average, with hard rules for lock-up and cash risk."""
    avg = sum(r.score for r in results) / len(results) if results else 0.0
    m, run = d.months_listed, d.cash_runway_years
    if run is not None and run < 1.5:
        label, why = "PASS (cash risk)", f"Only ~{run:.1f} years of cash left at today's burn. Likely to raise money and dilute owners."
    elif m is not None and m < 6:
        label, why = "WAIT (lock-up)", "Too new: let the lock-up expire and see two quarterly reports before deciding."
    elif avg >= 65:
        label, why = "BUY candidate (start small)", "Strong on IPO research and revenue quality. If you buy, start small and add as it proves itself."
    elif avg >= 52:
        label, why = "WATCH", "Promising, but not yet convincing. Watch the next two quarters."
    elif avg >= 40:
        label, why = "WAIT for proof", "Too many open questions on valuation or business quality."
    else:
        label, why = "PASS", "Weak on both IPO research and revenue quality."
    return {"label": label, "rationale": why, "average_score": round(avg, 1)}
