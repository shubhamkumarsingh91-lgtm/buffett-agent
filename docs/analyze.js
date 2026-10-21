// analyze.js — "⚡ Analyze now": type any ticker in a desk's search box and get the full analysis
// on the site in about a minute, without opening GitHub.
//
// How: browsers can't fetch Yahoo/SEC data directly, so the Python engine runs on GitHub's free
// servers (.github/workflows/analyze.yml). This file starts that run through GitHub's API with a
// key saved once in this browser, shows live progress, then loads the new result and opens it.
//
// Independent personal project, not tied to any employer or agency. Public market data only,
// no internal or personal data (no SSNs/PHI). Educational research, not financial advice.

const GH_KEY = 'ltl-gh-token', WF = 'analyze.yml';
let JOB = null;
const ghToken = () => { try { return localStorage.getItem(GH_KEY) || ''; } catch (e) { return ''; } };
const ghSave = t => { try { t ? localStorage.setItem(GH_KEY, t) : localStorage.removeItem(GH_KEY); } catch (e) {} };
const gh = (path, opts = {}) => fetch(`https://api.github.com/repos/${REPO}${path}`, {...opts, cache: 'no-store',
  headers: {Accept: 'application/vnd.github+json', Authorization: 'Bearer ' + ghToken(), 'X-GitHub-Api-Version': '2022-11-28', ...(opts.headers || {})}});
const ghError = s => s === 401 ? 'GitHub rejected the saved key (expired or mistyped). Paste a new one.'
  : s === 403 || s === 404 ? 'The key doesn’t have permission to run this site’s analyzer. It needs Actions: Read and write on buffett-agent.'
  : s === 422 ? 'The analyzer isn’t on the site yet. Merge the latest pull request first.'
  : `GitHub returned an error (${s}). Try again in a minute.`;

// ── Request box shown under the search when the ticker isn't on this desk ──
function reqHtml(qu, D, otherBtn, onOtherDesk){
  const title = encodeURIComponent((view === 'ipo' ? 'Analyze IPO: ' : 'Analyze: ') + qu);
  const body = encodeURIComponent(`Please add ${qu} to the ${D.title}.\n\nJust press "Submit new issue".`);
  return `<p><b class="mono">${esc(qu)}</b> isn't on the ${D.title} yet.${onOtherDesk ? ` It's on the ${DESKS[onOtherDesk].title}.` : ' Analyze it now and the result opens here in about a minute.'}</p>${otherBtn}
    <button class="btn ${D.btn}" onclick="analyzeNow('${esc(qu)}','${view}')">⚡ Analyze ${esc(qu)} now</button>
    <a class="muted" style="font-size:12px" target="_blank" rel="noopener" href="https://github.com/${REPO}/issues/new?title=${title}&body=${body}">or request on GitHub ↗</a>`;
}

// ── Live progress panel ──
function jobShow(html, kind = ''){
  const el = $('#job'); if (!el) return;
  el.className = 'job on ' + kind; el.innerHTML = html;
}
function jobLine(stage, detail){
  const s = JOB ? Math.round((Date.now() - JOB.start) / 1000) : 0;
  const steps = ['Starting', 'Waiting for a server', 'Fetching data & scoring', 'Loading the result'];
  const i = steps.indexOf(stage);
  jobShow(`<div class="jh"><b>⚡ Analyzing <span class="mono">${esc(JOB.list.join(', '))}</span> for the ${DESKS[JOB.desk].title}</b><span class="muted">${s}s · usually ${JOB.list.length > 3 ? 'a minute or two' : 'about a minute'}</span></div>
    <div class="steps">${steps.map((x, j) => `<span class="${j < i ? 'done' : j === i ? 'now' : ''}">${j < i ? '✓' : j === i ? '◌' : '○'} ${x}</span>`).join('')}</div>
    ${detail ? `<div class="muted" style="font-size:12px;margin-top:6px">${detail}</div>` : ''}`);
}

async function analyzeNow(t, desk){
  // one ticker, or a comma-separated list from the portfolio (max 15, one run)
  const list = [...new Set(String(t || '').toUpperCase().split(/[,\s]+/).filter(x => /^[A-Z0-9][A-Z0-9.\-^]{0,14}$/.test(x)))].slice(0, 15);
  if (!list.length) return;
  t = list.join(',');
  if (!ghToken()){ ghSetup(() => analyzeNow(t, desk)); return; }
  if (JOB && !JOB.done){ jobShow(`Already analyzing <b class="mono">${esc(JOB.list.join(', '))}</b>. One at a time; this one will be ready shortly.`, 'warn'); return; }
  JOB = {t, list, desk, from: view, start: Date.now(), done: false, stage: 'Starting', run: null};
  jobLine('Starting');
  JOB.tick = setInterval(() => JOB && !JOB.done && jobLine(JOB.stage, JOB.detail), 1000);
  try {
    const r = await gh(`/actions/workflows/${WF}/dispatches`, {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ref: 'main', inputs: {ticker: t, desk}})});
    if (r.status !== 204) return jobFail(ghError(r.status), r.status === 401 || r.status === 403 || r.status === 404);
    JOB.stage = 'Waiting for a server'; poll();
  } catch (e){ jobFail('Couldn’t reach GitHub. Check your connection and try again.'); }
}

async function poll(){
  if (!JOB || JOB.done) return;
  if (Date.now() - JOB.start > 6 * 60e3) return jobFail(`This is taking longer than usual. ${JOB.run ? `<a href="${JOB.run.html_url}" target="_blank" rel="noopener">See the run on GitHub ↗</a>` : ''}`);
  try {
    if (!JOB.run){
      const r = await gh(`/actions/workflows/${WF}/runs?event=workflow_dispatch&per_page=10`);
      if (r.ok){
        const title = `Analyze ${JOB.t} (${JOB.desk})`;
        JOB.run = ((await r.json()).workflow_runs || []).find(x => x.display_title === title && Date.parse(x.created_at) > JOB.start - 120e3) || null;
      }
    } else {
      const r = await gh(`/actions/runs/${JOB.run.id}`); if (r.ok) JOB.run = await r.json();
    }
    const run = JOB.run;
    if (run){
      if (run.status === 'completed'){
        if (run.conclusion === 'success') return finish();
        return jobFail(await failReason(run));
      }
      JOB.stage = run.status === 'in_progress' ? 'Fetching data & scoring' : 'Waiting for a server';
      JOB.detail = run.status === 'in_progress' ? 'Pulling prices, financials and filings, then running every investor’s rules and writing the memo.' : '';
    }
  } catch (e){ /* network blip: keep polling */ }
  setTimeout(poll, 4000);
}

async function failReason(run){
  try {
    const r = await gh(`/actions/runs/${run.id}/jobs`);
    const steps = ((await r.json()).jobs || [])[0]?.steps || [];
    const bad = steps.find(s => s.conclusion === 'failure');
    if (bad && bad.name === 'Score it') return `No market data for <b class="mono">${esc(JOB.list.join(', '))}</b>. It may not be listed yet, be a typo, or need an exchange suffix (India: <span class="mono">.NS</span>, Canada: <span class="mono">.TO</span>). If it's an IPO that hasn't listed, use <b>Upcoming IPOs → ⤓ Extract</b>.`;
  } catch (e){}
  return `The analysis didn't finish. <a href="${run.html_url}" target="_blank" rel="noopener">See what happened on GitHub ↗</a>`;
}

async function finish(){
  JOB.stage = 'Loading the result'; jobLine(JOB.stage);
  try {
    // Read the fresh data straight from the repo: the public site takes another minute to redeploy.
    const raw = {Accept: 'application/vnd.github.raw+json'};
    const [s, h] = await Promise.all([gh('/contents/docs/data/scores.json?ref=main', {headers: raw}).then(r => r.json()),
                                      gh('/contents/docs/data/history.json?ref=main', {headers: raw}).then(r => r.ok ? r.json() : HIST)]);
    if (!s || !Array.isArray(s.stocks)) throw new Error('bad data');
    DATA = s; HIST = h || HIST;
    $('#cIpo').textContent = DATA.stocks.filter(x => x.desk === 'ipo').length;
    $('#cCo').textContent = DATA.stocks.filter(x => x.desk === 'company').length;
    const {list, desk, from} = JOB, secs = Math.round((Date.now() - JOB.start) / 1000);
    stopJob();
    const norm = x => /\.(NS|BO|L|TO|V|HK|T|AX|DE|PA|AS|SW|MI|MC|SI|KS|SS|SZ|SA|MX)$/.test(x) ? x : x.replace(/\./g, '-');
    const got = list.map(x => DATA.stocks.find(s => s.ticker === norm(x) && s.desk === desk)), miss = list.filter((x, i) => !got[i]);
    const close = '<button class="btn" onclick="this.parentNode.classList.remove(\'on\')">OK</button>';
    const tail = miss.length ? ` No market data for <b class="mono">${esc(miss.join(', '))}</b> (not listed, a typo, or needs a suffix like .NS).` : '';
    if (from === 'port'){                   // stay on the portfolio and refresh it with the new scores
      renderPort();
      jobShow(`✓ Analyzed in ${secs}s: ${got.filter(Boolean).map(e => `<b class="mono">${esc(e.ticker)}</b> ${esc(e.overall.label)} (${Math.round(e.overall.score)})`).join(' · ') || 'nothing'}.${tail} They're on the Company Desk now. ${close}`, miss.length ? 'warn' : 'ok');
      return;
    }
    if (view !== desk) setView(desk); else { $('#q').value = ''; renderDesk(); }
    const e = got[0];
    jobShow(`✓ ${list.length > 1 ? `${got.filter(Boolean).length} stocks` : `<b class="mono">${esc(list[0])}</b>`} analyzed in ${secs}s and added to the ${DESKS[desk].title}${e && list.length === 1 ? `: <b>${esc(e.overall.label)}</b> (${Math.round(e.overall.score)}/100)` : ''}.${tail} Your friend sees it too once the site refreshes (about a minute). ${close}`, miss.length ? 'warn' : 'ok');
    if (e && list.length === 1) openD(desk, e.ticker);
  } catch (e){ jobFail('The analysis finished, but loading it failed. Refresh the page in a minute.'); }
}
function stopJob(){ if (JOB){ clearInterval(JOB.tick); JOB.done = true; } }
function jobFail(msg, reconnect){
  const t = JOB && JOB.list.join(', '); stopJob();
  jobShow(`<b>Couldn't analyze ${t ? `<span class="mono">${esc(t)}</span>` : 'that'}.</b> ${msg} ${reconnect ? '<button class="btn" onclick="ghSetup()">Fix the key</button>' : ''} <button class="btn" onclick="this.parentNode.classList.remove('on')">Close</button>`, 'bad');
}

// ── One-time setup: the GitHub key ──
function ghSetup(then){
  let m = $('#ghSetup');
  if (!m){
    m = document.createElement('div'); m.className = 'modal'; m.id = 'ghSetup'; m.setAttribute('role', 'dialog');
    m.innerHTML = `<div class="dh"><div><div class="t" style="font-size:18px">⚡ One-time setup</div><div class="muted" style="font-size:12.5px;margin-top:2px">Lets this site start an analysis for any ticker. Once per device; your friend can use the same key.</div></div><button class="btn" onclick="closeGh()">✕</button></div>
      <div style="padding:14px 20px;overflow:auto;max-height:64vh;font-size:13px;color:var(--soft);line-height:1.6">
        <p style="margin-bottom:10px">The analysis runs on GitHub's free servers (browsers can't pull market data themselves). To start it from here, the site needs a GitHub key that can only run this site's analyzer.</p>
        <ol style="padding-left:18px;display:grid;gap:4px">
          <li>Open <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener" style="color:var(--research)">GitHub → new fine-grained token ↗</a></li>
          <li><b>Token name:</b> Long-Term Lab · <b>Expiration:</b> 1 year</li>
          <li><b>Repository access:</b> Only select repositories → <span class="mono">buffett-agent</span></li>
          <li><b>Permissions → Repositories → Actions:</b> Read and write. Nothing else.</li>
          <li>Click <b>Generate token</b>, copy it, paste it here:</li></ol>
        <div style="display:flex;gap:8px;margin:12px 0 6px"><input id="ghTok" type="password" autocomplete="off" placeholder="github_pat_…" style="flex:1;background:#10141a;border:1px solid var(--line);color:var(--text);border-radius:8px;padding:9px 10px;font:inherit;font-size:13px">
          <button class="btn primary" onclick="ghTest()">Save &amp; test</button></div>
        <div id="ghMsg" style="font-size:12.5px;min-height:18px"></div>
        <p class="muted" style="font-size:12px;margin-top:8px">Saved only in this browser. This key can start and view this repo's runs, nothing else. Don't reuse your trading-bot key: that one can start your bots.</p>
        <p style="margin-top:8px"><button class="btn" onclick="ghSave('');$('#ghTok').value='';$('#ghMsg').textContent='Key removed from this browser.'">Remove saved key</button></p>
      </div>`;
    document.body.appendChild(m);
  }
  m._then = then || null;
  $('#ghTok').value = ''; $('#ghMsg').textContent = ghToken() ? 'A key is saved on this device. Paste a new one to replace it.' : '';
  m.classList.add('on'); $('#shade').classList.add('on');
}
function closeGh(){ $('#ghSetup').classList.remove('on'); if (!$('#drawer').classList.contains('on')) $('#shade').classList.remove('on'); }
async function ghTest(){
  const v = $('#ghTok').value.trim(), msg = t => $('#ghMsg').innerHTML = t;
  if (!/^(github_pat_|ghp_)[A-Za-z0-9_]{20,}$/.test(v)) return msg('<span style="color:var(--pass)">That doesn’t look like a GitHub token (it starts with github_pat_).</span>');
  const old = ghToken(); ghSave(v); msg('Testing…');
  try {
    const r = await gh(`/actions/workflows/${WF}`);
    if (r.ok){ msg('<span style="color:var(--buy)">✓ Connected. You can analyze any ticker now.</span>'); const m = $('#ghSetup'); setTimeout(() => { closeGh(); m._then && m._then(); }, 700); return; }
    if (r.status === 404){ const any = await gh('/actions/workflows'); if (any.ok){ msg('<span style="color:var(--hold)">Key works, but the analyzer isn’t on the site yet. Merge the latest pull request, then try again.</span>'); return; } }
    ghSave(old); msg(`<span style="color:var(--pass)">${ghError(r.status)}</span>`);
  } catch (e){ ghSave(old); msg('<span style="color:var(--pass)">Couldn’t reach GitHub. Check your connection.</span>'); }
}

// Enter in a desk's search box analyzes a ticker that isn't on the desk yet
document.addEventListener('keydown', e => {
  if (e.key !== 'Enter' || e.target.id !== 'q') return;
  const b = $('#req.on button.btn:not([onclick^="setView"])'); if (b) b.click();
});
