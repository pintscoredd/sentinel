"""Interactive weekly earnings board (self-contained HTML rendered in an iframe)."""
from __future__ import annotations

import json
from datetime import date, timedelta

_HTML = r"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
:root{--bg:#000;--panel:#0a0a0a;--panel2:#121212;--border:#1f1f1f;--border2:#333;--text:#ededed;--muted:#a3a3a3;--dim:#8a8a8a;--up:#3fcf8e;--down:#f2555a}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:var(--bg);color:var(--text);overflow-x:hidden;font:14px Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;margin-bottom:14px}
.bar h2{font-size:22px;font-weight:700;letter-spacing:-.01em}
.bar .sub{color:var(--dim);font-size:12px;margin-top:2px}
.ctl{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
input[type=search]{background:var(--panel);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:8px 10px;font:inherit;font-size:13px;width:180px}
.chip{background:var(--panel);border:1px solid var(--border2);color:var(--muted);border-radius:999px;padding:6px 12px;font-size:12px;cursor:pointer;min-height:32px}
.chip.on{background:#fff;color:#000;border-color:#fff}
.legend{display:flex;gap:14px;white-space:nowrap;padding-right:12px;color:var(--dim);font-size:12px;align-items:center}
.legend span{display:inline-flex;gap:5px;align-items:center}
.grid{display:grid;grid-template-columns:repeat(5,minmax(150px,1fr));gap:10px;overflow-x:auto}
.day{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:10px 8px 12px;min-width:150px}
.day.today{border-color:#555}
.dh{display:flex;justify-content:space-between;align-items:baseline;padding:0 4px 8px;border-bottom:1px solid var(--border);margin-bottom:8px}
.dh b{font-size:15px}.dh span{color:var(--dim);font-size:12px}
.slots{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.slot h4{display:flex;justify-content:center;align-items:center;gap:5px;color:var(--dim);font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px}
.tile{display:flex;flex-direction:column;align-items:center;gap:5px;padding:6px 2px;border-radius:10px;cursor:pointer;border:1px solid transparent;background:none;color:inherit;font:inherit;width:100%}
.tile:hover,.tile:focus-visible{background:var(--panel2);border-color:var(--border2);outline:none}
.tile.sel{border-color:#fff}
.logo{width:52px;height:52px;border-radius:10px;background:#fff;display:flex;align-items:center;justify-content:center;overflow:hidden;position:relative}
.logo img{width:80%;height:80%;object-fit:contain}
.logo.inv{background:#1c1c1c;box-shadow:inset 0 0 0 1px #333}
.logo .ph{font-weight:700;color:#111;font-size:15px}
.tk{font-size:13px;font-weight:600;letter-spacing:.02em}
.wl .logo{box-shadow:0 0 0 2px var(--up)}
.more{width:100%;margin-top:4px;background:none;border:1px dashed var(--border2);color:var(--muted);border-radius:8px;padding:6px;font:inherit;font-size:12px;cursor:pointer;min-height:32px}
.more:hover{color:var(--text);border-color:#666}
.tbd{margin-top:8px;border-top:1px solid var(--border);padding-top:8px}
.tbd h4{justify-content:flex-start;padding-left:4px}
.tbdl{display:flex;flex-wrap:wrap;gap:4px;padding:0 4px}
.tbdl button{background:var(--panel2);border:1px solid var(--border);color:var(--muted);border-radius:6px;padding:3px 7px;font:inherit;font-size:11px;cursor:pointer}
.tbdl button:hover{color:var(--text)}
.sp{font-size:11px;font-weight:700;line-height:1}.sp.up{color:var(--up)}.sp.dn{color:var(--down)}.sp.fl{color:var(--dim)}
.rep h4{display:flex;align-items:center;gap:5px;color:var(--dim);font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;margin:2px 4px 6px}
.repg{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.empty{color:var(--dim);font-size:12px;text-align:center;padding:10px 0}
#det{position:fixed;inset:0;background:rgba(0,0,0,.6);display:none;align-items:center;justify-content:center;padding:16px;z-index:9}
#det.show{display:flex}
.card{background:var(--panel);border:1px solid var(--border2);border-radius:14px;padding:18px;width:min(420px,100%);position:relative}
.card .x{position:absolute;top:10px;right:12px;background:none;border:0;color:var(--dim);font-size:18px;cursor:pointer;width:32px;height:32px}
.card .x:hover{color:var(--text)}
.ch{display:flex;gap:12px;align-items:center;margin-bottom:12px;padding-right:28px}
.ch .logo{width:56px;height:56px}
.ch h3{font-size:18px}.ch p{color:var(--dim);font-size:12px;margin-top:2px}
.row{display:flex;justify-content:space-between;gap:10px;padding:8px 0;border-bottom:1px solid #161616;font-size:13px}
.row span:first-child{color:var(--dim)}
.row span:last-child{font-variant-numeric:tabular-nums;text-align:right}
.links{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}
.links a{color:var(--text);text-decoration:none;border:1px solid var(--border2);border-radius:8px;padding:7px 10px;font-size:12px}
.links a:hover{background:#fff;color:#000}
.hint{color:var(--dim);font-size:12px;margin-top:10px}
@media(max-width:760px){.grid{grid-template-columns:repeat(5,minmax(140px,1fr))}}
</style></head><body>
<div class="bar">
  <div><h2>__TITLE__</h2><div class="sub">Ranked by market cap · click a company for details · watchlist names are ringed</div></div>
  <div class="ctl">
    <input id="q" type="search" placeholder="Find ticker or company" aria-label="Find ticker or company">
    <button class="chip" id="wlOnly" aria-pressed="false">Watchlist only</button>
    <div class="legend"><span>__SUN__ Before open</span><span>__MOON__ After close</span></div>
  </div>
</div>
<div class="grid" id="grid"></div>
<div id="det" role="dialog" aria-modal="true"><div class="card" id="card"></div></div>
<script>
const DATA = __DATA__, DAYS = __DAYS__, WL = new Set(__WL__), TODAY = "__TODAY__", PER = __PER__;
const SUN = `__SUN__`, MOON = `__MOON__`;
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const usd = v => v == null ? '—' : (v < 0 ? '-' : '') + '$' + (Math.abs(v) >= 1e12 ? (Math.abs(v)/1e12).toFixed(2)+'T' : Math.abs(v) >= 1e9 ? (Math.abs(v)/1e9).toFixed(1)+'B' : Math.abs(v) >= 1e6 ? (Math.abs(v)/1e6).toFixed(0)+'M' : Math.abs(v).toFixed(2));
const eps = v => v == null ? '—' : (v < 0 ? '-$' : '$') + Math.abs(v).toFixed(2);
const open = {}; let sel = null;
// Some logos are white-on-transparent and vanish on a white tile: sample the opaque pixels and
// switch that tile to a dark background when they are almost all light.
function checkLogo(img) {
  try {
    const c = document.createElement('canvas'); c.width = c.height = 24;
    const g = c.getContext('2d'); g.drawImage(img, 0, 0, 24, 24);
    const d = g.getImageData(0, 0, 24, 24).data;
    if (d[3] > 200 || d[d.length - 1] > 200) return;  // logo brings its own background
    let n = 0, light = 0;
    for (let i = 0; i < d.length; i += 4) {
      if (d[i + 3] < 40) continue;
      n++; if (d[i] + d[i + 1] + d[i + 2] > 690) light++;
    }
    if (n && light / n > 0.85) img.parentElement.classList.add('inv');
  } catch (e) { /* tainted canvas: keep the white tile */ }
}
function logo(s) {
  return `<div class="logo"><img src="https://financialmodelingprep.com/image-stock/${encodeURIComponent(s)}.png" alt="" loading="lazy" crossorigin="anonymous"
    onload="checkLogo(this)" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'ph',textContent:'${esc(s).slice(0,4)}'}))"></div>`;
}
function badge(r) {
  if (r.eps_actual == null) return '';
  if (r.surprise == null) return '<span class="sp fl">reported</span>';
  const c = r.surprise > 0.5 ? 'up' : r.surprise < -0.5 ? 'dn' : 'fl';
  return `<span class="sp ${c}" title="EPS surprise vs consensus">${r.surprise > 0 ? '+' : ''}${r.surprise.toFixed(1)}%</span>`;
}
function tile(r) {
  return `<button class="tile${WL.has(r.symbol) ? ' wl' : ''}${sel === r.symbol ? ' sel' : ''}" data-s="${esc(r.symbol)}" title="${esc(r.name)}">${logo(r.symbol)}<span class="tk">${esc(r.symbol)}</span>${badge(r)}</button>`;
}
function filtered() {
  const q = document.getElementById('q').value.trim().toLowerCase(), wl = document.getElementById('wlOnly').classList.contains('on');
  return DATA.filter(r => (!q || r.symbol.toLowerCase().includes(q) || r.name.toLowerCase().includes(q)) && (!wl || WL.has(r.symbol)));
}
function render() {
  const rows = filtered();
  document.getElementById('grid').innerHTML = DAYS.map(d => {
    const day = rows.filter(r => r.date === d.iso);
    const col = slot => {
      const list = day.filter(r => r.slot === slot), key = d.iso + slot, n = open[key] ? list.length : PER;
      return `<div class="slot"><h4>${slot === 'bmo' ? SUN : MOON}${slot === 'bmo' ? 'Pre' : 'Post'}</h4>${list.length ? list.slice(0, n).map(tile).join('') : '<div class="empty">—</div>'}
        ${list.length > PER ? `<button class="more" data-k="${key}">${open[key] ? 'Show less' : '+' + (list.length - PER) + ' more'}</button>` : ''}</div>`;
    };
    // After a company reports, Nasdaq drops its time-of-day but adds actual EPS and the surprise.
    const rep = day.filter(r => r.slot === 'tbd' && r.eps_actual != null);
    const tbd = day.filter(r => r.slot === 'tbd' && r.eps_actual == null);
    const timed = day.some(r => r.slot !== 'tbd');
    const rk = d.iso + 'rep', rn = open[rk] ? rep.length : PER * 2;
    const repHtml = rep.length ? `<div class="rep"><h4 title="Badge = EPS surprise vs consensus">Reported · ${rep.length}</h4><div class="repg">${rep.slice(0, rn).map(tile).join('')}</div>
        ${rep.length > PER * 2 ? `<button class="more" data-k="${rk}">${open[rk] ? 'Show less' : '+' + (rep.length - PER * 2) + ' more'}</button>` : ''}</div>` : '';
    return `<section class="day${d.iso === TODAY ? ' today' : ''}"><div class="dh"><b>${d.dow}</b><span>${d.label}${d.iso === TODAY ? ' · today' : ''}</span></div>
      ${timed || !rep.length ? `<div class="slots">${col('bmo')}${col('amc')}</div>` : ''}${repHtml}
      ${tbd.length ? `<div class="tbd"><h4 class="lbl" style="color:var(--dim);font-size:11px;letter-spacing:.08em;margin-bottom:6px">TIME NOT CONFIRMED · ${tbd.length}</h4><div class="tbdl">${tbd.slice(0, 18).map(r => `<button data-s="${esc(r.symbol)}">${esc(r.symbol)}</button>`).join('')}${tbd.length > 18 ? `<span class="hint">+${tbd.length - 18}</span>` : ''}</div></div>` : ''}
    </section>`;
  }).join('');
}
function detail(sym) {
  const r = DATA.find(x => x.symbol === sym); if (!r) return;
  sel = sym; render();
  const growth = r.eps_est != null && r.last_eps ? (r.eps_est / Math.abs(r.last_eps) - 1) * 100 * Math.sign(r.last_eps) : null;
  const when = r.slot === 'bmo' ? 'Before market open' : r.slot === 'amc' ? 'After market close' : r.eps_actual != null ? 'Reported' : 'Time not confirmed';
  const d = DAYS.find(x => x.iso === r.date);
  document.getElementById('card').innerHTML = `<button class="x" aria-label="Close" onclick="closeDet()">✕</button>
    <div class="ch">${logo(r.symbol)}<div><h3>${esc(r.symbol)}</h3><p>${esc(r.name)}</p></div></div>
    <div class="row"><span>Reports</span><span>${d ? d.dow + ' ' + d.label : r.date} · ${when}</span></div>
    <div class="row"><span>Fiscal quarter</span><span>${esc(r.fiscal_q || '—')}</span></div>
    <div class="row"><span>Consensus EPS</span><span>${eps(r.eps_est)}${r.n_est ? ' · ' + r.n_est + ' analysts' : ''}</span></div>
    ${r.eps_actual != null ? `<div class="row"><span>Reported EPS</span><span>${eps(r.eps_actual)}${r.surprise != null ? ` · <b style="color:${r.surprise >= 0 ? 'var(--up)' : 'var(--down)'}">${r.surprise >= 0 ? 'beat' : 'miss'} ${Math.abs(r.surprise).toFixed(1)}%</b>` : ''}</span></div>` : ''}
    <div class="row"><span>Year-ago EPS</span><span>${eps(r.last_eps)}${r.last_date ? ' · ' + esc(r.last_date) : ''}</span></div>
    <div class="row"><span>Implied EPS growth</span><span style="color:${growth == null ? 'inherit' : growth >= 0 ? 'var(--up)' : 'var(--down)'}">${growth == null ? '—' : (growth >= 0 ? '+' : '') + growth.toFixed(1) + '%'}</span></div>
    <div class="row"><span>Market cap</span><span>${usd(r.market_cap)}</span></div>
    <div class="links"><a href="https://finance.yahoo.com/quote/${encodeURIComponent(r.symbol)}" target="_blank" rel="noopener">Yahoo Finance ↗</a>
      <a href="https://www.nasdaq.com/market-activity/stocks/${encodeURIComponent(r.symbol.toLowerCase())}/earnings" target="_blank" rel="noopener">Nasdaq earnings ↗</a></div>
    <div class="hint">For expected move and beat history, pick ${esc(r.symbol)} in “Deep dive” below the board.</div>`;
  document.getElementById('det').classList.add('show');
}
function closeDet() { document.getElementById('det').classList.remove('show'); }
document.addEventListener('click', e => {
  const t = e.target.closest('[data-s]'); if (t) return detail(t.dataset.s);
  const m = e.target.closest('[data-k]'); if (m) { open[m.dataset.k] = !open[m.dataset.k]; render(); }
  if (e.target.id === 'det') closeDet();
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDet(); });
document.getElementById('q').addEventListener('input', render);
document.getElementById('wlOnly').addEventListener('click', e => { e.target.classList.toggle('on'); e.target.setAttribute('aria-pressed', e.target.classList.contains('on')); render(); });
window.closeDet = closeDet;
render();
</script></body></html>"""

_SUN = ('<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
        '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>')
_MOON = ('<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
         '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>')


def earnings_board_html(rows: list[dict], monday: date, watchlist: list[str], per_slot: int = 6) -> tuple[str, int]:
    """(html, suggested iframe height) for the week starting *monday*."""
    rows = sorted(rows, key=lambda r: -(r.get("market_cap") or 0))
    days = [{"iso": (monday + timedelta(days=i)).isoformat(),
             "dow": (monday + timedelta(days=i)).strftime("%a"),
             "label": (monday + timedelta(days=i)).strftime("%b %d")} for i in range(5)]
    title = f"Earnings · week of {monday:%b %d, %Y}"

    def js(o):
        return json.dumps(o, default=str).replace("</", "<\\/")

    html = (_HTML.replace("__DATA__", js(rows)).replace("__DAYS__", js(days)).replace("__WL__", js(sorted(watchlist)))
            .replace("__TODAY__", date.today().isoformat()).replace("__PER__", str(int(per_slot)))
            .replace("__TITLE__", title).replace("__SUN__", _SUN).replace("__MOON__", _MOON))
    height = 150 + per_slot * 88 + 150
    return html, height
