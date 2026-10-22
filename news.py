"""
news.py — "Last 30 days": one short paragraph on a stock's past month of news, plus the key headlines.

DISCLAIMER: Independent personal project. Not tied to any employer or agency.
Public data only (Google News RSS, Yahoo Finance prices). No internal or personal data
(no SSNs/PHI). Educational research, not financial advice.

No API key needed. Headlines come from Google News' public RSS search (last 30 days) and
the paragraph is assembled by rules: how far the price moved, how much news there was, what
it was mostly about (earnings, analyst calls, deals, legal...), and whether headlines leaned
positive or negative. That reads headlines, not the articles themselves. If the optional
GEMINI_API_KEY secret is set, Gemini writes the paragraph from the same headlines instead;
if that fails, the rule-based paragraph is used.
"""
from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

UA = "Mozilla/5.0 (LongTermLab research site; +https://github.com/shubhamkumarsingh91-lgtm/buffett-agent)"

THEMES = [  # (label, regex on the headline); a headline can count toward more than one theme
    ("earnings & guidance", r"\bearnings\b|\bresults\b|\bquarter(ly)?\b|\bQ[1-4]\b|\brevenue\b|\bprofit\b|\bEPS\b|\bbeats?\b|\bmiss(es|ed)?\b|\bguidance\b|\boutlook\b|\bforecast"),
    ("analyst calls", r"upgrade|downgrade|price target|\bPT\b|\brating\b|overweight|underweight|outperform|underperform|initiat|\banalysts?\b"),
    ("deals & partnerships", r"acqui|merger|\bdeal\b|partnership|\bstake\b|buyout|takeover|\bcontract\b|\border(s)?\b|agreement|joint venture"),
    ("products & technology", r"\blaunch|unveil|\bproduct|\bchips?\b|\bAI\b|platform|release|\bmodel\b|\bdevice|technology"),
    ("legal & regulation", r"lawsuit|\bsue[sd]?\b|probe|investigat|\bSEC\b|antitrust|regulat|\bban\b|export|tariff|\bfine[sd]?\b|court|settle"),
    ("management", r"\bCEO\b|\bCFO\b|executive|resign|appoint|steps down|\bboard\b|chairman|founder"),
    ("dividends & buybacks", r"dividend|buyback|repurchase|stock split|\bsplit\b"),
    ("stock moves", r"\bshares? (jump|surge|soar|rall|fall|drop|slide|slip|plunge|tumble|sink|climb|rise|gain)|\bstock (jump|surge|soar|rall|fall|drop|slide|slip|plunge|tumble|sink|climb|rise|gain)|record high|52-week|all-time high"),
    ("insider trades", r"insiders? (sells?|sold|buys?|bought|selling|buying|trading|trades)|(officer|director|ceo|cfo|coo|chairman|co-founder|founder|executive|evp|svp|\bvp)\b[^.]{0,40}\b(sells?|sold|buys?|bought|unloads?|dumps?)\b|(sells?|sold|buys?|bought) (US)?\$?[\d.,]+ ?(million|billion|M|B)? (in|of|worth) (common )?(stock|shares)|form 4\b|\bwithholds? [\d,]+ shares"),
    ("buy/sell opinion pieces", r"should you|\bis it (a|time)|buy now|\btop stock|best stock|no-brainer|undervalued|overvalued|expensive|\bcheap\b|\bbargain|millionaire|forever|prediction:|here'?s (why|what|how)|history says|\bI think\b|will be worth|could (soar|surge|double)|\?$|\bmy (top|favorite)|\bbuy and hold"),
    ("IPO & listing", r"\bIPO\b|listing|debut|lock-?up|\bfloat\b"),
]
POS = r"\bbeats?\b|surge|soar|\bjump|rall(y|ies|ied)|record|upgrade|\braise[sd]?\b|strong|\bgains?\b|\bwins?\b|approv|boost|climb|top(s|ped)? estimates|outperform|bullish|\bhigher\b"
NEG = r"\bmiss(es|ed)?\b|\bfall(s|ing)?\b|\bfell\b|\bdrop|plunge|tumble|\bcut[s]?\b|downgrade|lawsuit|probe|\bweak|slump|\bloss(es)?\b|\bwarn|recall|delay|\bsink|slide|slip|bearish|\blower\b|layoff|investigat|\bsell-?off"
STOP = {"inc", "corp", "corporation", "co", "company", "the", "ltd", "limited", "plc", "holding", "holdings", "group",
        "class", "a", "b", "nv", "sa", "ag", "se", "and", "international", "incorporated", "llc", "lp"}
# Publishers whose headlines are about markets/business, and words that put a headline in a business context.
# Used to keep "Visa Expands U.K. Merchant Reach" but drop "Latvia calls for visa ban" or "Jeremy Lin's Reddit AMA".
FIN_SOURCES = r"reuters|bloomberg|cnbc|wall street journal|\bwsj\b|barron|marketwatch|financial times|yahoo|motley fool|seeking alpha|marketbeat|investing\.com|tipranks|zacks|benzinga|tradingview|simply wall|business wire|pr ?newswire|globe ?newswire|forbes|business insider|fortune|axios|the information|techcrunch|quartz|globe and mail|morningstar|kiplinger|nasdaq|stocktwits|24/7 wall|moomoo|gurufocus|insider monkey|investopedia|the street|thestreet|fool\.com|marketscreener|stock titan|tikr|pymnts|american banker|fierce|s&p global|\bft\b|economist|associated press|\bap\b|cnn business|fox business|investor's business|ibd|kiplinger|sec\.gov"
BIZ_WORDS = r"\bstock|\bshares?\b|earnings|revenue|profit|\bsales\b|quarter|\bQ[1-4]\b|analyst|price target|rating|upgrade|downgrade|dividend|buyback|investor|\bCEO\b|\bCFO\b|executive|acqui|merger|\bdeal\b|partnership|partners? with|lawsuit|\bsued?\b|regulator|antitrust|\bfine[sd]?\b|guidance|forecast|outlook|valuation|market cap|\bIPO\b|layoffs?|jobs|launch|unveil|expands?|\bNYSE\b|\bNASDAQ\b|insider|stake|billion|million|\bfiling\b|\bSEC\b"
JUNK = r"stock price, news, quote|live share price|share price today|stock price today|stock quote|stock forecast|price prediction|forecast for 20\d\d|stock price forecast|\(.*\) stock forecasts?$"


def short_name(name: str, ticker: str) -> str:
    """'Micron Technology, Inc.' -> 'Micron Technology'; 'The Coca-Cola Company' -> 'Coca-Cola';
    'Johnson & Johnson' stays whole; 'ASML Holding N.V.' -> 'ASML'."""
    words = [w.strip(",") for w in (name or "").split()]
    keep = [w for w in words if w == "&" or w.lower().strip(".,").replace(".", "") not in STOP]
    keep = keep[:4]
    while keep and keep[-1] == "&":
        keep.pop()
    while keep and keep[0] == "&":
        keep.pop(0)
    return " ".join(w.rstrip(".") for w in keep) or ticker.split(".")[0]


def feed_url(name: str, ticker: str) -> str:
    base, _, suf = ticker.upper().partition(".")
    india = suf in ("NS", "BO")
    q = f'("{short_name(name, ticker)}" OR "{base} stock" OR "{base} shares") when:30d'
    region = "hl=en-IN&gl=IN&ceid=IN:en" if india else "hl=en-US&gl=US&ceid=US:en"
    return "https://news.google.com/rss/search?q=" + urllib.parse.quote(q) + "&" + region


def fetch_feed(name: str, ticker: str, timeout: int = 15) -> str:
    req = urllib.request.Request(feed_url(name, ticker), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def parse_feed(xml: str, name: str, ticker: str, days: int = 30, now: Optional[datetime] = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    root = ET.fromstring(xml)
    key = short_name(name, ticker).split()[0]
    base = ticker.split(".")[0].upper()
    out, seen = [], set()
    for it in root.iter("item"):
        title, src = (it.findtext("title") or "").strip(), (it.findtext("source") or "").strip()
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3].strip()
        try:
            when = parsedate_to_datetime(it.findtext("pubDate") or "")
        except (TypeError, ValueError):
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when < now - timedelta(days=days) or not title:
            continue
        # keep headlines about the company as a business: the ticker, or the name written as a proper
        # noun ("Visa", not "visa") plus a business word or a business/markets publisher
        has_tk = bool(re.search(rf"(?<![A-Za-z])\$?{re.escape(base)}(?![A-Za-z])", title)) and len(base) >= 2 and base not in ("A", "V", "ON", "IT", "ALL", "NOW", "ARE", "BIG", "CAN", "SO")
        nm = [m for m in re.finditer(re.escape(key), title, re.I) if title[m.start()].isupper()]
        if not nm and not has_tk:
            continue
        own = key.lower() in src.lower()                         # the company's own newsroom / IR site
        if not (has_tk or own or re.search(BIZ_WORDS, title, re.I) or re.search(FIN_SOURCES, src, re.I)):
            continue
        if re.search(JUNK, title, re.I):                         # quote pages and "forecast 2026-2030" pages
            continue
        # "J-1 Visa", "Golden Visa", "student visa": the word, not the company
        if re.search(r"(J-1|H-1B|H1B|F-1|L-1|O-1|E-2|EB-5|B-1|B-2|Golden|Student|Travel|Tourist|Work|Nomad|Investor|Startup|Family|Spousal|Partner)\s+" + re.escape(key) + r"\b", title, re.I):
            continue
        # the brand used for something else: a separately listed bottler, a scholarship, an arena...
        full = re.escape(short_name(name, ticker))
        if re.search(full + r"\s+(Consolidated|Bottling|Bottlers|Beverages|Europacific|HBC|FEMSA|Scholars?|Foundation|Bulletin|Arena|Center|Centre|Stadium|Park|Festival|Cup|Championship|Classic|Bowl|Theater|Theatre|Amphitheater)\b", title, re.I) and not has_tk:
            continue
        sig = re.sub(r"[^a-z0-9]", "", title.lower())[:50]
        if sig in seen:
            continue
        seen.add(sig)
        # match themes without the company's own name ("Micron Technology" isn't a technology story)
        bare = re.sub(re.escape(short_name(name, ticker)), " ", title, flags=re.I)
        out.append({"title": title, "source": src, "date": when.date().isoformat(), "link": (it.findtext("link") or "").strip(),
                    "themes": [lab for lab, rx in THEMES if re.search(rx, bare, re.I)],
                    "tone": (1 if re.search(POS, title, re.I) else 0) - (1 if re.search(NEG, title, re.I) else 0)})
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


def summarize(name: str, ticker: str, items: list[dict], change_1m: Optional[float], price: Optional[float]) -> dict:
    nm = short_name(name, ticker)
    n = len(items)
    themes = Counter(t for i in items for t in i["themes"]).most_common()
    pos, neg = sum(1 for i in items if i["tone"] > 0), sum(1 for i in items if i["tone"] < 0)
    tone = ("mostly positive" if pos >= 2 * max(neg, 1) and pos >= 3 else "mostly negative" if neg >= 2 * max(pos, 1) and neg >= 3
            else "mixed" if pos + neg >= 3 else "mostly neutral")
    parts = []
    if change_1m is not None:
        move = "rose" if change_1m > 0.005 else "fell" if change_1m < -0.005 else "were flat"
        parts.append(f"Over the last 30 days {nm} shares {move}{f' {abs(change_1m):.0%}' if move != 'were flat' else ''}"
                     + (f" (now ${price:,.2f})" if price and "." not in ticker else "") + ".")
    if not n:
        parts.append("There was little news coverage in the past month.")
        return {"summary": " ".join(parts), "count": 0, "tone": "quiet", "themes": [], "items": [], "by": "rules"}
    flow = "heavy" if n >= 40 else "steady" if n >= 12 else "light"
    parts.append(f"News flow was {flow} ({n} stories) and the headlines were {tone} ({pos} upbeat, {neg} downbeat).")
    top = [(t, c) for t, c in themes if c >= 2 and t != "buy/sell opinion pieces"][:3]
    if top:
        parts.append("Most coverage was about " + ", ".join(f"{t} ({c})" for t, c in top[:-1])
                     + (" and " if len(top) > 1 else "") + f"{top[-1][0]} ({top[-1][1]}).")
    ana = [i for i in items if "analyst calls" in i["themes"]]
    if len(ana) >= 2:
        up = sum(1 for i in ana if re.search(r"upgrade|raise|boost|outperform|overweight|\bbuy\b", i["title"], re.I))
        dn = sum(1 for i in ana if re.search(r"downgrade|\bcut|lower|underperform|underweight|\bsell\b", i["title"], re.I))
        if up + dn >= 2:
            parts.append(f"Analyst calls leaned {'positive' if up > dn else 'negative' if dn > up else 'split'}: {up} upgrade or target-raise headline{'s' if up != 1 else ''} vs {dn} cut{'s' if dn != 1 else ''}.")
    op = sum(1 for i in items if "buy/sell opinion pieces" in i["themes"])
    if op >= max(3, n // 4):
        parts.append(f"{op} of the {n} were buy-or-sell opinion pieces, which show attention more than new facts.")
    ins = [i for i in items if "insider trades" in i["themes"]]
    sells = sum(1 for i in ins if re.search(r"\bsells?\b|\bsold\b|selling|unload|dump|withhold", i["title"], re.I))
    buys = sum(1 for i in ins if re.search(r"\bbuys?\b|bought|buying", i["title"], re.I))
    if sells or buys:
        parts.append(f"Insiders: {sells} selling and {buys} buying headline{'s' if sells + buys != 1 else ''}"
                     + (f", plus {len(ins) - sells - buys} other filing{'s' if len(ins) - sells - buys != 1 else ''}" if len(ins) > sells + buys else "")
                     + f" (latest: “{ins[0]['title']}”).")
    elif ins:
        parts.append(f"{len(ins)} insider filing{'s' if len(ins) != 1 else ''} (Form 4) were reported; check them for buying or selling.")
    # the most informative recent headline: hard news, never an opinion piece
    hard = ("earnings & guidance", "deals & partnerships", "legal & regulation", "management", "dividends & buybacks",
            "IPO & listing", "insider trades", "analyst calls", "stock moves")
    facts = [i for i in items if "buy/sell opinion pieces" not in i["themes"]] or items
    pool = [i for i in facts if not ins or i is not ins[0]] or facts
    TOP = r"reuters|bloomberg|cnbc|wall street journal|\bwsj\b|financial times|barron|marketwatch|associated press|business wire|pr ?newswire|globe ?newswire"
    hard_items = [i for i in pool if any(t in hard for t in i["themes"])]
    top_items = [i for i in hard_items if re.search(TOP, i["source"], re.I) or short_name(name, ticker).split()[0].lower() in i["source"].lower()]
    key = (top_items or hard_items or pool)[0]
    parts.append(f"Key headline: “{key['title']}” ({key['source']}, {key['date']}).")
    # up to 5 headlines to show: hard news first (one per top theme), opinion pieces only to fill
    pick, used = [key], {key["link"]}
    for t, _ in themes:
        if t == "buy/sell opinion pieces":
            continue
        h = next((i for i in facts if t in i["themes"] and i["link"] not in used), None)
        if h:
            pick.append(h); used.add(h["link"])
        if len(pick) >= 4:
            break
    for i in facts + items:
        if len(pick) >= 5:
            break
        if i["link"] not in used:
            pick.append(i); used.add(i["link"])
    pick.sort(key=lambda x: x["date"], reverse=True)
    return {"summary": " ".join(parts), "count": n, "tone": tone, "positive": pos, "negative": neg,
            "themes": [[t, c] for t, c in themes[:5]], "items": [{k: i[k] for k in ("title", "source", "date", "link")} for i in pick],
            "by": "rules"}


def month_change(ticker: str) -> Optional[float]:
    try:
        import yfinance as yf
        closes = yf.Ticker(ticker).history(period="1mo", auto_adjust=True)["Close"].dropna()
        return float(closes.iloc[-1] / closes.iloc[0] - 1) if len(closes) >= 2 else None
    except Exception:
        return None


def build_news(name: str, ticker: str, price: Optional[float] = None) -> Optional[dict]:
    """Network call: fetch, parse and summarize. Returns None if the feed can't be read."""
    try:
        items = parse_feed(fetch_feed(name, ticker), name, ticker)
    except Exception:
        return None
    out = summarize(name, ticker, items, month_change(ticker), price)
    ai = _gemini_paragraph(name, ticker, items, out)
    if ai:
        out["rules_summary"], out["summary"], out["by"] = out["summary"], ai, "gemini"
    out["updated"] = datetime.now(timezone.utc).date().isoformat()
    return out


def _gemini_paragraph(name, ticker, items, rules) -> Optional[str]:
    if not items:
        return None
    from memo import gemini_text
    heads = "\n".join(f"- {i['date']} | {i['source']} | {i['title']}" for i in items[:45])
    prompt = (f"Summarize the past month of news for {name} ({ticker}) for a long-term investor in ONE paragraph of 60-100 words. "
              "Plain words, no hype, no advice. Use ONLY facts stated in these headlines and this price note; do not invent numbers, "
              "and say 'reportedly' for anything uncertain. Mention the main storylines and anything that could change the long-term case.\n\n"
              f"Price note: {rules['summary'].split('.')[0]}.\nHeadlines:\n{heads}")
    return gemini_text(prompt)
