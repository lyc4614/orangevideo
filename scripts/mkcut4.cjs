// mkcut4.cjs —— 区域生长泛洪抠图（适配带渐变晕影的 AI 出图底色）
// 用法：node mkcut4.cjs <源图> <输出名> [底部裁掉像素] [padPx] [邻域容差,默认14]
// 输出：<脚本所在工程>/assets/cut/<输出名>.png
// 思路：从四条边出发按"局部颜色连续"泛洪，把与边缘连通的底色判为背景；
//       主体自带明显边缘跳变，泛洪会停在轮廓上。再对 alpha 做 1~2px 羽化。
const fs = require('fs');
const path = require('path');
const { execFileSync: ex } = require('child_process');

function findFF() {
  if (process.env.FFMPEG && fs.existsSync(process.env.FFMPEG)) return process.env.FFMPEG;
  const base = path.join(process.env.LOCALAPPDATA || '', 'Microsoft/WinGet/Packages');
  if (fs.existsSync(base)) {
    for (const d of fs.readdirSync(base)) {
      if (!/FFmpeg/i.test(d)) continue;
      const sub = path.join(base, d);
      for (const v of fs.readdirSync(sub)) {
        const p = path.join(sub, v, 'bin', 'ffmpeg.exe');
        if (fs.existsSync(p)) return p;
      }
    }
  }
  for (const p of ['/usr/bin/ffmpeg', '/usr/local/bin/ffmpeg']) if (fs.existsSync(p)) return p;
  return 'ffmpeg';
}

const FF = findFF();
const FP = FF.replace(/ffmpeg(\.exe)?$/, (m) => (m === 'ffmpeg.exe' ? 'ffprobe.exe' : 'ffprobe'));
const DIR = path.join(process.cwd(), 'assets/cut');
fs.mkdirSync(DIR, { recursive: true });

const [src, out, cropBottomArg, padArg, tolArg] = process.argv.slice(2);
const cropBottom = +(cropBottomArg || 0);
const pad = padArg == null ? 12 : +padArg;
const TOL = tolArg == null ? 14 : +tolArg;

const probe = (f) => {
  const o = ex(FP, ['-v', 'error', '-select_streams', 'v:0', '-show_entries',
    'stream=width,height', '-of', 'csv=p=0', f]).toString().trim();
  const [w, h] = o.split(',').map(Number);
  return { w, h };
};

const { w: W, h: H0 } = probe(src);
const H = H0 - cropBottom;
const rgb = ex(FF, ['-v', 'error', '-i', src, '-vf', `crop=${W}:${H}:0:0`,
  '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { maxBuffer: 1 << 28 });

const N = W * H;
const isBG = new Uint8Array(N);
const stack = new Int32Array(N);
let sp = 0;
const push = (p) => { if (!isBG[p]) { isBG[p] = 1; stack[sp++] = p; } };

for (let x = 0; x < W; x++) { push(x); push((H - 1) * W + x); }
for (let y = 0; y < H; y++) { push(y * W); push(y * W + W - 1); }

while (sp > 0) {
  const p = stack[--sp];
  const x = p % W, y = (p - x) / W;
  const o = p * 3;
  const r = rgb[o], g = rgb[o + 1], b = rgb[o + 2];
  const nb = [];
  if (x > 0) nb.push(p - 1);
  if (x < W - 1) nb.push(p + 1);
  if (y > 0) nb.push(p - W);
  if (y < H - 1) nb.push(p + W);
  for (const q of nb) {
    if (isBG[q]) continue;
    const j = q * 3;
    const d = Math.max(Math.abs(rgb[j] - r), Math.abs(rgb[j + 1] - g), Math.abs(rgb[j + 2] - b));
    if (d <= TOL) push(q);
  }
}

let bgCount = 0;
for (let p = 0; p < N; p++) if (isBG[p]) bgCount++;
const bgRatio = bgCount / N;
if (bgRatio < 0.02) throw new Error(`背景只占 ${(bgRatio * 100).toFixed(1)}%，泛洪没走通，加大容差`);
if (bgRatio > 0.97) throw new Error(`背景占 ${(bgRatio * 100).toFixed(1)}%，主体被吃掉了，降低容差`);

// alpha：背景 0，主体 255
let a = new Float32Array(N);
for (let p = 0; p < N; p++) a[p] = isBG[p] ? 0 : 255;

// 羽化：3x3 均值两遍
for (let pass = 0; pass < 2; pass++) {
  const b2 = new Float32Array(N);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      let s = 0, c = 0;
      for (let dy = -1; dy <= 1; dy++) {
        const yy = y + dy; if (yy < 0 || yy >= H) continue;
        for (let dx = -1; dx <= 1; dx++) {
          const xx = x + dx; if (xx < 0 || xx >= W) continue;
          s += a[yy * W + xx]; c++;
        }
      }
      b2[y * W + x] = s / c;
    }
  }
  a = b2;
}

// 回写 RGBA（对边缘像素做一次轻微去底色污染）
const rgba = Buffer.alloc(N * 4);
for (let p = 0, o = 0; p < N; p++, o += 4) {
  let al = Math.round(a[p]);
  al = al < 24 ? 0 : al > 232 ? 255 : Math.round(((al - 24) / 208) * 255);
  rgba[o] = rgb[p * 3];
  rgba[o + 1] = rgb[p * 3 + 1];
  rgba[o + 2] = rgb[p * 3 + 2];
  rgba[o + 3] = al;
}

// bbox（alpha>40）
let x0 = W, y0 = H, x1 = -1, y1 = -1;
for (let y = 0; y < H; y++) {
  for (let x = 0; x < W; x++) {
    if (rgba[(y * W + x) * 4 + 3] > 40) {
      if (x < x0) x0 = x; if (x > x1) x1 = x;
      if (y < y0) y0 = y; if (y > y1) y1 = y;
    }
  }
}
const cx = Math.max(0, x0 - pad), cy = Math.max(0, y0 - pad);
const cw = Math.min(W - cx, (x1 - x0 + 1) + pad * 2);
const ch = Math.min(H - cy, (y1 - y0 + 1) + pad * 2);

const full = path.join(DIR, '_a_' + out + '.png');
const dst = path.join(DIR, out + '.png');
ex(FF, ['-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', `${W}x${H}`,
  '-i', '-', full], { input: rgba, maxBuffer: 1 << 28 });
ex(FF, ['-v', 'error', '-y', '-i', full, '-vf', `crop=${cw}:${ch}:${cx}:${cy}`, dst]);
fs.unlinkSync(full);

console.log(JSON.stringify({
  out: out + '.png', bgRatio: +bgRatio.toFixed(3), tol: TOL,
  bbox: { x: x0, y: y0, w: x1 - x0 + 1, h: y1 - y0 + 1 }, crop: [cw, ch, cx, cy]
}));
