"""
ai_client.py — the two AI-powered features layered on top of the scoring
engine: reading a portfolio screenshot, and a grounded chatbot.

Uses Google's Gemini API (via the `google-genai` SDK) rather than a paid-only
API, because Google AI Studio's free tier (as of this writing: Gemini 2.5
Flash, ~1,500 requests/day) requires no credit card at all -- unlike
Anthropic's API, which only gives a small one-time trial credit before
requiring billing. See README.md's "AI Features Setup" section for how to
get a free key. Free-tier terms/limits change over time -- check
ai.google.dev/gemini-api/docs/rate-limits if requests start failing.

Nothing in this file ever places a trade or executes anything irreversible --
the chatbot can only *read* ticker analysis and your current holdings; it
cannot add, remove, or modify your portfolio. Screenshot extraction always
requires you to review and confirm results before anything is added.

IMPORTANT: this needs a normal internet connection and a valid API key. It
was written and unit-tested with a mocked Gemini client in a
network-sandboxed build environment -- it has NOT been exercised against the
real API. Test it yourself with a real key before relying on it or sharing
your deployment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from data import StockData
from strategies import buffett_score, graham_score, lynch_score, overall_verdict

# Change this if Google retires the model name -- see ai.google.dev/gemini-api/docs/models
# if you get a "model not found" error. gemini-2.5-flash is on the free tier as of this writing.
MODEL = "gemini-2.5-flash"

MAX_IMAGE_BYTES = 8 * 1024 * 1024


def get_client(api_key: str):
    from google import genai
    return genai.Client(api_key=api_key)


# --------------------------------------------------------------------------
# Screenshot -> structured holdings
# --------------------------------------------------------------------------

@dataclass
class ExtractedHolding:
    ticker: str
    shares: Optional[float] = None
    cost_basis_per_share: Optional[float] = None
    note: str = ""


_RECORD_HOLDINGS_SCHEMA = {
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
}


def extract_holdings_from_image(image_bytes: bytes, media_type: str, api_key: str):
    """Returns (holdings: list[ExtractedHolding], warning: str | None)."""
    if len(image_bytes) > MAX_IMAGE_BYTES:
        return [], "Image is too large -- try a tighter crop or a lower-resolution screenshot."

    from google.genai import types

    client = get_client(api_key)
    record_fn = types.FunctionDeclaration(
        name="record_holdings",
        description="Record every stock/ETF position visible in the brokerage screenshot.",
        parametersJsonSchema=_RECORD_HOLDINGS_SCHEMA,
    )

    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=[types.Content(role="user", parts=[
                types.Part.from_bytes(data=image_bytes, mime_type=media_type),
                types.Part.from_text(text=(
                    "This is a screenshot of a brokerage account's portfolio/holdings screen "
                    "(could be Fidelity, Schwab, Robinhood, or any other broker). Extract every "
                    "position into the record_holdings function. If a number is ambiguous or cut off, "
                    "leave it blank and say why in 'note' rather than guessing."
                )),
            ])],
            config=types.GenerateContentConfig(
                tools=[types.Tool(functionDeclarations=[record_fn])],
                toolConfig=types.ToolConfig(functionCallingConfig=types.FunctionCallingConfig(
                    mode="ANY", allowedFunctionNames=["record_holdings"])),
            ),
        )
    except Exception as e:
        return [], f"Could not reach the AI service: {e}"

    calls = resp.function_calls
    if not calls:
        return [], "The AI didn't return structured data -- try again, or try a clearer screenshot."

    raw = calls[0].args.get("holdings", [])
    holdings = [ExtractedHolding(
        ticker=str(h.get("ticker", "")).upper().strip(),
        shares=h.get("shares"),
        cost_basis_per_share=h.get("cost_basis_per_share"),
        note=h.get("note", ""),
    ) for h in raw if h.get("ticker")]

    if not holdings:
        return [], "No holdings were recognized in that image. Try a clearer or less cropped screenshot."
    return holdings, None


# --------------------------------------------------------------------------
# Chatbot with tool use, grounded in the same 3-lens engine
# --------------------------------------------------------------------------

_ANALYZE_TICKER_SCHEMA = {
    "type": "object",
    "properties": {"ticker": {"type": "string", "description": "Stock ticker, e.g. AAPL"}},
    "required": ["ticker"],
}
_LIST_PORTFOLIO_SCHEMA = {"type": "object", "properties": {}}

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


def _execute_tool(name: str, args: dict, portfolio):
    if name == "analyze_ticker":
        ticker = str(args.get("ticker", "")).upper().strip()
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


def _build_tools():
    from google.genai import types
    return [types.Tool(functionDeclarations=[
        types.FunctionDeclaration(
            name="analyze_ticker",
            description="Run the Buffett/Munger, Graham, and Lynch scoring engine on a stock ticker "
                       "and return scores, verdicts, pros, and cons for all three lenses plus an "
                       "overall read.",
            parametersJsonSchema=_ANALYZE_TICKER_SCHEMA,
        ),
        types.FunctionDeclaration(
            name="list_portfolio",
            description="List the user's current portfolio holdings (ticker and share count) as "
                       "tracked in this app. Does not include external accounts not entered here.",
            parametersJsonSchema=_LIST_PORTFOLIO_SCHEMA,
        ),
    ])]


def chat_turn(messages: list, api_key: str, portfolio, max_tool_rounds: int = 4):
    """messages: list of {"role": "user"/"assistant", "content": str} (simple display-history format).
    Returns (messages, final_text) -- messages is returned unchanged; Gemini's own conversation
    state is rebuilt fresh from it each call, so there's nothing extra to persist between turns."""
    from google.genai import types

    client = get_client(api_key)
    contents = [
        types.Content(role=("model" if m["role"] == "assistant" else "user"),
                      parts=[types.Part.from_text(text=m["content"])])
        for m in messages
    ]
    config = types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, tools=_build_tools())

    for _ in range(max_tool_rounds):
        try:
            resp = client.models.generate_content(model=MODEL, contents=contents, config=config)
        except Exception as e:
            return messages, f"Could not reach the AI service: {e}"

        calls = resp.function_calls
        if not calls:
            return messages, (resp.text or "(no response)")

        model_content = resp.candidates[0].content
        contents.append(model_content)

        response_parts = []
        for fc in calls:
            result = _execute_tool(fc.name, dict(fc.args or {}), portfolio)
            response_parts.append(types.Part.from_function_response(name=fc.name, response=result))
        contents.append(types.Content(role="user", parts=response_parts))

    return messages, "I made several tool calls but couldn't reach a final answer -- try rephrasing your question."
