# Long-Term Lab — Buffett / Graham / Lynch stock screener

> **Disclaimer:** Independent personal project. Not tied to any employer or agency.
> Public market data only (Yahoo Finance via `yfinance`). No internal or personal
> data (no SSNs/PHI). Educational research only, **not financial advice**. This
> project never connects to a brokerage and never places trades.

A shareable website for long-term investing research. Every stock on a shared
watchlist is scored 0–100 through three classic investors' public criteria:

| Lens | What it rewards |
|---|---|
| **Buffett & Munger** (quality compounding) | High, stable margins (moat), low debt, high ROE, buybacks, margin of safety vs. an owner-earnings value estimate |
| **Benjamin Graham** (deep value) | Price below the Graham Number, P/E × P/B under 22.5, current ratio ≥ 2, debt covered by working capital, no loss years, dividends |
| **Peter Lynch** (growth at a reasonable price) | PEG under 1, growth category, manageable debt, low institutional ownership |

The average gives a headline verdict: **BUY candidate / WORTH RESEARCHING /
HOLD-NEUTRAL / LIKELY PASS**, with plain-English pros and cons for each lens.

## How it works

```
watchlist.txt ──► GitHub Action (build_site.py) ──► docs/data/scores.json ──► docs/index.html (GitHub Pages)
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
| `build_site.py` | Scores the watchlist, writes `docs/data/scores.json` and `history.json`. |
| `docs/index.html` | The website (single file). |
| `watchlist.txt` | The shared list of tickers. |

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
