// check_cap_render.cjs —— 渲染层验证「字幕真的只有一行」
//
// 数据层过了 check_spec.py 不代表没换行：CSS 会把长句悄悄折行。
// 实测踩过：`left:50%; transform:translateX(-50%)` 没有配 `right`，
// 绝对定位元素的可用宽度只有半个舞台（1920 → 960），`max-width:1700` 形同虚设，
// 63 条字幕里 6 条被浏览器折成两行 —— 数据是单行的，画面是两行的。
//
// 用法：
//   NODE_PATH=<有 puppeteer-core 的 node_modules> node check_cap_render.cjs [index.html]
//   默认读同目录 index.html，要求页面暴露 window.CUES 和 window.__render(t)
// 退出码：0 全部单行；1 有换行或超出安全宽度

const path = require('path');
const os = require('os');
const fs = require('fs');

// 解析 puppeteer-core：优先本地 node_modules，其次环境变量 PUPPETEER_NM / NODE_PATH
function loadPuppeteer() {
  try { return require('puppeteer-core'); } catch (e) { /* 继续找 */ }
  const sep = path.delimiter;
  const bases = [process.env.PUPPETEER_NM, process.env.NODE_PATH]
    .filter(Boolean).join(sep).split(sep);
  for (const b of bases) {
    if (!b) continue;
    try { return require(path.join(b, 'puppeteer-core')); } catch (e) { /* 继续 */ }
  }
  throw new Error('找不到 puppeteer-core。设 PUPPETEER_NM 指向含 puppeteer-core 的 node_modules 目录');
}
const puppeteer = loadPuppeteer();

// 工程根目录 = 当前工作目录（脚本本体在技能目录里，__dirname 不能用）
const ROOT = process.env.PROJ || process.cwd();
const PAGE = process.argv[2] ? path.resolve(process.argv[2]) : path.join(ROOT, 'index.html');
const MAX_W = 1750;       // 横向安全宽度
const SAFE_H = 1.6;       // 行高倍数上限（1 行 = 1.0，2 行 ≈ 2.0）

function findChrome() {
  const c = [
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    (process.env.LOCALAPPDATA || '') + '/Google/Chrome/Application/chrome.exe',
  ];
  for (const p of c) if (fs.existsSync(p)) return p;
  throw new Error('找不到 Chrome');
}

(async () => {
  const browser = await puppeteer.launch({
    executablePath: findChrome(),
    headless: 'new',
    userDataDir: path.join(os.tmpdir(), 'capchk-' + Date.now() + '-' + process.pid),
    args: ['--no-sandbox', '--disable-gpu', '--allow-file-access-from-files'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.goto('file:///' + PAGE.replace(/\\/g, '/'), { waitUntil: 'load' });
  await page.waitForFunction('typeof window.__render === "function"');
  await page.evaluate(async () => {
    await document.fonts.ready;
  });

  const res = await page.evaluate(async (MAX_W, SAFE_H) => {
    // `const CUES = [...]` 不会挂到 window 上，但同作用域可直接引用
    const CUESX = typeof CUES !== 'undefined' ? CUES : window.CUES || [];
    const bar = document.getElementById('capbar') || document.querySelector('[id*="cap"]');
    if (!bar) return { error: '页面上找不到字幕条元素（id 含 cap）' };
    const inner = bar.querySelector('span') || bar;
    const barW = bar.getBoundingClientRect().width;
    const lh = parseFloat(getComputedStyle(bar).lineHeight) || 1;
    const fs = parseFloat(getComputedStyle(bar).fontSize) || 1;
    const oneLine = lh > 1.5 ? lh : fs * lh;

    const bad = [];
    let maxW = 0;
    for (const c of CUESX) {
      const t = (c.s !== undefined ? c.s : c.t0) + 0.02;
      window.__render(t);
      await new Promise((r) => setTimeout(r, 18));
      const bb = bar.getBoundingClientRect();
      if (bb.width > maxW) maxW = bb.width;
      const rects = inner.getClientRects().length;
      const lines = Math.round(bb.height / oneLine);
      const txt = c.t !== undefined ? c.t : c.text;
      if (rects > 1 || lines > 1 || bb.height > oneLine * SAFE_H) {
        bad.push({ t: txt, lines, h: Math.round(bb.height), barW: Math.round(bb.width) });
      } else if (bb.width > MAX_W) {
        bad.push({ t: txt, lines, h: Math.round(bb.height), barW: Math.round(bb.width), over: true });
      }
    }
    return { total: CUESX.length, barW: Math.round(barW), maxW: Math.round(maxW), oneLine: Math.round(oneLine), bad };
  }, MAX_W, SAFE_H);

  await browser.close();

  if (res.error) {
    console.log('✗ ' + res.error);
    process.exit(2);
  }
  console.log(`· 字幕 ${res.total} 条，单行基准高 ${res.oneLine}px，字幕条最宽 ${res.maxW}px`);
  if (res.bad.length && res.maxW < 1500) {
    console.log(
      `! 字幕条最宽只有 ${res.maxW}px —— 典型原因：left:50% 没配 right，` +
        `可用宽度被砍半（1920 → 960），max-width 形同虚设。` +
        `修法：加 width:max-content，或改 left:0;right:0;margin:0 auto;width:fit-content。`
    );
  }
  for (const b of res.bad) {
    console.log(`✗ ${b.lines} 行 / 高 ${b.h}px / 宽 ${b.barW}px：${b.t}`);
  }
  console.log();
  console.log(res.bad.length ? `${res.bad.length} 条不是单行 —— 不通过` : '全部单行 —— 通过');
  process.exit(res.bad.length ? 1 : 0);
})().catch((e) => {
  console.log('ERROR', e.stack || e);
  process.exit(2);
});
