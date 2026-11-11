---
name: orangevideo
description: |
  橙子老师视频成片流水线（口播音频 / 文稿 / 图卡 → 横屏成片）。本 skill 是「做视频」类任务的
  唯一入口：做视频、出成片、剪一条片子、改这条片子、根据文稿或 SRT 做口播视频、写分镜、
  配字幕、给图卡做动画、渲染、压片、交付。
  承载四条不能破的视觉红线（字幕单行不换行、结尾不带标点、图片是主体解释动画是标点、
  画面不留非必要小字）、字幕引擎、3D 素材取用与自生成抠图、渲染编码、响度与交付规矩。
license: MIT
agent_created: true
---

# Orangevideo · 橙子老师视频流水线

这套东西是踩出来的，不是想出来的。**不要相信记忆，开工先读这份文件；
不要相信眼睛，交付前跑脚本。** 每条规矩下面都写着哪条片子在哪一步栽过。

## 〇、四条红线（破了必须重做，不许「下一版再说」）

| # | 红线 | 怎么判违规 | 正确做法 |
|---|---|---|---|
| 1 | **字幕单行，绝不换行** | 一条字幕出现 `\n`，或渲染成两行 | 拆成多条（每条 ≤26 字宽），见 [references/subtitle-engine.md](references/subtitle-engine.md) |
| 2 | **字幕结尾不带标点** | 末尾是 `，。、；：！？` 或 `.` `,` | 去掉。句中的逗号顿号照常保留，否则「编程、机器人、科创」会被读断 |
| 3 | **图片是主体，解释动画是标点** | `full` > 65%（图片轮播）或 < 30%（把用户给的图全糊掉了）；`blur/hero` < 25%（没有解释层）；解释层镜既无 `type` 也无 3D 素材 | `full` 30–65% / `blur·hero` 25–45% / `plain` ≤15%。见 [references/visual-rules.md](references/visual-rules.md) |
| 4 | **画面不留非必要小字** | 出现「注：」「来源：」「以上数据…」这类解释性小字 | 删。只留主信息 + 关键数字 |

> **红线 3 是双边约束，两个方向都算错。**
> 2026-11-11 第一次把方向做反：把用户上传的图卡全糊成深色底，`full` 只剩 8%。用户原话：
> 「大部分还是用我给你上传的图片，适合用解释动画，或者强调句子的时候再给图片背景上模糊……
> 这是为了丰富画面内容，不是让你只这么做。」
> 反方向是 `full` 100%（纯图卡轮播），同样被点名。
> 而且**解释层必须有实体** —— 3D 素材或图形组件，不能只有「深色底 + 三行字」，那等于没讲。

红线 4 的两个补充（同属「保持画面纯净」）：
- 章号 `01` 已在大字里，**不要再写 `01 / 05`** —— 重复信息就是脏。
- 标题和卡片内容**不要互相复述**（标题「总分变了 610→630」+ 卡里又是 610/630 = 白占地方）。

## 一、起片 SOP（按顺序做，别跳）

```bash
# ① 字幕：SRT 时间轴 + 原稿标点 双源合并 → 单行、无句尾标点
python scripts/build_cues.py --srt audio/source.srt --docx 原稿.docx \
    --out-json data/cues.json --out-srt 字幕.srt --maxline 18
python scripts/check_spec.py data/cues.json --fix data/cues.json   # 兜底再洗一遍

# ② 素材过一遍「不看字幕能不能猜出在讲什么」
#    对不上 → 翻素材库 → 再不行 ImageGen 生成（先告知积分成本）→ mkcut4 抠图

# ③ 分镜表：先数模式配比，再写内容
#    full 30–65% / blur·hero 25–45% / plain ≤15%，单镜 ≤ 11s
#    一镜一图的写法在这一步就会变成图片轮播

# ④ 引擎：拷成熟工程的 index.html + shots.js，只换 SHOTS 数组和 assets/
#    后半段引擎（build / hero / stage / shelf / fade）不要重写

# ⑤ 静帧验收：先出 8–10 张静帧人眼过一遍，再开全片
TIMES=48.5,80.5,119 node scripts/still.cjs

# ⑥ 全片渲染 + 编码
PUPPETEER_NM="<含 puppeteer-core 的 node_modules>" \
  FRAME_DIR=frames_v3 OUT=out_v3.mp4 node scripts/render.cjs

# ⑦ 两遍 loudnorm 混流 + 四项体检
python scripts/mkloudnorm.py --in audio/pp.wav --video out_v3.mp4 --out 成片.mp4
```

## 二、画面素材的取用顺序（红线 3 的落地）

前一级能用就不要跳到下一级：

1. **用户已有的图卡 / 海报** —— 当 `full` 用，但只能占少数。烤字图卡推镜**不超过 1.12**，否则切字。
2. **3D 素材库** —— `素材库/中考抢分3D素材包_73项/`，57 张透明主体 + 16 张场景，先开 `图册.html` 找。
3. **自己生成** —— 前两级都解释不了这段文稿时用 ImageGen。**必须先告知积分成本
   （5–10 credits/张）再调。** 品红底出图 → `mkcut4.cjs` 泛洪抠图 → 进 `assets/mat/`。
4. **纯 CSS 图形** —— 柱状、阶梯、天平、时间轴、数字跳动，`html-timeline-video` 有现成组件。

判断标准只有一条：**这个画面有没有真的把这句话讲清楚。**
讲不清楚的图，再好看也不要用。见 [references/assets-3d.md](references/assets-3d.md)。

## 三、脚本速查

| 脚本 | 用途 | 关键参数 |
|---|---|---|
| `scripts/build_cues.py` | SRT + 原稿 → 单行字幕 | `--srt --docx/--txt --out-json --maxline` |
| `scripts/check_spec.py` | **字幕数据层 + 分镜配比**体检 | `--shots shots.js`；`--fix out.json` 可改写 |
| `scripts/check_cap_render.cjs` | **字幕渲染层**体检（抓浏览器折行） | `<index.html>` |
| `scripts/still.cjs` | 按时间点出静帧验收 | `TIMES=48.5,80.5` |
| `scripts/render.cjs` | 逐帧渲染 + 编码 | `FRAME_DIR` `OUT` `START` `END` `NOENC` |
| `scripts/mkloudnorm.py` | 两遍 loudnorm，可直出混流 | `--in --out --video --measure` |
| `scripts/mkcut4.cjs` | 品红底泛洪抠图 | `<源图> <名字> [裁底部px] [pad] [容差]` |

`check_spec.py` 判定口径：`full` 30–65%、`blur·hero` ≥25%、解释层既无 `type` 也无 `mat` 直接报错、
单镜 > 11s 提示、字幕超 26 字宽 / 含换行 / 句尾带标点报错。

## 四、交付前 checklist（缺一项都不算完成）

- [ ] `check_spec.py --shots shots.js` 零红线违规
- [ ] `check_cap_render.cjs` 全部单行，且字幕条宽度 > 1500px（< 1500 说明可用宽被砍半）
- [ ] **每一镜**都抽帧看过（不是抽查）
- [ ] 字幕没盖住画面里烤死的文字
- [ ] 每个 `hero` 镜的素材，不看字幕也能猜出这句话在讲什么
- [ ] 响度 `-16.7±0.6 LUFS` / `≤ -1.0 dBTP`（两遍 loudnorm）
- [ ] 0 黑帧 / 0 长静音
- [ ] 编码显式转 TV range（`in_range=full:out_range=tv`）
- [ ] 口播跑过复读检测（用户对这条最敏感）
- [ ] 成片只在 `~/Desktop/视频成品/<片名>/` 一处，桌面根目录无 mp4
- [ ] 旧版进 `_归档_旧版本/`，没删

## 五、参考文件

| 文件 | 什么时候读 |
|---|---|
| [references/subtitle-engine.md](references/subtitle-engine.md) | 改字幕、字幕折行、SRT 断句、字宽度量、960 陷阱 |
| [references/visual-rules.md](references/visual-rules.md) | 定分镜、调配比、`hero`/`blur`/`plain` 参数、版面固定值 |
| [references/assets-3d.md](references/assets-3d.md) | 找素材、ImageGen 生成、抠图、素材对不上文本 |
| [references/audio-tts.md](references/audio-tts.md) | 口播、音色、数字读法、复读检测、响度 |
| [references/render-pipeline.md](references/render-pipeline.md) | 渲染、编码、体检、交付归档、工程目录 |

## 六、反例存档（2026-11-10 `keji2027`，用户点名批评）

| 违规 | 表现 |
|---|---|
| 红线 1 | 63 条里 6 条渲染成两行。数据层其实全是单行 —— CSS 把字幕条砍到 960 宽（`left:50%` 没配 `right`） |
| 红线 2 | 每条字幕都以 `，` `。` 结尾（63 条里 61 条） |
| 红线 3 | 15 张图卡一路推镜轮播，`full` 100%，全片没有一条解释层 |
| 红线 4 | 图卡上的次要标签、小字全部保留 |

一条命令体检出 66 条红线违规 / 6 条渲染层折行。**素材是对的，做法是错的。**

返工时又错到另一头：25 镜里 20 镜做成「模糊底 + 几行字」，`full` 只剩 8%，
用户上传的图卡全被糊掉，当天就被拍回来。
最终版 `keji2027b/` 落在 full 56% / hero 32% / plain 12%，两个方向都不碰边。

**一句话：图片是主体，解释动画是标点。**
全程只有逗号（全是解释层）和全程没有标点（全是图片）一样糟。

## 七、参考工程

| 抄什么 | 看哪里 |
|---|---|
| **合规范本**（可直接当模板起新片） | `examples/keji2027b/`（25 镜，142s，full 56/hero 32/plain 12） |
| 镜头结构（配比、模糊底、stage/shelf） | `examples/xingaozhong/`（87 镜） |
| 分镜骨架（`build_shots.py` + 双图层） | `examples/qiangfen2027/` |
| 技术方法论（渲染提速、几何体检、踩坑清单） | 技能 `html-timeline-video`（3323 行，先读「何时用 / 不用」） |

> ⚠ `xingaozhong` 的字幕是旧版做法：保证单行，但**保留了句尾标点**（`splitSegs` 只清段首）。
> 抄它的镜头，别抄它的标点。

### 本地资产（不在本仓库内）

下面这些是本项目配套的私有资产，**没有随仓库发布**，仓库里的路径只是命名示意：

| 路径 | 内容 | 拿不到怎么办 |
|---|---|---|
| `examples/<工程名>/` | 完整工程（`index.html` + `shots.js` + 素材），含真实片子的图卡 | 照 `references/visual-rules.md` 自己搭，`hero` 版式的 DOM 和 CSS 都在文档里 |
| `素材库/中考抢分3D素材包_73项/` | 73 张 3D 素材（57 透明主体 + 16 场景） | 用 `references/assets-3d.md` 的 ImageGen 锚点自己生成，或换你自己的素材库 |
| `tools/tts/` | 音色标准 `voice_standard.json`、数字读法 `zh_num.py`、复读检测 `detect_repeat.py` | 接你自己的 TTS；复读检测的判据在 `references/audio-tts.md` 里写全了，照着重写不到 100 行 |

脚本本身**不依赖**这些资产：`check_spec.py` / `check_cap_render.cjs` / `still.cjs` / `render.cjs` /
`build_cues.py` / `mkloudnorm.py` / `mkcut4.cjs` 都只吃你给的文件和参数。
