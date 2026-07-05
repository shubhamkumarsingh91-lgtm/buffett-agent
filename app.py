"""
app.py — the web page. Run locally with:

    streamlit run app.py

Two tabs:
  1. Analyze a Stock  — type a ticker, get live data run through three
     independent strategy lenses (Buffett/Munger, Graham, Lynch), each with
     explicit pros/cons, plus an overall read and recent news.
  2. My Portfolio      — everything you've added, with live scores and
     gain/loss, stored locally in portfolio_data.json next to this file.

This is an educational research aid, not financial advice, and it never
places trades or connects to a brokerage. See README.md for setup and full
disclaimers.
"""

import streamlit as st

from data import fetch_stock_data
from strategies import buffett_score, graham_score, lynch_score, overall_verdict
from portfolio import Portfolio

st.set_page_config(page_title="Buffett-Style Investing Agent", layout="wide")

if "portfolio" not in st.session_state:
    st.session_state.portfolio = Portfolio()


def render_strategy_card(result):
    st.markdown(f"#### {result.strategy}")
    st.progress(min(max(result.score / 100, 0.0), 1.0))
    st.caption(f"Score: {result.score}/100 — **{result.verdict}**")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Pros**")
        if result.pros:
            for p in result.pros:
                st.markdown(f"- {p}")
        else:
            st.caption("None identified from available data.")
    with col2:
        st.markdown("**Cons**")
        if result.cons:
            for c in result.cons:
                st.markdown(f"- {c}")
        else:
            st.caption("None identified from available data.")


def analyze(ticker: str):
    with st.spinner(f"Fetching live data for {ticker}..."):
        try:
            data = fetch_stock_data(ticker)
        except SystemExit as e:
            st.error(str(e))
            return None
    b = buffett_score(data)
    g = graham_score(data)
    l = lynch_score(data)
    overall = overall_verdict([b, g, l])
    return data, b, g, l, overall


st.title("Buffett-Style Investing Agent")
st.caption("Educational research tool — not financial advice. Combines Buffett/Munger, "
           "Benjamin Graham, and Peter Lynch's public criteria into one screen. "
           "Never places trades; you make every decision yourself.")

tab_analyze, tab_portfolio = st.tabs(["🔎 Analyze a Stock", "📁 My Portfolio"])

with tab_analyze:
    col_search, col_btn = st.columns([4, 1])
    with col_search:
        ticker_input = st.text_input("Ticker symbol", placeholder="e.g. AAPL, KO, AXP",
                                      label_visibility="collapsed")
    with col_btn:
        go = st.button("Analyze", type="primary", use_container_width=True)

    if go and ticker_input:
        result = analyze(ticker_input)
        if result:
            data, b, g, l, overall = result
            st.session_state["last_analysis"] = (data, b, g, l, overall)

    if "last_analysis" in st.session_state:
        data, b, g, l, overall = st.session_state["last_analysis"]

        header_col1, header_col2, header_col3 = st.columns([2, 1, 1])
        with header_col1:
            st.subheader(f"{data.name or data.ticker} ({data.ticker})")
            st.caption(f"{data.sector or 'n/a'} — {data.industry or 'n/a'}")
        with header_col2:
            st.metric("Price", f"${data.price:,.2f}" if data.price else "n/a")
        with header_col3:
            st.metric("Avg. Lens Score", f"{overall['average_score']}/100")

        verdict_color = {"BUY candidate": "green", "WORTH RESEARCHING": "orange",
                         "LIKELY PASS": "red", "HOLD / NEUTRAL": "gray"}.get(overall["label"], "gray")
        st.markdown(f"### :{verdict_color}[{overall['label']}]")
        st.write(overall["rationale"])

        if data.data_notes:
            with st.expander("Data limitations for this ticker"):
                for n in data.data_notes:
                    st.caption(f"- {n}")

        st.divider()
        c1, c2, c3 = st.columns(3)
        with c1:
            render_strategy_card(b)
        with c2:
            render_strategy_card(g)
        with c3:
            render_strategy_card(l)

        st.divider()
        add_col1, add_col2, add_col3, add_col4 = st.columns([1, 1, 1, 1])
        with add_col1:
            shares = st.number_input("Shares", min_value=0.0, value=0.0, step=1.0, key="add_shares")
        with add_col2:
            cost = st.number_input("Cost basis / share ($)", min_value=0.0, value=data.price or 0.0,
                                    step=1.0, key="add_cost")
        with add_col3:
            st.write("")
            st.write("")
            if st.button("Add to Portfolio"):
                if shares > 0:
                    st.session_state.portfolio.add(data.ticker, shares, cost or None)
                    st.success(f"Added {shares} shares of {data.ticker} to your portfolio.")
                else:
                    st.warning("Enter a number of shares greater than 0.")

        if data.news:
            st.divider()
            st.markdown("#### Recent News")
            for n in data.news:
                if n.get("link"):
                    st.markdown(f"- [{n['title']}]({n['link']}) — *{n.get('publisher','')}*")
                else:
                    st.markdown(f"- {n['title']} — *{n.get('publisher','')}*")

with tab_portfolio:
    holdings = st.session_state.portfolio.list()
    if not holdings:
        st.info("No holdings yet. Analyze a stock in the first tab and click **Add to Portfolio**.")
    else:
        st.markdown("Refreshing live prices and scores for your holdings...")
        rows = []
        total_value = 0.0
        total_cost = 0.0
        for h in holdings:
            try:
                data = fetch_stock_data(h.ticker)
                b = buffett_score(data)
                g = graham_score(data)
                l = lynch_score(data)
                price = data.price or 0.0
            except SystemExit:
                price = 0.0
                b = g = l = None
            value = price * h.shares
            cost = (h.cost_basis_per_share or 0) * h.shares
            total_value += value
            total_cost += cost
            rows.append({
                "Ticker": h.ticker,
                "Shares": h.shares,
                "Price": price,
                "Value ($)": round(value, 2),
                "Cost Basis": h.cost_basis_per_share,
                "Gain/Loss ($)": round(value - cost, 2) if h.cost_basis_per_share else None,
                "Gain/Loss (%)": round((value - cost) / cost * 100, 1) if cost else None,
                "Buffett Score": b.score if b else None,
                "Graham Score": g.score if g else None,
                "Lynch Score": l.score if l else None,
            })

        st.dataframe(rows, use_container_width=True, hide_index=True)

        m1, m2, m3 = st.columns(3)
        m1.metric("Total Value", f"${total_value:,.2f}")
        m2.metric("Total Cost Basis", f"${total_cost:,.2f}" if total_cost else "n/a")
        if total_cost:
            m3.metric("Total Gain/Loss", f"{(total_value - total_cost) / total_cost:+.1%}")

        st.divider()
        remove_ticker = st.selectbox("Remove a holding", options=[h.ticker for h in holdings])
        if st.button("Remove"):
            st.session_state.portfolio.remove(remove_ticker)
            st.rerun()

st.divider()
st.caption("Not financial advice. Scores are quantitative proxies for Buffett/Munger, Graham, and "
           "Lynch's public criteria, built on free data (Yahoo Finance via yfinance) — they cannot "
           "judge moat durability, management character, or whether a business is in *your* circle "
           "of competence. Always verify against actual filings before acting, and this tool never "
           "places trades on your behalf.")
