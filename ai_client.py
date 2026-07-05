"""
ai_client.py — the two AI-powered features layered on top of the scoring
engine: reading a portfolio screenshot, and a grounded chatbot.

Both require an Anthropic API key (see README.md's "AI Features Setup"
section for how to get one and where to put it). Nothing in this file ever
places a trade or executes anything irreversible -- the chatbot can only
*read* ticker analysis and your current holdings; it cannot add, remove, or
modify your portfolio. Screenshot extraction always requires you to review
and confirm results before anything is added.

IMPORTANT: this needs a normal internet connection and a valid API key. It
was written and unit-tested with a mocked Anthropic client in a
network-sandboxed build environment -- it has NOT been exercised against the
real API. Test it yourself with a real key before relying on it or sharing
your deployment.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Optional

from data import StockData
from strategies import buffett_score, graham_score, lynch_score, overall_verdict

# Change this if Anthropic retires the model name -- see docs.claude.com for
# current model identifiers if you get a "model not found" error.
MODEL = "claude-sonnet-5"

MAX_IMAGE_BYTES = 8 * 1024 * 1024  # Anthropic's vision limit is ~5MB per image encoded; stay well under it raw


def get_client(api_key: str):
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


# --------------------------------------------------------------------------
# Screenshot -> structured holdings
# --------------------------------------------------------------------------

@dataclass
class ExtractedHolding:
    ticker: str
    shares: Optional[float] = None
    cost_basis_per_share: Optional[float] = None
    note: str = ""


_RECORD_HOLDINGS_TOOL = {
    "name": "record_holdings",
    "description": "Record every stock/ETF position visible in the brokerage screenshot.",
    "input_schema": {
        "type": "object",
        "properties": {
            "holdings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Stock/ETF ticker symbol, uppercase"},
                        "shares": {"type": "number", "description": "Number of shares held, if visible"},
                        "cost_basis_per_share": {
                            "type": "number",
                            "description": "Average cost / cost basis per share in dollars, if visible. "
                                           "Do NOT confuse this with the current market price.",
                        },
                        "note": {
                            "type": "string",
                            "description": "Anything uncertain about this row, e.g. 'shares partially "
                                           "obscured' or 'cost basis not shown, left blank'.",
                        },
                    },
                    "required": ["ticker"],
                },
            }
        },
        "required": ["holdings"],
    },
}


def extract_holdings_from_image(image_bytes: bytes, media_type: str, api_key: str):
    """Returns (holdings: list[ExtractedHolding], warning: str | None)."""
    if len(image_bytes) > MAX_IMAGE_BYTES:
        return [], "Image is too large -- try a tighter crop or a lower-resolution screenshot."

    client = get_client(api_key)
    b64 = base64.b64encode(image_bytes).decode("utf-8")

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            tools=[_RECORD_HOLDINGS_TOOL],
            tool_choice={"type": "tool", "name": "record_holdings"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text", "text": (
                        "This is a screenshot of a brokerage account's portfolio/holdings screen "
                        "(could be Fidelity, Schwab, Robinhood, or any other broker). Extract every "
                        "position into the record_holdings tool. If a number is ambiguous or cut off, "
                        "leave it blank and say why in 'note' rather than guessing."
                    )},
                ],
            }],
        )
    except Exception as e:
        return [], f"Could not reach the AI service: {e}"

    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "record_holdings":
            raw = block.input.get("holdings", [])
            holdings = [ExtractedHolding(
                ticker=str(h.get("ticker", "")).upper().strip(),
                shares=h.get("shares"),
                cost_basis_per_share=h.get("cost_basis_per_share"),
                note=h.get("note", ""),
            ) for h in raw if h.get("ticker")]
            if not holdings:
                return [], "No holdings were recognized in that image. Try a clearer or less cropped screenshot."
            return holdings, None

    return [], "The AI didn't return structured data -- try again, or try a clearer screenshot."


# --------------------------------------------------------------------------
# Chatbot with tool use, grounded in the same 3-lens engine
# --------------------------------------------------------------------------

_CHAT_TOOLS = [
    {
        "name": "analyze_ticker",
        "description": "Run the Buffett/Munger, Graham, and Lynch scoring engine on a stock ticker and "
                       "return scores, verdicts, pros, and cons for all three lenses plus an overall read.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker, e.g. AAPL"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "list_portfolio",
        "description": "List the user's current portfolio holdings (ticker and share count) as tracked "
                       "in this app. Does not include external accounts not entered into this app.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

SYSTEM_PROMPT = """You are the research assistant inside a Buffett/Graham/Lynch-style stock screening app.

You have two tools: analyze_ticker (runs the app's own quantitative screen on any ticker) and
list_portfolio (the user's saved holdings in this app). Use them whenever a question is about a
specific stock or the user's portfolio -- don't guess at numbers you could look up.

Ground rules:
- This is educational research, never financial advice. Don't tell the user to buy or sell; help them
  reason through the evidence the three lenses surface, and be upfront about disagreement between lenses.
- You cannot add, remove, or modify the user's portfolio, and you never place trades. If asked to do so,
  explain that they need to use the "Import Screenshot" or manual "Add to Portfolio" flow themselves.
- If a ticker fails to fetch (rate-limited or invalid), say so plainly rather than fabricating numbers.
- Keep answers concise and concrete -- reference actual scores/metrics from the tools, not generic advice.
"""


def _execute_tool(name: str, tool_input: dict, portfolio):
    if name == "analyze_ticker":
        ticker = str(tool_input.get("ticker", "")).upper().strip()
        if not ticker:
            return {"error": "No ticker provided."}
        from data import fetch_stock_data
        try:
            data: StockData = fetch_stock_data(ticker)
        except SystemExit as e:
            return {"error": str(e)}
        b, g, l = buffett_score(data), graham_score(data), lynch_score(data)
        overall = overall_verdict([b, g, l])
        return {
            "ticker": data.ticker, "name": data.name, "price": data.price,
            "overall_label": overall["label"], "overall_rationale": overall["rationale"],
            "average_score": overall["average_score"],
            "strategies": [
                {"strategy": r.strategy, "score": r.score, "verdict": r.verdict, "pros": r.pros, "cons": r.cons}
                for r in (b, g, l)
            ],
        }
    if name == "list_portfolio":
        holdings = portfolio.list()
        return {"holdings": [{"ticker": h.ticker, "shares": h.shares,
                              "cost_basis_per_share": h.cost_basis_per_share} for h in holdings]}
    return {"error": f"Unknown tool: {name}"}


def chat_turn(messages: list, api_key: str, portfolio, max_tool_rounds: int = 4):
    """messages: list of {"role": "user"/"assistant", "content": str-or-blocks}.
    Returns (updated_messages, final_text). Runs the tool-use loop internally."""
    client = get_client(api_key)
    working = list(messages)

    for _ in range(max_tool_rounds):
        try:
            resp = client.messages.create(
                model=MODEL, max_tokens=1500, system=SYSTEM_PROMPT,
                tools=_CHAT_TOOLS, messages=working,
            )
        except Exception as e:
            return working, f"Could not reach the AI service: {e}"

        working.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
            return working, text or "(no response)"

        tool_results = []
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                result = _execute_tool(block.name, block.input, portfolio)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })
        working.append({"role": "user", "content": tool_results})

    return working, "I made several tool calls but couldn't reach a final answer -- try rephrasing your question."
