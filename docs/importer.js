/*
 * Long-Term Lab: portfolio importer. Reads holdings out of almost any file.
 *
 * DISCLAIMER: Independent personal project. Not tied to any employer or agency.
 * Files are read inside the browser and never uploaded. Not financial advice.
 *
 * How it reads (in this order, for every file type):
 *   1. TABLES BY COLUMN: find a header row (Symbol / Qty / Price / Market value / Avg cost ...)
 *      and read each row by column position. Works for CSV/Excel/Word/HTML tables and, using the
 *      x-position of each word, for PDF statements and screenshots.
 *   2. JSON: any list of objects with a symbol-like and a quantity-like field (broker exports,
 *      Alpaca/Robinhood-style API dumps, this site's own backup).
 *   3. TEXT LINES (fallback): a ticker followed by numbers. Labels help ("10 shares", "@ 150",
 *      "cost 120", "value 1,500"); without labels it looks for three numbers where
 *      shares x price = value, which pins down which number is which.
 * Every row gets a confidence (high / medium / low) and a reason, so the review screen can say
 * what to double-check. Option contracts, cash, totals and fine print are skipped and listed.
 *
 * Pure functions (no DOM): works in the browser (window.Importer) and in Node for tests.
 */
(function (root) {
  'use strict';

  // Words that look like tickers but are not (headers, legal fine print, broker boilerplate).
  const STOP = new Set(('USD CASH TOTAL TOTALS ETF INC CORP CO LLC LTD THE AND FOR OF ACCT ACCOUNT PAGE NA N A I AM PM ' +
    'YTD QTY US DATE BUY SELL NET GAIN LOSS VALUE PRICE DAY MKT SYMBOL SHARES IRA ROTH EST TAX ID NO CUSIP CLASS CL ' +
    'SHS COM ORD ADR NEW FUND TRUST MONEY MARKET SPAXX FDRXX DIV REINV PCT YES OR AS AT ON IN BY TO IS IT BE ' +
    'SIPC FINRA FDIC IRS APY SEC ACH DCF RHS RHF RAM INT BTO STO BTC STC DRIP NAV ADJ AVG CUR QTR EPS APR FAQ ' +
    'LLC NYSE NASDAQ OTC LP PLC SA AG NV DTC CEO CFO').split(/\s+/));
  // Lines that are legal text, addresses or account plumbing, never holdings.
  const FINE_PRINT = /\b(sipc|finra|fdic|member of|insured|insurance|securities investor protection|page \d+ of|statement period|account (number|#)|routing|suite \d+|p\.?o\.? box|apy|interest rate|sweep|disclosure|prospectus|1099|cusip:)\b/i;
  const OPTION = /\b(call|put)s?\b.*\$?\d|\d{1,2}\/\d{1,2}\/\d{2,4}.*\b(call|put)s?\b|\b[A-Z]{1,5}\d{6}[CP]\d{8}\b/i;
  const CASHLIKE = /^(cash|cash & cash investments|cash and cash equivalents|money market|sweep|pending activity|total|account total|grand total|subtotal)\b/i;

  const isTicker = t => /^[A-Z]{1,5}(?:[.\-][A-Z]{1,2})?$/.test(t) && !STOP.has(t);
  const yahoo = t => t.toUpperCase().replace(/\.(?=[A-Z]{1,2}$)/, '-');          // BRK.B -> BRK-B
  const cleanTok = t => String(t || '').replace(/[*:,;()\[\]]/g, '').trim();

  /** "$1,234.50" -> 1234.5 ; "(12.5)" -> -12.5 ; "12%" -> null (percent is never shares/price/value) */
  function toNum(v) {
    if (typeof v === 'number') return isFinite(v) ? v : null;
    const s = String(v ?? '').trim();
    if (!s || /%$/.test(s)) return null;
    const t = s.replace(/[$€£₹,\s]/g, '').replace(/^USD/i, '');
    if (!/^[-+(]?\d*\.?\d+\)?$/.test(t)) return null;
    const neg = /^\(.*\)$/.test(t) || t.startsWith('-');
    const n = parseFloat(t.replace(/[()\-+]/g, ''));
    return isFinite(n) ? (neg ? -n : n) : null;
  }
  const isMoneyTok = s => /^\(?-?[$€£₹]/.test(String(s).trim());
  const close = (a, b, tol = 0.025) => a > 0 && b > 0 && Math.abs(a - b) / Math.max(a, b) <= tol;

  /** Fill price/value from each other, score confidence and say why. */
  function finish(r) {
    const out = { ticker: yahoo(r.ticker), acct: r.acct || '', shares: r.shares, price: r.price ?? null, cost: r.cost ?? null,
                  value: r.value ?? null, desc: (r.desc || '').trim(), src: r.src };
    if (out.price == null && out.value != null && out.shares > 0) out.price = +(out.value / out.shares).toFixed(4);
    if (out.value == null && out.price != null) out.value = +(out.price * out.shares).toFixed(2);
    let conf = r.conf || 'medium', why = r.why || '';
    if (r.price != null && r.value != null) {
      if (close(r.shares * r.price, r.value)) { conf = 'high'; why = why || 'shares × price = value'; }
      else { conf = 'low'; why = 'shares × price ≠ value: check shares'; }
    }
    out.conf = conf; out.why = why;
    return out;
  }

  /** Only the last 4 characters of an account number are ever kept ("Z26954116" -> "4116"). */
  const lastDigits = v => { const t = String(v || '').replace(/[^A-Za-z0-9]/g, ''); return t.length >= 4 ? t.slice(-4) : ''; };
  const BROKERS = [['Fidelity', /fidelity/i], ['Robinhood', /robinhood/i], ['Schwab', /schwab/i], ['Vanguard', /vanguard brokerage|vanguard\.com/i],
    ['E*TRADE', /e\*trade|etrade/i], ['Merrill', /merrill/i], ['Webull', /webull/i], ['Interactive Brokers', /interactive brokers/i], ['Public', /public\.com/i], ['SoFi', /sofi invest/i], ['Alpaca', /alpaca/i]];
  /** Which broker a file came from, from its text (fine print usually names it). */
  function guessBroker(text) { for (const [n, re] of BROKERS) if (re.test(text)) return n; return ''; }

  // ───────────────────────── 1. tables by column ─────────────────────────
  const COLS = {
    ticker: [/^(symbol|ticker|sym)\b/, /sym\s*\/\s*cusip|symbol\s*\/\s*cusip/, /security symbol|stock symbol|^code$/],
    shares: [/^(quantity|qty|shares|units)\b/, /\b(quantity|qty|shares held|no\.? of shares|units)\b/, /^position$/],
    price: [/^(last|current|market|closing|recent)?\s*price\b(?!.*(change|paid|purchase|avg|average))/, /last price|current price|market price|closing price|price per share/],
    value: [/^(market|mkt|current|total)?\s*val(ue)?\b/, /market value|mkt\.? val(ue)?|current value|position value|total value|equity/],
    cost: [/(avg|average).*(cost|price)|cost.*(per|\/)\s*(share|unit)|unit cost|purchase price|price paid|avg\.? cost/],
    costTotal: [/^cost basis|total cost|^cost$|^basis$|cost basis total/],
    desc: [/^(description|security|security name|name|holding|instrument|investment|securities held)/],
    acct: [/^(account|acct)\.?\s*(number|no\.?|#)$|^account$/],
  };
  function classifyHeader(cell) {
    const c = String(cell || '').toLowerCase().replace(/\s+/g, ' ').trim();
    if (!c) return null;
    for (const k of ['acct', 'cost', 'costTotal', 'ticker', 'shares', 'price', 'value', 'desc'])
      if (COLS[k].some(re => re.test(c))) return k;
    return null;
  }
  // Columns that mean "history of trades / lending", not "what I own now".
  const ACTIVITY = /\b(transaction|debit|credit|trade date|settle(ment)? date|activity|action|lent|loaned|returned|buy\/sell)\b/i;
  /** Returns {field:index} if this row looks like a holdings header, {activity:true} for a trade-history header. */
  function headerOf(cells) {
    const map = {};
    const nonEmpty = cells.filter(c => String(c || '').trim()).length;
    if (nonEmpty >= 3 && cells.filter(c => ACTIVITY.test(String(c || ''))).length && cells.some(c => classifyHeader(c) === 'shares'))
      return { activity: true };
    cells.forEach((c, i) => { const k = classifyHeader(c); if (k && map[k] == null) map[k] = i; });
    const hasQty = map.shares != null;
    const hasId = map.ticker != null || map.desc != null;
    const extra = ['price', 'value', 'cost', 'costTotal'].filter(k => map[k] != null).length;
    return hasQty && hasId && (map.ticker != null || extra >= 1) ? map : null;
  }
  function tickerFrom(cell, desc) {
    const t = cleanTok(String(cell || '').toUpperCase().split(/[\s\/]/)[0]);
    if (isTicker(t)) return t;
    const m = String(desc || '').match(/\(([A-Z]{1,5}(?:[.\-][A-Z]{1,2})?)\)/);   // "Apple Inc (AAPL)"
    return m && isTicker(m[1]) ? m[1] : null;
  }
  /**
   * rows: array of arrays of cell strings (a sheet, a Word/HTML table, or column-aligned PDF lines).
   * Handles several holdings sections (multi-page statements); a header can appear anywhere.
   */
  function fromTables(tables, src = 'table') {
    const out = [], skipped = [];
    for (const t of tables) {
      const rows = t.map(r => r.map(c => String(c ?? '').trim()));
      let map = null, blanks = 0;
      for (const r of rows) {
        const h = headerOf(r);
        if (h) { map = h.activity ? null : h; blanks = 0; continue; }
        if (!map) continue;
        const line = r.join(' ').trim();
        if (!line) { if (++blanks > 3) map = null; continue; }
        blanks = 0;
        const desc = map.desc != null ? r[map.desc] : '';
        if (OPTION.test(line)) { skipped.push({ text: line, reason: 'option contract (not a stock holding)' }); continue; }
        if (CASHLIKE.test(desc || r[map.ticker] || '')) { skipped.push({ text: line, reason: 'cash or total line' }); continue; }
        const tk = tickerFrom(map.ticker != null ? r[map.ticker] : '', desc);
        const sh = toNum(r[map.shares]);
        if (!tk || !(sh > 0)) { if (tk || sh) skipped.push({ text: line, reason: 'no usable symbol or share count' }); continue; }
        const px = map.price != null ? toNum(r[map.price]) : null, mv = map.value != null ? toNum(r[map.value]) : null;
        if (px > 0 && mv > 0 && close(sh * px * 100, mv, 0.01) && !close(sh * px, mv)) {   // 1 contract = 100 shares
          skipped.push({ text: line, reason: 'option contract (value = qty × price × 100)' }); continue; }
        let cost = map.cost != null ? toNum(r[map.cost]) : null;
        if (cost == null && map.costTotal != null) { const ct = toNum(r[map.costTotal]); if (ct > 0) cost = +(ct / sh).toFixed(4); }
        out.push(finish({ ticker: tk, shares: sh, price: px, value: mv, cost: cost > 0 ? cost : null, desc,
          acct: map.acct != null ? lastDigits(r[map.acct]) : '', src, conf: 'high', why: 'read from a table with column headers' }));
      }
    }
    return { rows: out, skipped };
  }

  /**
   * PDF pages / OCR words -> column-aligned rows. items: [{str, x, y, w}] per page (y grows upward for PDF;
   * pass yDown=true for OCR where y grows downward). Words close together on a line are joined into cells.
   */
  function linesFromItems(items, yDown = false) {
    const rows = {};
    for (const it of items) {
      if (!String(it.str || '').trim()) continue;
      const key = Math.round((yDown ? -it.y : it.y) / 3);
      (rows[key] = rows[key] || []).push(it);
    }
    return Object.keys(rows).map(Number).sort((a, b) => b - a).map(k => {
      const its = rows[k].sort((a, b) => a.x - b.x), cells = [];
      for (const it of its) {
        const last = cells[cells.length - 1];
        const gap = last ? it.x - (last.x + last.w) : Infinity;
        const size = Math.max(4, (it.h || 10) * 0.9);
        if (last && gap < size) { last.str += (gap > 1 ? ' ' : '') + it.str.trim(); last.w = it.x + (it.w || 0) - last.x; }
        else cells.push({ str: it.str.trim(), x: it.x, w: it.w || it.str.length * 5 });
      }
      return cells;
    });
  }
  /** Column-aligned lines -> table rows: cells are assigned to the nearest header column by x position. */
  function fromItemLines(lines, src) {
    const tables = []; let cur = null, cols = null;
    for (const cells of lines) {
      const h = headerOf(cells.map(c => c.str));
      if (h && h.activity) { cur = null; continue; }
      if (h) { cols = cells.map(c => c.x + c.w / 2); cur = [cells.map(c => c.str)]; tables.push(cur); continue; }
      if (!cur) continue;
      const row = new Array(cols.length).fill('');
      for (const c of cells) {
        // left edge for text columns, centre for numbers (numbers are often right-aligned)
        const cx = toNum(c.str) != null ? c.x + c.w / 2 : c.x + Math.min(c.w, 30) / 2;
        let bi = 0, bd = Infinity;
        cols.forEach((x, i) => { const d = Math.abs(x - cx); if (d < bd) { bd = d; bi = i; } });
        row[bi] = row[bi] ? row[bi] + ' ' + c.str : c.str;
      }
      cur.push(row);
    }
    return fromTables(tables, src);
  }

  // ───────────────────────── 2. JSON ─────────────────────────
  const JKEYS = {
    ticker: ['ticker', 'symbol', 'sym', 'instrument_symbol', 'code', 'stock'],
    shares: ['shares', 'quantity', 'qty', 'units', 'position', 'shares_owned'],
    price: ['price', 'current_price', 'last_price', 'market_price', 'lastprice', 'close'],
    cost: ['cost', 'average_cost', 'avg_cost', 'average_buy_price', 'avg_entry_price', 'cost_per_share', 'averagecost', 'average_price'],
    costTotal: ['cost_basis', 'total_cost', 'costbasis'],
    value: ['value', 'market_value', 'equity', 'current_value', 'marketvalue'],
    desc: ['name', 'description', 'desc', 'security_name', 'title'],
  };
  function pick(o, keys) {
    for (const k of Object.keys(o)) if (keys.includes(k.toLowerCase())) return o[k];
    return undefined;
  }
  function fromJSON(data) {
    const out = [], skipped = [], seen = new Set();
    const visit = v => {
      if (!v || typeof v !== 'object' || seen.has(v)) return; seen.add(v);
      if (Array.isArray(v)) {
        for (const o of v) {
          if (o && typeof o === 'object' && !Array.isArray(o)) {
            let tk = pick(o, JKEYS.ticker); if (tk && typeof tk === 'object') tk = pick(tk, JKEYS.ticker);
            if (tk == null) for (const v2 of Object.values(o))           // {instrument:{symbol:'AMZN'}, quantity:4}
              if (v2 && typeof v2 === 'object' && !Array.isArray(v2) && typeof pick(v2, JKEYS.ticker) === 'string') { tk = pick(v2, JKEYS.ticker); break; }
            const sh = toNum(pick(o, JKEYS.shares));
            if (tk != null && sh != null) {
              const t = cleanTok(String(tk).toUpperCase());
              if (isTicker(t) && sh > 0) {
                let cost = toNum(pick(o, JKEYS.cost));
                if (cost == null) { const ct = toNum(pick(o, JKEYS.costTotal)); if (ct > 0) cost = +(ct / sh).toFixed(4); }
                const ac = String(pick(o, ['acct', 'account', 'account_number', 'account_id']) ?? '');
                out.push(finish({ ticker: t, acct: /[\s·]/.test(ac) ? ac : lastDigits(ac), shares: sh, price: toNum(pick(o, JKEYS.price)), value: toNum(pick(o, JKEYS.value)),
                  cost: cost > 0 ? cost : null, desc: String(pick(o, JKEYS.desc) || ''), src: 'json', conf: 'high', why: 'read from named fields' }));
                continue;
              }
              skipped.push({ text: JSON.stringify(o).slice(0, 80), reason: 'not a stock symbol or no shares' });
            }
          }
          visit(o);
        }
      } else Object.values(v).forEach(visit);
    };
    visit(data);
    return { rows: out, skipped };
  }

  // ───────────────────────── 3. text lines ─────────────────────────
  const LABEL = {
    shares: /^(shares?|sh|shs|units?|qty)$/i,
    price: /^(@|price:?|last:?|at)$/i,
    cost: /^(cost:?|avg:?|average:?)$/i,
    value: /^(value:?|mkt:?|market:?|equity:?|worth:?)$/i,
  };
  // Phone apps show a card: "NVDA        $228.38" then "1.03 shares" on the next line. Join those.
  function joinCards(lines) {
    const L = lines.map(l => String(l).replace(/\s+/g, ' ').trim()).filter(Boolean), out = [];
    const hasTicker = l => l.split(' ').some(x => isTicker(cleanTok(x)));
    for (const l of L) {
      const prev = out[out.length - 1];
      if (prev && !hasTicker(l) && /^\$?[\d.,]+\s*(shares?|sh|shs|units?)\b/i.test(l) && hasTicker(prev) && !/\b(shares?|sh|shs|units?)\b/i.test(prev))
        out[out.length - 1] = prev + ' ' + l;
      else out.push(l);
    }
    return out;
  }
  function fromText(lines, src = 'text') {
    const out = [], skipped = [];
    for (const raw of joinCards(lines)) {
      const line = String(raw).replace(/\s+/g, ' ').trim();
      if (!line) continue;
      if (FINE_PRINT.test(line)) continue;
      const toks = line.split(' ');
      const ti = toks.findIndex(x => isTicker(cleanTok(x)));
      if (ti < 0) continue;
      if (OPTION.test(line)) { skipped.push({ text: line, reason: 'option contract (not a stock holding)' }); continue; }
      const ticker = cleanTok(toks[ti]);
      // numbers after the ticker, with the word before/after them as a label
      const nums = [];
      for (let k = ti + 1; k < toks.length; k++) {
        const n = toNum(toks[k]);
        if (n == null || n <= 0) continue;
        if (Number.isInteger(n) && n >= 1900 && n <= 2100 && !isMoneyTok(toks[k])) continue;      // years
        const before = (toks[k - 1] || '').toLowerCase(), after = (toks[k + 1] || '').toLowerCase();
        const before2 = ((toks[k - 2] || '') + ' ' + before).toLowerCase();
        let label = null;
        if (LABEL.shares.test(after)) label = 'shares';
        else if (LABEL.price.test(before)) label = 'price';
        else if (LABEL.cost.test(before) || /avg cost|average cost|avg\. cost|cost basis/.test(before2)) label = /basis/.test(before2) ? 'costTotal' : 'cost';
        else if (LABEL.value.test(before) || /market value/.test(before2)) label = 'value';
        nums.push({ n, label, money: isMoneyTok(toks[k]) });
      }
      if (!nums.length) continue;
      const r = { ticker, src, desc: toks.slice(0, ti).join(' ') };
      for (const x of nums) if (x.label && r[x.label] == null) r[x.label] = x.n;
      let free = nums.filter(x => !x.label);
      if (r.costTotal != null) { r.costTotal = r.costTotal; }
      if (r.shares == null) {
        // three numbers where a x b ~= c: shares, price, value (shares is usually the non-money one)
        let found = null;
        for (let i = 0; i < free.length && !found; i++) for (let j = 0; j < free.length && !found; j++) for (let k = 0; k < free.length && !found; k++)
          if (i !== j && j !== k && i !== k && close(free[i].n * free[j].n, free[k].n, 0.015) && !free[i].money) found = [i, j, k];
        if (found) {
          r.shares = free[found[0]].n; r.price = r.price ?? free[found[1]].n; r.value = r.value ?? free[found[2]].n;
          r.conf = 'high'; r.why = 'shares × price = value';
          free = free.filter((_, z) => !found.includes(z));
        } else {
          const first = free.find(x => !x.money);              // a $ amount is never a share count
          if (!first) { skipped.push({ text: line, reason: 'symbol found but no share count' }); continue; }
          r.shares = first.n; free = free.filter(x => x !== first);
        }
      } else if (r.price == null && r.value == null && free.length >= 2) {
        for (let j = 0; j < free.length; j++) for (let k = 0; k < free.length; k++)
          if (j !== k && r.price == null && close(r.shares * free[j].n, free[k].n, 0.015)) { r.price = free[j].n; r.value = free[k].n; }
      }
      if (r.costTotal != null && r.cost == null && r.shares > 0) r.cost = +(r.costTotal / r.shares).toFixed(4);
      if (!(r.shares > 0) || r.shares > 1e7) continue;
      if (r.cost == null && r.price == null && r.value == null && free.length === 1) {
        if (free[0].money) { r.price = free[0].n; r.conf = 'low'; r.why = 'dollar amount taken as price: check it is not total value'; }
        else { r.cost = free[0].n; r.conf = 'low'; r.why = 'second number taken as cost per share: check it'; }   // legacy "TICKER shares cost"
      }
      if (!r.conf) { r.conf = (r.price != null || r.value != null || r.cost != null) ? 'medium' : 'low';
                     r.why = r.why || (r.conf === 'medium' ? 'read from labelled numbers' : 'only shares found'); }
      out.push(finish(r));
    }
    return { rows: out, skipped };
  }

  /** Same ticker found more than once (several accounts or pages): shares added, cost share-weighted. */
  function mergeRows(rows) {
    const m = new Map(), rank = { high: 3, medium: 2, low: 1 };
    for (const r of rows) {
      const k = r.ticker + '|' + (r.acct || '');      // same stock in two accounts stays two lots
      if (!m.has(k)) { m.set(k, { ...r, accounts: 1 }); continue; }
      const a = m.get(k), sh = a.shares + r.shares;
      const cost = (a.cost != null && r.cost != null) ? (a.cost * a.shares + r.cost * r.shares) / sh : (a.cost ?? r.cost);
      m.set(k, { ...a, shares: +sh.toFixed(6), cost: cost != null ? +cost.toFixed(4) : null, price: a.price ?? r.price,
        value: (a.value != null && r.value != null) ? +(a.value + r.value).toFixed(2) : (a.value ?? r.value),
        desc: a.desc || r.desc, accounts: a.accounts + 1, conf: rank[a.conf] <= rank[r.conf] ? a.conf : r.conf,
        why: (a.why || '') + ' · merged from ' + (a.accounts + 1) + ' lines' });
    }
    return [...m.values()];
  }

  /**
   * Main entry for parsed content. Pass whatever the file gave:
   *   {tables}  arrays of rows (sheets, Word/HTML tables)
   *   {items}   positioned words per page [{str,x,y,w,h}] (PDF, OCR) ; {yDown:true} for OCR
   *   {lines}   plain text lines
   *   {json}    parsed JSON
   * Strategy: the most structured reader that finds holdings wins; text lines are the fallback.
   */
  function extract(input) {
    const tries = [];
    if (input.json !== undefined) tries.push(fromJSON(input.json));
    if (input.tables && input.tables.length) tries.push(fromTables(input.tables, input.src || 'table'));
    if (input.items && input.items.length) {
      const lines = input.items.flatMap(page => linesFromItems(page, input.yDown));
      tries.push(fromItemLines(lines, input.src || 'pdf'));
      if (!input.lines) input.lines = lines.map(cells => cells.map(c => c.str).join(' '));
    }
    let best = tries.find(t => t.rows.length);
    if (!best && input.lines) best = fromText(input.lines, input.src || 'text');
    best = best || { rows: [], skipped: [] };
    const skipped = [...new Map(tries.concat(best).flatMap(t => t.skipped).map(s => [s.text, s])).values()];
    const text = [].concat(input.lines || [], (input.tables || []).flat().map(r => [].concat(r).join(' '))).join('\n');
    return { rows: mergeRows(best.rows), skipped, broker: guessBroker(text) };
  }

  const api = { extract, guessBroker, lastDigits, fromTables, fromText, fromJSON, fromItemLines, linesFromItems, mergeRows, toNum, isTicker, headerOf };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Importer = api;
})(typeof window !== 'undefined' ? window : globalThis);
