// Run: node tests/test_importer.js   (no installs needed)
// Synthetic data only. No real statements, names or account numbers belong in this repo.
const I = require('../docs/importer.js');
let fail = 0;
const fmt = r => r.rows.map(x => [x.ticker, x.shares, x.price ?? '-', x.cost ?? '-'].join(' ')).join(' ; ');
function check(name, res, expected) {
  const got = fmt(res), ok = got === expected; if (!ok) fail++;
  console.log((ok ? 'ok   ' : 'FAIL ') + name + (ok ? '' : `\n     got      ${got}\n     expected ${expected}`));
}
// Broker CSV with totals, money market and a class-B share
check('broker csv', I.extract({ tables: [[
  ['Account', 'Symbol', 'Description', 'Quantity', 'Last Price', 'Current Value', 'Cost Basis Total'],
  ['X1', 'AAPL', 'APPLE INC', '10', '$230.00', '$2,300.00', '$1,500.00'],
  ['X1', 'SPAXX**', 'MONEY MARKET', '500', '$1', '$500', ''],
  ['X1', 'BRK.B', 'BERKSHIRE', '2', '$480', '$960', '$700'],
  ['', 'Total', '', '', '', '$3,760', '']]] }), 'AAPL 10 230 150 ; BRK-B 2 480 350');
// PDF statement laid out in columns: holdings, an open option, then a trade-history table that must be ignored
const W = (str, x, y) => ({ str, x, y, w: str.length * 5, h: 9 });
const page = [
  ['Securities Held in Account', 40], ['Sym/Cusip', 200], ['Acct Type', 260], ['Qty', 330], ['Price', 400], ['Mkt Value', 470]].map(([s, x]) => W(s, x, 700))
  .concat([['ABC Corp', 40], ['ABC', 200], ['Margin', 260], ['3', 330], ['$10.00', 400], ['$30.00', 470]].map(([s, x]) => W(s, x, 680)))
  .concat([['XYZ 10/07/2026 Call $50.00', 40]].map(([s, x]) => W(s, x, 660)))
  .concat([['XYZ', 200], ['Margin', 260], ['1', 330], ['$2.00', 400], ['$200.00', 470]].map(([s, x]) => W(s, x, 650)))
  .concat([['Description', 40], ['Symbol', 200], ['Transaction', 260], ['Qty', 330], ['Price', 400], ['Debit', 470]].map(([s, x]) => W(s, x, 600)))
  .concat([['Bought', 40], ['ABC', 200], ['Buy', 260], ['3', 330], ['$9.00', 400], ['$27.00', 470]].map(([s, x]) => W(s, x, 580)));
const pdf = I.extract({ items: [page] });
check('pdf columns, option + history skipped', pdf, 'ABC 3 10 -');
console.log('     skipped:', pdf.skipped.map(s => s.reason).join(' | '));
check('json alpaca', I.extract({ json: [{ symbol: 'MSFT', qty: '3', avg_entry_price: '400', current_price: '420', market_value: '1260' }] }), 'MSFT 3 420 400');
check('json nested', I.extract({ json: { account: { positions: [{ instrument: { symbol: 'AMZN' }, quantity: 4, average_buy_price: 150 }] } } }), 'AMZN 4 - 150');
check('json site backup', I.extract({ json: [{ ticker: 'NVDA', shares: 2, cost: 120, price: 180 }] }), 'NVDA 2 180 120');
check('phone screenshot cards', I.extract({ lines: ['Stocks', 'NVDA $228.38', '1.03 shares', 'SNOW $339.56', '2.5 shares', 'Buying power $1.99'] }), 'NVDA 1.03 228.38 - ; SNOW 2.5 339.56 -');
check('qty x price = value', I.extract({ lines: ['AAPL Apple 10 230.00 2,300.00'] }), 'AAPL 10 230 -');
check('labels @ cost', I.extract({ lines: ['GLD 1.7 @ 380.84 cost 300'] }), 'GLD 1.7 380.84 300');
check('legacy TICKER shares cost', I.extract({ lines: ['AAPL 10 150', 'KO 5'] }), 'AAPL 10 - 150 ; KO 5 - -');
check('fine print ignored', I.extract({ lines: ['Member SIPC 123 Main St Suite 400', 'FINRA 2026 report 12', 'Page 1 of 20'] }), '');
check('same ticker merged', I.extract({ lines: ['AAPL 10 shares @ 200', 'AAPL 5 shares @ 200'] }), 'AAPL 15 200 -');
// Two accounts at one broker: same stock stays as two lots, only last 4 digits of the account kept, broker named from fine print
const two = I.extract({ tables: [[['Account Number', 'Symbol', 'Quantity', 'Last Price', 'Current Value'],
  ['Z00001111', 'NVDA', '6', '$200', '$1,200'], ['Z00002222', 'NVDA', '0.5', '$200', '$100'], [''], ['Brokerage services are provided by Fidelity Brokerage Services LLC']]] });
check('two accounts kept apart', two, 'NVDA 6 200 - ; NVDA 0.5 200 -');
const accOk = two.rows.map(r => r.acct).join(',') === '1111,2222' && two.broker === 'Fidelity'; if (!accOk) fail++;
console.log((accOk ? 'ok   ' : 'FAIL ') + 'account last-4 + broker name: ' + two.rows.map(r => r.acct).join(',') + ' / ' + two.broker);
console.log(fail ? `${fail} FAILED` : 'all passed'); process.exit(fail ? 1 : 0);
