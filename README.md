# Long-Term Lab — Buffett / Graham / Lynch stock screener

> **Disclaimer:** Independent personal project. Not tied to any employer or agency.
> Public market data only (Yahoo Finance via `yfinance`). No internal or personal
> data (no SSNs/PHI). Educational research only, **not financial advice**. This
> project never connects to a brokerage and never places trades.

A shareable website for long-term investing research with **two desks**:

| Desk | List file | Judged by |
|---|---|---|
| 🚀 **IPO Desk** (listed in the last ~3 years) | `ipos.txt` | **Jay Ritter** (decades of IPO research: size, price/sales, post-IPO operating performance, lock-up) and **Bill Gurley** ("All Revenue Is Not Created Equal": gross margin, growth, marginal profitability, predictability, Rule of 40), with **Philip Fisher** as a growth-quality check, an **IPO checklist** (lock-up, track record, first-day move, cash runway, insider ownership, short interest, valuation) and a link to the **SEC prospectus** |
| 🏛 **Company Desk** | `watchlist.txt` | **Buffett & Munger**, **Benjamin Graham**, **Peter Lynch**, **Philip Fisher**, **Joel Greenblatt** (Magic Formula) |

Every stock gets a **research memo** (business in plain words, bull and bear case, valuation, what to watch, what to do if you act), a **KPI panel** (growth, profitability, cash, valuation, balance sheet, ownership) and a **bear/base/bull valuation** from a two-stage DCF. The memo is written by rules from the numbers, so **no API key is needed**. If you add a free `GEMINI_API_KEY` repo secret, an extra AI "analyst's take" paragraph appears.

**Request analysis:** type a ticker in a desk's search box and click *Request analysis*. This opens a pre-filled GitHub issue; submitting it runs `.github/workflows/request.yml`, which adds the ticker, re-scores and replies with the link. Only the owner and collaborators can trigger it.

## How it works

```
watchlist.txt + ipos.txt ──► GitHub Action (build_site.py) ──► docs/data/scores.json ──► docs/index.html (GitHub Pages)
                  fetches Yahoo data, runs the        + history.json            reads the JSON, no keys,
                  three lenses, keeps last good                                 no server
                  result if a fetch fails
```

* **Watchlist:** `watchlist.txt`, one ticker per line with an optional `# note`.
  Use Yahoo symbols (`BRK-B`, not `BRK.B`). Edit it on GitHub; the site
  re-scores a few minutes after you save.
* **Updates:** `.github/workflows/update.yml` runs when the watchlist or
  scoring code changes, from the "Run workflow" button, and on a weekday
  evening schedule.
* **Our portfolio tab:** holdings are stored **only in each viewer's own
  browser** (localStorage). Nothing personal is written to this public repo.
  Use Export / Import to move or share a portfolio file.
* **Charts:** a free TradingView embed for price, plus a score-history chart
  that grows one point per update.

## Setup (one time)

1. **Settings → Pages →** Deploy from a branch → `main` → `/docs` → Save.
2. **Actions → Update investing site → Run workflow** to produce the first scores.
3. Share `https://shubhamkumarsingh91-lgtm.github.io/buffett-agent/`.

Optional: add a cron-job.org job that calls the workflow's dispatch API each
weekday at ~5:30 PM New York time (GitHub's own timer is sometimes late).

## Run it on your laptop instead

```bash
pip install -r requirements.txt
python build_site.py                      # writes docs/data/*.json
python -m http.server -d docs 8000        # open http://localhost:8000
```

## Code layout

| File | Purpose |
|---|---|
| `data.py` | Fetches fundamentals from `yfinance` into a `StockData` object; retries on rate limits. |
| `strategies.py` | The three scoring lenses and `overall_verdict()`. Pure functions, no network. |
| `build_site.py` | Scores both desks, writes `docs/data/scores.json` and `history.json`. |
| `memo.py` | Writes each stock's research memo (optional Gemini paragraph). |
| `edgar.py` | Finds the IPO prospectus (424B4 / S-1) on SEC EDGAR, no key needed. |
| `ipos.txt` | The IPO Desk list. |
| `docs/index.html` | The website (single file). |
| `watchlist.txt` | The shared list of tickers. |

## v2 (Oct 2026)

* Two desks (IPO + Company); new lenses: Fisher, Greenblatt, Ritter, Gurley.
* Valuation is now a two-stage DCF on free cash flow with the company's own growth rate
  (bear/base/bull). The old flat 20x-owner-earnings estimate made quality businesses like
  Coca-Cola and Apple look 100%+ overpriced.
* KPI panel, research memo, IPO checklist, SEC prospectus link, request-analysis workflow.

## Fixes in the October 2026 rebuild

* **Graham liquidity checks now work.** Current assets/liabilities are read from
  the balance sheet (Yahoo's `.info` doesn't provide them, so these checks
  were always a neutral placeholder before).
* **Dividend yield is correct.** yfinance now reports `dividendYield` in percent;
  the yield is computed from `dividendRate / price` instead (previously a 3.1%
  yield displayed as 310%).
* **Owner earnings sign fixed.** Yahoo's "Change In Working Capital" is already
  the cash effect, so it is added, not subtracted (previously intrinsic value
  was overstated when a company tied up cash in working capital).
* Streamlit app, screenshot import and Gemini chatbot removed in favour of the
  static site.

## Limitations: read before you trust a verdict

* **Quantitative proxies only.** No score can judge a moat's durability,
  management's character, or whether a business is within your circle of competence.
* **Free data has gaps.** About 4 years of annual history vs. the 10-year windows
  these investors used; Yahoo data can be delayed or wrong. Check filings.
* **The intrinsic value estimate is deliberately simple** (owner earnings,
  9% discount rate, 4% growth). Treat it as a rough sanity check.
* **Not investment advice.** Every score is a prompt for your own research.
