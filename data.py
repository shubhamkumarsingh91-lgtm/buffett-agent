"""
data.py — fetches and normalizes the fundamentals every strategy lens needs.

Data source: yfinance (free, uses Yahoo Finance). This module isolates all
network/data-shape concerns so strategies.py can work with a clean, typed
StockData object regardless of which fields Yahoo happens to expose for a
given ticker. Every field is Optional — strategies must handle missing data
gracefully (they do; see strategies.py's "neutral score + note" pattern).

IMPORTANT: this requires a normal internet connection. It will NOT work in a
network-sandboxed environment — run it on your own machine.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StockData:
    ticker: str
    name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    price: Optional[float] = None
    shares_outstanding: Optional[float] = None

    # Valuation
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    pb_ratio: Optional[float] = None
    book_value_per_share: Optional[float] = None
    eps_ttm: Optional[float] = None
    earnings_growth_estimate: Optional[float] = None   # decimal, e.g. 0.12 = 12%
    peg_ratio: Optional[float] = None

    # Dividends
    dividend_yield: Optional[float] = None
    dividend_rate: Optional[float] = None
    payout_ratio: Optional[float] = None

    # Ownership (Lynch's contrarian signal: lower institutional % = more room to run)
    institutional_ownership_pct: Optional[float] = None
    insider_ownership_pct: Optional[float] = None

    # Multi-year series, most recent last
    roe_series: list = field(default_factory=list)
    gross_margin_series: list = field(default_factory=list)
    operating_margin_series: list = field(default_factory=list)
    eps_series: list = field(default_factory=list)          # proxy: net income trend
    shares_series: list = field(default_factory=list)
    revenue_series: list = field(default_factory=list)

    # Balance sheet (latest period)
    total_debt: Optional[float] = None
    total_equity: Optional[float] = None
    current_assets: Optional[float] = None
    current_liabilities: Optional[float] = None
    long_term_debt: Optional[float] = None

    # Owner earnings components (latest period)
    net_income: Optional[float] = None
    depreciation_amortization: Optional[float] = None
    capital_expenditures: Optional[float] = None
    change_in_working_capital: Optional[float] = None

    rnd_to_revenue: Optional[float] = None

    news: list = field(default_factory=list)   # [{title, publisher, link}]
    data_notes: list = field(default_factory=list)

    # ---- derived helpers used by multiple strategies ----
    @property
    def working_capital(self) -> Optional[float]:
        if self.current_assets is None or self.current_liabilities is None:
            return None
        return self.current_assets - self.current_liabilities

    @property
    def current_ratio(self) -> Optional[float]:
        if not self.current_liabilities:
            return None
        if self.current_assets is None:
            return None
        return self.current_assets / self.current_liabilities

    @property
    def debt_to_equity(self) -> Optional[float]:
        if self.total_debt is None or not self.total_equity:
            return None
        return self.total_debt / self.total_equity

    @property
    def graham_number(self) -> Optional[float]:
        if self.eps_ttm is None or self.book_value_per_share is None:
            return None
        if self.eps_ttm <= 0 or self.book_value_per_share <= 0:
            return None
        return (22.5 * self.eps_ttm * self.book_value_per_share) ** 0.5

    def owner_earnings(self) -> Optional[float]:
        if None in (self.net_income, self.depreciation_amortization, self.capital_expenditures):
            return None
        wc = self.change_in_working_capital or 0.0
        return self.net_income + self.depreciation_amortization - abs(self.capital_expenditures) - wc

    def intrinsic_value_per_share(self, discount_rate: float = 0.09, growth_rate: float = 0.04) -> Optional[float]:
        oe = self.owner_earnings()
        if oe is None or not self.shares_outstanding:
            return None
        g = growth_rate if growth_rate < discount_rate else discount_rate - 0.01
        return (oe / (discount_rate - g)) / self.shares_outstanding


def _series_from(df, row_names, most_recent_first=True):
    if df is None or df.empty:
        return []
    for name in row_names:
        if name in df.index:
            vals = df.loc[name].dropna().tolist()
            return list(reversed(vals)) if most_recent_first else vals
    return []


def fetch_stock_data(ticker: str) -> StockData:
    try:
        import yfinance as yf
    except ImportError as e:
        raise SystemExit("Missing dependency. Install with:  pip install yfinance") from e

    notes = []
    t = yf.Ticker(ticker)

    try:
        info = t.info or {}
    except Exception as e:
        raise SystemExit(f"Could not fetch data for '{ticker}': {e}")

    try:
        fin = t.financials
        bs = t.balance_sheet
        cf = t.cashflow
    except Exception:
        fin = bs = cf = None
        notes.append("Historical statement data unavailable from Yahoo Finance for this ticker.")

    net_income_series = _series_from(fin, ["Net Income", "NetIncome"])
    revenue_series = _series_from(fin, ["Total Revenue", "TotalRevenue"])
    gross_profit_series = _series_from(fin, ["Gross Profit", "GrossProfit"])
    operating_income_series = _series_from(fin, ["Operating Income", "OperatingIncome"])
    rnd_series = _series_from(fin, ["Research And Development", "ResearchAndDevelopment"])
    shares_series = _series_from(fin, ["Diluted Average Shares", "Basic Average Shares"])

    equity_series = _series_from(bs, ["Common Stock Equity", "Stockholders Equity", "StockholdersEquity"])
    debt_series = _series_from(bs, ["Total Debt", "TotalDebt"])
    lt_debt_series = _series_from(bs, ["Long Term Debt", "LongTermDebt"])

    da_series = _series_from(cf, ["Depreciation And Amortization", "Depreciation Amortization Depletion",
                                   "DepreciationAndAmortization"])
    capex_series = _series_from(cf, ["Capital Expenditure", "CapitalExpenditure"])
    wc_series = _series_from(cf, ["Change In Working Capital", "ChangeInWorkingCapital"])

    gross_margin_series = [g / r for g, r in zip(gross_profit_series, revenue_series) if r] \
        if gross_profit_series and revenue_series else []
    operating_margin_series = [o / r for o, r in zip(operating_income_series, revenue_series) if r] \
        if operating_income_series and revenue_series else []
    roe_series = [ni / eq for ni, eq in zip(net_income_series, equity_series) if eq] \
        if net_income_series and equity_series else []
    eps_series = net_income_series

    rnd_to_revenue = None
    if revenue_series and rnd_series and revenue_series[-1]:
        rnd_to_revenue = rnd_series[-1] / revenue_series[-1]

    if not roe_series and info.get("returnOnEquity") is not None:
        roe_series = [info["returnOnEquity"]]
        notes.append("Only trailing ROE available (no multi-year history).")
    if not gross_margin_series and info.get("grossMargins") is not None:
        gross_margin_series = [info["grossMargins"]]
    if not operating_margin_series and info.get("operatingMargins") is not None:
        operating_margin_series = [info["operatingMargins"]]
    if not (fin is not None and not fin.empty):
        notes.append("Limited multi-year history from free data source vs. the 10-year windows "
                      "the original strategies were designed around.")

    news = []
    try:
        raw_news = t.news or []
        for item in raw_news[:8]:
            c = item.get("content", item)  # yfinance news shape has varied across versions
            title = c.get("title") or item.get("title")
            publisher = (c.get("provider") or {}).get("displayName") if isinstance(c.get("provider"), dict) \
                else item.get("publisher")
            link = (c.get("canonicalUrl") or {}).get("url") if isinstance(c.get("canonicalUrl"), dict) \
                else item.get("link")
            if title:
                news.append({"title": title, "publisher": publisher or "", "link": link or ""})
    except Exception:
        notes.append("News feed unavailable.")

    earnings_growth = info.get("earningsGrowth") or info.get("earningsQuarterlyGrowth")
    peg = info.get("pegRatio") or info.get("trailingPegRatio")
    pe = info.get("trailingPE")
    if peg is None and pe and earnings_growth and earnings_growth > 0:
        peg = pe / (earnings_growth * 100)

    return StockData(
        ticker=ticker.upper(),
        name=info.get("longName") or info.get("shortName"),
        sector=info.get("sector"),
        industry=info.get("industry"),
        price=info.get("currentPrice") or info.get("regularMarketPrice"),
        shares_outstanding=info.get("sharesOutstanding"),
        pe_ratio=pe,
        forward_pe=info.get("forwardPE"),
        pb_ratio=info.get("priceToBook"),
        book_value_per_share=info.get("bookValue"),
        eps_ttm=info.get("trailingEps"),
        earnings_growth_estimate=earnings_growth,
        peg_ratio=peg,
        dividend_yield=info.get("dividendYield"),
        dividend_rate=info.get("dividendRate"),
        payout_ratio=info.get("payoutRatio"),
        institutional_ownership_pct=info.get("heldPercentInstitutions"),
        insider_ownership_pct=info.get("heldPercentInsiders"),
        roe_series=roe_series,
        gross_margin_series=gross_margin_series,
        operating_margin_series=operating_margin_series,
        eps_series=eps_series,
        shares_series=shares_series,
        revenue_series=revenue_series,
        total_debt=debt_series[-1] if debt_series else info.get("totalDebt"),
        total_equity=equity_series[-1] if equity_series else None,
        current_assets=info.get("totalCurrentAssets"),
        current_liabilities=info.get("totalCurrentLiabilities"),
        long_term_debt=lt_debt_series[-1] if lt_debt_series else None,
        net_income=net_income_series[-1] if net_income_series else info.get("netIncomeToCommon"),
        depreciation_amortization=da_series[-1] if da_series else None,
        capital_expenditures=capex_series[-1] if capex_series else None,
        change_in_working_capital=wc_series[-1] if wc_series else None,
        rnd_to_revenue=rnd_to_revenue,
        news=news,
        data_notes=notes,
    )
