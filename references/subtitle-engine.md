# 字幕：一屏只放一行

## 为什么不能按字数硬切

按字数等分会在词中间下刀，切出「让电 / 脑按步骤」「深圳过去五年新 / 开的高中」这种读不通的断句，
观感比两行字幕更糟。**断点只能落在标点上，宁可每段长短不均。**

## 一、从 SRT + 原稿生成字幕（推荐入口）

```bash
python scripts/build_cues.py --srt audio/source.srt --docx 原稿.docx \
  --out-json data/cues.json --out-srt 字幕.srt --maxline 18
```

它解决的是「ASR 时间轴准、但断句不看语法」这个矛盾：

1. `difflib.SequenceMatcher` 把 ASR 文本 A 和原稿 B 对齐，得到 B 每个字符对应 A 的哪个位置
2. A 的字符有时间（SRT 每条内部按字数线性插值）
3. 于是 B 的每个字符也有时间 —— **时间轴一动不动，只有切点变好**
4. 把 B 按标点切成 ≤18 字显示行
5. 每行起止 = 首字 / 末字时间，再首尾收口（上一条结束 = 下一条开始）
6. 顺手去掉句尾标点

`keji2027` 用这个对齐过 63 条，0 条回退。

## 二、字宽度量（要按渲染宽度算，不按字数）

```js
const PUNCT = '，。、；：！？,.;:!?）)”」';
const cpw = (ch) => /[\u4e00-\u9fff\u3000-\u303f\uff01-\uff60]/.test(ch) ? 1 : 0.56;
function mw(s) { let w = 0; for (const ch of s) w += cpw(ch); return w; }
```

中文 1 个字宽，数字 / 字母 / 空格 0.56。
**上限 `CAPMAX = 26` 字宽**（60px × 26 ≈ 1560px，安全落在 `max-width:1750` 内）。

## 三、断点搜索 `bestCut`

在理想位置（按宽度均分点）附近扫，用惩罚值决定落在哪：

| 断点落在 | 惩罚 |
|---|---|
| 标点上 | 0 |
| 空格上 | 0.6 |
| **词中间** | **14** |

`score = |距理想位置的偏差| + 惩罚`，取最小。惩罚 14 是关键 —— 只要附近有标点，一定轮不到硬切。
两侧都要求 ≥3 字宽，避免切出孤零零一个字。

## 四、时长分摊

不重新计时，只把原 cue 的时窗**按字宽比例**分给各段：

```js
const span = Math.max(0.2, c.e - c.s);
segs.forEach((sg, i) => { const d = span * ws[i] / sum; push({s: t, e: t + d, txt: sg}); t += d; });
```

好处：整条音频时间轴不动，画面切点不用改，只有字幕变多。
规模参考：140 条 SRT → 180 段单行。

## 五、结尾标点必须去掉（红线 2）

```js
const seg = src.slice(cuts[i], cuts[i+1])
  .replace(/^[，。、；：\s]+/, '')
  .replace(/[，。、；：,.;:！？!?…]$/, '')   // ← 必须加这句
  .trim();
```

只清「段尾」，句中的逗号顿号**保留** —— 否则「编程、机器人、科创」会被读成「编程机器人科创」。
问号感叹号也算标点，一并去。

## 六、样式

```css
#cap{ position:absolute; left:50%; bottom:34px; transform:translateX(-50%);
      width:max-content;                     /* ← 见下方陷阱，必须有 */
      max-width:1750px; font-size:60px; font-weight:700; line-height:1.3;
      white-space:nowrap;                    /* ← 红线 1 的物理兜底 */
      color:#fff; text-shadow:0 2px 12px rgba(0,0,0,.7);
      letter-spacing:.02em; text-align:center }
```

`white-space:nowrap` 是最后一道保险：算法出错塞了长句，它会横向溢出被质检抓到，
而不是悄悄折成两行。**不要改成 `normal` 去「自动适应」。**

### ⚠ `left:50% + translateX(-50%)` 会把字幕条砍到半屏

数据层 63 条全是单行，渲染出来却有 6 条变两行。量出来 `barW = 960` —— 正好是 1920 的一半。

原因：绝对定位元素 `left:50%` 且没写 `right` 时，可用宽度 = 容器宽 − left = 960。
shrink-to-fit 取 `min(可用宽, 内容宽)`，所以 `max-width:1700` **一次都没生效过**。

```css
/* ✗ 错的：可用宽只有 960 */
#cap{position:absolute;left:50%;transform:translateX(-50%);max-width:1700px}

/* ✓ 对的：显式给宽度，max-width 才真的管事 */
#cap{position:absolute;left:50%;transform:translateX(-50%);
     width:max-content;max-width:1700px;white-space:nowrap}
```

`width:fit-content` 或 `left:0;right:0;margin:0 auto` 也可以。

**这类问题数据层查不出来，必须量渲染后的高度** —— 跑 `scripts/check_cap_render.cjs`。

## 七、字幕条和满幅烤字图卡抢地方

图卡 1920×1072 在 1080 高的框里 `object-fit:cover`，**垂直方向零余量**：
`scale(1.12)` 只腾出 60px，再放大只会把底部内容推得更低。而这批卡顶部有标题、底部有标签，上下顶满。

结论：**别挪图，把字幕条自己收下去** ——
`bottom:24px` / `font-size:52px` / `padding:12px 34px`，占位从 910~1016 收到 963~1054，
底部标签就全露出来了。只有极少数卡需要整体轻抬，幅度受 `(z-1)*1080/2` 限制，超了就露底。

## 八、数字读法与字幕文本分开

TTS 要口语化（「减」「除以」「百分之」），字幕要保留原符号。
`tools/tts/zh_num.py` 的 `speak()` 负责前者，字幕走原文。**别把两者混成一个字符串。**

## 九、改完必须双层复核

1. **数据层**：`python scripts/check_spec.py data/cues.json --shots shots.js`
   —— 换行 / 超长 / 结尾标点三项零违规。它还能直接改写：`--fix out.json`
   会去句尾标点 + 按标点重切成单行，原时间轴按字宽比例保留。
2. **渲染层**：`node scripts/check_cap_render.cjs index.html`
   —— 逐条渲染量 `getClientRects().length` 和高度，抓「数据单行但浏览器折成两行」。

只做第 1 步不够。**数据是单行、画面是两行，正是踩过的真实故障。**
