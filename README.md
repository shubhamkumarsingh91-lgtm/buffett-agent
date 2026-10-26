# Long-Term Lab: Buffett / Graham / Lynch stock research

> **Disclaimer:** Independent personal project. Not tied to any employer or agency.
> Public market data only (Yahoo Finance via `yfinance`, SEC EDGAR, Google News RSS) and
> synthetic test data. No internal or personal data (no SSNs/PHI). Educational research
> only, **not financial advice**. This project never connects to a brokerage and never places trades.
> Portfolio holdings stay in each viewer's own browser and are never written to this repo.

**Live site:** https://shubhamkumarsingh91-lgtm.github.io/buffett-agent/

A shareable research website for long-term investing, built for two friends investing together.
It judges every stock by the rules of the investors who did it best, writes a plain-English memo
for each one, and checks your own portfolio against those rules.

## What's on the site

| Tab | What it does |
|---|---|
| 🚀 **IPO Desk** | Companies listed in the last ~3 years (`ipos.txt`), judged by **Jay Ritter** (IPO research: size, price/sales, post-IPO performance, lock-up) and **Bill Gurley** (revenue quality, gross margin, Rule of 40), with **Philip Fisher** as a growth check, an **IPO checklist** and a link to the **SEC prospectus**. |
| 🗓 **Upcoming IPOs** | Companies that haven't listed yet. Paste an IPO page, or drop in a prospectus PDF, Word file or screenshot. The numbers are pulled out for you to check (`extract.js`) and scored in the browser (`upcoming.js`). "Save for both of us" stores it in `docs/data/upcoming.json` through a GitHub issue. |
| 🏛 **Company Desk** | Established companies (`watchlist.txt`), judged by **Buffett & Munger**, **Benjamin Graham**, **Peter Lynch**, **Philip Fisher** and **Joel Greenblatt** (Magic Formula). |
| 💼 **Our portfolio** | Your holdings from any broker: analysis, risk checks and an **action plan** (see below). |
| 📖 **How it works** | The rules behind every score, in plain words. |

Every stock gets:
* a **research memo** (the business in plain words, bull and bear case, valuation, what to watch)
* a **KPI panel** (growth, profitability, cash, valuation, balance sheet, ownership)
* a **bear/base/bull valuation** from a two-stage DCF
* a **last 30 days** news summary (`news.py`)

The memo is written by rules from the numbers, so **no API key is needed**. If you add a free
`GEMINI_API_KEY` repo secret, an extra AI "analyst's take" paragraph appears.

**Analyze any ticker:** type it in a desk's search box.
* **⚡ Analyze now** runs `.github/workflows/analyze.yml` through GitHub's API, using a key saved
  only in your browser. The result appears on the site in about a minute.
* **Request analysis** opens a pre-filled GitHub issue instead (`request.yml`). Only the owner and
  collaborators can trigger it.

**Agent HQ** (`hq.html`, with a lighter `hq-lite.html`) is a 3D view of the agent at work. It reads
`docs/data/events.json`, written by `hq_events.py` on every run.

## Our portfolio

Holdings are stored **only in the viewer's own browser** (localStorage). Files you import are
read inside the browser and **never uploaded**.

### Import from any file
Supported files:
* PDF statements
* CSV / Excel position exports
* JSON (broker or API dumps, or this site's own backup)
* Word
* text or HTML
* **screenshots and photos**: PNG, JPEG, and iPhone HEIC, which is converted first. Text is read in the browser with Tesseract OCR.

The file picker isn't limited to certain types, so phones list everything. The file type is
detected from the content, not the file name.

`docs/importer.js` reads each file in three ways, in order:
1. **Tables by column.** It finds a header row (Symbol / Qty / Price / Market value / Avg cost …)
   and reads each row by column position. This works for spreadsheets, and also for PDFs and
   screenshots, using the position of each word. App screens are left-aligned and statements are
   right-aligned; both are handled.
2. **JSON.** Any list of objects with a symbol-like field and a quantity-like field, even nested.
3. **Text lines.** Labels such as `10 shares`, `@ 150` or `cost 120` show which number is which.
   Phone-app cards are joined across lines. Without labels, it looks for three numbers where
   shares × price = value.

Every row is **checked** (shares × price = value). If OCR dropped a decimal point (1.7 read as 17),
value ÷ price recovers it and the row is flagged.

**Skipped, with the reason shown:**
* options
* cash and totals
* trade-history and securities-lending tables
* fine print

Nothing is added until you confirm the **review screen**.

### Several accounts
Each holding remembers its account: the broker's name plus **only the last 4 digits** of the
account number, kept only in your browser.
* Importing a second account **adds to** the first.
* Re-importing an account **updates** it without double-counting.
* The portfolio shows one row per stock, with shares summed across accounts.

### Analysis
* **Value and gain.** The gain counts only holdings that have a cost and shows how much of the
  portfolio it covers. The **newest price wins**: your file's (stamped when you import it) or the
  site's last update.
* **Mix:** stocks / index funds / bonds / gold / **crypto**. Crypto is detected by name and has
  its own type.
* **Checks:** concentration, index core, crypto share, PASS-rated stocks, unscored stocks,
  missing prices.

### 🧭 Action plan
For every holding: **Trim / Sell, Review: sell?, Add more, Hold, Hold (don't add), Analyze first**.
Each row gives the dollar amount, the number of shares and the reason. At the top it shows
**where the next $200 goes**. The rules (`RULES` in `index.html`) are printed on the panel:

| Rule | Value | Why |
|---|---|---|
| One stock | ≤ 10% of the portfolio | A common single-company cap. Above it: trim back to 10%. |
| Crypto | ≤ 10% in total | No earnings, and it can fall 70–80%. The smaller coins go first, then BTC and ETH are trimmed evenly. |
| Index core | ≥ 50% | Buffett's 2013 letter (90% index). While the core is below 50%, index funds are the default home for new money. A fund that overlaps a total-market fund (SPY next to VTI) gets Hold. |
| Add more | BUY-rated, under 5% of the portfolio, and less than 15% above fair value | Add only to strong, researched businesses at a sane price. Strong but expensive stocks get Hold, with the price to add at. |
| LIKELY PASS | Review: sell? | Shows the weakest lens's main con and the valuation gap. |

Every trim includes a **tax note** and a **no-tax alternative**: send new money only to the
"Add more" rows. That fixes the same imbalances, just more slowly.

### Export
Export the portfolio as:
* a PDF report (holdings, gains, scores, research notes)
* Excel
* CSV
* a JSON backup

## How it works

```
watchlist.txt + ipos.txt ──► GitHub Action (build_site.py) ──► docs/data/scores.json ──► docs/index.html (GitHub Pages)
                  fetches Yahoo / SEC / news data,        + history.json, events.json     reads the JSON, no keys,
                  runs the lenses, keeps the last good                                    no server
                  result if a fetch fails
```

* **Watchlist:** `watchlist.txt`, one ticker per line with an optional `# note`. Use Yahoo
  symbols (`BRK-B`, not `BRK.B`). Edit it on GitHub, and the site re-scores a few minutes after you save.
* **Updates:** `.github/workflows/update.yml` runs:
  * when the lists or the scoring code change
  * from the "Run workflow" button
  * on a backup weekday-evening schedule
* **TradingView panels** (display-only, free widgets):
  * weekly chart
  * technical rating
  * company profile
  * financial statements
  * ticker tape

  There is also a score-history chart that gains one point per update.

## Setup (one time)

1. **Settings → Pages →** Deploy from a branch → `main` → `/docs` → Save.
2. **Actions → Update investing site → Run workflow** to produce the first scores.
3. Share `https://shubhamkumarsingh91-lgtm.github.io/buffett-agent/`.

Optional: add a cron-job.org job that calls the workflow's dispatch API each weekday at about
5:30 PM New York time (GitHub's own timer is sometimes late).

## Run it on your laptop instead

```bash
pip install -r requirements.txt
python build_site.py                      # writes docs/data/*.json
python -m http.server -d docs 8000        # open http://localhost:8000
node tests/test_importer.js               # portfolio importer tests, no installs needed
```

## Code layout

| File | Purpose |
|---|---|
| `data.py` | Fetches fundamentals from `yfinance` into a `StockData` object; retries on rate limits. |
| `strategies.py` | The scoring lenses and `overall_verdict()`. Pure functions, no network. |
| `build_site.py` | Scores both desks; writes `docs/data/scores.json` and `history.json`. |
| `memo.py` | Writes each stock's research memo (optional Gemini paragraph). |
| `news.py` | "Last 30 days": price move plus headlines from Google News RSS, summarized by rules. |
| `edgar.py` | Finds the IPO prospectus (424B4 / S-1) on SEC EDGAR, no key needed. |
| `hq_events.py` | Writes the plain-English event list for Agent HQ (`docs/data/events.json`). |
| `add_upcoming.py` | Validates an "Add upcoming IPO" issue and saves it to `docs/data/upcoming.json`. |
| `watchlist.txt` / `ipos.txt` | The Company Desk and IPO Desk lists. |
| `docs/index.html` | The website: desks, drawer, portfolio, analysis and action plan. |
| `docs/importer.js` | Portfolio importer: reads holdings from any file (pure functions, tested in Node). |
| `docs/analyze.js` | "⚡ Analyze now" from the site. |
| `docs/upcoming.js`, `docs/extract.js` | Upcoming IPO desk and its number extractor. |
| `docs/export.js` | PDF export for the desks and single stocks. |
| `docs/hq.html`, `docs/hq-lite.html` | Agent HQ. |
| `tests/test_importer.js` | 14 importer cases on synthetic data: statements, broker CSV, JSON, screenshots, several accounts. |
| `.github/workflows/` | `update.yml` (scores), `analyze.yml` (one ticker), `request.yml` (issue requests). |

## Changelog

**Oct 2026: portfolio**
* The importer reads **any file**, including phone screenshots. It handles **several accounts**, a
  correct gain, crypto as its own type and newest-price-wins.
* New **action plan** panel (PRs #15–#20).

**Oct 2026: v2**
* Two desks (IPO and Company), plus the Upcoming IPOs desk.
* New lenses: Fisher, Greenblatt, Ritter, Gurley.
* **Valuation is a two-stage DCF** on free cash flow with the company's own growth rate
  (bear/base/bull). The old flat 20× owner-earnings estimate made quality businesses like
  Coca-Cola and Apple look 100%+ overpriced.
* KPI panel, research memo, IPO checklist, SEC prospectus link, news summary, Analyze now, Agent HQ.

**Oct 2026: fixes in the rebuild**
* **Graham liquidity checks work.** Current assets and liabilities are read from the balance sheet.
* **Dividend yield is correct.** It is computed from `dividendRate / price`; before, a 3.1% yield showed as 310%.
* **Owner earnings sign fixed.** Yahoo's "Change In Working Capital" is already the cash effect.
* The Streamlit app and Gemini chatbot were replaced by the static site.

## Limitations: read before you trust a verdict

* **Quantitative proxies only.** No score can judge a moat's durability, management's character,
  or whether a business is within your circle of competence.
* **Free data has gaps.** About 4 years of annual history vs. the 10-year windows these investors
  used. Yahoo data can be delayed or wrong; check the filings.
* **Valuations are rough.** The DCF uses a 9% discount rate and the company's recent growth. The
  site labels low-confidence estimates; treat them as a sanity check, not a price target.
* **Known issue:** foreign companies that report in another currency (for example ASML, in euros)
  can get a wrong Graham Number. Check those by hand.
* **Screenshots are read by OCR.** Always check the review screen, especially rows marked ⚠ and the tickers.
* **The action plan is a rules-based guide,** not advice. It doesn't know your taxes, goals or timeline.
