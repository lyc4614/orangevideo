// still.cjs —— 按时间点出静帧，用于验收单镜
// 用法：TIMES=48.5,80 node still.cjs
// 输出：_probe/still_<t>.png
// 解析 puppeteer-core：优先本地 node_modules，其次环境变量 PUPPETEER_NM 指向的 node_modules 目录
function loadPuppeteer() {
  try { return require('puppeteer-core'); } catch (e) { /* 继续找 */ }
  const bases = [process.env.PUPPETEER_NM, process.env.NODE_PATH]
    .filter(Boolean).join(require('path').delimiter).split(require('path').delimiter);
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

// 工程根目录 = 当前工作目录（脚本本体在技能目录里，__dirname 不能用）
const ROOT = process.env.PROJ || process.cwd();
const CW = 1920, CH = 1080;
const OUTDIR = path.join(ROOT, '_probe');
const TIMES = (process.env.TIMES || '0').split(',').map(Number);

function firstExisting(list) { for (const p of list) if (p && fs.existsSync(p)) return p; return null; }
const CHROME = firstExisting([
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  (process.env.LOCALAPPDATA || '') + '/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
]);

(async () => {
  fs.mkdirSync(OUTDIR, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: 'new',
    userDataDir: path.join(os.tmpdir(), 'xg-still-' + Date.now()),
    args: ['--no-sandbox', '--hide-scrollbars', '--force-device-scale-factor=1',
      '--disable-lcd-text', '--font-render-hinting=none', '--allow-file-access-from-files',
      '--disable-gpu', '--disable-dev-shm-usage']
  });
  const page = await browser.newPage();
  await page.setCacheEnabled(false);
  page.on('pageerror', e => console.log('PAGEERROR ' + e.message));
  await page.setViewport({ width: CW, height: CH, deviceScaleFactor: 1 });
  await page.goto('file:///' + path.join(ROOT, 'index.html').replace(/\\/g, '/'), { waitUntil: 'load' });
  await page.waitForFunction('typeof window.__render === "function"');
  await page.evaluate(async () => {
    await document.fonts.ready;
    const pend = [].slice.call(document.images)
      .filter(im => im.getAttribute('src') && !(im.complete && im.naturalWidth))
      .map(im => new Promise(r => { im.onload = r; im.onerror = r; setTimeout(r, 3000); }));
    await Promise.all(pend);
  });
  await new Promise(r => setTimeout(r, 400));
  for (const t of TIMES) {
    await page.evaluate((tt) => window.__render(tt), t);
    await new Promise(r => setTimeout(r, 120));
    const f = path.join(OUTDIR, 'still_' + String(t).replace('.', '_') + '.png');
    await page.screenshot({ path: f });
    console.log('OK ' + f);
  }
  await browser.close();
})().catch(e => { console.log('ERROR ' + (e && e.stack || e)); process.exit(1); });
