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

### Import Screenshot
Upload a screenshot of your brokerage's portfolio screen (Fidelity, Schwab,
Robinhood, whatever) and an AI model reads it and proposes ticker/shares/cost
basis for each position it sees. **You always review and can edit every row**
before anything is added — nothing goes into your portfolio automatically.
Requires an Anthropic API key (see "AI Features Setup" below).

### Ask the Agent
A chat panel grounded in the same scoring engine — ask things like "is NVDA
a Buffett-style buy" or "what's the weakest holding in my portfolio" and it
looks up real scores rather than guessing. It can only *read* — it cannot
add, remove, or modify your holdings, and it never places trades. Also
requires an Anthropic API key.

## AI Features Setup

The Import Screenshot and Ask the Agent tabs need an Anthropic API key
(Analyze and Portfolio work fully without one).

**Getting a key:** go to console.anthropic.com → sign up → API Keys → Create
Key. New accounts get a small amount of free credit; after that it's
pay-as-you-go and cheap for this kind of use (a screenshot read or a chat
reply typically costs a fraction of a cent to a few cents). Check
anthropic.com's current pricing page for exact rates, and consider setting a
spend limit in the console as a safety net.

**Two ways to configure it, depending on who's using the app:**

1. **Paste it into the sidebar** (`Anthropic API key` field). Kept only in
   that browser's session — never written to disk, never committed to git.
   Good for using the app yourself, or for testing.
2. **Streamlit Cloud secrets**, if you deployed this and want it to work for
   anyone with your shared link without them needing their own key: in your
   app's dashboard on share.streamlit.io, go to Settings → Secrets, and add:
   ```
   ANTHROPIC_API_KEY = "sk-ant-your-key-here"
   ```
   This keeps the key out of your public GitHub repo (it lives in Streamlit
   Cloud's secrets store, not in a file you upload) — **never paste a real
   key directly into `app.py` or any file you push to GitHub.**

**Important if you use option 2 (shared deployment):** everyone using your
link will be spending *your* API credits when they use these two tabs.
There's no per-user billing or hard usage cap built in. For sharing with one
friend this is normally a trivial cost, but keep an eye on usage in the
Anthropic console, and set a spend limit there if you want a hard ceiling.

**A note on testing:** this was built and unit-tested with mocked AI
responses in a network-sandboxed environment that had no access to a real
API key — the tool-calling logic and JSON parsing were verified against
synthetic responses shaped like the real API's, but the actual live calls
have not been exercised. Test both features yourself with a real key before
relying on them or sharing your deployment.

## How the code is organized

| File | Purpose |
|---|---|
| `data.py` | Fetches and normalizes fundamentals from `yfinance` into one `StockData` object. All fields are optional — missing data degrades gracefully rather than crashing. |
| `strategies.py` | Three independent scoring functions (`buffett_score`, `graham_score`, `lynch_score`) plus `overall_verdict()` to combine them. Pure functions of `StockData` — no network calls — so they're unit-testable with synthetic data. |
| `portfolio.py` | A tiny local JSON-backed holdings tracker. No brokerage integration. |
| `ai_client.py` | Screenshot-to-holdings extraction and the chatbot's tool-use loop, both via the Anthropic API. |
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
- **Screenshot reading can misread numbers**, especially cramped or partially
  obscured cells. Always check the review table before confirming an import.
- **The chatbot can be wrong or miss context.** It's grounded in the same
  scoring engine via tool calls, but it's still a language model — verify
  anything material the same way you would the scorecards themselves.

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
