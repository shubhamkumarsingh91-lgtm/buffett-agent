# Buffett-Style Investing Agent

A local web page that screens any stock through three famous investors'
public criteria at once — Warren Buffett & Charlie Munger (quality
compounding), Benjamin Graham (deep value), and Peter Lynch (growth at a
reasonable price) — and lets you build a simple portfolio tracker on top of
it.

**This is an educational research tool, not financial advice, and it never
places trades.** It only reads public financial data and tells you, in
plain language, why each strategy would or wouldn't be interested in a
stock. See "Limitations" below before you act on anything it says.

## Why this needs to run on your computer

Live financial data (prices, financial statements) requires a normal
internet connection. This tool was built and tested in a network-sandboxed
environment that could not reach Yahoo Finance directly — so all scoring
logic was verified with synthetic test data instead. It should work
correctly once you run it with your own internet access, but **test it on a
couple of tickers you know well before trusting it.**

## Setup

```bash
cd buffett_agent
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

This opens the app in your browser (usually `http://localhost:8501`).

## What it does

### Analyze a Stock
Type a ticker (e.g. `AAPL`, `KO`, `AXP`) and click Analyze. You'll get:

- Live price, sector, and a headline verdict (**BUY candidate / WORTH
  RESEARCHING / LIKELY PASS / HOLD-NEUTRAL**) combining all three lenses.
- Three side-by-side scorecards (0-100 each) with explicit **pros and cons**
  in plain English:
  - **Buffett & Munger** — economic moat (margin level & stability), balance
    sheet strength (debt/equity), earnings consistency & ROE, share
    buybacks vs. dilution, and a margin-of-safety check against an
    "owner earnings" intrinsic value estimate.
  - **Benjamin Graham** — Graham Number, P/E × P/B vs. Graham's 22.5
    ceiling, current ratio (liquidity), long-term debt vs. working capital,
    earnings stability, and dividend record.
  - **Peter Lynch** — PEG ratio, growth-category classification (Fast
    Grower / Stalwart / Slow Grower / Cyclical / Turnaround), debt load, and
    institutional ownership (Lynch's "still undiscovered" signal).
- Recent news headlines (via Yahoo Finance).
- An "Add to Portfolio" button.

### My Portfolio
Everything you've added: live price, current value, gain/loss vs. your cost
basis, and all three strategy scores per holding, plus portfolio totals.
Data is stored locally in `portfolio_data.json` next to `app.py` — nothing
leaves your machine, there's no account, and no brokerage is ever connected.

## How the code is organized

| File | Purpose |
|---|---|
| `data.py` | Fetches and normalizes fundamentals from `yfinance` into one `StockData` object. All fields are optional — missing data degrades gracefully rather than crashing. |
| `strategies.py` | Three independent scoring functions (`buffett_score`, `graham_score`, `lynch_score`) plus `overall_verdict()` to combine them. Pure functions of `StockData` — no network calls — so they're unit-testable with synthetic data. |
| `portfolio.py` | A tiny local JSON-backed holdings tracker. No brokerage integration. |
| `app.py` | The Streamlit UI tying it all together. |

If you want to plug in better data (e.g., from actual 10-K filings instead
of free Yahoo Finance data, which typically only exposes ~4 years of annual
history vs. the 10-year windows these strategies were originally built
around), construct a `StockData` object directly and pass it to the
`*_score()` functions — they don't care where the numbers came from.

## Limitations — read before you trust a verdict

- **Quantitative proxies only.** None of these scores can judge a moat's
  true durability, a management team's character, or whether a business is
  within *your* circle of competence. That judgment is still yours to make.
- **Free data has gaps.** Yahoo Finance data can be delayed, incomplete, or
  occasionally wrong. Always cross-check anything material against the
  company's actual SEC filings.
- **Graham's dividend and earnings-history checks are approximated.** Free
  data doesn't reliably expose 10-20 years of history, so those checks use
  whatever window is available and say so explicitly in the "Data
  limitations" panel.
- **PEG and growth-category calls depend on a single growth estimate**,
  which can be noisy quarter to quarter.
- **No execution, no automation.** This tool doesn't hold API keys to any
  brokerage and should not be wired up to place trades automatically.
  Every buy/sell decision should go through you, deliberately.
- **Not investment advice.** Treat every score as a prompt for your own
  research, not a final answer.

## Rate limiting

Yahoo Finance (the free data source behind `yfinance`) rate-limits requests
from shared cloud IP ranges more aggressively than from a home connection —
this shows up as "Too Many Requests" errors, most often on Streamlit
Community Cloud, Render, and similar free hosts. `data.py` already retries
automatically with backoff and uses a browser-impersonating session to
reduce the odds of this, and `app.py` caches each ticker's data for 15
minutes so the Portfolio tab doesn't re-trigger it. If it still happens
often on your deployment:

1. Wait a minute or two and try again — it's usually temporary.
2. Avoid analyzing many different tickers back-to-back in a short burst.
3. If it's persistent, swap the data source in `data.py` for a key-based API
   with a generous free tier (e.g. Financial Modeling Prep or Twelve Data)
   — ask me and I'll wire that in.
