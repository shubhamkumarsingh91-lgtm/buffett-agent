// export.js — PDF export for the IPO Desk, Company Desk, Upcoming IPOs and any single stock.
// Independent personal project, not tied to any employer or agency. Public and synthetic data only,
// no internal or personal data (no SSNs/PHI). Educational research, not financial advice.
//
// Everything runs in the browser: jsPDF is loaded from the CDN on first use, nothing is uploaded.
// The portfolio export lives in index.html (exportPdf); this file reuses LIBS, loadScript and download.

let DRAWER_ITEM = null;          // what the drawer is showing: {kind:'stock', s} or {kind:'up', ipo}
let GRID_LIST = [];              // desk cards in the order on screen (search + sort applied)

// Built-in PDF fonts only know plain Latin characters, so swap symbols for text.
const PA = t => String(t ?? '')
  .replace(/₹/g, 'Rs ').replace(/€/g, 'EUR ').replace(/£/g, 'GBP ').replace(/¥/g, 'JPY ')
  .replace(/–/g, ' - ').replace(/[—−]/g, '-').replace(/÷/g, '/').replace(/[‘’]/g, "'").replace(/[“”]/g, '"').replace(/·/g, '|').replace(/…/g, '...')
  .replace(/≥/g, '>=').replace(/≤/g, '<=').replace(/×/g, 'x').replace(/→/g, '->')
  .replace(/[^\x20-\x7E\n]/g, '');
const HEAD = {fillColor: [30, 34, 42]};
const VCOL = l => /^(BUY|SUBSCRIBE)/.test(l) ? [22, 140, 90] : /^(WATCH|WORTH|WAIT \(rich)/.test(l) ? [180, 120, 20] : /^WAIT/.test(l) ? [50, 110, 200] : [190, 60, 60];

async function newDoc(orientation){
  await loadScript(LIBS.jspdf); await loadScript(LIBS.autotable);
  return new jspdf.jsPDF({orientation, unit: 'pt', format: 'letter'});
}
function titleBlock(doc, title, sub){
  doc.setFont('helvetica', 'bold'); doc.setFontSize(19); doc.setTextColor(20); doc.text(PA(title), 40, 50);
  return flow(doc, 67, sub, {size: 9.5, color: 110, gap: 6});
}
function footer(doc){
  const n = doc.getNumberOfPages(), W = doc.internal.pageSize.getWidth(), H = doc.internal.pageSize.getHeight();
  for (let i = 1; i <= n; i++){ doc.setPage(i); doc.setFont('helvetica', 'normal'); doc.setFontSize(7.5); doc.setTextColor(120);
    doc.text(doc.splitTextToSize('Long-Term Lab | Independent personal project, not tied to any employer or agency. Public market data only, no personal data. Educational research, not financial advice.', W - 120), 40, H - 24);
    doc.text(`${i}/${n}`, W - 55, H - 20); }
}
// Flowing text that breaks onto a new page when it runs out of room.
function flow(doc, y, text, {size = 10, bold = false, color = 20, indent = 0, gap = 4} = {}){
  const W = doc.internal.pageSize.getWidth(), H = doc.internal.pageSize.getHeight();
  doc.setFont('helvetica', bold ? 'bold' : 'normal'); doc.setFontSize(size); doc.setTextColor(...(Array.isArray(color) ? color : [color]));
  for (const line of doc.splitTextToSize(PA(text), W - 80 - indent)){
    if (y > H - 50){ doc.addPage(); y = 50; }
    doc.text(line, 40 + indent, y); y += size * 1.3;
  }
  doc.setTextColor(20); return y + gap;
}
const heading = (doc, y, t) => flow(doc, y + 6, t, {size: 13, bold: true, gap: 2});
function bullets(doc, y, items, mark = '-'){
  if (!items || !items.length) return flow(doc, y, 'Nothing notable.', {color: 120});
  for (const it of items) y = flow(doc, y, `${mark}  ${it}`, {indent: 8, gap: 1});
  return y + 4;
}
const after = doc => doc.lastAutoTable.finalY + 14;
const fileName = t => `long-term-lab-${t.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}-${stamp()}.pdf`;
async function run(btn, fn){
  const old = btn && btn.textContent; if (btn){ btn.disabled = true; btn.textContent = 'Building PDF…'; }
  try { await fn(); } catch (e){ alert(e.message || 'PDF export failed.'); }
  finally { if (btn){ btn.disabled = false; btn.textContent = old; } }
}

// ── Desk PDF: every stock on the IPO Desk or Company Desk, in the order on screen ──
function exportDeskPdf(btn){ return run(btn, async () => {
  const list = GRID_LIST.length ? GRID_LIST : DATA.stocks.filter(s => s.desk === view);
  if (!list.length) throw new Error('Nothing on this desk to export.');
  const ipo = view === 'ipo', D = DESKS[view], doc = await newDoc('landscape');
  const q = $('#q').value.trim();
  let y = titleBlock(doc, `Long-Term Lab - ${D.title}`, `${list.length} stocks${q ? ` matching "${q}"` : ''}  |  data as of ${DATA.generated ? new Date(DATA.generated).toLocaleString() : 'n/a'}  |  exported ${new Date().toLocaleString()}`);
  const buys = list.filter(s => /^BUY/.test(s.overall.label)).length;
  y = flow(doc, y, `${buys} buy candidate${buys === 1 ? '' : 's'}  |  average score ${(list.reduce((a, s) => a + s.overall.score, 0) / list.length).toFixed(1)}/100  |  lenses: ${list[0].lenses.map(l => l.short).join(', ')}`, {size: 10.5});
  const lensKeys = list[0].lenses.map(l => [l.key, l.short]);
  const k = s => s.kpis;
  const extra = ipo
    ? [['Months public', s => s.ipo.months_listed == null ? '' : Math.round(s.ipo.months_listed)], ['P/S', s => num(k(s).price_to_sales, 1)], ['Rev growth', s => pct(k(s).revenue_growth_yoy, 0)], ['FCF margin', s => pct(k(s).fcf_margin, 0)], ['Rule of 40', s => num(k(s).rule_of_40, 0)]]
    : [['P/E', s => num(k(s).pe, 1)], ['ROIC', s => pct(k(s).roic, 0)], ['Rev growth', s => pct(k(s).revenue_growth_yoy, 0)], ['Fair value', s => money(s.valuation.base)], ['MoS', s => pct(s.valuation.margin_of_safety, 0)]];
  doc.autoTable({startY: y, headStyles: HEAD, styles: {fontSize: 8.5, cellPadding: 4}, alternateRowStyles: {fillColor: [245, 246, 248]},
    head: [['Ticker', 'Name', 'Price', 'Score', 'Verdict', ...lensKeys.map(([, n]) => n), ...extra.map(([n]) => n)]],
    body: list.map(s => [s.ticker + (s.stale ? ' *' : ''), (s.name || '').slice(0, 28), money(s.price), Math.round(s.overall.score), s.overall.label,
      ...lensKeys.map(([kk]) => { const l = s.lenses.find(x => x.key === kk); return l ? Math.round(l.score) : ''; }), ...extra.map(([, f]) => f(s))].map(PA)),
    didParseCell: c => { if (c.section === 'body' && c.column.index === 4){ c.cell.styles.textColor = VCOL(c.cell.raw); c.cell.styles.fontStyle = 'bold'; } }});
  y = after(doc);
  if (list.some(s => s.stale)) y = flow(doc, y, '* stale: the last data update failed for this stock, so the previous result is shown.', {size: 8, color: 120});
  y = heading(doc, y, 'Research notes');
  doc.autoTable({startY: y, headStyles: HEAD, styles: {fontSize: 8, cellPadding: 5, valign: 'top'}, columnStyles: {0: {cellWidth: 90}, 1: {cellWidth: 200}},
    head: [['Stock', 'Verdict and why', 'Why it could work', 'What worries us']],
    body: list.map(s => [`${s.ticker}\n${s.name || ''}`, `${s.overall.label} (${Math.round(s.overall.score)})\n${s.overall.rationale}`,
      (s.memo.bull || []).slice(0, 2).map(x => '+ ' + x).join('\n'), (s.memo.bear || []).slice(0, 2).map(x => '- ' + x).join('\n')].map(PA))});
  footer(doc); doc.save(fileName(D.title));
}); }

// ── Upcoming IPOs PDF ──
function exportUpcomingPdf(btn){ return run(btn, async () => {
  const all = upList();
  if (!all.length) throw new Error('No upcoming IPOs to export yet.');
  const list = all.map(analyzeUpcoming).sort((a, b) => (daysTo(a.ipo.close_date) ?? 999) - (daysTo(b.ipo.close_date) ?? 999));
  const doc = await newDoc('landscape');
  let y = titleBlock(doc, 'Long-Term Lab - Upcoming IPOs', `${list.length} IPO${list.length === 1 ? '' : 's'} before listing  |  page 1 is the summary, then a full report with the strategy for each IPO  |  numbers from IPO pages and prospectuses, verify before applying  |  exported ${new Date().toLocaleString()}`);
  doc.autoTable({startY: y, headStyles: HEAD, styles: {fontSize: 8.5, cellPadding: 4}, alternateRowStyles: {fillColor: [245, 246, 248]},
    head: [['Company', 'Exchange', 'Subscription', 'Listing', 'Price band', 'Market value', 'P/E', 'P/S', 'Rev growth', 'Score', 'Verdict']],
    body: list.map(a => { const i = a.ipo; return [i.name + (i.draft ? ' (draft)' : ''), i.exchange || '', i.open_date || i.close_date ? `${i.open_date || '?'} to ${i.close_date || '?'}` : 'dates tbc', i.listing_date || 'tbc',
      `${cp(i, a.priceLo)}-${cp(i, a.price)}`, cm(i, a.k.mcap), num(a.k.pe, 1), num(a.k.ps, 1), pct(a.k.rev_growth, 0), Math.round(a.overall.score), a.overall.label].map(PA); }),
    didParseCell: c => { if (c.section === 'body' && c.column.index === 10){ c.cell.styles.textColor = VCOL(c.cell.raw); c.cell.styles.fontStyle = 'bold'; } }});
  y = heading(doc, after(doc), 'Strategy at a glance');
  const st = (a, h) => (a.strategy.find(x => x.h === h) || {}).t || '-';
  doc.autoTable({startY: y, headStyles: HEAD, styles: {fontSize: 8, cellPadding: 5, valign: 'top'}, columnStyles: {0: {cellWidth: 95}},
    head: [['IPO', 'Apply or not', 'Buy zone after listing', 'Lock-up dates', 'Re-check or sell if']],
    body: list.map(a => [`${a.ipo.name}\n${a.overall.label} (${Math.round(a.overall.score)})`, st(a, 'Apply or not'), st(a, 'Buy zone after listing'),
      st(a, 'Mark the lock-up dates'), st(a, 'Re-check or sell if')].map(PA))});
  for (const a of list){ doc.addPage('letter', 'portrait'); writeUpcoming(doc, a); }
  footer(doc); doc.save(fileName('upcoming-ipos'));
}); }

// ── One stock / one upcoming IPO: the full memo as shown in the drawer ──
function exportOnePdf(btn){ return run(btn, async () => {
  if (!DRAWER_ITEM) throw new Error('Open a stock first.');
  const doc = await newDoc('portrait');
  if (DRAWER_ITEM.kind === 'up') return onePdfUpcoming(doc, analyzeUpcoming(DRAWER_ITEM.ipo));
  const s = DRAWER_ITEM.s, M = s.memo, k = s.kpis, v = s.valuation, ipo = s.desk === 'ipo';
  let y = titleBlock(doc, `${s.ticker} - ${s.name || ''}`, [ipo ? 'IPO Desk' : 'Company Desk', s.sector, s.industry, `price ${money(s.price)}`, `data ${new Date(s.updated).toLocaleDateString()}`].filter(Boolean).join('  |  '));
  y = flow(doc, y + 4, `${s.overall.label}  -  ${Math.round(s.overall.score)}/100`, {size: 15, bold: true, color: VCOL(s.overall.label)});
  y = flow(doc, y, s.overall.rationale, {size: 10.5});
  if (s.stale) y = flow(doc, y, 'Note: the last data update failed, so this is the previous result.', {size: 9, color: [190, 60, 60]});
  y = heading(doc, y, 'Research memo');
  y = flow(doc, y, M.business);
  y = flow(doc, y, 'Why it could work', {bold: true, color: [22, 140, 90], gap: 1}); y = bullets(doc, y, M.bull, '+');
  y = flow(doc, y, 'What worries us', {bold: true, color: [190, 60, 60], gap: 1}); y = bullets(doc, y, M.bear, '-');
  y = flow(doc, y, 'Valuation: ' + M.valuation);
  y = flow(doc, y, 'What to watch', {bold: true, gap: 1}); y = bullets(doc, y, M.watch);
  y = flow(doc, y, 'If we act on it: ' + M.plan, {bold: true, size: 10});
  y = flow(doc, y, "Buffett's view: " + M.buffett_view, {size: 9.5, color: 90});
  if (M.ai) { y = flow(doc, y, "Analyst's take (AI, Gemini)", {bold: true, gap: 1}); y = flow(doc, y, M.ai, {size: 9.5}); }
  if (v.base) y = flow(doc, y, `Fair value per share: bear ${money(v.bear)} | base ${money(v.base)} | bull ${money(v.bull)} vs price ${money(s.price)}${v.margin_of_safety != null ? ` | margin of safety ${pct(v.margin_of_safety, 0)}` : ''}. Two-stage DCF on ${v.method}, ${pct(v.growth, 0)} growth fading to 3%, 9% discount rate.`, {size: 9.5});
  if (ipo && s.ipo.checklist && s.ipo.checklist.length){
    y = heading(doc, y, 'IPO checklist');
    doc.autoTable({startY: y, headStyles: HEAD, styles: {fontSize: 8.5, cellPadding: 4}, columnStyles: {0: {cellWidth: 40}, 1: {cellWidth: 130}},
      head: [['', 'Check', 'Detail']], body: s.ipo.checklist.map(c => [c.status.toUpperCase(), c.label, c.detail].map(PA))});
    y = after(doc);
  }
  y = heading(doc, y, 'Investor lenses');
  doc.autoTable({startY: y, headStyles: HEAD, styles: {fontSize: 8, cellPadding: 4, valign: 'top'}, columnStyles: {0: {cellWidth: 110}, 1: {cellWidth: 40}},
    head: [['Lens', 'Score', 'Strengths', 'Weaknesses']],
    body: s.lenses.map(l => [`${l.name}\n${l.verdict || ''}`, Math.round(l.score), l.pros.map(x => '+ ' + x).join('\n'), l.cons.map(x => '- ' + x).join('\n')].map(PA))});
  y = heading(doc, after(doc), 'Key numbers');
  const rows = [['Revenue (TTM)', big(k.revenue_ttm)], ['Revenue growth', pct(k.revenue_growth_yoy)], ['Gross margin', pct(k.gross_margin)], ['Operating margin', pct(k.operating_margin)],
    ['Net margin', pct(k.profit_margin)], ['ROIC', pct(k.roic)], ['Free cash flow', big(k.free_cash_flow)], ['FCF margin', pct(k.fcf_margin)], ['Rule of 40', num(k.rule_of_40, 0)],
    ['Market cap', big(k.market_cap)], ['P/E', num(k.pe, 1)], ['Forward P/E', num(k.forward_pe, 1)], ['Price / sales', num(k.price_to_sales, 1)], ['EV / EBITDA', num(k.ev_to_ebitda, 1)],
    ['PEG', num(k.peg)], ['Dividend yield', pct(k.dividend_yield)], ['Debt / equity', num(k.debt_to_equity)], ['Current ratio', num(k.current_ratio)],
    ['Insiders own', pct(k.insider_pct, 0)], ['Short interest', pct(k.short_pct_float)]];
  const half = Math.ceil(rows.length / 2);
  doc.autoTable({startY: y, headStyles: HEAD, styles: {fontSize: 8.5, cellPadding: 3}, head: [['Metric', 'Value', 'Metric', 'Value']],
    body: rows.slice(0, half).map((r, i) => [...r, ...(rows[half + i] || ['', ''])].map(PA))});
  y = after(doc);
  if ((s.data_notes || []).length){ y = flow(doc, y, 'Data notes', {bold: true, size: 9, gap: 1}); y = bullets(doc, y, s.data_notes.map(PA)); }
  footer(doc); doc.save(fileName(s.ticker));
}); }

function onePdfUpcoming(doc, a){ writeUpcoming(doc, a); footer(doc); doc.save(fileName(a.ipo.name)); }
// The full report for one upcoming IPO: strategy, memo, checklist, experts, key numbers, financials, risks.
function writeUpcoming(doc, a){
  const i = a.ipo, k = a.k, v = a.valuation, M = a.memo;
  let y = titleBlock(doc, `${i.name}${i.symbol ? ' (' + i.symbol + ')' : ''}`, ['Upcoming IPO', i.exchange, i.sector, `price band ${cp(i, a.priceLo)}-${cp(i, a.price)}`, i.lot_size ? `lot ${i.lot_size}` : '', `subscription ${i.open_date || '?'} to ${i.close_date || '?'}`, i.listing_date ? `lists ${i.listing_date}` : ''].filter(Boolean).join('  |  '));
  y = flow(doc, y + 4, `${a.overall.label}  -  ${Math.round(a.overall.score)}/100`, {size: 15, bold: true, color: VCOL(a.overall.label)});
  y = flow(doc, y, a.overall.rationale, {size: 10.5});
  y = heading(doc, y, 'Strategy');
  for (const [j, st] of a.strategy.entries()){ y = flow(doc, y, `${j + 1}. ${st.h}`, {bold: true, size: 10, color: [150, 110, 30], gap: 0}); y = flow(doc, y, st.t, {size: 9.5, indent: 12, gap: 3}); }
  y = flow(doc, y + 4, `From prospectus numbers entered ${i.updated || ''}${i.added_by ? ' by ' + i.added_by : ''}${i.draft ? ' (draft, not saved to the site)' : ''}. Verify against the prospectus before applying.`, {size: 8.5, color: 120});
  y = heading(doc, y, 'Research memo');
  y = flow(doc, y, M.lead);
  y = flow(doc, y, 'Why it could work', {bold: true, color: [22, 140, 90], gap: 1}); y = bullets(doc, y, M.bull, '+');
  y = flow(doc, y, 'What worries us', {bold: true, color: [190, 60, 60], gap: 1}); y = bullets(doc, y, M.bear, '-');
  y = flow(doc, y, 'Valuation: ' + M.val);
  if (v.base) y = flow(doc, y, `Fair value per share: bear ${cp(i, v.bear)} | base ${cp(i, v.base)} | bull ${cp(i, v.bull)} vs band top ${cp(i, a.price)}. Two-stage DCF on net profit per share, ${pct(v.growth, 0)} growth fading to ${pct(v.tg, 0)}, ${pct(v.r, 0)} discount rate.`, {size: 9.5});
  y = flow(doc, y, 'What to watch', {bold: true, gap: 1}); y = bullets(doc, y, M.watch);
  y = flow(doc, y, 'If we act on it: ' + M.plan, {bold: true, size: 10});
  y = flow(doc, y, "Buffett's view: " + M.buffett, {size: 9.5, color: 90});
  y = heading(doc, y, 'IPO checklist');
  doc.autoTable({startY: y, headStyles: HEAD, styles: {fontSize: 8.5, cellPadding: 4}, columnStyles: {0: {cellWidth: 40}, 1: {cellWidth: 130}},
    head: [['', 'Check', 'Detail']], body: a.checklist.map(c => [c.status.toUpperCase(), c.label, c.detail].map(PA))});
  y = heading(doc, after(doc), 'IPO experts');
  doc.autoTable({startY: y, headStyles: HEAD, styles: {fontSize: 8, cellPadding: 4, valign: 'top'}, columnStyles: {0: {cellWidth: 110}, 1: {cellWidth: 40}},
    head: [['Lens', 'Score', 'Strengths', 'Weaknesses']],
    body: a.lenses.map(l => [l.name, Math.round(l.score), l.pros.map(x => '+ ' + x).join('\n'), l.cons.map(x => '- ' + x).join('\n')].map(PA))});
  y = heading(doc, after(doc), 'Key numbers at the top of the band');
  const rows = [['Market value', cm(i, k.mcap)], ['P/E', num(k.pe, 1)], ['Price / sales', num(k.ps, 1)], ['EV / EBITDA', num(k.ev_ebitda, 1)], ['PEG', num(k.peg, 2)],
    ['Revenue growth', pct(k.rev_growth)], ['Profit growth', pct(k.pat_growth)], ['EBITDA margin', pct(k.ebitda_margin)], ['Net margin', pct(k.pat_margin)], ['Rule of 40', num(k.rule40, 0)],
    ['Issue size', cm(i, i.issue_size)], ['Fresh issue', cm(i, i.fresh_issue)], ['Offer for sale', cm(i, i.ofs)], ['Promoter stake after', i.promoter_post_pct != null ? i.promoter_post_pct + '%' : '-']];
  const half = Math.ceil(rows.length / 2);
  doc.autoTable({startY: y, headStyles: HEAD, styles: {fontSize: 8.5, cellPadding: 3}, head: [['Metric', 'Value', 'Metric', 'Value']],
    body: rows.slice(0, half).map((r, j) => [...r, ...(rows[half + j] || ['', ''])].map(PA))});
  const yrs = i.years || (i.revenue || []).map((_, j, arr) => `Y-${arr.length - 1 - j}`);
  const fin = [['Revenue', i.revenue], ['EBITDA', i.ebitda], ['Net profit', i.net_profit]].filter(([, arr]) => arr && arr.length);
  if (fin.length){
    y = heading(doc, after(doc), `Financials (${i.unit} ${i.currency})`);
    doc.autoTable({startY: y, headStyles: HEAD, styles: {fontSize: 8.5, cellPadding: 3}, head: [['', ...yrs].map(PA)],
      body: fin.map(([n, arr]) => [n, ...yrs.map((_, j) => cm(i, arr[j]))].map(PA))});
  }
  y = after(doc);
  if ((i.risks || []).length){ y = flow(doc, y, 'Risks from the prospectus', {bold: true, gap: 1}); y = bullets(doc, y, i.risks); }
  const src = [i.prospectus_url, ...(i.sources || []).map(s => s.url)].filter(Boolean);
  if (src.length){ y = flow(doc, y, 'Sources', {bold: true, gap: 1}); y = bullets(doc, y, src); }
}
