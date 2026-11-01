// Port of the phone app's ModelTest.kt cases that cover Media: run with `node --test tests`
const test = require('node:test');
const assert = require('node:assert/strict');
const M = require('../ui/model.js');

const fmt = (h, v, a, fps = 30, size = null, tbr = null, extra = {}) =>
  ({ id: 'x', ext: 'mp4', height: h, width: null, fps, vcodec: v ?? 'none', acodec: a ?? 'none', size, tbr, abr: v ? null : tbr, ...extra });
const media = (formats, seconds = 100, extra = {}) => ({ kind: 'video', url: 'u', title: 'T', seconds, formats, ...extra });
const o = (extra = {}) => ({ mode: 'video', height: 1080, fps60: true, codec: 'h264', container: 'mp4', audio_format: 'original', bitrate: 192,
  gif_width: 480, gif_fps: 15, trim: false, start: 0, end: 5, ...extra });

const video = media([
  fmt(1080, 'avc1.640028', null, 60, 100_000_000), fmt(1080, 'vp09.00', null, 60, 80_000_000),
  fmt(720, 'avc1.4d401f', null, 30, 40_000_000), fmt(null, null, 'opus', 30, null, 160),
]);

test('format choices', () => {
  assert.deepEqual(M.heights(video), [1080, 720]);
  assert.equal(M.label(video, 1080), '1080p60');
  assert.equal(M.label(video, 720), '720p');
  assert.equal(M.pickHeight(video, 1440), 1080);
  assert.equal(M.pickHeight(video, 900), 720);
  assert.equal(M.pickHeight(video, 360), 720);
  assert.deepEqual(M.codecsAt(video, 1080), ['h264', 'vp9']);
  assert.equal(M.pickCodec(video, 720, 'av1'), 'h264');
  assert.ok(!M.containerAllows('webm', 'h264') && M.containerAllows('webm', 'vp9'));
  // vertical reels are labelled by their shorter side, like yt-dlp's -S res
  const reel = media([fmt(1280, 'avc1', 'mp4a', 30, null, 900, { width: 720 }), fmt(840, 'avc1', 'mp4a', 30, null, 500, { width: 472 })], 0);
  assert.deepEqual(M.heights(reel), [720, 472]);
  assert.equal(M.label(reel, 720), '720p');
  assert.equal(M.estimate(reel, o({ height: 720 })), null); // no size and no duration: unknown, not "1 KB"
});

test('unlabeled X GIF', () => {
  const xgif = media([fmt(null, null, null, null, null, null, { id: 'http', ext: 'mp4' })], 0);
  assert.ok(M.mediaHasVideo(xgif));
  assert.equal(M.label(xgif, 1080), 'Best quality');
  assert.equal(M.summary(o(), xgif), 'Best quality · MP4'); // unknown size is left out
  assert.ok(!M.mediaHasVideo(media([fmt(null, null, 'mp4a', null, null, null, { ext: 'm4a' })], 0)));
});

test('sizes', () => {
  // VP9 1080p 80 MB + Opus 160 kbps * 100 s = 2 MB
  assert.equal(M.estimate(video, o({ codec: 'vp9' })), 82_000_000);
  assert.equal(M.estimate(video, o({ codec: 'vp9', trim: true, start: 0, end: 50 })), 41_000_000);
  assert.equal(M.summary(o({ codec: 'vp9' }), video), '1080p60 · VP9 · MP4 · 82 MB');
  assert.equal(M.humanSize(154_000_000), '154 MB');
  assert.equal(M.humanSize(4_200_000), '4.2 MB');
  // GIF size depends on the section only, even when the site gives no duration
  const noDuration = { ...video, seconds: 0 };
  assert.equal(M.estimate(noDuration, o({ mode: 'gif', start: 0, end: 5 })), M.estimate(video, o({ mode: 'gif', start: 10, end: 15 })));
  assert.ok(M.estimate(noDuration, o({ mode: 'gif', start: 0, end: 5 })) > 1_000_000);
  // a vertical reel (9:16) has ~3x the pixels of a 16:9 clip at the same width
  const reel = { ...video, formats: [fmt(1920, 'avc1', null, 30, 1, null, { width: 1080 })] };
  const wide = M.estimate(video, o({ mode: 'gif' }));
  assert.ok(Math.abs(M.estimate(reel, o({ mode: 'gif' })) / wide - (16 / 9) / (9 / 16)) < 0.01);
});

test('clocks', () => {
  assert.equal(M.clock(75.5), '1:15.5');
  assert.equal(M.clock(3700), '1:01:40');
  assert.equal(M.parseClock('1:15.5'), 75.5);
  assert.equal(M.parseClock('1:x'), null);
  assert.equal(M.parseClock('1:2:3:4'), null);
});

test('saved choices fall back to what this video has', () => {
  const p = { mode: 'video', height: 1440, fps60: true, codec: 'av1', container: 'webm', audio_format: 'original', bitrate: 192, gif_width: 480, gif_fps: 15, gif_loop: true,
    subtitles: true, sub_lang: 'en', auto_subs: true, embed_subs: true, own_folder: true };
  const r = M.resolveOptions(p, video, { trim: false });
  assert.equal(r.height, 1080);                 // closest below
  assert.equal(r.codec, 'h264');                // first the video has
  assert.equal(r.container, 'mkv');             // WebM can't carry H.264
  assert.equal(r.fps60, true);                  // 1080 has 60 fps
  assert.equal(r.title, 'T');
  assert.equal(M.resolveOptions({ ...p, height: 720, container: 'mp4' }, video, {}).fps60, false); // 720 is 30 fps only
  assert.equal(M.resolveOptions({ ...p, container: 'webm', codec: 'vp9' }, video, { trim: true }).container, 'mkv'); // WebM can't be cut
  const pl = M.resolveOptions(p, { kind: 'playlist', title: 'P', seconds: 0, formats: [] }, { range_from: 3 });
  assert.equal(pl.playlist, true);
  assert.equal(pl.title, null);
  assert.equal(pl.range_from, 3);
});
