// extract.js — pulls upcoming-IPO numbers out of text: a copied IPO page (Chittorgarh, Groww, Zerodha,
// news), a prospectus (RHP / S-1) PDF, a Word file or a screenshot. Runs in the browser; nothing is uploaded.
// Independent personal project, not tied to any employer or agency. Public and synthetic data only,
// no internal or personal data (no SSNs/PHI). Educational research, not financial advice.
//
// extractIpo(text, {name, url}) -> {ipo, found: [field...], missing: [field...], warnings: [text...]}
// It is a best-effort reader: every number goes into the edit form so you can check it.

(function (root) {
const MON = {jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12};
const MONRX = '(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\\.?';
const DATE = `(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\\s*)?(?:(\\d{1,2})(?:st|nd|rd|th)?\\s+(${MONRX}),?\\s+(\\d{4})|(${MONRX})\\s+(\\d{1,2})(?:st|nd|rd|th)?,?\\s+(\\d{4}))`;
const CURSYM = '(?:₹|Rs\\.?|INR|US\\$|\\$|USD|€|£)';
const SCALE = {crore: 1e7, cr: 1e7, crores: 1e7, lakh: 1e5, lakhs: 1e5, lac: 1e5, million: 1e6, millions: 1e6, mn: 1e6, m: 1e6,
               billion: 1e9, billions: 1e9, bn: 1e9, b: 1e9, thousand: 1e3, thousands: 1e3, k: 1e3};
const UNITF = {crore: 1e7, million: 1e6, billion: 1e9, lakh: 1e5, thousand: 1e3};
const NUM = s => { const t = String(s).replace(/,/g, ''); const neg = /^\(.*\)$/.test(t) || t.startsWith('-'); const n = parseFloat(t.replace(/[()\-]/g, '')); return isFinite(n) ? (neg ? -n : n) : null; };
const iso = (y, m, d) => `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
function dateFrom(m, off = 1){             // m = match array where DATE's 6 groups start at index `off`
  if (!m) return null;
  const [d1, m1, y1, m2, d2, y2] = m.slice(off, off + 6);
  const mon = MON[(m1 || m2 || '').slice(0, 3).toLowerCase()], day = +(d1 || d2), yr = +(y1 || y2);
  return mon && day && yr ? iso(yr, mon, day) : null;
}

function extractIpo(raw, opts = {}){
  const text = String(raw || '').replace(/ /g, ' ').replace(/\r/g, '').replace(/[ \t]+/g, ' ');
  const flat = text.replace(/\s*\n\s*/g, ' ');          // one long line, but labels still separated
  const o = {}, found = [], warnings = [];
  const set = (k, v) => { if (v != null && v !== '' && !(typeof v === 'number' && !isFinite(v))){ o[k] = v; found.push(k); } };
  const first = (rx, s = flat) => { const m = s.match(rx); return m || null; };

  // ── Currency and units ──
  const inr = /₹|\bRs\.?\s?\d|\bINR\b|\bcrores?\b|\blakhs?\b|\bNSE\b|\bBSE\b/i.test(flat);
  o.currency = inr ? 'INR' : /€/.test(flat) && !/\$/.test(flat) ? 'EUR' : /£/.test(flat) && !/\$/.test(flat) ? 'GBP' : 'USD';
  o.unit = inr ? 'crore' : 'million';
  const U = UNITF[o.unit];
  const toU = (n, word) => {                    // amount with an optional scale word -> o.unit
    if (n == null) return null;
    const f = word ? SCALE[word.toLowerCase().replace(/\.$/, '')] : null;
    if (f) return n * f / U;
    return n >= 1e7 ? n / U : n;               // a bare big number is an absolute amount
  };
  const shareU = (n, word) => n == null ? null : word && SCALE[word.toLowerCase()] ? n * SCALE[word.toLowerCase()] / U : n / U;
  // first currency amount within `win` characters after a label match
  const moneyAfter = (labelRx, win = 140) => {
    const rx = new RegExp(labelRx.source, 'gi'); let m;
    while ((m = rx.exec(flat))){
      const seg = flat.slice(m.index + m[0].length, m.index + m[0].length + win);
      // skip per-share prices ("₹1,065 to ₹1,119 per share"); prefer amounts with a scale word
      const arx = new RegExp(`${CURSYM}\\s?([\\d,]+(?:\\.\\d+)?)\\s*(crores?|cr\\b\\.?|lakhs?|million|mn\\b|billion|bn\\b)?(\\s*(?:to\\b|-|–|per\\s+share))?`, 'gi'); let a;
      while ((a = arx.exec(seg))) if (a[2] || (!a[3] && NUM(a[1]) >= 1e5)) return toU(NUM(a[1]), a[2]);
    }
    return null;
  };

  // ── Name ──
  if (opts.name) set('name', opts.name.trim());
  else {
    const counts = {}; let m; const rx = /((?:[A-Z][A-Za-z0-9&.'-]*\s){0,4}[A-Z][A-Za-z0-9&.'-]*)\s+IPO\b/g;
    while ((m = rx.exec(flat))){ const n = m[1].replace(/^(?:The|About|Upcoming|Latest|Mainboard|SME|Check|Apply)\s+/, '').trim(); if (n.length > 2) counts[n] = (counts[n] || 0) + 1; }
    const best = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
    if (best) set('name', best[0].replace(/\s+(?:Ltd\.?|Limited|Inc\.?)$/, ''));
    else if ((m = first(/([A-Z][A-Za-z0-9&-]*(?:\s[A-Z][A-Za-z0-9&-]*){0,4}),?\s+(?:Inc\.|Corp\.|Corporation|Limited|Ltd\.|plc|N\.V\.|S\.A\.|Holdings)/))) set('name', m[1]);
  }

  // ── Price band and lot ──
  let m;
  m = first(new RegExp(`price\\s*(?:band|range)[^\\d]{0,40}?([\\d,]+(?:\\.\\d+)?)\\s*(?:to|-|–|and)\\s*${CURSYM}?\\s?([\\d,]+(?:\\.\\d+)?)`, 'i'))
       || first(new RegExp(`between\\s+${CURSYM}\\s?([\\d,]+(?:\\.\\d+)?)\\s+and\\s+${CURSYM}\\s?([\\d,]+(?:\\.\\d+)?)\\s+per\\s+share`, 'i'));
  if (m){ const a = NUM(m[1]), b = NUM(m[2]); if (a && b && b >= a && b / a < 1.5){ set('price_low', a); set('price_high', b); } }
  else if ((m = first(new RegExp(`(?:issue|offer)\\s*price[^\\d]{0,20}?([\\d,]+(?:\\.\\d+)?)\\s*per\\s*share`, 'i')))){ set('price_low', NUM(m[1])); set('price_high', NUM(m[1])); }
  m = first(/(?:lot size|market lot|minimum (?:order quantity|bid(?: lot)?|lot))[^\d]{0,20}([\d,]+)\s*(?:shares|equity)?/i) || first(/\/\s*([\d,]+)\s*shares/i);
  if (m) set('lot_size', NUM(m[1]));

  // ── Dates ──
  const dateAfter = (labelRx, win = 40) => {
    const rx = new RegExp(labelRx.source, 'gi'); let mm;
    while ((mm = rx.exec(flat))){
      const seg = flat.slice(mm.index + mm[0].length, mm.index + mm[0].length + win);
      const d = seg.match(new RegExp(DATE, 'i')); if (d) return dateFrom(d);
    }
    return null;
  };
  set('open_date', dateAfter(/(?:IPO|Issue|Subscription|Bid(?:ding)?|Offer)\s*(?:Open(?:s|ing)?|Start(?:s)?)(?:\s*Date)?|opened for subscription on|opens on/));
  set('close_date', dateAfter(/(?:IPO|Issue|Subscription|Bid(?:ding)?|Offer)\s*(?:Close(?:s)?|Closing|End(?:s)?)(?:\s*Date)?|will close on|closes on/));
  set('listing_date', dateAfter(/(?:Tentative\s*)?Listing(?:\s*Date)?(?:\s*fixed)?(?:\s*(?:as|on))?|Listing on (?:the )?(?:NSE|BSE|Nasdaq|NYSE)[A-Za-z ,&]{0,20}/));
  set('lockup_end', dateAfter(/lock-?in[^.]{0,70}?(?:50%|half)[^)]{0,40}\)?/, 45));
  set('lockup_end_2', dateAfter(/lock-?in[^.]{0,70}?remaining[^)]{0,40}\)?/, 45));
  if (o.close_date && o.open_date && o.close_date < o.open_date){ delete o.close_date; found.splice(found.indexOf('close_date'), 1); }

  // ── Offer size ──
  set('issue_size', moneyAfter(/(?:total\s*)?issue\s*size|(?:book[- ]?build(?:ing)?|fixed[- ]price)\s*issue\s*of/));
  set('fresh_issue', moneyAfter(/fresh\s*issue/));
  if (/(?:entirely|only|purely)\s+(?:a\s+)?fresh\s+(?:issue|capital)|fresh\s+capital\s+only|no\s+offer\s+for\s+sale|offer\s+for\s+sale\s*(?:\(OFS\))?\s*:?\s*(?:not applicable|nil|n\/?a\b|none)/i.test(flat)) set('ofs', 0);
  else set('ofs', moneyAfter(/offer\s*for\s*sale/));
  // US prospectus: "We are offering 20,000,000 shares", "selling stockholders are offering 5,000,000 shares"
  m = first(/(?:we\s+are|company\s+is)\s+offering\s+([\d,]{5,})\s+shares/i);
  if (m && o.fresh_shares == null) set('fresh_shares', shareU(NUM(m[1])));
  const sell = first(/selling\s+(?:stock|share)holders?\s+(?:are\s+)?offering\s+([\d,]{5,})\s+shares/i);
  if (o.price_high && o.fresh_shares != null && o.fresh_issue == null){ set('fresh_issue', o.fresh_shares * o.price_high); warnings.push('Issue size worked out as new shares x top of the price range.'); }
  if (o.price_high && sell && o.ofs == null) set('ofs', shareU(NUM(sell[1])) * o.price_high);
  else if (o.currency === 'USD' && o.fresh_issue != null && o.ofs == null && !/selling\s+(?:stock|share)holders/i.test(flat)) set('ofs', 0);
  if (o.issue_size == null && o.fresh_issue != null && o.ofs != null) set('issue_size', o.fresh_issue + o.ofs);
  if (o.fresh_issue == null && o.issue_size != null && o.ofs === 0) set('fresh_issue', o.issue_size);
  m = first(/fresh\s*issue\s*(?:of\s*)?(?:up\s*to\s*)?([\d,]+(?:\.\d+)?)\s*(crore|lakh|million|billion)?\s*(?:equity\s*)?shares/i);
  if (m) set('fresh_shares', shareU(NUM(m[1]), m[2]));
  m = first(/(?:share\s*holding|shares)\s*post[- ]issue[^\d]{0,15}([\d,]{6,})/i) || first(/outstanding\s+(?:immediately\s+)?after\s+(?:this|the)\s+offering[^\d]{0,40}([\d,]{6,})/i)
    || first(/([\d,]{6,})\s+shares\s+of\s+(?:our\s+)?(?:Class\s+A\s+)?common\s+stock\s+(?:will\s+be\s+)?outstanding\s+(?:immediately\s+)?after/i);
  if (m) set('shares_post', shareU(NUM(m[1])));
  const mcapRx = new RegExp(`market\\s*cap(?:italization|italisation)?[^₹$\\d]{0,40}${CURSYM}\\s?([\\d,]+(?:\\.\\d+)?)\\s*(crores?|cr\\b\\.?|million|mn\\b|billion|bn\\b)?`, 'gi');
  let mc = null; while ((m = mcapRx.exec(flat))) mc = toU(NUM(m[1]), m[2]);   // last one = post-issue / upper band on most pages
  if (mc && o.price_high){
    if (o.shares_post == null){ set('shares_post', mc / o.price_high); warnings.push('Shares after the IPO were worked out from the stated market cap at the top of the band.'); }
    else if (Math.abs(o.shares_post * o.price_high / mc - 1) > 0.15) warnings.push(`The page's market cap (${Math.round(mc).toLocaleString()} ${o.unit}) doesn't match shares x price; check the share count.`);
  }
  m = first(/promoters?(?:\s+(?:and|&)\s+promoter\s+group)?[^%\d]{0,60}?([\d.]+)\s*%\s*([\d.]+)\s*%/i);
  if (m && +m[2] <= 100) set('promoter_post_pct', +m[2]);
  else if ((m = first(/promoter[^%]{0,40}?post[- ]issue[^\d]{0,15}([\d.]+)\s*%/i))) set('promoter_post_pct', +m[1]);
  m = first(new RegExp(`(?:raises?|raised|mobili[sz]ed|garners?)\\s*${CURSYM}\\s?([\\d,]+(?:\\.\\d+)?)\\s*(crores?|cr\\b\\.?|million|mn\\b|billion|bn\\b)?\\s*from\\s*anchor`, 'i'));
  if (m) set('anchor_amount', toU(NUM(m[1]), m[2]));

  // ── Financial table ──
  const tScaleM = flat.match(/(?:amount|figures|all\s+amounts)?\s*\(?in\s*(?:₹|Rs\.?|INR|US\$|\$|USD)?\s*(crores?|cr\b|lakhs?|millions?|thousands?|billions?)\)?/i);
  const tScale = tScaleM ? SCALE[tScaleM[1].toLowerCase().replace(/s$/, '').replace(/^cr$/, 'crore')] || SCALE[tScaleM[1].toLowerCase()] : U;
  const NUMRX = '\\(?-?\\d[\\d,]*(?:\\.\\d{1,2})?\\)?';
  const rowAt = (labelRx) => {
    const rx = new RegExp(labelRx.source + `[^\\dA-Za-z(-]{0,12}((?:${NUMRX}[\\s|]*){2,8})`, 'gi'); let mm;
    while ((mm = rx.exec(flat))){
      const vals = (mm[mm.length - 1].match(new RegExp(NUMRX, 'g')) || []).map(NUM).filter(v => v != null);
      if (vals.length >= 2) return {vals, at: mm.index};
    }
    return null;
  };
  const revRow = rowAt(/revenue\s*from\s*operations/) || rowAt(/(?:total\s*)?revenues?(?!\s*(?:from|growth|increased|rose))/) || rowAt(/net\s*sales/);
  const incRow = revRow ? null : rowAt(/total\s*income/);
  const patRow = rowAt(/profit\s*after\s*tax(?:\s*\(PAT\))?/) || rowAt(/net\s*(?:profit|income|loss)(?:\s*\/\s*\(?(?:loss|income)\)?)?/) || rowAt(/profit\s*\/?\s*\(?loss\)?\s*for\s*the\s*(?:year|period)/);
  const ebRow = rowAt(/EBITDA/);
  const debtRow = rowAt(/total\s*borrowings?/) || rowAt(/total\s*debt/);
  const anyRow = [revRow || incRow, patRow, ebRow].filter(Boolean);
  if (anyRow.length){
    // Column headers: dates or FY labels just before the first row of the table
    const startAt = Math.min(...anyRow.map(r => r.at));
    const head = flat.slice(Math.max(0, startAt - 400), startAt);
    const HRX = new RegExp(`((?:three|six|nine|3|6|9)[- ]months?[^)]{0,30}?ended\\s+${DATE.replace(/\((?!\?)/g, '(?:')})|(${DATE.replace(/\((?!\?)/g, '(?:')})|\\b(FY\\s?'?\\d{2,4})\\b|\\b(Q[1-4]\\s?FY\\s?\\d{2,4}|H[12]\\s?FY\\s?\\d{2,4})\\b|\\b((?:19|20)\\d{2})\\b`, 'gi');
    let cols = [], h;
    while ((h = HRX.exec(head))){
      if (h[1]) cols.push({partial: true, label: 'partial'});
      else if (h[2]){ const d = h[2].match(new RegExp(DATE, 'i')); const ds = dateFrom(d); cols.push({date: ds, y: +ds.slice(0, 4), m: +ds.slice(5, 7)}); }
      else if (h[3]){ let y = +h[3].replace(/\D/g, ''); if (y < 100) y += 2000; cols.push({y, m: inr ? 3 : 12, fy: true}); }
      else if (h[4]) cols.push({partial: true, label: h[4]});
      else cols.push({y: +h[5], m: inr ? 3 : 12, fy: true});
    }
    // keep the last run of headers right before the table (pages often mention dates in prose earlier)
    const n = Math.max(...anyRow.map(r => r.vals.length));
    if (cols.length > n) cols = cols.slice(-n);
    if (cols.length === n){
      const months = cols.filter(c => !c.partial && !c.fy).map(c => c.m);
      const common = months.sort((a, b) => months.filter(x => x === b).length - months.filter(x => x === a).length)[0];
      cols.forEach(c => { if (!c.partial && !c.fy && months.length >= 2 && c.m !== common) c.partial = true; });
    } else cols = Array.from({length: n}, () => ({}));
    const keep = cols.map((c, i) => c.partial ? null : i).filter(i => i != null);
    if (keep.length < cols.length) warnings.push('Dropped a part-year column (e.g. one quarter) from the financials so growth is year over year.');
    const ys = keep.map(i => cols[i].y).filter(Boolean);
    const newestFirst = ys.length >= 2 ? ys[0] > ys[ys.length - 1] : true;
    const order = newestFirst ? [...keep].reverse() : keep;
    const pick = r => r ? order.filter(i => i < r.vals.length).map(i => Math.round(r.vals[i] * tScale / U * 100) / 100) : null;
    const lab = order.map(i => { const c = cols[i]; return c.y ? (inr && c.m === 3 ? 'FY' + String(c.y).slice(2) : String(c.y)) : null; });
    if (lab.every(Boolean)) set('years', lab);
    const rv = pick(revRow || incRow); if (rv && rv.length >= 2) set('revenue', rv);
    if (incRow && rv) warnings.push('Revenue is "Total income" (includes other income), the closest line the page shows.');
    const pt = pick(patRow); if (pt && pt.length >= 2) set('net_profit', pt);
    const eb = pick(ebRow); if (eb && eb.length >= 2) set('ebitda', eb);
    const db = pick(debtRow); if (db && db.length) set('debt', db[db.length - 1]);
    if (!ys.length) warnings.push('Could not read the column years; assumed the newest year comes first. Check the financials.');
    if (o.revenue && o.revenue.length >= 2){ const g = o.revenue[o.revenue.length - 1] / o.revenue[o.revenue.length - 2] - 1; if (g > 3 || g < -0.8) warnings.push('Revenue jumps oddly between years; the page may mix periods. Check the financials.'); }
  }
  // Money from the issue that repays debt (Objects of the issue)
  m = first(/(?:repay|prepay)[a-z]*[^.]{0,220}?(?:borrowings?|debt|loans?)[^\d₹$]{0,80}?(?:₹|Rs\.?|\$)?\s?([\d,]+\.\d{2})/i);
  if (m) set('proceeds_debt', NUM(m[1]) * tScale / U);
  else if ((m = first(new RegExp(`${CURSYM}\\s?([\\d,]+(?:\\.\\d+)?)\\s*(million|mn|billion|bn|crores?|cr)?\\s*of\\s*(?:the\\s*)?net\\s*proceeds\\s*to\\s*(?:re|pre)?pay`, 'i')))) set('proceeds_debt', toU(NUM(m[1]), m[2]));    // objects-of-the-issue tables use the same unit as the financials

  // ── Exchange, symbol, about ──
  m = first(/listing\s*at[:\s]*((?:BSE|NSE|BSE SME|NSE SME|NASDAQ|NYSE)(?:\s*[,&]\s*(?:BSE|NSE|NASDAQ|NYSE))*)/i);
  if (m) set('exchange', m[1].toUpperCase().replace(/\s*&\s*/, ', '));
  else if (/\bNSE\b/.test(flat) && /\bBSE\b/.test(flat)) set('exchange', 'NSE, BSE');
  else if ((m = first(/\b(Nasdaq(?: Global (?:Select )?Market)?|New York Stock Exchange|NYSE)\b/))) set('exchange', m[1].replace('New York Stock Exchange', 'NYSE'));
  m = first(/NSE\s*(?:Symbol|Code)[:\s]*([A-Z0-9&-]{2,20})\b/) || first(/under\s+the\s+(?:ticker\s+)?symbol\s*[“"']?([A-Z.]{1,6})[”"']?/);
  if (m){ set('symbol', m[1]); set('yahoo', /NSE/.test(m[0]) ? m[1] + '.NS' : m[1].replace('.', '-')); }
  const aboutAt = flat.search(/About\s/);
  if (aboutAt >= 0){
    m = flat.slice(aboutAt, aboutAt + 900).match(/(?:Limited|Ltd\.?|Inc\.?|Corporation|company|Company)\s+(?:is|operates as)\s+(an?\s[^.]{10,170})\./);
    if (m) set('about', m[1].replace(/\s+/g, ' '));
  }
  if (opts.url && /^https?:\/\//.test(opts.url)){ o.sources = [{url: opts.url, title: 'Extracted from ' + opts.url.replace(/^https?:\/\/(www\.)?/, '').split('/')[0]}]; found.push('sources'); }

  const want = ['name', 'price_high', ...(o.currency === 'INR' ? ['lot_size'] : []), 'close_date', 'issue_size', 'shares_post', 'revenue', 'net_profit', 'ebitda', 'promoter_post_pct'];
  const missing = want.filter(k => o[k] == null && !(k === 'shares_post' && o.fresh_shares && o.pct_sold));
  return {ipo: o, found: [...new Set(found)], missing, warnings};
}

root.extractIpo = extractIpo;
if (typeof module !== 'undefined') module.exports = {extractIpo};
})(typeof window !== 'undefined' ? window : globalThis);
