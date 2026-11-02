// Same as the Migration Studio assembler. Cut each scene out of the raw Playwright video and join them into one H.264 MP4.
// Scene boundaries come from the solid magenta (before) / cyan (after) flashes the recorder draws,
// found in the video itself: Playwright's video timeline drifts from wall-clock time, so logged
// timestamps alone can't be trusted.
import fs from "node:fs";
import { execFileSync } from "node:child_process";

const { video, segments } = JSON.parse(fs.readFileSync("segments.json", "utf8"));
const out = process.argv[2] || "Onboarding_Workbench_Demo.mp4";
const FPS = 30, W = 16, H = 9, FADE = 0.4, MARGIN = 0.12;

const raw = execFileSync("ffmpeg", ["-loglevel", "error", "-i", video, "-vf", `fps=${FPS},scale=${W}:${H},format=rgb24`, "-f", "rawvideo", "-"], { maxBuffer: 1 << 30 });
const frameBytes = W * H * 3;
const kinds = [];
for (let off = 0; off + frameBytes <= raw.length; off += frameBytes) {
  let r = 0, g = 0, b = 0;
  for (let p = off; p < off + frameBytes; p += 3) { r += raw[p]; g += raw[p + 1]; b += raw[p + 2]; }
  const n = W * H; r /= n; g /= n; b /= n;
  kinds.push(r > 220 && g < 50 && b > 220 ? "M" : r < 50 && g > 220 && b > 220 ? "C" : "-");
}
const runs = [];
kinds.forEach((k, i) => {
  if (k === "-") return;
  const last = runs[runs.length - 1];
  if (last && last.kind === k && last.end === i - 1) last.end = i; else runs.push({ kind: k, start: i, end: i });
});
// A real flash lasts ~12 frames; shorter runs are on-screen content that happens to match.
for (let i = runs.length - 1; i >= 0; i--) if (runs[i].end - runs[i].start < 4) runs.splice(i, 1);
const markers = [];
for (let i = 0; i < runs.length; i++) {
  if (runs[i].kind === "C" && (i === 0 || runs[i - 1].kind === "C")) {
    // An end flash with no start flash before it: the encoder dropped the start. Cut back from the end
    // flash by that scene's logged length (scenes are in order, so it is the next unmatched scene).
    const scene = segments[markers.length];
    if (scene) markers.push({ from: runs[i].start / FPS - MARGIN - (scene.end - scene.start), to: runs[i].start / FPS - MARGIN, synthetic: true });
    continue;
  }
  if (runs[i].kind !== "M") continue;
  const c = runs.slice(i + 1).find((r) => r.kind === "C");
  if (!c) break;
  markers.push({ from: (runs[i].end + 1) / FPS + MARGIN, to: c.start / FPS - MARGIN });
}
console.log(`found ${markers.length} scene markers (expected ${segments.length})`);
if (markers.length < segments.length) throw new Error("fewer scene markers than scenes in the log");

// On-screen content can match a flash colour and add a marker the recorder never drew, so the
// markers aren't always one per scene. Pick, in order, the run of markers whose lengths match the
// scenes' own logged lengths most closely (a small dynamic program over "use this marker or skip it").
const dur = (c) => c.to - c.from;
const want = segments.map((s) => s.end - s.start);
const INF = Infinity;
const cost = Array.from({ length: want.length + 1 }, () => new Array(markers.length + 1).fill(INF));
const back = Array.from({ length: want.length + 1 }, () => new Array(markers.length + 1).fill(0));
for (let j = 0; j <= markers.length; j++) cost[0][j] = 0;
for (let i = 1; i <= want.length; i++) {
  for (let j = 1; j <= markers.length; j++) {
    const take = cost[i - 1][j - 1] === INF ? INF : cost[i - 1][j - 1] + Math.abs(dur(markers[j - 1]) - want[i - 1]);
    const skip = cost[i][j - 1];
    if (take <= skip) { cost[i][j] = take; back[i][j] = 1; } else { cost[i][j] = skip; back[i][j] = 0; }
  }
}
const chosen = [];
for (let i = want.length, j = markers.length; i > 0 && j > 0; ) {
  if (back[i][j] === 1) { chosen.unshift(j - 1); i--; j--; } else j--;
}
if (chosen.length !== segments.length) throw new Error("scene markers don't match the scene log");
if (markers.length !== segments.length) console.log(`  using markers ${chosen.join(",")} (dropped ${markers.length - segments.length})`);

// A closing flash the encoder dropped would let a cut run on into the next page load -- dead air
// with no caption. The scene's own logged length is the ceiling, with a little slack for drift.
const cuts = chosen.map((j, i) => ({ from: markers[j].from, to: Math.min(markers[j].to, markers[j].from + want[i] + 1.5) }));

fs.rmSync("cuts", { recursive: true, force: true });
fs.mkdirSync("cuts");
const list = [];
cuts.forEach((c, i) => {
  const name = segments[i].name;
  const dur = c.to - c.from;
  const file = `${String(i).padStart(2, "0")}-${name}.mp4`;
  execFileSync("ffmpeg", [
    "-loglevel", "error", "-y", "-ss", c.from.toFixed(3), "-i", video, "-t", dur.toFixed(3),
    "-vf", `fps=30,format=yuv420p,fade=t=in:st=0:d=${FADE},fade=t=out:st=${(dur - FADE).toFixed(3)}:d=${FADE}`,
    "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-an", `cuts/${file}`,
  ]);
  list.push(`file '${file}'`);
  console.log(`  ${name.padEnd(15)} ${c.from.toFixed(1)}-${c.to.toFixed(1)}  (${dur.toFixed(1)}s)`);
});
fs.writeFileSync("cuts/list.txt", list.join("\n"));
execFileSync("ffmpeg", ["-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", "cuts/list.txt", "-c", "copy", "-movflags", "+faststart", out]);
const total = cuts.reduce((a, c) => a + (c.to - c.from), 0);
console.log(`wrote ${out} (${total.toFixed(0)}s)`);
