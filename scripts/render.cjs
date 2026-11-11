// render.cjs —— 横屏 1920×1080 逐帧渲染
// 用法：node render.cjs            全片
//       START=0 END=70 node render.cjs   只渲 0-70 秒（样片）
// 解析 puppeteer-core：优先本地 node_modules，其次环境变量 PUPPETEER_NM 指向的 node_modules 目录
function loadPuppeteer() {
  try { return require('puppeteer-core'); } catch (e) { /* 继续找 */ }
  const sep = require('path').delimiter;
  const bases = [process.env.PUPPETEER_NM, process.env.NODE_PATH]
    .filter(Boolean).join(sep).split(sep);
  for (const b of bases) {
    if (!b) continue;
    try { return require(require('path').join(b, 'puppeteer-core')); } catch (e) { /* 继续 */ }
  }
  throw new Error('找不到 puppeteer-core。设 PUPPETEER_NM 指向含 puppeteer-core 的 node_modules 目录');
}
const puppeteer = loadPuppeteer();
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execFileSync } = require('child_process');

// 工程根目录 = 当前工作目录（脚本本体在技能目录里，__dirname 不能用）
const ROOT = process.env.PROJ || process.cwd();
const CW = 1920, CH = 1080;
const DSF = +(process.env.DSF || 1);
const FPS = +(process.env.VIDEO_FPS || 30);
const FRAMES = path.join(ROOT, process.env.FRAME_DIR || 'frames');
const OUT = path.join(ROOT, process.env.OUT || 'out.mp4');

function firstExisting(list) { for (const p of list) if (p && fs.existsSync(p)) return p; return null; }
function findChrome() {
  return firstExisting([
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    (process.env.LOCALAPPDATA || '') + '/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
  ]);
}
function findFfmpeg() {
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
  return 'ffmpeg';
}
const log = (m) => process.stdout.write(m + '\n');

(async () => {
  if (!fs.existsSync(FRAMES)) fs.mkdirSync(FRAMES, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: findChrome(), headless: 'new',
    userDataDir: path.join(os.tmpdir(), 'xg-render-' + Date.now() + '-' + process.pid),
    args: ['--no-sandbox', '--hide-scrollbars', '--force-device-scale-factor=1',
      '--disable-lcd-text', '--font-render-hinting=none', '--allow-file-access-from-files',
      '--disable-gpu', '--disable-dev-shm-usage']
  });
  const page = await browser.newPage();
  await page.setCacheEnabled(false);
  page.on('pageerror', e => log('PAGEERROR ' + e.message));
  await page.setViewport({ width: CW, height: CH, deviceScaleFactor: DSF });
  await page.goto('file:///' + path.join(ROOT, 'index.html').replace(/\\/g, '/'), { waitUntil: 'load' });
  await page.waitForFunction('typeof window.__render === "function"');
  await page.evaluate(async () => {
    await Promise.all([...document.fonts].map(f => document.fonts.load(`${f.weight} 64px "${f.family}"`, '测试0123').catch(() => {})));
    await document.fonts.ready;
    // 只等真的有 src 的图；空 <img> 的 complete 为 true 但自然宽为 0，
    // 若不排除，onload 永远不触发，evaluate 会挂到 protocolTimeout。
    const pend = [].slice.call(document.images)
      .filter(im => im.getAttribute('src') && !(im.complete && im.naturalWidth))
      .map(im => new Promise(r => { im.onload = r; im.onerror = r; setTimeout(r, 3000); }));
    await Promise.all(pend);
  });
  await new Promise(r => setTimeout(r, 400));

  const DUR = await page.evaluate('window.__duration');
  const START = +(process.env.START || 0);
  const END = Math.min(+(process.env.END || DUR), DUR);
  const total = Math.round((END - START) * FPS);
  const OFF = +(process.env.OFFSET || 0);
  log(`duration=${DUR} range=${START}-${END} frames=${total} dsf=${DSF}`);

  const t0 = Date.now();
  for (let i = 0; i < total; i++) {
    const t = START + i / FPS;
    await page.evaluate((tt) => window.__render(tt), t);
    await page.screenshot({
      type: 'jpeg', quality: 93,
      path: path.join(FRAMES, 'f-' + String(i + OFF).padStart(5, '0') + '.jpg')
    });
    if (i % 300 === 0 || i === total - 1) log(`f ${i + 1}/${total} ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  await browser.close();
  log('frames done ' + ((Date.now() - t0) / 1000).toFixed(1) + 's');
  if (process.env.NOENC) { log('SKIP ENCODE'); return; }

  execFileSync(findFfmpeg(), ['-y', '-framerate', String(FPS), '-i', path.join(FRAMES, 'f-%05d.jpg'),
    '-vf', 'scale=in_range=full:out_range=tv:flags=lanczos,format=yuv420p',
    '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
    '-c:v', 'libx264', '-crf', '19', '-preset', 'medium', '-pix_fmt', 'yuv420p',
    '-r', String(FPS), '-movflags', '+faststart', OUT], { stdio: 'inherit' });
  log('DONE ' + OUT);
})().catch(e => { log('ERROR ' + (e && e.stack || e)); process.exit(1); });
