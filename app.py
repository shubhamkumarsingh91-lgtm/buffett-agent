"""
app.py — the web page. Run locally with:

    streamlit run app.py

A dark, glass/neon dashboard over the same three-lens engine (Buffett/Munger,
Graham, Lynch): search a ticker, get a verdict, KPI strip, circular score
gauges, a radar comparison, pros/cons, news, and a portfolio tracker.

Educational research tool, not financial advice. Never places trades.
"""

import json

import streamlit as st
import streamlit.components.v1 as components

from data import fetch_stock_data
from strategies import buffett_score, graham_score, lynch_score, overall_verdict
from portfolio import Portfolio
import ai_client

st.set_page_config(page_title="Buffett-Style Investing Agent", layout="wide",
                    page_icon="◈", initial_sidebar_state="expanded")


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

@st.cache_data(ttl=900, show_spinner=False)
def cached_fetch(ticker: str):
    """Cache each ticker for 15 minutes so repeated lookups (incl. the Portfolio
    tab re-checking every holding) don't trip Yahoo Finance's rate limiter."""
    return fetch_stock_data(ticker)


def esc(text: str) -> str:
    """Escape characters that Streamlit's markdown renderer would otherwise
    misinterpret -- most importantly '$', which triggers LaTeX math mode when
    it appears twice in one string (e.g. 'Price ($61) exceeds ... ($30)'),
    producing the squished/italic rendering bug. Also escape raw HTML angle
    brackets since some of this text is user-adjacent (tickers, names)."""
    return (text.replace("\\", "\\\\").replace("$", "\\$")
                .replace("<", "&lt;").replace(">", "&gt;"))


if "portfolio" not in st.session_state:
    st.session_state.portfolio = Portfolio()
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # list of {"role": "user"/"assistant", "content": str} for display


def resolve_api_key() -> str:
    """Prefer a key set by the deployer via Streamlit secrets (shared across
    everyone using a deployed link); fall back to a key pasted into the
    sidebar for this browser session only."""
    try:
        secret_key = st.secrets.get("GEMINI_API_KEY")
        if secret_key:
            return secret_key
    except Exception:
        pass
    return st.session_state.get("user_api_key", "") or ""


def render_html_embed(html: str, height: int):
    """st.iframe (newer Streamlit) is preferred; components.html is kept as a
    fallback for older Streamlit versions where st.iframe doesn't exist yet."""
    if hasattr(st, "iframe"):
        st.iframe(html, height=height)
    else:
        components.html(html, height=height)


# --------------------------------------------------------------------------
# Theme: dark glass / neon "2050 terminal" look
# --------------------------------------------------------------------------

ACCENT = "#00E5FF"      # cyan -- primary accent
ACCENT2 = "#B026FF"     # violet -- secondary accent
GOOD = "#00FFA3"        # green -- positive
BAD = "#FF3B69"         # red -- negative
WARN = "#FFB020"        # amber -- neutral/warning
BG = "#05060B"
PANEL = "rgba(255,255,255,0.035)"

CUSTOM_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');

html, body, [class*="css"] {{
    font-family: 'Space Grotesk', sans-serif;
}}
.stApp {{
    background:
        radial-gradient(circle at 15% 0%, rgba(0,229,255,0.08), transparent 40%),
        radial-gradient(circle at 85% 20%, rgba(176,38,255,0.07), transparent 40%),
        {BG};
}}
#MainMenu, footer {{visibility: hidden;}}

.hero {{
    padding: 8px 0 18px 0;
}}
.hero h1 {{
    font-size: 2.6rem;
    font-weight: 700;
    margin: 0;
    background: linear-gradient(90deg, #ffffff 0%, {ACCENT} 60%, {ACCENT2} 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -0.5px;
}}
.hero p {{
    color: #8a93a6;
    font-size: 0.95rem;
    margin-top: 6px;
    max-width: 780px;
}}
.badge-live {{
    display:inline-flex; align-items:center; gap:6px;
    font-family:'JetBrains Mono'; font-size:0.72rem; letter-spacing:1px;
    color:{GOOD}; border:1px solid rgba(0,255,163,0.35); background:rgba(0,255,163,0.06);
    padding:4px 10px; border-radius:20px; margin-bottom:14px;
}}
.dot {{ width:7px; height:7px; border-radius:50%; background:{GOOD}; box-shadow:0 0 8px {GOOD}; }}

/* Glass panel */
.glass {{
    background: {PANEL};
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 20px 22px;
    backdrop-filter: blur(6px);
    box-shadow: 0 4px 24px rgba(0,0,0,0.35);
}}

/* KPI chips */
.kpi-row {{ display:flex; gap:12px; flex-wrap:wrap; margin: 6px 0 22px 0; }}
.kpi {{
    flex:1; min-width:130px;
    background:{PANEL}; border:1px solid rgba(255,255,255,0.07); border-radius:14px;
    padding:12px 16px;
}}
.kpi .label {{ font-size:0.68rem; text-transform:uppercase; letter-spacing:1px; color:#6f7890; }}
.kpi .value {{ font-family:'JetBrains Mono'; font-size:1.25rem; font-weight:600; color:#fff; margin-top:2px; }}
.kpi .value.good {{ color:{GOOD}; }}
.kpi .value.bad {{ color:{BAD}; }}

/* Verdict banner */
.verdict {{
    border-radius: 18px; padding: 22px 26px; margin: 4px 0 22px 0;
    border: 1px solid rgba(255,255,255,0.1);
    position: relative; overflow:hidden;
}}
.verdict::before {{
    content:""; position:absolute; inset:0; opacity:0.12; z-index:0;
    background: radial-gradient(circle at 0% 0%, var(--vcolor), transparent 60%);
}}
.verdict .label {{
    font-family:'JetBrains Mono'; font-size:1.7rem; font-weight:700; letter-spacing:1px;
    color: var(--vcolor); text-shadow: 0 0 18px var(--vcolor); position:relative; z-index:1;
}}
.verdict .rationale {{ color:#c3cadb; margin-top:8px; position:relative; z-index:1; font-size:0.95rem; }}
.verdict .score {{ font-family:'JetBrains Mono'; color:#8a93a6; font-size:0.8rem; margin-top:10px; position:relative; z-index:1; }}

/* Strategy cards */
.strategy-card {{
    background:{PANEL}; border:1px solid rgba(255,255,255,0.08); border-radius:16px;
    padding:18px 18px 8px 18px; height:100%;
}}
.strategy-title {{ font-weight:600; font-size:1.02rem; color:#fff; margin-bottom:2px; }}
.strategy-sub {{ color:#6f7890; font-size:0.75rem; margin-bottom:10px; }}

/* Gauge */
.gauge-wrap {{ display:flex; flex-direction:column; align-items:center; margin: 6px 0 4px 0; }}
.gauge {{
    width:128px; height:128px; border-radius:50%;
    display:flex; align-items:center; justify-content:center;
}}
.gauge-inner {{
    width:100px; height:100px; border-radius:50%; background:#0a0c14;
    display:flex; flex-direction:column; align-items:center; justify-content:center;
}}
.gauge-score {{ font-family:'JetBrains Mono'; font-size:1.7rem; font-weight:700; color:#fff; }}
.gauge-max {{ font-family:'JetBrains Mono'; font-size:0.65rem; color:#6f7890; margin-top:-2px; }}
.gauge-verdict {{ font-size:0.78rem; color:#9aa3b8; margin-top:6px; font-weight:500; }}

/* Pros / cons chips */
.chip-list {{ margin-top:10px; }}
.chip {{
    font-size:0.83rem; line-height:1.35; padding:8px 10px; border-radius:8px;
    margin-bottom:6px; border-left:3px solid transparent; color:#d3d8e4;
    background: rgba(255,255,255,0.02);
}}
.chip.pro {{ border-left-color:{GOOD}; }}
.chip.con {{ border-left-color:{BAD}; }}
.chip-heading {{ font-size:0.7rem; text-transform:uppercase; letter-spacing:1px; color:#6f7890; margin:12px 0 4px 0; }}

/* News */
.news-card {{
    background:{PANEL}; border:1px solid rgba(255,255,255,0.07); border-radius:12px;
    padding:12px 14px; margin-bottom:8px;
}}
.news-card a {{ color:#e6ecff; text-decoration:none; font-weight:500; font-size:0.9rem; }}
.news-card a:hover {{ color:{ACCENT}; }}
.news-pub {{ color:#6f7890; font-size:0.72rem; margin-top:3px; }}

hr {{ border-color: rgba(255,255,255,0.08); }}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Render helpers
# --------------------------------------------------------------------------

def gauge_color(score: float) -> str:
    if score >= 65:
        return GOOD
    if score >= 40:
        return WARN
    return BAD


def render_gauge(label: str, sub: str, score: float, verdict: str):
    color = gauge_color(score)
    deg = max(0.0, min(100.0, score)) * 3.6
    html = f"""
    <div class="strategy-card">
      <div class="strategy-title">{esc(label)}</div>
      <div class="strategy-sub">{esc(sub)}</div>
      <div class="gauge-wrap">
        <div class="gauge" style="background: conic-gradient({color} {deg}deg, rgba(255,255,255,0.07) {deg}deg);">
          <div class="gauge-inner">
            <div class="gauge-score" style="color:{color}; text-shadow:0 0 14px {color};">{score:.0f}</div>
            <div class="gauge-max">/ 100</div>
          </div>
        </div>
        <div class="gauge-verdict">{esc(verdict)}</div>
      </div>
    </div>
    """
    return html


def render_pros_cons(pros, cons):
    parts = ['<div class="chip-list">']
    parts.append('<div class="chip-heading">Pros</div>')
    if pros:
        for p in pros:
            parts.append(f'<div class="chip pro">▲ {esc(p)}</div>')
    else:
        parts.append('<div class="chip" style="color:#6f7890;">None identified from available data.</div>')
    parts.append('<div class="chip-heading">Cons</div>')
    if cons:
        for c in cons:
            parts.append(f'<div class="chip con">▼ {esc(c)}</div>')
    else:
        parts.append('<div class="chip" style="color:#6f7890;">None identified from available data.</div>')
    parts.append('</div>')
    return "".join(parts)


def render_kpi(label, value, css_class=""):
    return f"""<div class="kpi"><div class="label">{esc(label)}</div>
                <div class="value {css_class}">{value}</div></div>"""


def fmt_money(x):
    if x is None:
        return "n/a"
    if abs(x) >= 1e12:
        return f"${x/1e12:.2f}T"
    if abs(x) >= 1e9:
        return f"${x/1e9:.2f}B"
    if abs(x) >= 1e6:
        return f"${x/1e6:.2f}M"
    return f"${x:,.2f}"


def fmt_pct(x, decimals=1):
    return f"{x*100:.{decimals}f}%" if x is not None else "n/a"


def render_radar(b_score, g_score, l_score):
    payload = json.dumps({
        "labels": ["Buffett & Munger", "Benjamin Graham", "Peter Lynch"],
        "data": [b_score, g_score, l_score],
    })
    html = f"""
    <html><head>
      <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
      <style>
        html,body {{ margin:0; background:{BG}; }}
        #wrap {{ width:100%; display:flex; justify-content:center; }}
      </style>
    </head>
    <body>
    <div id="wrap"><canvas id="radar" width="360" height="330"></canvas></div>
    <script>
      const payload = {payload};
      new Chart(document.getElementById('radar'), {{
        type: 'radar',
        data: {{
          labels: payload.labels,
          datasets: [{{
            label: 'Score',
            data: payload.data,
            backgroundColor: 'rgba(0,229,255,0.15)',
            borderColor: '{ACCENT}',
            borderWidth: 2,
            pointBackgroundColor: '{ACCENT2}',
            pointRadius: 4,
          }}]
        }},
        options: {{
          responsive:false,
          scales: {{
            r: {{
              min:0, max:100,
              ticks: {{ color:'#5b6478', backdropColor:'transparent', stepSize:25 }},
              grid: {{ color:'rgba(255,255,255,0.08)' }},
              angleLines: {{ color:'rgba(255,255,255,0.12)' }},
              pointLabels: {{ color:'#e6ecff', font: {{ family:'Space Grotesk', size:12 }} }}
            }}
          }},
          plugins: {{ legend: {{ display:false }} }}
        }}
      }});
    </script>
    </body></html>
    """
    render_html_embed(html, height=350)


# --------------------------------------------------------------------------
# Sidebar: AI features setup
# --------------------------------------------------------------------------

with st.sidebar:
    st.markdown("#### ⚡ AI Features")
    deployer_key_present = False
    try:
        deployer_key_present = bool(st.secrets.get("GEMINI_API_KEY"))
    except Exception:
        pass

    if deployer_key_present:
        st.success("AI screenshot import & chatbot are enabled for everyone using this deployment.")
    else:
        st.caption("Screenshot import and the chatbot need a free Gemini API key. "
                   "Get one at aistudio.google.com → Get API Key (no credit card needed), "
                   "then paste it below. It's kept only for this browser session -- never "
                   "saved to disk or committed anywhere.")
        st.text_input("Gemini API key", type="password", key="user_api_key",
                       placeholder="AIza...")
        if resolve_api_key():
            st.success("Key set for this session.")
        else:
            st.info("Without a key, Analyze/Portfolio still work fully -- only "
                    "screenshot import and chat are disabled.")
    st.caption("See README.md → 'AI Features Setup' for cost and security notes "
               "before sharing a deployed link with this enabled.")


# --------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------

st.markdown("""
<div class="hero">
  <div class="badge-live"><span class="dot"></span> LIVE SCREENING ENGINE</div>
  <h1>BUFFETT // GRAHAM // LYNCH</h1>
  <p>Three legendary investors, one screen. Quantitative proxies for quality compounding,
  deep value, and growth-at-a-reasonable-price — scored in real time from public data.
  Educational research only, not financial advice. Nothing here ever places a trade.</p>
</div>
""", unsafe_allow_html=True)

tab_analyze, tab_portfolio, tab_import, tab_chat = st.tabs(
    ["◈  ANALYZE", "▤  PORTFOLIO", "🖼  IMPORT SCREENSHOT", "💬  ASK THE AGENT"])


# --------------------------------------------------------------------------
# Analyze tab
# --------------------------------------------------------------------------

with tab_analyze:
    col_search, col_btn = st.columns([5, 1])
    with col_search:
        ticker_input = st.text_input("Ticker", placeholder="ENTER TICKER — e.g. AAPL, KO, AXP",
                                      label_visibility="collapsed").strip().upper()
    with col_btn:
        go = st.button("ANALYZE", type="primary", width="stretch")

    if go and ticker_input:
        with st.spinner(f"Pulling live data for {ticker_input}..."):
            try:
                data = cached_fetch(ticker_input)
                b = buffett_score(data)
                g = graham_score(data)
                l = lynch_score(data)
                overall = overall_verdict([b, g, l])
                st.session_state["last_analysis"] = (data, b, g, l, overall)
            except SystemExit as e:
                st.error(str(e))

    if "last_analysis" in st.session_state:
        data, b, g, l, overall = st.session_state["last_analysis"]

        st.markdown(f"### {esc(data.name or data.ticker)} <span style='color:#6f7890; font-family:JetBrains Mono; font-size:1rem;'>({data.ticker})</span>",
                    unsafe_allow_html=True)
        st.caption(f"{data.sector or 'n/a'} · {data.industry or 'n/a'}")

        avg_roe = None
        if b.metrics.get("avg_roe") is not None:
            avg_roe = b.metrics["avg_roe"]
        kpis = [
            render_kpi("Price", f"${data.price:,.2f}" if data.price else "n/a"),
            render_kpi("Market Cap", fmt_money(data.market_cap)),
            render_kpi("P/E Ratio", f"{data.pe_ratio:.1f}" if data.pe_ratio else "n/a"),
            render_kpi("Avg ROE", fmt_pct(avg_roe) if avg_roe is not None else "n/a",
                      "good" if (avg_roe or 0) >= 0.15 else ""),
            render_kpi("Debt/Equity", f"{data.debt_to_equity:.2f}" if data.debt_to_equity is not None else "n/a",
                      "good" if (data.debt_to_equity or 99) < 0.5 else "bad" if data.debt_to_equity is not None else ""),
            render_kpi("Dividend Yield", fmt_pct(data.dividend_yield) if data.dividend_yield else "n/a"),
        ]
        st.markdown(f'<div class="kpi-row">{"".join(kpis)}</div>', unsafe_allow_html=True)

        vcolor = {"BUY candidate": GOOD, "WORTH RESEARCHING": WARN,
                  "LIKELY PASS": BAD, "HOLD / NEUTRAL": "#8a93a6"}.get(overall["label"], "#8a93a6")
        st.markdown(f"""
        <div class="verdict" style="--vcolor:{vcolor};">
          <div class="label">{esc(overall['label'])}</div>
          <div class="rationale">{esc(overall['rationale'])}</div>
          <div class="score">COMPOSITE SCORE: {overall['average_score']} / 100 · averaged across all three lenses</div>
        </div>
        """, unsafe_allow_html=True)

        if data.data_notes:
            with st.expander("Data limitations for this ticker"):
                for n in data.data_notes:
                    st.caption(f"- {n}")

        c1, c2, c3 = st.columns(3)
        for col, r, sub in ((c1, b, "Quality compounding"), (c2, g, "Deep value"), (c3, l, "Growth at a reasonable price")):
            with col:
                st.markdown(render_gauge(r.strategy.split(" (")[0], sub, r.score, r.verdict), unsafe_allow_html=True)
                st.markdown(render_pros_cons(r.pros, r.cons), unsafe_allow_html=True)

        st.markdown("<br/>", unsafe_allow_html=True)
        st.markdown('<div class="chip-heading" style="font-size:0.75rem;">LENS COMPARISON</div>', unsafe_allow_html=True)
        render_radar(b.score, g.score, l.score)

        st.markdown("---")
        add_col1, add_col2, add_col3 = st.columns([1, 1, 1])
        with add_col1:
            # Keying on the ticker means each stock gets its own fresh input --
            # without this, Streamlit reuses the same widget state across
            # reruns and "Shares"/"Cost basis" would keep showing whatever was
            # last typed for a *different* ticker instead of resetting.
            shares = st.number_input("Shares", min_value=0.0, value=0.0, step=1.0,
                                      key=f"add_shares_{data.ticker}")
        with add_col2:
            cost = st.number_input(
                "Cost basis / share ($)", min_value=0.0, value=data.price or 0.0, step=1.0,
                key=f"add_cost_{data.ticker}",
                help="What YOU paid per share, not something we look up automatically. "
                     "Pre-filled with today's live price as a starting point -- edit it if "
                     "you actually bought at a different price/date.",
            )
        with add_col3:
            st.write("")
            if st.button("＋ ADD TO PORTFOLIO", width="stretch"):
                if shares > 0:
                    st.session_state.portfolio.add(data.ticker, shares, cost or None)
                    st.success(f"Added {shares:g} shares of {data.ticker}.")
                else:
                    st.warning("Enter a number of shares greater than 0.")

        if data.news:
            st.markdown("---")
            st.markdown('<div class="chip-heading" style="font-size:0.75rem;">RECENT NEWS</div>', unsafe_allow_html=True)
            for n in data.news:
                link = n.get("link") or "#"
                st.markdown(f"""
                <div class="news-card">
                  <a href="{link}" target="_blank">{esc(n['title'])}</a>
                  <div class="news-pub">{esc(n.get('publisher',''))}</div>
                </div>
                """, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Portfolio tab
# --------------------------------------------------------------------------

with tab_portfolio:
    holdings = st.session_state.portfolio.list()
    if not holdings:
        st.info("No holdings yet. Analyze a stock in the ◈ ANALYZE tab and click **＋ Add to Portfolio**.")
    else:
        rows = []
        total_value = 0.0
        total_cost = 0.0
        for h in holdings:
            try:
                data = cached_fetch(h.ticker)
                b = buffett_score(data); g = graham_score(data); l = lynch_score(data)
                price = data.price or 0.0
            except SystemExit:
                price = 0.0
                b = g = l = None
            value = price * h.shares
            cost = (h.cost_basis_per_share or 0) * h.shares
            total_value += value
            total_cost += cost
            rows.append({
                "Ticker": h.ticker, "Shares": h.shares, "Price": round(price, 2),
                "Value ($)": round(value, 2), "Cost Basis": h.cost_basis_per_share,
                "Gain/Loss ($)": round(value - cost, 2) if h.cost_basis_per_share else None,
                "Gain/Loss (%)": round((value - cost) / cost * 100, 1) if cost else None,
                "Buffett": b.score if b else None, "Graham": g.score if g else None, "Lynch": l.score if l else None,
            })

        gain_loss_pct = ((total_value - total_cost) / total_cost * 100) if total_cost else None
        kpis = [
            render_kpi("Total Value", fmt_money(total_value)),
            render_kpi("Total Cost Basis", fmt_money(total_cost) if total_cost else "n/a"),
            render_kpi("Total Gain/Loss", f"{gain_loss_pct:+.1f}%" if gain_loss_pct is not None else "n/a",
                      "good" if (gain_loss_pct or 0) >= 0 else "bad"),
            render_kpi("Holdings", str(len(holdings))),
        ]
        st.markdown(f'<div class="kpi-row">{"".join(kpis)}</div>', unsafe_allow_html=True)

        st.dataframe(rows, width="stretch", hide_index=True)

        st.markdown("---")
        remove_ticker = st.selectbox("Remove a holding", options=[h.ticker for h in holdings])
        if st.button("REMOVE"):
            st.session_state.portfolio.remove(remove_ticker)
            st.rerun()


# --------------------------------------------------------------------------
# Import Screenshot tab
# --------------------------------------------------------------------------

with tab_import:
    api_key = resolve_api_key()
    st.markdown("Upload a screenshot of your brokerage portfolio screen (Fidelity, Schwab, Robinhood, "
                "anything) and this will try to read off each position's ticker, shares, and cost basis "
                "for you -- **always review the results below before confirming**, AI reading of "
                "screenshots isn't perfect.")

    if not api_key:
        st.warning("Add a Gemini API key in the sidebar to use this feature.")
    else:
        uploaded = st.file_uploader("Portfolio screenshot", type=["png", "jpg", "jpeg"])
        if uploaded is not None:
            st.image(uploaded, caption="Uploaded screenshot", width=420)
            media_type = uploaded.type or "image/png"
            if st.button("🔍 EXTRACT HOLDINGS", type="primary"):
                with st.spinner("Reading the screenshot..."):
                    holdings, warning = ai_client.extract_holdings_from_image(
                        uploaded.getvalue(), media_type, api_key)
                if warning:
                    st.error(warning)
                    st.session_state.pop("extracted_holdings", None)
                else:
                    st.session_state["extracted_holdings"] = [
                        {"Ticker": h.ticker, "Shares": h.shares,
                         "Cost Basis/Share": h.cost_basis_per_share, "Note": h.note}
                        for h in holdings
                    ]

        if "extracted_holdings" in st.session_state:
            st.markdown("##### Review before adding -- edit any cell that looks wrong")
            edited = st.data_editor(st.session_state["extracted_holdings"], num_rows="dynamic",
                                    key="extracted_editor", width="stretch")
            def _clean_num(x):
                """st.data_editor turns blank numeric cells into NaN (via pandas), not None --
                and NaN is truthy in plain Python, so a naive `if x` check would treat a blank
                cost-basis cell as a real value and store NaN in the portfolio. Guard against that."""
                if x is None:
                    return None
                try:
                    xf = float(x)
                except (TypeError, ValueError):
                    return None
                return None if xf != xf else xf  # xf != xf is the standard NaN check

            if st.button("✓ CONFIRM & ADD ALL TO PORTFOLIO", type="primary"):
                added = 0
                for row in edited:
                    ticker = str(row.get("Ticker", "")).strip().upper()
                    shares = _clean_num(row.get("Shares"))
                    cost = _clean_num(row.get("Cost Basis/Share"))
                    if ticker and shares:
                        st.session_state.portfolio.add(ticker, shares, cost)
                        added += 1
                st.success(f"Added {added} holding(s) to your portfolio.")
                del st.session_state["extracted_holdings"]
                st.rerun()


# --------------------------------------------------------------------------
# Chat tab
# --------------------------------------------------------------------------

with tab_chat:
    api_key = resolve_api_key()
    st.caption("Ask about any ticker or your saved portfolio. This chatbot can look things up using the "
               "same three-lens engine as the Analyze tab, but it can't add/remove holdings or place "
               "trades -- and it's not financial advice.")

    if not api_key:
        st.warning("Add a Gemini API key in the sidebar to use the chatbot.")
    else:
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(esc(msg["content"]))

        user_msg = st.chat_input("e.g. \"Is NVDA a Buffett-style buy?\" or \"What's my weakest holding?\"")
        if user_msg:
            st.session_state.chat_history.append({"role": "user", "content": user_msg})
            with st.chat_message("user"):
                st.markdown(esc(user_msg))

            api_messages = [{"role": m["role"], "content": m["content"]}
                            for m in st.session_state.chat_history[:-1]]
            api_messages.append({"role": "user", "content": user_msg})

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    _, reply = ai_client.chat_turn(api_messages, api_key, st.session_state.portfolio)
                st.markdown(esc(reply))
            st.session_state.chat_history.append({"role": "assistant", "content": reply})

        if st.session_state.chat_history and st.button("Clear chat"):
            st.session_state.chat_history = []
            st.rerun()


st.markdown("---")
st.caption("Not financial advice. Scores are quantitative proxies for Buffett/Munger, Graham, and "
           "Lynch's public criteria, built on free data (Yahoo Finance via yfinance) — they cannot "
           "judge moat durability, management character, or whether a business is in *your* circle "
           "of competence. Always verify against actual filings before acting. This tool never "
           "places trades on your behalf.")
