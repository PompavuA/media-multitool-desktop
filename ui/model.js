/* Pure logic the UI needs: what a link offers (resolutions, codecs, sizes) and which choices are valid.
   A port of the phone app's Model.kt / Prefs.kt. Loaded by the page and by tests/model.test.js. No DOM here. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(); else root.Model = factory();
})(this, function () {
  const CODEC_LABEL = { h264: 'H.264', vp9: 'VP9', av1: 'AV1' };
  const CODEC_PREFIX = { h264: ['avc', 'h264'], vp9: ['vp9', 'vp09'], av1: ['av01', 'av1'] };
  const CONTAINER_LABEL = { mp4: 'MP4', mkv: 'MKV', webm: 'WebM' };
  const AUDIO_LABEL = { original: 'Original', m4a: 'M4A', mp3: 'MP3', opus: 'Opus' };
  const VIDEO_EXTS = ['mp4', 'webm', 'mov', 'm4v', 'mkv', 'gif', '3gp'];
  const BITRATES = [128, 192, 256, 320];
  const GIF_WIDTHS = [320, 480, 640, 800];
  const GIF_FPS = [10, 15, 24, 30];

  const codecMatches = (codec, vcodec) => !!vcodec && CODEC_PREFIX[codec].some(p => vcodec.toLowerCase().startsWith(p));
  const containerAllows = (c, codec) => c !== 'webm' || codec !== 'h264';   // WebM only carries VP9/AV1
  const containerAllowsTrim = c => c !== 'webm';                            // WebM only carries Opus, which can't be cut cleanly

  const hasVideo = f => !!f.vcodec && f.vcodec !== 'none' && f.height != null;
  const hasAudio = f => !!f.acodec && f.acodec !== 'none';
  /** Resolution the way yt-dlp counts it: the shorter side, so a vertical 720x1280 reel is "720p". */
  const res = f => (f.width != null && f.height != null) ? Math.min(f.width, f.height) : f.height;

  const heights = m => [...new Set(m.formats.filter(hasVideo).map(res).filter(h => h != null))].sort((a, b) => b - a);
  /** Sites like X list their "GIF" posts as a plain MP4 with no resolution or codec details. */
  const unlabeledVideo = m => m.formats.some(f => !hasVideo(f) && !hasAudio(f) && VIDEO_EXTS.includes((f.ext || '').toLowerCase()));
  const mediaHasVideo = m => heights(m).length > 0 || unlabeledVideo(m);
  const maxFps = (m, h) => { const fs = m.formats.filter(f => hasVideo(f) && res(f) === h).map(f => f.fps ?? 30); return fs.length ? Math.max(...fs) : 30; };
  const codecsAt = (m, h) => Object.keys(CODEC_LABEL).filter(c => m.formats.some(f => hasVideo(f) && res(f) === h && codecMatches(c, f.vcodec)));
  /** "1080p60" for high frame rate, else "1080p"; "Best quality" when the site lists no resolutions. */
  const label = (m, h) => heights(m).length === 0 ? 'Best quality' : (Math.round(maxFps(m, h)) > 30 ? `${h}p${Math.round(maxFps(m, h))}` : `${h}p`);
  /** Remembered height if this video has it, else the closest one below (or the lowest available). */
  const pickHeight = (m, wanted) => { const hs = heights(m); return hs.find(h => h <= wanted) ?? hs[hs.length - 1] ?? null; };
  /** Remembered codec if available at this height, else the first that is. */
  const pickCodec = (m, h, wanted) => { const cs = codecsAt(m, h); return cs.includes(wanted) ? wanted : (cs[0] ?? null); };
  /** Width / height of the picture (vertical reels are < 1); 16:9 when the site doesn't say. */
  const aspect = m => { const f = m.formats.filter(x => hasVideo(x) && (x.width || 0) > 0).sort((a, b) => b.height - a.height)[0]; return f ? f.width / f.height : 16 / 9; };
  const bestAudio = m => m.formats.filter(f => hasAudio(f) && !hasVideo(f)).sort((a, b) => (b.abr ?? b.tbr ?? 0) - (a.abr ?? a.tbr ?? 0))[0] ?? null;
  const bytes = (m, f) => !f ? null : f.size ? f.size : (f.tbr && m.seconds > 0) ? Math.floor(f.tbr * 125 * m.seconds) : null; // no duration = unknown

  /** Estimated download size in bytes, or null when the site doesn't say. */
  function estimate(m, o) {
    const part = (o.trim && o.mode !== 'gif' && m.seconds > 0) ? Math.min(1, Math.max(0, (o.end - o.start) / m.seconds)) : 1;
    let total = null;
    if (o.mode === 'video') {
      const atH = m.formats.filter(f => hasVideo(f) && res(f) === o.height);
      const same = atH.filter(f => codecMatches(o.codec, f.vcodec));
      const target = o.fps60 ? 60 : 30;
      const v = (same.length ? same : atH).sort((a, b) => Math.abs((a.fps ?? 30) - target) - Math.abs((b.fps ?? 30) - target) || (b.tbr ?? 0) - (a.tbr ?? 0))[0];
      const vb = bytes(m, v);
      const ab = v && hasAudio(v) ? 0 : (bytes(m, bestAudio(m)) ?? 0);
      total = vb != null ? vb + ab : null;
    } else if (o.mode === 'audio') {
      total = o.audio_format === 'original' ? bytes(m, bestAudio(m)) : (m.seconds > 0 ? o.bitrate * 125 * m.seconds : null);
    } else {
      // measured: a dithered GIF costs ~0.4 bytes per pixel per frame (uses the section length, so it works without a duration)
      total = o.gif_width * (o.gif_width / aspect(m)) * o.gif_fps * 0.4 * Math.max(0, o.end - o.start);
    }
    return total == null ? null : Math.floor(total * part);
  }

  function humanSize(b) {
    if (b == null) return 'size unknown';
    if (b >= 1e9) return (b / 1e9).toFixed(1) + ' GB';
    if (b >= 1e7) return Math.round(b / 1e6) + ' MB';
    if (b >= 1e6) return (b / 1e6).toFixed(1) + ' MB';
    return Math.max(1, Math.round(b / 1e3)) + ' KB';
  }

  function clock(sec) {
    const t = Math.round(sec * 10), s = Math.floor(t / 10), f = t % 10, p2 = n => String(n).padStart(2, '0');
    const base = s >= 3600 ? `${Math.floor(s / 3600)}:${p2(Math.floor(s / 60) % 60)}:${p2(s % 60)}` : `${Math.floor(s / 60)}:${p2(s % 60)}`;
    return f ? `${base}.${f}` : base;
  }
  function parseClock(text) {
    const parts = String(text).trim().split(':');
    if (!String(text).trim() || parts.length > 3) return null;
    let total = 0;
    for (const p of parts) { const n = parseFloat(p); if (isNaN(n) || n < 0 || !/^\d*\.?\d*$/.test(p.trim())) return null; total = total * 60 + n; }
    return total;
  }

  /** One line that says exactly what will be downloaded, e.g. "1080p60 · H.264 · MP4 · 154 MB". */
  function summary(o, m) {
    const est = m ? estimate(m, o) : null;
    const size = est != null ? (o.mode === 'gif' ? '≈ ' : '') + humanSize(est) : null;
    const parts = o.mode === 'video'
      ? ((m && heights(m).length === 0) ? ['Best quality', CONTAINER_LABEL[o.container]] : [m ? label(m, o.height) : `${o.height}p`, CODEC_LABEL[o.codec], CONTAINER_LABEL[o.container]])
      : o.mode === 'audio' ? ['Audio', o.audio_format === 'original' ? 'Original' : `${AUDIO_LABEL[o.audio_format]} ${o.bitrate} kbps`]
      : ['GIF', `${o.gif_width} px`, `${o.gif_fps} fps`];
    return [...parts, ...((o.trim || o.mode === 'gif') ? [`${clock(o.start)}–${clock(o.end)}`] : []), ...(size ? [size] : [])].join(' · ');
  }

  /** Saved choices + the per-video bits the screen collects -> the options the backend gets. The fallbacks of Prefs.options(). */
  function resolveOptions(p, m, v) {
    const media = m && m.kind !== 'playlist' ? m : null;
    const h = media ? (pickHeight(media, p.height) ?? p.height) : p.height;
    const c = media ? (pickCodec(media, h, p.codec) ?? p.codec) : p.codec;
    return {
      mode: p.mode, height: h, fps60: p.fps60 && (!media || maxFps(media, h) > 30), codec: c,
      container: (!containerAllows(p.container, c) || (v.trim && !containerAllowsTrim(p.container))) ? 'mkv' : p.container,
      audio_format: p.audio_format, bitrate: p.bitrate, gif_width: p.gif_width, gif_fps: p.gif_fps, gif_loop: p.gif_loop,
      trim: !!v.trim && p.mode !== 'gif', start: v.start ?? 0, end: v.end ?? 5,
      subtitles: !!p.subtitles && p.mode === 'video', sub_lang: p.sub_lang, auto_subs: p.auto_subs, embed_subs: p.embed_subs,
      custom_name: v.custom_name || null, title: media ? media.title : null,
      playlist: !!(m && m.kind === 'playlist'), range_from: v.range_from ?? null, range_to: v.range_to ?? null, own_folder: p.own_folder,
    };
  }

  return { CODEC_LABEL, CONTAINER_LABEL, AUDIO_LABEL, BITRATES, GIF_WIDTHS, GIF_FPS, codecMatches, containerAllows, containerAllowsTrim,
    heights, unlabeledVideo, mediaHasVideo, maxFps, codecsAt, label, pickHeight, pickCodec, aspect, bestAudio, estimate, humanSize,
    clock, parseClock, summary, resolveOptions };
});
