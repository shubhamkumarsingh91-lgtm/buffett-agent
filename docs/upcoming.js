/*
  upcoming.js — Upcoming IPO desk for Long-Term Lab.
  DISCLAIMER: Independent personal project. Not tied to any employer or agency.
  Public data only (numbers typed in from public prospectuses / news). No personal data.
  Educational research, not financial advice. Never places trades.

  A company that hasn't listed yet has no market data, so this desk works from the
  numbers in its prospectus (S-1 / 424B4 in the US, DRHP / RHP in India). Everything
  is calculated here in the browser:
    * valuation at the price band (market cap, P/E, P/S, EV/EBITDA, PEG)
    * Jay Ritter lens (what IPO research says predicts long-run returns)
    * Bill Gurley lens (revenue quality)
    * a simple two-stage DCF on net profit (bear / base / bull) vs the price band
    * an IPO checklist, a verdict and a written memo
  Saved IPOs live in docs/data/upcoming.json (added through a GitHub issue).
*/

const UNIT = {crore:1e7, lakh:1e5, million:1e6, billion:1e9, thousand:1e3};
// Approximate USD conversion, only used to size the company against Ritter's (USD) size bands.
const FX_USD = {USD:1, INR:0.012, EUR:1.08, GBP:1.27, CAD:0.73, AUD:0.66, HKD:0.128, JPY:0.0067, CNY:0.14, SGD:0.74, CHF:1.12};
const RATES = {INR:{r:0.12, tg:0.05}, default:{r:0.09, tg:0.03}};       // discount rate / terminal growth by currency
const CUR = {USD:'$', INR:'₹', EUR:'€', GBP:'£', CAD:'C$', AUD:'A$', HKD:'HK$', JPY:'¥', CNY:'¥', SGD:'S$', CHF:'CHF '};
let UPCOMING = [];

const clampN = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
const band = (x, steps) => { for (const [th, sc] of steps.slice(0, -1)) if (x >= th) return sc; return steps[steps.length - 1][1]; };
const last = a => (a || []).filter(v => v != null && v !== '').map(Number).slice(-1)[0];
const prev = a => { const v = (a || []).filter(v => v != null && v !== '').map(Number); return v.length > 1 ? v[v.length - 2] : null; };
const wavg = parts => parts.reduce((a, [s, w]) => a + s * w, 0) / parts.reduce((a, [, w]) => a + w, 0);
// Whole calendar days from today (0 = today, 1 = tomorrow, -1 = yesterday), in the viewer's time zone.
function daysTo(d){ if (!d) return null; const t = new Date(d + 'T00:00:00'), n = new Date(); n.setHours(0,0,0,0); return Math.round((t - n) / 864e5); }

function cm(ipo, amountInUnits){            // currency money in the IPO's own unit, e.g. "₹30,213 cr"
  if (amountInUnits == null || !isFinite(amountInUnits)) return '—';
  const c = CUR[ipo.currency] || (ipo.currency + ' ');
  const u = {crore:' cr', lakh:' lakh', million:'M', billion:'B', thousand:'K'}[ipo.unit] || '';
  return c + Number(amountInUnits).toLocaleString(undefined, {maximumFractionDigits: amountInUnits >= 100 ? 0 : 2}) + u;
}
function cp(ipo, perShare){ const c = CUR[ipo.currency] || (ipo.currency + ' '); return perShare == null || !isFinite(perShare) ? '—' : c + Number(perShare).toLocaleString(undefined, {maximumFractionDigits: 2}); }

function dcfPS(base, g, r, tg, years = 10){
  let pv = 0, cf = base;
  for (let y = 1; y <= years; y++){ const gy = y <= 5 ? g : g + (tg - g) * (y - 5) / (years - 5); cf *= 1 + gy; pv += cf / Math.pow(1 + r, y); }
  return pv + cf * (1 + tg) / (r - tg) / Math.pow(1 + r, years);
}

function analyzeUpcoming(ipo){
  const U = UNIT[ipo.unit] || 1, fx = FX_USD[ipo.currency] ?? 1, R = RATES[ipo.currency] || RATES.default;
  const r = ipo.discount_rate || R.r, tg = R.tg;
  const rev = last(ipo.revenue), revP = prev(ipo.revenue), pat = last(ipo.net_profit), patP = prev(ipo.net_profit);
  const ebitda = last(ipo.ebitda), ebitdaP = prev(ipo.ebitda);
  let shares = ipo.shares_post;                                   // in ipo.unit
  if (!shares && ipo.fresh_shares && ipo.pct_sold) shares = ipo.fresh_shares / (ipo.pct_sold / 100);
  const price = ipo.price_high || ipo.price_low, priceLo = ipo.price_low || price;
  const mcap = price && shares ? price * shares : null;            // in currency-units (same unit as financials)
  const k = {
    mcap, mcap_low: priceLo && shares ? priceLo * shares : null,
    pe: mcap && pat > 0 ? mcap / pat : null, ps: mcap && rev ? mcap / rev : null,
    rev_growth: rev && revP ? rev / revP - 1 : null, pat_growth: pat && patP && patP > 0 ? pat / patP - 1 : null,
    ebitda_margin: ebitda != null && rev ? ebitda / rev : null, ebitda_margin_prev: ebitdaP != null && revP ? ebitdaP / revP : null,
    pat_margin: pat != null && rev ? pat / rev : null, gross_margin: ipo.gross_margin != null ? ipo.gross_margin / 100 : null,
    ofs_share: ipo.issue_size ? (ipo.ofs || 0) / ipo.issue_size : null,
    debt_share_of_proceeds: ipo.fresh_issue && ipo.proceeds_debt ? ipo.proceeds_debt / ipo.fresh_issue : null,
    rev_usd: rev ? rev * U * fx : null, shares,
  };
  k.ev = mcap != null && ipo.debt != null ? mcap + ipo.debt - (ipo.cash || 0) - (ipo.fresh_issue || 0) : null;
  k.ev_ebitda = k.ev && ebitda > 0 ? k.ev / ebitda : null;
  k.peg = k.pe && k.pat_growth > 0 ? k.pe / (k.pat_growth * 100) : null;
  k.rule40 = k.rev_growth != null && k.pat_margin != null ? (k.rev_growth + k.pat_margin) * 100 : null;
  const revs = (ipo.revenue || []).filter(v => v != null && v !== '').map(Number);
  k.rev_up_every_year = revs.length >= 2 ? revs.every((v, i) => i === 0 || v > revs[i - 1]) : null;

  // ── Jay Ritter lens ──
  const rp = [], rc = [], rparts = [];
  if (k.rev_usd != null){ rparts.push([band(k.rev_usd, [[1e9, 80], [2.5e8, 65], [5e7, 45], [null, 25]]), .2]);
    (k.rev_usd >= 2.5e8 ? rp : rc).push(k.rev_usd >= 2.5e8 ? `Large company (revenue ${cm(ipo, rev)}). Ritter finds the long-run IPO underperformance comes mainly from the smallest issuers.`
      : `Small company (revenue ${cm(ipo, rev)}). Ritter's data shows the smallest IPOs drive long-run underperformance.`); }
  if (k.ps != null){ rparts.push([band(-k.ps, [[-6, 85], [-12, 60], [-24, 35], [null, 15]]), .25]);
    (k.ps <= 6 ? rp : rc).push(k.ps <= 6 ? `At the top of the band it's ${k.ps.toFixed(1)}x sales, near the historical tech-IPO norm of ~6.`
      : `At the top of the band it's ${k.ps.toFixed(1)}x sales. Ritter: at high multiples "the upside potential is more limited and the downside potential is greater."`); }
  if (pat != null){ rparts.push([pat > 0 ? 70 : 40, .1]); (pat > 0 ? rp : rc).push(pat > 0 ? `Profitable: ${cm(ipo, pat)} net profit last year.` : 'Loss-making. Growth has to carry the whole story.'); }
  if (k.ofs_share != null){ rparts.push([k.ofs_share <= .25 ? 85 : k.ofs_share <= .6 ? 60 : 35, .2]);
    (k.ofs_share <= .25 ? rp : rc).push(k.ofs_share <= .25 ? `${Math.round((1 - k.ofs_share) * 100)}% fresh issue: the money goes into the company, not to sellers cashing out.`
      : `${Math.round(k.ofs_share * 100)}% of the issue is existing holders selling (OFS). When insiders sell this much, ask why now.`); }
  if (k.rev_growth != null){ rparts.push([band(k.rev_growth, [[.2, 80], [0, 60], [null, 25]]), .15]);
    if (k.rev_growth < 0) rc.push(`Revenue fell ${pct(-k.rev_growth, 0)} last year. Weak operating performance is one of the clearest predictors of poor IPO returns.`); }
  if (k.peg != null){ rparts.push([band(-k.peg, [[-1, 85], [-2, 60], [-3, 40], [null, 25]]), .1]);
    (k.peg <= 1 ? rp : rc).push(k.peg <= 1 ? `PEG ${k.peg.toFixed(1)} (P/E ${k.pe.toFixed(0)} ÷ ${(k.pat_growth * 100).toFixed(0)}% profit growth): Lynch's "growth at a reasonable price".`
      : `PEG ${k.peg.toFixed(1)} (P/E ${k.pe.toFixed(0)} ÷ ${(k.pat_growth * 100).toFixed(0)}% profit growth). Lynch wanted under 1.`); }
  const ritter = {key:'ritter', short:'Ritter', name:'Jay Ritter (IPO Research)', score: rparts.length ? Math.round(wavg(rparts) * 10) / 10 : 50, pros: rp, cons: rc};

  // ── Bill Gurley lens ──
  const gp = [], gc = [], gparts = [];
  const m = k.gross_margin ?? k.ebitda_margin, mName = k.gross_margin != null ? 'Gross margin' : 'EBITDA margin (gross margin not entered)';
  if (m != null){ gparts.push([band(m, [[.7, 90], [.5, 70], [.3, 45], [null, 20]]), .25]); (m >= .5 ? gp : gc).push(`${mName} ${pct(m, 0)}${m >= .5 ? ': high-quality revenue (Gurley #5).' : '. Gurley: lower-margin revenue deserves a lower multiple (#5).'}`); }
  if (k.rev_growth != null){ gparts.push([band(k.rev_growth, [[.4, 90], [.25, 75], [.1, 55], [null, 30]]), .2]); (k.rev_growth >= .25 ? gp : gc).push(`Revenue growth ${pct(k.rev_growth, 0)} (#10)${k.rev_growth >= .25 ? '' : '. Steady, not fast'}.`); }
  if (k.ebitda_margin != null && k.ebitda_margin_prev != null){ const dlt = k.ebitda_margin - k.ebitda_margin_prev;
    gparts.push([dlt >= .05 ? 90 : dlt >= .01 ? 70 : dlt > -.01 ? 55 : 25, .2]);
    (dlt >= .01 ? gp : gc).push(dlt >= .01 ? `Margins up ${(dlt * 100).toFixed(1)} points as it grows: efficient scaling (#6).` : `Margins ${dlt > -.01 ? 'flat' : 'falling'} (${(dlt * 100).toFixed(1)} points). Gurley's #6 wants rising marginal profitability.`); }
  if (k.rev_up_every_year != null){ gparts.push([k.rev_up_every_year ? 85 : 40, .15]); (k.rev_up_every_year ? gp : gc).push(k.rev_up_every_year ? 'Revenue rose every year shown: predictable (#3).' : 'Revenue dipped in at least one year: less predictable (#3).'); }
  if (k.rule40 != null){ gparts.push([k.rule40 >= 40 ? 85 : k.rule40 >= 25 ? 60 : 30, .2]); (k.rule40 >= 40 ? gp : gc).push(`Rule of 40: ${k.rule40.toFixed(0)} (growth % + net margin %, a stand-in for free-cash-flow margin).`); }
  gc.push("Moat, network effects, switching costs, customer and partner concentration (Gurley #1, 2, 4, 7, 8): read the prospectus's business and risk-factor sections.");
  const gurley = {key:'gurley', short:'Gurley', name:'Bill Gurley (Revenue Quality)', score: gparts.length ? Math.round(wavg(gparts) * 10) / 10 : 50, pros: gp, cons: gc};

  // ── Valuation: two-stage DCF on net profit per share vs the band ──
  const v = {bear: null, base: null, bull: null, note: null, r, tg};
  if (pat > 0 && shares){
    const eps = pat / shares;                          // profit per share (both in ipo.unit)
    const gs = [k.pat_growth, k.rev_growth].filter(x => x != null);
    const g = clampN(gs.length ? Math.min(...gs) : .05, -.05, .25);
    v.growth = g; v.eps = eps;
    v.bear = dcfPS(eps, g > 0 ? g * .5 : g - .03, r, tg); v.base = dcfPS(eps, g, r, tg); v.bull = dcfPS(eps, Math.min(g * 1.5 + .02, .35), r, tg);
    v.mos = price ? (v.base - price) / v.base : null;
  } else v.note = pat != null && pat <= 0 ? 'Not meaningful: the company is loss-making.' : 'Enter net profit and share count to value it.';

  // ── Verdict ──
  const avg = (ritter.score + gurley.score) / 2;
  let label, why;
  if (pat != null && pat <= 0 && avg < 60){ label = 'SKIP'; why = 'Loss-making and not strong enough on IPO research or revenue quality to justify the risk.'; }
  else if ((k.ps != null && k.ps > 20) || (v.mos != null && v.mos < -0.6)){ label = 'WAIT (rich price)';
    why = 'Good business on the numbers, but at this price band the market is paying for much more growth than the company has shown. If you still like it, consider buying after listing if the price settles.'; }
  else if (pat != null && pat <= 0){ label = 'WAIT for listing';      // same guardrail as the IPO Desk: no "buy" while losing money
    why = 'Good revenue quality, but still loss-making. Ritter finds unprofitable IPOs have the worst long-run returns. Wait for listing and proof that losses are shrinking.'; }
  else if (avg >= 65 && (v.mos == null || v.mos >= -0.25)){ label = 'SUBSCRIBE candidate (small)'; why = 'Strong on IPO research and revenue quality at a price the numbers can support. If you apply, keep it small.'; }
  else if (avg >= 52){ label = 'WAIT for listing'; why = 'Decent, not compelling. Let it list and report a quarter or two, then decide at a known price.'; }
  else { label = 'SKIP'; why = 'Weak on IPO research and revenue quality at this price.'; }

  // ── Checklist ──
  const C = [];
  const dOpen = daysTo(ipo.open_date), dClose = daysTo(ipo.close_date), dList = daysTo(ipo.listing_date);
  if (ipo.close_date) C.push({label:'Subscription window', status: dClose < 0 ? 'info' : dClose <= 1 ? 'warn' : 'pass',
    detail: `${ipo.open_date || '?'} to ${ipo.close_date}` + (dClose < 0 ? ' (closed).' : dOpen > 0 ? ` (opens in ${dOpen} day${dOpen === 1 ? '' : 's'}).` : ` (closes ${dClose === 0 ? 'today' : 'in ' + dClose + ' day' + (dClose === 1 ? '' : 's')}).`)});
  if (ipo.listing_date) C.push({label:'Listing', status:'info', detail:`${ipo.listing_date} on ${ipo.exchange || 'exchange tbc'}${dList > 0 ? ` (in ${dList} days)` : ''}. After listing it moves to the IPO Desk automatically if a market symbol is set.`});
  if (mcap) C.push({label:'Valuation at the band', status: k.ps > 20 ? 'fail' : k.ps > 10 ? 'warn' : 'pass',
    detail:`${cm(ipo, k.mcap_low)}–${cm(ipo, mcap)} market value · P/E ${k.pe ? k.pe.toFixed(1) : '—'} · P/S ${k.ps ? k.ps.toFixed(1) : '—'}${k.ev_ebitda ? ' · EV/EBITDA ' + k.ev_ebitda.toFixed(1) : ''}.`});
  if (k.ofs_share != null) C.push({label:'Fresh issue vs selling shareholders', status: k.ofs_share <= .25 ? 'pass' : k.ofs_share <= .6 ? 'warn' : 'fail',
    detail:`${cm(ipo, ipo.fresh_issue || 0)} fresh, ${cm(ipo, ipo.ofs || 0)} offer-for-sale.`});
  if (ipo.use_of_proceeds || k.debt_share_of_proceeds != null) C.push({label:'Use of proceeds', status: k.debt_share_of_proceeds > .6 ? 'warn' : 'info',
    detail: (k.debt_share_of_proceeds > .6 ? `${pct(k.debt_share_of_proceeds, 0)} goes to repaying debt rather than growth. That makes the balance sheet safer, but adds nothing new to the business. ` : '') + (ipo.use_of_proceeds || '')});
  if (ipo.promoter_post_pct != null) C.push({label:'Promoter / founder stake after IPO', status: ipo.promoter_post_pct >= 50 ? 'pass' : ipo.promoter_post_pct >= 25 ? 'info' : 'warn',
    detail:`${ipo.promoter_post_pct}% retained: ${ipo.promoter_post_pct >= 50 ? 'strong skin in the game' : 'check who controls the company'}.`});
  if (pat != null) C.push({label:'Profitable', status: pat > 0 ? 'pass' : 'warn', detail:`Net profit ${cm(ipo, pat)}${k.pat_margin != null ? ` (${pct(k.pat_margin, 1)} margin)` : ''}.`});
  if (k.peg != null) C.push({label:'Price vs growth (PEG)', status: k.peg <= 1 ? 'pass' : k.peg <= 2 ? 'warn' : 'fail', detail:`${k.peg.toFixed(2)}: P/E ${k.pe.toFixed(1)} on ${(k.pat_growth * 100).toFixed(0)}% profit growth.`});
  if (ipo.anchor_amount) C.push({label:'Anchor investors', status:'info', detail:`${cm(ipo, ipo.anchor_amount)}${ipo.issue_size ? ` (${pct(ipo.anchor_amount / ipo.issue_size, 0)} of the issue)` : ''} committed by large institutions before the issue opened. A sign of demand, not of value: they can sell when their lock-in ends${ipo.lockup_end ? ` (${ipo.lockup_end}${ipo.lockup_end_2 ? ' and ' + ipo.lockup_end_2 : ''})` : ''}.`});
  C.push({label:'After listing', status:'info', detail:'Lock-up for pre-IPO investors and anchors typically ends a few months after listing; the prospectus has the exact terms. Prices often dip around then.'});
  C.push({label:'Read the prospectus', status:'info', detail:'Business, risk factors, related-party deals, litigation and lock-up terms. The numbers here were typed in from public sources; verify them.', link: ipo.prospectus_url || null});

  // ── Memo ──
  const lead = `${ipo.name}${ipo.exchange ? ` (${ipo.exchange})` : ''} ${ipo.about ? 'is ' + ipo.about.replace(/^\s*(is\s+)?/i, '').replace(/\.?\s*$/, '.') : 'is going public.'}` +
    (rev ? ` Revenue was ${cm(ipo, rev)}${k.rev_growth != null ? `, ${k.rev_growth >= 0 ? 'up' : 'down'} ${pct(Math.abs(k.rev_growth), 0)}` : ''}` : '') +
    (pat != null ? `, with ${cm(ipo, pat)} of net profit${k.pat_margin != null ? ` (${pct(k.pat_margin, 0)} margin)` : ''}.` : '.') +
    (mcap ? ` At ${cp(ipo, price)} a share it would be worth about ${cm(ipo, mcap)}.` : '');
  let val = v.base ? `On a simple cash-flow model (net profit as a stand-in for free cash flow, ${pct(v.growth, 0)} growth fading to ${pct(tg, 0)}, ${pct(r, 0)} discount rate) fair value is about ${cp(ipo, v.base)} a share (bear ${cp(ipo, v.bear)}, bull ${cp(ipo, v.bull)}) vs a price band of ${cp(ipo, priceLo)}–${cp(ipo, price)}. ` +
    (v.mos >= .25 ? `That's a ${pct(v.mos, 0)} margin of safety, which is rare for an IPO.` : v.mos >= 0 ? `A thin ${pct(v.mos, 0)} margin of safety.` :
     v.mos <= -1 ? `The band is ${(price / v.base).toFixed(1)}x the base-case value: the price assumes much faster growth than the company has shown.` : `The band is ${pct(-v.mos, 0)} above the base-case value, so you're paying for growth in advance.`)
    : v.note;
  if (k.pe) val += ` P/E ${k.pe.toFixed(1)}, P/S ${k.ps.toFixed(1)}${k.peg ? `, PEG ${k.peg.toFixed(1)}` : ''}.`;
  const watch = [];
  if (ipo.close_date && dClose >= 0) watch.push(`Subscription numbers by category, especially institutional (QIB / anchor) demand, before ${ipo.close_date}.`);
  watch.push('Grey-market or when-issued premiums are hype, not value. Ritter finds first-day moves don’t predict long-run returns.');
  if (k.rev_growth != null) watch.push(`Next results: revenue growth holding near ${pct(Math.max(k.rev_growth, 0), 0)}.`);
  if (k.debt_share_of_proceeds > .6) watch.push('Debt actually coming down after the issue, and interest savings showing up in profit.');
  (ipo.risks || []).slice(0, 4).forEach(x => watch.push(x));
  const plan = label.startsWith('SUBSCRIBE') ? 'If you apply, use money you won’t need for 5+ years and keep it a small position (a few % of the portfolio). Allotment isn’t guaranteed; don’t chase it on listing day.'
    : label.startsWith('WAIT (rich') ? `Skip the subscription. If you still like the business, put it on watch and revisit after listing.${v.base ? ` A price nearer ${cp(ipo, v.base * 1.1)} would line up with the base-case value.` : ''}`
    : label.startsWith('WAIT') ? 'Skip the subscription. Watch the first two quarterly results after listing, then decide at a known market price.'
    : 'Pass on this one.';
  const memo = {lead, bull: [...rp, ...gp].slice(0, 5), bear: [...rc, ...gc.filter(x => !x.startsWith('Moat, network'))].slice(0, 5), val, watch: watch.slice(0, 6), plan,
    buffett: 'Buffett almost never buys IPOs: the seller picks the time and the price. He wants years of public results first. Ritter & Welch (2002): US IPOs from 1980–2001 returned 22.6% over 3 years, 23.4 points below the market.'};
  // ── Strategy: what to actually do, step by step ──
  const lotCost = ipo.lot_size && price ? ipo.lot_size * price : null, strategy = [];
  strategy.push({h: 'Apply or not', t:
    label.startsWith('SUBSCRIBE') ? `Apply${lotCost ? ` for 1–2 lots (1 lot = ${ipo.lot_size} shares ≈ ${cp(ipo, lotCost)})` : ''}. Keep all your IPO money together under about 5% of the portfolio; when an issue is oversubscribed, allotment is a lottery anyway.`
    : label.startsWith('WAIT (rich') ? 'Don’t apply. The price band already assumes years of fast growth, so the odds favor waiting for a lower price after listing.'
    : label.startsWith('WAIT') ? 'Don’t apply. Nothing here is broken, but there’s no edge in buying before the market sets a price. Let it trade and report results first.'
    : 'Don’t apply. The numbers don’t support the risk.'});
  if (v.base) strategy.push({h: 'Buy zone after listing', t: `Fair value is about ${cp(ipo, v.base)} a share (bear ${cp(ipo, v.bear)}, bull ${cp(ipo, v.bull)}). A value buyer starts at ${cp(ipo, v.base * 0.75)} or lower, a 25% margin of safety${price && v.base * 0.75 < price ? ` (${pct(1 - v.base * 0.75 / price, 0)} below the top of the band)` : ''}. Between that and ${cp(ipo, v.base)}, buy in small steps. Above ${cp(ipo, v.bull)} you’re speculating, not investing.`});
  strategy.push({h: 'If you get shares', t: v.bull ? `If it lists above the bull-case value (${cp(ipo, v.bull)}), consider selling half to bank the gain and keep the rest only while the story holds. If it lists below the band, don’t average down until the first results confirm the numbers. Ritter: first-day pops don’t predict long-run returns.` : 'Don’t buy more or sell on day one; first-day moves are noise. Decide after the first quarterly results.'});
  const lk = ipo.lockup_end ? `Anchor lock-in ends ${ipo.lockup_end}${ipo.lockup_end_2 ? ` (half) and ${ipo.lockup_end_2} (the rest)` : ''}`
    : ipo.currency === 'INR' ? 'Anchor investors’ lock-in ends 30 days (half) and 90 days (the rest) after allotment' : 'The insider lock-up usually ends about 180 days after listing';
  strategy.push({h: 'Mark the lock-up dates', t: `${lk}. Big holders can sell from then, and prices often dip around these dates: a second, usually cheaper, chance to buy if you still like it.`});
  const trig = [];
  if (k.rev_growth != null) trig.push(`revenue growth drops below ${pct(Math.max(k.rev_growth / 2, 0.03), 0)}`);
  if (k.pat_margin != null && k.pat_margin > 0) trig.push(`net margin falls under ${pct(Math.max(k.pat_margin - 0.05, 0), 0)}`);
  if (k.debt_share_of_proceeds > 0.3) trig.push('debt climbs back up after the IPO money pays it down');
  if (pat != null && pat <= 0) trig.push('losses don’t shrink over the next two reports');
  strategy.push({h: 'Re-check or sell if', t: trig.length ? trig.join('; ') + '. Any of these means the story behind the price has changed.' : 'the next two quarterly reports miss the growth the prospectus implied.'});
  return {ipo, k, lenses: [ritter, gurley], overall: {label, rationale: why, score: Math.round(avg * 10) / 10}, valuation: v, checklist: C, memo, strategy, price, priceLo};
}

// ── UI ──
const ubc = l => /^SUBSCRIBE/.test(l) ? 'b-buy' : /^WAIT \(rich/.test(l) ? 'b-hold' : /^WAIT/.test(l) ? 'b-research' : 'b-pass';
function upCard(a){
  const i = a.ipo, dC = daysTo(i.close_date), dO = daysTo(i.open_date);
  const when = dC == null ? '' : dC < 0 ? (i.listing_date && daysTo(i.listing_date) >= 0 ? `lists ${i.listing_date}` : 'subscription closed') : dO > 0 ? `opens in ${dO}d` : dC === 0 ? 'closes today' : `closes in ${dC}d`;
  return `<div class="card" onclick="openUp('${esc(i.id)}')">
    <div class="top"><div><div class="tk" style="font-family:Fraunces,serif;font-size:17px">${esc(i.name)}</div>
      <div class="nm">${esc([i.exchange, i.currency].filter(Boolean).join(' · '))}</div><div class="price">${cp(i, a.priceLo)}–${cp(i, a.price)}</div></div>${ring(a.overall.score)}</div>
    <div class="tags"><span class="badge ${ubc(a.overall.label)}">${esc(a.overall.label)}</span>${when ? `<span class="mini ${dC != null && dC >= 0 && dC <= 1 ? 'warn' : ''}">${esc(when)}</span>` : ''}${a.k.ps ? `<span class="mini">${a.k.ps.toFixed(1)}x sales</span>` : ''}${a.k.pe ? `<span class="mini">P/E ${a.k.pe.toFixed(0)}</span>` : ''}</div>
    <div class="bars">${a.lenses.map(l => `<div class="bar"><span>${l.short}</span><div class="track"><i style="width:${l.score}%;background:${COL[l.key]}"></i></div><span>${Math.round(l.score)}</span></div>`).join('')}</div>
    ${i.draft ? '<div class="note" style="color:var(--hold)">● draft: only in this browser</div>' : ''}</div>`;
}
// Saved IPOs plus this browser's drafts. A draft wins over the saved version when it's a newer edit;
// drafts that match the saved copy, or whose IPO has since listed, are cleaned up.
function upList(){
  const drafts = store.get('ltl-up-drafts', []), byId = Object.fromEntries(UPCOMING.map(u => [u.id, u]));
  const strip = x => { const c = {...x}; delete c.draft; delete c.moved_to_ipo_desk; return JSON.stringify(c); };
  const keep = drafts.filter(d => { const u = byId[d.id]; return !u || (!u.moved_to_ipo_desk && strip(u) !== strip(d) && (d.updated || '') >= (u.updated || '')); });
  if (keep.length !== drafts.length) store.set('ltl-up-drafts', keep);
  const ids = new Set(keep.map(d => d.id));
  return [...keep.map(d => ({...d, draft: true})), ...UPCOMING.filter(u => !ids.has(u.id))].filter(u => !u.moved_to_ipo_desk);
}
function renderUpcoming(){
  const q = ($('#upQ') ? $('#upQ').value : '').trim(), ql = q.toLowerCase();
  const every = upList(), all = every.filter(u => !ql || (u.name || '').toLowerCase().includes(ql) || (u.symbol || '').toLowerCase().includes(ql));
  const req = $('#upReq');
  if (req){
    if (q.length >= 2 && !all.length){
      req.innerHTML = `<p><b>${esc(q)}</b> isn’t on the list yet. Extract it from an IPO page (Chittorgarh, Groww, news) or the prospectus and get the full analysis and strategy in seconds.</p><button class="btn ipo" onclick='upX(${JSON.stringify(q)})'>⤓ Extract ${esc(q)}</button>`;
      req.classList.add('on');
    } else req.classList.remove('on');
  }
  const list = all.map(analyzeUpcoming).sort((a, b) => (daysTo(a.ipo.close_date) ?? 999) - (daysTo(b.ipo.close_date) ?? 999));
  $('#upGrid').innerHTML = list.length ? list.map(upCard).join('') : q ? '' : '<div class="empty">No upcoming IPOs yet. Click <b>⤓ Extract IPO</b>.</div>';
  $('#cUp').textContent = every.length;
}
function findUp(id){ return upList().find(u => u.id === id) || UPCOMING.find(u => u.id === id); }
function openUp(id, given){
  const ipo = given || findUp(id); if (!ipo) return;
  const a = analyzeUpcoming(ipo), k = a.k, v = a.valuation;
  DRAWER_ITEM = {kind: 'up', ipo};
  if (!given) history.replaceState(null, '', '#up:' + id);
  $('#dT').innerHTML = `${esc(ipo.name)} <span class="mono" style="font-size:14px;color:var(--mute)">${esc(ipo.symbol || '')}</span>`;
  $('#dS').textContent = ['Upcoming IPO', ipo.exchange, ipo.sector, `price band ${cp(ipo, a.priceLo)}–${cp(ipo, a.price)}`, ipo.lot_size ? `lot ${ipo.lot_size}` : ''].filter(Boolean).join('  ·  ');
  const li = (arr, cls) => `<ul class="${cls}">${arr.map(x => `<li>${esc(x)}</li>`).join('') || '<li class="muted">Nothing notable.</li>'}</ul>`;
  const yrs = ipo.years || (ipo.revenue || []).map((_, j, arr) => `Y-${arr.length - 1 - j}`);
  const fin = `<div style="overflow-x:auto"><table><thead><tr><th></th>${yrs.map(y => `<th class="n">${esc(y)}</th>`).join('')}</tr></thead><tbody>
    ${[['Revenue', ipo.revenue], ['EBITDA', ipo.ebitda], ['Net profit', ipo.net_profit]].filter(([, arr]) => arr && arr.length).map(([n, arr]) => `<tr><td>${n}</td>${yrs.map((_, j) => `<td class="n">${cm(ipo, arr[j])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  const KR = (n, val) => `<div class="kr"><span>${n}</span><b>${val}</b></div>`;
  const vr = v.base ? (() => { const pts = [v.bear, v.base, v.bull, a.price, a.priceLo]; const lo = Math.min(...pts) * .9, hi = Math.max(...pts) * 1.08, pos = x => ((x - lo) / (hi - lo) * 100).toFixed(1);
    return `<div class="vr"><div class="ln"></div><div class="mk" style="left:${pos(v.bear)}%">Bear<b>${cp(ipo, v.bear)}</b></div><div class="mk" style="left:${pos(v.base)}%">Base<b>${cp(ipo, v.base)}</b></div><div class="mk" style="left:${pos(v.bull)}%">Bull<b>${cp(ipo, v.bull)}</b></div>
      <div class="mk pr" style="left:${pos(a.price)}%">Band top ${cp(ipo, a.price)}</div></div>
      <p class="muted" style="font-size:12px;margin-top:28px">Two-stage DCF on net profit per share (${cp(ipo, v.eps)}): ${pct(v.growth, 0)} growth for 5 years, fading to ${pct(v.tg, 0)}; ${pct(v.r, 0)} discount rate${ipo.currency === 'INR' ? ' (higher for rupee assets: Indian rates and inflation run above US levels)' : ''}. Net profit stands in for free cash flow, which prospectuses rarely state, so treat this as a rough check.</p>`; })()
    : `<p class="muted">${esc(v.note)}</p>`;
  $('#dB').innerHTML = `
    <div class="sec verdict">${ring(a.overall.score, 88)}<div style="flex:1;min-width:240px"><span class="badge ${ubc(a.overall.label)}">${esc(a.overall.label)}</span>
      <p style="margin-top:8px;color:var(--soft)">${esc(a.overall.rationale)}</p>
      <p class="muted" style="font-size:12px;margin-top:6px">From prospectus numbers entered ${esc(ipo.updated || '')}${ipo.added_by ? ' by ' + esc(ipo.added_by) : ''}${ipo.draft ? ' · <b style="color:var(--hold)">draft, only in this browser</b>' : ''}</p></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn" onclick='editUp(${JSON.stringify(ipo.id)})'>✎ Edit numbers</button>${ipo.draft ? `<button class="btn primary" onclick='saveUp(${JSON.stringify(ipo.id)})'>Save for both of us ↗</button>` : ''}</div></div>
    <div class="sec"><h4>🎯 Strategy</h4><div class="strat">${a.strategy.map((s, i) => `<div class="st"><b>${i + 1}. ${esc(s.h)}</b><span>${esc(s.t)}</span></div>`).join('')}</div></div>
    <div class="sec"><h4>📝 Research memo</h4><div class="memo"><div class="lead">${esc(a.memo.lead)}</div>
      <div class="cols"><div class="box"><h5 style="color:var(--buy)">Why it could work</h5>${li(a.memo.bull, 'p')}</div><div class="box"><h5 style="color:var(--pass)">What worries us</h5>${li(a.memo.bear, 'c')}</div></div>
      <div><b style="color:var(--text)">Valuation.</b> ${esc(a.memo.val)}</div>
      <div class="box"><h5 style="color:var(--gold)">What to watch</h5>${li(a.memo.watch, 'w')}</div>
      <div class="plan"><b>If we act on it:</b> ${esc(a.memo.plan)}</div>
      <div class="muted" style="font-size:12.5px"><b style="color:var(--soft)">Buffett's view:</b> ${esc(a.memo.buffett)}</div></div></div>
    <div class="sec"><h4>🚦 IPO checklist</h4><div class="check">${a.checklist.map(c => `<div class="ci"><div class="s s-${c.status}">${{pass:'✓', warn:'!', fail:'✕', info:'i'}[c.status]}</div><b>${esc(c.label)}</b><span>${esc(c.detail)}${c.link ? ` <a href="${esc(c.link)}" target="_blank" rel="noopener" style="color:var(--research)">Open ↗</a>` : ''}</span></div>`).join('')}</div></div>
    <div class="sec"><h4>IPO experts</h4><div class="lenses">${a.lenses.map(l => `<div class="lens"><div class="h"><span class="n" style="color:${COL[l.key]}">${esc(l.name.split(' (')[0])}</span><span class="s">${Math.round(l.score)}</span></div>
      <div class="vd">${esc(l.name.split('(')[1].replace(')', ''))}</div><ul>${l.pros.map(p => `<li class="p">${esc(p)}</li>`).join('')}${l.cons.map(c => `<li class="c">${esc(c)}</li>`).join('')}</ul></div>`).join('')}</div></div>
    <div class="sec"><h4>📊 Key numbers at the top of the band</h4><div class="kgroups">
      <div class="kg"><h5>Valuation</h5>${KR('Market value', cm(ipo, k.mcap))}${KR('P/E', num(k.pe, 1))}${KR('Price / sales', num(k.ps, 1))}${KR('EV / EBITDA', num(k.ev_ebitda, 1))}${KR('PEG', num(k.peg, 2))}</div>
      <div class="kg"><h5>Growth & margins</h5>${KR('Revenue growth', pct(k.rev_growth))}${KR('Profit growth', pct(k.pat_growth))}${KR('EBITDA margin', pct(k.ebitda_margin))}${KR('Net margin', pct(k.pat_margin))}${KR('Rule of 40', num(k.rule40, 0))}</div>
      <div class="kg"><h5>The offer</h5>${KR('Issue size', cm(ipo, ipo.issue_size))}${KR('Fresh issue', cm(ipo, ipo.fresh_issue))}${KR('Offer for sale', cm(ipo, ipo.ofs))}${KR('Shares after IPO', k.shares ? Number(k.shares).toLocaleString(undefined, {maximumFractionDigits: 1}) + ' ' + esc(ipo.unit) : '—')}${KR('Promoter stake after', ipo.promoter_post_pct != null ? ipo.promoter_post_pct + '%' : '—')}</div>
    </div></div>
    <div class="sec"><h4>Financials (${esc(ipo.unit)} ${esc(ipo.currency)})</h4>${fin}</div>
    <div class="sec"><h4>💰 Value vs price band</h4>${vr}</div>
    ${(ipo.sources || []).length ? `<div class="sec news"><h4>Sources</h4>${ipo.sources.map(s => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title || s.url)}</a>`).join('')}</div>` : ''}
    ${ipo.notes ? `<div class="sec"><h4>Notes</h4><p class="muted" style="font-size:12.5px">${esc(ipo.notes)}</p></div>` : ''}`;
  $('#drawer').classList.add('on'); $('#shade').classList.add('on'); $('#drawer').setAttribute('aria-hidden', 'false'); $('#drawer').scrollTop = 0;
}

// ── Entry form ──
const UP_FIELDS = [
  ['Company', [['name', 'Company name', 'text', 'Jio Platforms'], ['symbol', 'Expected ticker', 'text', 'JIOPLAT'], ['yahoo', 'Market symbol after listing (Yahoo)', 'text', 'e.g. JIO.NS', 'Used to move it to the IPO Desk on listing day. India: add .NS'],
    ['exchange', 'Exchange', 'text', 'NSE, BSE'], ['sector', 'Sector', 'text', 'Telecom & digital'], ['about', 'What the company does (one line)', 'text', "India's largest telecom and digital services company"]]],
  ['Money units', [['currency', 'Currency', 'select', ['USD', 'INR', 'EUR', 'GBP', 'CAD', 'AUD', 'HKD', 'JPY', 'CNY', 'SGD', 'CHF']], ['unit', 'All amounts and share counts in', 'select', ['million', 'crore', 'billion', 'lakh', 'thousand']]]],
  ['Dates', [['open_date', 'Subscription opens', 'date'], ['close_date', 'Subscription closes', 'date'], ['listing_date', 'Listing date', 'date'], ['lockup_end', 'Anchor lock-in ends (first half)', 'date'], ['lockup_end_2', 'Anchor lock-in ends (rest)', 'date']]],
  ['The offer', [['price_low', 'Price band low (per share)', 'number'], ['price_high', 'Price band high (per share)', 'number'], ['lot_size', 'Lot / minimum shares', 'number'],
    ['issue_size', 'Total issue size', 'number'], ['fresh_issue', 'Fresh issue (new money to company)', 'number'], ['ofs', 'Offer for sale (existing holders selling)', 'number'],
    ['shares_post', 'Total shares after IPO', 'number', '', 'If unknown, fill the next two instead'], ['fresh_shares', 'New shares issued', 'number'], ['pct_sold', '% of company sold in IPO', 'number'], ['anchor_amount', 'Raised from anchor investors', 'number']]],
  ['Financials (oldest → latest, comma-separated)', [['years', 'Year labels', 'text', 'FY24, FY25, FY26'], ['revenue', 'Revenue', 'text', '110000, 128218, 146885'], ['ebitda', 'EBITDA', 'text'], ['net_profit', 'Net profit', 'text'], ['gross_margin', 'Gross margin % (optional)', 'number']]],
  ['Balance sheet & ownership', [['debt', 'Total debt before IPO', 'number'], ['cash', 'Cash before IPO', 'number'], ['proceeds_debt', 'Proceeds used to repay debt', 'number'], ['promoter_post_pct', 'Promoter / founder stake after IPO (%)', 'number']]],
  ['Context', [['use_of_proceeds', 'Use of proceeds', 'text'], ['risks', 'Key risks (one per line)', 'textarea'], ['prospectus_url', 'Prospectus link (S-1 / RHP)', 'url'], ['sources', 'Other sources (one URL per line)', 'textarea'], ['notes', 'Notes', 'textarea'], ['added_by', 'Your name (optional)', 'text']]]
];
function upForm(ipo = {}){
  const val = (k) => { const x = ipo[k]; if (x == null) return ''; if (Array.isArray(x)) return k === 'risks' ? x.join('\n') : k === 'sources' ? x.map(s => s.url).join('\n') : x.join(', '); return x; };
  $('#upFormBody').innerHTML = UP_FIELDS.map(([g, fs]) => `<fieldset><legend>${g}</legend><div class="fgrid">${fs.map(([k, label, type, ph, hint]) =>
    `<label class="fld ${type === 'textarea' || k === 'about' || k === 'use_of_proceeds' ? 'wide' : ''}"><span>${label}</span>${
      type === 'select' ? `<select data-k="${k}">${ph.map(o => `<option ${String(val(k) || (k === 'currency' ? 'USD' : 'million')) === o ? 'selected' : ''}>${o}</option>`).join('')}</select>`
      : type === 'textarea' ? `<textarea data-k="${k}" rows="3">${esc(val(k))}</textarea>`
      : `<input data-k="${k}" type="${type}" ${type === 'number' ? 'step="any"' : ''} value="${esc(val(k))}" placeholder="${esc(type === 'select' ? '' : (ph || ''))}">`}${hint ? `<small>${hint}</small>` : ''}</label>`).join('')}</div></fieldset>`).join('');
  $('#upForm').dataset.id = ipo.id || '';
  $('#upForm').classList.add('on'); $('#shade').classList.add('on'); $('#upFormBody').scrollTop = 0;
}
function closeUpForm(){ $('#upForm').classList.remove('on'); if (!$('#drawer').classList.contains('on') && !$('#review').classList.contains('on')) $('#shade').classList.remove('on'); }
function readUpForm(){
  const o = {}; const nums = s => String(s).split(/[,\s]+/).filter(Boolean).map(x => parseFloat(x.replace(/[^0-9.\-]/g, ''))).filter(x => isFinite(x));
  $('#upFormBody').querySelectorAll('[data-k]').forEach(el => {
    const k = el.dataset.k, v = el.value.trim(); if (v === '') return;
    if (['revenue', 'ebitda', 'net_profit'].includes(k)) o[k] = nums(v);
    else if (k === 'years') o[k] = v.split(',').map(x => x.trim()).filter(Boolean);
    else if (k === 'risks') o[k] = v.split('\n').map(x => x.trim()).filter(Boolean).slice(0, 8);
    else if (k === 'sources') o[k] = v.split('\n').map(x => x.trim()).filter(x => /^https?:\/\//.test(x)).slice(0, 8).map(url => ({url, title: url.replace(/^https?:\/\/(www\.)?/, '').split('/')[0]}));
    else if (el.type === 'number') { const n = parseFloat(v); if (isFinite(n)) o[k] = n; }
    else o[k] = v.slice(0, 400);
  });
  if (!o.name){ alertUp('Enter the company name.'); return null; }
  if (!o.price_high && !o.price_low){ alertUp('Enter the price band.'); return null; }
  o.id = $('#upForm').dataset.id || (o.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') + '-' + (o.close_date || new Date().toISOString().slice(0, 10)).slice(0, 7));
  o.updated = new Date().toISOString().slice(0, 10);
  return o;
}
function alertUp(m){ $('#upMsg').textContent = m; setTimeout(() => $('#upMsg').textContent = '', 5000); }
function analyzeUpForm(){
  const o = readUpForm(); if (!o) return;
  const d = store.get('ltl-up-drafts', []).filter(x => x.id !== o.id); d.unshift(o); store.set('ltl-up-drafts', d.slice(0, 20));
  closeUpForm(); renderUpcoming(); openUp(o.id, {...o, draft: !UPCOMING.some(u => u.id === o.id && JSON.stringify(u) === JSON.stringify(o))});
}
function editUp(id){ const ipo = findUp(id); closeD(); upForm(ipo || {}); }
function saveUp(id){
  const ipo = store.get('ltl-up-drafts', []).find(u => u.id === id) || findUp(id); if (!ipo) return;
  const clean = {...ipo}; delete clean.draft;
  const title = encodeURIComponent('Add upcoming IPO: ' + ipo.name);
  const body = encodeURIComponent('Saves this upcoming IPO to Long-Term Lab so both of us see it. Just press "Submit new issue".\n\n```json\n' + JSON.stringify(clean, null, 1) + '\n```\n');
  window.open(`https://github.com/${REPO}/issues/new?title=${title}&body=${body}`, '_blank', 'noopener');
}

// ── Extract: read an IPO page, prospectus, Word file or screenshot and analyze it ──
const XLABEL = {name: 'company name', price_high: 'price band', lot_size: 'lot size', close_date: 'subscription dates', issue_size: 'issue size',
  shares_post: 'total shares after the IPO', revenue: 'revenue', net_profit: 'net profit', ebitda: 'EBITDA', promoter_post_pct: 'promoter stake after the IPO'};
function upX(name){
  $('#xName').value = name || ($('#upQ') ? $('#upQ').value.trim() : '');
  $('#xText').value = ''; $('#xUrl').value = ''; $('#xMsg').textContent = '';
  upXLinks(); $('#upX').classList.add('on'); $('#shade').classList.add('on');
}
function closeUpX(){ $('#upX').classList.remove('on'); if (!$('#drawer').classList.contains('on') && !$('#upForm').classList.contains('on')) $('#shade').classList.remove('on'); }
function upXLinks(){
  const n = $('#xName').value.trim(), q = encodeURIComponent(`"${n || 'upcoming'}" IPO`);
  $('#xLinks').innerHTML = [['Chittorgarh (India, most complete)', `https://www.google.com/search?q=${q}+site%3Achittorgarh.com`],
    ['Groww / Zerodha', `https://www.google.com/search?q=${q}+site%3Agroww.in+OR+site%3Azerodha.com`],
    ['US: SEC prospectus (S-1 / F-1)', `https://www.sec.gov/edgar/search/#/q=${encodeURIComponent('"' + (n || '') + '"')}&forms=S-1,F-1,424B4`],
    ['News', `https://www.google.com/search?q=${q}+price+band&tbm=nws`]]
    .map(([t, u]) => `<a class="btn" target="_blank" rel="noopener" href="${u}">${t} ↗</a>`).join('');
}
async function upXFile(input){
  const f = input.files[0]; input.value = ''; if (!f) return;
  const ext = (f.name.split('.').pop() || '').toLowerCase(), say = t => $('#xMsg').textContent = t;
  try{
    let text = '';
    say('Reading ' + f.name + '…');
    if (ext === 'pdf'){ await loadScript(LIBS.pdf); pdfjsLib.GlobalWorkerOptions.workerSrc = LIBS.pdfw;
      const doc = await pdfjsLib.getDocument({data: await f.arrayBuffer()}).promise, n = Math.min(doc.numPages, 80), lines = [];
      for (let p = 1; p <= n; p++){ if (p % 10 === 0) say(`Reading page ${p} of ${n}…`); lines.push(...groupLines((await (await doc.getPage(p)).getTextContent()).items)); }
      text = lines.join('\n'); if (doc.numPages > n) say(`Read the first ${n} of ${doc.numPages} pages (the summary and financials are near the front).`); }
    else if (ext === 'docx'){ await loadScript(LIBS.mammoth); text = (await mammoth.extractRawText({arrayBuffer: await f.arrayBuffer()})).value; }
    else if (['png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif'].includes(ext)){ await loadScript(LIBS.tess); say('Reading text from the image (OCR). This takes 10–40 seconds…');
      text = (await Tesseract.recognize(f, 'eng')).data.text; }
    else if (['html', 'htm', 'mhtml'].includes(ext)){ const d = new DOMParser().parseFromString(await f.text(), 'text/html'); d.querySelectorAll('script,style,noscript').forEach(e => e.remove()); text = d.body.innerText || d.body.textContent; }
    else if (['txt', 'md', 'csv', 'json'].includes(ext)) text = await f.text();
    else throw new Error('Use a PDF, Word (.docx), screenshot, saved web page (.html) or text file.');
    $('#xText').value = ($('#xText').value ? $('#xText').value + '\n\n' : '') + text;
    if (!/^Read the first/.test($('#xMsg').textContent)) say(`Read ${f.name}. Click Extract & analyze.`);
  }catch(e){ say(e.message || 'Could not read that file.'); }
}
function runUpX(){
  const text = $('#xText').value;
  if (text.trim().length < 60){ $('#xMsg').textContent = 'Paste the page text or add a file first.'; return; }
  const r = extractIpo(text, {name: $('#xName').value.trim() || null, url: $('#xUrl').value.trim()}), o = r.ipo;
  o.updated = new Date().toISOString().slice(0, 10);
  if (o.name) o.id = o.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') + '-' + (o.close_date || o.updated).slice(0, 7);
  o.notes = 'Extracted automatically from ' + (o.sources ? o.sources[0].url : 'pasted text / a file') + ' on ' + o.updated + '. Check the numbers against the prospectus.';
  const banner = `<div class="xban"><b>⤓ Extracted ${r.found.length} fields.</b> ${r.missing.length ? `Not found: <b>${r.missing.map(k => XLABEL[k] || k).join(', ')}</b>. ` : 'Everything the analysis needs was found. '}
    ${r.warnings.map(w => `<div class="muted">• ${esc(w)}</div>`).join('')}
    <div style="margin-top:8px">Check the numbers with <b>✎ Edit numbers</b>${r.missing.includes('shares_post') ? ' (the share count matters most: without it there is no valuation; Chittorgarh lists it as "Share Holding Post Issue")' : ''}, then <b>Save for both of us</b> so your friend sees it.</div></div>`;
  closeUpX();
  if (o.name && (o.price_high || o.price_low)){
    const d = store.get('ltl-up-drafts', []).filter(x => x.id !== o.id); d.unshift(o); store.set('ltl-up-drafts', d.slice(0, 20));
    if ($('#upQ')) $('#upQ').value = '';
    renderUpcoming(); openUp(o.id, {...o, draft: true});
    $('#dB').insertAdjacentHTML('afterbegin', banner);
  } else {
    upForm(o); $('#upForm').dataset.id = '';
    $('#upFormBody').insertAdjacentHTML('afterbegin', banner.replace('Check the numbers with <b>✎ Edit numbers</b>', 'Fill in the missing ones below and click <b>Analyze</b>'));
  }
}
