'use strict';
/* The page: screens, pop-up menus and wiring to the Python backend (pywebview, or the dev HTTP bridge in a browser).
   The markup and styles are the approved design (design/mockup.html); the data here is real. */
const APP_NAME = 'Media MultiTool Desktop';
document.querySelectorAll('.appname').forEach(e => e.textContent = APP_NAME);
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const ic = (n, c = '') => `<svg class="i ${c}"><use href="#${n}"/></svg>`;
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const { humanSize, clock, parseClock } = Model;

/* ---------- backend ---------- */
const viaHttp = !!window.DEV_BRIDGE;                     // dev bridge (app.py --dev) sets this flag: the same API over fetch
const api = new Proxy({}, { get: (_t, name) => (...args) => viaHttp
  ? fetch('/api/' + name, { method: 'POST', body: JSON.stringify(args) }).then(r => r.json()).then(j => { if (j.error) throw new Error(j.error); return j.ok; })
  : window.pywebview.api[name](...args) });
const ready = () => viaHttp || (window.pywebview && window.pywebview.api && typeof window.pywebview.api.boot === 'function') ? Promise.resolve() : new Promise(r => addEventListener('pywebviewready', r, { once: true }));

/* ---------- data ---------- */
const LANGS = [['en', 'English'], ['sk', 'Slovak'], ['cs', 'Czech'], ['de', 'German'], ['es', 'Spanish'], ['fr', 'French'], ['it', 'Italian'], ['pl', 'Polish'],
  ['hu', 'Hungarian'], ['pt', 'Portuguese'], ['ru', 'Russian'], ['uk', 'Ukrainian'], ['ja', 'Japanese'], ['ko', 'Korean']];
const RATES = [['', 'None'], ['500K', '500K/s'], ['1M', '1M/s'], ['2M', '2M/s'], ['5M', '5M/s'], ['10M', '10M/s']];
const MODES = [['video', 'Video', 'film'], ['audio', 'Audio', 'music'], ['gif', 'GIF', 'gif']];
const CONTS = [['mp4', 'MP4'], ['mkv', 'MKV'], ['webm', 'WebM']];
const AFMTS = Object.entries(Model.AUDIO_LABEL);
const langName = c => (LANGS.find(l => l[0] === c) || [c, c])[1];
const modeName = m => (MODES.find(x => x[0] === m) || [m, m])[1];

/* the (i) explanations: plain words for the options that need them */
const TIPS = {
  codec: 'How the video is compressed. H.264 plays on almost everything. VP9 and AV1 make smaller files at the same quality, but some older devices and players can’t play them.',
  container: 'The file type. MP4 plays almost everywhere. MKV can hold anything. WebM only works with VP9 or AV1, so it is unavailable with H.264.',
  runas: 'Batch downloads the whole playlist as one entry in the queue, one video after another. Separate makes every video its own download, so several can run at the same time.',
  fragments: 'Many sites serve a video as lots of small pieces. This downloads several pieces at once to speed up a single download. 4 is a good value; very high numbers can get you blocked.',
  proxy: 'Sends downloads through a proxy server, for example socks5://127.0.0.1:1080 or http://host:8080. Leave it empty unless you know you need one.',
  ipv4: 'Uses only the older IPv4 type of internet address. Turn it on if downloads fail or hang on a network where IPv6 is broken.',
  channel: 'Stable is the tested yt-dlp release. Nightly is built every day and often fixes a site that broke days before Stable does, but it can have new bugs.',
};
const tip = k => `<span class="tip" tabindex="0" role="img" aria-label="${esc(TIPS[k])}" data-tip="${esc(TIPS[k])}">${ic('info')}</span>`;

let P = {};                                           // saved settings and last-used choices (mirrors the backend)
let STATE = { jobs: [], history: [], simul: 3 };      // the backend's queue
const S = {
  screen: 'download', phase: 'empty', url: '', media: null, preview: null, error: null, loadId: 0, tools: { ready: true },
  setup: { running: false, text: '', fraction: 0, error: null },
  trim: false, from: '0:00', to: '0:05', nameOn: false, name: '', plRange: false, rFrom: '1', rTo: '', batch: [],
  started: {}, versions: null, sites: null, siteQ: '', upd: 'Check', lastClip: null,
};
const setP = (k, v) => { P[k] = v; api.set_pref(k, v); };
function applyTheme(animate) {
  if (animate) { document.body.classList.add('theming'); setTimeout(() => document.body.classList.remove('theming'), 450); }
  document.documentElement.dataset.theme = P.dark === false ? 'light' : 'dark';
}

/* ---------- what the screen is showing ---------- */
const cur = () => S.media || S.preview;                    // the preview stands in until yt-dlp has the formats
const isPL = () => !!S.media && S.media.kind === 'playlist';
const hasFormats = () => !!S.media && !isPL();
const from_ = () => parseClock(S.from), to_ = () => parseClock(S.to);
function effMode() { return S.media && !isPL() && !Model.mediaHasVideo(S.media) ? 'audio' : P.mode; }   // audio-only link: no video/GIF
function plRange() { return S.plRange ? { range_from: parseInt(S.rFrom) || 1, range_to: parseInt(S.rTo) || null } : {}; }
function opts() {
  const name = isPL() ? (P.own_folder && S.name.trim() ? S.name.trim() : null) : (S.nameOn && S.name.trim() ? S.name.trim() : null);
  return Model.resolveOptions({ ...P, mode: effMode() }, S.media, { trim: S.trim, start: from_() ?? 0, end: to_() ?? 5, custom_name: name, ...plRange() });
}
const needsSection = () => effMode() === 'gif' || S.trim;
function sectionOk() {
  if (!needsSection()) return true;
  const f = from_(), t = to_(), d = S.media ? S.media.seconds : 0;
  return f != null && t != null && t > f && !(d > 0 && t > d + 0.5);
}
const dirFor = mode => P[{ video: 'dir_video', audio: 'dir_audio', gif: 'dir_gif' }[mode]];
function selectionCount(m) { const n = m.playlist_count; return S.plRange ? Math.max(0, Math.min(parseInt(S.rTo) || n, n) - (parseInt(S.rFrom) || 1) + 1) : n; }

function summaryRows() {
  const o = opts(), m = S.media, est = m && !isPL() ? Model.estimate(m, o) : null, rows = [];
  if (isPL()) rows.push(['Items', S.plRange ? `${S.rFrom || 1}–${S.rTo || m.playlist_count}` : `all ${m.playlist_count}`],
    ['Run as', P.pl_run === 'batch' ? 'batch, in order' : `separate, ${P.simul} at a time`]);
  if (needsSection()) rows.push(['Section', `${S.from} – ${S.to}`]);
  if (o.mode === 'video') rows.push([hasFormats() && Model.heights(m).length ? 'Resolution' : 'Quality', hasFormats() && Model.heights(m).length ? Model.label(m, o.height) : 'Best available'],
    ['Format', (hasFormats() && Model.heights(m).length ? Model.CODEC_LABEL[o.codec] + ' · ' : '') + Model.CONTAINER_LABEL[o.container] + (o.subtitles ? ' · subs' : '')]);
  else if (o.mode === 'audio') rows.push(['Audio', o.audio_format === 'original' ? 'Original' : `${Model.AUDIO_LABEL[o.audio_format]} · ${o.bitrate} kbps`]);
  else rows.push(['GIF', `${o.gif_width} px · ${o.gif_fps} fps · ${o.gif_loop ? 'loops' : 'plays once'}`]);
  rows.push(['Size', est == null ? 'unknown' : (o.mode === 'gif' ? '≈ ' : '') + humanSize(est)], ['Saves to', dirFor(o.mode) + (isPL() && o.own_folder ? '\\…' : '')]);
  return rows;
}

/* ---------- pop-up menus ---------- */
let openMenu = null;
function closeMenu(instant) {
  if (!openMenu) return; const { el, btn } = openMenu; openMenu = null; btn && btn.setAttribute('aria-expanded', 'false');
  if (instant) el.remove(); else { el.classList.add('out'); setTimeout(() => el.remove(), 100); }
}
function showMenu(anchor, items, { header, align = 'right', onPick, at } = {}) {
  closeMenu(true);
  const el = document.createElement('div'); el.className = 'menu'; el.setAttribute('role', 'menu');
  el.innerHTML = (header ? `<div class="mh">${esc(header)}</div>` : '') + items.map((it, i) => it.sep ? '<hr>' :
    `<div class="mi ${it.sel ? 'sel' : ''} ${it.dis ? 'dis' : ''} ${it.danger ? 'danger' : ''}" role="menuitem" data-i="${i}" ${it.note ? `title="${esc(it.note)}"` : ''}>
       <span class="ck">${ic('check')}</span>${it.icon ? ic(it.icon, 'ic') : ''}<span class="l">${esc(it.label)}</span><span class="r">${esc(it.dis && it.note ? it.note : (it.right || ''))}</span></div>`).join('');
  document.body.appendChild(el);
  const w = el.offsetWidth, h = el.offsetHeight, vw = innerWidth, vh = innerHeight;
  let x, y, ox, oy;
  if (at) { x = Math.min(at.x, vw - w - 8); y = Math.min(at.y, vh - h - 8); ox = '0'; oy = '0'; }
  else { const r = anchor.getBoundingClientRect(); x = align === 'right' ? r.right - w : r.left; x = Math.max(8, Math.min(x, vw - w - 8));
    y = r.bottom + 6; oy = '0'; if (y + h > vh - 8) { y = Math.max(8, r.top - h - 6); oy = '100%'; } ox = (align === 'right' ? w - 20 : 20) + 'px'; }
  el.style.left = x + 'px'; el.style.top = y + 'px'; el.style.setProperty('--ox', ox); el.style.setProperty('--oy', oy);
  anchor && anchor.setAttribute('aria-expanded', 'true');
  openMenu = { el, btn: anchor };
  const live = () => $$('.mi:not(.dis)', el); let hl = -1;
  const setHl = n => { const l = live(); l.forEach(m => m.classList.remove('hl')); if (l.length) { hl = (n + l.length) % l.length; l[hl].classList.add('hl'); l[hl].scrollIntoView({ block: 'nearest' }); } };
  const pick = m => { const it = items[+m.dataset.i]; closeMenu(); if (it && onPick) onPick(it.id, it); };
  el.addEventListener('mouseover', e => { const m = e.target.closest('.mi:not(.dis)'); if (m) { $$('.mi', el).forEach(n => n.classList.remove('hl')); m.classList.add('hl'); hl = live().indexOf(m); } });
  el.addEventListener('click', e => { const m = e.target.closest('.mi:not(.dis)'); if (m) pick(m); });
  el._key = e => { if (e.key === 'ArrowDown') { e.preventDefault(); setHl(hl + 1); } else if (e.key === 'ArrowUp') { e.preventDefault(); setHl(hl < 0 ? -1 : hl - 1); } else if (e.key === 'Enter' && hl >= 0) { e.preventDefault(); pick(live()[hl]); } else if (e.key === 'Escape') { closeMenu(); anchor && anchor.focus(); } };
  const sel = $('.mi.sel', el); if (sel) setHl(live().indexOf(sel));
}
addEventListener('keydown', e => { if (openMenu) openMenu.el._key(e); else if (e.key === 'Escape') closeDialog(); });
addEventListener('mousedown', e => { if (openMenu && !openMenu.el.contains(e.target) && !(openMenu.btn && openMenu.btn.contains(e.target))) closeMenu(); }, true);
let resizeT;   // the blur layers are switched off while the window is being resized, and back on a moment after it stops
addEventListener('resize', () => { closeMenu(true); document.documentElement.classList.add('resizing'); clearTimeout(resizeT); resizeT = setTimeout(() => document.documentElement.classList.remove('resizing'), 160); });
$('#main').addEventListener('scroll', () => closeMenu(true), { passive: true });

/* what each pop-up offers, and what is unavailable and why */
function menuFor(k) {
  const m = S.media, o = opts();
  const list = (arr, cur_, fmt = x => x) => arr.map(x => ({ id: x, label: fmt(x), sel: String(x) === String(cur_) }));
  switch (k) {
    case 'mode': return { items: MODES.map(([id, label, icon]) => {
      const noVideo = m && !isPL() && !Model.mediaHasVideo(m) && id !== 'audio';
      const noGif = id === 'gif' && isPL();
      return { id, label, icon, sel: id === effMode(), dis: noVideo || noGif, note: noVideo ? 'No video in this link' : 'Needs a section per clip' }; }) };
    case 'res': return { header: 'Resolution · from this video', items: Model.heights(m).map(h => {
      const c = Model.pickCodec(m, h, P.codec) ?? o.codec;
      return { id: h, label: Model.label(m, h), sel: h === o.height, right: humanSize(Model.estimate(m, { ...o, height: h, codec: c, fps60: P.fps60 && Model.maxFps(m, h) > 30 })).replace('size unknown', '—') }; }) };
    case 'codec': return { items: Object.keys(Model.CODEC_LABEL).map(c => {
      const here = Model.codecsAt(m, o.height).includes(c), ok = here && Model.containerAllows(o.container, c);
      return { id: c, label: Model.CODEC_LABEL[c], sel: c === o.codec, dis: !ok, note: !here ? `Not offered at ${Model.label(m, o.height)}` : 'No H.264 in WebM' }; }) };
    case 'cont': return { items: CONTS.map(([c, l]) => {
      const bad = (hasFormats() && Model.heights(m).length && !Model.containerAllows(c, o.codec)) || (S.trim && !Model.containerAllowsTrim(c));
      return { id: c, label: l, sel: c === o.container, dis: bad, note: S.trim && !Model.containerAllowsTrim(c) ? "Can't be cut" : 'No H.264 in WebM' }; }) };
    case 'fps': { const f = Math.round(Model.maxFps(m, o.height)); return { items: [
      { id: '60', label: f > 30 ? `${f} fps` : '60 fps', sel: o.fps60, dis: f <= 30, note: `Only 30 fps at ${Model.label(m, o.height)}` }, { id: '30', label: '30 fps', sel: !o.fps60 }] }; }
    case 'afmt': return { items: AFMTS.map(([id, l]) => ({ id, label: l, sel: id === P.audio_format })) };
    case 'br': return { items: list(Model.BITRATES, P.bitrate, b => b + ' kbps') };
    case 'gw': return { items: list(Model.GIF_WIDTHS, P.gif_width, x => x + ' px') };
    case 'gfps': return { items: list(Model.GIF_FPS, P.gif_fps, x => x + ' fps') };
    case 'gloop': return { items: [{ id: 'loop', label: 'Forever', sel: P.gif_loop }, { id: 'once', label: 'Once', sel: !P.gif_loop }] };
    case 'plmode': return { items: [{ id: 'all', label: `All ${m.playlist_count}`, sel: !S.plRange }, { id: 'range', label: 'Range…', sel: S.plRange }] };
    case 'plrun': return { items: [{ id: 'batch', label: 'Batch', right: 'one entry, in order', sel: P.pl_run === 'batch' }, { id: 'separate', label: 'Separate', right: 'one entry per video', sel: P.pl_run === 'separate' }] };
    case 'bmode': return { items: [{ id: 'video', label: 'Video', icon: 'film', sel: P.b_mode === 'video' }, { id: 'audio', label: 'Audio', icon: 'music', sel: P.b_mode === 'audio' }, { id: 'gif', label: 'GIF', icon: 'gif', dis: true, note: 'Needs a section per clip' }] };
    case 'bq': return { header: 'Best each video has, up to', items: [2160, 1440, 1080, 720, 480].map(h => ({ id: h, label: `Up to ${h}p`, sel: h === P.b_height })) };
    case 'bcont': return { items: CONTS.map(([c, l]) => ({ id: c, label: l, sel: c === P.b_container })) };
    case 'bafmt': return { items: AFMTS.map(([id, l]) => ({ id, label: l, sel: id === P.b_audio_format })) };
    case 'bpl': return { items: [{ id: 'batch', label: 'Batch', right: 'one entry, in order', sel: P.b_pl_run === 'batch' }, { id: 'separate', label: 'Separate', right: 'one entry per video', sel: P.b_pl_run === 'separate' }] };
    case 'lang': return { items: LANGS.map(([c, l]) => ({ id: c, label: l, sel: c === P.sub_lang })) };
    case 'rate': return { items: RATES.map(([c, l]) => ({ id: c, label: l, sel: c === P.rate_limit })) };
    case 'chan': return { items: [{ id: 'stable', label: 'Stable', sel: !P.nightly }, { id: 'nightly', label: 'Nightly', sel: !!P.nightly, right: 'fixes sites sooner' }] };
  }
}
function applyPick(k, id) {
  switch (k) {
    case 'mode': setP('mode', id); break; case 'res': setP('height', +id); break; case 'codec': setP('codec', id); break; case 'cont': setP('container', id); break;
    case 'fps': setP('fps60', id === '60'); break; case 'afmt': setP('audio_format', id); break; case 'br': setP('bitrate', +id); break;
    case 'gw': setP('gif_width', +id); break; case 'gfps': setP('gif_fps', +id); break; case 'gloop': setP('gif_loop', id === 'loop'); break;
    case 'plmode': S.plRange = id === 'range'; break; case 'plrun': setP('pl_run', id); break;
    case 'bmode': setP('b_mode', id); break; case 'bq': setP('b_height', +id); break; case 'bcont': setP('b_container', id); break;
    case 'bafmt': setP('b_audio_format', id); break; case 'bpl': setP('b_pl_run', id); break;
    case 'lang': setP('sub_lang', id); break; case 'rate': setP('rate_limit', id); break; case 'chan': setP('nightly', id === 'nightly'); S.upd = 'Check'; break;
  }
}
const pop = (k, text, wide) => `<button class="pop ${wide ? 'wide' : ''}" data-pop="${k}" aria-haspopup="menu" aria-expanded="false"><span>${esc(text)}</span>${ic('updown')}</button>`;
const tog = (k, on) => `<button class="tog" role="switch" aria-checked="${!!on}" data-tog="${k}"></button>`;
const STARS = [[12, 24, 4, 0], [34, 64, 3, 90], [44, 16, 3, 150], [26, 42, 5, 40], [56, 60, 3, 200]]; // x%, y%, px, delay ms
const dayNight = on => `<span><button class="dn" role="switch" aria-checked="${!!on}" aria-label="Dark mode" data-tog="dark"><span class="dn-sky"></span>
  <span class="dn-stars">${STARS.map(([x, y, sz, d]) => `<svg viewBox="0 0 24 24" style="left:${x * 0.62}%;top:${y}%;width:${sz}px;height:${sz}px;--d:${d}ms"><path d="M12 0l2.2 9.8L24 12l-9.8 2.2L12 24l-2.2-9.8L0 12l9.8-2.2z"/></svg>`).join('')}</span>
  <span class="dn-clouds"><i></i><i></i><i></i><i></i></span>
  <span class="dn-orb"><b class="r r3"></b><b class="r r2"></b><b class="r r1"></b><b class="sun"></b><b class="moon"><u></u><u></u><u></u></b></span></button></span>`;
const thumbHtml = (url, cls = 'th') => `<div class="${cls}">${url ? `<img src="${esc(url)}" alt="" loading="lazy" onerror="this.remove()">` : ''}</div>`;
const sec = s => `<div class="sec">${s}</div>`;
const row = (l, ctl, sub) => `<div class="row"><span class="lbl">${l}${sub ? `<small>${sub}</small>` : ''}</span>${ctl}</div>`;

/* ---------- Download screen ---------- */
function viewDownload() {
  const linkbar = `<div class="topbar"><div class="linkbar">${ic('link', 'lead')}
    <input id="url" placeholder="Paste a link…" value="${esc(S.url)}" spellcheck="false" autocomplete="off" aria-label="Link" ${S.tools.ready ? '' : 'disabled'}>
    ${S.url ? `<button class="btn sq" data-act="clear" aria-label="Clear">${ic('close')}</button>` : `<button class="btn" data-act="paste">${ic('paste')}Paste</button>`}</div></div>`;
  let body;
  if (!S.tools.ready) body = setupCard();
  else if (S.phase === 'empty') body = emptyBody();
  else if (S.phase === 'loading') body = `<div class="card"><div class="state-center"><div class="spin"></div><span>${S.preview ? '' : 'Reading link…'}</span></div></div>`;
  else if (S.phase === 'error') body = `<div class="card err-card">${esc(S.error)}<button class="btn" data-act="retry">Try again</button></div>`;
  else if (S.phase === 'batch') body = batchBody();
  else body = loadedBody();
  return `<div class="view" id="v-download">${linkbar}${body}</div>`;
}
function emptyBody() {
  const o = Model.resolveOptions(P, null, {});
  const fmt = P.mode === 'video' ? `${o.height}p · ${Model.CODEC_LABEL[o.codec]} · ${Model.CONTAINER_LABEL[o.container]}` : P.mode === 'audio' ? (P.audio_format === 'original' ? 'Original' : `${Model.AUDIO_LABEL[P.audio_format]} · ${P.bitrate} kbps`) : `${P.gif_width} px · ${P.gif_fps} fps`;
  return `<div class="card hero"><div class="ic">${ic('download')}</div>Paste a link above, drop one here, or press <kbd>Ctrl</kbd> + <kbd>V</kbd> anywhere.<br>Copied links are filled in automatically.<br><b style="color:var(--text);font-weight:600">Have several?</b> Paste them all at once, one per line, and download them together.
      <div class="chips">${['YouTube', 'Instagram', 'X', 'TikTok', 'Reddit', 'Vimeo', '+ 1,800 more'].map(c => `<span class="chip">${c}</span>`).join('')}</div></div>
    ${sec('Last used')}<div class="card"><div class="row"><span class="lbl">Mode</span><span class="val">${modeName(P.mode)}</span></div><div class="row"><span class="lbl">Format</span><span class="val">${fmt}</span></div></div>`;
}
const TOOL_INFO = { 'yt-dlp': ['yt-dlp', 18], ffmpeg: ['ffmpeg', 140], deno: ['Deno', 40] };   // name, approximate download in MB
function setupCard() {
  const s = S.setup, missing = (S.tools.missing || []).map(k => TOOL_INFO[k]).filter(Boolean);
  const names = missing.map(t => `<b>${t[0]}</b>`), list = names.length > 1 ? names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1] : names.join('');
  const mb = missing.reduce((n, t) => n + t[1], 0);
  return `<div class="card setup"><h2>One-time setup</h2>
    <p>${APP_NAME} needs ${missing.length > 1 ? 'a few free tools' : 'a free tool'} to read and save videos: ${list} (about ${mb} MB). ${missing.length > 1 ? 'They are' : 'It is'} downloaded from the official GitHub releases and kept in this app's own folder, so nothing is installed on your PC. yt-dlp then keeps itself up to date.</p>
    ${s.running ? `<div class="prog"><i style="width:${Math.round(s.fraction * 100)}%"></i></div><div class="note" style="padding:0">${esc(s.text)}</div>`
      : `<button class="btn" data-act="setup">${ic('download')}Download ${missing.length > 1 ? 'the tools' : 'it'}</button>`}
    ${s.error ? `<div class="note" style="color:var(--danger);padding:0">${esc(s.error)}</div>` : ''}</div>`;
}
function tfields() { const bad = !sectionOk(); return `<span>From</span><input class="field c ${bad ? 'err' : ''}" data-in="from" value="${esc(S.from)}" aria-label="From"><span>to</span><input class="field c ${bad ? 'err' : ''}" data-in="to" value="${esc(S.to)}" aria-label="To">`; }
function sectionHint() {
  if (!sectionOk()) return 'Check the times: the end must be after the start and within the video.';
  if (S.media && S.media.seconds <= 0) return "This site doesn't give the clip's length. A section past the end simply stops there.";
  return `${(to_() - from_()).toFixed(1)} s · GIFs need a section, whole videos get huge`;
}
function loadedBody() {
  const m = S.media, reading = !m, o = reading ? null : opts();
  let fmt = '', optsHtml = '';
  if (reading) fmt = `${sec('Reading formats…')}<div class="sk" style="height:168px"></div><div class="sk" style="height:140px;margin-top:12px"></div>`;
  else {
    const hs = hasFormats() ? Model.heights(m) : [];
    let rows = row('Mode', pop('mode', modeName(o.mode)));
    if (o.mode === 'video') {
      if (!hs.length) rows += row('Resolution', `<span class="val">Best available</span>`, `${esc(m.site)} doesn't list resolutions for this ${isPL() ? 'playlist' : 'post'}`) + row('Container' + tip('container'), pop('cont', Model.CONTAINER_LABEL[o.container]));
      else {
        const f = Math.round(Model.maxFps(m, o.height));
        rows += row('Resolution', pop('res', `${Model.label(m, o.height)} · ${humanSize(Model.estimate(m, o)).replace('size unknown', '—')}`, true), 'From this video') +
          row('Codec' + tip('codec'), pop('codec', Model.CODEC_LABEL[o.codec])) + row('Container' + tip('container'), pop('cont', Model.CONTAINER_LABEL[o.container])) +
          row('Frame rate', pop('fps', o.fps60 ? (f > 30 ? `${f} fps` : '60 fps') : '30 fps'));
      }
    } else if (o.mode === 'audio') rows += row('Format', pop('afmt', Model.AUDIO_LABEL[o.audio_format])) +
      row('Bitrate', `<button class="pop" data-pop="br" ${o.audio_format === 'original' ? 'disabled' : ''} aria-haspopup="menu" aria-expanded="false"><span>${o.audio_format === 'original' ? 'Original' : o.bitrate + ' kbps'}</span>${ic('updown')}</button>`);
    else rows += row('Width', pop('gw', o.gif_width + ' px')) + row('Frame rate', pop('gfps', o.gif_fps + ' fps')) + row('Loop', pop('gloop', o.gif_loop ? 'Forever' : 'Once'));
    const secCard = o.mode === 'gif' ? `${sec('Section')}<div class="card"><div class="tfields" style="padding-top:14px">${tfields()}</div><div class="note" style="padding:0 16px 12px">${sectionHint()}</div></div>` : '';
    fmt = sec(o.mode === 'video' ? 'Format' : modeName(o.mode)) + `<div class="card">${rows}</div>` + secCard;   // GIF: the section comes after the GIF settings, before Options
    if (o.mode === 'audio') { const b = Model.bestAudio(m); fmt += `<div class="note">Original = the site's own audio${b ? ` (${esc([b.acodec.split('.')[0], Math.round(b.abr || b.tbr || 0) ? Math.round(b.abr || b.tbr) + ' kbps' : ''].join(' ').trim())} here)` : ''}, no re-encoding. Bitrate applies to M4A, MP3 and Opus.</div>`; }
    if (isPL()) fmt += sec('Playlist') + `<div class="card">${row('Download', pop('plmode', S.plRange ? 'Range…' : `All ${m.playlist_count}`))}
      <div class="xp ${S.plRange ? 'open' : ''}"><div><div class="inner tfields"><span>Items</span><input class="field c ${S.plRange && !/^\d+$/.test(S.rFrom) ? 'err' : ''}" data-in="rFrom" value="${esc(S.rFrom)}" inputmode="numeric" aria-label="First item"><span>to</span><input class="field c" data-in="rTo" value="${esc(S.rTo)}" placeholder="end" inputmode="numeric" aria-label="Last item"></div></div></div>
      ${row('Run as' + tip('runas'), pop('plrun', P.pl_run === 'batch' ? 'Batch' : 'Separate', true), P.pl_run === 'batch' ? 'One queue entry. The videos download in order, one after another.' : `Every video is its own download, up to ${P.simul} at a time`)}
      ${row('Own folder', tog('own_folder', P.own_folder), P.own_folder ? 'Saved in a folder named after the playlist' : 'Files go straight into the save folder')}
      <div class="xp ${P.own_folder ? 'open' : ''}"><div><div class="inner" style="padding:0 16px 14px"><div class="f" style="margin-bottom:0"><label>Folder name</label><input class="field" style="width:100%" data-in="name" value="${esc(S.name || m.title)}" aria-label="Folder name"></div><div class="note" style="padding:6px 0 0">The files inside keep their video titles, numbered 001, 002…</div></div></div></div></div>`;
    let ob = '';
    if (o.mode !== 'gif' && !isPL()) ob += row('Trim', tog('trim', S.trim)) + `<div class="xp ${S.trim ? 'open' : ''}"><div><div class="inner"><div class="tfields">${tfields()}</div><div class="note" style="padding:0 16px 12px">Cut losslessly at the nearest keyframe (up to ~2 s early), so the format stays exactly as chosen.</div></div></div></div>`;
    if (o.mode === 'video') ob += row('Subtitles', tog('subtitles', P.subtitles), `${langName(P.sub_lang)}${P.embed_subs ? ', embedded' : ', separate .srt'} · change in Settings`);
    if (!isPL()) ob += row('Custom name', tog('nameOn', S.nameOn)) + `<div class="xp ${S.nameOn ? 'open' : ''}"><div><div class="inner" style="padding:0 16px 14px"><input class="field" style="width:100%" data-in="name" value="${esc(S.name || m.title)}" aria-label="Custom name"></div></div></div>`;
    optsHtml = ob ? sec('Options') + `<div class="card">${ob}</div>` : '';
  }
  return `<div class="dl-grid" style="margin-top:6px"><div>${fmt}${optsHtml}</div>${inspector(reading)}</div>`;
}
function inspector(reading) {
  const m = cur();
  const meta = [m.uploader, m.date, isPL() ? 'playlist' : ''].filter(Boolean).join(' · ');
  const badge = isPL() ? `${m.playlist_count} videos` : (m.seconds > 0 ? clock(Math.round(m.seconds)) : '');
  const rows = reading ? '' : `<hr><div class="kv">${summaryRows().map(([k, v]) => `<span>${k}</span><i title="${esc(v)}">${esc(v)}</i>`).join('')}</div>${goButton()}${afterLinks()}`;
  return `<aside class="card insp"><div class="ih"><div class="thumb ${isPL() ? 'pl' : ''}">${m.thumbnail ? `<img src="${esc(m.thumbnail)}" alt="" onerror="this.remove()">` : ''}${badge ? `<b>${badge}</b>` : ''}</div>
    <div><div class="title" title="${esc(m.title)}">${esc(m.title)}</div><div class="by">${esc(meta)}</div><span class="site">${esc(m.site)}${isPL() ? ' · playlist' : ''}</span></div></div>${rows}</aside>`;
}

/* The Download button: its state comes from the jobs this exact link + settings started. */
const keyOf = () => S.url + '\n' + JSON.stringify(opts()) + (isPL() ? P.pl_run : '');
function buttonInfo() {
  const ids = S.started[keyOf()] || [];
  if (!ids.length) return { state: 'idle' };
  const jobs = STATE.jobs.filter(j => ids.includes(j.id)), hist = STATE.history.filter(h => ids.includes(h.id));
  const retry = hist.length ? STATE.jobs.find(j => j.merge_into === hist[0].id) : null;
  if (!jobs.length && !hist.length) return { state: 'idle' };           // cancelled
  if (retry) return { state: 'retrying', text: retry.phase || 'Retrying…', sub: retry.phase ? '' : `${hist[0].failed.length} item${hist[0].failed.length === 1 ? '' : 's'}` };
  const running = jobs.filter(j => j.status === 'running');
  if (running.length) {
    const retrying = running.find(j => j.phase);
    if (retrying) return { state: 'retrying', text: retrying.phase, sub: '' };
    const frac = (hist.length + running.reduce((a, j) => a + (j.progress ? j.progress.fraction : 0), 0)) / ids.length;
    const p = running[0].progress;
    const detail = p ? [p.item ? `Item ${p.item}` : null, p.part, p.total ? `of ${p.total}`.replace(/^of /, '') : null, p.speed].filter(Boolean).join(' · ') : '';
    return { state: !p || frac <= 0 ? 'starting' : frac >= 1 ? 'processing' : 'downloading', pct: frac * 100, sub: detail };
  }
  const failed = jobs.find(j => j.status === 'failed');
  if (failed) return { state: 'failed', error: failed.error, id: failed.id };
  const waiting = jobs.filter(j => j.status === 'waiting');
  if (waiting.length) { const ahead = STATE.jobs.slice(0, STATE.jobs.indexOf(waiting[0])).filter(j => j.status === 'running' || j.status === 'waiting').length; return { state: 'queued', ahead }; }
  const bad = hist.reduce((n, h) => n + h.failed.length, 0), files = hist.reduce((n, h) => n + h.files.length, 0);
  const size = hist.reduce((n, h) => n + h.files.reduce((a, f) => a + f.size, 0), 0);
  return bad ? { state: 'partial', bad, files, total: hist[0].total, hist: hist[0] } : { state: 'done', files, size };
}
const checkSvg = still => `<svg class="i chk${still ? ' still' : ''}" width="18" height="18" viewBox="0 0 24 24" style="width:18px;height:18px;stroke-width:2.8"><path d="M5 12.5l4.5 4.5L19 7"/></svg>`;
/* what the button shows right now: one place that both the first draw and every later update use */
function goView() {
  const b = buttonInfo(), o = opts(), valid = sectionOk() && !(isPL() && S.plRange && !/^\d+$/.test(S.rFrom)) && !(isPL() && selectionCount(S.media) <= 0);
  const count = isPL() ? selectionCount(S.media) : 1, pct = Math.round(b.pct || 0);
  const cls = { idle: '', queued: 'busy', starting: 'busy', downloading: 'busy', processing: 'busy proc', done: 'done', failed: 'fail', partial: 'warn', retrying: 'busy proc' }[b.state];
  const title = { idle: count > 1 ? `Download ${count} items` : 'Download', queued: `Queued · ${b.ahead} ahead`, starting: 'Starting…', downloading: `Downloading ${pct} %`, processing: 'Processing…',
    done: 'Downloaded', failed: 'Failed · Retry', partial: `Downloaded · ${b.bad} failed`, retrying: b.text || 'Retrying…' }[b.state];
  const sub = { idle: '', queued: 'Starts when a slot is free', starting: `Connecting to ${S.media.site}`, downloading: b.sub || 'Downloading…',
    processing: o.mode === 'video' ? 'Merging video and sound' : o.mode === 'audio' ? 'Converting the audio' : 'Making the GIF',
    done: [b.files > 1 ? `${b.files} files` : null, humanSize(b.size)].filter(Boolean).join(' · '), failed: b.error, partial: `${b.files} of ${b.total || b.files + b.bad} saved`, retrying: b.sub }[b.state] || '';
  return { state: b.state, cls, title, sub, fill: b.state === 'downloading' ? pct : b.state === 'processing' ? 100 : 0,
    disabled: (!valid && b.state === 'idle') || !['idle', 'failed'].includes(b.state), dim: !valid && b.state === 'idle', check: b.state === 'done' };
}
function goButton() {
  const v = goView();
  return `<button class="go ${v.cls}" id="go" data-act="go" data-state="${v.state}" ${v.disabled ? 'disabled' : ''} style="${v.dim ? 'opacity:.45' : ''}">
    <span class="fill" style="width:${v.fill}%"></span><b>${v.check ? checkSvg(true) : ''}<span class="tt">${esc(v.title)}</span></b>${v.sub ? `<small>${esc(v.sub)}</small>` : ''}</button>`;
}
const afterKey = () => { const s = buttonInfo().state; return s === 'done' || s === 'partial' ? s : ''; };
function afterInner() {
  const b = buttonInfo();
  return b.state === 'partial' ? `<button class="link" data-act="retry-failed">Retry ${b.bad} failed</button><button class="link plain" data-act="fail-details">Details</button>`
    : `<button class="link plain" data-act="show-folder">Show in folder</button><button class="link plain" data-act="again">Download again</button>`;
}
function afterLinks() { return `<div class="after ${afterKey() ? 'show' : ''}" id="after" data-k="${afterKey()}">${afterInner()}</div>`; }
/* Updates the button where it stands. It is never rebuilt while a download runs, so the fill glides, the
   text changes without flicker, and the check mark is drawn once and then stays still. */
function patchGo() {
  const g = $('#go'); if (!g || !S.media) return;
  const v = goView(), changed = g.dataset.state !== v.state;
  g.className = 'go ' + v.cls; g.disabled = v.disabled; g.style.opacity = v.dim ? '.45' : '';
  g.querySelector('.fill').style.width = v.fill + '%';
  const tt = g.querySelector('.tt'); if (tt.textContent !== v.title) tt.textContent = v.title;
  let sm = g.querySelector('small');
  if (v.sub) { if (!sm) { sm = document.createElement('small'); g.appendChild(sm); } if (sm.textContent !== v.sub) sm.textContent = v.sub; } else if (sm) { sm.remove(); sm = null; }
  const chk = g.querySelector('.chk');
  if (v.check && !chk) tt.parentElement.insertAdjacentHTML('afterbegin', checkSvg(false)); else if (!v.check && chk) chk.remove();
  if (changed) {
    g.dataset.state = v.state;
    for (const el of [tt, sm]) if (el) { el.classList.remove('swap'); void el.offsetWidth; el.classList.add('swap'); }
  }
  const a = $('#after');
  if (a && a.dataset.k !== afterKey()) { a.dataset.k = afterKey(); a.innerHTML = afterInner(); a.classList.toggle('show', !!afterKey()); }
}

/* ---------- several links at once ---------- */
function batchOptions(m) {
  const mode = P.b_mode === 'audio' || (m.kind !== 'playlist' && !Model.mediaHasVideo(m)) ? 'audio' : 'video';
  return Model.resolveOptions({ ...P, mode, height: P.b_height, container: P.b_container, audio_format: P.b_audio_format }, m, {});
}
function batchCount() {
  return S.batch.filter(b => b.state === 'ok').reduce((n, b) => n + (b.media.kind === 'playlist' && P.b_pl_run === 'separate' ? b.media.entries.length : 1), 0);
}
function batchBody() {
  const n = S.batch.length, reading = S.batch.some(b => b.state === 'reading'), ok = S.batch.filter(b => b.state === 'ok'), total = batchCount();
  const hasPl = ok.some(b => b.media.kind === 'playlist');
  const rows = S.batch.map((b, i) => {
    const m = b.media;
    const body = b.state === 'reading' ? `<div class="th sp"><div class="spin sm"></div></div><div class="m"><div class="t">${esc(b.url)}</div><div class="s">Reading…</div></div>`
      : b.state === 'error' ? `<div class="th"></div><div class="m"><div class="t">${esc(b.url)}</div><div class="s bad">${esc(b.error)}</div></div>`
      : `${thumbHtml(m.thumbnail)}<div class="m"><div class="t">${esc(m.title)}</div><div class="s">${esc([m.site, m.kind === 'playlist' ? 'playlist' : (m.seconds > 0 ? clock(Math.round(m.seconds)) : '')].filter(Boolean).join(' · '))}</div></div>`;
    return `<div class="job" data-b="${i}">${body}${m && m.kind === 'playlist' ? `<span class="site" style="margin:0">${m.playlist_count} videos</span>` : ''}<button class="icon-btn" data-brm="${i}" aria-label="Remove">${ic('close')}</button></div>`;
  }).join('');
  const f = (l, k, txt) => `<div class="f"><label>${l}</label>${pop(k, txt)}</div>`;
  const opts_ = f('Mode', 'bmode', modeName(P.b_mode)) + (P.b_mode === 'video' ? f('Quality', 'bq', `Up to ${P.b_height}p`) + f('Container', 'bcont', Model.CONTAINER_LABEL[P.b_container])
    : f('Format', 'bafmt', P.b_audio_format === 'mp3' ? `MP3 · ${P.bitrate} kbps` : Model.AUDIO_LABEL[P.b_audio_format])) + (hasPl ? f('Playlists', 'bpl', P.b_pl_run === 'batch' ? 'Batch' : 'Separate') : '');
  const kv = [['Links', n], ['Downloads', reading ? '…' : total], ['At once', `up to ${P.simul}`], ['Saves to', dirFor(P.b_mode)]];
  const sim = Math.min(P.simul, total);
  return `<div class="dl-grid" style="margin-top:6px"><div>${sec('Links · ' + n)}<div class="card">${rows || '<div class="empty">No links left. Paste some above.</div>'}</div>
    <div class="note">Paste or drop more links to add them. Each one is read separately, so a bad link never blocks the rest.</div></div>
    <aside class="card insp"><h3>Applies to all</h3>${opts_}<hr><div class="kv">${kv.map(([a, v]) => `<span>${a}</span><i title="${esc(v)}">${esc(v)}</i>`).join('')}</div>
    <button class="go" data-act="bgo" ${ok.length && !reading ? '' : 'disabled style="opacity:.45"'}><b>${reading ? 'Reading links…' : `Download ${total} ${total === 1 ? 'item' : 'items'}`}</b><small>${reading ? '' : `${sim} at a time, the rest wait in the queue`}</small></button></aside></div>`;
}
let batchTimer = 0;
const rerenderBatch = () => { if (!batchTimer) batchTimer = setTimeout(() => { batchTimer = 0; if (S.phase === 'batch' && S.screen === 'download') render(false); }, 120); };
async function loadBatch(urls) {
  const id = ++S.loadId; S.media = S.preview = null; S.batch = urls.map(url => ({ url, state: 'reading' })); S.url = `${urls.length} links`; S.phase = 'batch'; S.screen = 'download'; render(true);
  let next = 0;
  const worker = async () => { while (next < S.batch.length) {
    const item = S.batch[next++];
    try { const r = await api.info(item.url); if (id !== S.loadId) return; if (r.error) Object.assign(item, { state: 'error', error: r.error }); else Object.assign(item, { state: 'ok', media: r.media }); }
    catch (e) { Object.assign(item, { state: 'error', error: 'Couldn’t read this link.' }); }
    rerenderBatch(); } };
  await Promise.all([worker(), worker(), worker()]);
}

/* ---------- Queue / Settings / Info ---------- */
function relTime(ms) {
  const d = new Date(ms), now = new Date(), t = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  if (now - d < 60000) return 'Just now';
  if (d.toDateString() === now.toDateString()) return 'Today ' + t;
  const y = new Date(now); y.setDate(now.getDate() - 1);
  return d.toDateString() === y.toDateString() ? 'Yesterday' : d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}
function progressLine(j) {
  if (j.phase) return j.phase;
  const p = j.progress; if (!p) return 'Connecting…';
  if (p.fraction >= 1) return 'Processing…';
  return [p.item ? `Item ${p.item}` : null, `${Math.floor(p.fraction * 100)} %`, p.part ? p.part + (p.total ? ` of ${p.total}` : '') : null, p.speed].filter(Boolean).join(' · ') + (p.eta > 0 ? ` · ${clock(p.eta)} left` : '');
}
function histMeta(h) {
  const size = h.files.reduce((a, f) => a + f.size, 0), extra = h.failed.length ? ` · ${h.files.length} of ${h.total || h.files.length + h.failed.length} saved · ${h.failed.length} failed` : (h.files.length > 1 ? ` · ${h.files.length} files` : '');
  const sum = h.summary.split(' · ').filter(x => !/(\d MB|\d KB|\d GB|size unknown)$/.test(x)).join(' · ');
  return `${relTime(h.date)} · ${sum || h.site}${extra}${h.failed.length ? '' : ' · ' + humanSize(size)}`;
}
function runCard(j) {
  return `<div class="job" data-jid="${j.id}">${thumbHtml(j.thumb)}<div class="m"><div class="t">${esc(j.title)}</div><div class="s" data-rs="${j.id}">${esc(progressLine(j))}</div><div class="prog"><i data-rp="${j.id}" style="width:${j.progress ? Math.floor(j.progress.fraction * 100) : 0}%"></i></div></div><button class="icon-btn" data-act="q-cancel" data-id="${j.id}" aria-label="Cancel">${ic('close')}</button></div>`;
}
function queueSig() { return STATE.jobs.map(j => j.id + j.status + (j.phase || '')).join('|') + '#' + STATE.history.map(h => h.id + h.files.length + h.failed.length).join('|') + '#' + STATE.simul; }
function patchQueue() {
  STATE.jobs.filter(j => j.status === 'running').forEach(j => { const b = $(`[data-rp="${j.id}"]`), t = $(`[data-rs="${j.id}"]`);
    if (b) b.style.width = (j.progress ? Math.floor(j.progress.fraction * 100) : 0) + '%'; if (t) t.textContent = progressLine(j); });
}
function viewQueue() {
  const running = STATE.jobs.filter(j => j.status === 'running'), failed = STATE.jobs.filter(j => j.status === 'failed'), waiting = STATE.jobs.filter(j => j.status === 'waiting');
  const card = rows => `<div class="card">${rows}</div>`;
  const hrows = STATE.history.map(h => `<div class="job hist" data-h="${h.id}">${thumbHtml(h.thumb)}<div class="m"><div class="t">${esc(h.title)}</div><div class="s ${h.failed.length ? 'warn' : ''}">${esc(histMeta(h))}</div></div>
    ${h.failed.length ? `<button class="link" data-act="h-retry" data-id="${h.id}">Retry ${h.failed.length} failed</button>` : ''}<button class="icon-btn" data-more="${h.id}" aria-label="More" aria-haspopup="menu">${ic('more')}</button></div>`).join('');
  const none = !STATE.jobs.length && !STATE.history.length;
  return `<div class="view" id="v-queue"><h1>Queue</h1>${none ? `<div class="empty">Nothing here yet. Downloads you start appear here, then move to History when done.</div>` : ''}
    ${running.length ? `<div class="sechead"><div class="sec">Downloading · ${running.length} of ${P.simul} at a time</div><span class="note" style="padding:0 4px 4px">Change in Settings</span></div>${card(running.map(runCard).join(''))}` : ''}
    ${failed.length ? sec('Failed') + card(failed.map(j => `<div class="job">${thumbHtml(j.thumb)}<div class="m"><div class="t">${esc(j.title)}</div><div class="s bad">${esc(j.error)}</div></div><button class="link" data-act="q-retry" data-id="${j.id}">Retry</button><button class="link plain" data-act="q-cancel" data-id="${j.id}">Remove</button></div>`).join('')) : ''}
    ${waiting.length ? sec(`Up next · ${waiting.length}`) + card(waiting.map(j => `<div class="job">${thumbHtml(j.thumb)}<div class="m"><div class="t">${esc(j.title)}</div><div class="s">${esc([j.site, j.summary].filter(Boolean).join(' · '))}</div></div><button class="icon-btn" data-act="q-cancel" data-id="${j.id}" aria-label="Remove">${ic('close')}</button></div>`).join('')) : ''}
    ${STATE.history.length ? `<div class="sechead"><div class="sec">History</div><button class="link plain" data-act="clear-hist">Clear</button></div>${card(hrows)}<div class="note" style="text-align:center">Double-click to open · right-click or ⋯ for Show in Explorer, Open link again, Delete</div>` : ''}
  </div>`;
}
function viewSettings() {
  const dir = (l, k) => row(l, `<span class="path" title="${esc(P[k])}"><bdi>${esc(P[k])}</bdi></span><button class="link" data-choose="${k}">Choose…</button>`);
  const step = (k, lo, hi) => `<span class="stepper" data-step="${k}"><button data-d="-1" ${P[k] <= lo ? 'disabled' : ''} aria-label="Less">−</button><em>${P[k]}</em><button data-d="1" ${P[k] >= hi ? 'disabled' : ''} aria-label="More">+</button></span>`;
  return `<div class="view" id="v-settings"><h1>Settings</h1>
    ${sec('Appearance')}<div class="card">${row('Dark mode', dayNight(P.dark), 'Starts dark. Flip the switch to move between night and day.')}</div>
    ${sec('Save to')}<div class="card">${dir('Video', 'dir_video')}${dir('Audio', 'dir_audio')}${dir('GIF', 'dir_gif')}</div>
    <div class="note">Opens the normal Windows folder picker. Each kind of file can go anywhere you like.</div>
    ${sec('Behaviour')}<div class="card">${row('Fill in copied links', tog('clip', P.clip), 'Reads a link from the clipboard when the window comes forward')}${row('Notify when downloads finish', tog('notify', P.notify), 'A Windows notification when the queue is done')}</div>
    ${sec('Subtitle defaults')}<div class="card">${row('Language', pop('lang', langName(P.sub_lang)))}${row('Include auto-generated', tog('auto_subs', P.auto_subs))}${row('Embed in video', tog('embed_subs', P.embed_subs))}</div>
    <div class="note">Not embedded = saved as a separate .srt file next to the video.</div>
    ${sec('Downloading')}<div class="card">${row('Simultaneous downloads', step('simul', 1, 6), 'How many downloads run at the same time')}${row('Parallel fragments' + tip('fragments'), step('fragments', 1, 16), 'Speed-up inside one download')}${row('Speed limit', pop('rate', (RATES.find(r => r[0] === P.rate_limit) || RATES[0])[1]))}${row('Retries', step('retries', 0, 30), 'Tries per failed connection')}</div>
    ${sec('Network')}<div class="card">${row('Proxy' + tip('proxy'), `<input class="field" style="width:260px" data-in="proxy" value="${esc(P.proxy)}" placeholder="Off · socks5://host:1080" aria-label="Proxy">`)}${row('Force IPv4' + tip('ipv4'), tog('force_ipv4', P.force_ipv4))}</div>
    ${sec('yt-dlp')}<div class="card">${row('Update channel' + tip('channel'), pop('chan', P.nightly ? 'Nightly' : 'Stable'))}${row('Clear yt-dlp cache', `<button class="link" data-act="clear-cache">Clear</button>`)}</div>
    <div class="note">Nightly often fixes a broken site days before stable. yt-dlp's cache stores small helper data between links; it clears itself after updates and when a download fails.</div></div>`;
}
function viewInfo() {
  if (!S.versions) api.versions().then(v => { S.versions = v; fillFoot(); if (S.screen === 'info') render(false); });
  if (!S.sites) api.sites().then(s => { S.sites = s; if (S.screen === 'info') render(false); });
  const q = S.siteQ.trim().toLowerCase(), list = (S.sites || []).filter(x => !q || x.toLowerCase().includes(q)), groups = {};
  list.forEach(x => { const l = /[a-z]/i.test(x[0]) ? x[0].toUpperCase() : '#'; (groups[l] = groups[l] || []).push(x); });
  const sites = !S.sites ? `<div class="note" style="padding:14px 6px">Loading the list from yt-dlp…</div>` : Object.keys(groups).sort().map(l => `<div class="letter">${l}</div><div class="card">${groups[l].map(n => `<div class="site-row">${esc(n)}</div>`).join('')}</div>`).join('')
    || `<div class="note" style="padding:14px 6px">No site matches “${esc(S.siteQ)}”. yt-dlp may still handle the link as a generic page.</div>`;
  const v = S.versions || { yt_dlp: '…', ffmpeg: '…', app: '' };
  return `<div class="view" id="v-info"><h1>Info</h1>
    <div class="vers"><div class="card"><span>yt-dlp · ${P.nightly ? 'nightly' : 'stable'}</span><b>${esc(v.yt_dlp)}</b></div><div class="card"><span>ffmpeg</span><b>${esc(v.ffmpeg)}</b></div></div>
    <div class="card" style="margin-top:10px"><div class="row"><span class="lbl">Update yt-dlp now</span><button class="link" data-act="update" id="upd">${esc(S.upd)}</button></div><div class="row"><span class="lbl">App version</span><span class="val">${esc(v.app)}</span></div></div>
    ${sec(`Supported sites${S.sites ? ' · ' + S.sites.length.toLocaleString() : ''}`)}
    <label class="search">${ic('search')}<input id="siteq" placeholder="Search sites" value="${esc(S.siteQ)}" spellcheck="false"></label><div id="sitelist">${sites}</div></div>`;
}
function fillFoot() {
  const f = $('#foot'); if (!f) return;
  f.innerHTML = S.tools.ready ? `<i></i>yt-dlp ${esc(S.versions ? S.versions.yt_dlp : '')}<br>Updates itself daily` : `<i style="background:var(--warn)"></i>Setup needed<br>Open Download`;
}

/* ---------- render ---------- */
let lastScreen = null;
function render(animate) {
  const main = $('#main'), sc = main.scrollTop, focusId = document.activeElement && document.activeElement.id;
  main.innerHTML = { download: viewDownload, queue: viewQueue, settings: viewSettings, info: viewInfo }[S.screen]();
  if (animate || lastScreen !== S.screen) { $('.view', main).classList.add('enter'); main.scrollTop = 0; } else main.scrollTop = sc;
  lastScreen = S.screen;
  $$('#nav button').forEach(b => b.classList.toggle('on', b.dataset.nav === S.screen));
  placeInd();
  if (focusId) { const el = document.getElementById(focusId); if (el && el.setSelectionRange) { el.focus(); const n = el.value.length; el.setSelectionRange(n, n); } }
}
function placeInd() { const b = $(`#nav button[data-nav="${S.screen}"]`); if (b) $('#ind').style.transform = `translateY(${b.offsetTop}px)`; }

/* ---------- actions ---------- */
let toastT; function toast(msg) { const t = $('#toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('show'), 2400); }
function dialog(title, body, confirm, onOk, danger, cancelLabel = 'Cancel') {
  const d = document.createElement('div'); d.className = 'scrim';
  d.innerHTML = `<div class="dialog" role="alertdialog" aria-label="${esc(title)}"><h3>${esc(title)}</h3><p>${body}</p><div class="acts"><button class="btn" data-x="cancel">${esc(cancelLabel)}</button><button class="btn ${danger ? 'del' : ''}" data-x="ok">${esc(confirm)}</button></div></div>`;
  d.addEventListener('mousedown', e => { if (e.target === d) closeDialog(); });
  d.addEventListener('click', e => { const x = e.target.closest('[data-x]'); if (!x) return; closeDialog(); if (x.dataset.x === 'ok') onOk(); });
  $('#dialogs').appendChild(d); $('[data-x="cancel"]', d).focus();
}
function closeDialog() { $('#dialogs').innerHTML = ''; }
function failDialog(h) {
  const n = h.failed.length;
  dialog(`${n} item${n === 1 ? '' : 's'} couldn’t be downloaded`, `The other ${h.files.length} ${h.files.length === 1 ? 'is' : 'are'} saved. Each failed item was tried 3 times.<br><br>` +
    h.failed.map(f => `<b style="color:var(--text)">${String(f.index).padStart(2, '0')} · ${esc(f.title)}</b><br>${esc(f.reason)}`).join('<br><br>'), 'Retry failed items', () => retryFailed(h), false, 'Close');
}
async function retryFailed(h) { const id = await api.retry_failed(h.id); if (id) { const k = Object.keys(S.started).find(k => (S.started[k] || []).includes(h.id)); if (k) S.started[k].push(id); WATCH.add(id); poll(); } }

function resetPerVideo() { S.trim = false; S.nameOn = false; S.name = ''; S.plRange = false; S.rFrom = '1'; S.rTo = ''; }
async function loadLink(url) {
  const id = ++S.loadId; S.url = url; S.phase = 'loading'; S.screen = 'download'; S.media = S.preview = null; S.error = null; S.batch = []; resetPerVideo(); render(false);
  api.preview(url).then(p => { if (id === S.loadId && p && S.phase === 'loading') { S.preview = p; S.phase = 'preview'; render(false); } }).catch(() => {});   // only while still waiting: a late preview must never cover the result
  let r;
  try { r = await Promise.race([api.info(url), new Promise(res => setTimeout(() => res({ error: 'This is taking too long. Check your connection and try again.' }), 120000))]); }
  catch (e) { r = { error: 'Couldn’t read this link.' }; }
  if (id !== S.loadId) return;
  if (r.error) { S.phase = 'error'; S.error = r.error; S.preview = null; render(false); return; }
  S.media = r.media; S.phase = 'loaded'; S.preview = null;
  S.from = clock(0); S.to = clock(r.media.seconds > 0 ? Math.min(5, r.media.seconds) : 10);   // unknown length: 10 s covers a short clip whole
  render(false);
}
async function openLinks(text) {
  const links = await api.links(text);
  if (!links.length) { S.phase = 'error'; S.error = 'That doesn’t look like a link.'; S.media = S.preview = null; S.screen = 'download'; render(false); }
  else if (links.length === 1) loadLink(links[0]); else loadBatch(links);
}
async function pasteClipboard() {
  const links = await api.clipboard_links();
  if (!links.length) return toast('There’s no link on the clipboard');
  if (links.length === 1) loadLink(links[0]); else loadBatch(links);
}
function specsFor(m, o, plRun) {
  const base = { url: m.url, thumb: m.thumbnail, site: m.site, info_file: m.info_file };
  if (m.kind !== 'playlist') return [{ ...base, title: o.custom_name || m.title, options: o, summary: Model.summary(o, m) }];
  const titles = Object.fromEntries(m.entries.map(e => [e.index, e.title]));
  const lo = o.range_from ?? 1, hi = o.range_to ?? Infinity, picked = m.entries.filter(e => e.index >= lo && e.index <= hi);
  if (plRun === 'batch') return [{ ...base, title: o.custom_name || m.title, options: o, summary: Model.summary(o, m), playlist_total: m.playlist_count, entry_titles: titles }];
  return picked.filter(e => e.url).map(e => ({ url: e.url, thumb: e.thumbnail || m.thumbnail, site: m.site, title: e.title, summary: Model.summary(o, m),
    options: { ...o, playlist: false, range_from: null, range_to: null, index: e.index, playlist_title: m.title } }));
}
const WATCH = new Set();     // jobs started in this session: only these pop up a "finished" message
async function startDownload() {
  const key = keyOf(), specs = specsFor(S.media, opts(), P.pl_run);
  if (!specs.length) return toast('Nothing to download');
  const ids = await api.add_jobs(specs); ids.forEach(i => WATCH.add(i)); S.started[key] = ids; poll();
}
async function startBatch() {
  const specs = S.batch.filter(b => b.state === 'ok').flatMap(b => specsFor(b.media, batchOptions(b.media), P.b_pl_run));
  if (!specs.length) return;
  const ids = await api.add_jobs(specs); ids.forEach(i => WATCH.add(i));
  toast(`${specs.length} download${specs.length === 1 ? '' : 's'} queued`);
  S.url = ''; S.phase = 'empty'; S.batch = []; S.screen = 'queue'; await poll(); render(true);
}
function histMenu(id, anchor, at) {
  const h = STATE.history.find(x => x.id === id); if (!h) return;
  showMenu(anchor, [{ id: 'open', label: 'Open', icon: 'open' }, { id: 'show', label: 'Show in Explorer', icon: 'folder' }, { id: 'again', label: 'Open link again', icon: 'link' }, { id: 'copy', label: 'Copy link', icon: 'copy' }, { sep: 1 },
    { id: 'del', label: `Delete file${h.files.length > 1 ? 's' : ''}…`, icon: 'trash', danger: true }], { align: 'right', at, onPick: async pick => {
    if (pick === 'open') api.open_file(id); else if (pick === 'show') api.reveal(id);
    else if (pick === 'copy') { try { await navigator.clipboard.writeText(h.url); toast('Link copied'); } catch (e) { toast('Couldn’t copy the link'); } }
    else if (pick === 'again') loadLink(h.url);
    else if (pick === 'del') dialog(`Delete file${h.files.length > 1 ? 's' : ''}?`, `“${esc(h.title)}” will be moved to the Recycle Bin, not just removed from History.`, 'Delete', async () => {
      const row_ = $(`.job.hist[data-h="${id}"]`); if (row_) row_.classList.add('gone');
      const ok = await api.delete_files(id); setTimeout(() => { poll(); toast(ok ? 'Moved to the Recycle Bin' : 'Windows didn’t allow deleting the file; remove it in Explorer.'); }, 280); }, true);
  } });
}

/* ---------- live state from the backend ---------- */
let polling = false, prevJobs = new Map();
async function poll() {
  if (polling) return; polling = true;
  try { STATE = await api.state(); onState(); } catch (e) { /* the backend is busy; try again next tick */ } finally { polling = false; }
}
function onState() {
  const active = STATE.jobs.filter(j => j.status === 'waiting' || j.status === 'running').length, b = $('#qbadge');
  b.style.display = active ? '' : 'none'; b.textContent = active;
  // a watched job that left the queue has finished (or been cancelled)
  const now = new Map(STATE.jobs.map(j => [j.id, j]));
  for (const [id, j] of prevJobs) if (!now.has(id) && WATCH.has(id)) {
    const h = STATE.history.find(x => x.id === id || x.id === j.merge_into);
    if (!h) continue;
    if (h.failed.length) failDialog(h); else toast(`Saved to ${(h.files[0] && h.files[0].path.replace(/[\\/][^\\/]*$/, '')) || dirFor(h.mode)}`);
  }
  prevJobs = now;
  if (S.screen === 'queue') { const sig = queueSig(); if (sig !== S.qsig) { S.qsig = sig; render(false); } else patchQueue(); }
  else if (S.screen === 'download') patchGo();
}

/* ---------- events ---------- */
document.addEventListener('click', e => {
  const t = e.target;
  const nav = t.closest('[data-nav]'); if (nav) { S.screen = nav.dataset.nav; closeMenu(true); S.qsig = null; render(true); return; }
  const p = t.closest('[data-pop]');
  if (p && !p.disabled) {
    if (openMenu && openMenu.btn === p) { closeMenu(); return; }
    const k = p.dataset.pop, def = menuFor(k);
    showMenu(p, def.items, { header: def.header, onPick: id => { applyPick(k, id); render(false); const np = $(`[data-pop="${k}"]`); np && np.focus(); } }); return;
  }
  const tg = t.closest('[data-tog]');
  if (tg) {
    const k = tg.dataset.tog;
    if (k === 'trim' || k === 'nameOn') { S[k] = !S[k]; if (k === 'trim' && S.trim) { S.from = '0:00'; S.to = clock(S.media && S.media.seconds > 0 ? Math.min(5, S.media.seconds) : 5); } tg.setAttribute('aria-checked', S[k]); }
    else { setP(k, !P[k]); tg.setAttribute('aria-checked', !!P[k]); if (k === 'dark') applyTheme(true); }
    const on = k === 'trim' || k === 'nameOn' ? S[k] : P[k];
    if (['trim', 'nameOn', 'own_folder', 'subtitles'].includes(k)) {
      const nx = tg.closest('.row').nextElementSibling; if (nx && nx.classList.contains('xp')) { nx.classList.toggle('open', on); if (on) followOpen(k); }
      setTimeout(() => render(false), 380);
    }
    return;
  }
  const st = t.closest('[data-step] button');
  if (st && !st.disabled) { const k = st.closest('[data-step]').dataset.step; setP(k, P[k] + +st.dataset.d); render(false); return; }
  const mo = t.closest('[data-more]'); if (mo) { if (openMenu && openMenu.btn === mo) { closeMenu(); return; } histMenu(mo.dataset.more, mo); return; }
  const br = t.closest('[data-brm]'); if (br) { S.batch.splice(+br.dataset.brm, 1); S.url = S.batch.length + ' links'; render(false); return; }
  const ch = t.closest('[data-choose]'); if (ch) { const k = ch.dataset.choose; api.choose_folder(P[k]).then(d => { if (d) { setP(k, d); render(false); } }); return; }
  const a = t.closest('[data-act]'); if (!a) return;
  switch (a.dataset.act) {
    case 'paste': pasteClipboard(); break;
    case 'clear': ++S.loadId; S.url = ''; S.phase = 'empty'; S.media = S.preview = null; S.batch = []; render(false); setTimeout(() => $('#url') && $('#url').focus(), 0); break;
    case 'retry': loadLink(S.url); break;
    case 'setup': startSetup(); break;
    case 'go': { const b = buttonInfo(); if (b.state === 'idle') startDownload(); else if (b.state === 'failed') api.retry_job(b.id).then(poll); break; }
    case 'bgo': startBatch(); break;
    case 'retry-failed': { const b = buttonInfo(); if (b.hist) retryFailed(b.hist); break; }
    case 'fail-details': { const b = buttonInfo(); if (b.hist) failDialog(b.hist); break; }
    case 'show-folder': { const h = (S.started[keyOf()] || []).map(id => STATE.history.find(x => x.id === id)).find(Boolean); if (h) api.reveal(h.id); break; }
    case 'again': delete S.started[keyOf()]; patchGo(); break;
    case 'h-retry': { const h = STATE.history.find(x => x.id === a.dataset.id); if (h) { toast(`Retrying ${h.failed.length} item${h.failed.length === 1 ? '' : 's'}…`); retryFailed(h); } break; }
    case 'q-retry': api.retry_job(a.dataset.id).then(poll); break;
    case 'q-cancel': api.remove_job(a.dataset.id).then(poll); break;
    case 'clear-hist': dialog('Clear history?', 'This only empties the list. Your downloaded files stay where they are.', 'Clear', async () => { await api.clear_history(); poll(); }); break;
    case 'clear-cache': api.clear_cache().then(() => toast('yt-dlp cache cleared')); break;
    case 'update': { if (S.upd === 'Checking…') break; S.upd = 'Checking…'; $('#upd').textContent = S.upd;
      api.update_ytdlp().then(r => { S.upd = { updated: 'Updated', current: 'Up to date', managed: 'Managed by pip', failed: 'Failed' }[r.status] || 'Check'; S.versions = { ...(S.versions || {}), yt_dlp: r.version }; fillFoot(); if (S.screen === 'info') render(false); if (r.status === 'managed' || r.status === 'failed') toast(r.message); }).catch(() => { S.upd = 'Failed'; render(false); }); break; }
  }
});
/* a section that rolls open below the fold: ease the page up with it, only as far as needed to keep it in view */
function followOpen(k) {
  const main = $('#main'), t0 = performance.now();
  const step = () => {
    const r = $(`[data-tog="${k}"]`), xp = r && r.closest('.row').nextElementSibling;
    if (xp && xp.classList.contains('xp')) { const over = xp.getBoundingClientRect().bottom - (main.getBoundingClientRect().bottom - 24); if (over > 0.5) main.scrollTop += Math.max(1, over * 0.22); }
    if (performance.now() - t0 < 650) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
document.addEventListener('contextmenu', e => { const r = e.target.closest('.job.hist'); if (r) { e.preventDefault(); histMenu(r.dataset.h, null, { x: e.clientX, y: e.clientY }); } });
document.addEventListener('dblclick', e => { const r = e.target.closest('.job.hist'); if (r) api.open_file(r.dataset.h); });
document.addEventListener('input', e => {
  const t = e.target;
  if (t.id === 'siteq') { S.siteQ = t.value; const keep = t.selectionStart; render(false); const n = $('#siteq'); n.focus(); n.setSelectionRange(keep, keep); return; }
  if (t.id === 'url') { S.url = t.value; return; }
  const k = t.dataset.in; if (!k || k === 'proxy') return;
  if (k === 'rFrom' || k === 'rTo') { S[k] = t.value.replace(/\D/g, ''); t.value = S[k]; if (k === 'rFrom') t.classList.toggle('err', S.plRange && !S.rFrom); }
  else S[k] = t.value;
  if (k === 'from' || k === 'to') { const bad = !sectionOk(); $$('[data-in="from"],[data-in="to"]').forEach(f => f.classList.toggle('err', bad)); const h = $('.note', t.closest('.card')); if (effMode() === 'gif' && h) h.textContent = sectionHint(); }
  if (S.media) { const g = $('#go'); if (g) { patchGo(); const kv = $('.kv'); if (kv) kv.innerHTML = summaryRows().map(([a, v]) => `<span>${a}</span><i title="${esc(v)}">${esc(v)}</i>`).join(''); } }
});
document.addEventListener('change', e => { if (e.target.dataset.in === 'proxy') setP('proxy', e.target.value.trim()); });
const tokens = t => (t || '').split(/[\s,]+/).filter(x => /\./.test(x) && x.length > 6);
document.addEventListener('paste', e => { if (e.target.id !== 'url') return; const txt = e.clipboardData.getData('text'); if (tokens(txt).length > 1) { e.preventDefault(); openLinks(txt); } });
document.addEventListener('keydown', e => {
  if (e.target.id === 'url' && e.key === 'Enter' && S.url.trim()) { e.preventDefault(); openLinks(S.url); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v' && !/INPUT|TEXTAREA/.test(document.activeElement.tagName) && S.screen === 'download' && S.tools.ready) { e.preventDefault(); pasteClipboard(); }
});
// dropping a link (or a few) anywhere on the window
addEventListener('dragover', e => { e.preventDefault(); document.body.classList.add('drop'); });
addEventListener('dragleave', e => { if (!e.relatedTarget) document.body.classList.remove('drop'); });
addEventListener('drop', e => { e.preventDefault(); document.body.classList.remove('drop'); const txt = e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain'); if (txt && S.tools.ready) openLinks(txt); });
// a link copied while the app was in the background is filled in when it comes forward
async function clipFill() {
  if (!P.clip || !S.tools.ready || S.screen !== 'download' || S.phase !== 'empty' || document.querySelector('.scrim')) return;
  const links = await api.clipboard_links(); if (!links.length) return;
  const sig = links.join(' '); if (sig === S.lastClip) return; S.lastClip = sig;
  toast('Link filled in from the clipboard'); links.length === 1 ? loadLink(links[0]) : loadBatch(links);
}
addEventListener('focus', () => clipFill().catch(() => {}));

/* ---------- the (i) tooltip: one floating box, so no card or section can clip it ---------- */
const tipBox = document.createElement('div'); tipBox.id = 'tipbox'; tipBox.setAttribute('role', 'tooltip'); document.body.appendChild(tipBox);
let tipT = 0, tipFor = null;
function showTip(el) {
  tipFor = el; tipBox.textContent = el.dataset.tip; tipBox.classList.remove('show');
  const r = el.getBoundingClientRect(), w = Math.min(300, innerWidth - 24);
  tipBox.style.maxWidth = w + 'px';
  let x = Math.max(12, Math.min(r.left - 8, innerWidth - tipBox.offsetWidth - 12)), y = r.bottom + 8;
  if (y + tipBox.offsetHeight > innerHeight - 12) y = Math.max(12, r.top - tipBox.offsetHeight - 8);
  tipBox.style.left = x + 'px'; tipBox.style.top = y + 'px'; tipBox.classList.add('show');
}
function hideTip() { clearTimeout(tipT); tipFor = null; tipBox.classList.remove('show'); }
document.addEventListener('mouseover', e => { const t = e.target.closest('.tip'); if (!t || t === tipFor) return; clearTimeout(tipT); tipT = setTimeout(() => showTip(t), 140); });
document.addEventListener('mouseout', e => { if (e.target.closest('.tip')) hideTip(); });
document.addEventListener('focusin', e => { const t = e.target.closest && e.target.closest('.tip'); if (t) showTip(t); });
document.addEventListener('focusout', hideTip);
document.addEventListener('mousedown', hideTip, true);
addEventListener('keydown', e => { if (e.key === 'Escape') hideTip(); });
$('#main').addEventListener('scroll', hideTip, { passive: true });

/* ---------- sidebar: folds into an icon-only strip (Ctrl+B or the button at its bottom left) ---------- */
function applySidebar() {
  const c = !!P.sidebar_collapsed, b = $('#sbToggle'), label = c ? 'Expand sidebar' : 'Collapse sidebar';
  $('#win').classList.toggle('sb-collapsed', c); b.setAttribute('aria-label', label); b.title = label + ' (Ctrl+B)';
  closeMenu(true);
}
const toggleSidebar = () => { setP('sidebar_collapsed', !P.sidebar_collapsed); applySidebar(); };
$('#sbToggle').addEventListener('click', toggleSidebar);
addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'b') { e.preventDefault(); toggleSidebar(); } });

/* ---------- first-run setup ---------- */
async function startSetup() {
  await api.setup_tools(); S.setup.running = true; render(false);
  const t = setInterval(async () => {
    const s = await api.setup_status(); S.setup = { ...S.setup, ...s };
    if (s.ready && !s.running) { clearInterval(t); S.tools = { ready: true, missing: [] }; S.versions = null; fillFoot(); toast('Ready'); api.versions().then(v => { S.versions = v; fillFoot(); }); }
    if (S.screen === 'download') render(false);
  }, 500);
}

/* ---------- start ---------- */
(async function init() {
  try {
    await ready();
    const b = await api.boot();
    P = b.prefs; S.tools = b.tools; applyTheme(false); applySidebar(); fillFoot(); render(false);
    api.versions().then(v => { S.versions = v; fillFoot(); });
    await poll(); setInterval(poll, 600);
    clipFill().catch(() => {});
  } catch (e) {   // never leave a blank window: say what went wrong
    $('#main').innerHTML = `<div class="view"><h1>Couldn’t start</h1><div class="note">${esc(e && e.message || e)}</div></div>`;
  }
})();
