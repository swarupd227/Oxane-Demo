// Builds the narrated, caption-free cut of a walkthrough video, the same way as the Unit4 Studio videos:
//   1. the caption strip in each app scene is filled with the app's canvas colour, so no captions show;
//   2. each line in the narration file is spoken by a Windows voice, sped up only where it would overrun
//      its slot, and laid on its cue.
// It works from the finished captioned video, so nothing is re-recorded: scene joins are the fade-to-black
// dips, and caption cues are the moments the caption strip changed.
//   node voice/build-voice.mjs voice/onboarding.json
//   node voice/build-voice.mjs voice/monitoring.json
// Writes <out>.mp4 (no captions, silent, for a studio voice) and <out>_Draft_Voice.mp4 (Windows voice).
// The first run renames the captioned video to <out>_Captioned.mp4, which stays the source.
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { analyse } from './analyse.mjs';

const ROOT = path.resolve(import.meta.dirname, '..');
process.chdir(ROOT);
const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const FADE = 0.4, BAND_Y = 888, CANVAS = '0xF8F5F1', VOICE = 'Microsoft David Desktop';
const BUILD = path.join('voice', 'build', cfg.out);
fs.rmSync(BUILD, { recursive: true, force: true });
fs.mkdirSync(BUILD, { recursive: true });
const ff = (args) => execFileSync('ffmpeg', ['-loglevel', 'error', '-y', ...args]);
const dur = (f) => +execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f]).toString();

if (!fs.existsSync(cfg.captioned)) fs.renameSync(`${cfg.out}.mp4`, cfg.captioned);
const total = dur(cfg.captioned);

// ---- scenes and caption cues, read from the captioned video
const a = analyse(cfg.captioned);
if (a.joins.length !== cfg.scenes.length - 1) throw new Error(`found ${a.joins.length} scene joins, expected ${cfg.scenes.length - 1}`);
const bounds = [0, ...a.joins, total];
const scenes = cfg.scenes.map((name, i) => ({ name, from: bounds[i], to: bounds[i + 1] }));
const recorder = fs.readFileSync(cfg.out.startsWith('Monitoring') ? 'record-monitoring.mjs' : 'record.mjs', 'utf8');
const order = [...recorder.matchAll(/caption\(C\.(\w+)\)/g)].map((m) => m[1]);
const shown = a.caps.filter((c) => c.app && c.text < 35);
if (shown.length !== order.length) throw new Error(`found ${shown.length} captions, the recorder shows ${order.length}`);
const capAt = Object.fromEntries(order.map((k, i) => [k, shown[i].t - 0.5])); // the strip finishes fading in ~0.6s after it starts

const lines = cfg.lines.map((l) => ({ ...l, cue: l.caption ? capAt[l.caption] : scenes.find((s) => s.name === l.scene).from + l.at }));
lines.forEach((l, i) => { l.until = (lines[i + 1]?.cue ?? total - 0.3) - 0.2; });

// ---- 1. caption-free video: each app scene gets a canvas-coloured band over its strip. The band fades
// in and out with the scene, so it matches the scene's own fades (which are already in the frames).
const graph = [];
scenes.forEach((s, i) => {
  const d = s.to - s.from;
  const clip = `[0:v]trim=start=${s.from.toFixed(4)}:end=${s.to.toFixed(4)},setpts=PTS-STARTPTS`;
  if (cfg.cards.includes(s.name)) { graph.push(`${clip}[v${i}]`); return; }
  graph.push(`${clip}[s${i}]`);
  graph.push(`color=c=${CANVAS}:s=1920x${1080 - BAND_Y}:r=30:d=${d.toFixed(4)},format=yuv420p,fade=t=in:st=0:d=${FADE},fade=t=out:st=${(d - FADE).toFixed(3)}:d=${FADE}[b${i}]`);
  graph.push(`[s${i}][b${i}]overlay=0:${BAND_Y}:shortest=1[v${i}]`);
});
graph.push(`${scenes.map((_, i) => `[v${i}]`).join('')}concat=n=${scenes.length}:v=1:a=0[vout]`);
const silent = `${cfg.out}.mp4`;
ff(['-i', cfg.captioned, '-filter_complex', graph.join(';'), '-map', '[vout]',
  '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', '30', '-an', '-movflags', '+faststart', silent]);
console.log(`wrote ${silent} (${dur(silent).toFixed(2)}s)`);

// ---- 2. draft voice
const speak = (text, rate, file) => {
  const ps = `Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer;
    $s.SelectVoice('${VOICE}'); $s.Rate = ${rate}; $s.SetOutputToWaveFile('${path.resolve(file)}');
    $s.Speak([Console]::In.ReadToEnd()); $s.Dispose()`;
  execFileSync('powershell', ['-NoProfile', '-Command', ps], { input: text });
};
const inputs = [], delays = [];
let overruns = 0;
lines.forEach((line, i) => {
  const slot = line.until - line.cue;
  const file = path.join(BUILD, `line-${String(i).padStart(2, '0')}.wav`);
  let rate = 0;
  speak(line.text, rate, file);
  while (dur(file) > slot && rate < 3) { rate += 1; speak(line.text, rate, file); }
  const d = dur(file);
  if (d > slot) overruns++;
  console.log(`${line.cue.toFixed(1).padStart(6)}  ${(line.caption || line.scene).padEnd(12)} ${d.toFixed(2)}s of ${slot.toFixed(2)}s  rate ${rate}${d > slot ? '  OVERRUNS' : ''}`);
  inputs.push('-i', file);
  delays.push(`[${i + 1}:a]adelay=${Math.round(line.cue * 1000)}:all=1[a${i}]`);
});
const mix = `${delays.join(';')};${lines.map((_, i) => `[a${i}]`).join('')}amix=inputs=${lines.length}:normalize=0,apad[aout]`;
const voiced = `${cfg.out}_Draft_Voice.mp4`;
ff(['-i', silent, ...inputs, '-filter_complex', mix, '-map', '0:v', '-map', '[aout]', '-c:v', 'copy',
  '-c:a', 'aac', '-b:a', '160k', '-t', dur(silent).toFixed(3), '-movflags', '+faststart', voiced]);
fs.writeFileSync(path.join(BUILD, 'cues.json'), JSON.stringify(lines.map(({ caption, scene, cue, until, text }) => ({ caption, scene, cue: +cue.toFixed(2), until: +until.toFixed(2), text })), null, 2));
console.log(`wrote ${voiced} (${dur(voiced).toFixed(2)}s)${overruns ? `, ${overruns} line(s) overrun` : ''}`);
