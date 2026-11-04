// Finds, in a finished captioned video, the scene joins (fade-to-black frames) and the frames where
// the caption strip changes, so the voice can be cued without the raw recording.
import { execFileSync } from 'node:child_process';
export function analyse(video) {
  const W = 192, H = 108, FPS = 30;
  const raw = execFileSync('ffmpeg', ['-loglevel', 'error', '-i', video, '-vf', `fps=${FPS},scale=${W}:${H},format=gray`, '-f', 'rawvideo', '-'], { maxBuffer: 1 << 30 });
  const n = raw.length / (W * H);
  const frames = [];
  for (let f = 0; f < n; f++) {
    const o = f * W * H;
    let all = 0, above = 0, band = 0;
    for (let i = 0; i < W * H; i++) all += raw[o + i];
    for (let y = 60; y < 86; y++) for (let x = 0; x < W; x++) above += raw[o + y * W + x];
    for (let y = 90; y < H; y++) for (let x = 0; x < W; x++) band += raw[o + y * W + x];
    frames.push({ all: all / (W * H), above: above / (26 * W), band: band / ((H - 90) * W), o });
  }
  // joins: every cut fades out and the next fades in, so a join is a deep, short dip in brightness
  const joins = [];
  for (let i = 1; i < n - 1; i++) {
    const a = frames[i].all;
    let lo = true, peak = 0;
    for (let k = -6; k <= 6; k++) if (frames[i + k] && frames[i + k].all < a) lo = false;
    for (let k = -18; k <= 18; k++) if (frames[i + k]) peak = Math.max(peak, frames[i + k].all);
    if (lo && a < 0.35 * peak && (!joins.length || i / FPS - joins[joins.length - 1] > 2)) joins.push((i + 0.5) / FPS);
  }
  // caption appearances: band brightness (text) rising after a change in the band's pixels
  const bandSig = (f) => { const o = frames[f].o, s = []; for (let y = 92; y < H - 2; y += 2) for (let x = 0; x < W; x += 2) s.push(raw[o + y * W + x]); return s; };
  const caps = [];
  let prev = null, stableFrom = 0;
  for (let f = 0; f < n; f++) {
    const s = bandSig(f);
    const d = prev ? s.reduce((a, v, i) => a + Math.abs(v - prev[i]), 0) / s.length : 99;
    prev = s;
    if (d > 1.5) { stableFrom = f; continue; }
    if (f - stableFrom === 6) caps.push({ t: stableFrom / FPS, text: frames[f].band, app: frames[f].above > 120 && frames[f].band < 80 });
  }
  return { n, FPS, frames: frames.map(({ all, above, band }) => ({ all, above, band })), joins, caps };
}
if (process.argv[1] && import.meta.filename === (await import('node:path')).resolve(process.argv[1])) {
  const r = analyse(process.argv[2]);
  console.log('frames', r.n, 'joins', r.joins.length, r.joins.map((t) => t.toFixed(2)).join(' '));
  for (const c of r.caps) console.log(c.t.toFixed(2), c.text.toFixed(1), c.app);
}
